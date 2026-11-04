"""Tests for button_nz.api.serve's command line: the design model's reasoning effort (#165)."""

import pytest

from button_nz.agent.model import EFFORTS, ChatModel
from button_nz.api.serve import design_model, parse_args


def test_the_reasoning_effort_is_unset_by_default() -> None:
    """Nothing is sent, so the API's default applies: today's behaviour."""
    assert parse_args([]).reasoning_effort is None


@pytest.mark.parametrize("effort", EFFORTS)
def test_each_effort_the_api_accepts_can_be_chosen(effort: str) -> None:
    assert parse_args(["--reasoning-effort", effort]).reasoning_effort == effort


def test_an_effort_the_api_refuses_stops_the_server_starting() -> None:
    with pytest.raises(SystemExit):
        parse_args(["--reasoning-effort", "none"])  # Spark 1.3 refuses it


def test_the_design_worker_gets_a_model_with_the_chosen_effort(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("META_API_KEY", "test-key")
    model = design_model("low")()
    assert isinstance(model, ChatModel) and model.reasoning_effort == "low"
    unset = design_model(None)()
    assert isinstance(unset, ChatModel) and unset.reasoning_effort is None


def test_the_key_is_read_per_job_not_at_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("META_API_KEY", raising=False)
    make = design_model("low")  # the server starts without a key
    with pytest.raises(KeyError, match="META_API_KEY"):
        make()
