from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from pathlib import Path

from tro_frontier.ablation import run_component_ablation
from tro_frontier.structural import ScriptedSession


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default="structural-ablation-results")
    parser.add_argument("--manifest", default="frozen/trace-reval-oro-v0.2.json")
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as temp:
        repo = Path(temp) / "fixture"
        repo.mkdir()
        _git(repo, "init")
        _git(repo, "config", "user.email", "ablation@example.invalid")
        _git(repo, "config", "user.name", "Structural Ablation")
        (repo / "README.md").write_text("fixture\n")
        _git(repo, "add", "README.md")
        _git(repo, "commit", "-m", "seed")

        task = {
            "task_id": "structural-controller-ablation",
            "prompt": "Create answer.txt containing the exact word fixed.",
            "repo": str(repo),
            "check_commands": ["grep -q fixed answer.txt"],
            "allowed_paths": ["answer.txt"],
            "metadata": {"benchmark": "structural-controller-ablation", "model_performance_claim": False},
        }
        task_path = Path(temp) / "task.json"
        task_path.write_text(json.dumps(task))
        result = run_component_ablation(
            task_path=task_path,
            manifest_path=args.manifest,
            output_dir=args.output_dir,
            repeats=1,
            destructive_reset=True,
            session_factory=ScriptedSession,
        )
        print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
