"""Pure chat-completions-v1 profile rules: observations, findings, timeline.

Receives only dispatched SSE events (field names + data lines) from the
parser. Every exported value is a fixed constant or a structural boolean;
raw values (ids, models, text, tool arguments, usage numbers, error
bodies, unknown keys) are never included.
"""
from __future__ import annotations

import json

from . import PROFILE
from .parsers import (
    MAX_EVENT_DATA_BYTES,
    MAX_INPUT_BYTES,
    MAX_JSON_DEPTH,
    MAX_LINE_BYTES,
    MAX_DATA_EVENTS,
)

NORMAL_FINISH = ("stop", "tool_calls", "function_call")
SUPPORTED_FINISH = NORMAL_FINISH + ("length", "content_filter")

FINISH_KIND = {
    "stop": "normal",
    "tool_calls": "normal",
    "function_call": "normal",
    "length": "limit",
    "content_filter": "filter",
}

SEVERITY = {
    "NORMAL_TERMINATION": "info",
    "FINISH_WITHOUT_DONE": "warning",
    "DONE_WITHOUT_FINISH": "warning",
    "NO_TERMINAL_EVIDENCE": "warning",
    "NO_DATA": "warning",
    "UNTERMINATED_EVENT": "warning",
    "LIMIT_STOP": "warning",
    "FILTER_STOP": "warning",
    "UPSTREAM_ERROR": "warning",
    "DATA_AFTER_DONE": "warning",
    "UNSUPPORTED_PROFILE": "error",
    "UNSUPPORTED_EVENT": "error",
    "UNSUPPORTED_FINISH": "error",
    "INVALID_EVENT_JSON": "error",
    "DUPLICATE_KEY": "error",
    "LIMIT_EXCEEDED": "error",
}

INPUT_ERROR_SEVERITY = {
    "INPUT_UNREADABLE": "error",
    "INPUT_TOO_LARGE": "error",
    "LIMIT_EXCEEDED": "error",
    "INVALID_ENCODING": "error",
}

EXIT_CODES = {
    "NORMAL_TERMINATION": 0,
    "FINISH_WITHOUT_DONE": 1,
    "DONE_WITHOUT_FINISH": 1,
    "NO_TERMINAL_EVIDENCE": 1,
    "NO_DATA": 1,
    "UNTERMINATED_EVENT": 1,
    "LIMIT_STOP": 1,
    "FILTER_STOP": 1,
    "UPSTREAM_ERROR": 1,
    "DATA_AFTER_DONE": 1,
    "UNSUPPORTED_PROFILE": 2,
    "UNSUPPORTED_EVENT": 2,
    "UNSUPPORTED_FINISH": 2,
    "INVALID_EVENT_JSON": 2,
    "DUPLICATE_KEY": 2,
    "LIMIT_EXCEEDED": 2,
    "INVALID_ENCODING": 2,
    "INPUT_UNREADABLE": 2,
    "INPUT_TOO_LARGE": 2,
}

VERDICT_PRIORITY = [
    # Exit-2 causes first (deterministic primary pick), then exit-1.
    "LIMIT_EXCEEDED",
    "UNSUPPORTED_PROFILE",
    "UNSUPPORTED_EVENT",
    "UNSUPPORTED_FINISH",
    "INVALID_EVENT_JSON",
    "DUPLICATE_KEY",
    "UPSTREAM_ERROR",
    "DATA_AFTER_DONE",
    "UNTERMINATED_EVENT",
    "LIMIT_STOP",
    "FILTER_STOP",
    "FINISH_WITHOUT_DONE",
    "DONE_WITHOUT_FINISH",
    "NO_TERMINAL_EVIDENCE",
    "NO_DATA",
    "NORMAL_TERMINATION",
]


class _DuplicateKey(Exception):
    pass


def _object_pairs_no_duplicates(pairs):
    seen = set()
    for key, _value in pairs:
        if key in seen:
            raise _DuplicateKey
        seen.add(key)
    return dict(pairs)


def _reject_constant(name: str):
    raise ValueError(name)


def container_depth(value: object) -> int:
    """Iterative maximum container depth (dict/list nesting).

    Deliberately non-recursive so a deeply nested but parseable event
    cannot crash the checker itself (R01).
    """
    max_depth = 0
    stack: list[tuple[object, int]] = [(value, 0)]
    while stack:
        node, depth = stack.pop()
        if isinstance(node, dict):
            children = node.values()
        elif isinstance(node, list):
            children = node
        else:
            continue
        depth += 1
        if depth > max_depth:
            max_depth = depth
        for child in children:
            stack.append((child, depth))
    return max_depth


