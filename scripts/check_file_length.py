"""Fail if any given source file exceeds the line limit.

Used by the ``file-length`` and ``file-length-ts`` pre-commit hooks for
Python and TypeScript source. Test files are excluded by the hook
configuration, not by this script.
"""

import argparse
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import cast


def count_lines(path: Path) -> int:
    """Count lines in ``path``, including a final line without a newline."""
    return len(path.read_text(encoding="utf-8", errors="replace").splitlines())


def find_violations(paths: Iterable[Path], max_lines: int) -> list[str]:
    """Return one message per file longer than ``max_lines``."""
    violations: list[str] = []
    for path in paths:
        lines = count_lines(path)
        if lines > max_lines:
            violations.append(f"{path}: {lines} lines exceeds maximum {max_lines}")
    return violations


def main(argv: Sequence[str] | None = None) -> int:
    """Check files from the command line. Return 1 on any violation."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-lines", type=int, default=500)
    parser.add_argument("files", nargs="*", type=Path)
    args = parser.parse_args(argv)
    max_lines = cast("int", args.max_lines)
    files = cast("list[Path]", args.files)
    violations = find_violations(files, max_lines)
    for violation in violations:
        print(violation)
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
