"""Which code made a result: recorded in the results it writes."""

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]  # the repository
RESULT_INPUTS = ("src", "data", "pyproject.toml", "uv.lock")  # what results depend on


def code_commit(*inputs: str, root: Path = ROOT) -> str:
    """HEAD, marked if anything the results depend on (``RESULT_INPUTS``, and
    ``inputs``: other results read, relative to ``root``) differs from it,
    new files included, so a result is never credited to a commit that
    wouldn't make it. Git runs at ``root``, wherever this is run from. Old
    results deleted to make way for a run's don't count."""

    def git(*args: str) -> str:
        done = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True)
        return done.stdout

    commit = git("rev-parse", "--short", "HEAD").strip()
    changed = git("status", "--porcelain", "--untracked-files=all", "--", *RESULT_INPUTS, *inputs)
    return commit + (" with uncommitted changes" if changed.strip() else "")
