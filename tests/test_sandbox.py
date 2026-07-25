import subprocess
from pathlib import Path

import pytest

from tro_frontier.sandbox import Workspace, build_git_patch


def test_workspace_blocks_path_escape(tmp_path: Path) -> None:
    workspace = Workspace(tmp_path)
    with pytest.raises(ValueError):
        workspace.resolve("../outside")


def test_workspace_blocks_network_commands(tmp_path: Path) -> None:
    workspace = Workspace(tmp_path, blocked_commands=["curl", "git clone"])
    with pytest.raises(PermissionError):
        workspace.run("curl https://example.com")
    with pytest.raises(PermissionError):
        workspace.run("git clone https://example.com/repo.git")


def test_git_patch_includes_tracked_and_untracked_files(tmp_path: Path) -> None:
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    tracked = tmp_path / "tracked.txt"
    tracked.write_text("before\n")
    subprocess.run(["git", "add", "tracked.txt"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "seed"], cwd=tmp_path, check=True, capture_output=True)

    tracked.write_text("after\n")
    (tmp_path / "untracked.txt").write_text("new\n")
    patch = build_git_patch(tmp_path)

    assert "tracked.txt" in patch
    assert "+after" in patch
    assert "untracked.txt" in patch
    assert "+new" in patch
