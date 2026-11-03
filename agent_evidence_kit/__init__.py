"""Agent Evidence Kit: anonymous, shareable evidence for agent troubleshooting.

Two bounded diagnostic modules share one local product:
- ``agent_evidence_kit.config``: structure-only checks for agent MCP
  server configurations (JSON/TOML).
- ``agent_evidence_kit.stream``: terminal-evidence checks for captured
  LLM chat-completions SSE streams.

Both cores are standard library only. The web UI and CLI are thin
adapters over them. No API keys, no telemetry; raw input values never
appear in results.
"""

__version__ = "0.1.0"
