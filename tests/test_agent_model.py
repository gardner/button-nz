"""Tests for button_nz.agent.model.ChatModel against a mocked Meta Model API."""

import json
from pathlib import Path
from typing import Any

import httpx2  # the HTTP client the openai SDK is built on
import pytest
from openai import DefaultHttpxClient, OpenAI

from button_nz.agent.loop import Turn
from button_nz.agent.model import META_BASE_URL, ChatModel, ModelReplyError


def _completion(message: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": "c1",
        "object": "chat.completion",
        "created": 0,
        "model": "muse-spark-1.3",
        "choices": [{"index": 0, "finish_reason": "tool_calls", "message": message}],
    }


def _tool_call(code: str) -> dict[str, Any]:
    arguments = json.dumps({"code": code})
    call = {
        "id": "t1",
        "type": "function",
        "function": {"name": "run_blender_script", "arguments": arguments},
    }
    return {"role": "assistant", "content": None, "tool_calls": [call]}


def _model(reply: dict[str, Any]) -> tuple[ChatModel, list[dict[str, Any]]]:
    sent: list[dict[str, Any]] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        assert str(request.url) == f"{META_BASE_URL}/chat/completions"
        sent.append(json.loads(request.content))
        return httpx2.Response(200, json=_completion(reply))

    client = OpenAI(
        base_url=META_BASE_URL,
        api_key="test",
        http_client=DefaultHttpxClient(transport=httpx2.MockTransport(handler)),
    )
    return ChatModel(client), sent


def test_returns_the_script_from_the_tool_call() -> None:
    model, sent = _model(_tool_call("bpy.ops.mesh.primitive_cube_add()"))
    script = model.propose([Turn("system", "contract"), Turn("user", "brief")])
    assert script == "bpy.ops.mesh.primitive_cube_add()"
    request = sent[0]
    assert request["model"] == "muse-spark-1.3"
    assert request["tools"][0]["function"]["name"] == "run_blender_script"
    assert request["tool_choice"] == "required"


def test_attempts_become_tool_calls_and_results_with_the_render(tmp_path: Path) -> None:
    render = tmp_path / "design.png"
    render.write_bytes(b"\x89PNG")
    model, sent = _model(_tool_call("x"))
    model.propose(
        [
            Turn("system", "contract"),
            Turn("user", "brief"),
            Turn("design", "first script"),
            Turn("feedback", "title_boundary_setback: fail", render),
        ]
    )
    messages = sent[0]["messages"]
    assert [m["role"] for m in messages] == ["system", "user", "assistant", "tool", "user"]
    call = messages[2]["tool_calls"][0]
    assert json.loads(call["function"]["arguments"]) == {"code": "first script"}
    assert messages[3]["tool_call_id"] == call["id"]
    assert messages[3]["content"] == "title_boundary_setback: fail"
    image = messages[4]["content"][1]["image_url"]["url"]
    assert image.startswith("data:image/png;base64,")


def test_a_reply_without_a_script_raises() -> None:
    model, _ = _model({"role": "assistant", "content": "I think it passes."})
    with pytest.raises(ModelReplyError, match="run_blender_script"):
        model.propose([Turn("system", "contract"), Turn("user", "brief")])


def test_from_env_needs_a_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MODEL_API_KEY", raising=False)
    with pytest.raises(KeyError, match="MODEL_API_KEY"):
        ChatModel.from_env()


@pytest.mark.parametrize("arguments", ['{"code": "x', "[1, 2]", '"just a string"'])
def test_malformed_tool_arguments_are_a_reply_error(arguments: str) -> None:
    call = {
        "id": "t1",
        "type": "function",
        "function": {"name": "run_blender_script", "arguments": arguments},
    }
    model, _ = _model({"role": "assistant", "content": None, "tool_calls": [call]})
    with pytest.raises(ModelReplyError, match="malformed"):
        model.propose([Turn("system", "c"), Turn("user", "b")])
