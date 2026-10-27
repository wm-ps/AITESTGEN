"""One clean proof replay by default; EXPLORER_PROOF_RUNS changes it."""

import importlib

import pytest
from explorer_worker import tests_stage


def test_one_proof_run_by_default_and_the_setting_changes_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("EXPLORER_PROOF_RUNS", raising=False)
    assert importlib.reload(tests_stage).PROOF_RUNS == 1
    monkeypatch.setenv("EXPLORER_PROOF_RUNS", "3")
    assert importlib.reload(tests_stage).PROOF_RUNS == 3
    monkeypatch.delenv("EXPLORER_PROOF_RUNS")
    importlib.reload(tests_stage)  # leave the module as other tests expect it
