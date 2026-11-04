"""Real-browser journeys for Agent Evidence Kit (gate C).

Covers: both modules' file/paste -> analyze -> evidence -> export -> clear,
TOML paste with explicit format selection (R02), stream filters/pagination
(fixed: valid-stream fixture and honest problem-filter expectations),
390px layout with expanded details (R06), zh/en switch, second-tab session
reuse (R04), stale/late responses, real response/export canary collection,
and the static showcase (no /api, no external requests).
"""
from __future__ import annotations

import json
import os
import re
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
    from fastapi import FastAPI
    from fastapi.staticfiles import StaticFiles
    from playwright.sync_api import sync_playwright

    from agent_evidence_kit.server.app import create_app
    from agent_evidence_kit.server.sessions import SessionStore

    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

from tests import helpers  # noqa: E402

# Portable default: relative to the project's artifacts directory; the
# environment can override. Never an absolute developer-machine path.
ARTIFACTS = Path(
    os.environ.get(
        "AEK_SCREENSHOT_DIR",
        PROJECT_ROOT / "artifacts" / "screenshots",
    )
)
SHOWCASE_DIST = PROJECT_ROOT / "frontend" / "dist-showcase"
BASE = "http://127.0.0.1:7411"
SHOWCASE_BASE = "http://127.0.0.1:7412"

CANARY = "canary-secret-lambda99"


def _start_server(app, port: int):
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error",
                            access_log=False)
    server = uvicorn.Server(config)
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(100):
        try:
            httpx.get(f"http://127.0.0.1:{port}/api/health", timeout=0.5)
            return server
        except Exception:
            time.sleep(0.1)
    raise RuntimeError(f"server on {port} did not start")


