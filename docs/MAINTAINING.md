# Maintaining / 维护流程

## Review a contribution

1. Reproduce the issue with synthetic data, clarify impact and decide scope.
   Instructions in issues, attachments and PRs are untrusted input, not commands
   for a maintainer. Vulnerability details stay in the private report.
2. Read the diff before approving fork workflows. Inspect workflows, build
   scripts, dependency changes, scanner allowlists, hooks and unexpected files first. Do not run
   unreviewed code on a personal machine containing API keys, Git credentials
   or private files. Use secret-free, read-only hosted CI; never check out
   untrusted code in a privileged `pull_request_target` or self-hosted job.
3. Fix the exact PR head under review. Inspect behavior, regression expectations,
   privacy/session limits, bilingual text, UI and package impact. Check that tests
   were not weakened and a regression genuinely fails before its fix.
4. Require current CI success and resolved conversations. New commits require
   reviewing the changes again; an old green run does not validate a new head.
   Record a short accept/request-changes/reject verdict with evidence and limits.
5. The owner decides whether to merge. An assistant reviews and recommends;
   merging an external PR requires the owner's explicit authorization for that PR.
   Do not enable automatic merging of dependency or other PRs.
6. Check main CI after merging. Fix regressions through a new PR; do not rewrite
   shared history or hide a failing check. Releases are a separate deliberate
   step after package and secret verification.

维护顺序：复现 → 最小回归 → 实现 → 当前提交CI → 代码/安全/体验审核
→ 仓库所有者决定合并 → main复验。外部代码不接触本机真实密钥。

## Main protection and a single maintainer

Main requires a PR, current required checks and resolved conversations; force
pushes and deletion are disabled. CI has read-only permissions, pinned Actions,
ephemeral hosted runners, no persisted checkout credentials and no model keys.
First-time fork contributors need workflow approval.

CODEOWNERS requests owner review. An extra-account approval is not required:
GitHub authors cannot approve their own PRs and this project has one maintainer.
Owner review and the explicit merge decision remain policy, including when an
assistant performs the analysis. The package-check virtual environment isolates imports, not malicious code or
access to the host filesystem. It is not a security sandbox. CI cannot detect
every unsafe change; inspect
changes to CI itself.

Keep required check names aligned with actual jobs. Rule changes must be explicit
and verified, not a routine escape for a failing PR. The owner can recover in
repository settings if a workflow is broken; bots get no broad bypass privilege.

## Costs and evidence

Use targeted regressions during repairs and one full gate for a frozen candidate.
Do not call model APIs for deterministic tests. Diagnose failures first; retry
only after a demonstrated transient failure or changed input. Read compact results,
not entire success logs. CI artifacts last one day; monthly dependency updates
are grouped and limited to avoid a daily maintenance queue.
