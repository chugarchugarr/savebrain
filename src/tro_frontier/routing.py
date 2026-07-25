from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ModelTier:
    name: str
    model: str
    start_repair: int


class ModelRouter:
    """Deterministic Luna -> Terra -> Sol escalation keyed to failed verification."""

    def __init__(self, tiers: list[ModelTier]) -> None:
        if not tiers:
            raise ValueError("At least one model tier is required")
        self.tiers = sorted(tiers, key=lambda tier: tier.start_repair)
        self.history: list[dict[str, Any]] = []

    @classmethod
    def from_manifest(cls, model_config: dict[str, Any]) -> "ModelRouter":
        route = model_config.get("route")
        if not route:
            model = os.getenv(
                str(model_config.get("model_env", "OPENAI_MODEL")),
                str(model_config["default_model"]),
            )
            return cls([ModelTier(name="fixed", model=model, start_repair=0)])

        tiers: list[ModelTier] = []
        for raw in route:
            model = os.getenv(str(raw["model_env"]), str(raw["default_model"]))
            tiers.append(
                ModelTier(
                    name=str(raw["name"]),
                    model=model,
                    start_repair=int(raw["start_repair"]),
                )
            )
        return cls(tiers)

    def select(self, repairs: int) -> ModelTier:
        selected = self.tiers[0]
        for tier in self.tiers:
            if repairs >= tier.start_repair:
                selected = tier
            else:
                break
        event = {"repairs": repairs, "tier": selected.name, "model": selected.model}
        if not self.history or self.history[-1] != event:
            self.history.append(event)
        return selected
