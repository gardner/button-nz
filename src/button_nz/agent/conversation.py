"""The conversation between the design loop and a model, independent of any API."""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

type Role = Literal["system", "user", "design", "feedback"]


@dataclass(frozen=True)
class Turn:
    role: Role
    text: str
    image: Path | None = None  # the attempt's preview render, for feedback turns


class ModelReplyError(ValueError):
    """The model replied without a design script."""


class Model(Protocol):
    def propose(self, conversation: Sequence[Turn]) -> str:
        """The next design script. Raises ModelReplyError if the reply has none."""
        ...
