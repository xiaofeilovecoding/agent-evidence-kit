"""Capture real product screenshots from the production build.

Run (after `python scripts/build_frontend.py`):
    python scripts/capture_screenshots.py

Writes the four public README images into docs/screenshots/ (locale must
match the README language, never hardcoded to one language) and extra
review states into artifacts/screenshots/. Every shot comes from a real
page of the built bundle; no design mock-ups.
"""
from __future__ import annotations

import argparse
import threading
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

import sys  # noqa: E402

sys.path.insert(0, str(PROJECT_ROOT))

try:
    import httpx
    import uvicorn
    from playwright.sync_api import sync_playwright

    from agent_evidence_kit.server.app import create_app

    AVAILABLE = True
except ImportError:
    AVAILABLE = False

PUBLIC = PROJECT_ROOT / "docs" / "screenshots"
EXTRA = PROJECT_ROOT / "artifacts" / "screenshots"


def _start_server():
    server = uvicorn.Server(uvicorn.Config(
        create_app(), host="127.0.0.1", port=0, log_level="error", access_log=False,
    ))
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(200):
        if server.started:
            break
        time.sleep(0.01)
    assert server.started
    port = server.servers[0].sockets[0].getsockname()[1]
    return server, f"http://127.0.0.1:{port}"


def _prep(page, lang: str, theme: str):
    page.add_init_script(
        f"localStorage.setItem('aek.lang', {lang!r});"
        f"localStorage.setItem('aek.theme', {theme!r});"
    )


def _run_config_sample(page):
    # Locale-independent: click the first example card (http-residue demo).
    page.locator(".config-module .example-list .example-card").first.click()
    page.wait_for_selector('.config-module [data-testid="result-view"]')
    page.get_by_role("button", name="server-1").click()
    page.wait_for_selector(".config-module .service-body")


def _run_stream_sample(page):
    page.locator(".sidebar-nav .nav-item").nth(1).click()
    page.locator(".stream-module .example-list .example-card").nth(1).click()
    page.wait_for_selector('.stream-module [data-testid="result-view"]')
    page.locator(".stream-module .compare-block .ghost.small").click()
    page.wait_for_selector(".stream-module .compare-wide")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(PUBLIC), help="public screenshots dir")
    parser.add_argument("--extra-out", default=str(EXTRA))
    args = parser.parse_args()
    if not AVAILABLE:
        print("playwright + web extra required", file=__import__("sys").stderr)
        return 1
    out = Path(args.out)
    extra = Path(args.extra_out)
    out.mkdir(parents=True, exist_ok=True)
    extra.mkdir(parents=True, exist_ok=True)

    server, base = _start_server()
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            shots = [
                # (name, lang, theme, runner, dest, width)
                ("en-config-light", "en", "light", _run_config_sample, out, 1440),
                ("en-stream-dark", "en", "dark", _run_stream_sample, out, 1440),
                ("zh-config-light", "zh-CN", "light", _run_config_sample, out, 1440),
                ("zh-stream-dark", "zh-CN", "dark", _run_stream_sample, out, 1440),
                ("zh-config-390-expanded", "zh-CN", "light", _run_config_sample, extra, 390),
                ("en-privacy-panel", "en", "light", None, extra, 1440),
                ("zh-error-state", "zh-CN", "light", None, extra, 1440),
            ]
            for name, lang, theme, runner, dest, width in shots:
                context = browser.new_context(
                    viewport={"width": width, "height": 960 if width >= 1120 else 844},
                    locale="en-US" if lang == "en" else "zh-CN",
                    color_scheme=theme,
                )
                page = context.new_page()
                _prep(page, lang, theme)
                page.goto(base)
                if name == "en-privacy-panel":
                    page.locator(".local-badge").click()
                    page.wait_for_selector(".dialog-panel")
                elif name == "zh-error-state":
                    page.locator(".config-module").get_by_role(
                        "tab", name="粘贴").click()
                    page.locator(".config-module textarea").fill("{broken json")
                    page.locator(".config-module .analyze-button").click()
                    page.wait_for_selector(".config-module .result-error")
                elif runner is not None:
                    runner(page)
                else:  # pragma: no cover
                    runner = None
                page.screenshot(path=str(dest / f"{name}.png"), full_page=True)
                print(f"captured {dest / name}.png")
                context.close()
            browser.close()
    finally:
        server.should_exit = True
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
