from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from .ledger import RunLedger
from .sandbox import CommandResult, Workspace


@dataclass(frozen=True)
class CheckResult:
    name: str
    command: str
    required: bool
    result: CommandResult
    evidence_id: str

    @property
    def passed(self) -> bool:
        return self.result.returncode == 0


@dataclass
class VerificationReport:
    checks: list[CheckResult] = field(default_factory=list)
    changed_files: list[str] = field(default_factory=list)
    scope_violations: list[str] = field(default_factory=list)
    unsupported_claims: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return (
            all(check.passed for check in self.checks if check.required)
            and not self.scope_violations
            and not self.unsupported_claims
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "checks": [
                {
                    "name": check.name,
                    "command": check.command,
                    "required": check.required,
                    "passed": check.passed,
                    "returncode": check.result.returncode,
                    "stdout": check.result.stdout,
                    "stderr": check.result.stderr,
                    "evidence_id": check.evidence_id,
                }
                for check in self.checks
            ],
            "changed_files": self.changed_files,
            "scope_violations": self.scope_violations,
            "unsupported_claims": self.unsupported_claims,
        }


class RevalVerifier:
    def __init__(self, workspace: Workspace, ledger: RunLedger, always_run: list[str]) -> None:
        self.workspace = workspace
        self.ledger = ledger
        self.always_run = always_run

    def verify(
        self,
        check_commands: list[str],
        allowed_paths: list[str],
        claims: list[dict[str, Any]],
    ) -> VerificationReport:
        report = VerificationReport()
        commands = self._dedupe([*self.always_run, *check_commands, *self._autodetect_checks()])
        for index, command in enumerate(commands, start=1):
            result = self.workspace.run(command)
            payload = {
                "name": f"check-{index}",
                "command": command,
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
            event_id = self.ledger.add("verification_check", payload)
            evidence_id = f"evidence-{event_id}"
            self.ledger.events[-1].payload["evidence_id"] = evidence_id
            report.checks.append(
                CheckResult(
                    name=f"check-{index}",
                    command=command,
                    required=True,
                    result=result,
                    evidence_id=evidence_id,
                )
            )

        report.changed_files = self._changed_files()
        report.scope_violations = self._scope_violations(report.changed_files, allowed_paths)
        report.unsupported_claims = self._unsupported_claims(claims)
        self.ledger.add("verification_report", report.to_dict())
        return report

    def _changed_files(self) -> list[str]:
        result = self.workspace.run("git status --short")
        files: list[str] = []
        for line in result.stdout.splitlines():
            if len(line) >= 4:
                path = line[3:].strip()
                if " -> " in path:
                    path = path.split(" -> ", 1)[1]
                files.append(path)
        return sorted(set(files))

    @staticmethod
    def _scope_violations(changed_files: list[str], allowed_paths: list[str]) -> list[str]:
        if not allowed_paths:
            return []
        normalized = [path.rstrip("/") for path in allowed_paths]
        return [
            path
            for path in changed_files
            if not any(path == allowed or path.startswith(f"{allowed}/") for allowed in normalized)
        ]

    def _unsupported_claims(self, claims: list[dict[str, Any]]) -> list[str]:
        known = self.ledger.evidence_ids()
        failures: list[str] = []
        for index, claim in enumerate(claims, start=1):
            text = str(claim.get("text", "")).strip()
            evidence = claim.get("evidence_ids", [])
            if not text:
                failures.append(f"claim {index} has no text")
            if not evidence:
                failures.append(f"claim {index} has no evidence")
                continue
            unknown = [item for item in evidence if item not in known]
            if unknown:
                failures.append(f"claim {index} cites unknown evidence: {unknown}")
        return failures

    def _autodetect_checks(self) -> list[str]:
        root = self.workspace.root
        commands: list[str] = []

        if (root / "pyproject.toml").exists() or (root / "pytest.ini").exists():
            if (root / "tests").exists():
                commands.append("python -m pytest -q")

        package_json = root / "package.json"
        if package_json.exists():
            try:
                scripts = json.loads(package_json.read_text()).get("scripts", {})
            except (json.JSONDecodeError, OSError):
                scripts = {}
            for script in ("test", "lint", "build"):
                value = scripts.get(script)
                if value and "no test specified" not in value:
                    commands.append(f"npm run {script}")

        makefile = root / "Makefile"
        if makefile.exists():
            text = makefile.read_text(errors="replace")
            if "check:" in text:
                commands.append("make check")

        return commands

    @staticmethod
    def _dedupe(items: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for item in items:
            if item not in seen:
                seen.add(item)
                result.append(item)
        return result
