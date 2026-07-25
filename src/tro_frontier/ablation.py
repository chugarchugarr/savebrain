from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .config import load_manifest
from .runner import AgentRunner, SessionFactory, TaskSpec

VARIANTS: dict[str, dict[str, bool]] = {
    "gpt_only": {"trace": False, "reval": False, "oro": False},
    "trace_only": {"trace": True, "reval": False, "oro": False},
    "reval_only": {"trace": False, "reval": True, "oro": False},
    "oro_only": {"trace": False, "reval": False, "oro": True},
    "full": {"trace": True, "reval": True, "oro": True},
}


def build_variant_manifest(
    base_manifest: str | Path,
    *,
    variant: str,
    output_dir: str | Path,
) -> Path:
    if variant not in VARIANTS:
        raise ValueError(f"Unknown ablation variant: {variant}")
    data = json.loads(Path(base_manifest).read_text())
    data["name"] = f"{data['name']} [{variant}]"
    data["version"] = f"{data['version']}-ablation-{variant}"
    data["components"] = VARIANTS[variant]
    target = Path(output_dir) / f"{variant}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    return target


def run_component_ablation(
    *,
    task_path: str | Path,
    manifest_path: str | Path,
    output_dir: str | Path,
    repeats: int = 1,
    variants: list[str] | None = None,
    destructive_reset: bool = False,
    session_factory: SessionFactory | None = None,
) -> dict[str, Any]:
    if repeats < 1:
        raise ValueError("repeats must be positive")
    selected = variants or list(VARIANTS)
    task = TaskSpec.from_json(task_path)
    root = task.repo
    base_commit = _git(root, "rev-parse HEAD").strip()
    if (repeats > 1 or len(selected) > 1) and not destructive_reset:
        raise ValueError("Multiple ablation runs require destructive_reset=True on an isolated benchmark checkout")

    out = Path(output_dir)
    manifests_dir = out / "manifests"
    runs_dir = out / "runs"
    summary: dict[str, Any] = {
        "task_id": task.task_id,
        "base_commit": base_commit,
        "variants": {},
    }
    try:
        for variant in selected:
            manifest_file = build_variant_manifest(manifest_path, variant=variant, output_dir=manifests_dir)
            variant_results: list[dict[str, Any]] = []
            for repeat in range(repeats):
                if destructive_reset:
                    _reset(root, base_commit)
                result = AgentRunner(
                    manifest=load_manifest(manifest_file),
                    task=task,
                    output_dir=runs_dir / variant / str(repeat),
                    session_factory=session_factory,
                ).run()
                variant_results.append(result)
            summary["variants"][variant] = _summarize(variant_results)
    finally:
        if destructive_reset:
            _reset(root, base_commit)
        shutil.rmtree(manifests_dir, ignore_errors=True)

    target = out / "component-ablation.json"
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


def _git(root: Path, command: str) -> str:
    proc = subprocess.run(
        ["bash", "-lc", f"git {command}"],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr or proc.stdout or f"git {command} failed")
    return proc.stdout


def _reset(root: Path, base_commit: str) -> None:
    _git(root, f"reset --hard {base_commit}")
    _git(root, "clean -fd")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tro-ablate")
    parser.add_argument("task")
    parser.add_argument("--manifest", default="frozen/trace-reval-oro-v0.2.json")
    parser.add_argument("--output-dir", default="ablation-results")
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--variant", action="append", choices=list(VARIANTS))
    parser.add_argument("--allow-destructive-reset", action="store_true")
    return parser


def main() -> None:
    args = _parser().parse_args()
    result = run_component_ablation(
        task_path=args.task,
        manifest_path=args.manifest,
        output_dir=args.output_dir,
        repeats=args.repeats,
        variants=args.variant,
        destructive_reset=args.allow_destructive_reset,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
