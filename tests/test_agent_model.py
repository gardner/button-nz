"""Tests for button_nz.agent.model.ChatModel against a mocked Meta Model API."""

import json
from pathlib import Path
from typing import Any

import httpx2  # the HTTP client the openai SDK is built on
import pytest
from openai import DefaultHttpxClient, OpenAI

from button_nz.agent.conversation import Observe, Turn
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
    script = model.propose([Turn("system", "contract"), Turn("user", "brief")], False)
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
        ],
        False,
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
        model.propose([Turn("system", "contract"), Turn("user", "brief")], False)


def test_from_env_needs_a_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MODEL_API_KEY", raising=False)
    with pytest.raises(KeyError, match="MODEL_API_KEY"):
        ChatModel.from_env()


def _observation_call(tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
    call = {
        "id": "o1",
        "type": "function",
        "function": {"name": tool, "arguments": json.dumps(arguments)},
    }
    return {"role": "assistant", "content": None, "tool_calls": [call]}


def test_observation_tools_are_offered_only_when_allowed() -> None:
    model, sent = _model(_tool_call("x"))
    model.propose([Turn("system", "c"), Turn("user", "b")], True)
    model.propose([Turn("system", "c"), Turn("user", "b")], False)
    offered = [{t["function"]["name"] for t in request["tools"]} for request in sent]
    assert {"run_blender_script", "render_hillshade", "inspect_elevation"} <= offered[0]
    assert offered[1] == {"run_blender_script"}


def test_an_observation_call_becomes_a_request() -> None:
    model, _ = _model(_observation_call("render_contours", {"interval_m": 0.5}))
    action = model.propose([Turn("system", "c"), Turn("user", "b")], True)
    assert action == Observe("render_contours", {"interval_m": 0.5})


def test_requests_and_observations_become_tool_calls_and_results(tmp_path: Path) -> None:
    view = tmp_path / "observation-1.png"
    view.write_bytes(b"\x89PNG")
    model, sent = _model(_tool_call("x"))
    request = json.dumps({"tool": "render_contours", "arguments": {"interval_m": 0.5}})
    model.propose(
        [
            Turn("system", "c"),
            Turn("user", "b"),
            Turn("request", request),
            Turn("observation", "Contours every 0.5 m", view),
        ],
        True,
    )
    messages = sent[0]["messages"]
    assert [m["role"] for m in messages] == ["system", "user", "assistant", "tool", "user"]
    call = messages[2]["tool_calls"][0]
    assert call["function"]["name"] == "render_contours"
    assert json.loads(call["function"]["arguments"]) == {"interval_m": 0.5}
    assert messages[3]["tool_call_id"] == call["id"]
    assert messages[4]["content"][1]["image_url"]["url"].startswith("data:image/png;base64,")


@pytest.mark.parametrize("arguments", ['{"code": "x', "[1, 2]", '"just a string"'])
def test_malformed_tool_arguments_are_a_reply_error(arguments: str) -> None:
    call = {
        "id": "t1",
        "type": "function",
        "function": {"name": "run_blender_script", "arguments": arguments},
    }
    model, _ = _model({"role": "assistant", "content": None, "tool_calls": [call]})
    with pytest.raises(ModelReplyError, match="malformed"):
        model.propose([Turn("system", "c"), Turn("user", "b")], False)
