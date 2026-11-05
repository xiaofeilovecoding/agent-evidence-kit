## Problem and change / 问题与改动

Describe the behavior before and after. Link an issue when applicable (e.g. Fixes #123).

## Validation / 验证

List the commands and results actually run. For a bug fix, identify the regression that fails before the fix and passes afterward. For documentation-only changes, explain the relevant checks.

## UI / 界面（如适用）

Include real screenshots for affected languages/themes and a narrow viewport.

## Checklist / 检查

- [ ] Scope is focused; assertions were not removed, tests skipped or checks disabled to obtain a pass.
- [ ] Examples are synthetic; inputs, errors, logs and exports contain no real credentials or private raw values.
- [ ] Behavior or finding changes include regressions and English/Chinese text where applicable.
- [ ] Dependency, workflow, parser-limit or privacy-boundary changes are explained above.

CI passing supports review; the maintainer decides whether to merge. / CI 通过后仍由维护者审核决定是否合并。
