"""Tests for scripts/pre-push-review.sh, driven with a stubbed `claude` on PATH."""

import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "pre-push-review.sh"

# Records its arguments, writes ISSUES.md when given findings, can edit a
# tracked file, and exits as told.
FAKE_CLAUDE = """#!/usr/bin/env bash
printf '%s\\n' "$@" > "$FAKE_DIR/args"
if [[ -f "$FAKE_DIR/findings" ]]; then cp "$FAKE_DIR/findings" ISSUES.md; fi
if [[ -f "$FAKE_DIR/tamper" ]]; then echo "# edited" >> app.py; fi
exit "${FAKE_EXIT:-0}"
"""


@pytest.fixture
def fake_dir(tmp_path: Path) -> Path:
    fake = tmp_path / "bin" / "claude"
    fake.parent.mkdir()
    fake.write_text(FAKE_CLAUDE, encoding="utf-8")
    fake.chmod(0o755)
    return fake.parent


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    (root / "app.py").write_text("print('hi')\n", encoding="utf-8")
    subprocess.run(["git", "add", "app.py"], cwd=root, check=True)
    subprocess.run(
        ["git", "-c", "user.name=T", "-c", "user.email=t@example.com", "commit", "-qm", "init"],
        cwd=root,
        check=True,
    )
    return root


def _run(repo: Path, fake_dir: Path, *refs: str, **env: str) -> subprocess.CompletedProcess[str]:
    full_env = {
        **os.environ,
        "PATH": f"{fake_dir}{os.pathsep}{os.environ['PATH']}",
        "FAKE_DIR": str(fake_dir),
        **env,
    }
    return subprocess.run(
        [str(SCRIPT), *refs], cwd=repo, env=full_env, capture_output=True, text=True
    )


def test_clean_review_passes(repo: Path, fake_dir: Path) -> None:
    result = _run(repo, fake_dir, "abc", "def")
    assert result.returncode == 0, result.stdout + result.stderr
    assert not (repo / "ISSUES.md").exists()


def test_issues_file_is_printed_and_fails_the_push(repo: Path, fake_dir: Path) -> None:
    (fake_dir / "findings").write_text("- P1 `app.py:2`: subtracts.\n", encoding="utf-8")
    result = _run(repo, fake_dir, "abc", "def")
    assert result.returncode == 1
    assert "- P1 `app.py:2`: subtracts." in result.stdout


def test_stale_issues_file_is_removed_before_review(repo: Path, fake_dir: Path) -> None:
    (repo / "ISSUES.md").write_text("stale\n", encoding="utf-8")
    result = _run(repo, fake_dir, "abc", "def")
    assert result.returncode == 0
    assert not (repo / "ISSUES.md").exists()


def test_prompt_names_refs_from_pre_commit(repo: Path, fake_dir: Path) -> None:
    result = _run(repo, fake_dir, PRE_COMMIT_FROM_REF="abc", PRE_COMMIT_TO_REF="def")
    assert result.returncode == 0, result.stdout + result.stderr
    args = (fake_dir / "args").read_text(encoding="utf-8")
    assert "git diff abc def" in args
    assert "read-only" in args


def test_claude_failure_fails_the_push(repo: Path, fake_dir: Path) -> None:
    result = _run(repo, fake_dir, "abc", "def", FAKE_EXIT="1")
    assert result.returncode == 1


def test_missing_refs_fails_with_usage(
    repo: Path, fake_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("PRE_COMMIT_FROM_REF", raising=False)
    result = _run(repo, fake_dir)
    assert result.returncode != 0
    assert "usage" in result.stderr


def test_reviewer_editing_tracked_files_fails_the_push(repo: Path, fake_dir: Path) -> None:
    (fake_dir / "tamper").touch()
    result = _run(repo, fake_dir, "abc", "def")
    assert result.returncode == 1
    assert "modified tracked files" in result.stderr
