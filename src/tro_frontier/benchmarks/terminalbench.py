from __future__ import annotations

import base64
import json
import shlex
from pathlib import Path
from typing import Any

from harbor.agents.base import BaseAgent
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext


class TraceRevalOroHarborAgent(BaseAgent):
    """Harbor custom agent for Terminal-Bench 2.1 and other container tasks."""

    SUPPORTS_ATIF = False

    def __init__(
        self,
        logs_dir: Path,
        model_name: str | None = None,
        workspace: str = "/app",
        max_seconds: int = 3600,
        luna_model: str = "gpt-5.6-luna",
        terra_model: str = "gpt-5.6-terra",
        sol_model: str = "gpt-5.6-sol",
        **kwargs: Any,
    ) -> None:
        super().__init__(logs_dir=logs_dir, model_name=model_name, **kwargs)
        self.workspace = workspace
        self.max_seconds = max_seconds
        self.models = {"luna": luna_model, "terra": terra_model, "sol": sol_model}
        self.remote_package = "/tmp/tro-package"
        self.remote_runs = "/tmp/tro-runs"

    @staticmethod
    def name() -> str:
        return "trace-reval-oro"

    def version(self) -> str:
        return "0.2.0"

    async def setup(self, environment: BaseEnvironment) -> None:
        package_root = Path(__file__).resolve().parents[3]
        await environment.upload_dir(package_root, self.remote_package)
        result = await environment.exec(
            command=f"python -m pip install -e {shlex.quote(self.remote_package)}",
            timeout_sec=300,
        )
        if result.return_code != 0:
            raise RuntimeError(result.stderr or result.stdout or "Failed to install tro-frontier")

    async def run(
        self,
        instruction: str,
        environment: BaseEnvironment,
        context: AgentContext,
    ) -> None:
        task = {
            "task_id": str(self.session_id or "terminal-bench-task"),
            "prompt": instruction,
            "repo": self.workspace,
            "check_commands": [],
            "allowed_paths": [],
            "metadata": {"benchmark": "terminal-bench-2.1", "harbor_context_id": str(self.context_id or "")},
        }
        encoded = base64.b64encode(json.dumps(task).encode()).decode()
        env_values = {
            **self.extra_env,
            "OPENAI_MODEL_LUNA": self.models["luna"],
            "OPENAI_MODEL_TERRA": self.models["terra"],
            "OPENAI_MODEL_SOL": self.models["sol"],
        }
        exports = " ".join(f"{key}={shlex.quote(value)}" for key, value in env_values.items())
        manifest = f"{self.remote_package}/frozen/trace-reval-oro-v0.2.json"
        command = (
            f"mkdir -p {shlex.quote(self.remote_runs)} && "
            f"echo {shlex.quote(encoded)} | base64 -d > /tmp/tro-task.json && "
            f"env {exports} tro-frontier /tmp/tro-task.json "
            f"--manifest {shlex.quote(manifest)} --output-dir {shlex.quote(self.remote_runs)}"
        )
        result = await environment.exec(command=command, timeout_sec=self.max_seconds)
        if result.return_code != 0:
            raise RuntimeError(result.stderr or result.stdout or "tro-frontier failed")

        raw = (result.stdout or "").strip()
        payload = json.loads(raw)
        await environment.download_dir(self.remote_runs, self.logs_dir / "tro-runs")

        usage = payload.get("usage", {})
        context.n_input_tokens = int(usage.get("input_tokens", 0))
        context.n_cache_tokens = int(usage.get("cached_input_tokens", 0))
        context.n_output_tokens = int(usage.get("output_tokens", 0))
        context.cost_usd = float(usage.get("usd", 0.0))
        context.metadata = {
            "status": payload.get("status"),
            "run_id": payload.get("run_id"),
            "manifest_sha256": payload.get("manifest_sha256"),
            "model_route": payload.get("model_route", []),
            "patch_path": payload.get("patch_path"),
            "lineage_path": payload.get("lineage_path"),
        }
