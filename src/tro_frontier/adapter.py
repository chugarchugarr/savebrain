from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import load_manifest
from .runner import AgentRunner, TaskSpec


def run_task(
    task_payload: dict[str, Any],
    *,
    manifest_path: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    """Benchmark-owner entry point for one isolated rollout."""
    task = TaskSpec(
        task_id=str(task_payload["task_id"]),
        prompt=str(task_payload["prompt"]),
        repo=Path(task_payload["repo"]).expanduser().resolve(),
        check_commands=[str(item) for item in task_payload.get("check_commands", [])],
        allowed_paths=[str(item) for item in task_payload.get("allowed_paths", [])],
        metadata=dict(task_payload.get("metadata", {})),
    )
    return AgentRunner(
        manifest=load_manifest(manifest_path),
        task=task,
        output_dir=output_dir,
    ).run()
