from pathlib import Path

import pytest

from tro_frontier.config import load_manifest
from tro_frontier.model import calculate_cost


def _pricing() -> dict:
    manifest = load_manifest(Path(__file__).parents[1] / "frozen" / "trace-reval-oro-v0.2.json")
    return manifest.data["pricing"]


def test_short_context_cost_includes_cache_write_and_web_search(monkeypatch) -> None:
    for variable in (
        "OPENAI_INPUT_USD_PER_MILLION",
        "OPENAI_CACHED_INPUT_USD_PER_MILLION",
        "OPENAI_CACHE_WRITE_USD_PER_MILLION",
        "OPENAI_OUTPUT_USD_PER_MILLION",
        "OPENAI_WEB_SEARCH_USD_PER_CALL",
    ):
        monkeypatch.delenv(variable, raising=False)

    total, breakdown = calculate_cost(
        model="gpt-5.6-luna",
        input_tokens=1_000,
        cached_input_tokens=100,
        cache_write_tokens=100,
        output_tokens=200,
        web_search_calls=2,
        pricing=_pricing(),
    )

    assert total == pytest.approx(0.022135)
    assert breakdown["token_usd"] == pytest.approx(0.002135)
    assert breakdown["tool_usd"] == pytest.approx(0.02)
    assert breakdown["long_context"] is False


def test_long_context_multiplier_applies_to_full_request(monkeypatch) -> None:
    for variable in (
        "OPENAI_INPUT_USD_PER_MILLION",
        "OPENAI_CACHED_INPUT_USD_PER_MILLION",
        "OPENAI_CACHE_WRITE_USD_PER_MILLION",
        "OPENAI_OUTPUT_USD_PER_MILLION",
        "OPENAI_WEB_SEARCH_USD_PER_CALL",
    ):
        monkeypatch.delenv(variable, raising=False)

    total, breakdown = calculate_cost(
        model="gpt-5.6-sol",
        input_tokens=273_000,
        cached_input_tokens=1_000,
        cache_write_tokens=2_000,
        output_tokens=1_000,
        web_search_calls=0,
        pricing=_pricing(),
    )

    assert total == pytest.approx(2.771)
    assert breakdown["long_context"] is True
    assert breakdown["input_multiplier"] == 2.0
    assert breakdown["output_multiplier"] == 1.5
