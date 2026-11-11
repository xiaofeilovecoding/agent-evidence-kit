"""Renderers: projection core in, localized JSON/Markdown out.

Renderers only accept the projection model; they never receive raw
stream text. All explanation strings are fixed constants below.
"""
from __future__ import annotations

from ..next_steps import NEXT_STEPS_SCHEMA_VERSION, next_steps_for
from . import PROFILE
from .compare import COMPARE_SCHEMA_VERSION, NOTE, _diagnostic_codes

SCHEMA_VERSION = 2
LANGUAGES = ("zh-CN", "en")
OUTPUT_FORMATS = ("json", "md")

EXPLANATIONS = {
    "NORMAL_TERMINATION": {
        "zh-CN": "观察到正常finish且收到[DONE]：本profile下结束证据完整。这不代表答案正确或完整。",
        "en": "A normal finish was observed and [DONE] was received: terminal evidence is complete for this profile. This does not prove the answer is correct or complete.",
    },
    "FINISH_WITHOUT_DONE": {
        "zh-CN": "观察到finish但没有[DONE]：应用层结束标记缺失。请核对网关/SDK是否吞掉终止帧，不要直接断言数据丢失。",
        "en": "A finish was observed but no [DONE]: the application-level termination marker is missing. Check whether your gateway/SDK dropped the terminal frame; do not assume data loss.",
    },
    "DONE_WITHOUT_FINISH": {
        "zh-CN": "收到[DONE]但没有finish_reason：连接收尾正常，但供应商未给出结束原因。",
        "en": "[DONE] was received but no finish_reason: the stream closed normally, yet the provider never reported why it stopped.",
    },
    "NO_TERMINAL_EVIDENCE": {
        "zh-CN": "有数据事件但既无finish也无[DONE]：缺少结束证据。EOF本身不能证明供应商中断的原因。",
        "en": "Data events exist but neither a finish nor [DONE]: terminal evidence is missing. EOF alone cannot tell you why the provider stopped.",
    },
    "NO_DATA": {
        "zh-CN": "没有可分派的数据事件（空流或仅有注释/心跳）。",
        "en": "No dispatchable data events (empty stream or only comments/heartbeats).",
    },
    "UNTERMINATED_EVENT": {
        "zh-CN": "流在事件中途结束：最后一个data块缺少空行分派，其内容不计为已接收事件。",
        "en": "The stream ends mid-event: the trailing data block was never dispatched by a blank line, so it does not count as received.",
    },
    "LIMIT_STOP": {
        "zh-CN": "finish_reason=length：生成因长度上限停止，属于非正常结束证据。",
        "en": "finish_reason=length: generation stopped at a length limit; this is non-normal terminal evidence.",
    },
    "FILTER_STOP": {
        "zh-CN": "finish_reason=content_filter：生成被内容过滤停止，属于非正常结束证据。",
        "en": "finish_reason=content_filter: generation stopped by a content filter; this is non-normal terminal evidence.",
    },
    "UPSTREAM_ERROR": {
        "zh-CN": "流中包含上游错误事件（错误正文不回显）。",
        "en": "The stream contains an upstream error event (the error body is never echoed).",
    },
    "DATA_AFTER_DONE": {
        "zh-CN": "[DONE]之后仍收到已分派的数据事件：终止帧之后出现残留数据。",
        "en": "Dispatched data arrived after [DONE]: residual data follows the terminal frame.",
    },
    "UNSUPPORTED_PROFILE": {
        "zh-CN": "事件JSON不符合chat-completions-v1支持的结构（如多choices、非0 index、未知provider字段形态），本工具不猜测兼容。",
        "en": "The event JSON does not match the supported chat-completions-v1 shape (e.g. multiple choices, non-zero index, unknown provider structure); this tool does not guess compatibility.",
    },
    "UNSUPPORTED_EVENT": {
        "zh-CN": "出现本profile不支持的SSE event类型（其值不回显）。",
        "en": "An SSE event type unsupported by this profile was seen (its value is not echoed).",
    },
    "UNSUPPORTED_FINISH": {
        "zh-CN": "finish_reason不是受支持的枚举值（不回显原值）。",
        "en": "finish_reason is not one of the supported values (the raw value is not echoed).",
    },
    "INVALID_EVENT_JSON": {
        "zh-CN": "已分派的事件data不是合法JSON。",
        "en": "A dispatched event's data is not valid JSON.",
    },
    "DUPLICATE_KEY": {
        "zh-CN": "事件JSON存在重复键，已拒绝解析以避免歧义。",
        "en": "The event JSON contains duplicate keys; parsing was rejected to avoid ambiguity.",
    },
    "LIMIT_EXCEEDED": {
        "zh-CN": "超出冻结的解析限制（8MiB输入、128KiB行、256KiB事件data、10000事件、JSON深度16）。",
        "en": "A frozen parse limit was exceeded (8MiB input, 128KiB line, 256KiB event data, 10000 events, JSON depth 16).",
    },
    "INVALID_ENCODING": {
        "zh-CN": "输入不是有效UTF-8（允许一个BOM）。",
        "en": "The input is not valid UTF-8 (a single leading BOM is allowed).",
    },
    "INPUT_UNREADABLE": {
        "zh-CN": "无法读取输入文件（不存在、无权限或不是普通文件）。",
        "en": "The input file could not be read (missing, no permission, or not a regular file).",
    },
    "INPUT_TOO_LARGE": {
        "zh-CN": "输入超过8MiB上限。",
        "en": "The input exceeds the 8MiB limit.",
    },
}

