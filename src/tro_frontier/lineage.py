from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

_URL_PATTERN = re.compile(r"https?://[^\s'\"<>]+")
_GIT_REMOTE_ACTION = re.compile(r"(?:^|[;&|]\s*)git\s+(clone|fetch|pull|push|ls-remote|submodule)\b")
_PIP_ACTION = re.compile(r"(?:^|[;&|]\s*)(?:python(?:\d+(?:\.\d+)?)?\s+-m\s+)?pip\s+install\b")
_NPM_ACTION = re.compile(r"(?:^|[;&|]\s*)(?:npm|npx|pnpm|yarn)\s+(?:install|add|update|dlx)\b")
_APT_ACTION = re.compile(r"(?:^|[;&|]\s*)(?:sudo\s+)?apt(?:-get)?\s+(?:install|update|upgrade)\b")


@dataclass(frozen=True)
class SourceRecord:
    url: str
    purpose: str
    source_type: str
    solution_bearing: bool
    notes: str = ""


@dataclass
class SourceLineage:
    records: list[SourceRecord] = field(default_factory=list)

    def record(
        self,
        *,
        url: str,
        purpose: str,
        source_type: str,
        solution_bearing: bool,
        notes: str = "",
    ) -> SourceRecord:
        normalized = url.strip()
        if not normalized:
            raise ValueError("External source URL is required")
        record = SourceRecord(
            url=normalized,
            purpose=purpose.strip(),
            source_type=source_type.strip(),
            solution_bearing=bool(solution_bearing),
            notes=notes.strip(),
        )
        self.records.append(record)
        return record

    @property
    def contaminated(self) -> bool:
        return any(record.solution_bearing for record in self.records)

    def to_dict(self) -> dict[str, Any]:
        return {
            "contaminated": self.contaminated,
            "records": [asdict(record) for record in self.records],
        }

    def save(self, path: str | Path) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n")
        return target

    def run_external_hook(self, path: str | Path, hook_env: str) -> dict[str, Any]:
        """Run a benchmark-owner contamination scanner against the saved lineage file.

        The hook command receives the lineage file path as its final shell argument and
        must return zero for a clean run. A missing hook is reported but does not invent
        a clean verdict.
        """
        command = os.getenv(hook_env, "").strip()
        if not command:
            return {"configured": False, "passed": None, "returncode": None, "stdout": "", "stderr": ""}
        proc = subprocess.run(
            ["bash", "-lc", f"{command} {shlex.quote(str(path))}"],
            text=True,
            capture_output=True,
            check=False,
        )
        return {
            "configured": True,
            "passed": proc.returncode == 0,
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
        }


def infer_command_sources(command: str, repo_root: str | Path) -> list[SourceRecord]:
    """Create lineage records for network-bearing shell actions.

    The records are mechanical provenance, not declarations that a source contains
    benchmark solutions. The external contamination hook remains the adjudicator.
    """
    records: list[SourceRecord] = []
    urls = [_clean_url(match) for match in _URL_PATTERN.findall(command)]
    for url in urls:
        records.append(
            SourceRecord(
                url=url,
                purpose="retrieved_artifact",
                source_type="command_url",
                solution_bearing=False,
                notes=command,
            )
        )

    git_match = _GIT_REMOTE_ACTION.search(command)
    if git_match:
        git_urls = [url for url in urls if _looks_like_repository(url)]
        if not git_urls:
            git_urls = _git_remote_urls(Path(repo_root))
        if not git_urls:
            git_urls = ["git://unresolved-remote"]
        for url in git_urls:
            records.append(
                SourceRecord(
                    url=url,
                    purpose=f"git_{git_match.group(1)}",
                    source_type="remote_repository_action",
                    solution_bearing=False,
                    notes=command,
                )
            )

    if _PIP_ACTION.search(command):
        records.append(
            SourceRecord(
                url=os.getenv("PIP_INDEX_URL", "https://pypi.org/simple"),
                purpose="package_install",
                source_type="python_package_registry",
                solution_bearing=False,
                notes=command,
            )
        )
    if _NPM_ACTION.search(command):
        records.append(
            SourceRecord(
                url=os.getenv("NPM_CONFIG_REGISTRY", "https://registry.npmjs.org"),
                purpose="package_install",
                source_type="javascript_package_registry",
                solution_bearing=False,
                notes=command,
            )
        )
    if _APT_ACTION.search(command):
        records.append(
            SourceRecord(
                url="apt://configured-system-sources",
                purpose="package_install",
                source_type="system_package_registry",
                solution_bearing=False,
                notes=command,
            )
        )
    return _dedupe_records(records)


def _git_remote_urls(root: Path) -> list[str]:
    proc = subprocess.run(
        ["git", "remote", "-v"],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        return []
    urls: list[str] = []
    for line in proc.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2:
            urls.append(parts[1])
    return list(dict.fromkeys(urls))


def _clean_url(url: str) -> str:
    return url.rstrip(".,;:)]}")


def _looks_like_repository(url: str) -> bool:
    return url.endswith(".git") or "github.com/" in url or "gitlab.com/" in url


def _dedupe_records(records: list[SourceRecord]) -> list[SourceRecord]:
    seen: set[tuple[str, str, str]] = set()
    result: list[SourceRecord] = []
    for record in records:
        key = (record.url, record.purpose, record.notes)
        if key not in seen:
            seen.add(key)
            result.append(record)
    return result
