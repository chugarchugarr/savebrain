import json
from pathlib import Path

import pytest

from tro_frontier.benchmark_smoke import (
    summarize_swebench,
    summarize_terminalbench,
    verify_swebench,
    verify_terminalbench,
)


def test_verify_swebench_requires_resolved_instance(tmp_path: Path) -> None:
    report = tmp_path / "report.json"
    report.write_text(
        json.dumps(
            {
                "completed_ids": ["sympy__sympy-20590"],
                "resolved_ids": ["sympy__sympy-20590"],
                "error_ids": [],
            }
        )
    )

    result = verify_swebench(report, "sympy__sympy-20590")

    assert result["resolved"] is True
    with pytest.raises(RuntimeError, match="did not complete"):
        verify_swebench(report, "missing__instance-1")


def test_summarize_swebench_accepts_completed_unresolved_instance(tmp_path: Path) -> None:
    report = tmp_path / "report.json"
    report.write_text(
        json.dumps(
            {
                "completed_ids": ["sympy__sympy-20590"],
                "resolved_ids": [],
                "error_ids": [],
            }
        )
    )

    result = summarize_swebench(report, "sympy__sympy-20590")

    assert result["resolved"] is False
    assert result["score"] == 0
    with pytest.raises(RuntimeError, match="did not resolve"):
        verify_swebench(report, "sympy__sympy-20590")


def test_verify_terminalbench_requires_reward_one(tmp_path: Path) -> None:
    passed = tmp_path / "jobs" / "job" / "trial"
    passed.mkdir(parents=True)
    (passed / "result.json").write_text(
        json.dumps(
            {
                "trial_name": "trial",
                "task_name": "task",
                "verifier_result": {"rewards": {"reward": 1.0}},
                "exception_info": None,
            }
        )
    )

    result = verify_terminalbench(tmp_path / "jobs")

    assert result["passed"] == 1
    assert result["trials"][0]["reward"] == 1.0


def test_verify_terminalbench_rejects_failed_oracle(tmp_path: Path) -> None:
    failed = tmp_path / "jobs" / "job" / "trial"
    failed.mkdir(parents=True)
    (failed / "result.json").write_text(
        json.dumps(
            {
                "trial_name": "trial",
                "task_name": "task",
                "verifier_result": {"rewards": {"reward": 0.0}},
                "exception_info": None,
            }
        )
    )

    with pytest.raises(RuntimeError, match="oracle smoke failed"):
        verify_terminalbench(tmp_path / "jobs")

    result = summarize_terminalbench(tmp_path / "jobs")
    assert result["score"] == 0.0
