"""Tests for scripts/label-glm-comments.sh, driven with a fixture transcript and a stubbed `gh`."""

import json
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "label-glm-comments.sh"
COMMENT_TOOL = "mcp__github_inline_comment__create_inline_comment"
REPO = "gardner/button-nz"

# Appends each call's arguments (one per line, then a blank line) to $FAKE_DIR/calls.
# A GET of pulls/comments/<id> prints $FAKE_DIR/body-<id>; a PATCH succeeds.
# FAKE_FAIL makes every call fail.
FAKE_GH = """#!/usr/bin/env bash
{ printf '%s\\n' "$@"; echo; } >> "$FAKE_DIR/calls"
[[ -z "${FAKE_FAIL:-}" ]] || exit 1
for arg in "$@"; do [[ "$arg" == PATCH ]] && exit 0; done
for arg in "$@"; do
  if [[ "$arg" == repos/*/pulls/comments/* ]]; then cat "$FAKE_DIR/body-${arg##*/}"; exit 0; fi
done
exit 2
"""


def _comment_call(tool_id: str, body: str) -> object:
    tool_input = {"path": "a.py", "line": 3, "confirmed": True, "body": body}
    content = [{"type": "tool_use", "id": tool_id, "name": COMMENT_TOOL, "input": tool_input}]
    return {"type": "assistant", "message": {"content": content}}


def _comment_result(tool_id: str, comment_id: int | None, is_error: bool = False) -> object:
    payload: dict[str, object] = {"success": not is_error}
    if comment_id is not None:
        payload["comment_id"] = comment_id
    text = [{"type": "text", "text": json.dumps(payload)}]
    content = [
        {"type": "tool_result", "tool_use_id": tool_id, "is_error": is_error, "content": text}
    ]
    return {"type": "user", "message": {"content": content}}


@pytest.fixture
def fake_dir(tmp_path: Path) -> Path:
    fake = tmp_path / "bin" / "gh"
    fake.parent.mkdir()
    fake.write_text(FAKE_GH, encoding="utf-8")
    fake.chmod(0o755)
    return fake.parent


def _run(fake_dir: Path, *messages: object, **env: str) -> subprocess.CompletedProcess[str]:
    trace = fake_dir / "trace.json"
    trace.write_text(json.dumps([*messages, {"type": "result"}]), encoding="utf-8")
    path = f"{fake_dir}:/usr/bin:/bin"
    return subprocess.run(
        [str(SCRIPT), REPO, str(trace)],
        capture_output=True,
        text=True,
        env={"PATH": path, "FAKE_DIR": str(fake_dir), **env},
    )


def _calls(fake_dir: Path) -> list[list[str]]:
    calls = fake_dir / "calls"
    if not calls.exists():
        return []
    return [
        block.splitlines() for block in calls.read_text(encoding="utf-8").split("\n\n") if block
    ]


def _patches(fake_dir: Path) -> list[list[str]]:
    return [call for call in _calls(fake_dir) if "PATCH" in call]


def test_a_labelled_comment_is_left_alone(fake_dir: Path) -> None:
    (fake_dir / "body-11").write_text("GLM review P2: a risk.", encoding="utf-8")
    result = _run(
        fake_dir, _comment_call("t1", "GLM review P2: a risk."), _comment_result("t1", 11)
    )
    assert result.returncode == 0, result.stderr
    assert _patches(fake_dir) == []
    assert "::warning" not in result.stdout


def test_an_unlabelled_comment_gets_the_label_and_a_warning(fake_dir: Path) -> None:
    (fake_dir / "body-12").write_text("**P1:** a bug.", encoding="utf-8")
    result = _run(fake_dir, _comment_call("t1", "**P1:** a bug."), _comment_result("t1", 12))
    assert result.returncode == 0, result.stderr
    [patch] = _patches(fake_dir)
    assert f"repos/{REPO}/pulls/comments/12" in patch
    assert "body=GLM review **P1:** a bug." in patch
    assert "::warning::" in result.stdout and "12" in result.stdout


def test_the_current_body_is_checked_not_the_transcripts_copy(fake_dir: Path) -> None:
    (fake_dir / "body-13").write_text("P2: edited since.", encoding="utf-8")
    result = _run(
        fake_dir, _comment_call("t1", "GLM review P2: as posted."), _comment_result("t1", 13)
    )
    assert result.returncode == 0, result.stderr
    [patch] = _patches(fake_dir)
    assert "body=GLM review P2: edited since." in patch


def test_only_the_comments_glm_posted_are_touched(fake_dir: Path) -> None:
    (fake_dir / "body-14").write_text("GLM review P2: mine.", encoding="utf-8")
    result = _run(
        fake_dir,
        _comment_call("t1", "GLM review P2: mine."),
        _comment_result("t1", 14),
        _comment_call("t2", "P2: off the diff."),
        _comment_result("t2", None, is_error=True),
    )
    assert result.returncode == 0, result.stderr
    touched = [arg for call in _calls(fake_dir) for arg in call if "pulls/comments/" in arg]
    assert touched == [f"repos/{REPO}/pulls/comments/14"]


def test_no_comments_means_no_calls(fake_dir: Path) -> None:
    result = _run(fake_dir)
    assert result.returncode == 0, result.stderr
    assert _calls(fake_dir) == []


def test_a_posted_comment_without_an_id_fails(fake_dir: Path) -> None:
    result = _run(fake_dir, _comment_call("t1", "P2: lost."), _comment_result("t1", None))
    assert result.returncode != 0
    assert "comment_id" in result.stderr


def test_a_github_failure_fails(fake_dir: Path) -> None:
    result = _run(fake_dir, _comment_call("t1", "P2: x."), _comment_result("t1", 15), FAKE_FAIL="1")
    assert result.returncode != 0
