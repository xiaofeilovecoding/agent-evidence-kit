"""Shared in-memory session and result storage for the local web UI.

Security model: loopback binding, per-product session cookie, idle and
absolute expiry checked on every authenticated request (R03), session
reuse on bootstrap so a second tab does not overwrite the first (R04),
atomic generation counters so a clear() revokes in-flight analyses (R05),
and projection-only storage with hard caps. No raw input bytes are ever
stored; only the language-neutral projection cores.
"""
from __future__ import annotations

import json
import secrets
import threading
import time

MAX_SESSIONS = 10
MAX_SLOTS_PER_MODULE = 2
MAX_TOTAL_PROJECTION_BYTES = 50 * 1024 * 1024
MAX_CONCURRENT_ANALYSES = 2
SESSION_IDLE_SECONDS = 30 * 60
SESSION_COOKIE_MAX_AGE = 8 * 3600
SESSION_ABSOLUTE_SECONDS = 8 * 3600
COOKIE_NAME = "aek_session"
CSRF_HEADER = "X-CSRF-Token"

MODULES = ("config", "stream")
MAX_BODY_BYTES = 8 * 1024 * 1024


class HttpError(Exception):
    def __init__(self, status: int, code: str):
        self.status = status
        self.code = code


class _Slot:
    __slots__ = ("result_id", "core", "revision", "bytes")

    def __init__(self, result_id: str, core: dict, revision: int, size: int):
        self.result_id = result_id
        self.core = core
        self.revision = revision
        self.bytes = size


class _Session:
    def __init__(self, host_port: str):
        self.host_port = host_port
        self.csrf = secrets.token_urlsafe(32)
        self.created = time.monotonic()
        self.last_seen = self.created
        # slots[module][slot_name] -> _Slot; module is "config" or "stream".
        self.slots: dict[str, dict[str, _Slot]] = {m: {} for m in MODULES}
        self.revision = 0
        # Generation counter per module: clear() bumps it atomically, so an
        # in-flight analysis started before the clear can no longer land.
        self.generation: dict[str, int] = {m: 0 for m in MODULES}
        self.in_flight = 0
        self.lock = threading.Lock()

    def is_expired(self, now: float) -> bool:
        return (
            now - self.last_seen > SESSION_IDLE_SECONDS
            or now - self.created > SESSION_ABSOLUTE_SECONDS
        )


class SessionStore:
    def __init__(self):
        self._lock = threading.Lock()
        self._sessions: "dict[str, _Session]" = {}

    def create(self, host_port: str) -> tuple[str, _Session]:
        with self._lock:
            self._purge_locked()
            if len(self._sessions) >= MAX_SESSIONS:
                raise HttpError(429, "SESSION_LIMIT")
            session_id = secrets.token_urlsafe(32)
            session = _Session(host_port)
            self._sessions[session_id] = session
            return session_id, session

    def get(self, session_id: str | None) -> _Session:
        if not session_id:
            raise HttpError(401, "NO_SESSION")
        with self._lock:
            session = self._sessions.get(session_id)
        if session is None:
            raise HttpError(401, "NO_SESSION")
        return session

    def drop(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)

    def _purge_locked(self) -> None:
        now = time.monotonic()
        expired = [sid for sid, s in self._sessions.items() if s.is_expired(now)]
        for sid in expired:
            del self._sessions[sid]


def estimate_size(core: dict) -> int:
    return len(json.dumps(core, ensure_ascii=False).encode("utf-8"))
