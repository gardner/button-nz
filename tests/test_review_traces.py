"""Tests for scripts/review-traces.sh, driven with stubbed `gh` and `gpg` on PATH."""

import json
import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "review-traces.sh"

# `gh api` prints the canned artifact list; `gh run download` drops the canned
# trace where the real one would land, as if still encrypted.
FAKE_GH = """#!/usr/bin/env bash
printf '%s\\n' "$*" >> "$FAKE_DIR/gh-calls"
if [[ "$1" == api ]]; then cat "$FAKE_DIR/artifacts"; exit 0; fi
while [[ $# -gt 0 ]]; do
  if [[ "$1" == --dir ]]; then
    mkdir -p "$2"
    cp "$FAKE_DIR/trace.json" "$2/claude-review-trace.json.gpg"
  fi
  shift
done
"""

# Decrypting prints the file unchanged.
FAKE_GPG = """#!/usr/bin/env bash
cat "${@: -1}"
"""

TRACE: list[object] = [
    {"type": "system", "subtype": "init", "model": "claude-opus-5-5"},
    {
        "type": "assistant",
        "message": {"content": [{"type": "tool_use", "id": "t1", "name": "Bash", "input": {}}]},
    },
    {
        "type": "user",
        "message": {"content": [{"type": "tool_result", "tool_use_id": "t1", "is_error": False}]},
    },
    {
        "type": "result",
        "is_error": False,
        "num_turns": 3,
        "duration_ms": 9000,
        "total_cost_usd": 0.5,
        "permission_denials": [],
    },
]


def _artifacts(*artifacts: tuple[int, str, str], expired: bool = False) -> str:
    """One page of the artifacts API, as `gh api --paginate --slurp` prints it."""
    page = {
        "artifacts": [
            {"name": name, "created_at": created, "expired": expired, "workflow_run": {"id": run}}
            for run, name, created in artifacts
        ]
    }
    return json.dumps([page])


@pytest.fixture
def fake_dir(tmp_path: Path) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in (("gh", FAKE_GH), ("gpg", FAKE_GPG)):
        (bin_dir / name).write_text(body, encoding="utf-8")
        (bin_dir / name).chmod(0o755)
    (bin_dir / "trace.json").write_text(json.dumps(TRACE), encoding="utf-8")
    return bin_dir


def _run(fake_dir: Path, artifacts: str, *args: str) -> subprocess.CompletedProcess[str]:
    (fake_dir / "artifacts").write_text(artifacts, encoding="utf-8")
    env = {
        **os.environ,
        "PATH": f"{fake_dir}{os.pathsep}{os.environ['PATH']}",
        "FAKE_DIR": str(fake_dir),
    }
    return subprocess.run([str(SCRIPT), *args], env=env, capture_output=True, text=True)


def test_downloads_decrypts_and_summarises_each_trace(fake_dir: Path, tmp_path: Path) -> None:
    out = tmp_path / "out"
    artifacts = _artifacts(
        (101, "claude-review-trace-1", "2026-10-28T07:00:00Z"),
        (102, "claude-review-trace-2", "2026-10-28T08:00:00Z"),
    )
    result = _run(fake_dir, artifacts, "5", str(out))
    assert result.returncode == 0, result.stderr
    assert "# Run 101 (claude-review-trace-1)" in result.stdout
    assert "# Run 102 (claude-review-trace-2)" in result.stdout
    assert result.stdout.count("| claude-opus-5-5 | 3 | 9s | $0.50 | 0 | 0 |") == 2
    assert json.loads((out / "101-claude-review-trace-1" / "trace.json").read_text()) == TRACE
    assert result.stdout.endswith(f"Decrypted transcripts: {out}\n")


def test_stops_after_count_traces(fake_dir: Path, tmp_path: Path) -> None:
    artifacts = _artifacts(
        (102, "claude-review-trace-1", "2026-10-28T08:00:00Z"),
        (103, "claude-review-trace-1", "2026-10-28T09:00:00Z"),
        (101, "claude-review-trace-1", "2026-10-28T07:00:00Z"),
        (104, "other-artifact", "2026-10-28T10:00:00Z"),
    )
    result = _run(fake_dir, artifacts, "2", str(tmp_path / "out"))
    assert result.returncode == 0, result.stderr
    downloads = [c for c in (fake_dir / "gh-calls").read_text().splitlines() if "download" in c]
    assert [d.split()[2] for d in downloads] == ["103", "102"]


def test_skips_expired_traces(fake_dir: Path, tmp_path: Path) -> None:
    artifacts = _artifacts((101, "claude-review-trace-1", "2026-10-28T07:00:00Z"), expired=True)
    result = _run(fake_dir, artifacts, "5", str(tmp_path / "out"))
    assert result.returncode == 0, result.stderr
    assert result.stdout == "No review traces found.\n"


def test_no_traces(fake_dir: Path, tmp_path: Path) -> None:
    result = _run(fake_dir, _artifacts(), "5", str(tmp_path / "out"))
    assert result.returncode == 0, result.stderr
    assert result.stdout == "No review traces found.\n"


def test_a_review_that_ran_nothing_is_reported_not_fatal(fake_dir: Path, tmp_path: Path) -> None:
    (fake_dir / "trace.json").write_text(json.dumps([TRACE[0], TRACE[-1]]), encoding="utf-8")
    artifacts = _artifacts(
        (101, "claude-review-trace-1", "2026-10-28T07:00:00Z"),
        (102, "claude-review-trace-1", "2026-10-28T08:00:00Z"),
    )
    result = _run(fake_dir, artifacts, "5", str(tmp_path / "out"))
    assert result.returncode == 0, result.stderr
    assert result.stdout.count("**No review happened:** no shell command succeeded.") == 2


def test_a_broken_trace_fails_with_its_real_error(fake_dir: Path, tmp_path: Path) -> None:
    (fake_dir / "trace.json").write_text(json.dumps([TRACE[0]]), encoding="utf-8")
    artifacts = _artifacts((101, "claude-review-trace-1", "2026-10-28T07:00:00Z"))
    result = _run(fake_dir, artifacts, "5", str(tmp_path / "out"))
    assert result.returncode != 0
    assert "no result message" in result.stderr
    assert "No review happened" not in result.stdout
