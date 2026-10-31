"""Thread-safe WebSocket client registry and per-client send queues."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass, field
import logging
import queue
import threading
import time
from typing import Any

from fastapi import WebSocket

from app.ws.message_contract import MAX_SENSOR_UPDATE_BYTES, encode_message

logger = logging.getLogger(__name__)


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
        close_timeout_seconds: float = 1.0,
    ):
        self.max_message_bytes = max_message_bytes
        self.max_message_age_seconds = max_message_age_seconds
        self.close_timeout_seconds = close_timeout_seconds
        self._channels: dict[WebSocket, _ClientChannel] = {}
        self._close_tasks: set[asyncio.Task[None]] = set()
        self._lock = threading.RLock()

    @property
    def active_connections(self) -> list[WebSocket]:
        with self._lock:
            return list(self._channels)

    @property
    def connection_count(self) -> int:
        with self._lock:
            return len(self._channels)

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        channel = _ClientChannel(
            websocket=websocket,
            loop=asyncio.get_running_loop(),
            wakeup=asyncio.Event(),
        )
        with self._lock:
            self._channels[websocket] = channel

        channel.sender_task = asyncio.create_task(
            self._send_from_queue(channel),
            name=f"ws-sender-{id(websocket)}",
        )
        logger.info("WebSocket client connected; active=%d", self.connection_count)

    def disconnect(self, websocket: WebSocket) -> None:
        with self._lock:
            channel = self._channels.pop(websocket, None)
            active_count = len(self._channels)

        if channel is not None:
            try:
                channel.loop.call_soon_threadsafe(
                    self._cancel_sender_and_close,
                    channel,
                )
            except RuntimeError:
                logger.debug("Event loop already closed for WebSocket client")
        logger.info("WebSocket client disconnected; active=%d", active_count)

    def _cancel_sender_and_close(self, channel: _ClientChannel) -> None:
        if channel.sender_task is not None:
            channel.sender_task.cancel()
        task = asyncio.create_task(
            self._close_websocket(channel.websocket),
            name=f"ws-close-{id(channel.websocket)}",
        )
        self._close_tasks.add(task)
        task.add_done_callback(self._close_tasks.discard)

    async def _close_websocket(self, websocket: WebSocket) -> None:
        try:
            await asyncio.wait_for(
                websocket.close(),
                timeout=self.close_timeout_seconds,
            )
        except Exception:
            logger.debug("WebSocket close did not complete cleanly", exc_info=True)

    def enqueue_broadcast(
        self,
        data: Mapping[str, Any],
        *,
        queued_at: float | None = None,
    ) -> None:
        """Queue one shared payload for every currently connected client."""
        message = encode_message(data)
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
