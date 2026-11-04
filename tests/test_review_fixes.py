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
        self.context = self.browser.new_context(
            viewport={"width": 1440, "height": 960}, locale="zh-CN"
        )
        self.page = self.context.new_page()

    def tearDown(self):
        self.context.close()

    def wait_view(self, module: str):
        self.page.wait_for_selector(f'.{module}-module [data-testid="result-view"]')

    # ---- C04 ----
    def test_c04_idle_page_does_not_render_loop(self):
        self.page.add_init_script("""window.__commits = 0;
          window.__lastCommit = performance.now();
          window.__REACT_DEVTOOLS_GLOBAL_HOOK__ = {
            supportsFiber: true, renderers: new Map(),
            inject(r) { this.renderers.set(1, r); return 1; },
            onCommitFiberRoot() {
              window.__commits++;
              window.__lastCommit = performance.now();
            },
            onCommitFiberUnmount() {}
          };""")
        self.page.goto(BASE)

        def assert_settled():
            self.page.wait_for_load_state("networkidle")
            # Network idleness does not mean concurrent React updates have
            # committed yet. Wait for actual commit quiescence, bounded so
            # a continuous render feedback loop still fails this assertion.
            self.page.wait_for_function(
                "() => performance.now() - window.__lastCommit >= 300", timeout=5000,
            )
            first = self.page.evaluate("window.__commits")
            self.assertGreater(first, 0, "React commit counter was not installed")
            self.page.wait_for_timeout(200)
            self.assertEqual(self.page.evaluate("window.__commits"), first)

        assert_settled()
        self.page.get_by_role("button", name="带env_vars的http服务残留提示").first.click()
        self.wait_view("config")
        assert_settled()
        self.page.get_by_role("button", name="English").click()
        assert_settled()

    # ---- C03 ----
    def test_c03_combined_preview_invalidates_on_related_change(self):
        self.page.goto(BASE)
        self.page.get_by_role("button", name="带env_vars的http服务残留提示").first.click()
        self.wait_view("config")
        self.page.locator(".sidebar-nav .nav-item", has_text="流结束检查").click()
        self.page.get_by_role("button", name="只有finish，缺[DONE]").first.click()
        self.wait_view("stream")
        self.page.locator(".stream-module .advanced-combined summary").click()
        combined = self.page.locator(".stream-module .combined-box")
        combined.get_by_role("checkbox").first.check()
        combined.get_by_role("checkbox").nth(1).check()
        combined.get_by_role("button", name="导出预览").click()
        combined.locator('[data-testid="combined-export-preview"]').wait_for()

        # Edit the config input: the config result goes stale, so the
        # combined preview must disappear and download must be gone.
        self.page.locator(".sidebar-nav .nav-item", has_text="配置检查").click()
        self.page.locator(".config-module").get_by_role("tab", name="粘贴").click()
        self.page.locator(".config-module textarea").fill('{"mcp_servers": {}}')
        self.page.wait_for_selector(".config-module .status-banner.stale")
        self.assertEqual(
            self.page.locator('[data-testid="combined-export-preview"]').count(), 0
        )
        self.assertEqual(
            self.page.get_by_role("button", name="下载").count(), 0
        )

        # A language switch also invalidates a freshly generated preview.
        self.page.get_by_role("button", name="分析配置").click()
        self.wait_view("config")
        self.page.locator(".config-module .advanced-combined summary").click()
        combined = self.page.locator(".config-module .combined-box")
        combined.get_by_role("checkbox").first.check()
        combined.get_by_role("checkbox").nth(1).check()
        combined.get_by_role("button", name="导出预览").click()
        combined.locator('[data-testid="combined-export-preview"]').wait_for()
        self.page.get_by_role("button", name="English").click()
        self.page.wait_for_selector(".config-module .outcome-banner")
        self.assertEqual(combined.locator('[data-testid="combined-export-preview"]').count(), 0)

    # ---- C05 ----
    def test_c05_delayed_rerender_does_not_overwrite_new_result(self):
        held = []
        pattern = "**/api/results/*?lang=en*"

        def hold(route):
            held.append((route, route.fetch()))

        self.page.route(pattern, hold)
        self.page.goto(BASE)
        self.page.get_by_role("button", name="带env_vars的http服务残留提示").first.click()
        self.wait_view("config")
        self.page.get_by_role("button", name="English").click()
        for _ in range(100):
            if held:
                break
            self.page.wait_for_timeout(10)
        self.assertEqual(len(held), 1, "old response must still be held")
        self.page.get_by_role("button", name="plain stdio service, structure projection only").first.click()
        self.page.wait_for_selector("text=warnings: 0")
        route, response = held.pop()
        with self.page.expect_response(pattern) as delivered:
            route.fulfill(response=response)
        delivered.value.body()
        self.page.evaluate("() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))")
        body_after = self.page.inner_text("body")
        self.assertIn("warnings: 0", body_after)
        self.assertNotIn("warnings: 2", body_after)

    def test_c05_stale_single_export_preview_discarded(self):
        self.page.goto(BASE)
        self.page.locator(".sidebar-nav .nav-item", has_text="配置检查").click()
        self.page.get_by_role("button", name="带env_vars的http服务残留提示").first.click()
        self.wait_view("config")
        panel = self.page.locator(".config-module .result-pane")
        panel.locator(".share-row select").select_option("md")
        panel.get_by_role("button", name="导出预览").click()
        panel.locator('[data-testid="export-preview"]').wait_for()
        # Editing the input invalidates the preview immediately.
        self.page.locator(".config-module").get_by_role("tab", name="粘贴").click()
        self.page.locator(".config-module textarea").fill('{"mcp_servers": {}}')
        self.page.wait_for_selector(".config-module .status-banner.stale")
        self.assertEqual(panel.locator('[data-testid="export-preview"]').count(), 0)
        self.assertEqual(panel.get_by_role("button", name="下载").count(), 0)


if __name__ == "__main__":
    unittest.main()