LIMITS_NOTE = {
    "zh-CN": "固定局限：本工具只观察结束证据，不推断真实时间/吞吐量，不验证供应商兼容性或认证，无法判断答案正确性。",
    "en": "Fixed limits: this tool observes terminal evidence only; it does not infer real timing/throughput, provider compatibility, or authentication, and cannot judge answer correctness.",
}

_NEXT_LABEL = {"zh-CN": "下一步", "en": "Next step"}
_CANNOT_PROVE_LABEL = {"zh-CN": "不能证明", "en": "Does not prove"}

_VERDICT_LABELS = {
    "NORMAL_TERMINATION": {"zh-CN": "正常结束", "en": "Normal termination"},
    "NEEDS_REVIEW": {"zh-CN": "需要复核", "en": "Needs review"},
    "INVALID_INPUT": {"zh-CN": "输入无效", "en": "Invalid input"},
}

_SEVERITY_LABELS = {
    "warning": {"zh-CN": "警告", "en": "warning"},
    "error": {"zh-CN": "错误", "en": "error"},
    "info": {"zh-CN": "提示", "en": "info"},
}

_KIND_LABELS = {
    "chunk": {"zh-CN": "chunk", "en": "chunk"},
    "finish": {"zh-CN": "finish", "en": "finish"},
    "usage": {"zh-CN": "usage", "en": "usage"},
    "done": {"zh-CN": "done", "en": "done"},
    "error": {"zh-CN": "error", "en": "error"},
    "unsupported": {"zh-CN": "unsupported", "en": "unsupported"},
}


def _explanation(code: str, language: str) -> str:
    return EXPLANATIONS[code][language]


def render_card(core: dict, language: str, output_format: str) -> dict | str:
    if output_format == "json":
        return _render_json(core, language)
    return _render_markdown(core, language)


def _render_json(core: dict, language: str) -> dict:
    card = {
        "schema_version": SCHEMA_VERSION,
        "next_steps_schema_version": NEXT_STEPS_SCHEMA_VERSION,
        "profile": PROFILE,
        "language": language,
        "verdict": None,
        "summary": None,
        "findings": [],
        "timeline": [],
    }
    if "error" in core:
        code = core["error"]
        card["verdict"] = "INVALID_INPUT"
        card["summary"] = {
            "event_count": 0,
            "saw_finish": False,
            "saw_done": False,
            "usage_seen": False,
        }
        card["findings"] = [
            {"code": code, "severity": "error", "event_index": None,
             "explanation": _explanation(code, language),
             "next_steps": next_steps_for(code, language)}
        ]
        card["next_steps"] = next_steps_for(code, language)
        return card
    card["verdict"] = core["verdict"]
    card["summary"] = core["summary"]
    card["findings"] = [
        {
            "code": f["code"],
            "severity": f["severity"],
            "event_index": f["event_index"],
            "explanation": _explanation(f["code"], language),
            "next_steps": next_steps_for(f["code"], language),
        }
        for f in core["findings"]
    ]
    primary = core["findings"][0]["code"] if core["findings"] else None
    card["next_steps"] = next_steps_for(primary, language) if primary else None
    card["timeline"] = core["timeline"]
    return card


