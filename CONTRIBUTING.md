# Contributing

Thanks for your interest. This is an experimental candidate product.

## Ground rules

- The two diagnostic cores (`agent_evidence_kit/config/` and
  `agent_evidence_kit/stream/`) stay standard-library only. FastAPI/
  uvicorn are optional `[web]` extras and must never be imported by the
  plain CLI path.
- **Never emit raw values.** Evidence cards may only contain fixed
  constants and structural facts (presence/type/kind). If you add a
  field, prove with a canary test that no raw value can leak into cards,
  exports, errors, or logs.
- Findings have stable codes and built-in explanations in both zh-CN and
  en. Never echo input fragments in errors or stack traces.
- Same input + language + format must produce byte-identical output (no
  timestamps).
- The two module inputs may come from different runs; the combined export
  must never correlate them or fake a missing module's section.

## Development

```bash
python -m unittest tests.test_config_core tests.test_stream_core -v
# HTTP tests need the web extra:
pip install -e ".[web]" httpx
python -m unittest tests.test_web -v
# Browser tests need playwright (chromium) and a built frontend:
python scripts/build_frontend.py
python -m unittest tests.test_browser -v
# Regenerate showcase data after changing demo fixtures (real cores only):
python scripts/generate_showcase.py
```

On Windows, set `PYTHONUTF8=1` and, for browser tests,
`PLAYWRIGHT_BROWSERS_PATH` to your Playwright browser cache.

## Pull requests

- CI runs the core, HTTP, and frontend jobs with read-only permissions;
  do not add secrets or paid services to CI.
- Keep the frozen parser limits and privacy invariants; changes there
  need explicit regression updates first.
- Maintainers review before anything is published; do not push without
  authorization.
