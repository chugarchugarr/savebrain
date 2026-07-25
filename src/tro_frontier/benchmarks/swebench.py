from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any


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
    root = Path(repo).expanduser().resolve()
    proc = subprocess.run(
        ["git", "diff", "--binary"],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr or "git diff failed")
    return proc.stdout


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
