# Security Policy

## Scope

This tool is a local, evidence-only diagnostics kit with two bounded
modules: MCP configuration structure checks and LLM stream
terminal-evidence checks.

- It makes **no network requests**, runs no subprocesses, and never
  executes commands found in configuration files or event payloads.
- The web UI binds to 127.0.0.1 only and is intended for local use by the
  person running it. It is not hardened against other processes running as
  the same user, and it must not be exposed to a network.
- No API keys are needed, requested, or stored. Nothing is uploaded.

## Reporting

Do not open public issues for security problems. Contact the maintainers
through the repository's private security advisory once the repository is
published. Until then, treat all feedback channels as non-security.

## Design invariants worth protecting in review

1. Raw input values (server names, commands, URLs, env values, event ids,
   model output text, tool arguments, unknown fields) must never appear in
   evidence cards, combined exports, errors, or logs.
2. All parser limits (config: 256 KiB, depth 16, 32 services; stream: 8
   MiB input, 128 KiB line, 256 KiB event data, 10000 events, JSON depth
   16; 8 MiB request body; 50 MiB projections) are enforced on
   actually-read bytes, and deeply nested input is rejected with a stable
   error instead of crashing or leaking source paths.
3. Web sessions are HttpOnly + SameSite=Strict with CSRF and exact
   same-origin checks (including same-site different-port rejection) on
   every state-changing request; idle/absolute expiry cannot be revived;
   errors are sanitized and never echo input.
4. Results and exports contain only fixed constants and structural facts
   (presence/type/kind); the combined export marks missing modules
   explicitly and never correlates the two module inputs.
