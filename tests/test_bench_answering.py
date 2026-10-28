"""Tests for button_nz.bench.answering.ChatAnswerer against a mocked Meta Model API."""

import json
from typing import Any

import httpx2  # the HTTP client the openai SDK is built on
import pytest
from openai import DefaultHttpxClient, OpenAI

from button_nz.agent.conversation import ModelReplyError, Observe
from button_nz.bench.answering import ANSWER_TOOL, ChatAnswerer, QaTurn

BASE = "https://api.meta.ai/v1"


def _answerer(*replies: dict[str, Any]) -> tuple[ChatAnswerer, list[dict[str, Any]]]:
    sent: list[dict[str, Any]] = []
    queue = list(replies)

    def handler(request: httpx2.Request) -> httpx2.Response:
        sent.append(json.loads(request.content))
        message = queue.pop(0)
        choice = {"index": 0, "finish_reason": "tool_calls", "message": message}
        body = {"id": "c", "object": "chat.completion", "created": 0, "model": "m"}
        return httpx2.Response(200, json=body | {"choices": [choice]})

    client = OpenAI(
        base_url=BASE,
        api_key="test",
        http_client=DefaultHttpxClient(transport=httpx2.MockTransport(handler)),
    )
    return ChatAnswerer(client), sent


def _call(name: str, arguments: dict[str, Any] | str) -> dict[str, Any]:
    raw = arguments if isinstance(arguments, str) else json.dumps(arguments)
    call = {"id": "t1", "type": "function", "function": {"name": name, "arguments": raw}}
    return {"role": "assistant", "content": None, "tool_calls": [call]}


QUESTION = [
    QaTurn("system", "Answer questions."),
    QaTurn(
        "question", "Which way?", (("Aerial photograph", b"\x89PNG-a"), ("Slope", b"\x89PNG-s"))
    ),
]


def test_the_answer_comes_from_the_answer_tool() -> None:
    answerer, sent = _answerer(_call(ANSWER_TOOL, {"answer": "SW"}))
    assert answerer.answer(QUESTION, allow_observations=False) == "SW"
    request = sent[0]
    assert [t["function"]["name"] for t in request["tools"]] == [ANSWER_TOOL]
    assert request["tool_choice"] == "required"
    content = request["messages"][1]["content"]
    assert [part["type"] for part in content] == ["text", "text", "image_url", "text", "image_url"]
    assert content[2]["image_url"]["url"].startswith("data:image/png;base64,")


def test_observation_tools_are_offered_only_when_allowed() -> None:
    answerer, sent = _answerer(_call("render_contours", {"interval_m": 0.5}))
    action = answerer.answer(QUESTION, allow_observations=True)
    assert action == Observe("render_contours", {"interval_m": 0.5})
    offered = {t["function"]["name"] for t in sent[0]["tools"]}
    assert {ANSWER_TOOL, "render_contours", "inspect_elevation"} <= offered


def test_requests_and_observations_become_tool_calls_and_results() -> None:
    answerer, sent = _answerer(_call(ANSWER_TOOL, {"answer": "1.5"}))
    turns = [
        *QUESTION,
        QaTurn("request", json.dumps({"tool": "render_contours", "arguments": {}})),
        QaTurn("observation", "Contours every 0.25 m", (("View", b"\x89PNG-v"),)),
    ]
    answerer.answer(turns, allow_observations=True)
    roles = [m["role"] for m in sent[0]["messages"]]
    assert roles == ["system", "user", "assistant", "tool", "user"]
    assert sent[0]["messages"][3]["tool_call_id"] == sent[0]["messages"][2]["tool_calls"][0]["id"]


@pytest.mark.parametrize(
    "reply",
    [
        {"role": "assistant", "content": "SW", "tool_calls": None},
        _call(ANSWER_TOOL, '{"answer": '),
        _call(ANSWER_TOOL, {"answer": ""}),
        _call("run_blender_script", {"code": "x"}),
    ],
)
def test_a_reply_without_an_answer_is_an_error(reply: dict[str, Any]) -> None:
    answerer, _ = _answerer(reply)
    with pytest.raises(ModelReplyError):
        answerer.answer(QUESTION, allow_observations=False)
