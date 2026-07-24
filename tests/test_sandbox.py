from pathlib import Path

import pytest

from tro_frontier.sandbox import Workspace


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
