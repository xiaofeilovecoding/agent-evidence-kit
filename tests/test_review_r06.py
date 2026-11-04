"""R06 regression: guidance is progressive - one open set per result,
everything else folded but reachable; stream has no duplicated
card-level guidance block."""
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


@unittest.skipUnless(AVAILABLE, 'web and playwright dependencies required')
class R06ProgressiveGuidance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store = SessionStore()
        cls.server = _start_server(cls.store, 7420)
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.server.should_exit = True

    def setUp(self):
        self.store._sessions.clear()
        self.base = "http://127.0.0.1:7420"
        self.context = self.browser.new_context(
            viewport={"width": 1440, "height": 960}, locale="zh-CN"
        )
        self.page = self.context.new_page()
        self.page.set_default_timeout(8000)
        self.page.goto(self.base)

    def tearDown(self):
        self.context.close()

    def test_config_guidance_primary_open_others_folded(self):
        page = self.page
        page.locator(".config-module .example-list .example-card").first.click()
        page.wait_for_selector('.config-module [data-testid="result-view"]')
        page.get_by_role("button", name="server-1").click()
        page.wait_for_selector(".config-module .service-body")
        guidance = page.locator(".config-module .finding-guidance")
        # Three findings: exactly one (the primary warning) expanded.
        self.assertEqual(guidance.count(), 3)
        open_blocks = page.locator(".config-module .finding-guidance .next-steps")
        self.assertEqual(open_blocks.count(), 1)
        self.assertIn(
            "AMBIGUOUS_TRANSPORT", page.inner_text(".config-module .service-body")
        )
        # A folded finding's guidance is reachable via its toggle.
        folded = guidance.nth(2)
        folded.get_by_role("button").click()
        self.assertEqual(page.locator(".config-module .finding-guidance .next-steps").count(), 2)

    def test_stream_no_duplicated_card_level_guidance(self):
        page = self.page
        page.locator(".sidebar-nav .nav-item", has_text="流结束检查").click()
        page.locator(".stream-module .example-list .example-card").nth(1).click()
        page.wait_for_selector('.stream-module [data-testid="result-view"]')
        findings = page.locator(".stream-module .finding-list .finding")
        blocks = page.locator(".stream-module .finding-guidance")
        # One guidance block per finding - no extra card-level duplicate.
        self.assertEqual(blocks.count(), findings.count())
        # Primary expanded, others folded; toggle works both ways.
        self.assertEqual(
            page.locator(".stream-module .finding-guidance .next-steps").count(), 1
        )
        blocks.first.get_by_role("button").click()  # fold the primary
        self.assertEqual(
            page.locator(".stream-module .finding-guidance .next-steps").count(), 0
        )
        blocks.first.get_by_role("button").click()  # unfold again
        self.assertEqual(
            page.locator(".stream-module .finding-guidance .next-steps").count(), 1
        )


if __name__ == "__main__":
    unittest.main()
