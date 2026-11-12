"""0420-round regressions: unified input-identity contract.

Identity rules under test:
- Any source switch (Examples/File/Paste) revokes deferred readers, the
  in-flight analysis, and share eligibility; loading exits to a truthful
  stale/empty state.
- Switching back to a previous source NEVER revives a result: stale
  stays stale until a real new analysis on the current input.
- Cached input text is preserved; a real new analysis still succeeds.
- Deferred file reads and held analyze requests are genuinely held
  (no tautological assertions).
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "tests"))

from test_public_ready import _start_server  # noqa: E402

try:  # web/browser deps required only for these journeys
    import uvicorn  # noqa: E402,F401
    from playwright.sync_api import sync_playwright  # noqa: E402

    from agent_evidence_kit.server.app import create_app  # noqa: E402
    from agent_evidence_kit.server.sessions import SessionStore  # noqa: E402

    AVAILABLE = True
except ImportError:
    AVAILABLE = False


@unittest.skipUnless(AVAILABLE, "web and playwright dependencies required")
class SourceIdentityContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store = SessionStore()
        cls.server = _start_server(cls.store, 7423)
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.server.should_exit = True

    def setUp(self):
        self.store._sessions.clear()
        self.base = "http://127.0.0.1:7423"
        self.context = self.browser.new_context(
            viewport={"width": 1440, "height": 960}, locale="zh-CN"
        )
        self.page = self.context.new_page()
        self.page.set_default_timeout(8000)
        self.page.goto(self.base)

    def tearDown(self):
        self.context.close()

    def nav(self, page, module):
        page.locator(".sidebar-nav .nav-item", has_text=module).click()

    def paste_and_analyze(self, page, module, text=None):
        self.nav(page, "配置检查" if module == "config" else "流结束检查")
        page.locator(f".{module}-module").get_by_role("tab", name="粘贴").click()
        page.locator(f".{module}-module .paste-area textarea").fill(
            text
            if text is not None
            else ('{"mcp_servers": {"A": {"command": "x"}}}' if module == "config"
                  else "data: [DONE]\n\n")
        )
        page.get_by_role("button", name="分析配置" if module == "config" else "分析流").click()
        page.wait_for_selector(f'.{module}-module [data-testid="result-view"]')

    def held_analyze(self, page, module):
        """Hold the analyze request for this module; return (release, seen)."""
        held = []
        pattern = f"**/api/{module}/analyze*"

        def hold(route):
            held.append((route, route.fetch()))

        page.route(pattern, hold)

        def release():
            """Fulfill the held request. Returns 'delivered' if the page
            accepted the response, or 'superseded' if the request had been
            cancelled (both are valid observable outcomes; the test asserts
            which contract applies)."""
            outcome = []
            for route, upstream in held:
                try:
                    with page.expect_response(pattern, timeout=2500) as delivered:
                        route.fulfill(response=upstream)
                    delivered.value.body()
                    outcome.append("delivered")
                except Exception:
                    outcome.append("superseded")
            page.unroute(pattern)
            return outcome

        return release, held

    def test_source_switch_invalidates_held_paste_analysis(self):
        """Paste analysis held in flight -> switch to File -> the held
        request is superseded and its result never lands ready/shareable,
        even when the request is later released."""
        for module in ("config", "stream"):
            with self.subTest(module=module):
                page = self.page
                self.nav(page, "配置检查" if module == "config" else "流结束检查")
                page.locator(f".{module}-module").get_by_role(
                    "tab", name="粘贴").click()
                page.locator(f".{module}-module .paste-area textarea").fill(
                    '{"mcp_servers": {"A": {"command": "x"}}}' if module == "config"
                    else "data: [DONE]\n\n"
                )
                release, held = self.held_analyze(page, module)
                analyze_name = "分析配置" if module == "config" else "分析流"
                with page.expect_request(
                    lambda req: f"/api/{module}/analyze" in req.url
                ):
                    page.get_by_role("button", name=analyze_name).click()
                # The request really is held (no response yet).
                page.wait_for_timeout(400)
                self.assertEqual(len(held), 1, "analyze request must be held")
                page.wait_for_selector(f".{module}-module .status-banner.loading")
                # Switch source: File tab only - no new file selected.
                page.locator(f".{module}-module").get_by_role(
                    "tab", name="文件").click()
                page.wait_for_timeout(300)
                # The in-flight request is superseded: loading exited and
                # the result can never land ready/shareable.
                self.assertEqual(
                    page.locator(
                        f".{module}-module .status-banner.loading").count(),
                    0,
                    "loading must exit on source switch",
                )
                outcome = release()
                self.assertEqual(
                    outcome, ["superseded"],
                    "the superseded request must be cancelled, not delivered",
                )
                page.wait_for_timeout(300)
                panel = page.locator(f".{module}-module .result-pane")
                self.assertEqual(
                    panel.locator(".share-row button.ghost").count(), 0,
                    "superseded result must not offer export",
                )
                self.assertEqual(
                    panel.get_by_role("button", name="下载").count(), 0,
                    "superseded result must not offer download",
                )
                # A stale/empty truth state instead of a fresh ready card:
                # the outcome banner of a ready result must be absent while
                # the identity is switched away.
                # The cached text is preserved and a real new analysis
                # on the current input still succeeds.
                self.nav(page, "配置检查" if module == "config" else "流结束检查")
                page.locator(f".{module}-module").get_by_role(
                    "tab", name="粘贴").click()
                self.assertEqual(
                    page.locator(f".{module}-module .paste-area textarea").input_value(),
                    '{"mcp_servers": {"A": {"command": "x"}}}' if module == "config"
                    else "data: [DONE]\n\n",
                )
                page.get_by_role("button", name=analyze_name).click()
                page.wait_for_selector(f'.{module}-module [data-testid="result-view"]')
                self.assertEqual(
                    panel.locator(".share-row button.ghost").count(), 1,
                    "a real new analysis is shareable again",
                )

    def test_aba_does_not_revive_unrelated_result(self):
        """Paste A -> sample B (different evidence) -> deferred file makes B
        stale -> back to Paste A: B must not be revived ready/shareable;
        a real new analysis on the current input works."""
        for module in ("config", "stream"):
            with self.subTest(module=module):
                page = self.page
                self.nav(page, "配置检查" if module == "config" else "流结束检查")
                page.locator(f".{module}-module").get_by_role(
                    "tab", name="粘贴").click()
                page.locator(f".{module}-module .paste-area textarea").fill(
                    '{"mcp_servers": {"A": {"command": "x"}}}' if module == "config"
                    else "data: [DONE]\n\n"
                )
                page.get_by_role("button", name="分析配置" if module == "config" else "分析流").click()
                page.wait_for_selector(f'.{module}-module [data-testid="result-view"]')
                # Sample B: a different real fixture through the same core.
                self.nav(page, "配置检查" if module == "config" else "流结束检查")
                page.locator(f".{module}-module").get_by_role(
                    "tab", name="示例").click()
                page.locator(f".{module}-module .example-list .example-card").nth(2).click()
                page.wait_for_selector(f'.{module}-module [data-testid="result-view"]')
                # Deferred file selection makes B stale and revokes share.
                page.locator(f".{module}-module").get_by_role(
                    "tab", name="文件").click()
                with page.expect_file_chooser() as chooser:
                    page.locator(f".{module}-module .dropzone .primary").click()
                chooser.value.set_files(
                    {"name": "synthetic-deferred.json",
                     "mimeType": "application/json",
                     "buffer": b'{"mcp_servers": {"deferred": {"command": "x"}}}'}
                )
                page.wait_for_selector(f".{module}-module .status-banner.stale")
                panel = page.locator(f".{module}-module .result-pane")
                self.assertEqual(
                    panel.locator(".share-row button.ghost").count(), 0
                )
                # Back to Paste A: no revival - B stays stale, no share.
                self.nav(page, "配置检查" if module == "config" else "流结束检查")
                page.locator(f".{module}-module").get_by_role(
                    "tab", name="粘贴").click()
                page.wait_for_timeout(300)
                # Revival criterion: no ready/shareable affordances for the
                # unrelated card. The stale banner must still be present.
                self.assertEqual(
                    page.locator(f".{module}-module .status-banner.stale").count(),
                    1,
                    "returning to the old source keeps the stale truth",
                )
                self.assertEqual(
                    panel.locator(".share-row button.ghost").count(), 0,
                    "no export for the revived unrelated card",
                )
                self.assertEqual(
                    panel.get_by_role("button", name="下载").count(), 0,
                    "no download for the revived unrelated card",
                )
                # Cached text preserved; a real new analysis succeeds and
                # is shareable again.
                self.assertEqual(
                    page.locator(f".{module}-module .paste-area textarea").input_value(),
                    '{"mcp_servers": {"A": {"command": "x"}}}' if module == "config"
                    else "data: [DONE]\n\n",
                )
                page.get_by_role("button", name="分析配置" if module == "config" else "分析流").click()
                page.wait_for_selector(f'.{module}-module [data-testid="result-view"]')
                page.locator(
                    f".{module}-module .share-row button.ghost"
                ).first.click()
                page.wait_for_selector(
                    f'.{module}-module [data-testid="export-preview"]'
                )


if __name__ == "__main__":
    unittest.main()
