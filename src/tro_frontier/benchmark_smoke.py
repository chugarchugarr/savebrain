from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def verify_swebench(report_path: Path, instance_id: str) -> dict[str, Any]:
    report = json.loads(report_path.read_text())
    resolved_ids = set(report.get("resolved_ids", []))
    error_ids = set(report.get("error_ids", []))
    if instance_id not in resolved_ids:
        raise RuntimeError(
            f"SWE-bench oracle did not resolve {instance_id}: "
            f"resolved={sorted(resolved_ids)}, errors={sorted(error_ids)}"
        )
    return {
        "benchmark": "SWE-bench Verified",
        "mode": "official-gold-harness-smoke",
        "instance_id": instance_id,
        "resolved": True,
        "report": str(report_path),
    }


def verify_terminalbench(jobs_dir: Path) -> dict[str, Any]:
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
    failures = [trial for trial in trials if trial["reward"] != 1.0 or trial["exception"] is not None]
    if failures:
        raise RuntimeError(f"Terminal-Bench oracle smoke failed: {json.dumps(failures, sort_keys=True)}")
    return {
        "benchmark": "Terminal-Bench 2.1",
        "mode": "official-oracle-harness-smoke",
        "trials": trials,
        "passed": len(trials),
    }


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

    args = parser.parse_args()
    if args.benchmark == "swebench":
        summary = verify_swebench(args.report, args.instance_id)
    else:
        summary = verify_terminalbench(args.jobs_dir)
    _write_summary(summary, args.output)
