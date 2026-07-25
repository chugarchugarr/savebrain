import hashlib
from pathlib import Path

from tro_frontier.config import load_manifest


def test_frozen_manifest_loads() -> None:
    path = Path(__file__).parents[1] / "frozen" / "trace-reval-oro-v0.1.json"
    manifest = load_manifest(path)
    assert manifest.name == "GPT-5.6 Sol + TRACE + REVAL + ORO"
    assert len(manifest.sha256) == 64
    assert manifest.data["trace"]["stages"] == ["target", "rip", "assemble", "contain", "exit"]


def test_v01_frozen_bytes_are_unchanged() -> None:
    path = Path(__file__).parents[1] / "frozen" / "trace-reval-oro-v0.1.json"
    assert hashlib.sha256(path.read_bytes()).hexdigest() == (
        "383339f18bd5e421e82c8bac40bd416dbb91be836ae22cec6197a3ce8b2551da"
    )


def test_v02_frontiercode_contract_loads() -> None:
    path = Path(__file__).parents[1] / "frozen" / "trace-reval-oro-v0.2.json"
    manifest = load_manifest(path)
    assert manifest.version == "0.2.0"
    assert manifest.data["model"]["reasoning_efforts"] == [
        "none",
        "low",
        "medium",
        "high",
        "xhigh",
        "max",
    ]
    assert [tier["name"] for tier in manifest.data["model"]["route"]] == ["luna", "terra", "sol"]
    assert set(manifest.data["pricing"]["models"]) == {
        "gpt-5.6-luna",
        "gpt-5.6-terra",
        "gpt-5.6-sol",
    }
