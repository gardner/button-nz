"""A design model on the Meta Model API (OpenAI-compatible), e.g. Muse Spark.

Each design attempt goes back to the model as its own ``run_blender_script``
tool call, the evaluator's verdict as that call's result, and the preview
render as an image, so the model sees what it built as well as the numbers.
"""

import base64
import json
import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from openai import OpenAI

from button_nz.agent.conversation import ModelReplyError, Observe, Turn
from button_nz.agent.observe import OBSERVATION_TOOLS

__all__ = ["META_BASE_URL", "ChatModel", "ModelReplyError"]

META_BASE_URL = "https://api.meta.ai/v1"
TOOL = "run_blender_script"
TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": TOOL,
            "description": "Run a complete Blender Python script in the site scene. "
            "It must create the mesh object 'Dwelling'.",
            "parameters": {
                "type": "object",
                "properties": {"code": {"type": "string", "description": "The bpy script."}},
                "required": ["code"],
            },
        },
    }
]


@dataclass(frozen=True)
class ChatModel:
    client: OpenAI
    model: str = "muse-spark-1.3"

    @classmethod
    def from_env(cls, model: str = "muse-spark-1.3") -> ChatModel:
        """A client for the Meta Model API using the ``MODEL_API_KEY`` key."""
        key = os.environ.get("MODEL_API_KEY")
        if not key:
            raise KeyError("MODEL_API_KEY is not set: get a Meta Model API key")
        return cls(OpenAI(base_url=META_BASE_URL, api_key=key), model)

    def propose(self, conversation: Sequence[Turn], allow_observations: bool) -> str | Observe:
        tools = TOOLS + (OBSERVATION_TOOLS if allow_observations else [])
        response = self.client.chat.completions.create(
            model=self.model,
            messages=cast("Any", _messages(conversation)),
            tools=cast("Any", tools),
            tool_choice="required",
        )
        message = response.choices[0].message
        offered = {t["function"]["name"] for t in tools}
        for call in message.tool_calls or []:
            if call.type != "function" or call.function.name not in offered:
                continue
            arguments = _arguments(call.function.arguments)
            if call.function.name != TOOL:
                return Observe(call.function.name, arguments)
            code = arguments.get("code")
            if isinstance(code, str) and code.strip():
                return code
        raise ModelReplyError(
            f"The reply did not call {TOOL} with a script. Call it with your script."
        )


def _arguments(raw: str | None) -> dict[str, Any]:
    """A tool call's arguments as a JSON object, or a ModelReplyError the model can
    act on (e.g. a script cut off by the output limit)."""
    try:
        arguments = json.loads(raw or "{}")
    except json.JSONDecodeError as error:
        raise ModelReplyError(
            f"Your tool call's arguments were malformed or truncated JSON ({error.msg}). "
            "Send the complete call again; keep the script short enough to fit."
        ) from error
    if not isinstance(arguments, dict):
        raise ModelReplyError("Your tool call's arguments were malformed: expected a JSON object.")
    return cast("dict[str, Any]", arguments)


def _messages(conversation: Sequence[Turn]) -> list[dict[str, Any]]:
    """OpenAI messages: designs and observation requests become the model's tool
    calls, and feedback and observations their results (with the image)."""
    messages: list[dict[str, Any]] = []
    for n, turn in enumerate(conversation):
        if turn.role in ("system", "user"):
            messages.append({"role": turn.role, "content": turn.text})
        elif turn.role in ("design", "request"):
            messages.append({"role": "assistant", "content": None, "tool_calls": [_call(n, turn)]})
        else:  # feedback or an observation answers the call before it
            messages.append({"role": "tool", "tool_call_id": f"call_{n - 1}", "content": turn.text})
            if turn.image is not None:
                caption = (
                    "The preview render of that attempt:"
                    if turn.role == "feedback"
                    else "The view:"
                )
                messages.append(_image_message(caption, turn.image))
    return messages


def _call(n: int, turn: Turn) -> dict[str, Any]:
    if turn.role == "design":
        name, arguments = TOOL, json.dumps({"code": turn.text})
    else:
        request = json.loads(turn.text)
        name, arguments = request["tool"], json.dumps(request["arguments"])
    return {
        "id": f"call_{n}",
        "type": "function",
        "function": {"name": name, "arguments": arguments},
    }


def _image_message(caption: str, image: Path) -> dict[str, Any]:
    data = base64.b64encode(image.read_bytes()).decode("ascii")
    return {
        "role": "user",
        "content": [
            {"type": "text", "text": caption},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{data}"}},
        ],
    }
