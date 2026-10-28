"""Tests for scripts/review-metrics.sh, run against fixture execution files."""

import json
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "review-metrics.sh"
COMMENT_TOOL = "mcp__github_inline_comment__create_inline_comment"


def _tool_use(name: str, tool_id: str = "toolu_x", **tool_input: str) -> object:
    content = [{"type": "tool_use", "id": tool_id, "name": name, "input": tool_input}]
    return {"type": "assistant", "message": {"content": content}}


def _tool_result(tool_id: str, is_error: bool = False) -> object:
    content = [{"type": "tool_result", "tool_use_id": tool_id, "is_error": is_error}]
    return {"type": "user", "message": {"content": content}}


def _result(*denials: object, is_error: bool = False, result: str = "done") -> object:
    return {
        "type": "result",
        "subtype": "success",
        "is_error": is_error,
        "result": result,
        "num_turns": 7,
        "duration_ms": 125_000,
        "total_cost_usd": 1.234,
        "permission_denials": list(denials),
    }


INIT = {"type": "system", "subtype": "init", "model": "claude-opus-5-5"}


def _run(tmp_path: Path, *messages: object) -> subprocess.CompletedProcess[str]:
    trace = tmp_path / "trace.json"
    trace.write_text(json.dumps(list(messages)), encoding="utf-8")
    return subprocess.run([str(SCRIPT), str(trace)], capture_output=True, text=True)


def test_summarises_a_clean_run(tmp_path: Path) -> None:
    result = _run(
        tmp_path,
        INIT,
        _tool_use("Bash", command="git diff a...b"),
        _tool_use("Bash", command="cat x.py"),
        _result(),
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == (
        "## Claude review\n\n"
        "| Model | Turns | Duration | Cost | Findings posted | Denied calls |\n"
        "| --- | --- | --- | --- | --- | --- |\n"
        "| claude-opus-5-5 | 7 | 125s | $1.23 | 0 | 0 |\n\n"
        "**Tool calls:** Bash 2\n"
    )


def test_counts_findings_and_lists_denied_calls(tmp_path: Path) -> None:
    result = _run(
        tmp_path,
        INIT,
        _tool_use(COMMENT_TOOL, "toolu_1", path="a.py", body="P1: bug."),
        _tool_result("toolu_1"),
        _tool_use(COMMENT_TOOL, "toolu_2", path="b.py", body="P2: risk."),
        _tool_result("toolu_2"),
        _tool_use(COMMENT_TOOL, "toolu_3", path="c.py", body="P2: off the diff."),
        _tool_result("toolu_3", is_error=True),
        _tool_use("Bash", command="git log"),
        _result(
            {"tool_name": "Bash", "tool_input": {"command": "curl example.com"}},
            {"tool_name": "Read", "tool_input": {"file_path": "/proc/self/environ"}},
        ),
    )
    assert result.returncode == 0, result.stderr
    assert "| claude-opus-5-5 | 7 | 125s | $1.23 | 2 | 2 |" in result.stdout
    assert f"**Tool calls:** Bash 1, {COMMENT_TOOL} 3\n" in result.stdout
    assert result.stdout.endswith(
        "\n### Denied calls\n\n- Bash `curl example.com`\n- Read `/proc/self/environ`\n"
    )


def test_reports_the_error_of_a_failed_run(tmp_path: Path) -> None:
    result = _run(
        tmp_path,
        INIT,
        _result(is_error=True, result="API Error: 401 OAuth access token is invalid."),
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.endswith("\n**Error:** API Error: 401 OAuth access token is invalid.\n")


def test_run_without_a_result_fails(tmp_path: Path) -> None:
    result = _run(tmp_path, INIT)
    assert result.returncode != 0
    assert "no result" in result.stderr
