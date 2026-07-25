import asyncio
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

from tro_frontier.benchmarks.swebench import (
    build_task_payload,
    checkout_instance,
    export_prediction,
    extract_patch,
)
from tro_frontier.benchmarks.terminalbench import TraceRevalOroHarborAgent


def test_swebench_payload_and_prediction_contract(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    instance = {
        "instance_id": "project__issue-1",
        "problem_statement": "Fix the issue.",
        "repo": "owner/project",
        "base_commit": "abc123",
        "version": "1.0",
    }
    payload = build_task_payload(instance, repo=repo, check_commands=["pytest -q"])
    assert payload["task_id"] == "project__issue-1"
    assert payload["metadata"]["benchmark"] == "swe-bench_verified"

    (repo / "new_file.py").write_text("answer = 42\n")
    patch = extract_patch(repo)
    output = export_prediction(
        instance_id=instance["instance_id"],
        model_patch=patch,
        model_name_or_path="tro-v0.2",
        output_path=tmp_path / "prediction.json",
    )
    prediction = json.loads(output.read_text())[0]
    assert set(prediction) == {"instance_id", "model_name_or_path", "model_patch"}
    assert "new_file.py" in prediction["model_patch"]


def test_swebench_checkout_strips_grader_data(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo = tmp_path / "repo"
    instance = {
        "instance_id": "project__issue-1",
        "problem_statement": "Fix the issue.",
        "repo": "owner/project",
        "base_commit": "abc123",
        "version": "1.0",
        "patch": "gold patch",
        "test_patch": "hidden tests",
        "hints_text": "solution hint",
    }
    commands: list[tuple[list[str], Path | None]] = []

    def fake_run(command, *, cwd=None, check):
        del check
        commands.append((command, cwd))
        if command[:2] == ["git", "clone"]:
            repo.mkdir()
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = checkout_instance(
        instance,
        repo_dir=repo,
        instance_output=tmp_path / "instance.json",
        task_output=tmp_path / "task.json",
    )

    public_instance = json.loads((tmp_path / "instance.json").read_text())
    assert {"patch", "test_patch", "hints_text"}.isdisjoint(public_instance)
    assert json.loads((tmp_path / "task.json").read_text())["repo"] == str(repo)
    assert result["base_commit"] == "abc123"
    assert commands == [
        (["git", "clone", "https://github.com/owner/project.git", str(repo)], None),
        (["git", "checkout", "--detach", "abc123"], repo),
    ]


class _RecordingEnvironment:
    def __init__(self) -> None:
        self.commands: list[str] = []
        self.uploaded_dirs: list[tuple[Path, str]] = []
        self.uploaded_files: list[tuple[Path, str]] = []

    async def exec(self, *, command: str, timeout_sec: int):
        del timeout_sec
        self.commands.append(command)
        return SimpleNamespace(return_code=0, stdout="", stderr="")

    async def upload_dir(self, source: Path, target: str) -> None:
        self.uploaded_dirs.append((source, target))

    async def upload_file(self, source: Path, target: str) -> None:
        self.uploaded_files.append((source, target))


def test_terminalbench_setup_uploads_only_runtime_package(tmp_path: Path) -> None:
    agent = TraceRevalOroHarborAgent(logs_dir=tmp_path / "logs")
    environment = _RecordingEnvironment()
    asyncio.run(agent.setup(environment))

    assert [source.name for source, _ in environment.uploaded_dirs] == ["src", "frozen"]
    assert [source.name for source, _ in environment.uploaded_files] == ["pyproject.toml", "README.md"]
    assert not any(".venv" in str(source) for source, _ in environment.uploaded_dirs)
    assert environment.commands[-1] == "python -m pip install -e /tmp/tro-package"
