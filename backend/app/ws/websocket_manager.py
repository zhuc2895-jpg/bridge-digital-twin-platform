"""Thread-safe WebSocket client registry and per-client send queues."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import json
import logging
import queue
import threading
import time
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)

MAX_SENSOR_UPDATE_BYTES = 10 * 1024


class MessageTooLargeError(ValueError):
    """Raised when a WebSocket payload exceeds the configured byte limit."""


@dataclass(frozen=True, slots=True)
class _QueuedMessage:
    text: str
    queued_at: float


@dataclass
class _ClientChannel:
    websocket: WebSocket
    loop: asyncio.AbstractEventLoop
    wakeup: asyncio.Event
    messages: queue.Queue[_QueuedMessage] = field(
        default_factory=lambda: queue.Queue(maxsize=4)
    )
    sender_task: asyncio.Task[None] | None = None


class WebSocketManager:
    """Own one connection list and one bounded send queue per client.

    The live data producer runs in a dedicated thread, so queue insertion and
    wake-up calls must be safe to invoke from a different event-loop thread.
    """

    def __init__(
        self,
        max_message_bytes: int = MAX_SENSOR_UPDATE_BYTES,
        max_message_age_seconds: float = 0.5,
    ):
        self.max_message_bytes = max_message_bytes
        self.max_message_age_seconds = max_message_age_seconds
        self.active_connections: list[WebSocket] = []
        self._channels: dict[WebSocket, _ClientChannel] = {}
        self._lock = threading.RLock()

    @property
    def connection_count(self) -> int:
        with self._lock:
            return len(self.active_connections)

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        channel = _ClientChannel(
            websocket=websocket,
            loop=asyncio.get_running_loop(),
            wakeup=asyncio.Event(),
        )
        with self._lock:
            self.active_connections.append(websocket)
            self._channels[websocket] = channel

        channel.sender_task = asyncio.create_task(
            self._send_from_queue(channel),
            name=f"ws-sender-{id(websocket)}",
        )
        logger.info("WebSocket client connected; active=%d", self.connection_count)

    def disconnect(self, websocket: WebSocket) -> None:
        with self._lock:
            channel = self._channels.pop(websocket, None)
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)
            active_count = len(self.active_connections)

        if channel is not None:
            try:
                channel.loop.call_soon_threadsafe(
                    self._cancel_sender_and_close,
                    channel,
                )
            except RuntimeError:
                logger.debug("Event loop already closed for WebSocket client")
        logger.info("WebSocket client disconnected; active=%d", active_count)

    @staticmethod
    def _cancel_sender_and_close(channel: _ClientChannel) -> None:
        if channel.sender_task is not None:
            channel.sender_task.cancel()
        asyncio.create_task(WebSocketManager._close_websocket(channel.websocket))

    @staticmethod
    async def _close_websocket(websocket: WebSocket) -> None:
        try:
            await websocket.close()
        except Exception:
            logger.debug("WebSocket was already closed", exc_info=True)

    @staticmethod
    def encode(data: dict[str, Any]) -> str:
        return json.dumps(data, ensure_ascii=False, separators=(",", ":"))

    def enqueue_broadcast(
        self,
        data: dict[str, Any],
        *,
        queued_at: float | None = None,
    ) -> None:
        """Queue one shared payload for every currently connected client."""
        message = self.encode(data)
        self._validate_message_size(message)
        queued = _QueuedMessage(
            text=message,
            queued_at=time.monotonic() if queued_at is None else queued_at,
        )
        with self._lock:
            channels = list(self._channels.values())

        for channel in channels:
            self._enqueue(channel, queued)

    def _validate_message_size(self, message: str) -> None:
        size = len(message.encode("utf-8"))
        if size > self.max_message_bytes:
            raise MessageTooLargeError(
                f"WebSocket message is {size} bytes; limit is "
                f"{self.max_message_bytes} bytes"
            )

    def _enqueue(self, channel: _ClientChannel, message: _QueuedMessage) -> None:
        try:
            channel.messages.put_nowait(message)
        except queue.Full:
            logger.warning(
                "Disconnecting WebSocket client that cannot keep up with broadcasts"
            )
            self.disconnect(channel.websocket)
            return

        try:
            channel.loop.call_soon_threadsafe(channel.wakeup.set)
        except RuntimeError:
            self.disconnect(channel.websocket)

    async def _send_from_queue(self, channel: _ClientChannel) -> None:
        try:
            while True:
                await channel.wakeup.wait()
                channel.wakeup.clear()
                while True:
                    try:
                        message = channel.messages.get_nowait()
                    except queue.Empty:
                        break
                    remaining = self.max_message_age_seconds - (
                        time.monotonic() - message.queued_at
                    )
                    if remaining <= 0:
                        logger.warning(
                            "Disconnecting WebSocket client with stale queued frames"
                        )
                        self.disconnect(channel.websocket)
                        return
                    try:
                        await asyncio.wait_for(
                            channel.websocket.send_text(message.text),
                            timeout=remaining,
                        )
                    except TimeoutError:
                        logger.warning(
                            "Disconnecting WebSocket client whose send exceeded "
                            "the latency deadline"
                        )
                        self.disconnect(channel.websocket)
                        return
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("WebSocket send failed; removing client")
            self.disconnect(channel.websocket)
