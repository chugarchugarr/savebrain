from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .config import load_manifest
from .runner import AgentRunner, SessionFactory, TaskSpec


def build_effort_manifest(
    base_manifest: str | Path,
    *,
    effort: str,
    output_dir: str | Path,
) -> Path:
    data = json.loads(Path(base_manifest).read_text())
    supported = list(data["model"]["reasoning_efforts"])
    if effort not in supported:
        raise ValueError(f"Unsupported reasoning effort {effort!r}; expected one of {supported}")
    data["name"] = f"{data['name']} [{effort}]"
    data["version"] = f"{data['version']}-effort-{effort}"
    data["model"]["reasoning_efforts"] = [effort]
    target = Path(output_dir) / f"{effort}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    return target


def run_reasoning_sweep(
    *,
    task_path: str | Path,
    manifest_path: str | Path,
    output_dir: str | Path,
    repeats: int = 5,
    efforts: list[str] | None = None,
    destructive_reset: bool = False,
    session_factory: SessionFactory | None = None,
) -> dict[str, Any]:
    if repeats < 1:
        raise ValueError("repeats must be positive")
    base_manifest = load_manifest(manifest_path)
    supported = list(base_manifest.data["model"]["reasoning_efforts"])
    selected = efforts or supported
    invalid = [effort for effort in selected if effort not in supported]
    if invalid:
        raise ValueError(f"Unsupported reasoning efforts: {invalid}")

    task = TaskSpec.from_json(task_path)
    root = task.repo
    total_runs = repeats * len(selected)
    if total_runs > 1 and not destructive_reset:
        raise ValueError("Multiple sweep runs require destructive_reset=True on an isolated benchmark checkout")

    out = Path(output_dir).expanduser().resolve()
    if destructive_reset and _is_within(out, root):
        raise ValueError("Sweep output must be outside the reset benchmark checkout")
    manifests_dir = out / "manifests"
    runs_dir = out / "runs"
    base_commit = _git(root, ["rev-parse", "HEAD"]).strip()
    summary: dict[str, Any] = {
        "task_id": task.task_id,
        "base_commit": base_commit,
        "repeats": repeats,
        "efforts": {},
    }

    try:
        for effort in selected:
            manifest_file = build_effort_manifest(
                manifest_path,
                effort=effort,
                output_dir=manifests_dir,
            )
            results: list[dict[str, Any]] = []
            for repeat in range(repeats):
                if destructive_reset:
                    _reset(root, base_commit)
                result = AgentRunner(
                    manifest=load_manifest(manifest_file),
                    task=task,
                    output_dir=runs_dir / effort / str(repeat),
                    session_factory=session_factory,
                ).run()
                results.append(result)
            summary["efforts"][effort] = _summarize(results)
    finally:
        if destructive_reset:
            _reset(root, base_commit)
        shutil.rmtree(manifests_dir, ignore_errors=True)

    target = out / "reasoning-sweep.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    summary["summary_path"] = str(target)
    return summary


def _summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    statuses: dict[str, int] = {}
    total_usd = 0.0
    total_input = 0
    total_output = 0
    for result in results:
        status = str(result.get("status", "unknown"))
        statuses[status] = statuses.get(status, 0) + 1
        usage = result.get("usage", {})
        total_usd += float(usage.get("usd", 0.0))
        total_input += int(usage.get("input_tokens", 0))
        total_output += int(usage.get("output_tokens", 0))
    count = len(results)
    return {
        "runs": count,
        "statuses": statuses,
        "verified_rate": statuses.get("verified", 0) / count,
        "completion_rate": (statuses.get("verified", 0) + statuses.get("completed", 0)) / count,
        "average_usd": total_usd / count,
        "average_input_tokens": total_input / count,
        "average_output_tokens": total_output / count,
        "results": results,
    }


def _git(root: Path, args: list[str]) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr or proc.stdout or f"git {' '.join(args)} failed")
    return proc.stdout


def _reset(root: Path, base_commit: str) -> None:
    _git(root, ["reset", "--hard", base_commit])
    _git(root, ["clean", "-fd"])


def _is_within(candidate: Path, parent: Path) -> bool:
    try:
        candidate.relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tro-sweep")
    parser.add_argument("task")
    parser.add_argument("--manifest", default="frozen/trace-reval-oro-v0.2.json")
    parser.add_argument("--output-dir", default="reasoning-sweep-results")
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument(
        "--effort",
        action="append",
        choices=["none", "low", "medium", "high", "xhigh", "max"],
    )
    parser.add_argument("--allow-destructive-reset", action="store_true")
    return parser


def main() -> None:
    args = _parser().parse_args()
    result = run_reasoning_sweep(
        task_path=args.task,
        manifest_path=args.manifest,
        output_dir=args.output_dir,
        repeats=args.repeats,
        efforts=args.effort,
        destructive_reset=args.allow_destructive_reset,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
