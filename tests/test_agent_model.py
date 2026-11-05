"""Tests for button_nz.agent.model.ChatModel against a mocked Meta Model API."""

import base64
import io
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import httpx2  # the HTTP client the openai SDK is built on
import pytest
from openai import DefaultHttpxClient, OpenAI
from PIL import Image

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


SPEC = {"placement": 2, "floor_z_m": 0.4, "roof": {"form": "flat", "pitch_deg": 0}, "eaves_m": 0}


def _tool_call(spec: dict[str, Any] | None = None) -> dict[str, Any]:
    arguments = json.dumps(SPEC if spec is None else spec)
    call = {
        "id": "t1",
        "type": "function",
        "function": {"name": "propose_design", "arguments": arguments},
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


def test_returns_the_spec_from_the_tool_call() -> None:
    model, sent = _model(_tool_call())
    spec = model.propose([Turn("system", "contract"), Turn("user", "brief")], False)
    assert isinstance(spec, str) and json.loads(spec) == SPEC
    request = sent[0]
    assert request["model"] == "muse-spark-1.3"
    tool = request["tools"][0]["function"]
    assert tool["name"] == "propose_design"
    assert "placement" in tool["parameters"]["properties"]
    assert request["tool_choice"] == "auto"  # the Meta Model API accepts nothing else


def test_attempts_become_tool_calls_and_results_with_the_render(tmp_path: Path) -> None:
    render = png(tmp_path / "design.png", (64, 48))
    model, sent = _model(_tool_call())
    model.propose(
        [
            Turn("system", "contract"),
            Turn("user", "brief"),
            Turn("design", json.dumps(SPEC)),
            Turn("feedback", "title_boundary_setback: fail", render),
        ],
        False,
    )
    messages = sent[0]["messages"]
    assert [m["role"] for m in messages] == ["system", "user", "assistant", "tool", "user"]
    call = messages[2]["tool_calls"][0]
    assert call["function"]["name"] == "propose_design"
    assert json.loads(call["function"]["arguments"]) == SPEC
    assert messages[3]["tool_call_id"] == call["id"]
    assert messages[3]["content"] == "title_boundary_setback: fail"
    image = messages[4]["content"][1]["image_url"]["url"]
    assert image.startswith("data:image/png;base64,")


def test_a_reply_without_a_spec_raises() -> None:
    model, _ = _model({"role": "assistant", "content": "I think it passes."})
    with pytest.raises(ModelReplyError, match="propose_design"):
        model.propose([Turn("system", "contract"), Turn("user", "brief")], False)


def test_an_empty_spec_is_no_spec() -> None:
    model, _ = _model(_tool_call({}))
    with pytest.raises(ModelReplyError, match="design spec"):
        model.propose([Turn("system", "contract"), Turn("user", "brief")], False)


def test_a_design_that_sent_no_spec_is_resent_as_an_empty_call() -> None:
    model, sent = _model(_tool_call())
    model.propose([Turn("user", "b"), Turn("design", ""), Turn("feedback", "no spec")], False)
    call = sent[0]["messages"][1]["tool_calls"][0]
    assert call["function"]["arguments"] == "{}"


def test_from_env_needs_a_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("META_API_KEY", raising=False)
    with pytest.raises(KeyError, match="META_API_KEY"):
        ChatModel.from_env()


def _observation_call(tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
    call = {
        "id": "o1",
        "type": "function",
        "function": {"name": tool, "arguments": json.dumps(arguments)},
    }
    return {"role": "assistant", "content": None, "tool_calls": [call]}


def test_observation_tools_are_offered_only_when_allowed() -> None:
    model, sent = _model(_tool_call())
    model.propose([Turn("system", "c"), Turn("user", "b")], True)
    model.propose([Turn("system", "c"), Turn("user", "b")], False)
    offered = [{t["function"]["name"] for t in request["tools"]} for request in sent]
    assert {"propose_design", "render_hillshade", "inspect_elevation"} <= offered[0]
    assert offered[1] == {"propose_design"}


def test_an_observation_call_becomes_a_request() -> None:
    model, _ = _model(_observation_call("render_contours", {"interval_m": 0.5}))
    action = model.propose([Turn("system", "c"), Turn("user", "b")], True)
    assert action == Observe("render_contours", {"interval_m": 0.5})


def test_requests_and_observations_become_tool_calls_and_results(tmp_path: Path) -> None:
    view = png(tmp_path / "observation-1.png", (64, 64))
    model, sent = _model(_tool_call())
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


@pytest.mark.parametrize("arguments", ['{"placement": 1', "[1, 2]", '"just a string"'])
def test_malformed_tool_arguments_are_a_reply_error(arguments: str) -> None:
    call = {
        "id": "t1",
        "type": "function",
        "function": {"name": "propose_design", "arguments": arguments},
    }
    model, _ = _model({"role": "assistant", "content": None, "tool_calls": [call]})
    with pytest.raises(ModelReplyError, match="malformed"):
        model.propose([Turn("system", "c"), Turn("user", "b")], False)


def test_a_reasoning_effort_is_sent_only_when_chosen() -> None:
    model, sent = _model(_tool_call())
    model.propose([Turn("user", "brief")], False)
    assert "reasoning_effort" not in sent[0]  # the API's default
    effortful = replace(model, reasoning_effort="max")
    effortful.propose([Turn("user", "brief")], False)
    assert sent[1]["reasoning_effort"] == "max"


def png(path: Path, size: tuple[int, int]) -> Path:
    Image.new("RGB", size, (120, 160, 90)).save(path)
    return path


def sent_image(tmp_path: Path, image: Path) -> tuple[Image.Image, bytes]:
    model, sent = _model(_tool_call())
    model.propose(
        [
            Turn("system", "c"),
            Turn("user", "b"),
            Turn("design", "{}"),
            Turn("feedback", "f", image),
        ],
        False,
    )
    url = sent[0]["messages"][4]["content"][1]["image_url"]["url"]
    data = base64.b64decode(url.split(",", 1)[1])
    return Image.open(io.BytesIO(data)), data


def test_a_large_render_is_sent_smaller_keeping_its_shape(tmp_path: Path) -> None:
    sent, _ = sent_image(tmp_path, png(tmp_path / "design.png", (1280, 960)))
    assert sent.size == (800, 600)  # about 600 tokens, not 1,530 (measured on the API)


def test_an_image_already_small_enough_is_sent_as_it_is(tmp_path: Path) -> None:
    view = png(tmp_path / "observation-1.png", (672, 688))
    sent, data = sent_image(tmp_path, view)
    assert sent.size == (672, 688) and data == view.read_bytes()


def test_views_given_with_the_brief_are_part_of_its_message(tmp_path: Path) -> None:
    """The standard views come in the brief's own message, each captioned by its
    text: one first message, with no tool call the model never made."""
    hillshade = png(tmp_path / "observation-1.png", (64, 64))
    contours = png(tmp_path / "observation-2.png", (64, 64))
    model, sent = _model(_tool_call())
    model.propose(
        [
            Turn("system", "c"),
            Turn("user", "the brief"),
            Turn("view", "Shaded relief.", hillshade),
            Turn("view", "Contours every 0.25 m.", contours),
        ],
        True,
    )
    messages = sent[0]["messages"]
    assert [m["role"] for m in messages] == ["system", "user"]
    parts = messages[1]["content"]
    assert [p["type"] for p in parts] == ["text", "text", "image_url", "text", "image_url"]
    assert [p["text"] for p in parts if p["type"] == "text"] == [
        "the brief",
        "Shaded relief.",
        "Contours every 0.25 m.",
    ]
    assert parts[2]["image_url"]["url"].startswith("data:image/png;base64,")
