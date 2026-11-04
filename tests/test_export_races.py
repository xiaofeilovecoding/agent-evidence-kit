"""Delay real HTTP responses without blocking browser actions, then invalidate.

Every assertion runs after the held response has actually reached the browser.
No model, mock diagnostic result, or elapsed-time guess is used as an oracle.
"""
import threading
import time
import unittest
from pathlib import Path

try:
    import uvicorn
    from playwright.sync_api import sync_playwright
    from agent_evidence_kit.server.app import create_app
    AVAILABLE = True
except ImportError:
    AVAILABLE = False


@unittest.skipUnless(AVAILABLE, "web and playwright dependencies required")
class ExportRaces(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = uvicorn.Server(uvicorn.Config(
            create_app(), host="127.0.0.1", port=0,
            log_level="error", access_log=False,
        ))
        cls.thread = threading.Thread(target=cls.server.run, daemon=True)
        cls.thread.start()
        for _ in range(200):
            if cls.server.started:
                break
            time.sleep(.01)
        assert cls.server.started, "local test server failed to start"
        port = cls.server.servers[0].sockets[0].getsockname()[1]
        cls.base = f"http://127.0.0.1:{port}"
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.server.should_exit = True
        cls.thread.join(5)

    def setUp(self):
        self.context = self.browser.new_context(viewport={"width": 1440, "height": 960})
        self.page = self.context.new_page()
        self.page.set_default_timeout(5000)
        self.page.goto(self.base)

    def tearDown(self):
        self.context.close()

    def settle(self):
        self.page.evaluate("() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))")

    def module(self, name):
        return self.page.locator(f"main > .{name}-module")

    def sample(self, module, index=0):
        self.page.locator(".module-switch button").nth(1 if module == "stream" else 0).click()
        view = self.module(module)
        view.locator(".input-panel .segmented button").first.click()
        with self.page.expect_response(f"**/api/{module}/demo") as response:
            view.locator(".example-card").nth(index).click()
        response.value.body()
        self.settle()
        view.locator('[data-testid="result-view"]').wait_for()

    def defer(self, pattern):
        pending = []

        def hold(route):
            pending.append((route, route.fetch()))

        self.page.route(pattern, hold)
        return pending

    def release(self, pending, pattern):
        for _ in range(100):
            if pending:
                break
            self.page.wait_for_timeout(10)
        self.assertEqual(len(pending), 1, "response was not held during the user action")
        route, upstream = pending.pop()
        with self.page.expect_response(pattern) as delivered:
            route.fulfill(response=upstream)
        delivered.value.body()
        self.settle()

    def edit(self, module):
        self.page.locator(".module-switch button").nth(1 if module == "stream" else 0).click()
        view = self.module(module)
        view.locator(".input-panel .segmented button").nth(2).click()
        view.locator("textarea").fill('{"mcpServers": {}}' if module == "config" else "data: [DONE]\n\n")
        view.locator(".status-banner.stale").wait_for()

    def test_deferred_single_exports_cannot_restore_stale_preview(self):
        for module in ("config", "stream"):
            with self.subTest(module=module):
                self.sample(module)
                pattern = "**/api/export"
                pending = self.defer(pattern)
                panel = self.module(module).locator(".result-panel")
                panel.locator(".export-controls button").click()
                self.edit(module)
                self.release(pending, pattern)
                self.assertEqual(panel.locator('[data-testid="export-preview"]').count(), 0)
                self.assertEqual(panel.get_by_role("button", name="下载", exact=True).count(), 0)
                self.page.unroute(pattern)

    def test_deferred_combined_export_cannot_restore_stale_preview(self):
        self.sample("config")
        self.sample("stream")
        box = self.page.locator(".combined-box")
        box.locator('input[type="checkbox"]').nth(0).check()
        box.locator('input[type="checkbox"]').nth(1).check()
        pattern = "**/api/export/combined"
        pending = self.defer(pattern)
        box.locator("button.ghost").click()
        self.edit("config")
        self.release(pending, pattern)
        self.assertTrue(box.locator('input[type="checkbox"]').nth(0).is_disabled())
        self.assertEqual(box.locator('[data-testid="combined-export-preview"]').count(), 0)
        self.assertEqual(box.get_by_role("button", name="下载", exact=True).count(), 0)

    def test_single_export_rejects_format_language_and_new_result_changes(self):
        for module in ("config", "stream"):
            for change in ("format", "language", "new_result", "clear"):
                with self.subTest(module=module, change=change):
                    self.sample(module)
                    panel = self.module(module).locator(".result-panel")
                    pattern = "**/api/export"
                    pending = self.defer(pattern)
                    panel.locator(".export-controls button").click()
                    if change == "format":
                        panel.locator(".export-controls select").select_option("md")
                        panel.locator(".export-controls select").select_option("json")
                    elif change == "language":
                        self.page.get_by_role("button", name="English", exact=True).click()
                        self.page.get_by_role("button", name="中文", exact=True).click()
                    elif change == "new_result":
                        self.sample(module, 1)
                    else:
                        with self.page.expect_response("**/api/clear") as cleared:
                            self.module(module).locator(".input-actions button.ghost").click()
                        cleared.value.body()
                    self.release(pending, pattern)
                    self.assertEqual(panel.locator('[data-testid="export-preview"]').count(), 0)
                    self.assertEqual(panel.get_by_role("button", name="下载", exact=True).count(), 0)
                    self.page.unroute(pattern)

    def test_combined_selection_round_trip_revokes_pending_response(self):
        self.sample("config")
        box = self.page.locator(".combined-box")
        checkbox = box.locator('input[type="checkbox"]').first
        checkbox.check()
        pattern = "**/api/export/combined"
        pending = self.defer(pattern)
        box.locator("button.ghost").click()
        checkbox.uncheck()
        checkbox.check()
        self.release(pending, pattern)
        self.assertEqual(box.locator('[data-testid="combined-export-preview"]').count(), 0)

    def test_unselected_module_does_not_invalidate_combined_export(self):
        self.sample("config")
        self.sample("stream")
        box = self.page.locator(".combined-box")
        box.locator('input[type="checkbox"]').nth(1).check()
        pattern = "**/api/export/combined"
        pending = self.defer(pattern)
        box.locator("button.ghost").click()
        self.edit("config")
        self.release(pending, pattern)
        content = box.locator('[data-testid="combined-export-preview"]').inner_text()
        with self.page.expect_download() as downloaded:
            box.get_by_role("button", name="下载", exact=True).click()
        self.assertEqual(downloaded.value.suggested_filename, "agent-evidence-kit-combined-zh-CN.md")
        self.assertEqual(Path(downloaded.value.path()).read_text(encoding="utf-8"), content)
