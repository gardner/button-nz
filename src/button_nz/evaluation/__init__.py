"""Independent, deterministic evaluation of proposed dwellings. No model, and
no way for a model to override a failed check."""

from button_nz.evaluation.checks import ground_range
from button_nz.evaluation.evaluate import evaluate
from button_nz.evaluation.model import (
    Check,
    InvalidProposal,
    Proposal,
    Report,
    SiteContext,
    Status,
)

__all__ = [
    "Check",
    "InvalidProposal",
    "Proposal",
    "Report",
    "SiteContext",
    "Status",
    "evaluate",
    "ground_range",
]
