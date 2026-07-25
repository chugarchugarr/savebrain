from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class LedgerEvent:
    sequence: int
    timestamp: float
    kind: str
    payload: dict[str, Any]


@dataclass
class RunLedger:
    run_id: str
    manifest_sha256: str
    task_id: str
    started_at: float = field(default_factory=time.time)
    events: list[LedgerEvent] = field(default_factory=list)
    usage: dict[str, float] = field(
        default_factory=lambda: {
            "input_tokens": 0,
            "cached_input_tokens": 0,
            "output_tokens": 0,
            "tool_calls": 0,
            "usd": 0.0,
        }
    )

    def add(self, kind: str, payload: dict[str, Any]) -> str:
        sequence = len(self.events) + 1
        event = LedgerEvent(sequence=sequence, timestamp=time.time(), kind=kind, payload=payload)
        self.events.append(event)
        canonical = json.dumps(asdict(event), sort_keys=True, separators=(",", ":"))
        return f"ev-{sequence}-{hashlib.sha256(canonical.encode()).hexdigest()[:12]}"

    def add_usage(
        self,
        input_tokens: int,
        output_tokens: int,
        usd: float,
        *,
        cached_input_tokens: int = 0,
        tool_calls: int = 0,
    ) -> None:
        self.usage["input_tokens"] += input_tokens
        self.usage["cached_input_tokens"] += cached_input_tokens
        self.usage["output_tokens"] += output_tokens
        self.usage["tool_calls"] += tool_calls
        self.usage["usd"] += usd

    def evidence_ids(self) -> set[str]:
        ids: set[str] = set()
        for event in self.events:
            evidence_id = event.payload.get("evidence_id")
            if isinstance(evidence_id, str):
                ids.add(evidence_id)
        return ids

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "manifest_sha256": self.manifest_sha256,
            "task_id": self.task_id,
            "started_at": self.started_at,
            "finished_at": time.time(),
            "usage": self.usage,
            "events": [asdict(event) for event in self.events],
        }

    def save(self, path: str | Path) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n")
