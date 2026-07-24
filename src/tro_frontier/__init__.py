"""TRACE + REVAL + ORO frontier-code adapter."""

from .adapter import run_task
from .config import FrozenManifest, load_manifest
from .runner import AgentRunner, TaskSpec

__all__ = ["AgentRunner", "FrozenManifest", "TaskSpec", "load_manifest", "run_task"]
__version__ = "0.1.0"
