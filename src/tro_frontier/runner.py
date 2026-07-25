from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import FrozenManifest
from .ledger import RunLedger
from .lineage import SourceLineage, infer_command_sources
from .model import OpenAIReasoningSession
from .oro import OroBudget
from .reval import RevalVerifier
from .routing import ModelRouter
from .sandbox import Workspace
from .trace import TraceState, system_instructions

SessionFactory = Callable[[str, str], Any]


@dataclass(frozen=True)
class TaskSpec:
    task_id: str
    prompt: str
    repo: Path
    check_commands: list[str] = field(default_factory=list)
    allowed_paths: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_json(cls, path: str | Path) -> "TaskSpec":
        data = json.loads(Path(path).read_text())
        return cls(
            task_id=str(data["task_id"]),
            prompt=str(data["prompt"]),
            repo=Path(data["repo"]).expanduser().resolve(),
            check_commands=[str(item) for item in data.get("check_commands", [])],
            allowed_paths=[str(item) for item in data.get("allowed_paths", [])],
            metadata=dict(data.get("metadata", {})),
        )


class AgentRunner:
    def __init__(
        self,
        manifest: FrozenManifest,
        task: TaskSpec,
        output_dir: str | Path,
        session_factory: SessionFactory | None = None,
    ) -> None:
        self.manifest = manifest
        self.task = task
        self.output_dir = Path(output_dir).expanduser().resolve()
        try:
            self.output_dir.relative_to(task.repo.resolve())
        except ValueError:
            pass
        else:
            raise ValueError("Run output must be outside the task repository so artifacts cannot enter the patch")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.components = manifest.components
        run_id = f"{task.task_id}-{uuid.uuid4().hex[:12]}"
        self.ledger = RunLedger(
            run_id=run_id,
            manifest_sha256=manifest.sha256,
            task_id=task.task_id,
        )
        self.workspace = Workspace(
            task.repo,
            blocked_commands=list(manifest.data["internet"].get("blocked_commands", [])),
        )
        oro = manifest.data["oro"]
        efforts = list(manifest.data["model"]["reasoning_efforts"])
        self.budget = OroBudget(
            max_steps=int(oro["max_steps"]),
            max_repairs=int(oro["max_repairs"]),
            max_wall_seconds=int(oro["max_wall_seconds"]),
            max_usd=float(oro["max_usd"]),
            efforts=efforts if self.components["oro"] else [efforts[0]],
            escalate_effort=self.components["oro"] and bool(oro.get("escalate_effort_after_failed_verification", True)),
        )
        self.trace = TraceState(index=0 if self.components["trace"] else 4)

        model_config = dict(manifest.data["model"])
        if not self.components["oro"]:
            model_config.pop("route", None)
        self.router = ModelRouter.from_manifest(model_config)
        pricing = dict(manifest.data.get("pricing", {}))
        if session_factory is None:
            self.session_factory = lambda model, instructions: OpenAIReasoningSession(
                model,
                instructions,
                pricing=pricing,
            )
        else:
            self.session_factory = session_factory
        self.session: Any | None = None
        self.active_model: str | None = None
        self.active_tier: str | None = None

        self.verifier = RevalVerifier(
            workspace=self.workspace,
            ledger=self.ledger,
            always_run=list(manifest.data["reval"]["always_run"]),
        )
        self.source_lineage = SourceLineage()
        self.last_verification: dict[str, Any] | None = None
        self.pending_input: list[dict[str, Any]] = [self._initial_input()]

    def _initial_input(self) -> dict[str, Any]:
        return {
            "role": "user",
            "content": (
                f"Task ID: {self.task.task_id}\n"
                f"Repository: {self.task.repo}\n"
                f"Required checks: {self.task.check_commands}\n"
                f"Allowed paths: {self.task.allowed_paths or 'unrestricted'}\n"
                f"Components: {self.components}\n"
                f"Metadata: {self.task.metadata}\n\n"
                f"{self.task.prompt}"
            ),
        }

    def run(self) -> dict[str, Any]:
        self.ledger.add(
            "run_started",
            {
                "task": self.task.prompt,
                "repo": str(self.task.repo),
                "manifest": self.manifest.name,
                "manifest_sha256": self.manifest.sha256,
                "components": self.components,
                "metadata": self.task.metadata,
            },
        )

        final: dict[str, Any] | None = None
        while final is None:
            exhausted, reason = self.budget.exhausted()
            if exhausted:
                final = self._abstain(reason or "budget exhausted")
                break

            self.budget.consume_step()
            session = self._session_for_turn()
            try:
                turn = session.turn(self.pending_input, self._tools(), self.budget.effort)
            except Exception as exc:
                self.ledger.add("model_error", {"model": self.active_model, "error": str(exc)})
                final = self._abstain(f"model call failed: {exc}")
                break

            self.ledger.add_usage(
                turn.input_tokens,
                turn.output_tokens,
                turn.usd,
                cached_input_tokens=turn.cached_input_tokens,
                cache_write_tokens=turn.cache_write_tokens,
                tool_calls=turn.tool_call_count,
                web_search_calls=turn.web_search_calls,
            )
            self.budget.record_usage(turn.usd)
            for source in turn.external_sources:
                self._record_source(
                    url=source["url"],
                    purpose="provider_web_search",
                    source_type=source.get("source_type", "web"),
                    solution_bearing=False,
                    notes=source.get("title", ""),
                )
            self.ledger.add(
                "model_turn",
                {
                    "response_id": turn.response_id,
                    "model": turn.model,
                    "tier": self.active_tier,
                    "effort": self.budget.effort,
                    "text": turn.text,
                    "tool_calls": turn.tool_calls,
                    "external_sources": turn.external_sources,
                    "input_tokens": turn.input_tokens,
                    "cached_input_tokens": turn.cached_input_tokens,
                    "cache_write_tokens": turn.cache_write_tokens,
                    "output_tokens": turn.output_tokens,
                    "tool_call_count": turn.tool_call_count,
                    "web_search_calls": turn.web_search_calls,
                    "long_context": turn.long_context,
                    "pricing": turn.pricing,
                    "usd": turn.usd,
                },
            )

            if not turn.tool_calls:
                self.pending_input = [
                    {
                        "role": "user",
                        "content": "Use the provided function tools. Advance the enabled policy or submit a result.",
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

        return self._finalize(final)

    def _session_for_turn(self) -> Any:
        repairs = self.budget.repairs if self.components["oro"] else 0
        tier = self.router.select(repairs)
        if self.session is None or tier.model != self.active_model:
            previous_model = self.active_model
            self.session = self.session_factory(
                tier.model,
                system_instructions(
                    version=self.manifest.version,
                    internet_mode=str(self.manifest.data["internet"].get("mode", "closed")),
                ),
            )
            self.active_model = tier.model
            self.active_tier = tier.name
            self.ledger.add(
                "model_route",
                {
                    "from_model": previous_model,
                    "to_model": tier.model,
                    "tier": tier.name,
                    "repairs": repairs,
                    "effort": self.budget.effort,
                },
            )
            if previous_model is not None:
                self.pending_input = [
                    {
                        "role": "user",
                        "content": self._handoff_prompt(previous_model=previous_model),
                    }
                ]
        return self.session

    def _handoff_prompt(self, *, previous_model: str) -> str:
        verification = json.dumps(self.last_verification or {}, sort_keys=True)
        return (
            f"ORO escalated from {previous_model} to {self.active_model}. Continue the same task.\n"
            f"Task: {self.task.prompt}\n"
            f"Repository: {self.task.repo}\n"
            f"TRACE stage: {self.trace.stage}\n"
            f"Repair count: {self.budget.repairs}\n"
            f"Last verification: {verification}\n"
            "Inspect the repository state directly and repair only the surviving failures."
        )

    def _finalize(self, final: dict[str, Any]) -> dict[str, Any]:
        lineage_path = self.output_dir / f"{self.ledger.run_id}.sources.json"
        self.source_lineage.save(lineage_path)
        patch_path = self.output_dir / f"{self.ledger.run_id}.patch"
        patch_path.write_text(self.workspace.patch())

        final.update(
            {
                "run_id": self.ledger.run_id,
                "manifest_sha256": self.manifest.sha256,
                "manifest_version": self.manifest.version,
                "usage": dict(self.ledger.usage),
                "model_route": list(self.router.history),
                "lineage_path": str(lineage_path),
                "patch_path": str(patch_path),
            }
        )
        self.ledger.add("run_finished", final)
        ledger_path = self.output_dir / f"{self.ledger.run_id}.json"
        self.ledger.save(ledger_path)
        final["ledger_path"] = str(ledger_path)
        return final

    def _execute_tool(self, name: str, args: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None]:
        try:
            if name == "advance_trace":
                if not self.components["trace"]:
                    raise PermissionError("TRACE is disabled for this ablation")
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
                if self.components["trace"] and not self.trace.may_write():
                    raise PermissionError(f"Writes are blocked during TRACE stage {self.trace.stage}")
                path = str(args["path"])
                self.workspace.write_file(path, str(args["content"]))
                evidence_id = self._record_evidence("write_file", {"path": path})
                return {"ok": True, "path": path, "evidence_id": evidence_id}, None

            if name == "run_command":
                command = str(args["command"])
                timeout = int(args.get("timeout", 300))
                for source in infer_command_sources(command, self.task.repo):
                    self._record_source(
                        url=source.url,
                        purpose=source.purpose,
                        source_type=source.source_type,
                        solution_bearing=source.solution_bearing,
                        notes=source.notes,
                    )
                result = self.workspace.run(command, timeout=timeout)
                payload = result.to_dict()
                evidence_id = self._record_evidence("command", payload)
                payload["evidence_id"] = evidence_id
                return payload, None

            if name == "record_external_source":
                evidence_id = self._record_source(
                    url=str(args["url"]),
                    purpose=str(args["purpose"]),
                    source_type=str(args["source_type"]),
                    solution_bearing=bool(args["solution_bearing"]),
                    notes=str(args.get("notes", "")),
                )
                return {"ok": True, "evidence_id": evidence_id}, None

            if name == "submit_result":
                if self.components["trace"] and not self.trace.may_complete():
                    raise PermissionError("Completion is blocked until TRACE reaches exit")
                claims = list(args.get("claims", []))
                contamination = self._contamination_report()
                if contamination["contaminated"]:
                    blocker = self._abstain("solution-bearing external source detected")
                    blocker["contamination"] = contamination
                    return blocker, blocker

                if not self.components["reval"]:
                    completed = {
                        "status": "completed",
                        "summary": str(args.get("summary", "")),
                        "claims": claims,
                        "verification": None,
                        "contamination": contamination,
                    }
                    return completed, completed

                report = self.verifier.verify(
                    check_commands=self.task.check_commands,
                    allowed_paths=self.task.allowed_paths,
                    claims=claims,
                )
                self.last_verification = report.to_dict()
                if report.passed:
                    verified = {
                        "status": "verified",
                        "summary": str(args.get("summary", "")),
                        "claims": claims,
                        "verification": report.to_dict(),
                        "contamination": contamination,
                    }
                    return report.to_dict(), verified

                self.budget.verification_failed()
                if self.components["trace"]:
                    self.trace.index = 3
                return {
                    "status": "repair_required",
                    "verification": report.to_dict(),
                    "trace_stage": self.trace.stage,
                    "effort": self.budget.effort,
                    "next_model": self.router.select(self.budget.repairs).model,
                }, None

            if name == "submit_blocker":
                if self.components["trace"] and not self.trace.may_complete():
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

    def _record_source(
        self,
        *,
        url: str,
        purpose: str,
        source_type: str,
        solution_bearing: bool,
        notes: str,
    ) -> str:
        record = self.source_lineage.record(
            url=url,
            purpose=purpose,
            source_type=source_type,
            solution_bearing=solution_bearing,
            notes=notes,
        )
        return self._record_evidence("external_source", {"source": record.__dict__})

    def _contamination_report(self) -> dict[str, Any]:
        lineage_path = self.output_dir / f"{self.ledger.run_id}.sources.json"
        self.source_lineage.save(lineage_path)
        internet = self.manifest.data["internet"]
        hook = self.source_lineage.run_external_hook(
            lineage_path,
            str(internet.get("contamination_hook_env", "TRO_CONTAMINATION_CHECK_CMD")),
        )
        contaminated = self.source_lineage.contaminated or (hook["configured"] and hook["passed"] is False)
        payload = {
            "contaminated": contaminated,
            "declared_solution_source": self.source_lineage.contaminated,
            "external_hook": hook,
            "lineage_path": str(lineage_path),
        }
        self.ledger.add("contamination_check", payload)
        return payload

    def _abstain(self, reason: str) -> dict[str, Any]:
        return {"status": "abstained", "summary": reason, "claims": [], "verification": None}

    def _tools(self) -> list[dict[str, Any]]:
        tools: list[dict[str, Any]] = []
        if self.components["trace"]:
            tools.append(
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
                }
            )
        tools.extend(
            [
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
                    "description": "Create or replace one UTF-8 repository file.",
                    "parameters": {
                        "type": "object",
                        "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                        "required": ["path", "content"],
                        "additionalProperties": False,
                    },
                },
                {
                    "type": "function",
                    "name": "run_command",
                    "description": "Run a shell command inside the repository workspace.",
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
            ]
        )
        internet = self.manifest.data["internet"]
        if internet.get("enabled") and internet.get("mode") == "fair_use":
            tools.append({"type": "web_search"})
            tools.append(
                {
                    "type": "function",
                    "name": "record_external_source",
                    "description": "Record source lineage for any external URL or artifact used during the run.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "url": {"type": "string"},
                            "purpose": {
                                "type": "string",
                                "enum": list(internet.get("permitted_purposes", [])),
                            },
                            "source_type": {"type": "string"},
                            "solution_bearing": {"type": "boolean"},
                            "notes": {"type": "string"},
                        },
                        "required": ["url", "purpose", "source_type", "solution_bearing"],
                        "additionalProperties": False,
                    },
                }
            )
        tools.extend(
            [
                {
                    "type": "function",
                    "name": "submit_result",
                    "description": "Request completion; REVAL verifies it when enabled.",
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
                    "description": "Exit with an explicit blocker when completion is impossible.",
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
        )
        return tools
