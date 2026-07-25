from __future__ import annotations

import json
import os
import shlex
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SourceRecord:
    url: str
    purpose: str
    source_type: str
    solution_bearing: bool
    notes: str = ""


@dataclass
class SourceLineage:
    records: list[SourceRecord] = field(default_factory=list)

    def record(
        self,
        *,
        url: str,
        purpose: str,
        source_type: str,
        solution_bearing: bool,
        notes: str = "",
    ) -> SourceRecord:
        normalized = url.strip()
        if not normalized:
            raise ValueError("External source URL is required")
        record = SourceRecord(
            url=normalized,
            purpose=purpose.strip(),
            source_type=source_type.strip(),
            solution_bearing=bool(solution_bearing),
            notes=notes.strip(),
        )
        self.records.append(record)
        return record

    @property
    def contaminated(self) -> bool:
        return any(record.solution_bearing for record in self.records)

    def to_dict(self) -> dict[str, Any]:
        return {
            "contaminated": self.contaminated,
            "records": [asdict(record) for record in self.records],
        }

    def save(self, path: str | Path) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n")
        return target

    def run_external_hook(self, path: str | Path, hook_env: str) -> dict[str, Any]:
        """Run a benchmark-owner contamination scanner against the saved lineage file.

        The hook command receives the lineage file path as its final shell argument and
        must return zero for a clean run. A missing hook is reported but does not invent
        a clean verdict.
        """
        command = os.getenv(hook_env, "").strip()
        if not command:
            return {"configured": False, "passed": None, "returncode": None, "stdout": "", "stderr": ""}
        proc = subprocess.run(
            ["bash", "-lc", f"{command} {shlex.quote(str(path))}"],
            text=True,
            capture_output=True,
            check=False,
        )
        return {
            "configured": True,
            "passed": proc.returncode == 0,
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
        }
