"""Pure structure rules and the language-neutral projection model.

This layer never sees file paths or raw bytes; it only receives the
parsed document. Every output value is a fixed constant of this tool or
a structural fact (presence/type); raw values are never included.
"""
from __future__ import annotations

from .parsers import InputRejected

SERVER_KEYS = ("mcp_servers", "mcpServers")

TRANSPORT_NORMALIZATION = {
    "stdio": "stdio",
    "http": "http",
    "streamable_http": "http",
    "sse": "http",
}

STRING_FIELDS = ("command", "url", "type", "transport")
LIST_FIELDS = ("args", "env_vars")
MAP_FIELDS = ("env", "headers")
KNOWN_FIELDS = STRING_FIELDS + LIST_FIELDS + MAP_FIELDS
RESIDUE_FIELDS = ("command", "args", "env", "env_vars")

SEVERITY = {
    "AMBIGUOUS_TRANSPORT": "warning",
    "POSSIBLE_TRANSPORT_RESIDUE": "warning",
    "INVALID_FIELD_TYPE": "error",
    "TRANSPORT_CONFLICT": "error",
    "NOT_VALIDATED": "info",
}

FIELD_TYPE_NAMES = {
    str: "string",
    list: "list",
    dict: "object",
    bool: "boolean",
    int: "integer",
    float: "number",
}


def _type_name(value: object) -> str:
    return FIELD_TYPE_NAMES.get(type(value), "unknown")


def _add(findings: dict, code: str) -> None:
    findings.setdefault(code, SEVERITY[code])


def _validate_known_fields(config: dict, findings: dict) -> None:
    for name in ("command", "url"):
        if name in config:
            value = config[name]
            if not isinstance(value, str) or not value:
                _add(findings, "INVALID_FIELD_TYPE")
    for name in LIST_FIELDS:
        if name in config:
            value = config[name]
            if not isinstance(value, list) or any(
                not isinstance(item, str) for item in value
            ):
                _add(findings, "INVALID_FIELD_TYPE")
    for name in MAP_FIELDS:
        if name in config:
            value = config[name]
            if not isinstance(value, dict) or any(
                not isinstance(k, str) or not isinstance(v, str)
                for k, v in value.items()
            ):
                _add(findings, "INVALID_FIELD_TYPE")
    for name in ("type", "transport"):
        if name in config and not isinstance(config[name], str):
            _add(findings, "INVALID_FIELD_TYPE")


def _resolve_transport(config: dict, findings: dict) -> str:
    normalized = None
    if isinstance(config.get("transport"), str):
        declared = config["transport"]
        if declared in TRANSPORT_NORMALIZATION:
            normalized = TRANSPORT_NORMALIZATION[declared]
        else:
            _add(findings, "NOT_VALIDATED")
    type_normalized = None
    if isinstance(config.get("type"), str):
        declared_type = config["type"]
        if declared_type in TRANSPORT_NORMALIZATION:
            type_normalized = TRANSPORT_NORMALIZATION[declared_type]
        else:
            _add(findings, "NOT_VALIDATED")
    if normalized is not None and type_normalized is not None:
        if normalized != type_normalized:
            _add(findings, "TRANSPORT_CONFLICT")
    if normalized is not None:
        return normalized
    if type_normalized is not None:
        return type_normalized
    # No usable declaration: infer from shape only (url wins over command
    # because a present url is the active transport in residue scenarios).
    if "url" in config:
        return "http"
    if "command" in config:
        return "stdio"
    return "unknown"


def analyze_service(config: object, index: int) -> dict:
    if not isinstance(config, dict):
        raise InputRejected("INVALID_STRUCTURE")
    findings: dict = {}
    _validate_known_fields(config, findings)
    transport = _resolve_transport(config, findings)
    if "command" in config and "url" in config:
        _add(findings, "AMBIGUOUS_TRANSPORT")
    if "url" in config and any(name in config for name in RESIDUE_FIELDS):
        _add(findings, "POSSIBLE_TRANSPORT_RESIDUE")
    _add(findings, "NOT_VALIDATED")
    fields = {}
    for name in KNOWN_FIELDS:
        present = name in config
        fields[name] = {
            "present": present,
            "type": _type_name(config[name]) if present else None,
        }
    return {
        "id": f"server-{index}",
        "transport": transport,
        "fields": fields,
        "findings": [
            {"code": code, "severity": findings[code]}
            for code in sorted(findings)
        ],
    }


def analyze_document(document: object) -> dict:
    """Return the language-neutral projection core for a parsed document."""
    if not isinstance(document, dict):
        raise InputRejected("INVALID_STRUCTURE")
    present_keys = [key for key in SERVER_KEYS if key in document]
    if len(present_keys) != 1:
        raise InputRejected("INVALID_STRUCTURE")
    servers = document[present_keys[0]]
    if not isinstance(servers, dict):
        raise InputRejected("INVALID_STRUCTURE")
    if len(servers) > 32:
        raise InputRejected("LIMIT_EXCEEDED")
    services = []
    warning_count = 0
    error_count = 0
    for index, config in enumerate(servers.values(), start=1):
        service = analyze_service(config, index)
        services.append(service)
        for finding in service["findings"]:
            if finding["severity"] == "warning":
                warning_count += 1
            elif finding["severity"] == "error":
                error_count += 1
    outcome = "needs_review" if warning_count or error_count else "not_validated"
    return {
        "outcome": outcome,
        "summary": {
            "service_count": len(services),
            "warning_count": warning_count,
            "error_count": error_count,
        },
        "services": services,
    }
