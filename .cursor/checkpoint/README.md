# Checkpoint Review Gate

This project uses a Cursor hook to gate `git commit` and `git push`.

## Rules Enforced

- `git commit` is allowed only when all gate flags are `true`.
- `git commit` is always interactive (`permission: ask`) even when gate passes.
- `git push` is always interactive (`permission: ask`).
- Staged files must be a subset of `allowed_files` to enforce current-task scope.

## Gate File

Update `.cursor/checkpoint/review_gate.json` before committing:

```json
{
  "bmad_code_review_approved": true,
  "security_or_bugbot_passed_when_applicable": true,
  "lint_passed": true,
  "tests_passed": true,
  "allowed_files": [
    "path/to/file1",
    "path/to/file2"
  ]
}
```

## Recommended Workflow

1. Run review(s), lint, and tests.
2. Update `review_gate.json` with pass/fail statuses and the exact files for this checkpoint.
3. Stage only checkpoint files (`git add ...`).
4. Run `git commit` with a Conventional Commit message.
5. Confirm the commit when Cursor asks.
6. Run `git push` only when explicitly desired; confirm when asked.
