from pathlib import Path

from tro_frontier.config import load_manifest


def test_frozen_manifest_loads() -> None:
    path = Path(__file__).parents[1] / "frozen" / "trace-reval-oro-v0.1.json"
    manifest = load_manifest(path)
    assert manifest.name == "GPT-5.6 Sol + TRACE + REVAL + ORO"
    assert len(manifest.sha256) == 64
    assert manifest.data["trace"]["stages"] == ["target", "rip", "assemble", "contain", "exit"]
