"""Tests for scripts/pr-review-threads.sh, driven with a stubbed `gh` on PATH."""

import json
import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "pr-review-threads.sh"

# Records its arguments and prints the canned GraphQL response.
FAKE_GH = """#!/usr/bin/env bash
printf '%s\\n' "$@" > "$FAKE_DIR/args"
cat "$FAKE_DIR/response.json"
exit "${FAKE_EXIT:-0}"
"""


def _thread(path: str, line: int | None, resolved: bool, *comments: tuple[str, str]) -> object:
    return {
        "path": path,
        "line": line,
        "isResolved": resolved,
        "comments": {"nodes": [{"author": {"login": a}, "body": b} for a, b in comments]},
    }


def _response(*threads: object) -> str:
    pr = {"reviewThreads": {"nodes": list(threads)}}
    return json.dumps({"data": {"repository": {"pullRequest": pr}}})


@pytest.fixture
def fake_dir(tmp_path: Path) -> Path:
    fake = tmp_path / "bin" / "gh"
    fake.parent.mkdir()
    fake.write_text(FAKE_GH, encoding="utf-8")
    fake.chmod(0o755)
    return fake.parent


def _run(fake_dir: Path, response: str, **env: str) -> subprocess.CompletedProcess[str]:
    (fake_dir / "response.json").write_text(response, encoding="utf-8")
    full_env = {
        **os.environ,
        "PATH": f"{fake_dir}{os.pathsep}{os.environ['PATH']}",
        "FAKE_DIR": str(fake_dir),
        **env,
    }
    return subprocess.run(
        [str(SCRIPT), "octo/repo", "24"], env=full_env, capture_output=True, text=True
    )


def test_queries_the_named_pull_request(fake_dir: Path) -> None:
    result = _run(fake_dir, _response())
    assert result.returncode == 0, result.stderr
    args = (fake_dir / "args").read_text(encoding="utf-8")
    assert "owner=octo" in args
    assert "name=repo" in args
    assert "number=24" in args


def test_no_threads(fake_dir: Path) -> None:
    result = _run(fake_dir, _response())
    assert result.stdout == "No earlier review threads.\n"


def test_threads_list_location_state_and_every_comment(fake_dir: Path) -> None:
    response = _response(
        _thread(
            "scripts/a.sh",
            6,
            True,
            ("bot", "P2: root commit unsupported."),
            ("gardner", "Declined on purpose."),
        ),
        _thread("b.py", None, False, ("bot", "P1: multi-line\nfinding.")),
    )
    result = _run(fake_dir, response)
    assert result.returncode == 0, result.stderr
    assert result.stdout == (
        "## scripts/a.sh:6 (resolved)\n\n"
        "**bot:** P2: root commit unsupported.\n\n"
        "**gardner:** Declined on purpose.\n\n"
        "## b.py (open)\n\n"
        "**bot:** P1: multi-line\nfinding.\n\n"
    )


def test_gh_failure_fails_the_script(fake_dir: Path) -> None:
    result = _run(fake_dir, "", FAKE_EXIT="1")
    assert result.returncode != 0
