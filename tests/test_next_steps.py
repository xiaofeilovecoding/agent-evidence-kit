"""F01 regression: versioned bilingual next-step guidance.

Independent expectations: every finding code either core can emit has a
complete four-part entry in both languages; the generic fallback never
echoes unknown codes; cards carry additive next_steps fields; Markdown
exports contain the guidance; determinism and canary discipline hold.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from agent_evidence_kit import next_steps as ns  # noqa: E402
from agent_evidence_kit.config.analysis import analyze_bytes as cfg_analyze  # noqa: E402
from agent_evidence_kit.config.diagnostics import SEVERITY as CONFIG_CODES  # noqa: E402
from agent_evidence_kit.config.parsers import InputRejected  # noqa: E402
from agent_evidence_kit.config.renderers import render_card as cfg_render  # noqa: E402
from agent_evidence_kit.stream.analysis import analyze_bytes as stream_analyze  # noqa: E402
from agent_evidence_kit.stream.diagnostics import SEVERITY as STREAM_CODES  # noqa: E402
from agent_evidence_kit.stream.renderers import render_card as stream_render  # noqa: E402
from tests import helpers  # noqa: E402

ENV = {**os.environ, "PYTHONUTF8": "1"}


class F01SuggestionCoverage(unittest.TestCase):
    REQUIRED_KEYS = ("observed", "meaning", "next_steps", "does_not_prove")

    def test_every_config_code_covered_bilingually(self):
        for code in CONFIG_CODES:
            for language in ("zh-CN", "en"):
                with self.subTest(code=code, lang=language):
                    entry = ns.next_steps_for(code, language)
                    self.assertIsNotNone(entry)
                    for key in self.REQUIRED_KEYS:
                        self.assertTrue(entry[key].strip(), f"{code}/{language}/{key}")

    def test_every_stream_code_covered_bilingually(self):
        for code in STREAM_CODES:
            for language in ("zh-CN", "en"):
                with self.subTest(code=code, lang=language):
                    entry = ns.next_steps_for(code, language)
                    self.assertIsNotNone(entry)
                    for key in self.REQUIRED_KEYS:
                        self.assertTrue(entry[key].strip(), f"{code}/{language}/{key}")

    def test_unknown_code_safe_fallback_no_echo(self):
        weird = "TOTALLY_UNKNOWN_CODE_99"
        entry = ns.next_steps_for(weird, "en")
        self.assertEqual(entry["next_steps"],
                         ns.NEXT_STEPS and ns._GENERIC["next_steps"]["en"])
        blob = json.dumps(entry, ensure_ascii=False)
        self.assertNotIn(weird, blob)

    def test_no_suggestion_contains_forbidden_claim_words(self):
        # Suggestions are fixed knowledge: no root-cause verdicts, no
        # verified-compatibility/auth claims, no one-click fixes.
        forbidden = [
            "根因是", "一键修复", "已验证兼容", "已验证认证", "自动修复",
            "root cause is", "one-click fix", "verified compatible",
            "verified auth", "auto-fix",
        ]
        blob = json.dumps(ns.NEXT_STEPS, ensure_ascii=False)
        for word in forbidden:
            self.assertNotIn(word, blob)

    def test_schema_version_exported(self):
        self.assertEqual(ns.NEXT_STEPS_SCHEMA_VERSION, 1)


class F01RendererIntegration(unittest.TestCase):
    def _with_tmp(self, data: bytes, suffix: str):
        handle = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
        handle.write(data)
        handle.close()
        return handle.name

    def test_config_json_card_has_next_steps_additive(self):
        raw = helpers.residue_config().encode("utf-8")
        card = cfg_render(cfg_analyze(raw, "json"), "en", "json")
        self.assertIn("next_steps_schema_version", card)
        for service in card["services"]:
            for finding in service["findings"]:
                entry = finding["next_steps"]
                for key in ("observed", "meaning", "next_steps", "does_not_prove"):
                    self.assertIn(key, entry)
        # Additive: the old required keys are all still present.
        self.assertIn("schema_version", card)
        self.assertIn("scope", card)
        self.assertIn("outcome", card)

    def test_config_not_validated_gets_structure_state(self):
        card = cfg_render(cfg_analyze(b'{"mcp_servers": {}}', "json"), "zh-CN", "json")
        self.assertEqual(card["outcome"], "not_validated")
        self.assertIsNotNone(card["next_steps"])
        self.assertIn("结构", card["next_steps"]["observed"])

    def test_config_error_card_has_guidance(self):
        from agent_evidence_kit.config.parsers import InputRejected

        core = {"error": "INPUT_TOO_LARGE"}
        card = cfg_render(core, "en", "json")
        self.assertIsNotNone(card["error"]["next_steps"])
        self.assertIsNotNone(card["next_steps"])

    def test_stream_json_card_findings_have_guidance(self):
        card = stream_render(stream_analyze(helpers.normal_stream()), "zh-CN", "json")
        self.assertTrue(card["findings"])
        for finding in card["findings"]:
            self.assertIn("next_steps", finding)
        self.assertIsNotNone(card["next_steps"])

    def test_markdown_export_contains_next_step_lines(self):
        raw = helpers.residue_config().encode("utf-8")
        md = cfg_render(cfg_analyze(raw, "json"), "zh-CN", "md")
        self.assertIn("下一步:", md)
        self.assertIn("不能证明:", md)
        en = stream_render(stream_analyze(helpers.normal_stream()), "en", "md")
        self.assertIn("Next step:", en)
        self.assertIn("Does not prove:", en)

    def test_markdown_export_is_deterministic(self):
        raw = helpers.residue_config().encode("utf-8")
        first = cfg_render(cfg_analyze(raw, "json"), "zh-CN", "md")
        second = cfg_render(cfg_analyze(raw, "json"), "zh-CN", "md")
        self.assertEqual(first, second)

    def test_cli_md_export_carries_guidance(self):
        path = self._with_tmp(helpers.residue_config().encode(), ".json")
        try:
            result = subprocess.run(
                [sys.executable, "-m", "agent_evidence_kit", "config",
                 "--input", path, "--format", "md", "--lang", "zh-CN"],
                cwd=PROJECT_ROOT, capture_output=True, text=True,
                encoding="utf-8", env=ENV,
            )
            self.assertIn("下一步:", result.stdout)
        finally:
            os.unlink(path)

    def test_guidance_never_contains_canary(self):
        canaries = [helpers.CANARY_KEY, helpers.CANARY_URL, helpers.CANARY_TOKEN]
        blob = json.dumps(ns.NEXT_STEPS, ensure_ascii=False) + json.dumps(
            ns.STATE_NEXT_STEPS, ensure_ascii=False
        )
        for canary in canaries:
            self.assertNotIn(canary, blob)


if __name__ == "__main__":
    unittest.main()
