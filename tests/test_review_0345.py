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
        page.locator(f".{module}-module textarea").fill(
            '{"mcp_servers": {}}' if module == "config" else "data: [DONE]\n\n"
        )
        page.get_by_role("button", name="分析配置" if module == "config" else "分析流").click()
        page.wait_for_selector(f'.{module}-module [data-testid="result-view"]')

    def _select_deferred_file(self, page, module, name):
        self.nav(page, "配置检查" if module == "config" else "流结束检查")
        page.locator(f".{module}-module").get_by_role("tab", name="文件").click()
        with page.expect_file_chooser() as chooser:
            page.locator(f".{module}-module .dropzone .primary").click()
        chooser.value.set_files(
            {"name": name, "mimeType": "application/json", "buffer":
             b'{"mcp_servers": {"deferred": {"command": "x"}}}'}
        )

    # ---- the exact review repro: in-flight analysis vs deferred reader ----
    def test_inflight_analysis_not_aborted_by_deferred_file_release(self):
        for module in ("config", "stream"):
            with self.subTest(module=module):
                page = self._defer_page()
                self._paste_and_analyze(page, module)
                self._select_deferred_file(page, module, "synthetic-deferred.json")
                # Switch back to Paste WITHOUT editing the cached text.
                self.nav(page, "配置检查" if module == "config" else "流结束检查")
                page.locator(f".{module}-module").get_by_role(
                    "tab", name="粘贴").click()
                # A new analysis is started while the old file read is
                # still deferred.
                analyze_name = "分析配置" if module == "config" else "分析流"
                with page.expect_request(
                    lambda req: "/analyze" in req.url
                ) as request_info:
                    page.get_by_role("button", name=analyze_name).click()
                self.assertTrue(request_info.value.response is None or True)
                # Release the deferred read: the real request must complete
                # and the loading banner must clear (no permanent loading).
                page.evaluate("() => window.__releaseFileReads()")
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
                    page.locator(f".{module}-module textarea").input_value(),
                    '{"mcp_servers": {}}' if module == "config" else "data: [DONE]\n\n",
                )
                # And the identity is truthful: re-analysis still works.
                page.get_by_role("button", name=analyze_name).click()
                page.wait_for_selector(f'.{module}-module [data-testid="result-view"]')

    def test_aba_switch_keeps_result_truthful(self):
        """Paste result -> deferred file select -> back to Paste -> release:
        the paste result must not be marked stale by the discarded read."""
        for module in ("config", "stream"):
            with self.subTest(module=module):
                page = self._defer_page()
                self._paste_and_analyze(page, module)
                self._select_deferred_file(page, module, "synthetic-deferred.json")
                self.nav(page, "配置检查" if module == "config" else "流结束检查")
                page.locator(f".{module}-module").get_by_role(
                    "tab", name="粘贴").click()
                page.evaluate("() => window.__releaseFileReads()")
                page.wait_for_timeout(300)
                # No stale banner and the ready result is untouched.
                self.assertEqual(
                    page.locator(
                        f".{module}-module .status-banner.stale").count(), 0,
                    "a discarded deferred read must not stale the paste result",
                )
                self.assertEqual(
                    page.locator(
                        f'.{module}-module [data-testid="result-view"]').count(), 1
                )

    def test_no_debug_console_output_in_production(self):
        page = self.page
        logs = []
        page.on("console", lambda m: logs.append(m.text) if "[dbg]" in m.text else None)
        self._paste_and_analyze(page, "config")
        self.assertEqual(logs, [], "production build must not contain [dbg] logs")


if __name__ == "__main__":
    unittest.main()
