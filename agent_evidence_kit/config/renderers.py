"""Renderers: projection model in, localized JSON/Markdown out.

Renderers only accept the projection model produced by diagnostics;
they never receive parsed user documents or raw text. All explanation
strings come from the fixed constants below.
"""
from __future__ import annotations

from ..next_steps import NEXT_STEPS_SCHEMA_VERSION, next_steps_for, state_next_steps

SCHEMA_VERSION = 1
SCOPE = "structure_only"
LANGUAGES = ("zh-CN", "en")
OUTPUT_FORMATS = ("json", "md")

EXPLANATIONS = {
    "INPUT_UNREADABLE": {
        "zh-CN": "无法读取输入文件（不存在、无权限或不是普通文件）。",
        "en": "The input file could not be read (missing, no permission, or not a regular file).",
    },
    "INPUT_TOO_LARGE": {
        "zh-CN": "输入文件超过256KiB上限，未进行分析。",
        "en": "The input file exceeds the 256KiB limit and was not analyzed.",
    },
    "UNSUPPORTED_FORMAT": {
        "zh-CN": "仅支持扩展名为.json或.toml的文件。",
        "en": "Only files with a .json or .toml extension are supported.",
    },
    "INVALID_ENCODING": {
        "zh-CN": "输入不是有效的UTF-8文本（允许一个BOM）。",
        "en": "The input is not valid UTF-8 text (a single BOM is allowed).",
    },
    "INVALID_SYNTAX": {
        "zh-CN": "语法错误，无法按所选格式解析。",
        "en": "Syntax error: the document could not be parsed in the selected format.",
    },
    "DUPLICATE_KEY": {
        "zh-CN": "存在重复键，已拒绝解析以避免歧义。",
        "en": "Duplicate keys were found; parsing was rejected to avoid ambiguity.",
    },
    "LIMIT_EXCEEDED": {
        "zh-CN": "超出结构限制（嵌套深度16层或服务数32个）。",
        "en": "A structural limit was exceeded (nesting depth 16 or 32 services).",
    },
    "INVALID_STRUCTURE": {
        "zh-CN": "结构错误：根必须是对象，且mcp_servers/mcpServers必须恰好出现一个，服务映射与每个服务配置都必须是对象。",
        "en": "Structure error: the root must be an object with exactly one of mcp_servers/mcpServers, and both the service mapping and each service entry must be objects.",
    },
    "AMBIGUOUS_TRANSPORT": {
        "zh-CN": "同一服务同时声明command与url，传输方式不明确，请核对客户端实际读取的字段。",
        "en": "This service declares both command and url, so the transport is ambiguous; check which field your client actually reads.",
    },
    "POSSIBLE_TRANSPORT_RESIDUE": {
        "zh-CN": "服务带url且同时存在command/args/env/env_vars字段，可能是从其他传输方式迁移后的残留。本工具无法确认，请自行核对，不会自动删除任何字段。",
        "en": "This service has a url together with command/args/env/env_vars fields, which may be residue from another transport. This tool cannot confirm that; review manually. No fields are removed automatically.",
    },
    "INVALID_FIELD_TYPE": {
        "zh-CN": "已知字段的类型或空值不符合要求（command/url须非空字符串，args/env_vars须字符串列表，env/headers须字符串映射，type/transport须字符串）。",
        "en": "A known field has a wrong type or an invalid empty value (command/url must be non-empty strings, args/env_vars string lists, env/headers string mappings, type/transport strings).",
    },
    "TRANSPORT_CONFLICT": {
        "zh-CN": "显式type与transport字段指向不同的传输方式。",
        "en": "The explicit type and transport fields point to different transports.",
    },
    "NOT_VALIDATED": {
        "zh-CN": "本工具只做结构检查，不验证客户端版本或运行兼容性；未知字段与未知枚举不回显。",
        "en": "This tool performs structure checks only and does not validate client versions or runtime compatibility; unknown fields and enums are not echoed.",
    },
}

TRANSPORT_LABELS = {
    "stdio": {"zh-CN": "stdio", "en": "stdio"},
    "http": {"zh-CN": "http", "en": "http"},
    "unknown": {"zh-CN": "unknown", "en": "unknown"},
}

_OUTCOME_LABELS = {
    "error": {"zh-CN": "输入错误", "en": "Input error"},
    "needs_review": {"zh-CN": "需要人工复核", "en": "Needs review"},
    "not_validated": {"zh-CN": "仅结构检查完成", "en": "Structure check only"},
}

_SEVERITY_LABELS = {
    "warning": {"zh-CN": "警告", "en": "warning"},
    "error": {"zh-CN": "错误", "en": "error"},
    "info": {"zh-CN": "提示", "en": "info"},
}

