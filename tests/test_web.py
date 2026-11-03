"""HTTP layer regressions: both modules' sessions, CSRF, limits, privacy,
CLI/API consistency (gate A/B), plus R03 expiry, R05 clear race, R07 exact
same-origin, and stable 4xx for malformed demo payloads.
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
    from agent_evidence_kit.server.sessions import SessionStore, _Session

    FASTAPI_AVAILABLE = True
except Exception:  # web extra or its httpx test dependency not installed
    FASTAPI_AVAILABLE = False

from tests import helpers  # noqa: E402

BASE = "http://127.0.0.1:7411"
HEADERS = {"Host": "127.0.0.1:7411"}
ENV = {**os.environ, "PYTHONUTF8": "1"}


def run_cli(args):
    return subprocess.run(
        [sys.executable, "-m", "agent_evidence_kit", *args],
        cwd=PROJECT_ROOT, capture_output=True, text=True,
        encoding="utf-8", env=ENV,
    )


def skip_unless_fastapi(cls):
    return unittest.skipUnless(FASTAPI_AVAILABLE, "fastapi (web extra) not installed")(cls)


class WebCase(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(create_app(), base_url=BASE)

    def bootstrap(self):
        response = self.client.get("/api/session", headers=HEADERS)
        assert response.status_code == 200, response.text
        csrf = response.json()["csrf_token"]
        return csrf, {"Host": "127.0.0.1:7411", "X-CSRF-Token": csrf}

    def analyze_config(self, headers, data: bytes, fmt="json"):
        return self.client.post(
            "/api/config/analyze?lang=zh-CN",
            content=data,
            headers={
                **headers,
                "Content-Type": "application/octet-stream",
                "X-Input-Format": fmt,
                "Origin": BASE,
            },
        )

    def analyze_stream(self, headers, data: bytes):
        return self.client.post(
            "/api/stream/analyze?lang=zh-CN",
            content=data,
            headers={
                **headers,
                "Content-Type": "application/octet-stream",
                "Origin": BASE,
            },
        )


@skip_unless_fastapi
class TestSession(WebCase):
    def test_bootstrap_sets_cookie_and_csrf(self):
        response = self.client.get("/api/session", headers=HEADERS)
        self.assertEqual(response.status_code, 200)
        self.assertIn("aek_session", response.cookies)
        body = response.json()
        self.assertIn("csrf_token", body)
        set_cookie = response.headers["set-cookie"]
        self.assertIn("HttpOnly", set_cookie)
        self.assertIn("SameSite=strict", set_cookie.replace("Strict", "strict"))
        self.assertNotIn("Domain=", set_cookie)

    def test_cross_site_fetch_metadata_rejected(self):
        response = self.client.get(
            "/api/session", headers={**HEADERS, "Sec-Fetch-Site": "cross-site"}
        )
        self.assertEqual(response.status_code, 403)

    def test_bad_host_rejected(self):
        response = self.client.get("/api/session", headers={"Host": "evil.example:80"})
        self.assertEqual(response.status_code, 403)

    def test_no_session_unauthorized(self):
        response = self.client.get("/api/results/whatever", headers=HEADERS)
        self.assertEqual(response.status_code, 401)

    def test_bootstrap_reuses_valid_session(self):
        """R04: a second tab must not invalidate the first."""
        first = self.client.get("/api/session", headers=HEADERS)
        csrf1 = first.json()["csrf_token"]
        second = self.client.get("/api/session", headers=HEADERS)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json().get("reused"), True)
        self.assertEqual(second.json()["csrf_token"], csrf1)

    def test_bootstrap_rejects_same_site_different_port(self):
        """R07: exact same-origin, not just same-host."""
        send = {
            **HEADERS,
            "Origin": "http://127.0.0.1:9999",
            "Sec-Fetch-Site": "same-site",
        }
        response = self.client.get("/api/session", headers=send)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"]["code"], "CROSS_ORIGIN")

    def test_bootstrap_rejects_cross_origin(self):
        send = {**HEADERS, "Origin": "http://evil.example:8080"}
        response = self.client.get("/api/session", headers=send)
        self.assertEqual(response.status_code, 403)

    def test_analyze_rejects_same_site_different_origin(self):
        csrf, headers = self.bootstrap()
        send = {
            **headers,
            "Origin": "http://127.0.0.1:9999",
            "Sec-Fetch-Site": "same-site",
            "Content-Type": "application/octet-stream",
            "X-Input-Format": "json",
        }
        response = self.client.post(
            "/api/config/analyze?lang=zh-CN", content=b"{}", headers=send
        )
        self.assertEqual(response.status_code, 403)


@skip_unless_fastapi
class TestSessionExpiry(WebCase):
    """R03: idle/absolute expiry is enforced before refreshing last_seen."""

    def setUp(self):
        self.store = SessionStore()
        self.client = TestClient(create_app(store=self.store), base_url=BASE)

    def _age_session(self, idle=0.0, absolute=0.0):
        csrf, headers = self.bootstrap()
        session_id = self.client.cookies.get("aek_session")
        session = self.store._sessions[session_id]
        now = time.monotonic()
        session.last_seen = now - idle
        session.created = now - absolute
        return csrf, headers, session_id

    def test_idle_expired_result_get_rejected(self):
        csrf, headers, session_id = self.bootstrap(), None, None
        csrf, headers = csrf
        response = self.analyze_config(headers, b'{"mcp_servers": {}}')
        assert response.status_code == 200
        result_id = response.json()["result_id"]
        # age past idle AFTER storing the result, then try to read it
        session_id = self.client.cookies.get("aek_session")
        session = self.store._sessions[session_id]
        session.last_seen = time.monotonic() - 31 * 60
        got = self.client.get(f"/api/results/{result_id}", headers=headers)
        self.assertEqual(got.status_code, 401)
        self.assertEqual(got.json()["error"]["code"], "SESSION_EXPIRED")

    def test_absolute_expired_rejected(self):
        csrf, headers, session_id = self._age_session(absolute=9 * 3600)
        response = self.analyze_config(headers, b'{"mcp_servers": {}}')
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"]["code"], "SESSION_EXPIRED")

    def test_expired_session_cannot_revive(self):
        csrf, headers, session_id = self._age_session(idle=31 * 60)
        self.analyze_config(headers, b'{"mcp_servers": {}}')
        self.client.get("/api/results/whatever", headers=headers)
        # session was dropped; the old cookie must not come back
        self.assertNotIn(session_id, self.store._sessions)
        again = self.client.get("/api/results/whatever", headers=headers)
        self.assertEqual(again.status_code, 401)
        self.assertEqual(again.json()["error"]["code"], "NO_SESSION")

    def test_bootstrap_does_not_revive_expired_session(self):
        csrf, headers, session_id = self._age_session(idle=31 * 60)
        # bootstrap with the stale cookie: must create a NEW session, not reuse
        response = self.client.get("/api/session", headers=HEADERS)
        self.assertEqual(response.status_code, 200)
        self.assertNotEqual(response.json().get("reused"), True)


@skip_unless_fastapi
class TestClearRace(WebCase):
    """R05: clear must atomically revoke in-flight analyses."""

    def setUp(self):
        self.store = SessionStore()
        self.client = TestClient(create_app(store=self.store), base_url=BASE)
        import agent_evidence_kit.server.app as app_module

        self.app_module = app_module
        self.original = app_module.config_analyze_bytes

    def tearDown(self):
        self.app_module.config_analyze_bytes = self.original

    def test_inflight_result_does_not_land_after_clear(self):
        csrf, headers = self.bootstrap()
        session_id = self.client.cookies.get("aek_session")
        session = self.store._sessions[session_id]

        release = threading.Event()
        started = threading.Event()

        def slow_analyze(raw, fmt):
            started.set()
            release.wait(5.0)
            return self.original(raw, fmt)

        self.app_module.config_analyze_bytes = slow_analyze

        outcome: dict = {}

        def worker():
            outcome["response"] = self.analyze_config(headers, b'{"mcp_servers": {}}')

        thread = threading.Thread(target=worker)
        thread.start()
        started.wait(5.0)
        # wait until the request is registered in flight
        for _ in range(100):
            if session.in_flight >= 1:
                break
            time.sleep(0.02)
        cleared = self.client.post(
            "/api/clear", json={"module": "config"},
            headers={**headers, "Origin": BASE},
        )
        self.assertEqual(cleared.status_code, 200)
        release.set()
        thread.join(10)
        response = outcome["response"]
        # The stale analysis must not land: either rejected with a fixed
        # code or missing from the session afterwards.
        with session.lock:
            slots = dict(session.slots["config"])
        if response.status_code == 200:
            result_id = response.json()["result_id"]
            self.assertNotIn(result_id, {s.result_id for s in slots.values()},
                             "cleared-then-landed result must not exist")
        else:
            self.assertEqual(response.status_code, 409)
        self.assertEqual(len(slots), 0)
        # a fresh analysis still works after the race
        self.app_module.config_analyze_bytes = self.original
        fresh = self.analyze_config(headers, b'{"mcp_servers": {}}')
        self.assertEqual(fresh.status_code, 200)


@skip_unless_fastapi
class TestConfigAnalyze(WebCase):
    def test_analyze_demo_and_consistency_with_cli(self):
        csrf, headers = self.bootstrap()
        raw = helpers.residue_config().encode("utf-8")
        response = self.analyze_config(headers, raw)
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["slot"], "current")
        self.assertEqual(body["module"], "config")
        card = body["result"]
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as handle:
            handle.write(raw)
            path = handle.name
        try:
            cli = run_cli(["config", "--input", path, "--lang", "zh-CN"])
        finally:
            os.unlink(path)
        self.assertEqual(json.loads(cli.stdout), card)

    def test_demo_runs_real_core(self):
        csrf, headers = self.bootstrap()
        response = self.client.post(
            "/api/config/demo",
            json={"case_id": "http-residue", "lang": "en"},
            headers={**headers, "Origin": BASE},
        )
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["slot"], "reference")
        codes = [
            f["code"] for f in body["result"]["services"][0]["findings"]
        ]
        self.assertIn("POSSIBLE_TRANSPORT_RESIDUE", codes)
        self.assertEqual(body["result"]["language"], "en")

    def test_demo_malformed_case_id_is_4xx_not_500(self):
        csrf, headers = self.bootstrap()
        for payload in (
            {"case_id": ["http-residue"], "lang": "zh-CN"},  # array: was 500
            {"case_id": 42, "lang": "zh-CN"},
            {"lang": "zh-CN"},
        ):
            response = self.client.post(
                "/api/config/demo", json=payload,
                headers={**headers, "Origin": BASE},
            )
            self.assertGreaterEqual(response.status_code, 400, payload)
            self.assertLess(response.status_code, 500, payload)

    def test_wrong_input_format_rejected(self):
        csrf, headers = self.bootstrap()
        send = dict(headers)
        send["Content-Type"] = "application/octet-stream"
        send["X-Input-Format"] = "exe"
        send["Origin"] = BASE
        response = self.client.post(
            "/api/config/analyze?lang=zh-CN", content=b"{}", headers=send
        )
        self.assertEqual(response.status_code, 422)
        self.assertNotIn(b"exe", response.content)

    def test_oversized_body_rejected_413(self):
        csrf, headers = self.bootstrap()
        response = self.analyze_config(headers, b"x" * (8 * 1024 * 1024 + 1))
        self.assertEqual(response.status_code, 413)

    def test_over_file_limit_returns_error_card_200(self):
        csrf, headers = self.bootstrap()
        response = self.analyze_config(headers, b"x" * (300 * 1024))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["result"]["error"]["code"], "INPUT_TOO_LARGE")

    def test_csrf_required(self):
        _, headers = self.bootstrap()
        response = self.analyze_config(
            {k: v for k, v in headers.items() if k != "X-CSRF-Token"}, b"{}"
        )
        self.assertEqual(response.status_code, 403)

    def test_cross_origin_rejected(self):
        csrf, headers = self.bootstrap()
        send = dict(headers)
        send["Content-Type"] = "application/octet-stream"
        send["X-Input-Format"] = "json"
        send["Origin"] = "http://evil.example:8080"
        response = self.client.post(
            "/api/config/analyze?lang=zh-CN", content=b"{}", headers=send
        )
        self.assertEqual(response.status_code, 403)

    def test_wrong_content_type_rejected(self):
        csrf, headers = self.bootstrap()
        response = self.client.post(
            "/api/config/analyze?lang=zh-CN",
            json={"a": 1},
            headers={**headers, "Origin": BASE},
        )
        self.assertEqual(response.status_code, 415)


@skip_unless_fastapi
class TestStreamAnalyze(WebCase):
    def test_analyze_matches_cli_json(self):
        csrf, headers = self.bootstrap()
        raw = helpers.normal_stream()
        response = self.analyze_stream(headers, raw)
        self.assertEqual(response.status_code, 200, response.text)
        card = response.json()["result"]
        self.assertEqual(response.json()["module"], "stream")
        with tempfile.NamedTemporaryFile(suffix=".sse", delete=False) as handle:
            handle.write(raw)
            path = handle.name
        try:
            cli = run_cli(["stream", "--input", path, "--lang", "zh-CN"])
        finally:
            os.unlink(path)
        self.assertEqual(json.loads(cli.stdout), card)

    def test_demo_runs_real_core(self):
        csrf, headers = self.bootstrap()
        response = self.client.post(
            "/api/stream/demo",
            json={"case_id": "finish-only", "lang": "en"},
            headers={**headers, "Origin": BASE},
        )
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["slot"], "reference")
        self.assertIn(
            "FINISH_WITHOUT_DONE", [f["code"] for f in body["result"]["findings"]]
        )
        self.assertEqual(body["result"]["language"], "en")

    def test_demo_malformed_case_id_is_4xx_not_500(self):
        csrf, headers = self.bootstrap()
        response = self.client.post(
            "/api/stream/demo",
            json={"case_id": {"bad": 1}, "lang": "zh-CN"},
            headers={**headers, "Origin": BASE},
        )
        self.assertGreaterEqual(response.status_code, 400)
        self.assertLess(response.status_code, 500)


@skip_unless_fastapi
class TestSessionIsolationAndLimits(WebCase):
    def test_result_ids_are_session_scoped(self):
        client_a = TestClient(create_app(), base_url=BASE)
        client_b = TestClient(create_app(), base_url=BASE)
        r = client_a.get("/api/session", headers=HEADERS)
        headers_a = {"Host": "127.0.0.1:7411", "X-CSRF-Token": r.json()["csrf_token"]}
        r = client_b.get("/api/session", headers=HEADERS)
        headers_b = {"Host": "127.0.0.1:7411", "X-CSRF-Token": r.json()["csrf_token"]}

        def config_analyze(client, headers):
            return client.post(
                "/api/config/analyze?lang=zh-CN",
                content=helpers.plain_stdio_config().encode(),
                headers={
                    **headers,
                    "Origin": BASE,
                    "Content-Type": "application/octet-stream",
                    "X-Input-Format": "json",
                },
            )

        result_id = config_analyze(client_a, headers_a).json()["result_id"]
        other = client_b.get(f"/api/results/{result_id}", headers=headers_b)
        self.assertEqual(other.status_code, 404)
        mine = client_a.get(f"/api/results/{result_id}", headers=headers_a)
        self.assertEqual(mine.status_code, 200)

    def test_two_modules_keep_separate_slots(self):
        csrf, headers = self.bootstrap()
        config_result = self.analyze_config(headers, b'{"mcp_servers": {}}').json()
        stream_result = self.analyze_stream(headers, helpers.normal_stream()).json()
        self.assertEqual(
            self.client.get(f"/api/results/{config_result['result_id']}", headers=headers).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(f"/api/results/{stream_result['result_id']}", headers=headers).status_code,
            200,
        )

    def test_clear_module_does_not_touch_other_module(self):
        csrf, headers = self.bootstrap()
        config_result = self.analyze_config(headers, b'{"mcp_servers": {}}').json()
        stream_result = self.analyze_stream(headers, helpers.normal_stream()).json()
        cleared = self.client.post(
            "/api/clear", json={"module": "config"},
            headers={**headers, "Origin": BASE},
        )
        self.assertEqual(cleared.status_code, 200)
        self.assertEqual(
            self.client.get(f"/api/results/{config_result['result_id']}", headers=headers).status_code,
            404,
        )
        self.assertEqual(
            self.client.get(f"/api/results/{stream_result['result_id']}", headers=headers).status_code,
            200,
        )

    def test_clear_all_clears_both_modules(self):
        csrf, headers = self.bootstrap()
        config_result = self.analyze_config(headers, b'{"mcp_servers": {}}').json()
        stream_result = self.analyze_stream(headers, helpers.normal_stream()).json()
        cleared = self.client.post(
            "/api/clear", json={"module": "all"},
            headers={**headers, "Origin": BASE},
        )
        self.assertEqual(cleared.status_code, 200)
        for rid in (config_result["result_id"], stream_result["result_id"]):
            self.assertEqual(
                self.client.get(f"/api/results/{rid}", headers=headers).status_code,
                404,
            )

    def test_language_re_render_without_reanalysis(self):
        csrf, headers = self.bootstrap()
        response = self.analyze_config(headers, b'{"mcp_servers": {}}')
        result_id = response.json()["result_id"]
        en = self.client.get(f"/api/results/{result_id}?lang=en", headers=headers)
        self.assertEqual(en.json()["result"]["language"], "en")
        zh = self.client.get(f"/api/results/{result_id}?lang=zh-CN", headers=headers)
        self.assertEqual(zh.json()["result"]["language"], "zh-CN")

    def test_export_returns_fixed_name_and_content(self):
        csrf, headers = self.bootstrap()
        response = self.analyze_config(headers, b'{"mcp_servers": {}}')
        result_id = response.json()["result_id"]
        exported = self.client.post(
            "/api/export",
            json={"result_id": result_id, "lang": "en", "format": "md"},
            headers={**headers, "Origin": BASE},
        )
        self.assertEqual(exported.status_code, 200, exported.text)
        body = exported.json()
        self.assertTrue(body["filename"].endswith("-en.md"))
        self.assertIn("Agent Configuration Evidence Card", body["content"])

    def test_stream_export_contains_evidence_card(self):
        csrf, headers = self.bootstrap()
        response = self.analyze_stream(headers, helpers.normal_stream())
        result_id = response.json()["result_id"]
        exported = self.client.post(
            "/api/export",
            json={"result_id": result_id, "lang": "zh-CN", "format": "md"},
            headers={**headers, "Origin": BASE},
        )
        self.assertEqual(exported.status_code, 200, exported.text)
        self.assertIn("流结束证据卡", exported.json()["content"])

    def test_combined_export_requires_both_results_and_marks_missing(self):
        csrf, headers = self.bootstrap()
        config_result = self.analyze_config(headers, b'{"mcp_servers": {}}').json()
        stream_result = self.analyze_stream(headers, helpers.normal_stream()).json()
        # both
        both = self.client.post(
            "/api/export/combined",
            json={
                "items": [
                    {"module": "config", "result_id": config_result["result_id"]},
                    {"module": "stream", "result_id": stream_result["result_id"]},
                ],
                "lang": "en",
                "format": "json",
            },
            headers={**headers, "Origin": BASE},
        )
        self.assertEqual(both.status_code, 200, both.text)
        content = json.loads(both.json()["content"])
        self.assertEqual(content["envelope_version"], 1)
        self.assertIn("config", content["modules"])
        self.assertIn("stream", content["modules"])
        self.assertEqual(content["not_provided"], [])
        self.assertTrue(content["limitations"])
        # config only: stream explicitly not provided, never faked
        only = self.client.post(
            "/api/export/combined",
            json={
                "items": [
                    {"module": "config", "result_id": config_result["result_id"]}
                ],
                "lang": "zh-CN",
                "format": "json",
            },
            headers={**headers, "Origin": BASE},
        )
        self.assertEqual(only.status_code, 200)
        content = json.loads(only.json()["content"])
        self.assertNotIn("stream", content["modules"])
        self.assertIn("stream", content["not_provided"])
        # a cleared (expired) result must never be silently included
        self.client.post(
            "/api/clear", json={"module": "stream"},
            headers={**headers, "Origin": BASE},
        )
        stale = self.client.post(
            "/api/export/combined",
            json={
                "items": [
                    {"module": "config", "result_id": config_result["result_id"]},
                    {"module": "stream", "result_id": stream_result["result_id"]},
                ],
                "lang": "en",
                "format": "json",
            },
            headers={**headers, "Origin": BASE},
        )
        self.assertEqual(stale.status_code, 404)

    def test_projection_limit_enforced(self):
        from agent_evidence_kit.config.analysis import analyze_bytes as cfg

        big_doc = {
            "mcp_servers": {f"svc-{i}": {"command": "c"} for i in range(32)}
        }
        core = cfg(json.dumps(big_doc).encode(), "json")
        size = len(json.dumps({"core": core}, ensure_ascii=False).encode())
        client = TestClient(create_app(projection_limit=size + 1), base_url=BASE)
        r = client.get("/api/session", headers=HEADERS)
        headers = {"Host": "127.0.0.1:7411", "X-CSRF-Token": r.json()["csrf_token"]}
        send = {
            **headers,
            "Origin": BASE,
            "Content-Type": "application/octet-stream",
            "X-Input-Format": "json",
        }
        first = client.post(
            "/api/config/analyze?lang=zh-CN", content=json.dumps(big_doc).encode(),
            headers=send,
        )
        self.assertEqual(first.status_code, 200)
        second = client.post("/api/config/analyze?lang=zh-CN", content=b"{}", headers=send)
        self.assertEqual(second.status_code, 413)

    def test_error_responses_are_sanitized(self):
        csrf, headers = self.bootstrap()
        response = self.client.post(
            "/api/config/analyze?lang=zh-CN",
            content=b"\xff\xfe\xff",
            headers={
                **headers,
                "Content-Type": "application/octet-stream",
                "X-Input-Format": "json",
                "Origin": BASE,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["result"]["error"]["code"], "INVALID_ENCODING")
        self.assertNotIn(b"\\xff", response.content)

    def test_deep_input_http_is_stable_error_card(self):
        """R01: deep input via HTTP must not 500 and must not leak."""
        csrf, headers = self.bootstrap()
        deep = helpers.deep_config_json(1500).encode()
        response = self.analyze_config(headers, deep)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["result"]["error"]["code"], "LIMIT_EXCEEDED")
        self.assertNotIn(b"Traceback", response.content)
        self.assertNotIn(b"parsers.py", response.content)

    def test_stream_invalid_encoding_sanitized(self):
        csrf, headers = self.bootstrap()
        response = self.analyze_stream(headers, b"data: \xff\xfe\xff\n\n")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["result"]["findings"][0]["code"], "INVALID_ENCODING"
        )
        self.assertNotIn(b"\\xff", response.content)


@skip_unless_fastapi
class TestStaticAndHeaders(WebCase):
    def test_security_headers_present(self):
        response = self.client.get("/api/health", headers=HEADERS)
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        self.assertIn("frame-ancestors 'none'", response.headers["Content-Security-Policy"])
        self.assertEqual(response.headers["Referrer-Policy"], "no-referrer")

    def test_no_swagger(self):
        for path in ("/docs", "/redoc", "/openapi.json"):
            response = self.client.get(path, headers=HEADERS)
            self.assertIn(response.status_code, (404, 401))


if __name__ == "__main__":
    unittest.main()
