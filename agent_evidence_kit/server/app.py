"""FastAPI adapter: one local-only web service over both cores.

Routes are module-scoped (``/api/config/*``, ``/api/stream/*``) while
session, results, export, and clear are shared. Security: loopback
binding, exact same-origin enforcement including bootstrap (R07),
Fetch Metadata, CSRF, streaming body limits, bounded projection slots
per module, and fully sanitized fixed-code errors. No model keys, no
telemetry, no raw values in responses or logs.
"""
from __future__ import annotations

import json
import secrets
from pathlib import Path

# Imported at module level so FastAPI can resolve Request annotations
# under `from __future__ import annotations`.
from fastapi import Request  # noqa: E402

from ..config.analysis import analyze_bytes as config_analyze_bytes
from ..config.parsers import MAX_FILE_BYTES as CONFIG_MAX_FILE_BYTES
from ..config.parsers import InputRejected as ConfigInputRejected
from ..config.renderers import LANGUAGES
from ..config.renderers import render_card as render_config_card
from ..demos import (
    CONFIG_DEMO_CASES,
    STREAM_DEMO_BYTES,
    STREAM_DEMO_CASES,
    STREAM_DEMO_DESCRIPTIONS,
    config_demo_bytes,
)
from ..stream.analysis import analyze_bytes as stream_analyze_bytes
from ..stream.analysis import analyze_chunks as stream_analyze_chunks
from ..stream.compare import compare_projections
from ..stream.parsers import InputRejected as StreamInputRejected
from ..stream.parsers import MAX_INPUT_BYTES as STREAM_MAX_INPUT_BYTES
from ..stream.renderers import render_card as render_stream_card
from ..stream.renderers import render_compare_card
from .sessions import (
    COOKIE_NAME,
    CSRF_HEADER,
    MAX_BODY_BYTES,
    SESSION_COOKIE_MAX_AGE,
    MAX_CONCURRENT_ANALYSES,
    MAX_SLOTS_PER_MODULE,
    MAX_SLOTS_PER_MODULE_STREAM,
    MAX_TOTAL_PROJECTION_BYTES,
    MODULES,
    HttpError,
    SessionStore,
    estimate_size,
)

_STATIC_DIR = Path(__file__).resolve().parent.parent / "_web_static"

CONFIG_SCOPE_STATEMENT = {
    "zh-CN": "范围说明：本卡片只检查配置结构，不验证任何客户端版本、连接或运行行为；结果不含任何原始配置值。",
    "en": "Scope: this card checks configuration structure only; it does not validate client versions, connectivity, or runtime behavior, and it never contains raw configuration values.",
}
STREAM_LIMITS_STATEMENT = {
    "zh-CN": "固定局限：本工具只观察结束证据，不推断真实时间/吞吐量，不验证供应商兼容性或认证，无法判断答案正确性。",
    "en": "Fixed limits: this tool observes terminal evidence only; it does not infer real timing/throughput, provider compatibility, or authentication, and cannot judge answer correctness.",
}
MODULE_NOT_PROVIDED = {
    "zh-CN": "未提供本模块的结果。",
    "en": "No result was provided for this module.",
}


def _check_host(request: Request) -> str:
    host = request.headers.get("host", "")
    if not host:
        raise HttpError(403, "UNTRUSTED_HOST")
    if host.startswith("["):
        hostname = host[1 : host.index("]")]
    else:
        hostname = host.rsplit(":", 1)[0] if ":" in host else host
    if hostname not in ("127.0.0.1", "::1", "localhost"):
        raise HttpError(403, "UNTRUSTED_HOST")
    return host


def _require_exact_origin(request: Request, host: str) -> None:
    """Exact same-origin: reject cross-origin AND same-site different port."""
    origin = request.headers.get("origin")
    if origin is not None and origin != f"http://{host}":
        raise HttpError(403, "CROSS_ORIGIN")


def _check_fetch_metadata(request: Request) -> None:
    site = request.headers.get("sec-fetch-site")
    if site in ("cross-site", "same-site"):
        # same-site with a different port is not same-origin (R07).
        raise HttpError(403, "CROSS_ORIGIN")


