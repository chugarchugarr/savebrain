from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ModelTurn:
    response_id: str
    tool_calls: list[dict[str, Any]]
    text: str
    input_tokens: int
    output_tokens: int
    usd: float


class OpenAIReasoningSession:
    def __init__(self, model: str, instructions: str) -> None:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("Install the package with `pip install -e .`") from exc
        self.client = OpenAI()
        self.model = model
        self.instructions = instructions
        self.previous_response_id: str | None = None
        self.input_rate = float(os.getenv("OPENAI_INPUT_USD_PER_MILLION", "0"))
        self.output_rate = float(os.getenv("OPENAI_OUTPUT_USD_PER_MILLION", "0"))

    def turn(self, input_items: list[dict[str, Any]], tools: list[dict[str, Any]], effort: str) -> ModelTurn:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "instructions": self.instructions,
            "input": input_items,
            "tools": tools,
            "reasoning": {"effort": effort},
        }
        if self.previous_response_id:
            kwargs["previous_response_id"] = self.previous_response_id
        response = self.client.responses.create(**kwargs)
        self.previous_response_id = response.id

        tool_calls: list[dict[str, Any]] = []
        for item in response.output:
            if getattr(item, "type", None) == "function_call":
                raw_arguments = getattr(item, "arguments", "{}")
                try:
                    arguments = json.loads(raw_arguments)
                except json.JSONDecodeError:
                    arguments = {"_raw": raw_arguments}
                tool_calls.append(
                    {
                        "call_id": item.call_id,
                        "name": item.name,
                        "arguments": arguments,
                    }
                )

        usage = getattr(response, "usage", None)
        input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
        output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
        usd = (input_tokens * self.input_rate + output_tokens * self.output_rate) / 1_000_000
        return ModelTurn(
            response_id=response.id,
            tool_calls=tool_calls,
            text=getattr(response, "output_text", "") or "",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            usd=usd,
        )
