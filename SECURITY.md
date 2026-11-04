# Security Policy

## Scope

Agent Evidence Kit is a local, evidence-only diagnostics tool with two
bounded modules: MCP configuration structure checks and LLM stream
terminal-evidence checks.

- The product makes **no outbound network requests**, runs no
  subprocesses, and never executes commands from configuration files or
  event payloads. Analysis happens over local HTTP between the browser
  workspace and a Python service on the same machine (bound to
  127.0.0.1 only).
- Raw input lives in your input control (that display is expected) and
  in temporary parse memory; the local service keeps only a bounded
  structural projection in memory. Temporary parse memory is not secure
  erasure.
- Copying/downloading is your explicit action; downloads and clipboard
  content are not affected by Clear. Installing dependencies and opening
  documentation links touch the network only on your explicit action.
- The web UI is intended for the person running it; it is not hardened
  against other processes running as the same user, browser extensions,
  and it must not be exposed to a network.

## Reporting

There is no dedicated security email and no private disclosure channel
yet. Once the repository is public, use GitHub's private vulnerability
reporting for this repository. Until such a channel exists, do not open
public issues for security problems; coordinate with the maintainers
directly through an existing contact you already have.

## Design invariants worth protecting in review

1. Raw input values (server names, commands, URLs, env values, event
   ids, model output text, tool arguments, unknown fields) never appear
   in evidence cards, exports, errors, or logs. The allow-listed
   structural projection is the boundary — not post-hoc regex scanning.
2. All parser limits (config: 256 KiB, depth 16, 32 services; stream:
   8 MiB input, 128 KiB line, 256 KiB event data, 10000 events, JSON
   depth 16; 8 MiB request body; 50 MiB projections) are enforced on
   actually-read bytes; deeply nested input is rejected with a stable
   error instead of crashing or leaking paths.
3. Web sessions are HttpOnly + SameSite=Strict with CSRF and exact
   same-origin checks (same-site different-port is rejected); clear()
   gates pending analyses per generation; idle (30 min) and absolute
   (8 h) expiry cannot be revived; errors are sanitized and never echo
   input.
4. Evidence contains only fixed constants and structural facts
   (presence/type/kind). Combined exports mark omitted modules
   explicitly and never correlate the two module inputs.
5. The only persisted data is the language/theme preference
   (`aek.lang`, `aek.theme`); input text, responses, and exports are
   never written to storage, history, or logs.
