"""C01 regression: SSE line-ending invariance (CR / LF / CRLF).

Independently derived expectations: each of CR, LF, CRLF is exactly one
line break; a CRLF split across chunks counts once; EOF without a true
blank line must not fabricate a dispatch.
"""
from __future__ import annotations

import json
import unittest
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from agent_evidence_kit.stream.analysis import analyze_bytes  # noqa: E402

# Multi-data-line finish event followed by [DONE] (LF spelling here).
MULTI_LF = (
    'data: {"choices":\n'
    'data: [{"index":0,"delta":{},"finish_reason":"stop"}]}\n'
    "\n"
    "data: [DONE]\n\n"
)


class C01LineEndingInvariance(unittest.TestCase):
    def test_three_line_endings_same_result(self):
        expected = None
        for name, eol in (("LF", "\n"), ("CRLF", "\r\n"), ("CR", "\r")):
            with self.subTest(eol=name):
                core = analyze_bytes(MULTI_LF.replace("\n", eol).encode("utf-8"))
                self.assertEqual(core["verdict"], "NORMAL_TERMINATION", name)
                self.assertEqual(core["summary"]["event_count"], 2, name)
                self.assertTrue(core["summary"]["saw_done"], name)
                self.assertTrue(core["summary"]["saw_finish"], name)
                projection = json.dumps(
                    {"verdict": core["verdict"], "summary": core["summary"],
                     "timeline": core["timeline"],
                     "findings": [f["code"] for f in core["findings"]]},
                    sort_keys=True,
                )
                if expected is None:
                    expected = projection
                self.assertEqual(projection, expected)

    def test_crlf_split_across_single_byte_chunks(self):
        raw = MULTI_LF.replace("\n", "\r\n").encode("utf-8")
        for size in (1, 2, 3):
            with self.subTest(chunk=size):
                core = analyze_bytes(raw, size)
                self.assertEqual(core["verdict"], "NORMAL_TERMINATION", f"size={size}")
                self.assertEqual(core["summary"]["event_count"], 2)

    def test_single_trailing_newline_does_not_dispatch(self):
        for name, eol in (("LF", "\n"), ("CRLF", "\r\n"), ("CR", "\r")):
            with self.subTest(eol=name):
                raw = (
                    'data: {"choices":\n'
                    'data: [{"index":0,"delta":{},"finish_reason":"stop"}]}\n'
                ).replace("\n", eol).encode("utf-8")
                core = analyze_bytes(raw)
                codes = [f["code"] for f in core["findings"]]
                self.assertIn("UNTERMINATED_EVENT", codes, name)
                self.assertEqual(core["summary"]["event_count"], 0, name)
                self.assertFalse(core["summary"]["saw_done"], name)
                self.assertFalse(core["summary"]["saw_finish"], name)

    def test_blank_line_only_dispatches_once(self):
        for name, eol in (("LF", "\n"), ("CRLF", "\r\n"), ("CR", "\r")):
            with self.subTest(eol=name):
                raw = ("data: [DONE]" + eol + eol).encode("utf-8")
                core = analyze_bytes(raw)
                self.assertEqual(core["summary"]["event_count"], 1, name)
                self.assertTrue(core["summary"]["saw_done"], name)
                self.assertFalse(core["summary"]["saw_finish"], name)

    def test_cr_at_eof_completes_nothing_extra(self):
        raw = (
            'data: {"choices":\n'
            'data: [{"index":0,"delta":{},"finish_reason":"stop"}]}\n'
        ).replace("\n", "\r").encode("utf-8")
        core = analyze_bytes(raw)
        self.assertEqual(core["summary"]["event_count"], 0)
        self.assertIn("UNTERMINATED_EVENT", [f["code"] for f in core["findings"]])
        self.assertFalse(core["summary"]["saw_done"])


if __name__ == "__main__":
    unittest.main()
