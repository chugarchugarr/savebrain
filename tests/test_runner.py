from pathlib import Path

import pytest

from tro_frontier.config import load_manifest
from tro_frontier.runner import AgentRunner, TaskSpec


def test_runner_rejects_output_inside_task_repository(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    manifest = load_manifest(Path(__file__).parents[1] / "frozen" / "trace-reval-oro-v0.2.json")
    task = TaskSpec(task_id="fixture", prompt="Do work.", repo=repo)

    with pytest.raises(ValueError, match="outside the task repository"):
        AgentRunner(manifest, task, output_dir=repo / "runs")
