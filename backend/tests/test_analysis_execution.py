import asyncio
import threading

from app.analysis_execution import InlineAnalysisExecutor, ThreadedAnalysisExecutor


class RecordingExecutor:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def run(self, operation, *args, **kwargs):
        self.calls.append(operation.__name__)
        return operation(*args, **kwargs)


def test_threaded_executor_runs_work_off_the_event_loop_thread() -> None:
    caller_thread = threading.get_ident()

    worker_thread = asyncio.run(
        ThreadedAnalysisExecutor().run(threading.get_ident)
    )

    assert worker_thread != caller_thread


def test_inline_executor_runs_work_synchronously() -> None:
    executor = InlineAnalysisExecutor()

    result = asyncio.run(executor.run(lambda value: value + 1, 41))

    assert result == 42


def test_report_route_uses_configured_analysis_executor(client, app) -> None:
    executor = RecordingExecutor()
    app.state.services.analysis_executor = executor

    response = client.get("/api/analysis/report", params={"hours": 1})

    assert response.status_code == 200
    assert executor.calls == ["render_monitoring_report"]
