"""Smoke tests for the package entry point."""

import pytest

import button_nz


def test_main_prints_greeting(capsys: pytest.CaptureFixture[str]) -> None:
    button_nz.main()
    assert "button-nz" in capsys.readouterr().out
