"""Tests for logging setup (a packaged windowed build has no stderr)."""

from __future__ import annotations

import logging

import pytest

from biounlock_agent import logging_setup


def _capture(monkeypatch: pytest.MonkeyPatch) -> dict:
    captured: dict = {}
    monkeypatch.setattr(logging_setup.logging, "basicConfig", lambda **kwargs: captured.update(kwargs))
    return captured


def test_stderr_handler_is_used_normally(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    captured = _capture(monkeypatch)
    logging_setup.configure_logging("INFO", tmp_path / "agent.log")
    kinds = [type(handler) for handler in captured["handlers"]]
    assert logging.StreamHandler in kinds
    assert logging.FileHandler in kinds


def test_missing_stderr_does_not_break_the_file_log(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setattr(logging_setup.sys, "stderr", None)
    captured = _capture(monkeypatch)
    logging_setup.configure_logging("INFO", tmp_path / "agent.log")
    assert [type(handler) for handler in captured["handlers"]] == [logging.FileHandler]


def test_no_destination_falls_back_to_a_null_handler(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(logging_setup.sys, "stderr", None)
    captured = _capture(monkeypatch)
    logging_setup.configure_logging("INFO")
    assert [type(handler) for handler in captured["handlers"]] == [logging.NullHandler]
