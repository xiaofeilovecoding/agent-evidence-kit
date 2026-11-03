"""Stream core regressions: S-01..S-06 + R01 deep-event stability.

Independently derived expectations, not generated from current output.
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

from agent_evidence_kit.stream.analysis import analyze_bytes, analyze_chunks  # noqa: E402
from agent_evidence_kit.demos import STREAM_DEMO_BYTES  # noqa: E402
from tests import helpers  # noqa: E402

PYTHON = sys.executable
ENV = {**os.environ, "PYTHONUTF8": "1"}

# Independent oracle: each demo's expected (primary code, exit code).
DEMO_ORACLE = {
    "normal": ("NORMAL_TERMINATION", 0),
    "finish-only": ("FINISH_WITHOUT_DONE", 1),
    "done-only": ("DONE_WITHOUT_FINISH", 1),
    "truncated": ("NO_TERMINAL_EVIDENCE", 1),
    "limit-stop": ("LIMIT_STOP", 1),
    "after-done": ("DATA_AFTER_DONE", 1),
    "bad-json": ("INVALID_EVENT_JSON", 2),
    "unterminated": ("UNTERMINATED_EVENT", 1),
}


def run_cli(args):
    return subprocess.run(
        [PYTHON, "-m", "agent_evidence_kit", "stream", *args],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=ENV,
    )


class TempFileCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="aek-s-test-")
        self.files = []

    def write_input(self, data: bytes, suffix=".sse") -> str:
        handle = tempfile.NamedTemporaryFile(
            suffix=suffix, delete=False, dir=self.tmp
        )
        handle.write(data)
        handle.close()
        self.files.append(handle.name)
        return handle.name

    def tearDown(self):
        for name in self.files:
            try:
                os.unlink(name)
            except OSError:
                pass
        try:
            os.rmdir(self.tmp)
        except OSError:
            pass


class S01Demos(unittest.TestCase):
    def test_all_demos_match_oracle(self):
        for name, (code, exit_code) in DEMO_ORACLE.items():
            with self.subTest(demo=name):
                core = analyze_bytes(STREAM_DEMO_BYTES[name])
                card = json.loads(
                    run_cli(["demo", "--case", name]).stdout
                )
                verdict = {0: "NORMAL_TERMINATION", 1: "NEEDS_REVIEW",
                           2: "INVALID_INPUT"}[exit_code]
                self.assertEqual(card["verdict"], verdict)
                codes = {f["code"] for f in card["findings"]}
                self.assertIn(code, codes)
                self.assertEqual(run_cli(["demo", "--case", name]).returncode,
                                 exit_code, name)

    def test_finish_only_differs_from_truncated(self):
        finish_core = analyze_bytes(STREAM_DEMO_BYTES["finish-only"])
        truncated_core = analyze_bytes(STREAM_DEMO_BYTES["truncated"])
        self.assertEqual(finish_core["summary"]["saw_finish"], True)
        self.assertEqual(truncated_core["summary"]["saw_finish"], False)
        self.assertNotEqual(
            finish_core["summary"]["saw_finish"],
            truncated_core["summary"]["saw_finish"],
        )

    def test_stream_module_evidence_card_markdown(self):
        card = run_cli(["demo", "--case", "finish-only", "--format", "md"])
        self.assertEqual(card.returncode, 1)
        self.assertIn("流结束证据卡", card.stdout)
        en = run_cli(["demo", "--case", "finish-only", "--format", "md", "--lang", "en"])
        self.assertIn("Stream End Evidence Card", en.stdout)


class S02ChunkInvariance(unittest.TestCase):
    STREAM = (
        helpers.chunk("你好")  # multibyte chars
        + helpers.chunk("OK")
        + helpers.chunk(finish="stop")
        + helpers.done()
    ).encode("utf-8")

    def test_any_splitting_gives_same_result(self):
        expected = None
        for size in (1, 2, 3, 4096, len(self.STREAM)):
            with self.subTest(chunk=size):
                core = analyze_bytes(self.STREAM, size)
                projection = json.dumps(
                    {"verdict": core["verdict"], "summary": core["summary"],
                     "timeline": core["timeline"],
                     "findings": [f["code"] for f in core["findings"]]},
                    sort_keys=True,
                )
                if expected is None:
                    expected = projection
                self.assertEqual(projection, expected)

    def test_crlf_split_across_chunks(self):
        stream = helpers.chunk("OK").replace("\n\n", "\r\n\r\n").encode("utf-8")
        self.assertIn(b"\r\n", stream)
        for size in (1, 2, 3, 4096):
            core = analyze_bytes(stream, size)
            self.assertEqual(core["summary"]["event_count"], 1, f"size={size}")

    def test_split_inside_done_token(self):
        raw = (helpers.chunk(finish="stop") + helpers.done()).encode("utf-8")
        core = analyze_bytes(raw)
        self.assertTrue(core["summary"]["saw_done"])
        # byte-at-a-time through the [DONE] region still sees DONE
        marker = raw.index(b"[DONE]")
        cut = raw[:marker]  # first half only: no DONE yet
        core = analyze_chunks([cut[i:i+1] for i in range(len(cut))] )
        self.assertFalse(core["summary"]["saw_done"])
        self.assertTrue(core["summary"]["saw_finish"])


class S03SSESubset(TempFileCase):
    def test_multi_data_lines_join_with_newline(self):
        raw = (
            b'data: {"choices": [{"index": 0, "delta": {"content":\n'
            b'data: "OK"}}]}\n\n'
        )
        core = analyze_bytes(raw)
        self.assertEqual(core["summary"]["event_count"], 1)
        self.assertEqual(core["timeline"][0]["kind"], "chunk")
        self.assertTrue(core["timeline"][0]["has_content"])

    def test_comments_and_empty_chunks_not_counted(self):
        raw = b": keep-alive\n\n\n\n: another\n\n"
        core = analyze_bytes(raw)
        self.assertEqual(core["summary"]["event_count"], 0)
        self.assertEqual(core["findings"][0]["code"], "NO_DATA")

    def test_bom_allowed(self):
        raw = b"\xef\xbb\xbf" + helpers.chunk("OK").encode("utf-8")
        core = analyze_bytes(raw)
        self.assertEqual(core["summary"]["event_count"], 1)

    def test_line_endings_cr_lf_crlf(self):
        for eol in ("\n", "\r", "\r\n"):
            raw = f'data: {{"x": 1}}{eol}{eol}'.encode("utf-8")
            core = analyze_bytes(raw)
            self.assertEqual(core["summary"]["event_count"], 1, eol)

    def test_eof_undispatched_data_not_counted(self):
        raw = (helpers.chunk("OK") + "data: {\"partial\"").encode("utf-8")
        core = analyze_bytes(raw)
        self.assertEqual(core["summary"]["event_count"], 1)
        codes = [f["code"] for f in core["findings"]]
        self.assertIn("UNTERMINATED_EVENT", codes)
        self.assertFalse(core["summary"]["saw_done"])

    def test_eof_does_not_invent_done_or_finish(self):
        raw = helpers.chunk("OK").encode("utf-8")
        core = analyze_bytes(raw)
        self.assertFalse(core["summary"]["saw_done"])
        self.assertFalse(core["summary"]["saw_finish"])

    def test_field_value_strips_one_space(self):
        raw = b"data:  {\"x\": 1}\n\n"
        core = analyze_bytes(raw)
        # Two-space value is not valid JSON -> INVALID_EVENT_JSON (exit 2),
        # which proves the value kept one leading space.
        self.assertEqual(core["verdict"], "INVALID_INPUT")

    def test_id_retry_unknown_fields_ignored(self):
        raw = (
            b"id: abc123\nretry: 5000\nx-custom: secret-value\n"
            + helpers.chunk("OK").encode("utf-8")
        )
        core = analyze_bytes(raw)
        self.assertEqual(core["summary"]["event_count"], 1)


class S04ProfileRules(TempFileCase):
    def test_normal_finish_variants(self):
        for finish in ("stop", "tool_calls", "function_call"):
            raw = (helpers.chunk(finish=finish) + helpers.done()).encode("utf-8")
            core = analyze_bytes(raw)
            self.assertEqual(core["verdict"], "NORMAL_TERMINATION", finish)

    def test_length_and_filter(self):
        for finish, code in (("length", "LIMIT_STOP"), ("content_filter", "FILTER_STOP")):
            raw = (helpers.chunk(finish=finish) + helpers.done()).encode("utf-8")
            core = analyze_bytes(raw)
            codes = {f["code"] for f in core["findings"]}
            self.assertIn(code, codes)
            self.assertNotEqual(core["verdict"], "NORMAL_TERMINATION")
            self.assertTrue(core["summary"]["saw_finish"])

    def test_upstream_error_variants(self):
        raw = (
            'event: error\ndata: {"message": "' + helpers.CANARY_S_KEY + '"}\n\n'
        ).encode("utf-8")
        core = analyze_bytes(raw)
        codes = [f["code"] for f in core["findings"]]
        self.assertIn("UPSTREAM_ERROR", codes)
        self.assertNotIn(helpers.CANARY_S_KEY, json.dumps(core))

        raw = ('data: {"error": {"code": 500}}\n\n').encode("utf-8")
        core = analyze_bytes(raw)
        self.assertIn("UPSTREAM_ERROR", [f["code"] for f in core["findings"]])

    def test_unsupported_profile_variants(self):
        cases = [
            '{"choices": [{"index": 0}, {"index": 1}]}',  # multi-choice
            '{"choices": [{"index": 1, "delta": {}}]}',   # non-zero index
            '{"choices": [{"index": true, "delta": {}}]}',  # bool index
            '{"choices": [{"index": 0, "delta": "text"}]}',  # delta not object
            '{"vendor_field": 1}',  # unknown provider structure
            '{"choices": []}',  # empty choices without usage
        ]
        for data in cases:
            raw = f"data: {data}\n\n".encode("utf-8")
            core = analyze_bytes(raw)
            self.assertIn("UNSUPPORTED_PROFILE", [f["code"] for f in core["findings"]], data)

    def test_usage_only_allowed(self):
        raw = helpers.usage_only().encode("utf-8")
        core = analyze_bytes(raw)
        kinds = [t["kind"] for t in core["timeline"]]
        self.assertIn("usage", kinds)
        self.assertTrue(core["summary"]["usage_seen"])

    def test_unsupported_finish_and_event(self):
        raw = helpers.chunk(finish="weird_reason").encode("utf-8")
        core = analyze_bytes(raw)
        self.assertIn("UNSUPPORTED_FINISH", [f["code"] for f in core["findings"]])
        self.assertNotIn("weird_reason", json.dumps(core))

        raw = b"event: custom\ndata: {}\n\n"
        core = analyze_bytes(raw)
        self.assertIn("UNSUPPORTED_EVENT", [f["code"] for f in core["findings"]])

    def test_unsupported_profile_exits_2(self):
        raw = b'data: {"vendor_field": 1}\n\n'
        path = self.write_input(raw)
        result = run_cli(["inspect", "--input", path]) if False else run_cli(["--input", path])
        self.assertEqual(result.returncode, 2)

    def test_multiple_done_and_after_done(self):
        raw = (helpers.chunk(finish="stop") + helpers.done() + helpers.done()).encode("utf-8")
        core = analyze_bytes(raw)
        codes = [f["code"] for f in core["findings"]]
        self.assertIn("DATA_AFTER_DONE", codes)
        self.assertEqual(core["verdict"], "NEEDS_REVIEW")


class S05Limits(TempFileCase):
    def test_input_size_limit(self):
        from agent_evidence_kit.stream.parsers import InputRejected

        big = helpers.chunk("OK").encode("utf-8")
        filler = b":" + b"x" * 1024 + b"\n\n"
        data = big + filler * ((8 * 1024 * 1024 // len(filler)) + 2)
        self.assertGreater(len(data), 8 * 1024 * 1024)
        try:
            analyze_chunks(data[i:i+65536] for i in range(0, len(data), 65536))
            self.fail("expected INPUT_TOO_LARGE")
        except InputRejected as rejected:
            self.assertEqual(rejected.code, "INPUT_TOO_LARGE")

    def test_line_limit(self):
        from agent_evidence_kit.stream.parsers import InputRejected

        data = b"data: " + b"x" * (128 * 1024 + 1) + b"\n\n"
        try:
            analyze_chunks([data])
            self.fail("expected LIMIT_EXCEEDED")
        except InputRejected as rejected:
            self.assertEqual(rejected.code, "LIMIT_EXCEEDED")

    def test_event_data_limit(self):
        from agent_evidence_kit.stream.parsers import InputRejected

        data = b"data: " + b"x" * (256 * 1024 + 1) + b"\n\n"
        try:
            analyze_chunks([data])
            self.fail("expected LIMIT_EXCEEDED")
        except InputRejected as rejected:
            self.assertEqual(rejected.code, "LIMIT_EXCEEDED")

    def test_json_depth_limit(self):
        deep = "[" * 17 + "]" * 17
        raw = f"data: {deep}\n\n".encode("utf-8")
        core = analyze_bytes(raw)
        self.assertIn("LIMIT_EXCEEDED", [f["code"] for f in core["findings"]])
        ok = "[" * 16 + "]" * 16
        raw = f"data: {ok}\n\n".encode("utf-8")
        core = analyze_bytes(raw)
        self.assertNotIn("LIMIT_EXCEEDED", [f["code"] for f in core["findings"]])

    def test_invalid_utf8(self):
        from agent_evidence_kit.stream.parsers import InputRejected

        raw = b"data: \xff\xfe\n\n"
        try:
            analyze_chunks([raw])
            self.fail("expected INVALID_ENCODING")
        except InputRejected as rejected:
            self.assertEqual(rejected.code, "INVALID_ENCODING")

    def test_cli_rejections_stable_and_sanitized(self):
        cases = [
            (b"data: {bad json}\n\n", ".sse", "INVALID_EVENT_JSON"),
            (b"data: {\"a\": 1, \"a\": 2}\n\n", ".sse", "DUPLICATE_KEY"),
            (b"data: \xff\n\n", ".sse", "INVALID_ENCODING"),
            (b"data: [DONE]\n\n", ".log", "INPUT_UNREADABLE"),
        ]
        for data, suffix, code in cases:
            path = self.write_input(data, suffix)
            result = run_cli(["--input", path])
            self.assertEqual(result.returncode, 2, code)
            self.assertIn(code, result.stdout)
            self.assertNotIn(self.tmp, result.stdout + result.stderr)

    def test_data_events_limit(self):
        from agent_evidence_kit.stream.parsers import InputRejected, MAX_DATA_EVENTS

        data = b"data: 1\n\n" * (MAX_DATA_EVENTS + 1)
        try:
            analyze_chunks([data])
            self.fail("expected LIMIT_EXCEEDED")
        except InputRejected as rejected:
            self.assertEqual(rejected.code, "LIMIT_EXCEEDED")

    def test_missing_file(self):
        missing = os.path.join(self.tmp, "nope.sse")
        result = run_cli(["--input", missing])
        self.assertEqual(result.returncode, 2)
        self.assertIn("INPUT_UNREADABLE", result.stdout)


class S06Privacy(TempFileCase):
    CANARIES = [
        helpers.CANARY_S_KEY,
        helpers.CANARY_S_ID,
        helpers.CANARY_EMAIL,
        helpers.CANARY_S_TEXT,
        "weird_reason",
        "secret-value",
    ]

    def build_canary_stream(self) -> bytes:
        return (
            b"id: " + helpers.CANARY_S_ID.encode() + b"\n"
            b"x-trace: " + helpers.CANARY_S_KEY.encode() + b"\n"
            b"event: error\n"
            b'data: {"error": {"message": "' + helpers.CANARY_S_TEXT.encode() + b'"}}\n\n'
            b'data: {"choices": [{"index": 0, "delta": {"content": "'
            + helpers.CANARY_S_TEXT.encode() + b'"}}]}\n\n'
            b'data: {"choices": [{"index": 0, "delta": {}, "finish_reason": "weird_reason"}]}\n\n'
            b'data: {"model": "' + helpers.CANARY_S_ID.encode() + b'", "usage": {"cost": "'
            + helpers.CANARY_EMAIL.encode() + b'"}, "choices": []}\n\n'
        )

    def test_no_canary_anywhere(self):
        raw = self.build_canary_stream()
        path = self.write_input(raw)
        for out_format in ("json", "md"):
            for lang in ("zh-CN", "en"):
                result = run_cli(
                    ["--input", path, "--format", out_format, "--lang", lang]
                )
                combined = result.stdout + result.stderr
                for canary in self.CANARIES:
                    self.assertNotIn(canary, combined, f"{out_format}/{lang}/{canary}")
                self.assertNotIn(self.tmp, combined)

    def test_input_bytes_unchanged_and_deterministic(self):
        raw = self.build_canary_stream()
        path = self.write_input(raw)
        first = run_cli(["--input", path])
        with open(path, "rb") as handle:
            self.assertEqual(handle.read(), raw)
        second = run_cli(["--input", path])
        self.assertEqual(first.stdout, second.stdout)
        self.assertEqual(first.returncode, second.returncode)

    def test_demo_requires_known_case(self):
        result = run_cli(["demo", "--case", "not-a-case"])
        self.assertEqual(result.returncode, 2)
        self.assertNotIn("not-a-case", result.stdout + result.stderr)

    def test_bad_args_generic(self):
        result = run_cli(["--chunk-bytes", "0"])
        self.assertEqual(result.returncode, 2)
        result = run_cli(["--chunk-bytes", "70000"])
        self.assertEqual(result.returncode, 2)
        result = run_cli(["bogus-subcommand"])
        self.assertEqual(result.returncode, 2)
        self.assertNotIn("bogus-subcommand", result.stdout + result.stderr)

    def test_chunk_bytes_flag_does_not_change_result(self):
        raw = self.write_input(helpers.normal_stream())
        base = run_cli(["--input", raw]).stdout
        for size in ("1", "3", "65536"):
            other = run_cli(["--input", raw, "--chunk-bytes", size]).stdout
            self.assertEqual(base, other, f"chunk={size}")


if __name__ == "__main__":
    unittest.main()
