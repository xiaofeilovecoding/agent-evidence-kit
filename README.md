# Agent Evidence Kit

**Share the evidence. Keep the raw data.**

Local, privacy-safe evidence cards for agent troubleshooting: structure
checks for MCP server configurations and terminal-evidence checks for
captured LLM streams. Deterministic, bilingual, exportable — no API key,
no telemetry, no uploads.

![Config evidence card](docs/screenshots/en-config-light.png)

## What it does

Two bounded checkers in one local tool:

- **Config check** — paste or drop an agent MCP server configuration
  (`.json` / `.toml`, ≤256 KiB). Get a structure-only evidence card:
  per-server transport facts (presence/type — never values), transport
  conflicts, migration residue, field-type problems, each with an
  *Observed / Meaning / Next step / Does not prove* breakdown.
- **Stream end check** — paste or drop a captured chat-completions SSE
  stream (`.sse` / `.txt`, ≤8 MiB). Get terminal-evidence evidence: was a
  `finish_reason` observed, was `[DONE]` received, truncation,
  `length`/`content_filter` stops, upstream errors, data after `[DONE]` —
  with a normal-termination sample side by side and a 50-per-page event
  sequence.

![Stream evidence with normal-sample comparison](docs/screenshots/en-stream-dark.png)

Everything runs in this workspace (light/dark/system theme, English or
中文): click a sample to try the real pipeline — no key, no network.

## Quick start (from a source checkout)

```bash
git clone https://github.com/xiaofeilovecoding/agent-evidence-kit
cd agent-evidence-kit

# Windows (PowerShell)
py -3 --version          # needs Python 3.11+
pip install -e ".[web]"
python -m agent_evidence_kit web

# macOS / Linux
python3 --version        # needs Python 3.11+
pip install -e ".[web]"
python -m agent_evidence_kit web
```

The web UI opens at `http://127.0.0.1:7411` and needs **no Node.js** —
the interface ships pre-built inside the package. Once the package is
published on PyPI, `pip install "agent-evidence-kit[web]"` becomes the
fastest entry; until then the checkout above is the supported install.

CLI, same cores and exit codes:

```bash
python -m agent_evidence_kit config --input config.toml --format md --lang en
python -m agent_evidence_kit stream --input capture.sse --format json
python -m agent_evidence_kit stream demo --case finish-only
```

## Three problems it answers

1. **"My config changed and a service broke"** — check the config for
   transport conflicts and migration residue; each finding says what was
   observed, what it means, what to do next, and what it cannot prove.
2. **"The stream just ended and I don't know why"** — check whether the
   capture shows a `finish`, a `[DONE]`, both, or neither; the card
   separates the two signals instead of guessing.
3. **"What does a healthy stream look like?"** — every result has a
   normal-termination sample to compare against (config ships a plain
   structure sample too).

All samples are synthetic fixtures run through the same real cores as
your own input — nothing is faked per sample.

## What evidence contains — and what it never contains

An evidence card or export **contains only**: field presence/type, event
order and kinds (chunk/finish/done), stable finding codes with fixed
bilingual explanations and next-step guidance, and fixed scope
statements.

It **never contains**: server names, commands, URLs, env names or values,
model output text, tool arguments, ids, hashes, raw errors, or stack
traces. Even the structural facts it does show (service count, transport
types, event counts) are worth a look before you share — the preview is
the exact bytes of the copy/download.

## Privacy: processed locally, verifiably

- Raw input lives only in your input control (that display is expected)
  and in temporary parse memory on this machine. The local service keeps
  a bounded structural projection in memory; temporary memory is not
  secure erasure.
- No third-party upload, no telemetry, no remote fonts. The only
  persisted data is your language/theme preference.
- The **Processed locally** button in the app opens the four-step data
  path panel so you can verify the claim instead of trusting a badge.
- Copying/downloading is your explicit action and leaves the session —
  downloads and clipboard are not affected by Clear.
- Installing dependencies and opening documentation links touch the
  network, only on your explicit action.

## Not a fit for

- Runtime debugging of a live agent: this tool never connects to
  anything, sends requests, or reads files beyond the one you give it.
- Judging whether an answer is correct, or provider compatibility.
- Automatic fixes: findings come with human next-steps; your config is
  never modified.

## Feedback

Issues and discussion live in the repository's
[issue tracker](https://github.com/xiaofeilovecoding/agent-evidence-kit/issues).
Security-sensitive reports: see [SECURITY.md](SECURITY.md) — please do
not open public issues for them.

## Development

```bash
python -m unittest tests.test_config_core tests.test_stream_core tests.test_next_steps -v
pip install -e ".[web]" httpx
python -m unittest tests.test_web tests.test_clear_race tests.test_export_races -v
python scripts/build_frontend.py          # locked npm ci + both builds + asset sync
python -m unittest tests.test_browser tests.test_review_fixes tests.test_public_ready -v
python scripts/capture_screenshots.py     # regenerate README screenshots from the build
```

Browser tests need Playwright Chromium
(`pip install playwright && python -m playwright install chromium`, or set
`PLAYWRIGHT_BROWSERS_PATH` to an existing cache). See
[CONTRIBUTING.md](CONTRIBUTING.md). 中文说明：[README.zh-CN.md](README.zh-CN.md)。

## Status & license

Version 0.2.0, experimental candidate. MIT — see [LICENSE](LICENSE).
