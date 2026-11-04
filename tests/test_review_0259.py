"""R03 remainder (02:59 review): file-selection boundaries.

Selection must immediately revoke the previous share/input identity; a
deferred old reader must not pollute a newer input source or a completed
newer analysis; an invalid/oversized new selection must not silently
reuse the previous file's bytes.
"""
from __future__ import annotations

import os
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
class R03FileBoundaries(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store = SessionStore()
        cls.server = _start_server(cls.store, 7421)
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.server.should_exit = True

    def setUp(self):
        self.store._sessions.clear()
        self.base = "http://127.0.0.1:7421"
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
        return page

    def _select_file(self, page, name, buffer):
        # Set files on the hidden input directly: the change event is
        # exactly what a real selection triggers, without chooser races.
        page.locator(".config-module .input-pane").get_by_role(
            "tab", name="文件"
        ).click()
        file_input = page.locator('.config-module input[type="file"]')
        file_input.set_input_files(
            {"name": name, "mimeType": "application/json", "buffer": buffer}
        )

    def test_selection_start_revokes_old_share_immediately(self):
        """A shareable result + a deferred file selection: the old preview
        and its copy/download must be revoked the moment the file is
        selected - before the read ever completes."""
        page = self._defer_page()
        page.locator(".config-module .example-list .example-card").first.click()
        page.wait_for_selector('.config-module [data-testid="result-view"]')
        panel = page.locator(".config-module .result-pane")
        panel.locator(".share-row button.ghost").click()
        page.wait_for_selector('[data-testid="export-preview"]')

        self._select_file(
            page, "synthetic-new.json",
            b'{"mcp_servers": {"new": {"command": "x"}}}',
        )
        # Selection start: old preview gone, no copy/download affordance,
        # even though the deferred read has not completed.
        self.assertEqual(
            panel.locator('[data-testid="export-preview"]').count(), 0,
            "old preview must revoke at selection start",
        )
        self.assertEqual(panel.get_by_role("button", name="复制", exact=True).count(), 0)
        self.assertEqual(panel.get_by_role("button", name="下载").count(), 0)
        page.evaluate("() => window.__releaseFileReads()")
        page.wait_for_timeout(300)
        # After the read lands the input is pending and still not shareable.
        self.assertEqual(
            panel.locator('[data-testid="export-preview"]').count(), 0
        )

    def test_deferred_reader_cannot_pollute_newer_paste_analysis(self):
        """Defer an old file read; switch to Paste, run a new analysis and
        build a fresh preview; releasing the old onload must NOT mark the
        new result stale or overwrite anything."""
        page = self._defer_page()
        self._select_file(
            page, "synthetic-old.json",
            b'{"mcp_servers": {"old": {"command": "x"}}}',
        )
        page.wait_for_selector(".config-module .pending-info")
        pending_before = page.locator(".config-module .dropzone .pending-info").inner_text()
        page.evaluate("() => window.__deferFileReads()")
        # Second (deferred) selection.
        self._select_file(
            page, "synthetic-deferred.json",
            b'{"mcp_servers": {"deferred": {"command": "x"}}}',
        )
        # Switch source to Paste and complete a fresh analysis + preview.
        page.locator(".config-module").get_by_role("tab", name="粘贴").click()
        page.locator(".config-module textarea").fill('{"mcp_servers": {}}')
        page.get_by_role("button", name="分析配置").click()
        page.wait_for_selector('.config-module [data-testid="result-view"]')
        panel = page.locator(".config-module .result-pane")
        panel.locator(".share-row button.ghost").click()
        page.wait_for_selector('[data-testid="export-preview"]')

        page.evaluate("() => window.__releaseFileReads()")
        page.wait_for_timeout(400)
        # The new analysis stays untouched: fresh, no stale banner, preview
        # still present.
        self.assertEqual(
            page.locator(".config-module .status-banner.stale").count(), 0,
            "a late old-file read must not mark the newer result stale",
        )
        self.assertEqual(
            panel.locator('[data-testid="export-preview"]').count(), 1,
            "the fresh preview must survive the late read",
        )
        # If the deferred onload HAD landed it would call invalidate() and
        # mark the fresh result stale (asserted above); the paste input and
        # preview stay untouched either way.
        self.assertNotIn("JSON · 47 B", page.inner_text("body"))

    def test_oversized_selection_does_not_reuse_previous_bytes(self):
        try:
            self._oversized_body()
        except Exception:
            try:
                self.page.screenshot(
                    path=str(
                        Path(os.environ.get(
                            "AEK_SCREENSHOT_DIR",
                            str(PROJECT_ROOT / "artifacts" / "screenshots"),
                        ))
                        / "debug-oversized-hang.png"
                    )
                )
            except Exception:
                pass
            raise

    def _oversized_body(self):
        """A valid selection followed by an oversized one must clear the
        pending input instead of silently keeping the old bytes."""
        page = self.page
        self._select_file(
            page, "synthetic-small.json",
            b'{"mcp_servers": {"small": {"command": "x"}}}',
        )
        page.wait_for_selector(".config-module .pending-info")
        analyze = page.locator(".config-module .analyze-button")
        self.assertFalse(analyze.is_disabled())
        # Oversized selection: the old bytes must be dropped with an
        # explicit status, and analysis must stay disabled.
        import sys as _sys
        print("URL-at-hang-check:", page.url, "closed:", page.is_closed(),
              "eval:", end=" ", file=_sys.stderr)
        try:
            print(page.evaluate("() => location.href"), file=_sys.stderr)
        except Exception as e:
            print("EVALFAIL", str(e)[:80], file=_sys.stderr)
        self._select_file(
            page, "synthetic-huge.json",
            b'{"mcp_servers": {"huge": {"command": "x"}}}' + b" " * (300 * 1024),
        )
        self.assertTrue(
            analyze.is_disabled(),
            "oversized selection must not leave the previous file analyzable",
        )
        self.assertEqual(
            page.locator(".config-module .pending-info").count(),
            1,
            "an explicit status replaces the stale pending info",
        )
        info = page.locator(".config-module .pending-info").inner_text()
        self.assertIn("256KiB", info)


if __name__ == "__main__":
    unittest.main()