def _render_markdown(core: dict, language: str) -> str:
    is_zh = language == "zh-CN"
    lines = []
    lines.append("# Stream End Evidence Card" if not is_zh else "# 流结束证据卡")
    lines.append("")
    lines.append(LIMITS_NOTE[language])
    lines.append("")
    if "error" in core:
        code = core["error"]
        lines.append(f"- {code}: {_explanation(code, language)}")
        lines.append("")
        return "\n".join(lines)
    verdict = _VERDICT_LABELS[core["verdict"]][language]
    summary = core["summary"]
    lines.append(f"**{verdict}**")
    lines.append("")
    if is_zh:
        lines.append(
            f"- finish证据: {'有' if summary['saw_finish'] else '无'}"
            f"（正常/limit/filter见findings）"
        )
        lines.append(f"- DONE证据: {'有' if summary['saw_done'] else '无'}")
        lines.append(f"- 事件数: {summary['event_count']}")
        lines.append(f"- usage出现: {'是' if summary['usage_seen'] else '否'}")
    else:
        lines.append(f"- finish evidence: {'yes' if summary['saw_finish'] else 'none'}")
        lines.append(f"- [DONE] evidence: {'yes' if summary['saw_done'] else 'none'}")
        lines.append(f"- events: {summary['event_count']}")
        lines.append(f"- usage seen: {'yes' if summary['usage_seen'] else 'no'}")
    lines.append("")
    for finding in core["findings"]:
        where = "" if finding["event_index"] is None else f" @event{finding['event_index']}"
        severity = _SEVERITY_LABELS[finding["severity"]][language]
        lines.append(
            f"- [{severity}] {finding['code']}{where}: "
            f"{_explanation(finding['code'], language)}"
        )
        steps = next_steps_for(finding["code"], language)
        lines.append(f"  - {_NEXT_LABEL[language]}: {steps['next_steps']}")
        lines.append(
            f"  - {_CANNOT_PROVE_LABEL[language]}: {steps['does_not_prove']}"
        )
    lines.append("")
    if is_zh:
        lines.append("## 事件序列（顺序索引，非真实时间）")
    else:
        lines.append("## Event sequence (order index, not real time)")
    lines.append("")
    for entry in core["timeline"]:
        kind = _KIND_LABELS[entry["kind"]][language]
        extras = []
        if entry["finish_kind"]:
            extras.append(f"finish={entry['finish_kind']}")
        if entry["has_content"]:
            extras.append("content")
        if entry["has_tool_calls"]:
            extras.append("tool_calls")
        if entry["diagnostic_codes"]:
            extras.extend(entry["diagnostic_codes"])
        suffix = f" ({', '.join(extras)})" if extras else ""
        lines.append(f"- #{entry['index']} {kind}{suffix}")
    lines.append("")
    return "\n".join(lines)


# ---- stream compare (normal vs abnormal) ----

_COMPARE_FIELD_LABELS = {
    "terminal": {"zh-CN": "终态", "en": "Terminal state"},
    "verdict": {"zh-CN": "判定", "en": "Verdict"},
    "finish_reason": {"zh-CN": "finish_reason（受控枚举）", "en": "finish_reason (controlled enum)"},
    "done_seen": {"zh-CN": "是否见 [DONE]", "en": "[DONE] seen"},
    "terminal_event_index": {"zh-CN": "终态事件位置", "en": "Terminal event index"},
    "diagnostic_codes": {"zh-CN": "诊断代码", "en": "Diagnostic codes"},
    "event_count": {"zh-CN": "事件数", "en": "Event count"},
}

_COMPARE_SIDE_LABELS = {
    "baseline": {"zh-CN": "基线（正常）", "en": "Baseline"},
    "candidate": {"zh-CN": "候选（待比较）", "en": "Candidate"},
}

_COMPARE_NOTE_TEXT = {
    "zh-CN": "以上为两侧捕获流之间的观察差异；本比较不证明上游根因。",
    "en": "The differences above are observations between the two captured streams; this comparison does not prove upstream root causes.",
}

_COMPARE_TITLE = {
    "zh-CN": "流结束比较：正常 vs 异常",
    "en": "Stream end comparison: baseline vs candidate",
}

_COMPARE_TERMINAL_SECTION = {
    "zh-CN": "终态差异",
    "en": "Terminal differences",
}

_COMPARE_DIAG_SECTION = {
    "zh-CN": "诊断差异（逐步展开）",
    "en": "Diagnostic differences (expanded)",
}

_COMPARE_SAME_SECTION = {
    "zh-CN": "两侧一致的字段",
    "en": "Fields equal on both sides",
}


