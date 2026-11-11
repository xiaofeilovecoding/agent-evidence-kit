"""Normal-vs-abnormal stream comparison (ADOPTION E1).

Compares TWO safe projection cores produced by the existing chat-completions
analysis pipeline. The comparison reads only the projections — never raw
stream bytes, event data, generated text, tool arguments, commands,
addresses, session ids, timestamps or source file names. Unknown
finish_reason text never enters a comparison: it is bucketed to the
"other" category upstream in the diagnostics projection.

Differences are OBSERVATIONS about the two captured streams only; they do
not prove anything about upstream root causes.
"""
from __future__ import annotations

from . import PROFILE

COMPARE_SCHEMA_VERSION = 1

# Controlled finish_reason categories. Recognized chat-completions values
# keep their names; an unrecognized value was already bucketed to "other"
# by the diagnostics projection; no finish observed maps to "none".
FINISH_ENUM = (
    "none",
    "stop",
    "tool_calls",
    "function_call",
    "length",
    "content_filter",
    "other",
)

# Fixed difference field order: terminal state first, everything else after.
DIFF_FIELDS = (
    "terminal",
    "verdict",
    "finish_reason",
    "done_seen",
    "terminal_event_index",
    "diagnostic_codes",
    "event_count",
)

NOTE = (
    "observed differences between the two captured streams only; "
    "this comparison does not prove upstream root causes"
)


def side_projection(core: dict) -> dict:
    """Reduces one single-stream projection to its comparison-safe shape.

    An error core ({"error": code}) projects as its input-error terminal.
    """
    if isinstance(core, dict) and "error" in core:
        return {
            "verdict": "INVALID_INPUT",
            "terminal": core["error"],
            "finish_reason": "none",
            "done_seen": False,
            "finish_seen": False,
            "terminal_event_index": None,
            "event_count": 0,
            "diagnostic_codes": [
                {"code": core["error"], "severity": "error", "event_index": None}
            ],
        }
    timeline = core.get("timeline", [])
    finish_reason = "none"
    terminal_event_index = None
    done_index = None
    for entry in timeline:
        # An unrecognized finish_reason was bucketed to "other" upstream;
        # its raw text never reaches this projection.
        enum = entry.get("finish_enum")
        if enum and finish_reason == "none":
            finish_reason = enum if enum in FINISH_ENUM else "other"
        if entry.get("kind") == "finish" and terminal_event_index is None:
            terminal_event_index = entry.get("index")
        if entry.get("kind") == "done" and done_index is None:
            done_index = entry.get("index")
    if terminal_event_index is None:
        # a [DONE] frame is terminal evidence too when no finish was observed
        terminal_event_index = done_index
    return {
        "verdict": core.get("verdict"),
        "terminal": core.get("primary_finding"),
        "finish_reason": finish_reason,
        "done_seen": bool(core.get("summary", {}).get("saw_done")),
        "finish_seen": bool(core.get("summary", {}).get("saw_finish")),
        "terminal_event_index": terminal_event_index,
        "event_count": core.get("summary", {}).get("event_count", 0),
        "diagnostic_codes": [
            {"code": f["code"], "severity": f["severity"], "event_index": f["event_index"]}
            for f in core.get("findings", [])
        ],
    }


def _diagnostic_codes(side: dict) -> list[str]:
    return [d["code"] for d in side["diagnostic_codes"]]


def compare_projections(baseline_core: dict, candidate_core: dict) -> dict:
    """Builds the versioned comparison from two safe projection cores.

    The result carries no raw material from either side; ordering is fixed
    and identical inputs always produce identical output.
    """
    baseline = side_projection(baseline_core)
    candidate = side_projection(candidate_core)

    differences: list[dict] = []
    same: list[str] = []
    for field in DIFF_FIELDS:
        if field == "diagnostic_codes":
            a = _diagnostic_codes(baseline)
            b = _diagnostic_codes(candidate)
        else:
            a = baseline.get(field)
            b = candidate.get(field)
        if a != b:
            differences.append({"field": field, "baseline": a, "candidate": b})
        else:
            same.append(field)

    return {
        "schema_version": COMPARE_SCHEMA_VERSION,
        "kind": "stream-compare",
        "profile": PROFILE,
        "baseline": baseline,
        "candidate": candidate,
        "differences": differences,
        "same_fields": same,
        "note": NOTE,
    }
