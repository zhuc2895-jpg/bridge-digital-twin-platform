"""Long-running stability probe for live-stream memory and connection health."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import ctypes
import json
import os
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Sequence

import httpx
import websockets

ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import AppConfig  # noqa: E402

from benchmarks.acceptance import (  # noqa: E402
    DEFAULT_RUNS_DIR,
    environment_info,
    running_server,
)

STABILITY_RUNS_DIR = DEFAULT_RUNS_DIR.parent / "stability" / "runs"
REPRODUCTION_COMMAND = "python -m benchmarks.stability --hours 24"


def process_memory_bytes() -> int:
    """Return the current process working set using platform-native APIs."""
    if os.name == "nt":
        class ProcessMemoryCounters(ctypes.Structure):
            _fields_ = [
                ("cb", ctypes.c_ulong),
                ("PageFaultCount", ctypes.c_ulong),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        counters = ProcessMemoryCounters()
        counters.cb = ctypes.sizeof(ProcessMemoryCounters)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        kernel32.GetCurrentProcess.restype = ctypes.c_void_p
        psapi.GetProcessMemoryInfo.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ProcessMemoryCounters),
            ctypes.c_ulong,
        ]
        psapi.GetProcessMemoryInfo.restype = ctypes.c_bool
        process = kernel32.GetCurrentProcess()
        success = psapi.GetProcessMemoryInfo(
            process,
            ctypes.byref(counters),
            counters.cb,
        )
        if success:
            return int(counters.WorkingSetSize)
    elif Path("/proc/self/status").exists():
        for line in Path("/proc/self/status").read_text(encoding="utf-8").splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) * 1024
    try:
        import resource

        return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss) * 1024
    except (ImportError, AttributeError):
        return 0


async def _ws_reader(
    ws_url: str,
    *,
    client_index: int,
    stop_event: asyncio.Event,
    connected: asyncio.Event,
    counters: dict[str, Any],
    errors: list[str],
) -> None:
    try:
        async with websockets.connect(ws_url, open_timeout=5) as socket:
            counters["connected"] += 1
            connected.set()
            while not stop_event.is_set():
                try:
                    await asyncio.wait_for(socket.recv(), timeout=3)
                    counters["frames"] += 1
                except TimeoutError:
                    continue
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        errors.append(f"client {client_index}: {type(exc).__name__}: {exc}")


async def run_stability(
    *,
    hours: float,
    probe_interval_seconds: float,
    clients: int,
    temporary_root: Path,
) -> dict[str, Any]:
    if hours <= 0:
        raise ValueError("hours must be positive")
    if probe_interval_seconds <= 0:
        raise ValueError("probe_interval_seconds must be positive")
    if clients < 0:
        raise ValueError("clients must be non-negative")

    config = AppConfig(
        simulation_enabled=True,
        live_interval_seconds=1.0,
        checkpoint_path=temporary_root / "stability.json",
        log_level="WARNING",
    )
    duration_seconds = hours * 3600
    stop_event = asyncio.Event()
    connected = asyncio.Event()
    counters: dict[str, Any] = {"connected": 0, "frames": 0}
    errors: list[str] = []
    samples: list[dict[str, Any]] = []
    started_at = time.monotonic()
    health_requests = 0
    health_errors = 0

    with running_server(config) as (base_url, ws_url):
        async with httpx.AsyncClient(base_url=base_url, timeout=10) as client:
            tasks = [
                asyncio.create_task(
                    _ws_reader(
                        ws_url,
                        client_index=index,
                        stop_event=stop_event,
                        connected=connected,
                        counters=counters,
                        errors=errors,
                    )
                )
                for index in range(clients)
            ]
            if clients:
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(connected.wait(), timeout=10)

            while True:
                elapsed = time.monotonic() - started_at
                remaining = duration_seconds - elapsed
                if remaining <= 0:
                    break
                try:
                    response = await client.get("/api/health")
                    response.raise_for_status()
                    health = response.json()
                    health_requests += 1
                except Exception as exc:
                    health_errors += 1
                    health = {"status": "unreachable", "error": str(exc)}
                samples.append(
                    {
                        "elapsed_seconds": round(elapsed, 3),
                        "memory_bytes": process_memory_bytes(),
                        "health_status": health.get("status"),
                        "sensor_count": health.get("sensor_count"),
                        "alert_count": health.get("retained_alerts"),
                        "websocket_connections": health.get("websocket_connections"),
                        "live_stream_running": health.get("live_stream_running"),
                        "ws_clients_alive": sum(not task.done() for task in tasks),
                        "live_frames": counters["frames"],
                        "errors": health_errors + len(errors),
                    }
                )
                await asyncio.sleep(min(probe_interval_seconds, max(0, remaining)))

            try:
                final_response = await client.get("/api/health")
                final_response.raise_for_status()
                final_health = final_response.json()
                health_requests += 1
            except Exception as exc:
                health_errors += 1
                final_health = {"status": "unreachable", "error": str(exc)}

            stop_event.set()
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    elapsed_seconds = time.monotonic() - started_at
    memory_values = [int(sample["memory_bytes"]) for sample in samples]
    start_memory = memory_values[0] if memory_values else process_memory_bytes()
    end_memory = memory_values[-1] if memory_values else start_memory
    memory_growth = end_memory - start_memory
    final_alive = final_health.get("status") == "healthy"
    clients_alive = int(final_health.get("websocket_connections") or 0)
    accepted = (
        final_alive
        and health_errors == 0
        and not errors
        and clients_alive >= min(clients, 10)
    )
    return {
        "schema_version": 1,
        "status": "passed" if accepted else "failed",
        "generated_at": datetime.now(UTC).isoformat(),
        "reproduction_command": REPRODUCTION_COMMAND,
        "environment": environment_info(),
        "configuration": {
            "duration_hours": hours,
            "probe_interval_seconds": probe_interval_seconds,
            "websocket_clients": clients,
        },
        "summary": {
            "elapsed_seconds": elapsed_seconds,
            "health_requests": health_requests,
            "health_errors": health_errors,
            "client_errors": errors,
            "start_memory_bytes": start_memory,
            "end_memory_bytes": end_memory,
            "peak_memory_bytes": max(memory_values, default=start_memory),
            "memory_growth_bytes": memory_growth,
            "memory_growth_bytes_per_hour": (
                memory_growth / (elapsed_seconds / 3600)
                if elapsed_seconds > 0
                else 0.0
            ),
            "live_frames_received": counters["frames"],
            "live_frame_rate_per_second": (
                counters["frames"] / elapsed_seconds if elapsed_seconds > 0 else 0.0
            ),
            "final_health": final_health,
            "final_alive": final_alive,
            "final_websocket_connections": clients_alive,
        },
        "samples": samples,
        "exit_reason": (
            "stability gates passed"
            if accepted
            else "final health, connection, or error gate failed"
        ),
    }


def write_report(payload: dict[str, Any], output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "stability.json"
    markdown_path = output_dir / "stability.md"
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    summary = payload["summary"]
    lines = [
        "# Stability Report",
        "",
        f"- Status: **{payload['status']}**",
        f"- Generated: {payload['generated_at']}",
        f"- Reproduction: `{payload['reproduction_command']}`",
        f"- Duration: {summary['elapsed_seconds']:.1f} seconds",
        f"- Final alive: {summary['final_alive']}",
        f"- Health errors: {summary['health_errors']}",
        f"- Client errors: {len(summary['client_errors'])}",
        f"- Start memory: {summary['start_memory_bytes']} bytes",
        f"- End memory: {summary['end_memory_bytes']} bytes",
        f"- Peak memory: {summary['peak_memory_bytes']} bytes",
        f"- Memory growth/hour: {summary['memory_growth_bytes_per_hour']:.1f} bytes",
        f"- Live frames received: {summary['live_frames_received']}",
        f"- Final WebSocket connections: {summary['final_websocket_connections']}",
        f"- Exit reason: {payload['exit_reason']}",
    ]
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, markdown_path


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hours", type=float, default=24.0)
    parser.add_argument("--probe-interval", type=float, default=60.0)
    parser.add_argument("--clients", type=int, default=10)
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args(argv)

    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    output_dir = args.output_dir or STABILITY_RUNS_DIR / timestamp
    with tempfile.TemporaryDirectory(prefix="bridge-stability-") as temporary:
        payload = asyncio.run(
            run_stability(
                hours=args.hours,
                probe_interval_seconds=args.probe_interval,
                clients=args.clients,
                temporary_root=Path(temporary),
            )
        )
    json_path, markdown_path = write_report(payload, output_dir)
    print(f"Stability status: {payload['status']}")
    print(f"JSON report: {json_path}")
    print(f"Markdown report: {markdown_path}")
    return 0 if payload["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
