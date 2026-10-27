"""Tests for scripts/check_file_length.py."""

from pathlib import Path

from check_file_length import count_lines, find_violations, main


def _write(path: Path, lines: int) -> Path:
    path.write_text("\n".join(f"line {i}" for i in range(lines)) + "\n", encoding="utf-8")
    return path


def test_count_lines_counts_final_line_without_newline(tmp_path: Path) -> None:
    target = tmp_path / "a.py"
    target.write_text("one\ntwo", encoding="utf-8")
    assert count_lines(target) == 2


def test_find_violations_flags_only_files_over_limit(tmp_path: Path) -> None:
    small = _write(tmp_path / "small.py", 3)
    big = _write(tmp_path / "big.py", 7)
    violations = find_violations([small, big], max_lines=5)
    assert len(violations) == 1
    assert "big.py" in violations[0]
    assert "7" in violations[0]


def test_main_returns_zero_when_all_files_within_limit(tmp_path: Path) -> None:
    small = _write(tmp_path / "small.py", 2)
    assert main(["--max-lines", "5", str(small)]) == 0


def test_main_returns_one_when_a_file_exceeds_limit(tmp_path: Path) -> None:
    big = _write(tmp_path / "big.py", 9)
    assert main(["--max-lines", "5", str(big)]) == 1
