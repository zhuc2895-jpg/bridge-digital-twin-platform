"""Windows desktop entry point for the bridge digital twin application."""

from __future__ import annotations

import argparse
import os
import socket
import sys
import threading
import time
import traceback
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

APP_TITLE = "桥梁结构健康监测"


def project_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS"))
    return Path(__file__).resolve().parents[1]


def app_data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    root = Path(base) if base else Path.home() / "AppData" / "Local"
    return root / "BridgeDigitalTwin"


def install_frozen_logging() -> Path | None:
    if not getattr(sys, "frozen", False):
        return None
    log_path = app_data_dir() / "desktop.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    stream = log_path.open("a", encoding="utf-8", buffering=1)
    sys.stdout = stream
    sys.stderr = stream
    print(f"--- desktop start {time.strftime('%Y-%m-%d %H:%M:%S')} ---")
    return log_path


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def configure_environment(port: int) -> Path:
    root = project_root()
    frontend_dist = root / "frontend" / "dist"
    data_dir = app_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "models").mkdir(parents=True, exist_ok=True)
    (data_dir / "state").mkdir(parents=True, exist_ok=True)

    backend_dir = root / "backend"
    if not getattr(sys, "frozen", False) and str(backend_dir) not in sys.path:
        sys.path.insert(0, str(backend_dir))

    os.environ.setdefault(
        "BRIDGE_CHECKPOINT_PATH",
        str(data_dir / "state" / "monitoring.json"),
    )
    os.environ.setdefault("BRIDGE_MODEL_DIR", str(data_dir / "models"))
    os.environ.setdefault("BRIDGE_FRONTEND_DIST", str(frontend_dist))
    os.environ.setdefault("BRIDGE_HOST", "127.0.0.1")
    os.environ.setdefault("BRIDGE_PORT", str(port))
    os.environ.setdefault(
        "BRIDGE_CORS_ORIGINS",
        f"http://127.0.0.1:{port},http://localhost:{port}",
    )
    os.environ.setdefault("BRIDGE_LOG_LEVEL", "INFO")
    return frontend_dist


def wait_until_ready(base_url: str, timeout: float = 20.0) -> None:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"{base_url}/api/health", timeout=2) as response:
                if response.status == 200:
                    return
        except (OSError, urllib.error.URLError) as exc:
            last_error = exc
        time.sleep(0.2)
    raise RuntimeError(f"Bridge service did not start in time: {last_error}")


def start_server(port: int):
    from app.main import create_app

    try:
        import uvicorn
    except ImportError as exc:
        raise RuntimeError("uvicorn is required to run the desktop application") from exc

    application = create_app()
    config = uvicorn.Config(
        application,
        host="127.0.0.1",
        port=port,
        log_level="warning",
        access_log=False,
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, name="bridge-desktop-server", daemon=True)
    thread.start()
    return server, thread


def open_desktop_window(url: str) -> None:
    try:
        import webview
    except ImportError as exc:
        raise RuntimeError(
            "pywebview is required for the Windows desktop window. "
            "Install desktop/requirements.txt or use the packaged application."
        ) from exc

    webview.create_window(
        APP_TITLE,
        url,
        width=1480,
        height=920,
        min_size=(1100, 700),
        background_color="#0d1117",
        text_select=True,
    )
    webview.start()


def headless_smoke(base_url: str) -> None:
    for path in ("/api/health", "/api/models/active", "/app"):
        with urllib.request.urlopen(f"{base_url}{path}", timeout=5) as response:
            if response.status != 200:
                raise RuntimeError(f"{path} returned HTTP {response.status}")
    print("desktop smoke ok")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument(
        "--headless-smoke",
        action="store_true",
        help="Start the embedded server, verify /app and APIs, then exit.",
    )
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args(argv)

    port = args.port or find_free_port()
    frontend_dist = configure_environment(port)
    if not (frontend_dist / "index.html").is_file():
        raise RuntimeError(
            f"Built frontend was not found at {frontend_dist}. Run pnpm build first."
        )

    server, thread = start_server(port)
    base_url = f"http://127.0.0.1:{port}"
    try:
        wait_until_ready(base_url)
        if args.headless_smoke:
            headless_smoke(base_url)
            sys.stdout.flush()
            sys.stderr.flush()
            os._exit(0)
        open_desktop_window(f"{base_url}/app")
        return 0
    finally:
        server.should_exit = True
        thread.join(timeout=5)


if __name__ == "__main__":
    install_frozen_logging()
    try:
        raise SystemExit(main())
    except Exception as exc:
        traceback.print_exc()
        if sys.platform == "win32" and "--headless-smoke" not in sys.argv:
            try:
                import ctypes

                ctypes.windll.user32.MessageBoxW(0, str(exc), APP_TITLE, 0x10)
            except Exception:
                pass
        print(f"desktop startup failed: {exc}", file=sys.stderr)
        sys.stderr.flush()
        os._exit(1)
