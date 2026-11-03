"""Synthetic fixtures shared by tests. Never real user material."""
from __future__ import annotations

import json

# ---- config fixtures ----

CANARY_KEY = "sk-canary-ALPHA7Q9Z"
CANARY_URL = "https://canary.example.invalid/v1?key=canary-query-BETA42"
CANARY_TOKEN = "canary-env-token-GAMMA77"
CANARY_MARKDOWN = "![canary](http://canary.example.invalid/x)"
CANARY_EMAIL = "canary-delta@example.invalid"


def residue_config() -> str:
    """http service with transport residue (JSON syntax)."""
    return """{
  "mcp_servers": {
    "magpie-prod": {
      "url": "%s",
      "command": "npx",
      "args": ["-y", "magpie@1.2.3"],
      "env": {"MAGPIE_TOKEN": "%s"}
    }
  }
}""" % (
        CANARY_URL,
        CANARY_TOKEN,
    )


def residue_config_toml() -> str:
    return """[mcp_servers.primary-svc]
url = "%s"
command = "node"
args = ["server.js"]
env_vars = ["%s"]
""" % (
        CANARY_URL,
        CANARY_TOKEN,
    )


def ambiguous_config() -> str:
    return (
        '{"mcpServers": {"dual": {"command": "uvx", "url": "%s", '
        '"type": "stdio", "transport": "sse"}}}' % CANARY_URL
    )


def plain_stdio_config() -> str:
    return """{
  "mcp_servers": {
    "local-tools": {
      "command": "python",
      "args": ["-m", "server"],
      "env": {"API_KEY": "%s", "NOTE": "%s"}
    }
  }
}""" % (
        CANARY_KEY,
        CANARY_MARKDOWN,
    )


def deep_config_json(depth: int) -> str:
    inner = '{"n":' * (depth - 3) + "1" + "}" * (depth - 3)
    return '{"mcp_servers":{"s":{"command":"x","probe":' + inner + "}}}"


def deep_config_toml(depth: int) -> str:
    inner = "{x = " * (depth - 2) + "1" + "}" * (depth - 2)
    return '[mcp_servers.s]\ncommand="x"\nnested=' + inner + "\n"


# ---- stream fixtures ----

CANARY_S_KEY = "sk-canary-OMEGA42Z"
CANARY_S_ID = "chatcmpl-canary-OMEGA42"
CANARY_S_TEXT = "canary-secret-lambda99"


def chunk(content=None, finish=None, index=0, tool_calls=None, extra=None):
    choice = {"index": index}
    delta = {}
    if content is not None:
        delta["content"] = content
    if tool_calls is not None:
        delta["tool_calls"] = tool_calls
    choice["delta"] = delta
    if finish is not None:
        choice["finish_reason"] = finish
    event = {"choices": [choice]}
    if extra:
        event.update(extra)
    return "data: " + json.dumps(event, ensure_ascii=False) + "\n\n"


def usage_only():
    event = {"choices": [], "usage": {"prompt_tokens": 3, "completion_tokens": 5}}
    return "data: " + json.dumps(event) + "\n\n"


def done():
    return "data: [DONE]\n\n"


def normal_stream() -> bytes:
    return (
        ": heartbeat\n\n"
        + chunk("你好")
        + chunk("OK")
        + usage_only()
        + chunk(finish="stop")
        + done()
    ).encode("utf-8")


def tool_calls_stream() -> bytes:
    return (
        chunk(tool_calls=[{"id": CANARY_S_ID, "function": {"name": "f", "arguments": "{}"}}])
        + chunk(finish="tool_calls")
        + done()
    ).encode("utf-8")
