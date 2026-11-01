"""Which code made a result: recorded in the results it writes."""

import subprocess

RESULT_INPUTS = ("src", "data", "pyproject.toml", "uv.lock")  # what results depend on


def code_commit() -> str:
    """HEAD, marked if anything the results depend on differs from it, so a
    result is never credited to a commit that wouldn't make it. Old results
    deleted to make way for a run's don't count."""

    def git(*args: str) -> str:
        return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout

    commit = git("rev-parse", "--short", "HEAD").strip()
    changed = git("status", "--porcelain", "--untracked-files=no", "--", *RESULT_INPUTS).strip()
    return commit + (" with uncommitted changes" if changed else "")
