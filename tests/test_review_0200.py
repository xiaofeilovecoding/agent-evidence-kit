"""Independent failing-then-passing assertions for Codex review R01-R05.

Each test encodes the acceptance expectation, not the probe's
implementation. Config and stream paths share the logic; both are
covered where applicable.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "tests"))

from test_public_ready import _start_server  # noqa: E402  (reuses harness)

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


@unittest.skipUnless(AVAILABLE, 'web and playwright dependencies required')
class Review0200Fixes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store = SessionStore()
        cls.server = _start_server(cls.store, 7419)
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.server.should_exit = True

    def setUp(self):
        self.store._sessions.clear()
        self.base = "http://127.0.0.1:7419"
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

    def run_sample(self, page, module, index=0):
        self.nav(page, "配置检查" if module == "config" else "流结束检查")
        page.locator(f".{module}-module .example-list .example-card").nth(index).click()
        page.wait_for_selector(f'.{module}-module [data-testid="result-view"]')

    def panel(self, page, module):
        return page.locator(f".{module}-module .result-pane")

    def edit_input(self, page, module):
        self.nav(page, "配置检查" if module == "config" else "流结束检查")
        page.locator(f".{module}-module").get_by_role("tab", name="粘贴").click()
        page.locator(f".{module}-module .paste-area textarea").fill(
            '{"mcp_servers": {}}' if module == "config" else "data: [DONE]\n\n"
        )
        page.wait_for_selector(f".{module}-module .status-banner.stale")

    # ---- R01: stale result must not be re-shareable ----
    def test_r01_stale_result_cannot_be_re_exported(self):
        for module in ("config", "stream"):
            with self.subTest(module=module):
                page = self.page
                self.run_sample(page, module)
                panel = self.panel(page, module)
                panel.locator(".share-row button.ghost").click()
                page.wait_for_selector(
                    f'.{module}-module [data-testid="export-preview"]'
                )
                self.edit_input(page, module)
                self.assertEqual(
                    panel.locator('[data-testid="export-preview"]').count(),
                    0,
                    "stale preview must be revoked",
                )
                self.assertEqual(
                    panel.locator(".share-row button.ghost").count(),
                    0,
                    "stale result must not offer an export action",
                )
                self.assertEqual(
                    panel.get_by_role("button", name="下载").count(),
                    0,
                    "stale result must not offer download",
                )

    def test_r01_error_state_hides_share(self):
        page = self.page
        self.run_sample(page, "config")
        page.locator(".config-module").get_by_role("tab", name="粘贴").click()
        page.locator(".config-module .paste-area textarea").fill("x" * (300 * 1024))
        page.get_by_role("button", name="分析配置").click()
        page.wait_for_selector(".config-module .status-banner.error")
        panel = self.panel(page, "config")
        self.assertEqual(
            panel.locator(".share-row button.ghost").count(),
            0,
            "error state must not offer export",
        )
        self.assertEqual(
            panel.get_by_role("button", name="下载").count(),
            0,
            "error state must not offer download",
        )

    # ---- R02: clear pending/unconfirmed gates analysis ----
    def _demo_spy(self, page):
        seen = []
        page.on(
            "request",
            lambda req: seen.append(req.url) if "/demo" in req.url else None,
        )
        return seen

    def test_r02_clear_pending_gates_samples_then_real_ack(self):
        for module in ("config", "stream"):
            with self.subTest(module=module):
                page = self.page
                self.run_sample(page, module)
                held = []
                page.route("**/api/clear", lambda r: held.append(r))
                page.locator(f".{module}-module").get_by_role(
                    "button", name="清空当前模块"
                ).click()
                self.assertEqual(
                    page.locator(
                        f'.{module}-module [data-testid="result-view"]'
                    ).count(),
                    0,
                    "local revoke must be immediate",
                )
                demo = self._demo_spy(page)
                self.assertTrue(
                    page.locator(
                        f".{module}-module .example-list .example-card"
                    ).first.is_disabled(),
                    "sample button must be gated while clear pending",
                )
                self.assertTrue(
                    page.locator(f".{module}-module .analyze-button").is_disabled(),
                    "analyze button must be gated while clear pending",
                )
                page.wait_for_timeout(200)
                self.assertEqual(demo, [])
                for r in held:
                    r.continue_()
                page.wait_for_selector("text=本机会话结果已清空")
                page.locator(
                    f".{module}-module .example-list .example-card"
                ).nth(0).click()
                page.wait_for_selector(f'.{module}-module [data-testid="result-view"]')
                page.unroute("**/api/clear")

    def test_r02_global_clear_no_premature_success_and_gates(self):
        page = self.page
        self.run_sample(page, "config")
        held = []
        page.route("**/api/clear", lambda r: held.append(r))
        page.get_by_role("button", name="清空全部", exact=True).click()
        self.assertNotIn(
            "本机会话结果已清空",
            page.inner_text("body"),
            "no success wording before server ack",
        )
        demo = self._demo_spy(page)
        self.assertTrue(
            page.locator(
                ".config-module .example-list .example-card"
            ).first.is_disabled(),
            "sample button must be gated while global clear pending",
        )
        page.wait_for_timeout(200)
        self.assertEqual(demo, [])
        for r in held:
            r.continue_()
        page.wait_for_selector("text=本机会话结果已清空")
        page.locator(".config-module .example-list .example-card").nth(0).click()
        page.wait_for_selector('.config-module [data-testid="result-view"]')

    def test_r02_clear_unconfirmed_blocks_analysis_until_retry(self):
        page = self.page
        self.run_sample(page, "config")
        page.route("**/api/clear", lambda r: r.abort())
        page.locator(".config-module").get_by_role(
            "button", name="清空当前模块"
        ).click()
        page.wait_for_selector(".config-module .clear-banner.error")
        demo = self._demo_spy(page)
        self.assertTrue(
            page.locator(
                ".config-module .example-list .example-card"
            ).first.is_disabled(),
            "sample button must stay gated while clear unconfirmed",
        )
        self.assertTrue(
            page.locator(".config-module .analyze-button").is_disabled(),
            "analyze button must stay gated while clear unconfirmed",
        )
        page.wait_for_timeout(200)
        self.assertEqual(demo, [])
        page.unroute("**/api/clear")
        page.locator(".config-module").get_by_role("button", name="重试清空").click()
        page.wait_for_selector("text=本机会话结果已清空")
        page.locator(".config-module .example-list .example-card").nth(0).click()
        page.wait_for_selector('.config-module [data-testid="result-view"]')

    # ---- R03: stale FileReader cannot restore cleared input ----
    def test_r03_deferred_file_read_cannot_land_after_clear(self):
        page = self.page
        page.add_init_script(FILE_READER_DEFER)
        # init scripts apply to the next navigation.
        page.reload()
        page.locator(".config-module .input-pane").get_by_role(
            "tab", name="文件"
        ).click()
        page.locator(".config-module .dropzone .primary").click()
        page.locator('.dropzone input[type="file"]').set_input_files(
            {
                "name": "synthetic-old.json",
                "mimeType": "application/json",
                "buffer": b'{"mcp_servers": {"old": {"command": "x"}}}',
            }
        )
        page.wait_for_selector(".config-module .pending-info")
        # Defer all subsequent file reads, then clear while a re-selected
        # file read is pending.
        page.evaluate("() => window.__deferFileReads()")
        page.locator('.dropzone input[type="file"]').set_input_files(
            {
                "name": "synthetic-late.json",
                "mimeType": "application/json",
                "buffer": b'{"mcp_servers": {"late": {"command": "x"}}}',
            }
        )
        page.locator(".config-module").get_by_role(
            "button", name="清空当前模块"
        ).click()
        page.wait_for_selector(".config-module .clear-banner")
        page.evaluate("() => window.__releaseFileReads()")
        page.wait_for_timeout(500)
        self.assertEqual(
            page.locator(".config-module .pending-info").count(),
            0,
            "stale/late file bytes must not restore pending input after clear",
        )
        self.assertTrue(
            page.locator(".config-module .analyze-button").is_disabled(),
            "analyze must stay disabled after confirmed clear",
        )

    # ---- R04: late copy feedback cannot mark a newer preview copied ----
    def test_r04_late_copy_does_not_mark_new_preview_copied(self):
        page = self.page
        self.context.grant_permissions(
            ["clipboard-read", "clipboard-write"], origin=self.base
        )
        self.run_sample(page, "config")
        panel = self.panel(page, "config")
        panel.locator(".share-row button.ghost").click()
        page.wait_for_selector('[data-testid="export-preview"]')
        page.evaluate(
            """() => {
              const orig = navigator.clipboard.writeText.bind(navigator.clipboard);
              navigator.clipboard.writeText = (text) => new Promise((resolve, reject) => {
                window.__resolveWrite = () => orig(text).then(resolve, reject);
              });
            }"""
        )
        panel.get_by_role("button", name="复制", exact=True).click()
        # New snapshot: JSON format with a fresh preview (never copied).
        panel.locator(".share-row select").select_option("json")
        panel.locator(".share-row button.ghost").click()
        page.wait_for_selector('[data-testid="export-preview"]')
        self.assertIn(
            "{", page.locator('[data-testid="export-preview"]').inner_text()[:1]
        )
        page.evaluate("() => window.__resolveWrite && window.__resolveWrite()")
        page.wait_for_timeout(300)
        pane_text = self.panel(page, "config").inner_text()
        self.assertNotIn(
            "已复制",
            pane_text,
            "late copy feedback must not attach to the newer preview",
        )

    # ---- R05: valid TOML paste auto-detects correctly ----
    def test_r05_toml_table_header_auto_format(self):
        page = self.page
        self.nav(page, "配置检查")
        page.locator(".config-module").get_by_role("tab", name="粘贴").click()
        toml = '[mcp_servers.synthetic]\ncommand = "python"\n'
        page.locator(".config-module .paste-area textarea").fill(toml)
        self.assertIn(
            "TOML",
            page.inner_text(".config-module .format-row"),
            "TOML table header must auto-detect as TOML",
        )
        page.get_by_role("button", name="分析配置").click()
        page.wait_for_selector('.config-module [data-testid="result-view"]')
        self.assertIn("server-1", page.inner_text("body"))

    def test_r05_json_array_still_auto_json(self):
        page = self.page
        self.nav(page, "配置检查")
        page.locator(".config-module").get_by_role("tab", name="粘贴").click()
        page.locator(".config-module .paste-area textarea").fill('[{"mcpServers": {}}]')
        self.assertIn("JSON", page.inner_text(".config-module .format-row"))
        page.get_by_role("button", name="分析配置").click()
        page.wait_for_selector(".config-module .result-error")
        self.assertIn("INVALID_STRUCTURE", page.inner_text("body"))


if __name__ == "__main__":
    unittest.main()
