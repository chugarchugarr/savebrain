from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import FrozenManifest
from .ledger import RunLedger
from .model import OpenAIReasoningSession
from .oro import OroBudget
from .reval import RevalVerifier
from .sandbox import Workspace
from .trace import TraceState, system_instructions


@dataclass(frozen=True)
class TaskSpec:
    task_id: str
    prompt: str
    repo: Path
    check_commands: list[str] = field(default_factory=list)
    allowed_paths: list[str] = field(default_factory=list)

    @classmethod
    def from_json(cls, path: str | Path) -> "TaskSpec":
        data = json.loads(Path(path).read_text())
        return cls(
            task_id=str(data["task_id"]),
            prompt=str(data["prompt"]),
            repo=Path(data["repo"]).expanduser().resolve(),
            check_commands=[str(item) for item in data.get("check_commands", [])],
            allowed_paths=[str(item) for item in data.get("allowed_paths", [])],
        )


class AgentRunner:
    def __init__(self, manifest: FrozenManifest, task: TaskSpec, output_dir: str | Path) -> None:
        self.manifest = manifest
        self.task = task
        self.output_dir = Path(output_dir)
        run_id = f"{task.task_id}-{uuid.uuid4().hex[:12]}"
        self.ledger = RunLedger(
            run_id=run_id,
            manifest_sha256=manifest.sha256,
            task_id=task.task_id,
        )
        self.workspace = Workspace(
            task.repo,
            blocked_commands=manifest.data["internet"]["blocked_commands"],
        )
        oro = manifest.data["oro"]
        self.budget = OroBudget(
            max_steps=int(oro["max_steps"]),
            max_repairs=int(oro["max_repairs"]),
            max_wall_seconds=int(oro["max_wall_seconds"]),
            max_usd=float(oro["max_usd"]),
            efforts=list(manifest.data["model"]["reasoning_efforts"]),
        )
        self.trace = TraceState()
        model_name = os.getenv(
            manifest.data["model"]["model_env"],
            manifest.data["model"]["default_model"],
        )
        self.session = OpenAIReasoningSession(model=model_name, instructions=system_instructions())
        self.verifier = RevalVerifier(
            workspace=self.workspace,
            ledger=self.ledger,
            always_run=list(manifest.data["reval"]["always_run"]),
        )
        self.pending_input: list[dict[str, Any]] = [
            {
                "role": "user",
                "content": (
                    f"Task ID: {task.task_id}\n"
                    f"Repository: {task.repo}\n"
                    f"Required checks: {task.check_commands}\n"
                    f"Allowed paths: {task.allowed_paths or 'unrestricted'}\n\n"
                    f"{task.prompt}"
                ),
            }
        ]

    def run(self) -> dict[str, Any]:
        self.ledger.add(
            "run_started",
            {
                "task": self.task.prompt,
                "repo": str(self.task.repo),
                "manifest": self.manifest.name,
                "manifest_sha256": self.manifest.sha256,
            },
        )

        final: dict[str, Any] | None = None
        while final is None:
            exhausted, reason = self.budget.exhausted()
            if exhausted:
                final = self._abstain(reason or "budget exhausted")
                break

            self.budget.consume_step()
            turn = self.session.turn(self.pending_input, self._tools(), self.budget.effort)
            self.ledger.add_usage(turn.input_tokens, turn.output_tokens, turn.usd)
            self.budget.record_usage(turn.usd)
            self.ledger.add(
                "model_turn",
                {
                    "response_id": turn.response_id,
                    "effort": self.budget.effort,
                    "text": turn.text,
                    "tool_calls": turn.tool_calls,
                    "input_tokens": turn.input_tokens,
                    "output_tokens": turn.output_tokens,
                    "usd": turn.usd,
                },
            )

            if not turn.tool_calls:
                self.pending_input = [
                    {
                        "role": "user",
                        "content": "Use the provided tools. Advance TRACE or submit a verified result.",
                    }
                ]
                continue

            tool_outputs: list[dict[str, Any]] = []
            for call in turn.tool_calls:
                output, maybe_final = self._execute_tool(call["name"], call["arguments"])
                tool_outputs.append(
                    {
                        "type": "function_call_output",
                        "call_id": call["call_id"],
                        "output": json.dumps(output, sort_keys=True),
                    }
                )
                if maybe_final is not None:
                    final = maybe_final
                    break
            self.pending_input = tool_outputs

        self.ledger.add("run_finished", final)
        ledger_path = self.output_dir / f"{self.ledger.run_id}.json"
        self.ledger.save(ledger_path)
        final["ledger_path"] = str(ledger_path)
        final["run_id"] = self.ledger.run_id
        final["manifest_sha256"] = self.manifest.sha256
        return final

    def _execute_tool(self, name: str, args: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None]:
        try:
            if name == "advance_trace":
                self.trace.advance(str(args["stage"]))
                evidence_id = self._record_evidence(
                    "trace_transition",
                    {"stage": self.trace.stage, "summary": str(args.get("summary", ""))},
                )
                return {"ok": True, "stage": self.trace.stage, "evidence_id": evidence_id}, None

            if name == "list_files":
                files = self.workspace.list_files(str(args.get("path", ".")))
                evidence_id = self._record_evidence("list_files", {"files": files})
                return {"files": files, "evidence_id": evidence_id}, None

            if name == "read_file":
                path = str(args["path"])
                content = self.workspace.read_file(path)
                evidence_id = self._record_evidence("read_file", {"path": path, "content": content})
                return {"path": path, "content": content, "evidence_id": evidence_id}, None

            if name == "write_file":
                if not self.trace.may_write():
                    raise PermissionError(f"Writes are blocked during TRACE stage {self.trace.stage}")
                path = str(args["path"])
                self.workspace.write_file(path, str(args["content"]))
                evidence_id = self._record_evidence("write_file", {"path": path})
                return {"ok": True, "path": path, "evidence_id": evidence_id}, None

            if name == "run_command":
                command = str(args["command"])
                timeout = int(args.get("timeout", 300))
                result = self.workspace.run(command, timeout=timeout)
                payload = result.to_dict()
                evidence_id = self._record_evidence("command", payload)
                payload["evidence_id"] = evidence_id
                return payload, None

            if name == "submit_result":
                if not self.trace.may_complete():
                    raise PermissionError("Completion is blocked until TRACE reaches exit")
                claims = list(args.get("claims", []))
                report = self.verifier.verify(
                    check_commands=self.task.check_commands,
                    allowed_paths=self.task.allowed_paths,
                    claims=claims,
                )
                if report.passed:
                    return report.to_dict(), {
                        "status": "verified",
                        "summary": str(args.get("summary", "")),
                        "claims": claims,
                        "verification": report.to_dict(),
                    }

                self.budget.verification_failed()
                self.trace.index = 3
                return {
                    "status": "repair_required",
                    "verification": report.to_dict(),
                    "trace_stage": self.trace.stage,
                    "effort": self.budget.effort,
                }, None

            if name == "submit_blocker":
                if not self.trace.may_complete():
                    raise PermissionError("Blocker submission is blocked until TRACE reaches exit")
                blocker = self._abstain(str(args["reason"]))
                blocker["evidence_ids"] = list(args.get("evidence_ids", []))
                return blocker, blocker

            raise ValueError(f"Unknown tool: {name}")
        except Exception as exc:
            self.ledger.add("tool_error", {"tool": name, "arguments": args, "error": str(exc)})
            return {"ok": False, "error": str(exc), "trace_stage": self.trace.stage}, None

    def _record_evidence(self, kind: str, payload: dict[str, Any]) -> str:
        event_id = self.ledger.add(kind, payload)
        evidence_id = f"evidence-{event_id}"
        self.ledger.events[-1].payload["evidence_id"] = evidence_id
        return evidence_id

    def _abstain(self, reason: str) -> dict[str, Any]:
        return {"status": "abstained", "summary": reason, "claims": [], "verification": None}

    @staticmethod
    def _tools() -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "name": "advance_trace",
                "description": "Advance exactly one TRACE stage in the frozen order.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "stage": {"type": "string", "enum": ["rip", "assemble", "contain", "exit"]},
                        "summary": {"type": "string"},
                    },
                    "required": ["stage", "summary"],
                    "additionalProperties": False,
                },
            },
            {
                "type": "function",
                "name": "list_files",
                "description": "List files inside the repository.",
                "parameters": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "additionalProperties": False,
                },
            },
            {
                "type": "function",
                "name": "read_file",
                "description": "Read one UTF-8 repository file.",
                "parameters": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                    "additionalProperties": False,
                },
            },
            {
                "type": "function",
                "name": "write_file",
                "description": "Create or replace one UTF-8 repository file. Allowed only in ASSEMBLE or CONTAIN.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "content": {"type": "string"},
                    },
                    "required": ["path", "content"],
                    "additionalProperties": False,
                },
            },
            {
                "type": "function",
                "name": "run_command",
                "description": "Run a non-network shell command inside the repository sandbox.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {"type": "string"},
                        "timeout": {"type": "integer", "minimum": 1, "maximum": 900},
                    },
                    "required": ["command"],
                    "additionalProperties": False,
                },
            },
            {
                "type": "function",
                "name": "submit_result",
                "description": "Request REVAL verification and complete only if every required gate passes.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "summary": {"type": "string"},
                        "claims": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "text": {"type": "string"},
                                    "evidence_ids": {"type": "array", "items": {"type": "string"}},
                                },
                                "required": ["text", "evidence_ids"],
                                "additionalProperties": False,
                            },
                        },
                    },
                    "required": ["summary", "claims"],
                    "additionalProperties": False,
                },
            },
            {
                "type": "function",
                "name": "submit_blocker",
                "description": "Exit with an explicit blocker when verified completion is impossible.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "reason": {"type": "string"},
                        "evidence_ids": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["reason", "evidence_ids"],
                    "additionalProperties": False,
                },
            },
        ]
