"""C02 regression: clear must revoke analyses that are still READING their
body, not only analyses inside the core.

The worker invokes the ASGI app directly with a receive() that delivers
the first body chunk, then blocks until released — so the request is
demonstrably mid-body-read when clear() runs (same reproduction shape as
the review evidence, without socket-flaky client threads).
"""
from __future__ import annotations

import asyncio
import sys
import threading
import time
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from fastapi.testclient import TestClient

    from agent_evidence_kit.server.app import create_app
    from agent_evidence_kit.server.sessions import SessionStore

    FASTAPI_AVAILABLE = True
except Exception:
    FASTAPI_AVAILABLE = False

from tests import helpers  # noqa: E402


@unittest.skipUnless(FASTAPI_AVAILABLE, "fastapi (web extra) not installed")
class C02ClearDuringBodyRead(unittest.TestCase):
    def setUp(self):
        self.store = SessionStore()
        self.app = create_app(store=self.store)
        self.client = TestClient(self.app, base_url="http://127.0.0.1:7411")
        r = self.client.get("/api/session", headers={"Host": "127.0.0.1:7411"})
        assert r.status_code == 200, r.text
        csrf = r.json()["csrf_token"]
        self.headers = {"Host": "127.0.0.1:7411", "X-CSRF-Token": csrf}
        session_id = self.client.cookies.get("aek_session")
        self.session = self.store._sessions[session_id]

    def _race(self, module: str, clear_module: str):
        if module == "config":
            body = b'{"mcp_servers": {}}'
            send_headers = [
                (b"host", b"127.0.0.1:7411"),
                (b"content-type", b"application/octet-stream"),
                (b"x-input-format", b"json"),
                (b"origin", b"http://127.0.0.1:7411"),
                (b"x-csrf-token", self.headers["X-CSRF-Token"].encode()),
                (b"cookie", f"aek_session={self.client.cookies.get('aek_session')}".encode()),
            ]
            path = "/api/config/analyze?lang=zh-CN"
        else:
            body = helpers.normal_stream()
            send_headers = [
                (b"host", b"127.0.0.1:7411"),
                (b"content-type", b"application/octet-stream"),
                (b"origin", b"http://127.0.0.1:7411"),
                (b"x-csrf-token", self.headers["X-CSRF-Token"].encode()),
                (b"cookie", f"aek_session={self.client.cookies.get('aek_session')}".encode()),
            ]
            path = "/api/stream/analyze?lang=zh-CN"

        scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": path.split("?")[0],
            "raw_path": path.encode(),
            "query_string": b"lang=zh-CN",
            "root_path": "",
            "server": ("127.0.0.1", 7411),
            "client": ("127.0.0.1", 50000),
            "headers": send_headers,
        }

        started = threading.Event()
        release = threading.Event()
        first = [True]

        async def receive():
            if first[0]:
                first[0] = False
                started.set()
                await asyncio.get_event_loop().run_in_executor(
                    None, release.wait, 10
                )
                return {"type": "http.request", "body": body, "more_body": False}
            return {"type": "http.disconnect"}

        messages: list = []

        async def send(message):
            messages.append(message)

        async def call_app():
            await self.app(scope, receive, send)

        def worker():
            asyncio.run(call_app())

        thread = threading.Thread(target=worker)
        thread.start()
        self.assertTrue(started.wait(10), "request never reached body read")
        self.assertGreaterEqual(self.session.in_flight, 1,
                                "request not registered in flight")

        cleared = self.client.post(
            "/api/clear", json={"module": clear_module},
            headers={**self.headers, "Origin": "http://127.0.0.1:7411"},
        )
        self.assertEqual(cleared.status_code, 200, cleared.text)
        release.set()
        thread.join(15)
        self.assertFalse(thread.is_alive(), "worker request did not finish")

        self.assertTrue(messages, "no ASGI response messages")
        start = next(m for m in messages if m["type"] == "http.response.start")
        body_msgs = b"".join(
            m.get("body", b"") for m in messages if m["type"] == "http.response.body"
        )
        self.assertEqual(start["status"], 409,
                         f"{module}: stale request must not land, got "
                         f"{start['status']} {body_msgs[:120]!r}")
        self.assertIn(b"STALE_ANALYSIS", body_msgs)
        with self.session.lock:
            slots = {m: dict(v) for m, v in self.session.slots.items()}
        self.assertEqual(len(slots[module]), 0,
                         "cleared module must stay empty after the race")
        # A normal new analysis still works after the race.
        if module == "config":
            fresh = self.client.post(
                "/api/config/analyze?lang=zh-CN", content=body,
                headers={**self.headers,
                         "Content-Type": "application/octet-stream",
                         "X-Input-Format": "json",
                         "Origin": "http://127.0.0.1:7411"},
            )
        else:
            fresh = self.client.post(
                "/api/stream/analyze?lang=zh-CN", content=body,
                headers={**self.headers,
                         "Content-Type": "application/octet-stream",
                         "Origin": "http://127.0.0.1:7411"},
            )
        self.assertEqual(fresh.status_code, 200, fresh.text)

    def test_config_clear_module_during_body_read(self):
        self._race("config", "config")

    def test_stream_clear_module_during_body_read(self):
        self._race("stream", "stream")

    def test_config_clear_all_during_body_read(self):
        self._race("config", "all")

    def test_stream_clear_all_during_body_read(self):
        self._race("stream", "all")


if __name__ == "__main__":
    unittest.main()
