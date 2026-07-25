import json
import subprocess
from pathlib import Path

import pytest

from scripts.run_structural_ablation import ScriptedSession
from tro_frontier.sweep import build_effort_manifest, run_reasoning_sweep


def test_build_effort_manifest_freezes_one_effort(tmp_path: Path) -> None:
    base = Path(__file__).parents[1] / "frozen" / "trace-reval-oro-v0.2.json"
    target = build_effort_manifest(base, effort="xhigh", output_dir=tmp_path)
    data = json.loads(target.read_text())
    assert data["model"]["reasoning_efforts"] == ["xhigh"]
    assert data["version"] == "0.2.0-effort-xhigh"


def test_build_effort_manifest_rejects_unknown_effort(tmp_path: Path) -> None:
    base = Path(__file__).parents[1] / "frozen" / "trace-reval-oro-v0.2.json"
    with pytest.raises(ValueError, match="Unsupported reasoning effort"):
        build_effort_manifest(base, effort="impossible", output_dir=tmp_path)


def test_reasoning_sweep_runs_and_resets_isolated_checkout(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
    (repo / "README.md").write_text("fixture\n")
    subprocess.run(["git", "add", "README.md"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "seed"], cwd=repo, check=True, capture_output=True)
    task = {
        "task_id": "sweep-fixture",
        "prompt": "Create answer.txt containing the exact word fixed.",
        "repo": str(repo),
        "check_commands": ["grep -q fixed answer.txt"],
        "allowed_paths": ["answer.txt"],
    }
    task_path = tmp_path / "task.json"
    task_path.write_text(json.dumps(task))

    result = run_reasoning_sweep(
        task_path=task_path,
        manifest_path=Path(__file__).parents[1] / "frozen" / "trace-reval-oro-v0.2.json",
        output_dir=tmp_path / "results",
        repeats=2,
        efforts=["low", "high"],
        destructive_reset=True,
        session_factory=ScriptedSession,
    )

    assert result["efforts"]["low"]["statuses"] == {"verified": 2}
    assert result["efforts"]["high"]["statuses"] == {"verified": 2}
    assert not (repo / "answer.txt").exists()
    assert Path(result["summary_path"]).is_file()
