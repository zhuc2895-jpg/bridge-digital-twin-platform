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


@dataclass
class _ClientChannel:
    websocket: WebSocket
    loop: asyncio.AbstractEventLoop
    wakeup: asyncio.Event
    messages: queue.Queue[tuple[str, float]] = field(
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
        self._latest_message: tuple[str, float] | None = None
        self._lock = threading.RLock()

    @property
    def connection_count(self) -> int:
        with self._lock:
            return len(self.active_connections)

    def has_connections(self) -> bool:
        return self.connection_count > 0

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
            latest_message = self._latest_message

        channel.sender_task = asyncio.create_task(
            self._send_from_queue(channel),
            name=f"ws-sender-{id(websocket)}",
        )
        if latest_message is not None:
            message, queued_at = latest_message
            if time.monotonic() - queued_at <= self.max_message_age_seconds:
                self._enqueue(channel, message, queued_at)
        logger.info("WebSocket client connected; active=%d", self.connection_count)

    def disconnect(self, websocket: WebSocket) -> None:
        with self._lock:
            channel = self._channels.pop(websocket, None)
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)
            active_count = len(self.active_connections)

        if channel is not None and channel.sender_task is not None:
            try:
                channel.loop.call_soon_threadsafe(channel.sender_task.cancel)
            except RuntimeError:
                logger.debug("Sender loop already closed for WebSocket client")
        logger.info("WebSocket client disconnected; active=%d", active_count)

    @staticmethod
    def encode(data: dict[str, Any]) -> str:
        return json.dumps(data, ensure_ascii=False, separators=(",", ":"))

    def broadcast_now(
        self,
        data: dict[str, Any],
        *,
        queued_at: float | None = None,
    ) -> None:
        """Queue one shared payload for every currently connected client."""
        message = self.encode(data)
        self.broadcast_message(message, queued_at=queued_at)

    def broadcast_message(
        self,
        message: str,
        *,
        queued_at: float | None = None,
    ) -> None:
        self._validate_message_size(message)
        queued_at = time.monotonic() if queued_at is None else queued_at
        with self._lock:
            self._latest_message = (message, queued_at)
            channels = list(self._channels.values())

        for channel in channels:
            self._enqueue(channel, message, queued_at)

    async def broadcast(self, data: dict[str, Any]) -> None:
        """Broadcast a payload from an async request handler."""
        self.broadcast_now(data)

    async def send_to(self, websocket: WebSocket, data: dict[str, Any]) -> None:
        message = self.encode(data)
        self._validate_message_size(message)
        with self._lock:
            channel = self._channels.get(websocket)
        if channel is not None:
            self._enqueue(channel, message, time.monotonic())

    def _validate_message_size(self, message: str) -> None:
        size = len(message.encode("utf-8"))
        if size > self.max_message_bytes:
            raise MessageTooLargeError(
                f"WebSocket message is {size} bytes; limit is "
                f"{self.max_message_bytes} bytes"
            )

    def _enqueue(
        self,
        channel: _ClientChannel,
        message: str,
        queued_at: float,
    ) -> None:
        try:
            channel.messages.put_nowait((message, queued_at))
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
                        message, queued_at = channel.messages.get_nowait()
                    except queue.Empty:
                        break
                    if time.monotonic() - queued_at > self.max_message_age_seconds:
                        continue
                    await channel.websocket.send_text(message)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("WebSocket send failed; removing client")
            self.disconnect(channel.websocket)
