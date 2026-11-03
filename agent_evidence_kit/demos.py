"""Built-in synthetic demo inputs for both modules.

All content is fictional and safe to publish; nothing here comes from
real user material. Demo analysis runs through the same cores as the
CLI and web adapters.
"""
from __future__ import annotations

import json

# ---- config module demos -------------------------------------------------

CONFIG_DEMO_CASES = (
    {
        "case_id": "http-residue",
        "input_format": "json",
        "description": {
            "zh-CN": "带env_vars的http服务残留提示",
            "en": "http service with env_vars residue hint",
        },
    },
    {
        "case_id": "transport-conflict",
        "input_format": "toml",
        "description": {
            "zh-CN": "command与url同时存在的传输冲突",
            "en": "transport conflict between command and url",
        },
    },
    {
        "case_id": "plain-stdio",
        "input_format": "json",
        "description": {
            "zh-CN": "普通stdio服务，仅投影结构",
            "en": "plain stdio service, structure projection only",
        },
    },
)

_CONFIG_DEMO_BYTES = {
    "http-residue": lambda: json.dumps(
        {
            "mcp_servers": {
                "remote-search": {
                    "url": "https://search.example.invalid/v1",
                    "command": "npx",
                    "args": ["-y", "search-server@1.4.0"],
                    "env_vars": ["SEARCH_TOKEN", "PROXY_URL"],
                }
            }
        },
        indent=2,
    ).encode("utf-8"),
    "transport-conflict": lambda: (
        "[mcp_servers.media-bridge]\n"
        'url = "https://media.example.invalid/mcp"\n'
        'command = "uvx"\n'
        'type = "stdio"\n'
        'transport = "sse"\n'
    ).encode("utf-8"),
    "plain-stdio": lambda: json.dumps(
        {
            "mcp_servers": {
                "local-files": {
                    "command": "python",
                    "args": ["-m", "file_server"],
                    "env": {
                        "LOCAL_TOKEN": "sk-demo-not-a-real-key-0000",
                        "CACHE_DIR": "/tmp/cache",
                    },
                }
            }
        },
        indent=2,
    ).encode("utf-8"),
}

# ---- stream module demos --------------------------------------------------

STREAM_DEMO_CASES = (
    "normal",
    "finish-only",
    "done-only",
    "truncated",
    "limit-stop",
    "after-done",
    "bad-json",
    "unterminated",
)

STREAM_DEMO_DESCRIPTIONS = {
    "normal": {
        "zh-CN": "正常结束：finish stop + [DONE]",
        "en": "Normal: finish stop + [DONE]",
    },
    "finish-only": {
        "zh-CN": "只有finish，缺[DONE]",
        "en": "finish without [DONE]",
    },
    "done-only": {
        "zh-CN": "只有[DONE]，缺finish",
        "en": "[DONE] without finish",
    },
    "truncated": {
        "zh-CN": "内容流被截断：两种结束证据都没有",
        "en": "Truncated content stream: no terminal evidence",
    },
    "limit-stop": {
        "zh-CN": "finish_reason=length：长度上限停止",
        "en": "finish_reason=length",
    },
    "after-done": {
        "zh-CN": "[DONE]之后仍收到数据",
        "en": "Data after [DONE]",
    },
    "bad-json": {
        "zh-CN": "已分派的事件data不是合法JSON",
        "en": "Dispatched event with invalid JSON",
    },
    "unterminated": {
        "zh-CN": "最后一个data缺空行，未分派",
        "en": "Trailing data without a blank line",
    },
}


def _chunk(delta: dict, finish: str | None = None, extra: dict | None = None) -> str:
    choice: dict = {"index": 0, "delta": delta}
    if finish is not None:
        choice["finish_reason"] = finish
    event = {"choices": [choice]}
    if extra:
        event.update(extra)
    return "data: " + json.dumps(event, ensure_ascii=False) + "\n\n"


def _usage_only() -> str:
    event = {"choices": [], "usage": {"prompt_tokens": 1, "completion_tokens": 1}}
    return "data: " + json.dumps(event, ensure_ascii=False) + "\n\n"


DEMO_STREAMS = {
    "normal": (
        ": heartbeat\n\n"
        + _chunk({"role": "assistant", "content": "你好"})
        + _chunk({"content": "OK"})
        + _usage_only()
        + _chunk({}, finish="stop")
        + "data: [DONE]\n\n"
    ),
    "finish-only": (
        _chunk({"content": "OK"})
        + _chunk({}, finish="stop")
    ),
    "done-only": (
        _chunk({"content": "OK"})
        + "data: [DONE]\n\n"
    ),
    "truncated": (
        _chunk({"content": "你好"})
        + _chunk({"content": "OK"})
    ),
    "limit-stop": (
        _chunk({"content": "OK"})
        + _chunk({}, finish="length")
    ),
    "after-done": (
        _chunk({"content": "OK"})
        + _chunk({}, finish="stop")
        + "data: [DONE]\n\n"
        + _chunk({"content": "late"})
    ),
    "bad-json": (
        _chunk({"content": "OK"})
        + "data: {not-json}\n\n"
    ),
    "unterminated": (
        _chunk({"content": "OK"})
        + "data: [DONE]\n"  # no blank line: never dispatched
    ),
}

STREAM_DEMO_BYTES = {name: text.encode("utf-8") for name, text in DEMO_STREAMS.items()}


def config_demo_bytes(case_id: str) -> tuple[bytes, str] | None:
    builder = _CONFIG_DEMO_BYTES.get(case_id)
    if builder is None:
        return None
    for case in CONFIG_DEMO_CASES:
        if case["case_id"] == case_id:
            return builder(), case["input_format"]
    return None
