import subprocess

from tro_frontier.lineage import infer_command_sources


def test_infers_package_and_explicit_url_sources(tmp_path) -> None:
    records = infer_command_sources(
        "python -m pip install demo && curl https://docs.example.test/api",
        tmp_path,
    )
    assert {(record.purpose, record.source_type) for record in records} == {
        ("package_install", "python_package_registry"),
        ("retrieved_artifact", "command_url"),
    }


def test_infers_configured_git_remote(tmp_path) -> None:
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "remote", "add", "origin", "https://github.com/example/project.git"],
        cwd=tmp_path,
        check=True,
    )
    records = infer_command_sources("git fetch origin", tmp_path)
    assert any(
        record.url == "https://github.com/example/project.git"
        and record.purpose == "git_fetch"
        and record.source_type == "remote_repository_action"
        for record in records
    )
