# Agent Evidence Kit

Anonymous, shareable evidence for agent troubleshooting — generated
locally, in seconds, without uploading anything.

Two bounded diagnostic modules in one tool:

- **Config check** — paste or drop an agent MCP server configuration
  (`.json` / `.toml`, ≤256 KiB) and get a structure-only evidence card:
  per-server transport facts (presence/type, never values), transport
  conflicts and migration residue warnings, stable finding codes.
- **Stream end check** — paste or drop a captured chat-completions SSE
  stream (`.sse` / `.txt`, ≤8 MiB) and get terminal-evidence evidence:
  was a `finish_reason` observed, was `[DONE]` received, truncated
  streams, `length`/`content_filter` stops, upstream errors, data after
  `[DONE]` — with a normal-termination sample for comparison.

You can use one module alone; both results can be combined into a single
Markdown/JSON export suitable as an anonymous issue attachment. The tool
never assumes the two inputs come from the same run and never correlates
them.

## Why

When an agent misbehaves, the fastest help comes from sharing evidence —
but configs and stream captures are full of secrets (commands, URLs,
tokens, conversation text). Agent Evidence Kit converts either input into
a deterministic projection that contains **only fixed constants and
structural facts**: no server names, no commands, no URLs, no tokens, no
model output text, no hashes, no raw errors. Share the card, keep the
secrets.

## 30-second demo (no install, no key)

```bash
pip install "agent-evidence-kit[web]"
python -m agent_evidence_kit web          # opens http://127.0.0.1:7411
```

Click any built-in synthetic sample (config or stream), see the evidence
card, export it. Everything stays on your machine; there is no API key,
no telemetry, no network access.

## CLI

```bash
python -m agent_evidence_kit config --input config.toml --format md --lang en
python -m agent_evidence_kit stream --input capture.sse --format json
python -m agent_evidence_kit stream demo --case finish-only
python -m agent_evidence_kit web --no-open --port 7411
```

Exit codes per module: `0` clean / `1` findings need review / `2` invalid
input. The web UI and CLI produce identical cards for identical input.

## Privacy model

- Raw values are never rendered, stored, logged, or exported — only
  presence/type/kind facts and fixed explanation strings.
- All limits (256 KiB config / 8 MiB stream, depth, line, event counts)
  are enforced on the bytes actually read; deeply nested input is rejected
  with a stable error, never a crash or a leaked path.
- The web UI binds to `127.0.0.1` only, uses an HttpOnly `SameSite=Strict`
  session with CSRF and exact same-origin checks, expires idle (30 min)
  and absolute (8 h) sessions, and stores only bounded projections.
- Deterministic: same input + language + format → byte-identical output.

## Not a fit for

- Runtime debugging of a live agent (this tool never connects to
  anything, sends requests, or reads logs beyond the file you give it).
- Judging whether an answer is correct, or provider compatibility.
- Automatic fixes — findings come with explanations, and nothing in your
  config is modified.

## Development

```bash
git clone <repo> && cd agent-evidence-kit
python -m unittest tests.test_config_core tests.test_stream_core -v   # cores (stdlib only)
pip install -e ".[web]" httpx && python -m unittest tests.test_web -v  # HTTP layer
python scripts/build_frontend.py                                       # build + sync web assets
python -m unittest tests.test_browser -v                               # real-browser journeys
```

Frontend: React + TypeScript + Vite (`frontend/`); the local UI is served
from the Python package (`agent_evidence_kit/_web_static`) by the build
script. A static sample showcase build (`npm run build:showcase`) is also
available; it performs no API calls. See [CONTRIBUTING.md](CONTRIBUTING.md)
and [SECURITY.md](SECURITY.md).

## Status

Experimental candidate. The two modules were consolidated from earlier
single-purpose prototypes (Agent Diagnostic Card, Stream End Lab); the
schema of each module's card is versioned independently.

## License

MIT — see [LICENSE](LICENSE).