def render_compare_card(core: dict, language: str, output_format: str) -> dict | str:
    """Renders a comparison core (kind=stream-compare) as localized JSON/MD."""
    if output_format == "json":
        card = dict(core)
        card["language"] = language
        card["note_text"] = _COMPARE_NOTE_TEXT[language]
        card["note"] = NOTE
        return card
    return _render_compare_markdown(core, language)


def _format_value(field: str, value: object, language: str) -> str:
    if field == "done_seen":
        return ("有" if value else "无") if language == "zh-CN" else ("yes" if value else "none")
    if field == "terminal_event_index":
        return (
            ("未观察到" if value is None else f"@event{value}")
            if language == "zh-CN"
            else ("not observed" if value is None else f"@event{value}")
        )
    if field == "diagnostic_codes":
        codes = value or []
        return ", ".join(codes) if codes else ("—" if language == "zh-CN" else "none")
    if field == "finish_reason" and value == "none":
        return "none（未观察到 finish）" if language == "zh-CN" else "none (no finish observed)"
    return "—" if value is None else str(value)


def _render_compare_markdown(core: dict, language: str) -> str:
    is_zh = language == "zh-CN"
    lines: list[str] = []
    lines.append(f"# {_COMPARE_TITLE[language]}")
    lines.append("")
    for side in ("baseline", "candidate"):
        label = _COMPARE_SIDE_LABELS[side][language]
        s = core[side]
        lines.append(
            f"- {label}: {_format_value('terminal', s['terminal'], language)}"
            f" · {_COMPARE_FIELD_LABELS['finish_reason'][language]}: {_format_value('finish_reason', s['finish_reason'], language)}"
            f" · {_COMPARE_FIELD_LABELS['done_seen'][language]}: {_format_value('done_seen', s['done_seen'], language)}"
        )
    lines.append("")

    lines.append(f"## {_COMPARE_TERMINAL_SECTION[language]}")
    lines.append("")
    terminal_diffs = [d for d in core["differences"] if d["field"] in ("terminal", "verdict")]
    if not terminal_diffs:
        lines.append(
            "- 终态一致。" if is_zh else "- Terminal states are equal."
        )
    for d in terminal_diffs:
        label = _COMPARE_FIELD_LABELS[d["field"]][language]
        lines.append(
            f"- **{label}**: {d['baseline']} → {d['candidate']}"
        )
        # explain both terminal codes with the fixed single-card explanations
        for v in (d["baseline"], d["candidate"]):
            if isinstance(v, str) and v in EXPLANATIONS:
                lines.append(f"  - {v}: {_explanation(v, language)}")
    lines.append("")

    other_diffs = [d for d in core["differences"] if d["field"] not in ("terminal", "verdict")]
    lines.append(f"## {_COMPARE_DIAG_SECTION[language]}")
    lines.append("")
    if not other_diffs:
        lines.append("- 无其他差异。" if is_zh else "- No other differences.")
    for d in other_diffs:
        label = _COMPARE_FIELD_LABELS[d["field"]][language]
        lines.append(f"- **{label}**: {_format_value(d['field'], d['baseline'], language)} → {_format_value(d['field'], d['candidate'], language)}")
        if d["field"] == "diagnostic_codes":
            base_codes = set(_diagnostic_codes(core["baseline"]))
            cand_codes = set(_diagnostic_codes(core["candidate"]))
            for code in sorted((base_codes | cand_codes) & set(EXPLANATIONS)):
                side_tag = (
                    "基线" if (code in base_codes and code not in cand_codes)
                    else "候选" if (code in cand_codes and code not in base_codes)
                    else "两侧"
                ) if is_zh else (
                    "baseline" if (code in base_codes and code not in cand_codes)
                    else "candidate" if (code in cand_codes and code not in base_codes)
                    else "both"
                )
                lines.append(f"  - [{side_tag}] {code}: {_explanation(code, language)}")
                steps = next_steps_for(code, language)
                lines.append(f"    - {_NEXT_LABEL[language]}: {steps['next_steps']}")
                lines.append(
                    f"    - {_CANNOT_PROVE_LABEL[language]}: {steps['does_not_prove']}"
                )
    lines.append("")

    same = core.get("same_fields", [])
    if same:
        labels = "、".join(_COMPARE_FIELD_LABELS[f][language] for f in same if f in _COMPARE_FIELD_LABELS)
        lines.append(f"## {_COMPARE_SAME_SECTION[language]}")
        lines.append("")
        lines.append(f"- {labels}")
        lines.append("")
    lines.append(f"> {_COMPARE_NOTE_TEXT[language]}")
    lines.append("")
    return chr(10).join(lines)
