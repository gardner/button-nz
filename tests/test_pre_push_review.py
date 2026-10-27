"""Tests for scripts/pre-push-review.sh, driven with a stubbed `claude` on PATH."""

import json
import os
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "pre-push-review.sh"

FAKE_CLAUDE = """#!/usr/bin/env bash
printf '%s\\n' "$@" > "$FAKE_DIR/args"
cat > "$FAKE_DIR/stdin"
cat "$FAKE_DIR/response"
exit "$(cat "$FAKE_DIR/exit_code")"
"""

FINDING: Mapping[str, object] = {
    "severity": "P1",
    "file": "app.py",
    "line": 2,
    "issue": "Subtracts instead of adds.",
}


@dataclass
class Repo:
    root: Path
    fake_dir: Path
    base: str

    def git(self, *args: str) -> str:
        result = subprocess.run(
            ["git", *args], cwd=self.root, check=True, capture_output=True, text=True
        )
        return result.stdout.strip()

    def commit(self, name: str, content: str) -> str:
        (self.root / name).write_text(content, encoding="utf-8")
        self.git("add", name)
        self.git("commit", "-q", "-m", f"change {name}")
        return self.git("rev-parse", "HEAD")

    def respond(self, payload: object, exit_code: int = 0) -> None:
        text = payload if isinstance(payload, str) else json.dumps(payload)
        (self.fake_dir / "response").write_text(text, encoding="utf-8")
        (self.fake_dir / "exit_code").write_text(str(exit_code), encoding="utf-8")

    def run(self, *refs: str) -> subprocess.CompletedProcess[str]:
        env = {
            **os.environ,
            "PATH": f"{self.fake_dir}{os.pathsep}{os.environ['PATH']}",
            "FAKE_DIR": str(self.fake_dir),
        }
        return subprocess.run(
            [str(SCRIPT), *refs], cwd=self.root, env=env, capture_output=True, text=True
        )

    @property
    def issues(self) -> Path:
        return self.root / "ISSUES.md"


def _review(findings: list[Mapping[str, object]]) -> dict[str, object]:
    return {"is_error": False, "structured_output": {"findings": findings}}


@pytest.fixture
def repo(tmp_path: Path) -> Repo:
    root = tmp_path / "repo"
    fake_dir = tmp_path / "bin"
    root.mkdir()
    fake_dir.mkdir()
    fake = fake_dir / "claude"
    fake.write_text(FAKE_CLAUDE, encoding="utf-8")
    fake.chmod(0o755)
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)
    repo = Repo(root=root, fake_dir=fake_dir, base="")
    repo.base = repo.commit("app.py", "def add(a, b):\n    return a + b\n")
    repo.respond(_review([]))
    return repo


def test_clean_review_passes_without_issues_file(repo: Repo) -> None:
    head = repo.commit("app.py", "def add(a, b):\n    return b + a\n")
    result = repo.run(repo.base, head)
    assert result.returncode == 0, result.stdout + result.stderr
    assert not repo.issues.exists()


def test_findings_write_issues_file_print_it_and_fail(repo: Repo) -> None:
    head = repo.commit("app.py", "def add(a, b):\n    return a - b\n")
    repo.respond(_review([FINDING]))
    result = repo.run(repo.base, head)
    assert result.returncode == 1
    issues = repo.issues.read_text(encoding="utf-8")
    assert "P1" in issues
    assert "app.py:2" in issues
    assert "Subtracts instead of adds." in issues
    assert issues in result.stdout


def test_stale_issues_file_is_removed_before_review(repo: Repo) -> None:
    head = repo.commit("app.py", "def add(a, b):\n    return b + a\n")
    repo.issues.write_text("stale findings\n", encoding="utf-8")
    result = repo.run(repo.base, head)
    assert result.returncode == 0
    assert not repo.issues.exists()


def test_reads_refs_from_pre_commit_environment(
    repo: Repo, monkeypatch: pytest.MonkeyPatch
) -> None:
    head = repo.commit("app.py", "def add(a, b):\n    return a - b\n")
    monkeypatch.setenv("PRE_COMMIT_FROM_REF", repo.base)
    monkeypatch.setenv("PRE_COMMIT_TO_REF", head)
    result = repo.run()
    assert result.returncode == 0, result.stdout + result.stderr
    assert "return a - b" in (repo.fake_dir / "stdin").read_text(encoding="utf-8")


def test_root_commit_push_reviews_whole_history(
    repo: Repo, monkeypatch: pytest.MonkeyPatch
) -> None:
    # pre-commit sets no refs when the pushed history includes the root commit.
    repo.commit("app.py", "def add(a, b):\n    return a - b\n")
    monkeypatch.delenv("PRE_COMMIT_FROM_REF", raising=False)
    monkeypatch.delenv("PRE_COMMIT_TO_REF", raising=False)
    monkeypatch.setenv("PRE_COMMIT_LOCAL_BRANCH", "refs/heads/main")
    result = repo.run()
    assert result.returncode == 0, result.stdout + result.stderr
    stdin = (repo.fake_dir / "stdin").read_text(encoding="utf-8")
    assert "new file mode" in stdin
    assert "return a - b" in stdin


def test_missing_refs_is_a_usage_error(repo: Repo, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PRE_COMMIT_FROM_REF", raising=False)
    monkeypatch.delenv("PRE_COMMIT_TO_REF", raising=False)
    monkeypatch.delenv("PRE_COMMIT_LOCAL_BRANCH", raising=False)
    result = repo.run()
    assert result.returncode == 2
    assert "usage" in result.stderr


def test_sends_outgoing_diff_without_lockfiles_to_read_only_reviewer(repo: Repo) -> None:
    repo.commit("uv.lock", "lock-noise\n")
    head = repo.commit("app.py", "def add(a, b):\n    return a - b\n")
    result = repo.run(repo.base, head)
    assert result.returncode == 0, result.stdout + result.stderr
    stdin = (repo.fake_dir / "stdin").read_text(encoding="utf-8")
    assert "return a - b" in stdin
    assert "lock-noise" not in stdin
    args = (repo.fake_dir / "args").read_text(encoding="utf-8").splitlines()
    assert args[args.index("--permission-mode") + 1] == "plan"
    assert "--json-schema" in args


def test_lockfile_only_push_skips_review(repo: Repo) -> None:
    head = repo.commit("uv.lock", "lock-noise\n")
    result = repo.run(repo.base, head)
    assert result.returncode == 0
    assert not (repo.fake_dir / "stdin").exists()


@pytest.mark.parametrize(
    ("payload", "exit_code"),
    [
        (_review([]), 1),
        ({"is_error": True, "result": "Not logged in"}, 0),
        ({"is_error": False, "result": "no structured output"}, 0),
        ("not json", 0),
    ],
    ids=["claude-exit-nonzero", "claude-error", "missing-findings", "unparseable"],
)
def test_failed_review_blocks_push(repo: Repo, payload: object, exit_code: int) -> None:
    head = repo.commit("app.py", "def add(a, b):\n    return a - b\n")
    repo.respond(payload, exit_code=exit_code)
    result = repo.run(repo.base, head)
    assert result.returncode == 1
    assert "review failed" in result.stderr
    assert not repo.issues.exists()
