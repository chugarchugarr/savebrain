from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class FrozenManifest:
    path: Path
    data: dict[str, Any]
    sha256: str

    @property
    def name(self) -> str:
        return str(self.data["name"])

    @property
    def version(self) -> str:
        return str(self.data["version"])


def load_manifest(path: str | Path) -> FrozenManifest:
    manifest_path = Path(path).expanduser().resolve()
    raw = manifest_path.read_bytes()
    data = json.loads(raw)
    _validate_manifest(data)
    return FrozenManifest(path=manifest_path, data=data, sha256=hashlib.sha256(raw).hexdigest())


def _validate_manifest(data: dict[str, Any]) -> None:
    required = {"name", "version", "model", "trace", "reval", "oro", "internet", "logging"}
    missing = required.difference(data)
    if missing:
        raise ValueError(f"Manifest missing keys: {sorted(missing)}")

    stages = data["trace"].get("stages")
    expected = ["target", "rip", "assemble", "contain", "exit"]
    if stages != expected:
        raise ValueError(f"TRACE stages must be frozen as {expected}")

    efforts = data["model"].get("reasoning_efforts")
    if not efforts or not isinstance(efforts, list):
        raise ValueError("At least one reasoning effort is required")
