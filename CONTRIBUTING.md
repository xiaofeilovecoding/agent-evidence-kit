# Contributing / 参与贡献

Bug reports, practical feature requests and focused pull requests are welcome.
Use the issue forms, or a blank issue for questions. A linked issue helps but
is not mandatory for small fixes. Report vulnerabilities privately through
[SECURITY.md](SECURITY.md).

欢迎中英文反馈与贡献；请用合成示例，不贴真实密钥或私密日志。

## From issue to merge

1. Describe the problem, version and a minimal synthetic reproduction.
2. Fork the repository and work on a topic branch. Keep unrelated changes separate.
3. For a bug, add a regression that fails before the fix. Do not remove assertions,
   skip failures or inflate timeouts to obtain a pass.
4. Open a PR using the template and provide actual test results. A maintainer may
   need to approve CI for a first-time fork contributor after inspecting it.
5. Address review feedback. The maintainer decides whether to merge; passing CI
   supports that decision. Dependency-update PRs follow the same process.

## Product boundaries

- Config and stream cores stay standard-library only; optional web imports must
  not enter the plain CLI path.
- Evidence, exports, errors and logs contain fixed constants and bounded facts,
  never raw commands, URLs, credentials or model text. Projection changes need
  synthetic canary coverage.
- Same input, language and format produce deterministic output. Module inputs
  must not be correlated or presented as one run.
- Finding codes are stable; guidance supports English and Chinese.
- Parser limits, clear/session ownership, async response identity and export
  validity are contracts. Explain changes and test their boundaries.
- UI changes include real screenshots for affected languages/themes and 390px.
  Browser fixtures choose an explicit locale; detection cases use their intended
  locale rather than inheriting the host.

## Run locally

Use Python 3.11+ in an isolated environment. Frontend development needs Node 22.

```bash
python -m venv .venv
# Activate: Windows .\.venv\Scripts\Activate.ps1 ; Unix . .venv/bin/activate
python -m pip install -e ".[web]" httpx playwright
python -m playwright install chromium
python scripts/build_frontend.py
python -m unittest discover -s tests -v
python scripts/build_frontend.py --check
```

Commit updated packaged assets when frontend output changes. Regenerate showcase
fixtures with `python scripts/generate_showcase.py` if they change. For package
changes install `.github/requirements-ci.txt`, run `python -m build`, then
`python scripts/check_distribution.py dist`. This creates a temporary environment
outside the checkout and tests the installed CLI, web assets and licenses.

On Windows set `PYTHONUTF8=1`; `PLAYWRIGHT_BROWSERS_PATH` can reuse a browser cache.
Never use real credentials in examples, tests or test environments.

## CI and review

CI checks core Python 3.11/3.14, HTTP, frontend typechecking/builds and npm
advisories, the full browser suite, wheel/sdist installation on Linux and Windows,
Git-history secrets and resolved Python dependency advisories. Frontend builds
are shared; newer PR runs cancel obsolete ones. Checks need no model key or
paid service. Actions and CI tool versions are pinned.

Dependencies receive grouped monthly PRs with a small queue; none are approved
or merged automatically. See [the maintainer checklist](docs/MAINTAINING.md).
