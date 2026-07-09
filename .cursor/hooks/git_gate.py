#!/usr/bin/env python3
import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
GATE_FILE = REPO_ROOT / ".cursor" / "checkpoint" / "review_gate.json"


def emit(payload: dict) -> None:
    sys.stdout.write(json.dumps(payload))


def run_git(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def load_input() -> dict:
    raw = sys.stdin.read().strip()
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def load_gate() -> tuple[dict | None, str | None]:
    if not GATE_FILE.exists():
        return None, f"Missing gate file: {GATE_FILE}"
    try:
        data = json.loads(GATE_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return None, f"Invalid gate JSON: {exc}"
    return data, None


def list_staged_files() -> tuple[list[str], str | None]:
    proc = run_git(["diff", "--cached", "--name-only"])
    if proc.returncode != 0:
        return [], proc.stderr.strip() or "Unable to read staged files."
    files = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
    return files, None


def validate_commit_gate(gate: dict) -> tuple[bool, list[str]]:
    failures: list[str] = []
    checks = [
        ("bmad_code_review_approved", "BMAD Code Review not approved"),
        ("security_or_bugbot_passed_when_applicable", "Security/Bugbot gate not passed"),
        ("lint_passed", "Lint gate not passed"),
        ("tests_passed", "Automated tests gate not passed"),
    ]
    for key, message in checks:
        if gate.get(key) is not True:
            failures.append(message)

    allowed_files = gate.get("allowed_files")
    if not isinstance(allowed_files, list) or not all(isinstance(x, str) for x in allowed_files):
        failures.append("allowed_files must be a string array")
        return False, failures

    staged_files, err = list_staged_files()
    if err:
        failures.append(err)
        return False, failures

    if not staged_files:
        failures.append("No staged files found. Stage task files before commit.")
        return False, failures

    allowed_set = set(allowed_files)
    outside_scope = [f for f in staged_files if f not in allowed_set]
    if outside_scope:
        failures.append(
            "Staged files include out-of-scope paths: " + ", ".join(outside_scope)
        )

    return len(failures) == 0, failures


def main() -> int:
    payload = load_input()
    command = str(payload.get("command", "")).strip()
    lowered = command.lower()

    if lowered.startswith("git push"):
        emit(
            {
                "permission": "ask",
                "user_message": "Push requires explicit approval. Confirm before running git push.",
                "agent_message": "Hook enforced manual approval for git push.",
            }
        )
        return 0

    if lowered.startswith("git commit"):
        gate, err = load_gate()
        if err:
            emit(
                {
                    "permission": "deny",
                    "user_message": f"Commit blocked: {err}",
                    "agent_message": "Create/update .cursor/checkpoint/review_gate.json first.",
                }
            )
            return 0

        ok, failures = validate_commit_gate(gate)
        if not ok:
            emit(
                {
                    "permission": "deny",
                    "user_message": "Commit blocked by Review Gate: " + " | ".join(failures),
                    "agent_message": "Fix gate status or staged scope, then retry commit.",
                }
            )
            return 0

        emit(
            {
                "permission": "ask",
                "user_message": "Review Gate passed. Confirm commit now (Conventional Commit message required).",
                "agent_message": "Hook verified review/lint/tests and current-task file scope.",
            }
        )
        return 0

    emit({"permission": "allow"})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
