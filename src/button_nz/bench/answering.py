"""Asking a model Experiment A's questions, independent of how it is reached,
and ``ChatAnswerer``, which asks one on the Meta Model API (OpenAI-compatible).

The model answers by calling ``submit_answer``; under the ``agent`` condition
it may first call the observation tools, whose results come back as tool
results with their images.
"""

import base64
import json
import os
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal, Protocol, cast

from openai import OpenAI

from button_nz.agent.conversation import ModelReplyError, Observe
from button_nz.agent.model import META_BASE_URL
from button_nz.agent.observe import OBSERVATION_TOOLS

ANSWER_TOOL = "submit_answer"
TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": ANSWER_TOOL,
            "description": "Give your answer: only what the question asks for.",
            "parameters": {
                "type": "object",
                "properties": {"answer": {"type": "string"}},
                "required": ["answer"],
            },
        },
    }
]

type QaRole = Literal["system", "question", "request", "observation"]


@dataclass(frozen=True)
class QaTurn:
    role: QaRole
    text: str
    images: tuple[tuple[str, bytes], ...] = ()  # (caption, PNG)


class Answerer(Protocol):
    def answer(self, turns: Sequence[QaTurn], allow_observations: bool) -> str | Observe:
        """The answer, or (if ``allow_observations``) an observation request.
        Raises ModelReplyError if the reply has neither."""
        ...


@dataclass(frozen=True)
class ChatAnswerer:
    client: OpenAI
    model: str = "muse-spark-1.3"

    @classmethod
    def from_env(cls, model: str = "muse-spark-1.3") -> ChatAnswerer:
        key = os.environ.get("MODEL_API_KEY")
        if not key:
            raise KeyError("MODEL_API_KEY is not set: get a Meta Model API key")
        return cls(OpenAI(base_url=META_BASE_URL, api_key=key), model)

    def answer(self, turns: Sequence[QaTurn], allow_observations: bool) -> str | Observe:
        tools = TOOLS + (OBSERVATION_TOOLS if allow_observations else [])
        response = self.client.chat.completions.create(
            model=self.model,
            messages=cast("Any", _messages(turns)),
            tools=cast("Any", tools),
            tool_choice="required",
        )
        offered = {t["function"]["name"] for t in tools}
        for call in response.choices[0].message.tool_calls or []:
            if call.type != "function" or call.function.name not in offered:
                continue
            arguments = _arguments(call.function.arguments)
            if call.function.name != ANSWER_TOOL:
                return Observe(call.function.name, arguments)
            answer = arguments.get("answer")
            if isinstance(answer, str) and answer.strip():
                return answer
        raise ModelReplyError(f"The reply did not call {ANSWER_TOOL} with an answer.")


def _messages(turns: Sequence[QaTurn]) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    for n, turn in enumerate(turns):
        if turn.role == "system":
            messages.append({"role": "system", "content": turn.text})
        elif turn.role == "question":
            messages.append({"role": "user", "content": _content(turn.text, turn.images)})
        elif turn.role == "request":
            request = json.loads(turn.text)
            arguments = json.dumps(request["arguments"])
            function = {"name": request["tool"], "arguments": arguments}
            call = {"id": f"call-{n}", "type": "function", "function": function}
            messages.append({"role": "assistant", "content": None, "tool_calls": [call]})
        else:  # an observation: the result of the request just before it
            messages.append({"role": "tool", "tool_call_id": f"call-{n - 1}", "content": turn.text})
            if turn.images:
                messages.append({"role": "user", "content": _content("The view:", turn.images)})
    return messages


def _content(text: str, images: Sequence[tuple[str, bytes]]) -> list[dict[str, Any]]:
    parts: list[dict[str, Any]] = [{"type": "text", "text": text}]
    for caption, png in images:
        url = "data:image/png;base64," + base64.b64encode(png).decode("ascii")
        parts += [
            {"type": "text", "text": caption},
            {"type": "image_url", "image_url": {"url": url}},
        ]
    return parts


def _arguments(raw: str | None) -> dict[str, Any]:
    try:
        arguments = json.loads(raw or "{}")
    except json.JSONDecodeError as error:
        raise ModelReplyError(
            f"Your tool call's arguments were malformed ({error.msg})."
        ) from error
    if not isinstance(arguments, dict):
        raise ModelReplyError("Your tool call's arguments were malformed: expected an object.")
    return cast("dict[str, Any]", arguments)
