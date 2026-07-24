from __future__ import annotations

import os
import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CommandResult:
    command: str
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class Workspace:
    def __init__(
        self,
        root: str | Path,
        blocked_commands: list[str] | None = None,
        output_limit: int = 50_000,
    ) -> None:
        self.root = Path(root).expanduser().resolve()
        if not self.root.is_dir():
            raise ValueError(f"Workspace does not exist: {self.root}")
        self.blocked_commands = [item.lower() for item in (blocked_commands or [])]
        self.output_limit = output_limit

    def resolve(self, relative_path: str) -> Path:
        candidate = (self.root / relative_path).resolve()
        try:
            candidate.relative_to(self.root)
        except ValueError as exc:
            raise ValueError(f"Path escapes workspace: {relative_path}") from exc
        return candidate

    def read_file(self, relative_path: str, max_chars: int = 50_000) -> str:
        path = self.resolve(relative_path)
        text = path.read_text(errors="replace")
        return text[:max_chars]

    def write_file(self, relative_path: str, content: str) -> None:
        path = self.resolve(relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)

    def list_files(self, relative_path: str = ".", limit: int = 500) -> list[str]:
        base = self.resolve(relative_path)
        paths: list[str] = []
        for path in sorted(base.rglob("*")):
            if path.is_file() and ".git" not in path.parts:
                paths.append(str(path.relative_to(self.root)))
                if len(paths) >= limit:
                    break
        return paths

    def run(self, command: str, timeout: int = 300) -> CommandResult:
        self._reject_network_command(command)
        env = os.environ.copy()
        env.update(
            {
                "CI": "1",
                "GIT_TERMINAL_PROMPT": "0",
                "PIP_DISABLE_PIP_VERSION_CHECK": "1",
                "NO_PROXY": "*",
                "no_proxy": "*",
            }
        )
        try:
            proc = subprocess.run(
                ["bash", "-lc", command],
                cwd=self.root,
                env=env,
                text=True,
                capture_output=True,
                timeout=timeout,
                check=False,
            )
            return CommandResult(
                command=command,
                returncode=proc.returncode,
                stdout=proc.stdout[-self.output_limit :],
                stderr=proc.stderr[-self.output_limit :],
            )
        except subprocess.TimeoutExpired as exc:
            stdout = (exc.stdout or "")[-self.output_limit :]
            stderr = (exc.stderr or "")[-self.output_limit :]
            return CommandResult(
                command=command,
                returncode=124,
                stdout=stdout,
                stderr=stderr,
                timed_out=True,
            )

    def _reject_network_command(self, command: str) -> None:
        normalized = re.sub(r"\s+", " ", command.strip().lower())
        for blocked in self.blocked_commands:
            pattern = rf"(^|[;&|()\s]){re.escape(blocked)}($|[;&|()\s])"
            if re.search(pattern, normalized):
                raise PermissionError(f"Network-bearing command blocked by frozen policy: {blocked}")
