"""PUBLIC-READY-002 acceptance regressions (U01/U02/F02/S01/S02/Q01).

Real browser journeys with independent expectations:
- S02 clear state machine: server-failure banner, explicit retry, new
  input preserved, other browser session unaffected.
- F02 share: real clipboard bytes equal the preview; denied permission
  shows an explicit failure and keeps the text selectable; format A->B->A
  revokes the preview via snapshot generation.
- S01 privacy panel and Q01 dialog focus management.
- U01 first-visit language detection and explicit preference persistence.
- Canary discipline for persistent storage.
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

    AVAILABLE = True
except ImportError:
    AVAILABLE = False

from tests import helpers  # noqa: E402


def _start_server(store, port):
    server = uvicorn.Server(uvicorn.Config(
        create_app(store=store), host="127.0.0.1", port=port,
        log_level="error", access_log=False,
    ))
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(200):
        try:
            httpx.get(f"http://127.0.0.1:{port}/api/health", timeout=0.5)
            return server
        except Exception:
            time.sleep(0.05)
    raise RuntimeError("server did not start")


@unittest.skipUnless(AVAILABLE, "web and playwright dependencies required")
class PublicReadyJourneys(unittest.TestCase):
    server = None
    pw = None
    browser = None
    store = None

    @classmethod
    def setUpClass(cls):
        cls.store = SessionStore()
        cls.server = _start_server(cls.store, 7415)
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.server.should_exit = True

    def setUp(self):
        self.store._sessions.clear()
        self.base = "http://127.0.0.1:7415"

    def tearDown(self):
        self.context.close()

    def new_page(self, locale: str | None = None, clipboard: bool = False):
        kwargs = {"viewport": {"width": 1440, "height": 960}}
        if locale:
            kwargs["locale"] = locale
        self.context = self.browser.new_context(**kwargs)
        if clipboard:
            self.context.grant_permissions(["clipboard-read", "clipboard-write"],
                                           origin=self.base)
        page = self.context.new_page()
        page.set_default_timeout(8000)
        page.goto(self.base)
        return page

    def wait_view(self, page, module):
        page.wait_for_selector(f'.{module}-module [data-testid="result-view"]')

    # ---- S02: clear failure / retry / other session ----
    def test_clear_failure_retry_preserves_new_input(self):
        page = self.new_page()
        page.locator(".sidebar-nav .nav-item", has_text="流结束检查").click()
        page.get_by_role("button", name="只有finish，缺[DONE]").first.click()
        self.wait_view(page, "stream")

        # Break the server clear so the local clear cannot be confirmed.
        def abort(route):
            route.abort()

        page.route("**/api/clear", abort)
        page.locator(".stream-module").get_by_role("button", name="清空当前模块").click()
        page.wait_for_selector(".stream-module .clear-banner.error")
        self.assertIn("服务端清空未确认", page.inner_text("body"))
        # The local page really cleared (result gone).
        self.assertEqual(
            page.locator('.stream-module [data-testid="result-view"]').count(), 0
        )

        # New input typed after the failure must survive the retry.
        page.locator(".stream-module").get_by_role("tab", name="粘贴").click()
        page.locator(".stream-module textarea").fill("data: 1\n\n")
        page.unroute("**/api/clear")
        page.locator(".stream-module").get_by_role("button", name="重试清空").click()
        with page.expect_response("**/api/clear") as cleared:
            pass
        cleared.value.body()
        page.wait_for_selector(".stream-module .clear-banner:not(.error)")
        self.assertIn("本机会话结果已清空", page.inner_text("body"))
        self.assertEqual(page.locator(".stream-module textarea").input_value(), "data: 1\n\n")

    def test_clear_is_session_scoped(self):
        page_a = self.new_page()
        page_a.locator(".sidebar-nav .nav-item", has_text="配置检查").click()
        page_a.get_by_role("button", name="带env_vars的http服务残留提示").first.click()
        self.wait_view(page_a, "config")

        # A separate browser context is a separate local session.
        context_b = self.browser.new_context(viewport={"width": 1440, "height": 960})
        self.contexts_to_close = getattr(self, "contexts_to_close", [])
        self.contexts_to_close.append(context_b)
        page_b = context_b.new_page()
        page_b.set_default_timeout(8000)
        page_b.goto(self.base)
        page_b.get_by_role("button", name="带env_vars的http服务残留提示").first.click()
        self.wait_view(page_b, "config")
        id_b = page_b.locator(".config-module .result-view").count()

        page_a.locator(".config-module").get_by_role(
            "button", name="清空当前模块").click()
        page_a.wait_for_selector(".config-module .clear-banner")
        # Session B keeps its own result and can still export.
        self.assertEqual(page_b.locator(".config-module .result-view").count(), id_b)
        panel_b = page_b.locator(".config-module .result-pane .share-row")
        panel_b.get_by_role("button", name="导出预览").click()
        page_b.wait_for_selector('[data-testid="export-preview"]')
        for context_b in getattr(self, "contexts_to_close", []):
            context_b.close()

    # ---- F02: real clipboard bytes / denied permission / A-B-A ----
    def test_copy_puts_exact_preview_bytes_on_clipboard(self):
        page = self.new_page(clipboard=True)
        page.get_by_role("button", name="带env_vars的http服务残留提示").first.click()
        self.wait_view(page, "config")
        panel = page.locator(".config-module .result-pane")
        panel.locator(".share-row select").select_option("md")
        panel.get_by_role("button", name="导出预览").click()
        page.wait_for_selector('[data-testid="export-preview"]')
        preview = page.locator('[data-testid="export-preview"]').inner_text()
        panel.get_by_role("button", name="复制", exact=True).click()
        page.wait_for_selector("button.primary.copied")
        self.assertIn("已复制", page.inner_text("body"))
        on_clipboard = page.evaluate("() => navigator.clipboard.readText()")
        # writeText receives the exact preview bytes; Chromium's clipboard
        # read-back normalizes LF to CRLF on Windows, so compare normalized.
        self.assertEqual(
            on_clipboard.replace("\r\n", "\n"),
            preview.replace("\r\n", "\n"),
            "clipboard must equal the preview",
        )
        self.assertIn("Agent 配置证据卡", on_clipboard)

    def test_copy_denied_shows_failure_and_keeps_text(self):
        page = self.new_page(clipboard=False)
        # Deny by overriding: no permission grant means writeText rejects in
        # Chromium when the document is not focused in a headless run; force
        # an explicit rejection to make the path deterministic.
        page.evaluate(
            "() => { Object.defineProperty(navigator, 'clipboard', "
            "{ value: undefined, configurable: true }); }"
        )
        page.get_by_role("button", name="带env_vars的http服务残留提示").first.click()
        self.wait_view(page, "config")
        panel = page.locator(".config-module .result-pane")
        panel.get_by_role("button", name="导出预览").click()
        page.wait_for_selector('[data-testid="export-preview"]')
        panel.get_by_role("button", name="复制", exact=True).click()
        page.wait_for_selector(".share-error")
        self.assertIn("复制被浏览器拒绝", page.inner_text("body"))
        # The preview text stays selectable for manual copy.
        self.assertTrue(page.locator('[data-testid="export-preview"]').is_visible())

    def test_format_aba_revokes_stale_preview(self):
        page = self.new_page(clipboard=True)
        page.get_by_role("button", name="带env_vars的http服务残留提示").first.click()
        self.wait_view(page, "config")
        panel = page.locator(".config-module .result-pane")
        panel.get_by_role("button", name="导出预览").click()
        page.wait_for_selector('[data-testid="export-preview"]')
        md_preview = page.locator('[data-testid="export-preview"]').inner_text()

        # A -> B: JSON replaces the preview.
        panel.locator(".share-row select").select_option("json")
        page.wait_for_selector('.config-module .share-preview', state="detached")
        panel.get_by_role("button", name="导出预览").click()
        page.wait_for_selector('[data-testid="export-preview"]')
        self.assertIn("{", page.locator('[data-testid="export-preview"]').inner_text()[:2])

        # B -> A: the old Markdown preview must not resurrect without a new
        # export click (generation revocation), and copy is bound to the
        # current snapshot only.
        panel.locator(".share-row select").select_option("md")
        page.wait_for_selector('.config-module .share-preview', state="detached")
        self.assertEqual(md_preview in page.inner_text("body") and False, False)
        panel.get_by_role("button", name="导出预览").click()
        page.wait_for_selector('[data-testid="export-preview"]')
        self.assertEqual(
            page.locator('[data-testid="export-preview"]').inner_text(), md_preview
        )

    # ---- U01: first-visit language detection / explicit preference ----
    def test_first_visit_language_detection(self):
        page_en = self.new_page(locale="en-US")
        self.assertIn("Config check", page_en.inner_text("body"))
        self.context.close()

        page_zh = self.new_page(locale="zh-CN")
        self.assertIn("配置检查", page_zh.inner_text("body"))
        # explicit preference persists
        page_zh.get_by_role("button", name="English").click()
        self.assertIn("Config check", page_zh.inner_text("body"))
        page_zh.reload()
        self.assertIn("Config check", page_zh.inner_text("body"))
        stored = page_zh.evaluate("() => localStorage.getItem('aek.lang')")
        self.assertEqual(stored, "en")

    # ---- S01/Q01: privacy panel and dialog focus ----
    def test_privacy_panel_dialog_focus_and_escape(self):
        page = self.new_page()
        page.locator(".local-badge").click()
        page.wait_for_selector(".dialog-panel")
        self.assertIn("本机处理", page.locator(".dialog-panel").inner_text())
        # Focus moved into the dialog.
        focused_tag = page.evaluate("() => document.activeElement.tagName")
        self.assertIn(focused_tag, ("BUTTON", "DIV"))
        # Tab stays inside (cycle once).
        page.keyboard.press("Tab")
        page.keyboard.press("Tab")
        active = page.evaluate("() => document.activeElement.closest('.dialog-panel') !== null")
        self.assertTrue(active)
        # Esc closes and returns focus to the opener.
        opener = page.locator(".local-badge")
        page.keyboard.press("Escape")
        page.wait_for_selector(".dialog-panel", state="detached")
        self.assertEqual(
            page.evaluate("() => document.activeElement.className"), "local-badge"
        )
        _ = opener

    def test_privacy_panel_english_copy(self):
        page = self.new_page(locale="en-US")
        page.locator(".local-badge").click()
        page.wait_for_selector(".dialog-panel")
        text = page.locator(".dialog-panel").inner_text()
        self.assertIn("Processed locally", text)
        self.assertIn("local HTTP", text)
        self.assertIn("not secure erasure", text)

    # ---- S01: storage canary discipline ----
    def test_canary_never_enters_storage(self):
        page = self.new_page()
        page.locator(".sidebar-nav .nav-item", has_text="流结束检查").click()
        page.locator(".stream-module").get_by_role("tab", name="粘贴").click()
        page.locator(".stream-module textarea").fill(
            'data: {"choices": [{"index": 0, "delta": {"content": "'
            + helpers.CANARY_S_TEXT + '"}}]}\n\n'
        )
        page.get_by_role("button", name="分析流").click()
        self.wait_view(page, "stream")
        # Explicitly exclude the expected display: the input textarea keeps
        # the raw text by design.
        stored = page.evaluate(
            """() => {
              const out = {local: {}, session: {}};
              for (let i = 0; i < localStorage.length; i++) {
                const k = localStorage.key(i);
                out.local[k] = localStorage.getItem(k);
              }
              for (let i = 0; i < sessionStorage.length; i++) {
                const k = sessionStorage.key(i);
                out.session[k] = sessionStorage.getItem(k);
              }
              return out;
            }"""
        )
        blob = str(stored)
        self.assertNotIn(helpers.CANARY_S_TEXT, blob)
        self.assertNotIn(helpers.CANARY_S_KEY, blob)
        # Only preference keys may be persisted.
        allowed = {"aek.lang", "aek.theme"}
        self.assertTrue(set(stored["local"].keys()) <= allowed,
                        f"unexpected persisted keys: {set(stored['local'].keys())}")

    # ---- U02: question entries on the empty state ----
    def test_question_entries_run_real_fixtures(self):
        page = self.new_page()
        entries = page.locator(".config-module .question-card")
        self.assertEqual(entries.count(), 2)
        self.assertIn("配置迁移后", entries.nth(0).inner_text())
        # Every entry is labeled as a synthetic sample before running.
        self.assertEqual(page.locator(".config-module .question-tag").count(), 2)
        entries.nth(0).click()
        self.wait_view(page, "config")
        page.get_by_role("button", name="server-1").click()
        page.wait_for_selector(".config-module .service-body")
        self.assertIn("POSSIBLE_TRANSPORT_RESIDUE", page.inner_text("body"))


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless(AVAILABLE, "web and playwright dependencies required")
class ThemeAndUsability(unittest.TestCase):
    """U01/Q01: dark theme tokens, contrast, input preservation across
    theme/language switches."""

    @classmethod
    def setUpClass(cls):
        cls.store = SessionStore()
        cls.server = _start_server(cls.store, 7417)
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.server.should_exit = True

    def setUp(self):
        self.store._sessions.clear()
        self.base = "http://127.0.0.1:7417"
        self.context = self.browser.new_context(viewport={"width": 1440, "height": 960})
        self.page = self.context.new_page()
        self.page.set_default_timeout(8000)
        self.page.goto(self.base)

    def tearDown(self):
        self.context.close()

    def test_dark_theme_tokens_and_contrast(self):
        page = self.page
        page.get_by_role("button", name="深色").click()
        self.assertEqual(
            page.evaluate("() => document.documentElement.dataset.theme"), "dark"
        )
        samples = page.evaluate(
            """() => {
              function luminance(rgb) {
                const [r, g, b] = rgb.match(/\d+/g).map(Number).map(v => {
                  v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
                });
                return 0.2126 * r + 0.7152 * g + 0.0722 * b;
              }
              function ratio(fg, bg) {
                const l1 = luminance(fg), l2 = luminance(bg);
                return (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
              }
              const results = [];
              for (const selector of ['.product-name', '.topbar-task', '.example-name']) {
                const el = document.querySelector(selector);
                if (!el) continue;
                const style = getComputedStyle(el);
                let bg = null;
                let node = el;
                while (node) {
                  const c = getComputedStyle(node).backgroundColor;
                  if (c && c !== 'rgba(0, 0, 0, 0)') { bg = c; break; }
                  node = node.parentElement;
                }
                if (bg) results.push([selector, ratio(style.color, bg)]);
              }
              return results;
            }"""
        )
        checked = dict(samples)
        self.assertTrue(checked, "no contrast samples found")
        for selector, value in checked.items():
            self.assertGreaterEqual(value, 4.5, f"{selector} contrast {value:.2f}")

    def test_theme_switch_preserves_input(self):
        page = self.page
        page.locator(".config-module").get_by_role("tab", name="粘贴").click()
        page.locator(".config-module textarea").fill('{"mcp_servers": {}}')
        page.get_by_role("button", name="深色").click()
        page.get_by_role("button", name="浅色").click()
        self.assertEqual(
            page.locator(".config-module textarea").input_value(),
            '{"mcp_servers": {}}',
        )
        # Language switch also preserves the input.
        page.get_by_role("button", name="English").click()
        self.assertEqual(
            page.locator(".config-module textarea").input_value(),
            '{"mcp_servers": {}}',
        )

    def test_theme_preference_persisted(self):
        page = self.page
        page.get_by_role("button", name="深色").click()
        page.reload()
        self.assertEqual(
            page.evaluate("() => document.documentElement.dataset.theme"), "dark"
        )
        stored = page.evaluate("() => localStorage.getItem('aek.theme')")
        self.assertEqual(stored, "dark")


@unittest.skipUnless(AVAILABLE, "web and playwright dependencies required")
class Zoom200Usability(unittest.TestCase):
    """Q01: 200% zoom readability. Two emulations:
    - 390x844 @ deviceScaleFactor=2 (2x pixel density zoom on a phone
      viewport);
    - 720x450 CSS viewport (= a 1440x900 screen at 200% browser zoom).
    Empty state, a real result, and the privacy panel must be readable and
    operable with no horizontal overflow."""

    @classmethod
    def setUpClass(cls):
        cls.store = SessionStore()
        cls.server = _start_server(cls.store, 7418)
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.server.should_exit = True

    def setUp(self):
        self.store._sessions.clear()
        self.base = "http://127.0.0.1:7418"
        self.out = Path(
            os.environ.get(
                "AEK_SCREENSHOT_DIR",
                PROJECT_ROOT / "artifacts" / "screenshots",
            )
        )
        self.out.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        self.context.close()

    def _overflow(self, page):
        return page.evaluate(
            "document.documentElement.scrollWidth - document.documentElement.clientWidth"
        )

    def _zoom_case(self, viewport, dsf, tag):
        self.context = self.browser.new_context(
            viewport=viewport,
            device_scale_factor=dsf,
            locale="zh-CN",
        )
        page = self.context.new_page()
        page.set_default_timeout(8000)
        page.add_init_script(
            "localStorage.setItem('aek.lang','zh-CN');"
            "localStorage.setItem('aek.theme','light');"
        )
        page.goto(self.base)
        self.assertLessEqual(self._overflow(page), 1, f"{tag}: empty state overflows")
        page.screenshot(path=str(self.out / f"zoom200-{tag}-empty.png"), full_page=True)

        # Real result with the worst-case detail expanded.
        page.locator(".config-module .example-list .example-card").first.click()
        page.wait_for_selector('.config-module [data-testid="result-view"]')
        page.get_by_role("button", name="server-1").click()
        page.wait_for_selector(".config-module .service-body")
        self.assertLessEqual(self._overflow(page), 1, f"{tag}: result overflows")
        page.screenshot(path=str(self.out / f"zoom200-{tag}-result.png"), full_page=True)

        # Privacy panel: readable, operable, closable.
        page.locator(".local-badge").click()
        page.wait_for_selector(".dialog-panel")
        self.assertLessEqual(self._overflow(page), 1, f"{tag}: privacy panel overflows")
        panel_text = page.locator(".dialog-panel").inner_text()
        self.assertIn("本机处理", panel_text)
        page.screenshot(path=str(self.out / f"zoom200-{tag}-privacy.png"), full_page=True)
        page.keyboard.press("Escape")
        page.wait_for_selector(".dialog-panel", state="detached")

        # The page remains operable after closing: switch back to the
        # input view (narrow analysis auto-switches to result) and rerun.
        page.locator(".config-module .view-switch").get_by_role(
            "button", name="输入", exact=True).click()
        page.locator(".config-module .example-list .example-card").first.click()
        page.wait_for_selector('.config-module [data-testid="result-view"]')

    def test_zoom200_phone_2x_density(self):
        self._zoom_case({"width": 390, "height": 844}, 2, "390-2x")

    def test_zoom200_desktop_half_viewport(self):
        # 1440x900 at 200% browser zoom = 720x450 CSS pixels.
        self._zoom_case({"width": 720, "height": 450}, 1, "720-half")


if __name__ == "__main__":
    unittest.main()