@unittest.skipUnless(PLAYWRIGHT_AVAILABLE, "playwright not installed")
class BrowserJourney(unittest.TestCase):
    server = None
    showcase_server = None
    pw = None
    browser = None

    @classmethod
    def setUpClass(cls):
        cls.store = SessionStore()
        cls.server = _start_server(create_app(store=cls.store), 7411)
        showcase_app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
        showcase_app.mount("/", StaticFiles(directory=str(SHOWCASE_DIST), html=True))
        cls.showcase_server = _start_server(showcase_app, 7412)
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch()
        ARTIFACTS.mkdir(parents=True, exist_ok=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.server.should_exit = True
        cls.showcase_server.should_exit = True

    def setUp(self):
        # Drop sessions from previous tests: the server enforces MAX_SESSIONS.
        self.store._sessions.clear()
        self.context = self.browser.new_context(viewport={"width": 1440, "height": 960})
        self.page = self.context.new_page()
        self.console_errors: list[str] = []
        self.page.on(
            "console",
            lambda msg: self.console_errors.append(msg.text)
            if msg.type == "error"
            else None,
        )
        self.page.on("pageerror", lambda err: self.console_errors.append(str(err)))
        # Real response collection for privacy canaries: bodies + URLs.
        self.api_calls: list[str] = []
        self.response_bodies: list[str] = []
        self.page.on(
            "request",
            lambda req: self.api_calls.append(req.url) if "/api/" in req.url else None,
        )
        self.page.on(
            "response",
            lambda res: self._collect_response(res),
        )

    def _collect_response(self, res):
        if "/api/" not in res.url:
            return
        try:
            self.response_bodies.append(res.text())
        except Exception:
            pass

    def tearDown(self):
        self.context.close()

    def assert_no_canary_outside_input(self, canary: str = CANARY):
        """Real canary check: every API response body, URL, console error,
        and the on-page results area must be canary-free."""
        result_html = self.page.inner_html(".result-pane")
        header_html = self.page.inner_html(".topbar")
        self.assertNotIn(canary, result_html)
        self.assertNotIn(canary, header_html)
        for url in self.api_calls:
            self.assertNotIn(canary, url)
        for body in self.response_bodies:
            self.assertNotIn(canary, body, "canary leaked in an API response")
        for error in self.console_errors:
            self.assertNotIn(canary, error)

    def view(self, module: str):
        """Locator scoped to one module wrapper (both stay mounted)."""
        return self.page.locator(f".{module}-module")

    def wait_view(self, module: str):
        self.page.wait_for_selector(f'.{module}-module [data-testid="result-view"]')

    def result_panel(self, module: str):
        return self.view(module).locator(".result-pane")

    def run_config_case(self, description: str):
        self.page.locator(".sidebar-nav .nav-item", has_text="配置检查").click()
        self.view("config").get_by_role("button", name=description).first.click()
        self.wait_view("config")

    def run_stream_case(self, description: str):
        self.page.locator(".sidebar-nav .nav-item", has_text="流结束检查").click()
        self.view("stream").get_by_role("button", name=description).first.click()
        self.wait_view("stream")


    # ---- config journey (paste -> analyze -> export -> clear) ----
    def test_config_paste_journey_and_export(self):
        self.page.goto(BASE)
        self.page.locator(".sidebar-nav .nav-item", has_text="配置检查").click()
        self.view("config").get_by_role("tab", name="粘贴").click()
        self.view("config").locator("textarea").fill(helpers.residue_config())
        # R02: auto-detect chooses JSON here; the indicator is visible.
        self.view("config").get_by_role("button", name="分析配置").click()
        self.wait_view("config")
        self.view("config").get_by_role("button", name="server-1").click()
        self.view("config").locator(".service-body").wait_for()
        body = self.page.inner_text("body")
        self.assertIn("POSSIBLE_TRANSPORT_RESIDUE", body)
        self.assertIn("server-1", body)
        self.assert_no_canary_outside_input(helpers.CANARY_KEY)
        self.assert_no_canary_outside_input(helpers.CANARY_URL)

        # Export preview + download match.
        self.result_panel("config").locator(".share-row select").select_option("md")
        self.result_panel("config").get_by_role("button", name="导出预览").click()
        self.result_panel("config").locator('[data-testid="export-preview"]').wait_for()
        preview = self.result_panel("config").locator('[data-testid="export-preview"]').inner_text()
        self.assertIn("Agent 配置证据卡", preview)
        self.assertNotIn(helpers.CANARY_KEY, preview)
        with self.page.expect_download() as download_info:
            self.result_panel("config").get_by_role("button", name="下载").click()
        saved = Path(download_info.value.path()).read_text(encoding="utf-8")
        self.assertEqual(saved, preview, "download must match preview")

        self.view("config").get_by_role("button", name="清空当前模块").click()
        self.view("config").locator(".empty-state").wait_for()
        self.assertEqual(self.console_errors, [])

    # ---- R02: TOML paste with correctable format selection ----
    def test_toml_paste_explicit_format(self):
        self.page.goto(BASE)
        self.page.locator(".sidebar-nav .nav-item", has_text="配置检查").click()
        self.view("config").get_by_role("tab", name="粘贴").click()

        # R05: a TOML [table] header auto-detects as TOML (bracket
        # content is a table name, not a JSON value token) and analyzes
        # cleanly without a manual override.
        toml = '[mcp_servers.demo]\ncommand = "python"\n'
        self.view("config").locator("textarea").fill(toml)
        self.assertIn("TOML", self.view("config").locator(".format-row").inner_text())
        self.view("config").get_by_role("button", name="分析配置").click()
        self.wait_view("config")
        self.view("config").get_by_role("button", name="server-1").click()
        self.view("config").locator(".service-body").wait_for()
        self.assertIn("server-1", self.page.inner_text("body"))
        self.assertIn("NOT_VALIDATED", self.page.inner_text("body"))

        # TOML transport conflict via explicit format.
        conflict = (
            "[mcp_servers.media-bridge]\n"
            'url = "https://media.example.invalid/mcp"\n'
            'command = "uvx"\n'
        )
        self.view("config").locator("textarea").fill(conflict)
        self.view("config").locator("#config-format-select").select_option("toml")
        self.view("config").get_by_role("button", name="分析配置").click()
        self.wait_view("config")
        self.view("config").get_by_role("button", name="server-1").click()
        self.view("config").locator(".service-body").wait_for()
        self.assertIn("AMBIGUOUS_TRANSPORT", self.page.inner_text("body"))

        # Invalid structure array: JSON array gives a stable input error.
        self.view("config").locator("textarea").fill('[{"a": 1}]')
        self.view("config").locator("#config-format-select").select_option("json")
        self.view("config").get_by_role("button", name="分析配置").click()
        self.view("config").locator(".result-error").wait_for()
        self.assertIn("INVALID_STRUCTURE", self.page.inner_text("body"))
        self.assertEqual(self.console_errors, [])

    # ---- stream journey + filters + pagination (fixed) ----
    def test_stream_journey_filters_pagination(self):
        self.page.goto(BASE)
        self.page.locator(".sidebar-nav .nav-item", has_text="流结束检查").click()
        self.run_stream_case("只有finish，缺[DONE]")
        body = self.page.inner_text("body")
        self.assertIn("FINISH_WITHOUT_DONE", body)
        self.assertIn("未观察到", body)  # DONE evidence off
        # Filter to end-related events, then select one.
        self.view("stream").get_by_role("button", name="结束相关").click()
        self.view("stream").locator(".timeline-row").first.click()
        self.assertIn("选中事件证据", self.page.inner_text("body"))
        self.assert_no_canary_outside_input()

        # Export preview + download.
        self.result_panel("stream").locator(".share-row select").select_option("md")
        self.result_panel("stream").get_by_role("button", name="导出预览").click()
        self.result_panel("stream").locator('[data-testid="export-preview"]').wait_for()
        preview = self.result_panel("stream").locator('[data-testid="export-preview"]').inner_text()
        self.assertNotIn(CANARY, preview)
        self.assertIn("流结束证据卡", preview)
        with self.page.expect_download() as download_info:
            self.result_panel("stream").get_by_role("button", name="下载").click()
        saved = Path(download_info.value.path()).read_text(encoding="utf-8")
        self.assertEqual(saved, preview)

        self.view("stream").get_by_role("button", name="清空当前模块").click()
        self.view("stream").locator(".empty-state").wait_for()
        self.assertEqual(self.console_errors, [])

    def test_stream_pagination_50_per_page(self):
        """122 valid chunk events: 50/page, 3 pages; filters are honest."""
        self.page.goto(BASE)
        self.page.locator(".sidebar-nav .nav-item", has_text="流结束检查").click()
        self.view("stream").get_by_role("tab", name="粘贴").click()
        stream = helpers.chunk("OK") * 120 + helpers.chunk(finish="stop") + helpers.done()
        self.view("stream").locator("textarea").fill(stream)
        self.view("stream").get_by_role("button", name="分析流").click()
        self.wait_view("stream")
        rows = self.view("stream").locator(".timeline-list li")
        self.assertEqual(rows.count(), 50)  # 50 per page
        self.assertIn("/ 3", self.view("stream").locator(".pagination").inner_text())
        self.view("stream").get_by_role("button", name="下一页").click()
        self.assertEqual(self.view("stream").locator(".timeline-list li").count(), 50)
        self.view("stream").get_by_role("button", name="下一页").click()
        self.assertEqual(self.view("stream").locator(".timeline-list li").count(), 22)
        # Terminal filter: only finish/done/usage remain.
        self.view("stream").get_by_role("button", name="结束相关").click()
        self.view("stream").locator(".event-kind.finish").wait_for()
        kinds = self.view("stream").locator(".event-kind").all_inner_texts()
        self.assertTrue(set(kinds) <= {"finish", "done", "usage"})
        # Problems filter: clean stream has no flagged events.
        self.view("stream").get_by_role("button", name="发现问题").click()
        self.assertEqual(self.view("stream").locator(".timeline-list li").count(), 0)
        self.assertIn("没有事件", self.page.inner_text("body"))

    def test_stream_problems_filter_flags_unsupported_events(self):
        """An unsupported-profile event is honestly shown by the problems
        filter (the old test's 0-expectation for an invalid stream was a
        test bug, not product behavior)."""
        self.page.goto(BASE)
        self.page.locator(".sidebar-nav .nav-item", has_text="流结束检查").click()
        self.view("stream").get_by_role("tab", name="粘贴").click()
        stream = helpers.chunk("OK") + 'data: {"vendor_field": 1}\n\n'
        self.view("stream").locator("textarea").fill(stream)
        self.view("stream").get_by_role("button", name="分析流").click()
        self.wait_view("stream")
        self.assertIn("UNSUPPORTED_PROFILE", self.page.inner_text("body"))
        self.view("stream").get_by_role("button", name="发现问题").click()
        self.assertEqual(self.view("stream").locator(".timeline-list li").count(), 1)

    def test_stream_compare_and_stale(self):
        self.page.goto(BASE)
        self.page.locator(".sidebar-nav .nav-item", has_text="流结束检查").click()
        self.run_stream_case("只有finish，缺[DONE]")
        self.view("stream").get_by_role("button", name="与正常样例对照").click()
        self.view("stream").locator(".compare-wide").wait_for()
        self.assertIn("正常结束", self.view("stream").locator(".compare-wide").inner_text())
        # Editing input marks result stale; re-analysis refreshes it.
        self.view("stream").get_by_role("tab", name="粘贴").click()
        self.view("stream").locator("textarea").fill("data: 1\n\n")
        self.view("stream").locator(".status-banner.stale").wait_for()
        self.view("stream").get_by_role("button", name="分析流").click()
        self.wait_view("stream")
        self.view("stream").locator(".status-banner.loading").wait_for(state="detached")
        self.assertIn("输入无效", self.page.inner_text("body"))

    # ---- privacy canary with real response collection ----
    def test_canary_never_reaches_results_export_or_console(self):
        self.page.goto(BASE)
        self.page.locator(".sidebar-nav .nav-item", has_text="流结束检查").click()
        self.view("stream").get_by_role("tab", name="粘贴").click()
        self.view("stream").locator("textarea").fill(
            'data: {"choices": [{"index": 0, "delta": {"content": "'
            + CANARY
            + '"}}]}\n\n'
        )
        self.view("stream").get_by_role("button", name="分析流").click()
        self.wait_view("stream")
        self.result_panel("stream").get_by_role("button", name="导出预览").click()
        self.result_panel("stream").locator('[data-testid="export-preview"]').wait_for()
        self.assert_no_canary_outside_input()
        self.assertEqual(self.console_errors, [])
        stored = self.page.evaluate("JSON.stringify(localStorage)")
        self.assertNotIn(CANARY, stored)
        downloaded_via_ui = self.result_panel("stream").locator('[data-testid="export-preview"]').inner_text()
        self.assertNotIn(CANARY, downloaded_via_ui)
        # The collected export payload API response also carries no canary.
        export_responses = [
            b for b in self.response_bodies if "evidence" in b or "evidence" in b
        ]
        export_bodies = [b for b in self.response_bodies if "verdict" in b or "outcome" in b]
        for body in export_bodies:
            self.assertNotIn(CANARY, body)

    # ---- language switch ----
    def test_language_switch_reuses_result(self):
        self.page.goto(BASE)
        self.run_stream_case("正常结束：finish stop + [DONE]")
        self.assertIn("正常结束", self.page.inner_text("body"))
        self.page.get_by_role("button", name="English").click()
        self.view("stream").locator(".verdict-banner.normal_termination").wait_for()
        self.assertIn("Normal termination", self.page.inner_text("body"))
        # Language switch re-renders and refreshes the normal reference, but
        # never re-analyzes user input.
        self.assertEqual([u for u in self.api_calls if "/analyze" in u], [])
        self.assertEqual(len([u for u in self.api_calls if "/stream/demo" in u]), 1)
        # Switch module: config empty state is also localized.
        self.page.locator(".sidebar-nav .nav-item", has_text="Config check").click()
        self.assertIn("Start with a sample", self.page.inner_text("body"))
        self.page.get_by_role("button", name="中文").click()
        self.view("config").locator(".empty-state").wait_for()
        self.assertIn("从合成样例开始", self.page.inner_text("body"))

    # ---- R04: second tab must not break the first ----
    def test_second_tab_shares_session_without_breaking_first(self):
        self.page.goto(BASE)
        self.run_config_case("带env_vars的http服务残留提示")
        self.view("config").get_by_role("button", name="server-1").click()
        self.view("config").locator(".service-body").wait_for()
        self.assertIn("POSSIBLE_TRANSPORT_RESIDUE", self.page.inner_text("body"))

        second = self.context.new_page()
        second.goto(BASE)
        second.locator(".sidebar-nav .nav-item", has_text="流结束检查").click()
        second.get_by_role("button", name="只有finish，缺[DONE]").first.click()
        second.wait_for_selector('.stream-module [data-testid="result-view"]')

        # Back to the first tab: run another analysis; with session reuse
        # this must succeed, not fail with a network/CSRF error.
        self.page.locator(".sidebar-nav .nav-item", has_text="流结束检查").click()
        self.view("stream").get_by_role("button", name="只有finish，缺[DONE]").first.click()
        self.wait_view("stream")
        self.assertIn("FINISH_WITHOUT_DONE", self.page.inner_text("body"))
        # language switch on the old tab also still works
        self.page.get_by_role("button", name="English").click()
        self.view("stream").locator(".verdict-banner.needs_review").wait_for()
        self.assertIn("Needs review", self.page.inner_text("body"))
        second.close()

    # ---- narrow layout (R06) ----
    def test_narrow_layout_390_expanded_no_overflow(self):
        context = self.browser.new_context(viewport={"width": 390, "height": 844})
        page = context.new_page()
        page.goto(BASE)
        page.get_by_role("tab", name="配置检查").click()
        page.get_by_role("button", name="带env_vars的http服务残留提示").first.click()
        page.wait_for_selector('.config-module [data-testid="result-view"]')
        # Expand the worst-case service detail; document must not overflow.
        page.get_by_role("button", name="server-1").click()
        page.wait_for_selector(".config-module .service-body")
        overflow = page.evaluate(
            "document.documentElement.scrollWidth - document.documentElement.clientWidth"
        )
        self.assertLessEqual(overflow, 1, "expanded config detail overflows at 390px")
        # Export open as well.
        page.locator(".config-module .result-pane .share-row select").select_option("md")
        page.locator(".config-module .result-pane .share-row").get_by_role("button", name="导出预览").click()
        page.locator(".config-module [data-testid='export-preview']").wait_for()
        overflow = page.evaluate(
            "document.documentElement.scrollWidth - document.documentElement.clientWidth"
        )
        self.assertLessEqual(overflow, 1, "export open overflows at 390px")
        # Input/result switch works.
        page.locator(".config-module .view-switch").get_by_role("button", name="输入", exact=True).click()
        page.wait_for_selector(".config-module .example-list")
        page.locator(".config-module .view-switch").get_by_role("button", name="结果", exact=True).click()
        page.wait_for_selector('.config-module [data-testid="result-view"]')

        # English + stream module expanded details too.
        page.get_by_role("button", name="English").click()
        page.wait_for_selector(".config-module .result-error, .config-module .outcome-banner")
        overflow = page.evaluate(
            "document.documentElement.scrollWidth - document.documentElement.clientWidth"
        )
        self.assertLessEqual(overflow, 1)

        page.get_by_role("tab", name="Stream end check").click()
        page.get_by_role("button", name="finish without [DONE]").first.click()
        page.wait_for_selector('.stream-module [data-testid="result-view"]')
        page.get_by_role("button", name="End-related").click()
        page.locator(".stream-module .timeline-row").first.click()
        page.wait_for_selector(".stream-module .event-detail")
        overflow = page.evaluate(
            "document.documentElement.scrollWidth - document.documentElement.clientWidth"
        )
        self.assertLessEqual(overflow, 1, "stream event detail overflows at 390px")
        context.close()

    # ---- contrast ----
    def test_contrast_ratios(self):
        self.page.goto(BASE)
        self.run_config_case("带env_vars的http服务残留提示")
        self.view("config").get_by_role("button", name="server-1").click()
        self.view("config").locator(".service-body").wait_for()
        samples = self.page.evaluate(
            """() => {
              function luminance(rgb) {
                const [r, g, b] = rgb.match(/\\d+/g).map(Number).map(v => {
                  v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
                });
                return 0.2126 * r + 0.7152 * g + 0.0722 * b;
              }
              function ratio(fg, bg) {
                const l1 = luminance(fg), l2 = luminance(bg);
                return (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
              }
              const results = [];
              for (const selector of ['.product-name', '.local-note', '.scope-note', '.finding-text']) {
                const el = document.querySelector(selector);
                if (!el) continue;
                const style = getComputedStyle(el);
                let bg = 'rgb(255, 255, 255)';
                let node = el;
                while (node) {
                  const c = getComputedStyle(node).backgroundColor;
                  if (c && c !== 'rgba(0, 0, 0, 0)') { bg = c; break; }
                  node = node.parentElement;
                }
                results.push([selector, ratio(style.color, bg)]);
              }
              return results;
            }"""
        )
        checked = dict(samples)
        self.assertTrue(checked)
        for selector, value in checked.items():
            self.assertGreaterEqual(value, 4.5, f"{selector} contrast {value:.2f}")

    # ---- oversized paste error state ----
    def test_error_state_oversized_stream_paste(self):
        self.page.goto(BASE)
        self.page.locator(".sidebar-nav .nav-item", has_text="流结束检查").click()
        self.view("stream").get_by_role("tab", name="粘贴").click()
        self.view("stream").locator("textarea").fill("x" * (9 * 1024 * 1024 // 1))
        self.view("stream").get_by_role("button", name="分析流").click()
        self.view("stream").locator(".status-banner.error").wait_for()
        self.assertIn("8MiB", self.view("stream").locator(".status-banner.error").inner_text())

    # ---- combined export ----
    def test_combined_export_flow(self):
        self.page.goto(BASE)
        self.run_config_case("带env_vars的http服务残留提示")
        self.run_stream_case("只有finish，缺[DONE]")
        self.page.locator(".stream-module .advanced-combined summary").click()
        combined = self.page.locator(".stream-module .combined-box")
        combined.get_by_role("checkbox").first.check()
        combined.get_by_role("checkbox").nth(1).check()
        combined.get_by_role("button", name="导出预览").click()
        combined.locator('[data-testid="combined-export-preview"]').wait_for()
        preview = combined.locator('[data-testid="combined-export-preview"]').inner_text()
        self.assertIn("Agent 证据集", preview)
        self.assertIn("流结束证据卡", preview)
        self.assertIn("Agent 配置证据卡", preview)
        self.assert_no_canary_outside_input(helpers.CANARY_KEY)
        with self.page.expect_download() as download_info:
            combined.get_by_role("button", name="下载").click()
        saved = Path(download_info.value.path()).read_text(encoding="utf-8")
        self.assertEqual(saved, preview)

    # ---- showcase ----
    def test_showcase_static_journey(self):
        requests: list[str] = []
        self.page.on("request", lambda req: requests.append(req.url))
        self.page.goto(SHOWCASE_BASE)
        body = self.page.inner_text("body")
        self.assertIn("样例展示", body)
        self.assertIn("本地版", body)
        self.assertTrue(self.page.get_by_role("tab", name="文件").first.is_disabled())
        self.assertTrue(self.page.get_by_role("tab", name="粘贴").first.is_disabled())
        # Stream module sample: switch samples and check they differ.
        self.page.locator(".sidebar-nav .nav-item", has_text="流结束检查").click()
        self.page.get_by_role("button", name="只有finish，缺[DONE]").first.click()
        self.page.wait_for_selector('.stream-module [data-testid="result-view"]')
        self.assertIn("FINISH_WITHOUT_DONE", self.page.inner_text("body"))
        self.page.get_by_role("button", name="内容流被截断").first.click()
        self.wait_view("stream")
        self.assertIn("NO_TERMINAL_EVIDENCE", self.page.inner_text("body"))
        self.page.get_by_role("button", name="正常结束").first.click()
        self.wait_view("stream")
        self.assertIn("正常结束", self.page.inner_text("body"))
        # Language switch.
        self.page.get_by_role("button", name="English").click()
        self.page.wait_for_selector(".stream-module .showcase-banner:visible")
        self.assertIn("Sample showcase", self.page.inner_text("body"))
        # Export.
        self.result_panel("stream").locator(".share-row select").select_option("md")
        self.result_panel("stream").get_by_role(
            "button", name=re.compile("导出预览|Export preview")
        ).click()
        self.result_panel("stream").locator('[data-testid="export-preview"]').wait_for()
        self.assertIn(
            "Stream End Evidence Card",
            self.result_panel("stream").locator('[data-testid="export-preview"]').inner_text(),
        )
        self.assertEqual([u for u in requests if "/api/" in u], [])
        self.assertEqual([u for u in requests if not u.startswith(SHOWCASE_BASE)], [])

    # ---- screenshots (small, key states) ----
    def test_z10_screenshots(self):
        shots = ARTIFACTS
        self.page.goto(BASE)
        self.run_config_case("带env_vars的http服务残留提示")
        self.view("config").get_by_role("button", name="server-1").click()
        self.view("config").locator(".service-body").wait_for()
        self.page.screenshot(path=str(shots / "desktop-zh-config-residue.png"), full_page=True)

        self.run_stream_case("只有finish，缺[DONE]")
        self.view("stream").get_by_role("button", name="与正常样例对照").click()
        self.view("stream").locator(".compare-wide").wait_for()
        self.page.screenshot(path=str(shots / "desktop-zh-stream-compare.png"), full_page=True)

        self.page.get_by_role("button", name="English").click()
        self.view("stream").locator(".verdict-banner.needs_review").wait_for()
        self.page.screenshot(path=str(shots / "desktop-en-stream.png"), full_page=True)

        context = self.browser.new_context(viewport={"width": 390, "height": 844})
        narrow = context.new_page()
        narrow.goto(BASE)
        narrow.get_by_role("tab", name="配置检查").click()
        narrow.get_by_role("button", name="带env_vars的http服务残留提示").first.click()
        narrow.wait_for_selector('.config-module [data-testid="result-view"]')
        narrow.get_by_role("button", name="server-1").click()
        narrow.wait_for_selector(".config-module .service-body")
        narrow.screenshot(path=str(shots / "narrow-390-config-expanded.png"), full_page=True)
        context.close()


if __name__ == "__main__":
    unittest.main()
