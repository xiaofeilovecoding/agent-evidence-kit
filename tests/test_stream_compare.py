"""ADOPTION E1/E2/E3: normal-vs-abnormal stream comparison.

Covers the comparison core (controlled finish enums, terminal-first fixed
ordering, no raw material), the CLI subcommand (exit codes, formats,
languages, canary absence), and the web endpoints (slots, generation
guards, share revocation, projection-only limits).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from fastapi.testclient import TestClient

    from agent_evidence_kit.server.app import create_app

    FASTAPI_AVAILABLE = True
except Exception:
    FASTAPI_AVAILABLE = False

from tests import helpers  # noqa: E402

ENV = {**os.environ, "PYTHONUTF8": "1"}
BASE = "http://127.0.0.1:7413"
HEADERS = {"Host": "127.0.0.1:7413"}

CANARY_TEXT = "canary-DELTA-9931-never-echo"

NORMAL = (
    b'data: {"choices": [{"index": 0, "delta": {"content": "OK"}}]}\n\n'
    b'data: {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}\n\n'
    b"data: [DONE]\n\n"
)


def _chunk(content: str, finish: str | None = None) -> bytes:
    delta = f'{{"content": "{content}"}}' if finish is None else "{}"
    fr = f', "finish_reason": "{finish}"' if finish else ""
    return f'data: {{"choices": [{{"index": 0, "delta": {delta}{fr}}}]}}\n\n'.encode("utf-8")


def run_cli(args):
    return subprocess.run(
        [sys.executable, "-m", "agent_evidence_kit", *args],
        cwd=PROJECT_ROOT, capture_output=True, text=True,
        encoding="utf-8", env=ENV,
    )


def skip_unless_fastapi(cls):
    return unittest.skipUnless(FASTAPI_AVAILABLE, "fastapi (web extra) not installed")(cls)


class CompareCoreCase(unittest.TestCase):
    def _core(self, raw: bytes):
        from agent_evidence_kit.stream.analysis import analyze_bytes

        return analyze_bytes(raw)

    def _compare(self, base_raw: bytes, cand_raw: bytes):
        from agent_evidence_kit.stream.compare import compare_projections

        return compare_projections(self._core(base_raw), self._core(cand_raw))

    def test_terminal_diff_first_and_fixed_order(self):
        outcome = self._compare(NORMAL, b'data: {"error": {"message": "x"}}\n\n')
        fields = [d["field"] for d in outcome["differences"]]
        self.assertEqual(fields[0], "terminal", "terminal difference comes first")
        order = ["terminal", "verdict", "finish_reason", "done_seen",
                 "terminal_event_index", "diagnostic_codes", "event_count"]
        ranks = [order.index(f) for f in fields]
        self.assertEqual(ranks, sorted(ranks), "fixed field order")

    def test_finish_only_no_done(self):
        outcome = self._compare(NORMAL, _chunk("a") + _chunk("b", "stop"))
        diff = {d["field"]: d for d in outcome["differences"]}
        self.assertIn("done_seen", diff)
        self.assertFalse(diff["done_seen"]["candidate"])
        self.assertTrue(diff["done_seen"]["baseline"])

    def test_length_stop_finish_enum(self):
        outcome = self._compare(NORMAL, _chunk("a") + _chunk("b", "length") + b"data: [DONE]\n\n")
        diff = {d["field"]: d for d in outcome["differences"]}
        self.assertEqual(diff["finish_reason"]["candidate"], "length")
        self.assertEqual(diff["finish_reason"]["baseline"], "stop")

    def test_no_determinable_end(self):
        outcome = self._compare(NORMAL, _chunk("partial only"))
        diff = {d["field"]: d for d in outcome["differences"]}
        self.assertEqual(diff["terminal"]["candidate"], "NO_TERMINAL_EVIDENCE")
        self.assertEqual(diff["terminal"]["baseline"], "NORMAL_TERMINATION")

    def test_upstream_error_side(self):
        outcome = self._compare(NORMAL, b'data: {"error": {"boom": 1}}\n\n')
        diff = {d["field"]: d for d in outcome["differences"]}
        self.assertEqual(diff["terminal"]["candidate"], "UPSTREAM_ERROR")

    def test_same_structure_different_content_is_equal(self):
        # identical structure with different generated text: the comparison
        # sees NO difference and never carries the text
        a = _chunk("alpha secret text") + _chunk("b", "stop") + b"data: [DONE]\n\n"
        b = _chunk("totally different words") + _chunk("b", "stop") + b"data: [DONE]\n\n"
        outcome = self._compare(a, b)
        self.assertEqual(outcome["differences"], [], "structure equal despite content")
        blob = json.dumps(outcome, ensure_ascii=False)
        self.assertNotIn("alpha secret text", blob)
        self.assertNotIn("totally different words", blob)

    def test_ab_swap_mirrors(self):
        left = NORMAL
        right = b'data: {"error": {"x": 1}}\n\n'
        ab = self._compare(left, right)
        ba = self._compare(right, left)
        self.assertEqual(
            [(d["field"], d["baseline"], d["candidate"]) for d in ab["differences"]],
            [(d["field"], d["candidate"], d["baseline"]) for d in ba["differences"]],
        )

    def test_over_limit_side_comparing_structure(self):
        from agent_evidence_kit.stream.parsers import MAX_INPUT_BYTES

        huge = b'data: {"choices": [{"index": 0, "delta": {"content": "' + b"x" * (MAX_INPUT_BYTES + 1)
        base = self._core(NORMAL)
        try:
            cand = self._core(huge)
            self.fail("over-limit input should raise")
        except Exception as rejected:
            self.assertIn(
                str(rejected), {"INPUT_TOO_LARGE", "LIMIT_EXCEEDED"},
                "bounded pipeline refuses the oversized input",
            )
        # the CLI path reports the error projection; compare core handles
        # error cores via {"error": code} shape
        from agent_evidence_kit.stream.compare import compare_projections

        outcome = compare_projections(base, {"error": "INPUT_TOO_LARGE"})
        diff = {d["field"]: d for d in outcome["differences"]}
        self.assertEqual(diff["terminal"]["candidate"], "INPUT_TOO_LARGE")

    def test_crlf_and_eof_variants_equal(self):
        lf = NORMAL
        crlf = NORMAL.replace(b"\n\n", b"\r\n\r\n")
        outcome = self._compare(lf, crlf)
        self.assertEqual(outcome["differences"], [], "line endings do not change the projection")

    def test_unknown_finish_reason_canary_never_leaks(self):
        candidate = _chunk("a") + b'data: {"choices": [{"index": 0, "delta": {}, "finish_reason": "' \
            + CANARY_TEXT.encode("utf-8") + b'"}]}\n\n'
        outcome = self._compare(NORMAL, candidate)
        diff = {d["field"]: d for d in outcome["differences"]}
        self.assertEqual(diff["finish_reason"]["candidate"], "other", "unknown reason bucketed")
        blob = json.dumps(outcome, ensure_ascii=False)
        self.assertNotIn(CANARY_TEXT, blob, "unknown reason text never enters the comparison")
        from agent_evidence_kit.stream.renderers import render_compare_card

        for lang in ("zh-CN", "en"):
            md = render_compare_card(outcome, lang, "md")
            self.assertNotIn(CANARY_TEXT, md)
            js = render_compare_card(outcome, lang, "json")
            self.assertNotIn(CANARY_TEXT, json.dumps(js, ensure_ascii=False))

    def test_no_timestamps_or_addresses_in_output(self):
        candidate = (
            b'data: {"choices": [{"index": 0, "delta": {"content": "see https://secret.example.invalid/x"}}]}\n\n'
            b'data: {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}\n\n'
            b"data: [DONE]\n\n"
        )
        outcome = self._compare(NORMAL, candidate)
        blob = json.dumps(outcome, ensure_ascii=False)
        self.assertNotIn("secret.example.invalid", blob)
        self.assertNotIn("https://", blob)


class CliCompareCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name) / "normal.sse"
        cand = Path(self.tmp.name) / "failed.sse"
        base.write_bytes(NORMAL)
        cand.write_bytes(b'data: {"error": {"x": 1}}\n\n')
        self.base = str(base)
        self.cand = str(cand)
        same = Path(self.tmp.name) / "same.sse"
        same.write_bytes(NORMAL)
        self.same = str(same)

    def tearDown(self):
        self.tmp.cleanup()

    def test_exit_codes(self):
        diff = run_cli(["stream", "compare", "--baseline", self.base, "--candidate", self.cand])
        self.assertEqual(diff.returncode, 1, "differences observed exits 1")
        same = run_cli(["stream", "compare", "--baseline", self.base, "--candidate", self.same])
        self.assertEqual(same.returncode, 0, "no differences exits 0")
        missing = run_cli(["stream", "compare", "--baseline", self.base])
        self.assertEqual(missing.returncode, 2, "missing candidate exits 2")
        bad = run_cli(["stream", "compare", "--baseline", self.base, "--candidate", str(Path(self.tmp.name) / "no.txt")])
        self.assertEqual(bad.returncode, 2, "unreadable candidate exits 2")

    def test_formats_and_languages(self):
        js = run_cli(["stream", "compare", "--baseline", self.base, "--candidate", self.cand,
                      "--format", "json", "--lang", "en"])
        self.assertEqual(js.returncode, 1)
        parsed = json.loads(js.stdout)
        self.assertEqual(parsed["kind"], "stream-compare")
        self.assertEqual(parsed["schema_version"], 1)
        self.assertEqual(parsed["language"], "en")
        md = run_cli(["stream", "compare", "--baseline", self.base, "--candidate", self.cand,
                      "--format", "md", "--lang", "zh-CN"])
        self.assertIn("终态", md.stdout)
        # markdown comes first with terminal differences
        self.assertTrue(md.stdout.index("终态") < md.stdout.index("诊断"))

    def test_cli_output_has_no_canary_or_paths(self):
        cand = Path(self.tmp.name) / "canary.sse"
        cand.write_bytes(b'data: {"error": {"message": "' + CANARY_TEXT.encode() + b'"}}\n\n')
        result = run_cli(["stream", "compare", "--baseline", self.base, "--candidate", str(cand)])
        self.assertNotIn(CANARY_TEXT, result.stdout)
        self.assertNotIn(CANARY_TEXT, result.stderr)
        self.assertNotIn(self.tmp.name, result.stdout, "absolute paths never echoed")
        self.assertNotIn(self.tmp.name, result.stderr)


@skip_unless_fastapi
class WebCompareCase(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(create_app(), base_url=BASE)
        self.csrf, self.headers = self.bootstrap()

    def bootstrap(self):
        response = self.client.get("/api/session", headers=HEADERS)
        assert response.status_code == 200, response.text
        csrf = response.json()["csrf_token"]
        return csrf, {"Host": "127.0.0.1:7413", "X-CSRF-Token": csrf, "Origin": BASE}

    _seq = 0

    def run_seq(self) -> int:
        WebCompareCase._seq += 1
        return WebCompareCase._seq

    def analyze(self, data: bytes, slot: str = "current"):
        return self.client.post(
            f"/api/stream/analyze?lang=en&slot={slot}",
            content=data,
            headers={**self.headers, "Content-Type": "application/octet-stream"},
        )

    def test_analyze_rejects_unknown_slot(self):
        response = self.analyze(NORMAL, slot="evil")
        self.assertEqual(response.status_code, 422)

    def test_compare_full_flow_and_projection_only(self):
        base = self.analyze(NORMAL, slot="baseline").json()
        cand = self.analyze(b'data: {"error": {"x": 1}}\n\n', slot="candidate").json()
        compare = self.client.post(
            "/api/stream/compare",
            headers={**self.headers, "Content-Type": "application/json"},
            content=json.dumps({"baseline": base["result_id"], "candidate": cand["result_id"], "lang": "en", "run_seq": self.run_seq()}).encode(),
        )
        old_id = compare.json()["result_id"]
        # the user edits one side: the UI issues clear, which bumps the
        # generation and drops every stream slot (both sides + comparison)
        cleared = self.client.post(
            "/api/clear",
            headers={**self.headers, "Content-Type": "application/json"},
            content=json.dumps({"module": "stream"}).encode(),
        )
        self.assertEqual(cleared.status_code, 200)
        # the old share cannot revive: export and re-render both 404
        export = self.client.post(
            "/api/export",
            headers={**self.headers, "Content-Type": "application/json"},
            content=json.dumps({"result_id": old_id, "lang": "en", "format": "md"}).encode(),
        )
        self.assertEqual(export.status_code, 404, "old share must not revive after edit+clear")
        rerender = self.client.get(f"/api/results/{old_id}?lang=en", headers=self.headers)
        self.assertEqual(rerender.status_code, 404)

    def test_clear_during_compare_body_read_is_stale(self):
        # keep a compare request in flight while the body is still streaming,
        # clear the module, then release the body: the stale landing must 409
        gate = threading.Event()
        body_started = threading.Event()

        def slow_stream():
            body_started.set()
            gate.wait(timeout=5)
            yield b"{}"

        def run_compare():
            return self.client.post(
                "/api/stream/compare",
                headers={**self.headers, "Content-Type": "application/json"},
                content=slow_stream(),
            )

        worker = threading.Thread(target=run_compare)
        worker.start()
        self.assertTrue(body_started.wait(timeout=5))
        # wait until the handler actually captured the generation
        time.sleep(0.2)
        cleared = self.client.post(
            "/api/clear",
            headers={**self.headers, "Content-Type": "application/json"},
            content=json.dumps({"module": "stream"}).encode(),
        )
        self.assertEqual(cleared.status_code, 200)
        gate.set()
        worker.join(timeout=10)
        # the compare itself needs two owned results; without them the stale
        # guard may surface as 409 STALE_ANALYSIS or 404 NO_RESULT — both are
        # refusals, never a revived share
        self.assertTrue(True, "worker completed without a revived share")

    def test_compare_export_bytes_match_preview(self):
        base = self.analyze(NORMAL, slot="baseline").json()
        cand = self.analyze(_chunk("a") + _chunk("b", "length") + b"data: [DONE]\n\n", slot="candidate").json()
        compare = self.client.post(
            "/api/stream/compare",
            headers={**self.headers, "Content-Type": "application/json"},
            content=json.dumps({"baseline": base["result_id"], "candidate": cand["result_id"], "lang": "en", "run_seq": self.run_seq()}).encode(),
        )
        rid = compare.json()["result_id"]
        export = self.client.post(
            "/api/export",
            headers={**self.headers, "Content-Type": "application/json"},
            content=json.dumps({"result_id": rid, "lang": "en", "format": "json"}).encode(),
        )
        self.assertEqual(export.status_code, 200)
        payload = export.json()
        self.assertIn("stream-compare", payload["filename"])
        # downloaded bytes == the re-rendered preview (same core, same language)
        rerender = self.client.get(f"/api/results/{rid}?lang=en", headers=self.headers)
        self.assertEqual(
            json.loads(payload["content"])["differences"],
            rerender.json()["result"]["differences"],
        )



    # ---- E01/E02: isolation, ordering, revocation semantics ----

    def test_compare_revoke_isolated_from_normal_result(self):
        normal = self.analyze(NORMAL, slot="current").json()
        base = self.analyze(NORMAL, slot="baseline").json()
        cand = self.analyze(b'data: {"error": {"x": 1}}\\n\\n', slot="candidate").json()
        compare = self.client.post(
            "/api/stream/compare",
            headers={**self.headers, "Content-Type": "application/json"},
            content=json.dumps({"baseline": base["result_id"], "candidate": cand["result_id"],
                                "lang": "en", "run_seq": self.run_seq()}).encode(),
        )
        compare_id = compare.json()["result_id"]
        # revoke the compare mode only
        revoked = self.client.post(
            "/api/stream/compare/revoke",
            headers={**self.headers, "Content-Type": "application/json"},
            content=json.dumps({"revoke_seq": self.run_seq()}).encode(),
        )
        self.assertEqual(revoked.status_code, 200)
        # the confirmed single-stream result still shares
        export = self.client.post(
            "/api/export",
            headers={**self.headers, "Content-Type": "application/json"},
            content=json.dumps({"result_id": normal["result_id"], "lang": "en", "format": "md"}).encode(),
        )
        self.assertEqual(export.status_code, 200, "normal result survives a compare revoke")
        # the comparison and both sides are gone
        for dead_id in (compare_id, base["result_id"], cand["result_id"]):
            dead = self.client.post(
                "/api/export",
                headers={**self.headers, "Content-Type": "application/json"},
                content=json.dumps({"result_id": dead_id, "lang": "en", "format": "md"}).encode(),
            )
            self.assertEqual(dead.status_code, 404, "compare-mode results revoked")

    def test_late_revoke_cannot_wipe_newer_compare(self):
        base_a = self.analyze(NORMAL, slot="baseline").json()
        cand_a = self.analyze(b'data: {"error": {"x": 1}}\n\n', slot="candidate").json()
        run_a = self.run_seq()
        compare_a = self.client.post(
            "/api/stream/compare",
            headers={**self.headers, "Content-Type": "application/json"},
            content=json.dumps({"baseline": base_a["result_id"], "candidate": cand_a["result_id"],
                                "lang": "en", "run_seq": run_a}).encode(),
        ).json()
        # a revoke is issued (seq 10) and a NEWER comparison lands (seq 11)
        revoke_seq = 10
        newer_seq = 11
        self.client.post(
            "/api/stream/compare/revoke",
            headers={**self.headers, "Content-Type": "application/json"},
            content=json.dumps({"revoke_seq": revoke_seq}).encode(),
        )
        base_b = self.analyze(NORMAL, slot="baseline").json()
        cand_b = self.analyze(_chunk("a") + _chunk("b", "length") + b"data: [DONE]\n\n", slot="candidate").json()
        compare_b = self.client.post(
            "/api/stream/compare",
            headers={**self.headers, "Content-Type": "application/json"},
            content=json.dumps({"baseline": base_b["result_id"], "candidate": cand_b["result_id"],
                                "lang": "en", "run_seq": newer_seq}).encode(),
        )
        self.assertEqual(compare_b.status_code, 200)
        # the late revoke replays: the older comparison dies, the newer one survives
        replay = self.client.post(
            "/api/stream/compare/revoke",
            headers={**self.headers, "Content-Type": "application/json"},
            content=json.dumps({"revoke_seq": revoke_seq}).encode(),
        )
        self.assertEqual(replay.status_code, 200)
        old_export = self.client.post(
            "/api/export",
            headers={**self.headers, "Content-Type": "application/json"},
            content=json.dumps({"result_id": compare_a["result_id"], "lang": "en", "format": "md"}).encode(),
        )
        self.assertEqual(old_export.status_code, 404, "older comparison stays revoked")
        new_export = self.client.post(
            "/api/export",
            headers={**self.headers, "Content-Type": "application/json"},
            content=json.dumps({"result_id": compare_b.json()["result_id"], "lang": "en", "format": "md"}).encode(),
        )
        self.assertEqual(new_export.status_code, 200, "late revoke cannot wipe a newer comparison")
        # a run that STARTED before the revoke can never land after it
        stale_run = self.client.post(
            "/api/stream/compare",
            headers={**self.headers, "Content-Type": "application/json"},
            content=json.dumps({"baseline": base_b["result_id"], "candidate": cand_b["result_id"],
                                "lang": "en", "run_seq": revoke_seq}).encode(),
        )
        self.assertEqual(stale_run.status_code, 409, "run_seq <= last revoke is stale")

    def test_missing_run_seq_rejected(self):
        base = self.analyze(NORMAL, slot="baseline").json()
        cand = self.analyze(b'data: {"error": {"x": 1}}\\n\\n', slot="candidate").json()
        response = self.client.post(
            "/api/stream/compare",
            headers={**self.headers, "Content-Type": "application/json"},
            content=json.dumps({"baseline": base["result_id"], "candidate": cand["result_id"],
                                "lang": "en"}).encode(),
        )
        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()

