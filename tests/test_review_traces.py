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
        "type": "result",
        "is_error": False,
        "num_turns": 3,
        "duration_ms": 9000,
        "total_cost_usd": 0.5,
        "permission_denials": [],
    },
]


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
    result = _run(fake_dir, "101 claude-review-trace-1\n102 claude-review-trace-2\n", "5", str(out))
    assert result.returncode == 0, result.stderr
    assert "# Run 101 (claude-review-trace-1)" in result.stdout
    assert "# Run 102 (claude-review-trace-2)" in result.stdout
    assert result.stdout.count("| claude-opus-5-5 | 3 | 9s | $0.50 | 0 | 0 |") == 2
    assert json.loads((out / "101-claude-review-trace-1" / "trace.json").read_text()) == TRACE
    assert result.stdout.endswith(f"Decrypted transcripts: {out}\n")


def test_stops_after_count_traces(fake_dir: Path, tmp_path: Path) -> None:
    result = _run(fake_dir, "101 a\n102 b\n103 c\n", "2", str(tmp_path / "out"))
    assert result.returncode == 0, result.stderr
    downloads = [c for c in (fake_dir / "gh-calls").read_text().splitlines() if "download" in c]
    assert len(downloads) == 2
    assert "# Run 103" not in result.stdout


def test_no_traces(fake_dir: Path, tmp_path: Path) -> None:
    result = _run(fake_dir, "", "5", str(tmp_path / "out"))
    assert result.returncode == 0, result.stderr
    assert result.stdout == "No review traces found.\n"
