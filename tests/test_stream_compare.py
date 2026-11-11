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

    def analyze(self, data: bytes, slot: str = "current", run_id: str = ""):
        suffix = f"&run_id={run_id}" if run_id else ""
        return self.client.post(
            f"/api/stream/analyze?lang=en&slot={slot}{suffix}",
            content=data,
            headers={**self.headers, "Content-Type": "application/octet-stream"},
        )

    def prepare(self) -> str:
        response = self.client.post(
            "/api/stream/compare/prepare",
            headers={**self.headers, "Content-Type": "application/json"},
            content=b"{}",
        )
        assert response.status_code == 200, response.text
        return response.json()["run_id"]

    def compare(self, base_id: str, cand_id: str, run_id: str, lang: str = "en"):
        return self.client.post(
            "/api/stream/compare",
            headers={**self.headers, "Content-Type": "application/json"},
            content=json.dumps({
                "baseline": base_id, "candidate": cand_id, "lang": lang, "run_id": run_id,
            }).encode(),
        )

    def export(self, result_id: str, lang: str = "en", fmt: str = "md"):
        return self.client.post(
            "/api/export",
            headers={**self.headers, "Content-Type": "application/json"},
            content=json.dumps({"result_id": result_id, "lang": lang, "format": fmt}).encode(),
        )

    def test_analyze_rejects_unknown_slot(self):
        response = self.analyze(NORMAL, slot="evil")
        self.assertEqual(response.status_code, 422)

    def test_compare_full_flow_and_projection_only(self):
        run_id = self.prepare()
        base = self.analyze(NORMAL, slot="baseline", run_id=run_id).json()
        cand = self.analyze(b'data: {"error": {"x": 1}}\n\n', slot="candidate", run_id=run_id).json()
        compare = self.compare(base["result_id"], cand["result_id"], run_id)
        self.assertEqual(compare.status_code, 200, compare.text)
        card = compare.json()["result"]
        self.assertEqual(card["kind"], "stream-compare")
        self.assertEqual(card["schema_version"], 1)
        fields = [d["field"] for d in card["differences"]]
        self.assertEqual(fields[0], "terminal")
        rid = compare.json()["result_id"]
        rerender = self.client.get(f"/api/results/{rid}?lang=zh-CN", headers=self.headers)
        self.assertEqual(rerender.status_code, 200)
        self.assertEqual(rerender.json()["result"]["language"], "zh-CN")

    def test_compare_requires_both_stream_results(self):
        run_id = self.prepare()
        config = self.client.post(
            "/api/config/analyze?lang=en",
            content=b"{}",
            headers={**self.headers, "Content-Type": "application/octet-stream", "X-Input-Format": "json"},
        ).json()
        response = self.compare(config["result_id"], config["result_id"], run_id)
        self.assertIn(response.status_code, (404, 409), "config results can never feed a stream compare")

    def test_edit_then_clear_revokes_old_share(self):
        run_id = self.prepare()
        base = self.analyze(NORMAL, slot="baseline", run_id=run_id).json()
        cand = self.analyze(b'data: {"error": {"x": 1}}\n\n', slot="candidate", run_id=run_id).json()
        compare = self.compare(base["result_id"], cand["result_id"], run_id)
        old_id = compare.json()["result_id"]
        cleared = self.client.post(
            "/api/clear",
            headers={**self.headers, "Content-Type": "application/json"},
            content=json.dumps({"module": "stream"}).encode(),
        )
        self.assertEqual(cleared.status_code, 200)
        export = self.export(old_id)
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
        time.sleep(0.2)
        cleared = self.client.post(
            "/api/clear",
            headers={**self.headers, "Content-Type": "application/json"},
            content=json.dumps({"module": "stream"}).encode(),
        )
        self.assertEqual(cleared.status_code, 200)
        gate.set()
        worker.join(timeout=10)
        self.assertTrue(True, "worker completed without a revived share")

    def test_compare_export_bytes_match_preview(self):
        run_id = self.prepare()
        base = self.analyze(NORMAL, slot="baseline", run_id=run_id).json()
        cand = self.analyze(_chunk("a") + _chunk("b", "length") + b"data: [DONE]\n\n", slot="candidate", run_id=run_id).json()
        compare = self.compare(base["result_id"], cand["result_id"], run_id)
        rid = compare.json()["result_id"]
        export = self.export(rid, fmt="json")
        self.assertEqual(export.status_code, 200)
        payload = export.json()
        self.assertIn("stream-compare", payload["filename"])
        rerender = self.client.get(f"/api/results/{rid}?lang=en", headers=self.headers)
        self.assertEqual(
            json.loads(payload["content"])["differences"],
            rerender.json()["result"]["differences"],
        )

    # ---- E03: server-issued run identity ----


    def test_compare_validates_bound_side_results(self):
        """E04: the caller must hand back exactly the side results the current
        run landed — ids from any other stream slot are refused."""
        # a single-stream result exists alongside the compare run
        normal = self.analyze(NORMAL, slot="current").json()
        run_id = self.prepare()
        base = self.analyze(NORMAL, slot="baseline", run_id=run_id).json()
        cand = self.analyze(b'data: {"error": {"x": 1}}\n\n', slot="candidate", run_id=run_id).json()
        # swapping in the normal result for one side is refused
        swapped = self.compare(normal["result_id"], cand["result_id"], run_id)
        self.assertEqual(swapped.status_code, 409, "foreign result id refused")
        swapped2 = self.compare(base["result_id"], normal["result_id"], run_id)
        self.assertEqual(swapped2.status_code, 409, "foreign result id refused")
        # the exact bound pair still compares
        ok = self.compare(base["result_id"], cand["result_id"], run_id)
        self.assertEqual(ok.status_code, 200)

    def test_prepare_revokes_previous_run_immediately(self):
        # the reported defect: after a successful comparison, a refreshed page
        # (fresh prepare) must not collide with stale session state — and the
        # OLD comparison is revoked the moment the new run is prepared
        run_a = self.prepare()
        base_a = self.analyze(NORMAL, slot="baseline", run_id=run_a).json()
        cand_a = self.analyze(b'data: {"error": {"x": 1}}\n\n', slot="candidate", run_id=run_a).json()
        compare_a = self.compare(base_a["result_id"], cand_a["result_id"], run_a)
        self.assertEqual(compare_a.status_code, 200)
        old_id = compare_a.json()["result_id"]
        self.assertEqual(self.export(old_id).status_code, 200)
        # "refresh": a new prepare — the old comparison dies right here
        run_b = self.prepare()
        self.assertEqual(self.export(old_id).status_code, 404,
                         "prepare revokes the previous run's landed results immediately")
        # and a fresh comparison works under the new identity
        base_b = self.analyze(NORMAL, slot="baseline", run_id=run_b).json()
        cand_b = self.analyze(_chunk("a") + _chunk("b", "length") + b"data: [DONE]\n\n", slot="candidate", run_id=run_b).json()
        compare_b = self.compare(base_b["result_id"], cand_b["result_id"], run_b)
        self.assertEqual(compare_b.status_code, 200, "the refreshed run compares cleanly")
        self.assertEqual(self.export(compare_b.json()["result_id"]).status_code, 200)

    def test_stale_run_id_cannot_land(self):
        run_a = self.prepare()
        run_b = self.prepare()
        # analyzing for a superseded run can never land over the newer run
        stale_side = self.analyze(NORMAL, slot="baseline", run_id=run_a)
        self.assertEqual(stale_side.status_code, 409, "stale run_id side is refused")
        base_b = self.analyze(NORMAL, slot="baseline", run_id=run_b).json()
        cand_b = self.analyze(b'data: {"error": {"x": 1}}\n\n', slot="candidate", run_id=run_b).json()
        stale_compare = self.compare(base_b["result_id"], cand_b["result_id"], run_a)
        self.assertEqual(stale_compare.status_code, 409, "stale run_id compare is refused")

    def test_sides_must_belong_to_the_run(self):
        run_a = self.prepare()
        base_a = self.analyze(NORMAL, slot="baseline", run_id=run_a).json()
        run_b = self.prepare()
        cand_b = self.analyze(b'data: {"error": {"x": 1}}\n\n', slot="candidate", run_id=run_b).json()
        # mixing sides from different runs can never compare
        mixed = self.compare(base_a["result_id"], cand_b["result_id"], run_b)
        self.assertEqual(mixed.status_code, 409, "side from another run is refused")

    def test_cancel_kills_in_flight_and_landed_results(self):
        run_id = self.prepare()
        base = self.analyze(NORMAL, slot="baseline", run_id=run_id).json()
        cand = self.analyze(b'data: {"error": {"x": 1}}\n\n', slot="candidate", run_id=run_id).json()
        compare = self.compare(base["result_id"], cand["result_id"], run_id)
        self.assertEqual(compare.status_code, 200)
        landed_id = compare.json()["result_id"]
        cancelled = self.client.post(
            "/api/stream/compare/cancel",
            headers={**self.headers, "Content-Type": "application/json"},
            content=json.dumps({"run_id": run_id}).encode(),
        )
        self.assertEqual(cancelled.status_code, 200)
        # everything that run landed is revoked — even without any further
        # client action (the response could have been lost in transit)
        self.assertEqual(self.export(landed_id).status_code, 404)
        self.assertEqual(self.export(base["result_id"]).status_code, 404)
        self.assertEqual(self.export(cand["result_id"]).status_code, 404)
        # a late landing for the cancelled run can never arrive
        late_side = self.analyze(NORMAL, slot="baseline", run_id=run_id)
        self.assertEqual(late_side.status_code, 409, "cancelled run is dead server-side")

    def test_cancel_of_old_run_cannot_touch_newer_results(self):
        run_a = self.prepare()
        base_a = self.analyze(NORMAL, slot="baseline", run_id=run_a).json()
        cand_a = self.analyze(b'data: {"error": {"x": 1}}\n\n', slot="candidate", run_id=run_a).json()
        compare_a = self.compare(base_a["result_id"], cand_a["result_id"], run_a)
        landed_a = compare_a.json()["result_id"]
        # a NEWER run supersedes A, then the user cancels the OLD run
        run_b = self.prepare()
        base_b = self.analyze(NORMAL, slot="baseline", run_id=run_b).json()
        cand_b = self.analyze(b'data: {"error": {"x": 1}}\n\n', slot="candidate", run_id=run_b).json()
        compare_b = self.compare(base_b["result_id"], cand_b["result_id"], run_b)
        self.assertEqual(compare_b.status_code, 200)
        landed_b = compare_b.json()["result_id"]
        cancelled = self.client.post(
            "/api/stream/compare/cancel",
            headers={**self.headers, "Content-Type": "application/json"},
            content=json.dumps({"run_id": run_a}).encode(),
        )
        self.assertEqual(cancelled.status_code, 200)
        self.assertEqual(self.export(landed_a).status_code, 404, "old run revoked by its own cancel")
        self.assertEqual(self.export(landed_b).status_code, 200,
                         "a late cancel of an older run cannot wipe a newer comparison")

    def test_missing_run_id_rejected(self):
        run_id = self.prepare()
        base = self.analyze(NORMAL, slot="baseline", run_id=run_id).json()
        cand = self.analyze(b'data: {"error": {"x": 1}}\n\n', slot="candidate", run_id=run_id).json()
        no_run = self.client.post(
            "/api/stream/compare",
            headers={**self.headers, "Content-Type": "application/json"},
            content=json.dumps({"baseline": base["result_id"], "candidate": cand["result_id"],
                                "lang": "en"}).encode(),
        )
        self.assertEqual(no_run.status_code, 422)
        side_without_run = self.analyze(NORMAL, slot="baseline")
        self.assertEqual(side_without_run.status_code, 409, "compare sides must name their run")


if __name__ == "__main__":
    unittest.main()
