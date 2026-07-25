from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

from ..sandbox import build_git_patch


def build_task_payload(
    instance: dict[str, Any],
    *,
    repo: str | Path,
    check_commands: list[str] | None = None,
) -> dict[str, Any]:
    instance_id = str(instance["instance_id"])
    prompt = str(instance.get("problem_statement") or instance.get("prompt") or "").strip()
    if not prompt:
        raise ValueError("SWE-bench instance is missing problem_statement")
    return {
        "task_id": instance_id,
        "prompt": prompt,
        "repo": str(Path(repo).expanduser().resolve()),
        "check_commands": list(check_commands or []),
        "allowed_paths": [],
        "metadata": {
            "benchmark": "swe-bench_verified",
            "instance_id": instance_id,
            "repo": instance.get("repo"),
            "base_commit": instance.get("base_commit"),
            "version": instance.get("version"),
        },
    }


def extract_patch(repo: str | Path) -> str:
    return build_git_patch(repo)


def checkout_instance(
    instance: dict[str, Any],
    *,
    repo_dir: str | Path,
    instance_output: str | Path,
    task_output: str | Path,
) -> dict[str, Any]:
    repo_name = str(instance["repo"])
    base_commit = str(instance["base_commit"])
    checkout = Path(repo_dir).expanduser().resolve()
    if checkout.exists():
        raise ValueError(f"Checkout path already exists: {checkout}")

    subprocess.run(
        ["git", "clone", f"https://github.com/{repo_name}.git", str(checkout)],
        check=True,
    )
    subprocess.run(
        ["git", "checkout", "--detach", base_commit],
        cwd=checkout,
        check=True,
    )

    public_instance = {
        key: value
        for key, value in instance.items()
        if key not in {"patch", "test_patch", "hints_text"}
    }
    instance_path = Path(instance_output)
    instance_path.parent.mkdir(parents=True, exist_ok=True)
    instance_path.write_text(json.dumps(public_instance, indent=2, sort_keys=True) + "\n")

    task = build_task_payload(public_instance, repo=checkout)
    task_path = Path(task_output)
    task_path.parent.mkdir(parents=True, exist_ok=True)
    task_path.write_text(json.dumps(task, indent=2, sort_keys=True) + "\n")
    return {
        "instance_id": public_instance["instance_id"],
        "repo": repo_name,
        "base_commit": base_commit,
        "checkout": str(checkout),
        "instance_path": str(instance_path.resolve()),
        "task_path": str(task_path.resolve()),
    }


def load_instance(dataset_name: str, instance_id: str) -> dict[str, Any]:
    try:
        from datasets import load_dataset
    except ImportError as exc:
        raise RuntimeError("Install the official SWE-bench harness before loading a dataset") from exc

    dataset = load_dataset(dataset_name, split="test")
    for instance in dataset:
        if str(instance["instance_id"]) == instance_id:
            return dict(instance)
    raise ValueError(f"Instance {instance_id!r} not found in {dataset_name!r}")


def export_prediction(
    *,
    instance_id: str,
    model_patch: str,
    model_name_or_path: str,
    output_path: str | Path,
) -> Path:
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = [
        {
            "instance_id": instance_id,
            "model_patch": model_patch,
            "model_name_or_path": model_name_or_path,
        }
    ]
    target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return target


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tro-swebench")
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser("prepare", help="Convert one SWE-bench instance to a tro-frontier task")
    prepare.add_argument("instance_json")
    prepare.add_argument("--repo", required=True)
    prepare.add_argument("--output", required=True)
    prepare.add_argument("--check", action="append", default=[])

    checkout = subparsers.add_parser("checkout", help="Load and check out one official SWE-bench instance")
    checkout.add_argument("--dataset", default="SWE-bench/SWE-bench_Verified")
    checkout.add_argument("--instance-id", required=True)
    checkout.add_argument("--repo-dir", required=True)
    checkout.add_argument("--instance-output", required=True)
    checkout.add_argument("--task-output", required=True)

    export = subparsers.add_parser("export", help="Export the current repository diff in sb-cli prediction format")
    export.add_argument("--instance-id", required=True)
    export.add_argument("--repo", required=True)
    export.add_argument("--model-name", default="GPT-5.6 routed + TRACE + REVAL + ORO v0.2")
    export.add_argument("--output", required=True)
    return parser


def main() -> None:
    args = _parser().parse_args()
    if args.command == "prepare":
        instance = json.loads(Path(args.instance_json).read_text())
        payload = build_task_payload(instance, repo=args.repo, check_commands=args.check)
        target = Path(args.output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        print(target)
        return

    if args.command == "checkout":
        instance = load_instance(args.dataset, args.instance_id)
        result = checkout_instance(
            instance,
            repo_dir=args.repo_dir,
            instance_output=args.instance_output,
            task_output=args.task_output,
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return

    patch = extract_patch(args.repo)
    target = export_prediction(
        instance_id=args.instance_id,
        model_patch=patch,
        model_name_or_path=args.model_name,
        output_path=args.output,
    )
    print(target)


if __name__ == "__main__":
    main()
