"""0457-round regressions: revocation must bump the analysis token.

R03/P1 final gap: revokeIdentity did not increment the revisionRef that
runAnalysis' completion callback checks, so a held demo response could
land ready/shareable after the identity had switched. These tests hold
the real demo request, switch source, release the response, and assert
the identity contract. They also cover the "response delivered over the
wire but discarded by the token" boundary (transport cancel is not the
protection).
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
class DemoHoldSourceSwitch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store = SessionStore()
        cls.server = _start_server(cls.store, 7424)
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.server.should_exit = True

    def setUp(self):
        self.store._sessions.clear()
        self.base = "http://127.0.0.1:7424"
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

    def _hold_demo_and_run_sample(self, page, module):
        """Hold the demo request; run a sample; return release() and the
        held list. The request is demonstrably in flight (held, no
        response)."""
        held = []
        pattern = f"**/api/{module}/demo"

        def hold(route):
            held.append((route, route.fetch()))

        page.route(pattern, hold)
        page.locator(f".{module}-module .example-list .example-card").nth(0).click()
        page.wait_for_selector(f".{module}-module .status-banner.loading")
        for _ in range(100):
            if held:
                break
            page.wait_for_timeout(50)
        assert held, "demo request was not held"

        def release():
            delivered = []
            for route, upstream in held:
                try:
                    with page.expect_response(pattern, timeout=2500) as info:
                        route.fulfill(response=upstream)
                    info.value.body()
                    delivered.append(True)
                except Exception:
                    delivered.append(False)
            page.unroute(pattern)
            return delivered

        return release

    def test_held_demo_does_not_land_after_source_switch(self):
        """hold demo -> sample -> switch to Paste -> loading exits -> release
        the response: the old sample must not land ready/shareable; cached
        text preserved; a real new analysis still works."""
        for module in ("config", "stream"):
            with self.subTest(module=module):
                page = self.page
                self.nav(page, "配置检查" if module == "config" else "流结束检查")
                page.locator(f".{module}-module").get_by_role(
                    "tab", name="粘贴").click()
                cached = (
                    '{"mcp_servers": {"A": {"command": "x"}}}' if module == "config"
                    else "data: [DONE]\n\n"
                )
                page.locator(f".{module}-module textarea").fill(cached)
                # Back to Examples and run a sample with the request held.
                page.locator(f".{module}-module").get_by_role(
                    "tab", name="示例").click()
                release = self._hold_demo_and_run_sample(page, module)
                # Switch source to Paste: identity revocation while the
                # demo response is still held.
                self.nav(page, "配置检查" if module == "config" else "流结束检查")
                page.locator(f".{module}-module").get_by_role(
                    "tab", name="粘贴").click()
                page.wait_for_timeout(300)
                # Loading exited; nothing ready/shareable.
                self.assertEqual(
                    page.locator(
                        f".{module}-module .status-banner.loading").count(),
                    0,
                    "loading must exit on source switch",
                )
                self.assertEqual(
                    page.locator(
                        f'.{module}-module [data-testid="result-view"]'
                    ).count(),
                    0,
                    "held sample must not have landed",
                )
                # Release the real response: discarded by the analysis
                # token even though the transport delivered it.
                delivered = release()
                page.wait_for_timeout(400)
                self.assertEqual(
                    page.locator(
                        f'.{module}-module [data-testid="result-view"]'
                    ).count(),
                    0,
                    "late demo response must not land after revocation",
                )
                panel = page.locator(f".{module}-module .result-pane")
                self.assertEqual(
                    panel.locator(".share-row button.ghost").count(), 0,
                    "no export for the late sample",
                )
                # Cached paste text preserved; a real new analysis works
                # and is shareable again.
                self.assertEqual(
                    page.locator(f".{module}-module textarea").input_value(),
                    cached,
                )
                page.locator(f".{module}-module").get_by_role(
                    "tab", name="粘贴").click()
                page.get_by_role(
                    "button", name="分析配置" if module == "config" else "分析流"
                ).click()
                page.wait_for_selector(f'.{module}-module [data-testid="result-view"]')
                self.assertEqual(
                    panel.locator(".share-row button.ghost").count(), 1,
                    "a real new analysis is shareable again",
                )


if __name__ == "__main__":
    unittest.main()