_NEXT_LABEL = {"zh-CN": "下一步", "en": "Next step"}
_CANNOT_PROVE_LABEL = {"zh-CN": "不能证明", "en": "Does not prove"}

_SCOPE_STATEMENT = {
    "zh-CN": "范围说明：本卡片只检查配置结构，不验证任何客户端版本、连接或运行行为；结果不含任何原始配置值。",
    "en": "Scope: this card checks configuration structure only; it does not validate client versions, connectivity, or runtime behavior, and it never contains raw configuration values.",
}

_NO_RUNTIME_STATEMENT = {
    "zh-CN": "即使没有发现问题，也不代表配置可以正常运行或完全安全。",
    "en": "Even with no findings, this does not mean the configuration runs correctly or is fully safe.",
}


def _explanation(code: str, language: str) -> str:
    return EXPLANATIONS[code][language]


def render_card(core: dict, language: str, output_format: str) -> dict | str:
    """Render a full card (success or error) from a projection core.

    ``core`` is either the analyze_document() result or
    {"error": code} for file-level errors.
    """
    if output_format == "json":
        return _render_json(core, language)
    return _render_markdown(core, language)


def _render_json(core: dict, language: str) -> dict:
    card = {
        "schema_version": SCHEMA_VERSION,
        "next_steps_schema_version": NEXT_STEPS_SCHEMA_VERSION,
        "scope": SCOPE,
        "language": language,
        "outcome": None,
        "summary": None,
        "services": [],
    }
    if "error" in core:
        code = core["error"]
        card["outcome"] = "error"
        card["error"] = {
            "code": code,
            "explanation": _explanation(code, language),
            "next_steps": next_steps_for(code, language),
        }
        card["summary"] = {
            "service_count": 0,
            "warning_count": 0,
            "error_count": 0,
        }
        card["next_steps"] = next_steps_for(code, language)
        return card
    card["outcome"] = core["outcome"]
    card["summary"] = core["summary"]
    for service in core["services"]:
        card["services"].append(
            {
                "id": service["id"],
                "transport": service["transport"],
                "fields": service["fields"],
                "findings": [
                    {
                        "code": finding["code"],
                        "severity": finding["severity"],
                        "explanation": _explanation(finding["code"], language),
                        "next_steps": next_steps_for(finding["code"], language),
                    }
                    for finding in service["findings"]
                ],
            }
        )
    if core["outcome"] == "not_validated":
        card["next_steps"] = state_next_steps(
            "config", "STRUCTURE_CHECK_COMPLETE", language
        )
    return card


def _render_markdown(core: dict, language: str) -> str:
    is_zh = language == "zh-CN"
    lines = []
    if is_zh:
        lines.append("# Agent 配置证据卡")
    else:
        lines.append("# Agent Configuration Evidence Card")
    lines.append("")
    lines.append(_SCOPE_STATEMENT[language])
    lines.append("")
    if "error" in core:
        code = core["error"]
        lines.append(f"- {code}: {_explanation(code, language)}")
        lines.append("")
        return "\n".join(lines)
    summary = core["summary"]
    if is_zh:
        lines.append(
            f"共分析 {summary['service_count']} 个服务；"
            f"警告 {summary['warning_count']} 项，错误 {summary['error_count']} 项。"
        )
    else:
        lines.append(
            f"Analyzed {summary['service_count']} service(s); "
            f"{summary['warning_count']} warning(s), {summary['error_count']} error(s)."
        )
    lines.append("")
    if not core["services"]:
        lines.append(_explanation("INVALID_STRUCTURE", language))
        lines.append("")
    for service in core["services"]:
        transport_label = TRANSPORT_LABELS[service["transport"]][language]
        lines.append(f"## {service['id']} ({transport_label})")
        lines.append("")
        for name, meta in service["fields"].items():
            if not meta["present"]:
                continue
            state = meta["type"] if meta["type"] else "unknown"
            lines.append(f"- {name}: {state}")
        lines.append("")
        for finding in service["findings"]:
            severity = _SEVERITY_LABELS[finding["severity"]][language]
            lines.append(
                f"- [{severity}] {finding['code']}: "
                f"{_explanation(finding['code'], language)}"
            )
            steps = next_steps_for(finding["code"], language)
            lines.append(
                f"  - {_NEXT_LABEL[language]}: {steps['next_steps']}"
            )
            lines.append(
                f"  - {_CANNOT_PROVE_LABEL[language]}: {steps['does_not_prove']}"
            )
        lines.append("")
    lines.append(_explanation("NOT_VALIDATED", language))
    lines.append("")
    lines.append(_NO_RUNTIME_STATEMENT[language])
    lines.append("")
    return "\n".join(lines)
