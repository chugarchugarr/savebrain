import subprocess
from pathlib import Path

from tro_frontier.ledger import RunLedger
from tro_frontier.reval import RevalVerifier
from tro_frontier.sandbox import Workspace


def test_reval_passes_grounded_claim(tmp_path: Path) -> None:
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    (tmp_path / "answer.txt").write_text("ok\n")
    workspace = Workspace(tmp_path)
    ledger = RunLedger(run_id="run", manifest_sha256="x" * 64, task_id="task")
    evidence_id = "evidence-seed"
    ledger.add("seed", {"evidence_id": evidence_id})
    verifier = RevalVerifier(workspace=workspace, ledger=ledger, always_run=[])
    report = verifier.verify(
        check_commands=["test -f answer.txt"],
        allowed_paths=["answer.txt"],
        claims=[{"text": "answer exists", "evidence_ids": [evidence_id]}],
    )
    assert report.passed
