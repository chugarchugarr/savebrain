from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ModelTurn:
    response_id: str
    model: str
    tool_calls: list[dict[str, Any]]
    external_sources: list[dict[str, str]]
    text: str
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    tool_call_count: int
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
        self.cached_input_rate = float(os.getenv("OPENAI_CACHED_INPUT_USD_PER_MILLION", "0"))
        self.output_rate = float(os.getenv("OPENAI_OUTPUT_USD_PER_MILLION", "0"))
        self.tool_rate = float(os.getenv("OPENAI_TOOL_USD_PER_CALL", "0"))

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
        external_sources: list[dict[str, str]] = []
        tool_call_count = 0
        for item in response.output:
            item_type = str(getattr(item, "type", ""))
            if item_type.endswith("_call"):
                tool_call_count += 1
            if item_type == "function_call":
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
            for content in getattr(item, "content", []) or []:
                for annotation in getattr(content, "annotations", []) or []:
                    if getattr(annotation, "type", None) == "url_citation":
                        url = str(getattr(annotation, "url", "")).strip()
                        if url:
                            external_sources.append(
                                {
                                    "url": url,
                                    "title": str(getattr(annotation, "title", "")),
                                }
                            )

        usage = getattr(response, "usage", None)
        input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
        output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
        input_details = getattr(usage, "input_tokens_details", None)
        cached_input_tokens = int(getattr(input_details, "cached_tokens", 0) or 0)
        uncached_input_tokens = max(input_tokens - cached_input_tokens, 0)
        usd = (
            uncached_input_tokens * self.input_rate
            + cached_input_tokens * self.cached_input_rate
            + output_tokens * self.output_rate
        ) / 1_000_000
        usd += tool_call_count * self.tool_rate
        return ModelTurn(
            response_id=response.id,
            model=self.model,
            tool_calls=tool_calls,
            external_sources=external_sources,
            text=getattr(response, "output_text", "") or "",
            input_tokens=input_tokens,
            cached_input_tokens=cached_input_tokens,
            output_tokens=output_tokens,
            tool_call_count=tool_call_count,
            usd=usd,
        )
