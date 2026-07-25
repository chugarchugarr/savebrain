from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class OroBudget:
    max_steps: int
    max_repairs: int
    max_wall_seconds: int
    max_usd: float
    efforts: list[str]
    escalate_effort: bool = True
    started_at: float = field(default_factory=time.time)
    steps: int = 0
    repairs: int = 0
    effort_index: int = 0
    usd: float = 0.0

    @property
    def effort(self) -> str:
        return self.efforts[min(self.effort_index, len(self.efforts) - 1)]

    def consume_step(self) -> None:
        self.steps += 1

    def record_usage(self, usd: float) -> None:
        self.usd += usd

    def verification_failed(self) -> None:
        self.repairs += 1
        if self.escalate_effort and self.effort_index < len(self.efforts) - 1:
            self.effort_index += 1

    def exhausted(self) -> tuple[bool, str | None]:
        if self.steps >= self.max_steps:
            return True, "maximum model steps reached"
        if self.repairs > self.max_repairs:
            return True, "maximum repair cycles reached"
        if time.time() - self.started_at >= self.max_wall_seconds:
            return True, "maximum wall time reached"
        if self.max_usd > 0 and self.usd >= self.max_usd:
            return True, "maximum USD budget reached"
        return False, None