class _Obs:
    __slots__ = (
        "index",
        "kind",
        "finish_kind",
        "has_content",
        "has_tool_calls",
        "codes",
    )

    def __init__(self, index: int, kind: str):
        self.index = index
        self.kind = kind  # chunk/finish/usage/done/error/unsupported
        self.finish_kind: str | None = None
        self.has_content = False
        self.has_tool_calls = False
        self.codes: list[str] = []


class _Analysis:
    def __init__(self):
        self.timeline: list[_Obs] = []
        self.findings: dict[tuple[int | None, str], str] = {}
        self.usage_seen = False

    def add(self, index: int | None, code: str) -> None:
        self.findings.setdefault((index, code), SEVERITY[code])
        if index is not None and 0 <= index < len(self.timeline):
            if code not in self.timeline[index].codes:
                self.timeline[index].codes.append(code)

    def parse_event_json(self, data: str, index: int) -> object:
        try:
            parsed = json.loads(
                data,
                object_pairs_hook=_object_pairs_no_duplicates,
                parse_constant=_reject_constant,
            )
        except _DuplicateKey:
            self.add(index, "DUPLICATE_KEY")
            return None
        except RecursionError:
            # Deeply nested event JSON crashes the recursive C scanner
            # before the depth check runs; report the frozen limit instead
            # of letting a traceback escape (R01).
            self.add(index, "LIMIT_EXCEEDED")
            return None
        except ValueError:
            self.add(index, "INVALID_EVENT_JSON")
            return None
        if container_depth(parsed) > MAX_JSON_DEPTH:
            self.add(index, "LIMIT_EXCEEDED")
            return None
        return parsed

    def classify_chunk(self, obs: _Obs, parsed: object) -> None:
        if not isinstance(parsed, dict):
            self.add(obs.index, "UNSUPPORTED_PROFILE")
            obs.kind = "unsupported"
            return
        if parsed.get("error") is not None:
            self.add(obs.index, "UPSTREAM_ERROR")
            obs.kind = "error"
            return
        choices = parsed.get("choices")
        if not isinstance(choices, list) or len(choices) > 1:
            self.add(obs.index, "UNSUPPORTED_PROFILE")
            obs.kind = "unsupported"
            return
        if isinstance(parsed.get("usage"), dict):
            self.usage_seen = True
            has_usage = True
        else:
            has_usage = False
        if len(choices) == 0:
            if has_usage:
                obs.kind = "usage"  # usage-only event: allowed with usage object
                return
            self.add(obs.index, "UNSUPPORTED_PROFILE")
            obs.kind = "unsupported"
            return
        choice = choices[0]
        if not isinstance(choice, dict):
            self.add(obs.index, "UNSUPPORTED_PROFILE")
            obs.kind = "unsupported"
            return
        choice_index = choice.get("index", 0)
        if isinstance(choice_index, bool) or not isinstance(choice_index, int):
            self.add(obs.index, "UNSUPPORTED_PROFILE")
            obs.kind = "unsupported"
            return
        if choice_index != 0:
            self.add(obs.index, "UNSUPPORTED_PROFILE")
            obs.kind = "unsupported"
            return
        delta = choice.get("delta")
        if delta is None:
            delta = {}
        if not isinstance(delta, dict):
            self.add(obs.index, "UNSUPPORTED_PROFILE")
            obs.kind = "unsupported"
            return
        if delta.get("content") is not None:
            obs.has_content = True
        if delta.get("tool_calls") is not None:
            obs.has_tool_calls = True
        finish = choice.get("finish_reason")
        if finish is None:
            obs.kind = "chunk"
            return
        if not isinstance(finish, str) or finish not in SUPPORTED_FINISH:
            self.add(obs.index, "UNSUPPORTED_FINISH")
            obs.kind = "unsupported"
            return
        obs.kind = "finish"
        obs.finish_kind = FINISH_KIND[finish]


