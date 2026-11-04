"""Execution policy for blocking monitoring analysis and report work."""

from __future__ import annotations

from collections.abc import Callable
from typing import ParamSpec, Protocol, TypeVar

from starlette.concurrency import run_in_threadpool

P = ParamSpec("P")
T = TypeVar("T")


class AnalysisExecutor(Protocol):
    """Run one blocking analysis operation outside the event loop."""

    async def run(
        self,
        operation: Callable[P, T],
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> T: ...


class ThreadedAnalysisExecutor:
    """Production adapter backed by the framework thread pool."""

    async def run(
        self,
        operation: Callable[P, T],
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> T:
        return await run_in_threadpool(operation, *args, **kwargs)


class InlineAnalysisExecutor:
    """Synchronous adapter for deterministic local tests."""

    async def run(
        self,
        operation: Callable[P, T],
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> T:
        return operation(*args, **kwargs)
