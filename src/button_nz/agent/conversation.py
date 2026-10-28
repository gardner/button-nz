"""The conversation between the design loop and a model, independent of any API."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol

# design/feedback: a script and the evaluator's verdict on it.
# request/observation: the model asking for a LiDAR view, and the view.
type Role = Literal["system", "user", "design", "feedback", "request", "observation"]


@dataclass(frozen=True)
class Turn:
    role: Role
    text: str
    image: Path | None = None  # a render or LiDAR view, for feedback and observation turns


@dataclass(frozen=True)
class Observe:
    """The model asking for an observation (a LiDAR view or measurement)."""

    tool: str
    arguments: Mapping[str, Any]


class ModelReplyError(ValueError):
    """The model replied with neither a design script nor an observation request."""


class Model(Protocol):
    def propose(self, conversation: Sequence[Turn], allow_observations: bool) -> str | Observe:
        """The next design script, or (if ``allow_observations``) an observation
        request. Raises ModelReplyError if the reply has neither."""
        ...
