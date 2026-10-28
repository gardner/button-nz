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
from typing import Any, cast

from openai import OpenAI

from button_nz.agent.conversation import ModelReplyError, Turn

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

    def propose(self, conversation: Sequence[Turn]) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=cast("Any", _messages(conversation)),
            tools=cast("Any", TOOLS),
            tool_choice="required",
        )
        message = response.choices[0].message
        for call in message.tool_calls or []:
            if call.type == "function" and call.function.name == TOOL:
                code = json.loads(call.function.arguments).get("code")
                if isinstance(code, str) and code.strip():
                    return code
        raise ModelReplyError(
            f"The reply did not call {TOOL} with a script. Call it with your script."
        )


def _messages(conversation: Sequence[Turn]) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    for n, turn in enumerate(conversation):
        call_id = f"attempt_{n}"
        if turn.role in ("system", "user"):
            messages.append({"role": turn.role, "content": turn.text})
        elif turn.role == "design":
            arguments = json.dumps({"code": turn.text})
            call = {
                "id": call_id,
                "type": "function",
                "function": {"name": TOOL, "arguments": arguments},
            }
            messages.append({"role": "assistant", "content": None, "tool_calls": [call]})
        else:  # feedback answers the design turn before it
            messages.append(
                {"role": "tool", "tool_call_id": f"attempt_{n - 1}", "content": turn.text}
            )
            if turn.image is not None:
                data = base64.b64encode(turn.image.read_bytes()).decode("ascii")
                messages.append(
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "The preview render of that attempt:"},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/png;base64,{data}"},
                            },
                        ],
                    }
                )
    return messages
