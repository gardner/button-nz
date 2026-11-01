"""Tests for button_nz.bench.provenance: a result names the code that made it."""

import subprocess
from pathlib import Path

import pytest

from button_nz.bench.provenance import code_commit


def _repo(root: Path) -> None:
    def git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)

    git("init", "-q")
    (root / "src").mkdir()
    (root / "src" / "a.py").write_text("x = 1\n")
    git("add", ".")
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "one")


def test_a_clean_tree_is_credited_to_head(tmp_path: Path) -> None:
    _repo(tmp_path)
    assert "uncommitted" not in code_commit(root=tmp_path)


def test_a_new_uncommitted_input_marks_the_result(tmp_path: Path) -> None:
    _repo(tmp_path)
    (tmp_path / "src" / "new.py").write_text("y = 2\n")  # never committed
    assert code_commit(root=tmp_path).endswith(" with uncommitted changes")


def test_it_is_checked_from_the_repository_root_wherever_it_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _repo(tmp_path)
    (tmp_path / "src" / "a.py").write_text("x = 2\n")
    monkeypatch.chdir(tmp_path / "src")  # pathspecs would be src/src from here
    assert code_commit(root=tmp_path).endswith(" with uncommitted changes")