def _require_csrf(request: Request, session) -> None:
    token = request.headers.get(CSRF_HEADER)
    if not token or not secrets.compare_digest(token, session.csrf):
        raise HttpError(403, "CSRF")


def _check_content_type(request: Request, expected: str) -> None:
    ctype = request.headers.get("content-type", "").split(";")[0].strip().lower()
    if ctype != expected:
        raise HttpError(415, "BAD_CONTENT_TYPE")


async def _read_body_limited(request: Request) -> bytes:
    chunks = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > MAX_BODY_BYTES:
            raise HttpError(413, "BODY_TOO_LARGE")
        chunks.append(chunk)
    return b"".join(chunks)


async def _read_json_payload(request: Request) -> dict:
    body = await _read_body_limited(request)
    try:
        payload = json.loads(body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        raise HttpError(422, "BAD_JSON") from None
    if not isinstance(payload, dict):
        raise HttpError(422, "BAD_JSON") from None
    return payload


def create_app(store: SessionStore | None = None,
               projection_limit: int = MAX_TOTAL_PROJECTION_BYTES):
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse
    from fastapi.staticfiles import StaticFiles

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    sessions = store if store is not None else SessionStore()

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data:; "
            "frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        )
        return response

    @app.exception_handler(HttpError)
    async def http_error(request: Request, exc: HttpError):
        return JSONResponse({"error": {"code": exc.code}}, status_code=exc.status)

    # ---- session handling (R03/R04) ----

    def _session_from_cookie(request: Request):
        host = _check_host(request)
        session_id = request.cookies.get(COOKIE_NAME)
        if not session_id:
            raise HttpError(401, "NO_SESSION")
        session = sessions.get(session_id)
        # R03: check idle/absolute expiry BEFORE refreshing last_seen, so an
        # idle session cannot be revived by any request.
        import time

        with session.lock:
            now = time.monotonic()
            if session.is_expired(now):
                sessions.drop(session_id)
                raise HttpError(401, "SESSION_EXPIRED")
            session.last_seen = now
        if session.host_port != host:
            raise HttpError(403, "SESSION_HOST_MISMATCH")
        return session

    def _owned_result(session, result_id: str):
        for module in MODULES:
            for slot in session.slots[module].values():
                if slot.result_id == result_id:
                    return module, slot
        raise HttpError(404, "NO_RESULT")

    # ---- shared endpoints ----

    @app.get("/api/health")
    def health():
        return {"status": "ok", "mode": "local", "needs_api_key": False}

    @app.get("/api/session")
    def session_bootstrap(request: Request):
        host = _check_host(request)
        # R07: bootstrap enforces the same exact same-origin rule as the
        # rest of the API, including same-site different-port rejection.
        _check_fetch_metadata(request)
        _require_exact_origin(request, host)
        # R04: reuse a still-valid session instead of creating a new one,
        # so a second tab sharing the cookie does not invalidate the first.
        cookie_id = request.cookies.get(COOKIE_NAME)
        if cookie_id:
            import time

            try:
                existing = sessions.get(cookie_id)
            except HttpError:
                existing = None
            if existing is not None and not existing.is_expired(time.monotonic()):
                response = JSONResponse(
                    {"csrf_token": existing.csrf, "mode": "local", "reused": True}
                )
                response.set_cookie(
                    COOKIE_NAME,
                    cookie_id,
                    max_age=SESSION_COOKIE_MAX_AGE,
                    httponly=True,
                    samesite="strict",
                    path="/",
                )
                return response
        session_id, session = sessions.create(host)
        response = JSONResponse({"csrf_token": session.csrf, "mode": "local"})
        response.set_cookie(
            COOKIE_NAME,
            session_id,
            max_age=SESSION_COOKIE_MAX_AGE,
            httponly=True,
            samesite="strict",
            path="/",
        )
        return response

    @app.get("/api/catalog")
    def catalog(request: Request, module: str = "config", lang: str = "zh-CN"):
        _check_host(request)
        if lang not in LANGUAGES:
            raise HttpError(422, "BAD_LANGUAGE")
        if module == "config":
            return {"cases": list(CONFIG_DEMO_CASES)}
        if module == "stream":
            # The normal-termination reference is rendered by the same core
            # per language; it never occupies a session slot.
            normal_core = stream_analyze_chunks([STREAM_DEMO_BYTES["normal"]])
            return {
                "cases": [
                    {
                        "case_id": case_id,
                        "description": STREAM_DEMO_DESCRIPTIONS[case_id],
                    }
                    for case_id in STREAM_DEMO_CASES
                ],
                "normal_reference": render_stream_card(normal_core, lang, "json"),
            }
        raise HttpError(422, "BAD_MODULE")

    @app.get("/api/results/{result_id}")
    def get_result(result_id: str, request: Request, lang: str = "zh-CN"):
        _check_host(request)
        session = _session_from_cookie(request)
        if lang not in LANGUAGES:
            raise HttpError(422, "BAD_LANGUAGE")
        module, slot = _owned_result(session, result_id)
        card = _render_slot_card(slot.core, module, lang, "json")
        return {
            "result_id": slot.result_id,
            "revision": slot.revision,
            "module": module,
            "result": card,
        }

    @app.post("/api/export")
    async def export(request: Request):
        host = _check_host(request)
        session = _session_from_cookie(request)
        _require_exact_origin(request, host)
        _require_csrf(request, session)
        _check_content_type(request, "application/json")
        payload = await _read_json_payload(request)
        result_id = payload.get("result_id")
        lang = payload.get("lang")
        export_format = payload.get("format")
        if not isinstance(result_id, str):
            raise HttpError(422, "BAD_JSON")
        if lang not in LANGUAGES:
            raise HttpError(422, "BAD_LANGUAGE")
        if export_format not in ("json", "md"):
            raise HttpError(422, "BAD_EXPORT_FORMAT")
        module, slot = _owned_result(session, result_id)
        if module == "config":
            card = render_config_card(slot.core, lang, export_format)
            base = "config-evidence-card"
        elif isinstance(slot.core, dict) and slot.core.get("kind") == "stream-compare":
            card = render_compare_card(slot.core, lang, export_format)
            base = "stream-compare-report"
        else:
            card = render_stream_card(slot.core, lang, export_format)
            base = "stream-evidence-report"
        if export_format == "json":
            content = json.dumps(card, ensure_ascii=False, indent=2)
            media = "application/json"
            ext = "json"
        else:
            content = card if isinstance(card, str) else str(card)
            media = "text/markdown; charset=utf-8"
            ext = "md"
        filename = f"{base}-{slot.result_id[:8]}-{lang}.{ext}"
        return {"filename": filename, "content_type": media, "content": content}

    @app.post("/api/export/combined")
    async def export_combined(request: Request):
        host = _check_host(request)
        session = _session_from_cookie(request)
        _require_exact_origin(request, host)
        _require_csrf(request, session)
        _check_content_type(request, "application/json")
        payload = await _read_json_payload(request)
        items = payload.get("items")
        lang = payload.get("lang")
        export_format = payload.get("format")
        if lang not in LANGUAGES:
            raise HttpError(422, "BAD_LANGUAGE")
        if export_format not in ("json", "md"):
            raise HttpError(422, "BAD_EXPORT_FORMAT")
        if not isinstance(items, list) or not items:
            raise HttpError(422, "BAD_JSON")
        cards: dict[str, object] = {}
        markdown_parts: dict[str, str] = {}
        for item in items:
            if not isinstance(item, dict):
                raise HttpError(422, "BAD_JSON")
            module = item.get("module")
            result_id = item.get("result_id")
            if module not in MODULES or not isinstance(result_id, str):
                raise HttpError(422, "BAD_JSON")
            # A missing or expired result is never silently included.
            found_module, slot = _owned_result(session, result_id)
            if found_module != module:
                raise HttpError(404, "NO_RESULT")
            if module == "config":
                cards["config"] = render_config_card(slot.core, lang, "json")
                markdown_parts["config"] = render_config_card(slot.core, lang, "md")
            else:
                cards["stream"] = _render_slot_card(slot.core, module, lang, "json")
                markdown_parts["stream"] = _render_slot_card(slot.core, module, lang, "md")
        is_zh = lang == "zh-CN"
        limitations = []
        if "config" in cards:
            limitations.append(
                CONFIG_SCOPE_STATEMENT[lang]
            )
        if "stream" in cards:
            limitations.append(
                STREAM_LIMITS_STATEMENT[lang]
            )
        envelope = {
            "envelope_version": 1,
            "language": lang,
            "modules": cards,
            "limitations": limitations,
            "not_provided": [
                m for m in MODULES
                if m not in cards
            ],
        }
        if export_format == "md":
            lines = ["# Agent Evidence Kit" if not is_zh else "# Agent 证据集"]
            lines.append("")
            if is_zh:
                lines.append(
                    "组合导出包含用户勾选的模块结果；未勾选的模块明确标注未提供。"
                    "两个模块的输入可能来自不同运行，本工具不推断其关联。"
                )
            else:
                lines.append(
                    "This combined export contains only the module results the "
                    "user selected; omitted modules are explicitly marked as not "
                    "provided. The two module inputs may come from different runs "
                    "and are never correlated."
                )
            lines.append("")
            for note in limitations:
                lines.append(f"- {note}")
            lines.append("")
            if "config" in markdown_parts:
                lines.append(markdown_parts["config"].rstrip("\n"))
                lines.append("")
            if "stream" in markdown_parts:
                lines.append(markdown_parts["stream"].rstrip("\n"))
                lines.append("")
            for module in envelope["not_provided"]:
                label = "配置检查" if module == "config" else "流结束检查"
                lines.append(f"- {MODULE_NOT_PROVIDED[lang]} ({module}: {label})" if is_zh
                             else f"- {MODULE_NOT_PROVIDED[lang]} ({module})")
            lines.append("")
            return {
                "filename": f"agent-evidence-kit-combined-{lang}.md",
                "content_type": "text/markdown; charset=utf-8",
                "content": "\n".join(lines),
            }
        return {
            "filename": f"agent-evidence-kit-combined-{lang}.json",
            "content_type": "application/json",
            "content": json.dumps(envelope, ensure_ascii=False, indent=2),
        }

    @app.post("/api/clear")
    async def clear(request: Request):
        host = _check_host(request)
        session = _session_from_cookie(request)
        _require_exact_origin(request, host)
        _require_csrf(request, session)
        _check_content_type(request, "application/json")
        payload = await _read_json_payload(request)
        module = payload.get("module", "all")
        with session.lock:
            if module == "all":
                for m in MODULES:
                    session.slots[m].clear()
                    session.generation[m] += 1
                session.compare_generation += 1
                session.compare_run_id = None
                session.compare_side_run.clear()
                session.compare_side_result.clear()
                session.compare_result_run = None
            elif module in MODULES:
                session.slots[module].clear()
                session.generation[module] += 1
                if module == "stream":
                    session.compare_generation += 1
                    session.compare_run_id = None
                    session.compare_side_run.clear()
                    session.compare_side_result.clear()
                    session.compare_result_run = None
            else:
                raise HttpError(422, "BAD_MODULE")
        return {"cleared": True}

    @app.exception_handler(Exception)
    async def internal_error(request: Request, exc: Exception):
        return JSONResponse({"error": {"code": "INTERNAL_ERROR"}}, status_code=500)

    # ---- config module endpoints ----

    @app.post("/api/config/analyze")
    async def config_analyze(request: Request, lang: str = "zh-CN"):
        host = _check_host(request)
        session = _session_from_cookie(request)
        _require_exact_origin(request, host)
        _require_csrf(request, session)
        _check_content_type(request, "application/octet-stream")
        input_format = request.headers.get("x-input-format")
        if input_format not in ("json", "toml"):
            raise HttpError(422, "BAD_INPUT_FORMAT")
        if lang not in LANGUAGES:
            raise HttpError(422, "BAD_LANGUAGE")
        # C02: capture the generation BEFORE reading the body so a clear()
        # that arrives while the request is still streaming is carried
        # through analysis to landing.
        with session.lock:
            if session.in_flight >= MAX_CONCURRENT_ANALYSES:
                raise HttpError(429, "TOO_MANY_ANALYSES")
            session.in_flight += 1
            generation = session.generation["config"]
        try:
            body = await _read_body_limited(request)
            return _run_config_analysis(session, generation, body, input_format,
                                        lang, "current", projection_limit)
        finally:
            with session.lock:
                session.in_flight -= 1

    @app.post("/api/config/demo")
    async def config_demo(request: Request):
        host = _check_host(request)
        session = _session_from_cookie(request)
        _require_exact_origin(request, host)
        _require_csrf(request, session)
        _check_content_type(request, "application/json")
        payload = await _read_json_payload(request)
        case_id = payload.get("case_id")
        lang = payload.get("lang")
        # Fixed 4xx for malformed case ids (never a 500).
        if not isinstance(case_id, str):
            raise HttpError(422, "BAD_JSON")
        if case_id not in {case["case_id"] for case in CONFIG_DEMO_CASES}:
            raise HttpError(404, "NO_CASE")
        if lang not in LANGUAGES:
            raise HttpError(422, "BAD_LANGUAGE")
        raw, input_format = config_demo_bytes(case_id)
        assert raw is not None
        with session.lock:
            generation = session.generation["config"]
        return _run_config_analysis(session, generation, raw, input_format,
                                    lang, "reference", projection_limit)

    # ---- stream module endpoints ----

    @app.post("/api/stream/analyze")
    async def stream_analyze(request: Request, lang: str = "zh-CN", slot: str = "current",
                             run_id: str = ""):
        host = _check_host(request)
        session = _session_from_cookie(request)
        _require_exact_origin(request, host)
        _require_csrf(request, session)
        _check_content_type(request, "application/octet-stream")
        if lang not in LANGUAGES:
            raise HttpError(422, "BAD_LANGUAGE")
        if slot not in ("current", "baseline", "candidate"):
            raise HttpError(422, "BAD_SLOT")
        # C02: capture the generation BEFORE reading the body (see above).
        # Compare-mode sides guard their own generation AND must name the
        # server-issued run they belong to (E03): a stale run_id from an
        # older prepare can never land over a newer run's side.
        with session.lock:
            compare_mode = slot in ("baseline", "candidate")
            if compare_mode:
                if not run_id or session.compare_run_id != run_id:
                    raise HttpError(409, "STALE_ANALYSIS")
            if session.in_flight >= MAX_CONCURRENT_ANALYSES:
                raise HttpError(429, "TOO_MANY_ANALYSES")
            session.in_flight += 1
            generation = (
                session.compare_generation
                if compare_mode
                else session.generation["stream"]
            )
        try:
            body = await _read_body_limited(request)
            result = _run_stream_analysis(session, generation, body, lang,
                                        slot, projection_limit,
                                        compare_guard=compare_mode)
            if compare_mode:
                with session.lock:
                    session.compare_side_run[slot] = run_id
                    session.compare_side_result[slot] = result["result_id"]
            return result
        finally:
            with session.lock:
                session.in_flight -= 1

    @app.post("/api/stream/compare")
    async def stream_compare(request: Request):
        host = _check_host(request)
        session = _session_from_cookie(request)
        _require_exact_origin(request, host)
        _require_csrf(request, session)
        _check_content_type(request, "application/json")
        payload = await _read_json_payload(request)
        baseline_id = payload.get("baseline")
        candidate_id = payload.get("candidate")
        lang = payload.get("lang")
        run_id = payload.get("run_id")
        if not isinstance(baseline_id, str) or not isinstance(candidate_id, str):
            raise HttpError(422, "BAD_JSON")
        if not isinstance(run_id, str) or not run_id:
            raise HttpError(422, "BAD_JSON")
        if lang not in LANGUAGES:
            raise HttpError(422, "BAD_LANGUAGE")
        # E03: the comparison belongs to ONE server-issued run. Both sides
        # must be results of THIS run; a stale run_id (older prepare) or an
        # inter-generational clear invalidates the whole comparison.
        with session.lock:
            generation = session.compare_generation
            if session.compare_run_id != run_id:
                raise HttpError(409, "STALE_ANALYSIS")
            if (
                session.compare_side_run.get("baseline") != run_id
                or session.compare_side_run.get("candidate") != run_id
            ):
                raise HttpError(409, "STALE_ANALYSIS")
            # E04: the caller must hand back exactly the side results this run
            # landed — a result id from any other stream slot is refused.
            if (
                session.compare_side_result.get("baseline") != baseline_id
                or session.compare_side_result.get("candidate") != candidate_id
            ):
                raise HttpError(409, "STALE_ANALYSIS")
        baseline_module, baseline_slot = _owned_result(session, baseline_id)
        candidate_module, candidate_slot = _owned_result(session, candidate_id)
        if baseline_module != "stream" or candidate_module != "stream":
            raise HttpError(404, "NO_RESULT")
        compare_core = compare_projections(baseline_slot.core, candidate_slot.core)
        result = _land_result(session, "stream", generation, "compare",
                              compare_core, lang, projection_limit, compare_guard=True)
        with session.lock:
            session.compare_result_run = run_id
        return result

    @app.post("/api/stream/compare/prepare")
    async def stream_compare_prepare(request: Request):
        host = _check_host(request)
        session = _session_from_cookie(request)
        _require_exact_origin(request, host)
        _require_csrf(request, session)
        _check_content_type(request, "application/json")
        await _read_json_payload(request)
        # E03: compare identity is issued by the server. Starting a run
        # immediately revokes everything compare-mode landed before it (old
        # results and old sides die NOW, before the new run starts), so the
        # identity is stable across page refreshes and never re-counted
        # client-side. A confirmed single-stream result stays untouched.
        with session.lock:
            session.compare_generation += 1
            session.compare_run_id = secrets.token_urlsafe(16)
            session.compare_side_run.clear()
            session.compare_side_result.clear()
            session.compare_result_run = None
            for slot_name in ("baseline", "candidate", "compare"):
                session.slots["stream"].pop(slot_name, None)
            run_id = session.compare_run_id
        return {"run_id": run_id}

    @app.post("/api/stream/compare/cancel")
    async def stream_compare_cancel(request: Request):
        host = _check_host(request)
        session = _session_from_cookie(request)
        _require_exact_origin(request, host)
        _require_csrf(request, session)
        _check_content_type(request, "application/json")
        payload = await _read_json_payload(request)
        run_id = payload.get("run_id")
        if not isinstance(run_id, str) or not run_id:
            raise HttpError(422, "BAD_JSON")
        # E03: cancelling a run revokes whatever that run landed AND marks the
        # run dead server-side — in-flight results of it can never land, even
        # if the client never receives this response. Cancelling an OLDER run
        # touches only that run's slots; a newer comparison survives.
        with session.lock:
            if session.compare_side_run.get("baseline") == run_id:
                session.slots["stream"].pop("baseline", None)
                session.compare_side_run.pop("baseline", None)
                session.compare_side_result.pop("baseline", None)
            if session.compare_side_run.get("candidate") == run_id:
                session.slots["stream"].pop("candidate", None)
                session.compare_side_run.pop("candidate", None)
                session.compare_side_result.pop("candidate", None)
            if session.compare_result_run == run_id:
                session.slots["stream"].pop("compare", None)
                session.compare_result_run = None
            if session.compare_run_id == run_id:
                session.compare_generation += 1
                session.compare_run_id = None
        return {"cancelled": True}

    @app.post("/api/stream/demo")
    async def stream_demo(request: Request):
        host = _check_host(request)
        session = _session_from_cookie(request)
        _require_exact_origin(request, host)
        _require_csrf(request, session)
        _check_content_type(request, "application/json")
        payload = await _read_json_payload(request)
        case_id = payload.get("case_id")
        lang = payload.get("lang")
        if not isinstance(case_id, str):
            raise HttpError(422, "BAD_JSON")
        if case_id not in STREAM_DEMO_BYTES:
            raise HttpError(404, "NO_CASE")
        if lang not in LANGUAGES:
            raise HttpError(422, "BAD_LANGUAGE")
        with session.lock:
            generation = session.generation["stream"]
        return _run_stream_analysis(session, generation, STREAM_DEMO_BYTES[case_id],
                                    lang, "reference", projection_limit)

    if _STATIC_DIR.is_dir():
        app.mount("/", StaticFiles(directory=str(_STATIC_DIR), html=True), name="static")

    return app


# ---- analysis runners (R05: generation-guarded landing) ----


def _run_config_analysis(session, generation: int, raw: bytes,
                         input_format: str, language: str,
                         slot_name: str, projection_limit: int):
    if len(raw) > CONFIG_MAX_FILE_BYTES:
        core: dict = {"error": "INPUT_TOO_LARGE"}
    else:
        try:
            core = config_analyze_bytes(raw, input_format)
        except (ConfigInputRejected, StreamInputRejected) as rejected:
            core = {"error": rejected.code}
        except RecursionError:  # defensive: bounded pre-scan should prevent this
            core = {"error": "LIMIT_EXCEEDED"}
    return _land_result(session, "config", generation, slot_name, core,
                        language, projection_limit)


def _run_stream_analysis(session, generation: int, raw: bytes, language: str,
                         slot_name: str, projection_limit: int,
                         compare_guard: bool = False):
    if len(raw) > STREAM_MAX_INPUT_BYTES:
        core: dict = {"error": "INPUT_TOO_LARGE"}
    else:
        try:
            core = stream_analyze_bytes(raw)
        except (ConfigInputRejected, StreamInputRejected) as rejected:
            core = {"error": rejected.code}
        except RecursionError:  # defensive: event parsing must never traceback
            core = {"error": "LIMIT_EXCEEDED"}
    return _land_result(session, "stream", generation, slot_name, core,
                        language, projection_limit, compare_guard=compare_guard)


def _land_result(session, module: str, generation: int, slot_name: str,
                 core: dict, language: str, projection_limit: int,
                 compare_guard: bool = False):
    size = estimate_size({"core": core})
    with session.lock:
        current = session.compare_generation if compare_guard else session.generation[module]
        if current != generation:
            # R05: a clear()/revoke happened while this analysis was in
            # flight; the stale result must not land in a slot.
            raise HttpError(409, "STALE_ANALYSIS")
        total = sum(
            slot.bytes
            for m in MODULES
            for slot in session.slots[m].values()
        )
        if total + size > projection_limit:
            raise HttpError(413, "PROJECTION_LIMIT")
        session.revision += 1
        revision = session.revision
        result_id = secrets.token_urlsafe(16)
        session.slots[module][slot_name] = _make_slot(result_id, core, revision, size)
        slot_cap = (
            MAX_SLOTS_PER_MODULE_STREAM if module == "stream" else MAX_SLOTS_PER_MODULE
        )
        while len(session.slots[module]) > slot_cap:
            oldest = min(
                session.slots[module],
                key=lambda k: session.slots[module][k].revision,
            )
            del session.slots[module][oldest]
    card = _render_slot_card(core, module, language, "json")
    return {
        "result_id": result_id,
        "revision": revision,
        "slot": slot_name,
        "module": module,
        "result": card,
    }


def _make_slot(result_id: str, core: dict, revision: int, size: int):
    from .sessions import _Slot

    return _Slot(result_id, core, revision, size)


def _render_slot_card(core: dict, module: str, lang: str, output_format: str):
    """Renders a stored slot core; comparison cores render as comparisons."""
    if module == "config":
        return render_config_card(core, lang, output_format)
    if isinstance(core, dict) and core.get("kind") == "stream-compare":
        return render_compare_card(core, lang, output_format)
    return render_stream_card(core, lang, output_format)
