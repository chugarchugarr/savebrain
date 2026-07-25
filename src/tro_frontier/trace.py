from __future__ import annotations

from dataclasses import dataclass

STAGES = ("target", "rip", "assemble", "contain", "exit")


@dataclass
class TraceState:
    index: int = 0

    @property
    def stage(self) -> str:
        return STAGES[self.index]

    def advance(self, requested_stage: str) -> None:
        if self.index >= len(STAGES) - 1:
            raise ValueError("TRACE is already at exit")
        expected = STAGES[self.index + 1]
        if requested_stage != expected:
            raise ValueError(f"Invalid TRACE transition: {self.stage} -> {requested_stage}; expected {expected}")
        self.index += 1

    def may_write(self) -> bool:
        return self.stage in {"assemble", "contain"}

    def may_complete(self) -> bool:
        return self.stage == "exit"


def system_instructions(*, version: str = "0.1.0", internet_mode: str = "closed") -> str:
    if internet_mode == "fair_use":
        internet_rule = (
            "Fair internet use is permitted for documentation, API references, error searches, package metadata, "
            "and background concepts. Never seek benchmark solutions. Record every external source and its purpose."
        )
    else:
        internet_rule = "Do not use the internet or solution-bearing external sources."

    return f"""You are GPT running the frozen TRACE + REVAL + ORO v{version} coding policy.

TRACE is mandatory and ordered when enabled:
1. TARGET: restate the exact requested repository state and success conditions.
2. RIP: inspect the repository, expose assumptions, constraints, regressions, and missing evidence.
3. ASSEMBLE: make the smallest complete implementation that satisfies the target.
4. CONTAIN: run verification, repair failures, prevent scope drift, and preserve unrelated behavior.
5. EXIT: submit only verified completion or an explicit blocker/abstention.

Rules:
- Advance stages only through the advance_trace tool when TRACE is enabled.
- Do not write before ASSEMBLE when TRACE is enabled.
- Use repository evidence, not confidence, as the completion signal.
- {internet_rule}
- Every final factual claim must cite one or more evidence IDs when REVAL is enabled.
- Prefer the smallest reversible change. Do not rewrite unrelated code.
- A failed check is a repair instruction, not something to explain away.
- Submit a blocker when verification cannot be resolved within the frozen budget.
"""
