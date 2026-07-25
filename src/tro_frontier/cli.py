from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import load_manifest
from .runner import AgentRunner, TaskSpec


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tro-frontier")
    parser.add_argument("task", help="Path to a task JSON file")
    parser.add_argument(
        "--manifest",
        default=str(Path(__file__).resolve().parents[2] / "frozen" / "trace-reval-oro-v0.2.json"),
        help="Path to the frozen policy manifest",
    )
    parser.add_argument("--output-dir", default="runs", help="Directory for immutable run ledgers")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    manifest = load_manifest(args.manifest)
    task = TaskSpec.from_json(args.task)
    result = AgentRunner(manifest=manifest, task=task, output_dir=args.output_dir).run()
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
