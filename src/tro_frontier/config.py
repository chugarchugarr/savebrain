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

    @property
    def components(self) -> dict[str, bool]:
        configured = self.data.get("components", {})
        return {
            "trace": bool(configured.get("trace", True)),
            "reval": bool(configured.get("reval", True)),
            "oro": bool(configured.get("oro", True)),
        }


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

    route = data["model"].get("route", [])
    if route:
        starts = [int(item["start_repair"]) for item in route]
        if starts != sorted(starts) or starts[0] != 0:
            raise ValueError("Model route must start at repair 0 and remain ordered")
        for item in route:
            for key in ("name", "model_env", "default_model", "start_repair"):
                if key not in item:
                    raise ValueError(f"Model route tier missing {key}")

    internet = data["internet"]
    mode = str(internet.get("mode", "closed"))
    if mode not in {"closed", "fair_use"}:
        raise ValueError("internet.mode must be closed or fair_use")
    if mode == "fair_use" and not internet.get("require_lineage"):
        raise ValueError("Fair-use internet requires source lineage")
