from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
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
    cache_write_tokens: int = 0
    web_search_calls: int = 0
    long_context: bool = False
    pricing: dict[str, Any] = field(default_factory=dict)


class OpenAIReasoningSession:
    def __init__(self, model: str, instructions: str, pricing: dict[str, Any] | None = None) -> None:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("Install the package with `pip install -e .`") from exc
        self.client = OpenAI()
        self.model = model
        self.instructions = instructions
        self.previous_response_id: str | None = None
        self.pricing = dict(pricing or {})

    def turn(self, input_items: list[dict[str, Any]], tools: list[dict[str, Any]], effort: str) -> ModelTurn:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "instructions": self.instructions,
            "input": input_items,
            "tools": tools,
            "reasoning": {"effort": effort},
        }
        if any(tool.get("type") == "web_search" for tool in tools):
            kwargs["include"] = ["web_search_call.action.sources"]
        if self.previous_response_id:
            kwargs["previous_response_id"] = self.previous_response_id
        response = self.client.responses.create(**kwargs)
        self.previous_response_id = response.id

        tool_calls: list[dict[str, Any]] = []
        external_sources: list[dict[str, str]] = []
        tool_call_count = 0
        web_search_calls = 0
        for item in response.output:
            item_type = str(getattr(item, "type", ""))
            if item_type.endswith("_call"):
                tool_call_count += 1
            if item_type == "web_search_call":
                web_search_calls += 1
                action = getattr(item, "action", None)
                action_url = str(getattr(action, "url", "") or "").strip()
                if action_url:
                    external_sources.append(
                        {
                            "url": action_url,
                            "title": "",
                            "source_type": str(getattr(action, "type", "web")),
                        }
                    )
                for source in getattr(action, "sources", []) or []:
                    url = str(getattr(source, "url", "") or "").strip()
                    if url:
                        external_sources.append(
                            {
                                "url": url,
                                "title": str(getattr(source, "title", "") or ""),
                                "source_type": str(getattr(source, "type", "web")),
                            }
                        )
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
                                    "source_type": "citation",
                                }
                            )

        external_sources = _dedupe_sources(external_sources)
        usage = getattr(response, "usage", None)
        input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
        output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
        input_details = getattr(usage, "input_tokens_details", None)
        cached_input_tokens = int(getattr(input_details, "cached_tokens", 0) or 0)
        cache_write_tokens = int(getattr(input_details, "cache_write_tokens", 0) or 0)
        usd, pricing_breakdown = calculate_cost(
            model=self.model,
            input_tokens=input_tokens,
            cached_input_tokens=cached_input_tokens,
            cache_write_tokens=cache_write_tokens,
            output_tokens=output_tokens,
            web_search_calls=web_search_calls,
            pricing=self.pricing,
        )
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
            cache_write_tokens=cache_write_tokens,
            web_search_calls=web_search_calls,
            long_context=bool(pricing_breakdown["long_context"]),
            pricing=pricing_breakdown,
        )


def calculate_cost(
    *,
    model: str,
    input_tokens: int,
    cached_input_tokens: int,
    cache_write_tokens: int,
    output_tokens: int,
    web_search_calls: int,
    pricing: dict[str, Any],
) -> tuple[float, dict[str, Any]]:
    model_rates = dict(pricing.get("models", {}).get(model, {}))
    input_rate = _rate("OPENAI_INPUT_USD_PER_MILLION", model_rates, "input_usd_per_million")
    cached_rate = _rate(
        "OPENAI_CACHED_INPUT_USD_PER_MILLION",
        model_rates,
        "cached_input_usd_per_million",
    )
    cache_write_rate = _rate(
        "OPENAI_CACHE_WRITE_USD_PER_MILLION",
        model_rates,
        "cache_write_usd_per_million",
    )
    output_rate = _rate("OPENAI_OUTPUT_USD_PER_MILLION", model_rates, "output_usd_per_million")
    web_search_rate = float(
        os.getenv(
            "OPENAI_WEB_SEARCH_USD_PER_CALL",
            str(pricing.get("web_search_usd_per_call", 0)),
        )
    )
    threshold = int(pricing.get("long_context_input_threshold", 272_000))
    long_context = input_tokens > threshold
    input_multiplier = float(pricing.get("long_context_input_multiplier", 2.0)) if long_context else 1.0
    output_multiplier = float(pricing.get("long_context_output_multiplier", 1.5)) if long_context else 1.0
    uncached_input_tokens = max(input_tokens - cached_input_tokens - cache_write_tokens, 0)
    token_usd = (
        uncached_input_tokens * input_rate * input_multiplier
        + cached_input_tokens * cached_rate * input_multiplier
        + cache_write_tokens * cache_write_rate * input_multiplier
        + output_tokens * output_rate * output_multiplier
    ) / 1_000_000
    tool_usd = web_search_calls * web_search_rate
    total = token_usd + tool_usd
    return total, {
        "source": pricing.get("source"),
        "as_of": pricing.get("as_of"),
        "model": model,
        "long_context": long_context,
        "long_context_input_threshold": threshold,
        "input_multiplier": input_multiplier,
        "output_multiplier": output_multiplier,
        "input_usd_per_million": input_rate,
        "cached_input_usd_per_million": cached_rate,
        "cache_write_usd_per_million": cache_write_rate,
        "output_usd_per_million": output_rate,
        "web_search_usd_per_call": web_search_rate,
        "token_usd": token_usd,
        "tool_usd": tool_usd,
        "total_usd": total,
    }


def _rate(env_name: str, model_rates: dict[str, Any], key: str) -> float:
    return float(os.getenv(env_name, str(model_rates.get(key, 0))))


def _dedupe_sources(sources: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[tuple[str, str]] = set()
    result: list[dict[str, str]] = []
    for source in sources:
        key = (source["url"], source.get("source_type", ""))
        if key not in seen:
            seen.add(key)
            result.append(source)
    return result