def analyze_events(events, unterminated_tail: bool) -> dict:
    """Produce the language-neutral projection core for dispatched events."""
    analysis = _Analysis()

    for index, event in enumerate(events):
        data = "\n".join(event.data_parts)
        event_type = event.event_type
        if event_type == "error":
            obs = _Obs(index, "error")
            analysis.timeline.append(obs)
            analysis.add(index, "UPSTREAM_ERROR")
            continue
        if event_type not in (None, "message"):
            obs = _Obs(index, "unsupported")
            analysis.timeline.append(obs)
            analysis.add(index, "UNSUPPORTED_EVENT")
            continue
        if data == "[DONE]":
            analysis.timeline.append(_Obs(index, "done"))
            continue
        obs = _Obs(index, "chunk")
        analysis.timeline.append(obs)
        parsed = analysis.parse_event_json(data, index)
        if parsed is None:
            obs.kind = "unsupported"
            continue
        analysis.classify_chunk(obs, parsed)

    saw_done = False
    done_index = -1
    normal_finish = False
    non_normal_finish = False
    for obs in analysis.timeline:
        if saw_done and obs.index > done_index:
            # Any dispatched data after the first DONE, including a
            # duplicate DONE, is residue.
            analysis.add(obs.index, "DATA_AFTER_DONE")
        if obs.kind == "done" and not saw_done:
            saw_done = True
            done_index = obs.index
            continue
        if obs.kind == "finish":
            if obs.finish_kind == "normal":
                normal_finish = True
            elif obs.finish_kind in ("limit", "filter"):
                non_normal_finish = True
                code = "LIMIT_STOP" if obs.finish_kind == "limit" else "FILTER_STOP"
                analysis.add(obs.index, code)

    if unterminated_tail:
        analysis.add(
            len(analysis.timeline) - 1 if analysis.timeline else None,
            "UNTERMINATED_EVENT",
        )
    if not analysis.timeline:
        analysis.add(None, "NO_DATA")

    saw_finish = normal_finish or non_normal_finish
    error_codes = sorted(
        code for (_, code), severity in analysis.findings.items() if severity == "error"
    )
    if error_codes:
        primary = min(error_codes, key=VERDICT_PRIORITY.index)
        verdict = "INVALID_INPUT"
    else:
        candidates = []
        if not analysis.timeline:
            candidates.append("NO_DATA")
        else:
            if any(code == "UNTERMINATED_EVENT" for (_, code) in analysis.findings):
                candidates.append("UNTERMINATED_EVENT")
            if any(code == "UPSTREAM_ERROR" for (_, code) in analysis.findings):
                candidates.append("UPSTREAM_ERROR")
            if any(code == "DATA_AFTER_DONE" for (_, code) in analysis.findings):
                candidates.append("DATA_AFTER_DONE")
            if non_normal_finish:
                candidates.append(
                    "LIMIT_STOP" if any(c == "LIMIT_STOP" for _, c in analysis.findings) else "FILTER_STOP"
                )
            if saw_done and normal_finish and not non_normal_finish:
                candidates.append("NORMAL_TERMINATION")
            elif saw_done:
                candidates.append("DONE_WITHOUT_FINISH")
            elif saw_finish:
                candidates.append("FINISH_WITHOUT_DONE")
            else:
                candidates.append("NO_TERMINAL_EVIDENCE")
        primary = min(candidates, key=VERDICT_PRIORITY.index)
        verdict = (
            "NORMAL_TERMINATION" if primary == "NORMAL_TERMINATION" else "NEEDS_REVIEW"
        )

    ordered = []
    for index, code in sorted(
        analysis.findings, key=lambda k: (k[0] is None, k[0] if k[0] is not None else 0, k[1])
    ):
        ordered.append(
            {
                "code": code,
                "severity": analysis.findings[(index, code)],
                "event_index": index,
            }
        )
    if primary not in {f["code"] for f in ordered}:
        ordered.insert(
            0,
            {"code": primary, "severity": SEVERITY[primary], "event_index": None},
        )

    return {
        "profile": PROFILE,
        "verdict": verdict,
        "primary_finding": primary,
        "summary": {
            "event_count": len(analysis.timeline),
            "saw_finish": saw_finish,
            "saw_done": saw_done,
            "usage_seen": analysis.usage_seen,
        },
        "findings": ordered,
        "timeline": [
            {
                "index": o.index,
                "kind": o.kind,
                "finish_kind": o.finish_kind,
                "has_content": o.has_content,
                "has_tool_calls": o.has_tool_calls,
                "diagnostic_codes": list(o.codes),
            }
            for o in analysis.timeline
        ],
    }
