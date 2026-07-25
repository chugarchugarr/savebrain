from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def summarize_swebench(report_path: Path, instance_id: str) -> dict[str, Any]:
    report = json.loads(report_path.read_text())
    resolved_ids = set(report.get("resolved_ids", []))
    completed_ids = set(report.get("completed_ids", []))
    error_ids = set(report.get("error_ids", []))
    if instance_id not in completed_ids or instance_id in error_ids:
        raise RuntimeError(
            f"SWE-bench grader did not complete {instance_id}: "
            f"completed={sorted(completed_ids)}, errors={sorted(error_ids)}"
        )
    return {
        "benchmark": "SWE-bench Verified",
        "mode": "official-model-smoke",
        "instance_id": instance_id,
        "resolved": instance_id in resolved_ids,
        "score": int(instance_id in resolved_ids),
        "report": str(report_path),
    }


def verify_swebench(report_path: Path, instance_id: str) -> dict[str, Any]:
    summary = summarize_swebench(report_path, instance_id)
    if not summary["resolved"]:
        raise RuntimeError(f"SWE-bench oracle did not resolve {instance_id}")
    summary["mode"] = "official-gold-harness-smoke"
    return summary


def summarize_terminalbench(jobs_dir: Path) -> dict[str, Any]:
    trials: list[dict[str, Any]] = []
    for path in sorted(jobs_dir.rglob("result.json")):
        result = json.loads(path.read_text())
        if "trial_name" not in result:
            continue
        verifier = result.get("verifier_result") or {}
        rewards = verifier.get("rewards") or {}
        reward = rewards.get("reward")
        trials.append(
            {
                "trial_name": result["trial_name"],
                "task_name": result.get("task_name"),
                "reward": reward,
                "exception": result.get("exception_info"),
                "result": str(path),
            }
        )

    if not trials:
        raise RuntimeError(f"No Harbor trial results found under {jobs_dir}")
    failures = [trial for trial in trials if trial["reward"] is None or trial["exception"] is not None]
    if failures:
        raise RuntimeError(f"Terminal-Bench grader smoke failed: {json.dumps(failures, sort_keys=True)}")
    total_reward = sum(float(trial["reward"]) for trial in trials)
    return {
        "benchmark": "Terminal-Bench 2.1",
        "mode": "official-model-smoke",
        "trials": trials,
        "passed": sum(trial["reward"] == 1.0 for trial in trials),
        "score": total_reward / len(trials),
    }


def verify_terminalbench(jobs_dir: Path) -> dict[str, Any]:
    summary = summarize_terminalbench(jobs_dir)
    failures = [trial for trial in summary["trials"] if trial["reward"] != 1.0]
    if failures:
        raise RuntimeError(f"Terminal-Bench oracle smoke failed: {json.dumps(failures, sort_keys=True)}")
    summary["mode"] = "official-oracle-harness-smoke"
    return summary


def _write_summary(summary: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary, indent=2, sort_keys=True))


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="benchmark", required=True)

    swebench = subparsers.add_parser("swebench")
    swebench.add_argument("--report", type=Path, required=True)
    swebench.add_argument("--instance-id", required=True)
    swebench.add_argument("--output", type=Path, required=True)

    terminalbench = subparsers.add_parser("terminalbench")
    terminalbench.add_argument("--jobs-dir", type=Path, required=True)
    terminalbench.add_argument("--output", type=Path, required=True)

    swebench_score = subparsers.add_parser("swebench-score")
    swebench_score.add_argument("--report", type=Path, required=True)
    swebench_score.add_argument("--instance-id", required=True)
    swebench_score.add_argument("--output", type=Path, required=True)

    terminalbench_score = subparsers.add_parser("terminalbench-score")
    terminalbench_score.add_argument("--jobs-dir", type=Path, required=True)
    terminalbench_score.add_argument("--output", type=Path, required=True)

    args = parser.parse_args()
    if args.benchmark == "swebench":
        summary = verify_swebench(args.report, args.instance_id)
    elif args.benchmark == "terminalbench":
        summary = verify_terminalbench(args.jobs_dir)
    elif args.benchmark == "swebench-score":
        summary = summarize_swebench(args.report, args.instance_id)
    else:
        summary = summarize_terminalbench(args.jobs_dir)
    _write_summary(summary, args.output)
