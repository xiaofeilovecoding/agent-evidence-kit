"""Codex review C03/C04/C05 browser regressions.

C04: an idle page must not re-render in a loop (commit counter must stay
flat). C03: the combined export preview/download is bound to the selected
results + language + format snapshot and invalidates immediately. C05: a
delayed language re-render response must never overwrite a newer result,
and a stale single-module export preview must not resurrect.
"""
from __future__ import annotations

import os
import sys
import threading
import time
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

try:
    import httpx

    import uvicorn
    from playwright.sync_api import sync_playwright

    from agent_evidence_kit.server.app import create_app
    from agent_evidence_kit.server.sessions import SessionStore

    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

from tests import helpers  # noqa: E402

BASE = "http://127.0.0.1:7414"


def _start_server(store):
    config = uvicorn.Config(create_app(store=store), host="127.0.0.1",
                            port=7414, log_level="error", access_log=False)
    server = uvicorn.Server(config)
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(100):
        try:
            httpx.get(f"{BASE}/api/health", timeout=0.5)
            return server
        except Exception:
            time.sleep(0.1)
    raise RuntimeError("server did not start")


@unittest.skipUnless(PLAYWRIGHT_AVAILABLE, "playwright not installed")
class ReviewFixJourneys(unittest.TestCase):
    server = None
    pw = None
    browser = None
    store = None

    @classmethod
    def setUpClass(cls):
        cls.store = SessionStore()
        cls.server = _start_server(cls.store)
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.server.should_exit = True

    def setUp(self):
        self.store._sessions.clear()
        self.context = self.browser.new_context(viewport={"width": 1440, "height": 960})
        self.page = self.context.new_page()

    def tearDown(self):
        self.context.close()

    def wait_view(self, module: str):
        self.page.wait_for_selector(f'.{module}-module [data-testid="result-view"]')

    # ---- C04 ----
    def test_c04_idle_page_does_not_render_loop(self):
        self.page.goto(BASE)
        # Install a commit counter via React DevTools hook equivalent:
        # count DOM mutations instead (no DevTools dependency).
        self.page.evaluate(
            """() => {
              window.__mut = 0;
              const obs = new MutationObserver((m) => { window.__mut += m.length; });
              obs.observe(document.getElementById("root"), { subtree: true, childList: true, attributes: true, characterData: true });
            }"""
        )
        self.page.wait_for_timeout(1500)
        idle_1 = self.page.evaluate("window.__mut")
        self.page.wait_for_timeout(1500)
        idle_2 = self.page.evaluate("window.__mut")
        self.assertEqual(idle_2, idle_1,
                         f"idle page keeps mutating the DOM ({idle_1} -> {idle_2})")

        # After interacting, the page must settle again.
        self.page.get_by_role("button", name="带env_vars的http服务残留提示").first.click()
        self.wait_view("config")
        self.page.evaluate("window.__mut = 0")
        self.page.wait_for_timeout(1500)
        after_1 = self.page.evaluate("window.__mut")
        self.page.wait_for_timeout(1500)
        after_2 = self.page.evaluate("window.__mut")
        self.assertEqual(after_2, after_1, "result page keeps mutating while idle")

        # Language switch works and settles.
        self.page.get_by_role("button", name="English").click()
        self.page.wait_for_selector(".config-module .outcome-banner")
        self.page.evaluate("window.__mut = 0")
        self.page.wait_for_timeout(1200)
        self.assertEqual(self.page.evaluate("window.__mut"), 0)

    # ---- C03 ----
    def test_c03_combined_preview_invalidates_on_related_change(self):
        self.page.goto(BASE)
        self.page.get_by_role("button", name="带env_vars的http服务残留提示").first.click()
        self.wait_view("config")
        self.page.get_by_role("tab", name="流结束检查").click()
        self.page.get_by_role("button", name="只有finish，缺[DONE]").first.click()
        self.wait_view("stream")
        combined = self.page.locator(".combined-box")
        combined.get_by_role("checkbox").first.check()
        combined.get_by_role("checkbox").nth(1).check()
        combined.get_by_role("button", name="导出预览").click()
        combined.locator('[data-testid="combined-export-preview"]').wait_for()

        # Edit the config input: the config result goes stale, so the
        # combined preview must disappear and download must be gone.
        self.page.get_by_role("tab", name="配置检查").click()
        self.page.get_by_role("tab", name="粘贴").click()
        self.page.locator(".config-module textarea").fill('{"mcp_servers": {}}')
        self.page.wait_for_selector(".config-module .status-banner.stale")
        self.assertEqual(combined.locator('[data-testid="combined-export-preview"]').count(), 0)
        self.assertEqual(combined.get_by_role("button", name="下载").count(), 0)

        # A language switch also invalidates a freshly generated preview.
        self.page.get_by_role("button", name="分析配置").click()
        self.wait_view("config")
        combined.get_by_role("checkbox").first.check()
        combined.get_by_role("checkbox").nth(1).check()
        combined.get_by_role("button", name="导出预览").click()
        combined.locator('[data-testid="combined-export-preview"]').wait_for()
        self.page.get_by_role("button", name="English").click()
        self.page.wait_for_selector(".config-module .outcome-banner")
        self.assertEqual(combined.locator('[data-testid="combined-export-preview"]').count(), 0)

    # ---- C05 ----
    def test_c05_delayed_rerender_does_not_overwrite_new_result(self):
        route_lock = threading.Event()

        def handle_route(route):
            # Hold the language re-render response until the newer result
            # has been produced.
            route_lock.wait(10)
            route.continue_()

        self.page.route("**/api/results/*?lang=en*", handle_route)
        self.page.goto(BASE)
        self.page.get_by_role("button", name="带env_vars的http服务残留提示").first.click()
        self.wait_view("config")
        self.page.get_by_role("button", name="English").click()
        # Give the intercepted re-render time to reach the pause.
        self.page.wait_for_timeout(300)
        self.page.get_by_role("button", name="plain stdio service, structure projection only").first.click()
        self.wait_view("config")
        self.page.wait_for_selector(".status-banner.loading", state="detached")
        self.page.wait_for_selector("text=warnings: 0")
        body_now = self.page.inner_text("body")
        self.assertIn("warnings: 0", body_now)
        # Release the stale re-render: the display must stay the new result.
        route_lock.set()
        self.page.wait_for_timeout(800)
        body_after = self.page.inner_text("body")
        self.assertIn("warnings: 0", body_after)
        self.assertNotIn("warnings: 2", body_after)

    def test_c05_stale_single_export_preview_discarded(self):
        self.page.goto(BASE)
        self.page.get_by_role("tab", name="配置检查").click()
        self.page.get_by_role("button", name="带env_vars的http服务残留提示").first.click()
        self.wait_view("config")
        panel = self.page.locator(".config-module .result-panel")
        panel.locator(".export-controls select").select_option("md")
        panel.get_by_role("button", name="导出预览").click()
        panel.locator('[data-testid="export-preview"]').wait_for()
        # Editing the input invalidates the preview immediately.
        self.page.get_by_role("tab", name="粘贴").click()
        self.page.locator(".config-module textarea").fill('{"mcp_servers": {}}')
        self.page.wait_for_selector(".config-module .status-banner.stale")
        self.assertEqual(panel.locator('[data-testid="export-preview"]').count(), 0)
        self.assertEqual(panel.get_by_role("button", name="下载").count(), 0)


if __name__ == "__main__":
    unittest.main()
