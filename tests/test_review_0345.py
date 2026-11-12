"""0345-round regressions: source switching and in-flight analysis must
invalidate deferred file reads; aborted analyses must exit loading.

R03 remainder: Paste has valid analyzed text -> a deferred File selection
starts -> switch back to Paste WITHOUT editing -> a new analysis is in
flight -> releasing the old reader must neither abort the real request
nor leave a permanent loading state. A-B-A switching covered for both
modules.
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

FILE_READER_DEFER = """
  const OriginalReader = window.FileReader;
  let queue = [];
  window.__deferFileReads = () => { window.__deferred = true; };
  window.__releaseFileReads = () => {
    const jobs = queue;
    queue = [];
    window.__deferred = false;
    for (const job of jobs) job();
  };
  window.FileReader = class extends OriginalReader {
    readAsArrayBuffer(...args) {
      if (window.__deferred) {
        queue.push(() => super.readAsArrayBuffer(...args));
        return;
      }
      return super.readAsArrayBuffer(...args);
    }
  };
"""


@unittest.skipUnless(AVAILABLE, "web and playwright dependencies required")
class R0345SourceSwitch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store = SessionStore()
        cls.server = _start_server(cls.store, 7422)
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.server.should_exit = True

    def setUp(self):
        self.store._sessions.clear()
        self.base = "http://127.0.0.1:7422"
        self.context = self.browser.new_context(
            viewport={"width": 1440, "height": 960}, locale="zh-CN"
        )
        self.page = self.context.new_page()
        self.page.set_default_timeout(8000)
        self.page.goto(self.base)

    def tearDown(self):
        self.context.close()

    def _defer_page(self):
        page = self.page
        page.add_init_script(FILE_READER_DEFER)
        page.reload()
        page.goto(self.base)
        return page

    def nav(self, page, module):
        page.locator(".sidebar-nav .nav-item", has_text=module).click()

    def _paste_and_analyze(self, page, module):
        self.nav(page, "配置检查" if module == "config" else "流结束检查")
        page.locator(f".{module}-module").get_by_role("tab", name="粘贴").click()
        page.locator(f".{module}-module .paste-area textarea").fill(
                    '{"mcp_servers": {}}' if module == "config" else "data: [DONE]\n\n"
                )
        page.get_by_role("button", name="分析配置" if module == "config" else "分析流").click()
        page.wait_for_selector(f'.{module}-module [data-testid="result-view"]')

    def _select_deferred_file(self, page, module, name):
        self.nav(page, "配置检查" if module == "config" else "流结束检查")
        page.locator(f".{module}-module").get_by_role("tab", name="文件").click()
        buffer = (b'{"mcp_servers": {"deferred": {"command": "x"}}}'
                  if name.endswith(".json") else
                  b'data: [DONE]\r\n\r\n')
        with page.expect_file_chooser() as chooser:
            page.locator(f".{module}-module .dropzone .primary").click()
        chooser.value.set_files(
            {"name": name, "mimeType": "application/json", "buffer": buffer}
        )

    # ---- the exact review repro: in-flight analysis vs deferred reader ----
    def test_inflight_analysis_not_aborted_by_deferred_file_release(self):
        for module in ("config", "stream"):
            with self.subTest(module=module):
                page = self._defer_page()
                self._paste_and_analyze(page, module)
                # Genuinely defer the next file read and verify the flag.
                self.nav(page, "配置检查" if module == "config" else "流结束检查")
                page.locator(f".{module}-module").get_by_role(
                    "tab", name="文件").click()
                page.evaluate("() => window.__deferFileReads()")
                self.assertTrue(
                    page.evaluate("() => window.__deferred === true"),
                    "file reads must actually be deferred",
                )
                fname = ("synthetic-deferred."
                         + ("json" if module == "config" else "sse"))
                with page.expect_file_chooser() as chooser:
                    page.locator(f".{module}-module .dropzone .primary").click()
                chooser.value.set_files(
                    {"name": fname, "mimeType": "application/json",
                     "buffer": (b'{"mcp_servers": {"deferred": {"command": "x"}}}'
                                if module == "config"
                                else b'data: [DONE]\r\n\r\n')}
                )
                # The read is queued but not completed: no pending info yet.
                page.wait_for_timeout(300)
                self.assertEqual(
                    page.locator(f".{module}-module .pending-info").count(),
                    0,
                    "deferred read must not have completed",
                )
                # Switch back to Paste WITHOUT editing the cached text.
                self.nav(page, "配置检查" if module == "config" else "流结束检查")
                page.locator(f".{module}-module").get_by_role(
                    "tab", name="粘贴").click()
                # Hold the new analysis in flight via route interception.
                analyze_name = "分析配置" if module == "config" else "分析流"
                held = []
                pattern = f"**/api/{module}/analyze*"

                def hold(route):
                    held.append((route, route.fetch()))

                page.route(pattern, hold)
                page.get_by_role("button", name=analyze_name).click()
                page.wait_for_selector(f".{module}-module .status-banner.loading")
                for _ in range(100):
                    if held:
                        break
                    page.wait_for_timeout(50)
                self.assertTrue(held, "analyze request must be genuinely held")
                # Release the deferred read FIRST: old bytes are discarded
                # by ticket/source checks; the analysis stays in flight.
                page.evaluate("() => window.__releaseFileReads()")
                page.wait_for_timeout(400)
                self.assertEqual(len(held), 1,
                                 "analysis must not be cancelled")
                self.assertTrue(
                    page.locator(
                        f".{module}-module .status-banner.loading"
                    ).is_visible(),
                    "held analysis still in flight",
                )
                # Release the real request: it completes normally.
                for route, upstream in held:
                    with page.expect_response(pattern) as delivered:
                        route.fulfill(response=upstream)
                    delivered.value.body()
                page.unroute(pattern)
                page.wait_for_selector(
                    f".{module}-module .status-banner.loading",
                    state="detached",
                    timeout=8000,
                )
                self.assertNotIn(
                    "正在分析", page.inner_text("body"),
                    "analysis must not stay loading after the deferred read",
                )
                # The cached paste text is preserved.
                self.assertEqual(
                    page.locator(f".{module}-module .paste-area textarea").input_value(),
                    '{"mcp_servers": {}}' if module == "config" else "data: [DONE]\n\n",
                )
                # And the identity is truthful: re-analysis still works.
                page.get_by_role("button", name=analyze_name).click()
                page.wait_for_selector(f'.{module}-module [data-testid="result-view"]')

    def test_aba_switch_keeps_result_truthful(self):
        """0420 identity contract: Paste result -> deferred file select ->
        back to Paste -> release: the selection is an identity change, so
        the old result stays stale with NO share affordances (no revival),
        the cached text is preserved, and a real new analysis succeeds."""
        for module in ("config", "stream"):
            with self.subTest(module=module):
                page = self._defer_page()
                self._paste_and_analyze(page, module)
                self._select_deferred_file(page, module, "synthetic-deferred."
                                           + ("json" if module == "config" else "sse"))
                self.nav(page, "配置检查" if module == "config" else "流结束检查")
                page.locator(f".{module}-module").get_by_role(
                    "tab", name="粘贴").click()
                page.evaluate("() => window.__releaseFileReads()")
                page.wait_for_timeout(300)
                # Truthful identity: stale, no export, no download.
                self.assertEqual(
                    page.locator(
                        f".{module}-module .status-banner.stale").count(), 1,
                    "the identity change must keep the old result stale",
                )
                self.assertEqual(
                    page.locator(
                        f".{module}-module .result-pane .share-row button.ghost"
                    ).count(),
                    0,
                    "no export affordance for the revoked result",
                )
                self.assertEqual(
                    page.locator(
                        f".{module}-module .result-pane"
                    ).get_by_role("button", name="下载").count(),
                    0,
                    "no download affordance for the revoked result",
                )
                # Cached text preserved; a real new analysis still succeeds.
                self.assertEqual(
                    page.locator(f".{module}-module .paste-area textarea").input_value(),
                    '{"mcp_servers": {}}' if module == "config" else "data: [DONE]\n\n"
                )
                page.get_by_role(
                    "button", name="分析配置" if module == "config" else "分析流"
                ).click()
                page.wait_for_selector(f'.{module}-module [data-testid="result-view"]')
                self.assertEqual(
                    page.locator(
                        f".{module}-module .status-banner.stale").count(), 0,
                    "the new analysis is fresh",
                )

    def test_no_debug_console_output_in_production(self):
        page = self.page
        logs = []
        page.on("console", lambda m: logs.append(m.text) if "[dbg]" in m.text else None)
        self._paste_and_analyze(page, "config")
        self.assertEqual(logs, [], "production build must not contain [dbg] logs")


if __name__ == "__main__":
    unittest.main()
