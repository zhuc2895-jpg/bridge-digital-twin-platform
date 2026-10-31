import asyncio
import json

from app.ws.websocket_manager import WebSocketManager
from tests.helpers import async_wait_until


class FakeWebSocket:
    def __init__(self, *, fail_send: bool = False):
        self.fail_send = fail_send
        self.accepted = False
        self.closed = False
        self.sent: list[str] = []

    async def accept(self):
        self.accepted = True

    async def send_text(self, message: str):
        if self.fail_send:
            raise RuntimeError("send failed")
        self.sent.append(message)

    async def close(self):
        self.closed = True


class BlockingWebSocket(FakeWebSocket):
    def __init__(self):
        super().__init__()
        self.send_started = asyncio.Event()
        self.release_send = asyncio.Event()

    async def send_text(self, message: str):
        self.send_started.set()
        await self.release_send.wait()
        self.sent.append(message)


class BlockingCloseWebSocket(FakeWebSocket):
    async def close(self):
        await asyncio.Event().wait()



def test_blocking_close_tasks_are_bounded():
    async def scenario():
        manager = WebSocketManager(close_timeout_seconds=0.01)
        for _ in range(20):
            websocket = BlockingCloseWebSocket()
            await manager.connect(websocket)
            manager.disconnect(websocket)

        await asyncio.sleep(0.05)
        current = asyncio.current_task()
        pending = [
            task
            for task in asyncio.all_tasks()
            if task is not current and not task.done()
        ]

        assert manager.connection_count == 0
        assert manager.pending_close_task_count == 0
        assert pending == []

    asyncio.run(scenario())


def test_send_failure_unregisters_and_closes_websocket():
    async def scenario():
        manager = WebSocketManager()
        websocket = FakeWebSocket(fail_send=True)
        await manager.connect(websocket)
        manager.enqueue_broadcast({"type": "sensor_update", "sequence": 1})

        assert await async_wait_until(lambda: manager.connection_count == 0)
        assert await async_wait_until(lambda: websocket.closed)

    asyncio.run(scenario())


def test_slow_client_queue_overflow_unregisters_and_closes_websocket():
    async def scenario():
        manager = WebSocketManager()
        websocket = BlockingWebSocket()
        await manager.connect(websocket)
        manager.enqueue_broadcast({"sequence": 1})
        await websocket.send_started.wait()

        for sequence in range(2, 7):
            manager.enqueue_broadcast({"sequence": sequence})

        assert await async_wait_until(lambda: manager.connection_count == 0)
        assert await async_wait_until(lambda: websocket.closed)
        websocket.release_send.set()

    asyncio.run(scenario())


def test_blocked_send_is_closed_at_latency_deadline():
    async def scenario():
        manager = WebSocketManager(max_message_age_seconds=0.02)
        websocket = BlockingWebSocket()
        await manager.connect(websocket)
        manager.enqueue_broadcast({"sequence": 1})
        await websocket.send_started.wait()
        await asyncio.sleep(0.03)
        websocket.release_send.set()

        assert await async_wait_until(lambda: manager.connection_count == 0)
        assert await async_wait_until(lambda: websocket.closed)
        assert websocket.sent == []

    asyncio.run(scenario())


def test_stale_queued_frame_closes_slow_client_instead_of_skipping():
    async def scenario():
        manager = WebSocketManager(max_message_age_seconds=0.01)
        websocket = BlockingWebSocket()
        await manager.connect(websocket)
        manager.enqueue_broadcast({"sequence": 1})
        await websocket.send_started.wait()
        manager.enqueue_broadcast({"sequence": 2})
        await asyncio.sleep(0.02)
        websocket.release_send.set()

        assert await async_wait_until(lambda: manager.connection_count == 0)
        assert await async_wait_until(lambda: websocket.closed)

    asyncio.run(scenario())


def test_new_client_does_not_replay_cached_frame():
    async def scenario():
        manager = WebSocketManager()
        first = FakeWebSocket()
        second = FakeWebSocket()
        await manager.connect(first)
        manager.enqueue_broadcast({"sequence": 1})
        assert await async_wait_until(lambda: len(first.sent) == 1)

        await manager.connect(second)
        await asyncio.sleep(0.02)
        assert second.sent == []

        manager.enqueue_broadcast({"sequence": 2})
        assert await async_wait_until(lambda: len(second.sent) == 1)
        assert json.loads(second.sent[0]) == {"sequence": 2}

    asyncio.run(scenario())


def test_ten_clients_receive_identical_sustained_broadcast_sequences():
    async def scenario():
        manager = WebSocketManager()
        clients = [FakeWebSocket() for _ in range(10)]
        for client in clients:
            await manager.connect(client)

        expected = []
        for sequence in range(3):
            payload = {"type": "sensor_update", "sequence": sequence}
            expected.append(json.dumps(payload, separators=(",", ":")))
            manager.enqueue_broadcast(payload)

        assert await async_wait_until(
            lambda: all(len(client.sent) == 3 for client in clients)
        )
        assert [client.sent for client in clients] == [expected] * 10

    asyncio.run(scenario())
