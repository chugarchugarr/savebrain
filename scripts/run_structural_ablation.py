from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from tro_frontier.ablation import run_component_ablation
from tro_frontier.model import ModelTurn


class ScriptedSession:
    """Deterministic model double used only to test controller contribution."""

    def __init__(self, model: str, instructions: str) -> None:
        self.model = model
        self.instructions = instructions
        self.response_index = 0
        self.phase: str | None = None
        self.trace_enabled = False
        self.reval_enabled = False
        self.trace_stage = "target"
        self.evidence_ids: list[str] = []

    def turn(self, input_items: list[dict[str, Any]], tools: list[dict[str, Any]], effort: str) -> ModelTurn:
        del effort
        text = json.dumps(input_items)
        tool_names = {str(tool.get("name")) for tool in tools if tool.get("type") == "function"}
        if self.phase is None:
            self.trace_enabled = "advance_trace" in tool_names
            self.reval_enabled = "'reval': True" in text or '"reval": true' in text.lower()
            if "ORO escalated" in text or "Repair count: 1" in text:
                self.trace_enabled = "TRACE stage: contain" in text or self.trace_enabled
                self.reval_enabled = True
                self.trace_stage = "contain"
                self.phase = "repair_write"
            else:
                self.phase = "advance_rip" if self.trace_enabled else "write_bad"

        for item in input_items:
            if item.get("type") != "function_call_output":
                continue
            payload = json.loads(str(item.get("output", "{}")))
            evidence_id = payload.get("evidence_id")
            if isinstance(evidence_id, str):
                self.evidence_ids.append(evidence_id)
            if payload.get("status") == "repair_required":
                self.reval_enabled = True
                self.trace_stage = str(payload.get("trace_stage", self.trace_stage))
                self.phase = "repair_write"

        call = self._next_call()
        self.response_index += 1
        return ModelTurn(
            response_id=f"scripted-{self.model}-{self.response_index}",
            model=self.model,
            tool_calls=[call],
            external_sources=[],
            text="",
            input_tokens=10,
            cached_input_tokens=0,
            output_tokens=5,
            tool_call_count=1,
            usd=0.0,
        )

    def _next_call(self) -> dict[str, Any]:
        phase = self.phase
        if phase == "advance_rip":
            self.phase = "advance_assemble"
            return self._call("advance_trace", {"stage": "rip", "summary": "inspect"})
        if phase == "advance_assemble":
            self.phase = "write_bad"
            return self._call("advance_trace", {"stage": "assemble", "summary": "implement"})
        if phase == "write_bad":
            self.phase = "advance_contain" if self.trace_enabled else "run_bad_check"
            return self._call("write_file", {"path": "answer.txt", "content": "bad\n"})
        if phase == "advance_contain":
            self.trace_stage = "contain"
            self.phase = "run_bad_check"
            return self._call("advance_trace", {"stage": "contain", "summary": "verify"})
        if phase == "run_bad_check":
            self.phase = "advance_initial_exit" if self.trace_enabled else "submit_initial"
            return self._call("run_command", {"command": "grep -q fixed answer.txt"})
        if phase == "advance_initial_exit":
            self.trace_stage = "exit"
            self.phase = "submit_initial"
            return self._call("advance_trace", {"stage": "exit", "summary": "submit"})
        if phase == "submit_initial":
            self.phase = "await_initial_result"
            return self._submit("initial completion")
        if phase == "repair_write":
            self.phase = "run_fixed_check"
            return self._call("write_file", {"path": "answer.txt", "content": "fixed\n"})
        if phase == "run_fixed_check":
            self.phase = "advance_final_exit" if self.trace_enabled else "submit_final"
            return self._call("run_command", {"command": "grep -q fixed answer.txt"})
        if phase == "advance_final_exit":
            self.trace_stage = "exit"
            self.phase = "submit_final"
            return self._call("advance_trace", {"stage": "exit", "summary": "repaired"})
        if phase == "submit_final":
            self.phase = "done"
            return self._submit("verified repair")
        raise RuntimeError(f"Unexpected scripted phase: {phase}")

    def _submit(self, summary: str) -> dict[str, Any]:
        evidence = self.evidence_ids[-1:] if self.reval_enabled else []
        claims = [{"text": "answer is fixed", "evidence_ids": evidence}] if self.reval_enabled else []
        return self._call("submit_result", {"summary": summary, "claims": claims})

    def _call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return {
            "call_id": f"call-{self.response_index + 1}",
            "name": name,
            "arguments": arguments,
        }


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
