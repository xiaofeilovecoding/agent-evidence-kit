"""Web launcher: loopback binding, limited port fallback, no external calls.

Default is 127.0.0.1:7411. If the preferred port is busy, only a small
neighboring range is tried; nothing else is ever killed. Port 0 lets the
OS pick a free port (used by tests).
"""
from __future__ import annotations

import socket
import sys
import threading
import webbrowser

DEFAULT_PORT = 7411


def _free_port(preferred: int) -> int:
    candidates = [preferred] if preferred == 0 else [preferred]
    if preferred != 0:
        candidates += [preferred + i for i in range(1, 11)]
    for port in candidates:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port if port != 0 else sock.getsockname()[1]
    raise RuntimeError("no free port found")


def run_web(argv: list[str]) -> int:
    port = DEFAULT_PORT
    open_browser = True
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--port":
            if i + 1 >= len(argv):
                print("--port requires a value", file=sys.stderr)
                return 2
            try:
                port = int(argv[i + 1])
            except ValueError:
                print("--port must be an integer", file=sys.stderr)
                return 2
            i += 2
            continue
        if arg == "--no-open":
            open_browser = False
            i += 1
            continue
        print("unknown web argument", file=sys.stderr)
        return 2

    import uvicorn

    from .app import _STATIC_DIR, create_app

    if not _STATIC_DIR.is_dir():
        print(
            "web static assets are missing; reinstall the package or build "
            "the frontend (see README)",
            file=sys.stderr,
        )
        return 1
    try:
        actual_port = _free_port(port)
    except RuntimeError:
        print("no free port found near the requested port", file=sys.stderr)
        return 2
    url = f"http://127.0.0.1:{actual_port}"
    print(f"Agent Evidence Kit web UI: {url}")
    print("Local only. No API key needed; nothing leaves this machine.")
    if open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    uvicorn.run(
        create_app(),
        host="127.0.0.1",
        port=actual_port,
        log_level="warning",
        access_log=False,
    )
    return 0
