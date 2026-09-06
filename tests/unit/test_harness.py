"""Contract tests for the Harness composition root (the CLI/web entry point)."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from om_harness.harness import Harness
from om_harness.models.task import TaskStatus


@pytest.fixture
def repo(tmp_path: Any) -> Any:
    import subprocess

    subprocess.run(
        ["git", "init", "-q"], cwd=tmp_path, check=True, capture_output=True, shell=False
    )
    (tmp_path / "calc.py").write_text("def add(a, b):\n    return a - b  # buggy\n")
    return tmp_path


async def test_run_completes_offline_with_mock_provider(repo: Any) -> None:
    harness = Harness(repo_root=repo, env={})
    outcome = await harness.run("fix the sign bug in calc.py")
    assert outcome.status == "completed"
    assert outcome.results[0].status == TaskStatus.completed
    assert outcome.usage.requests >= 1
    # Session and events were persisted
    sessions = harness.sessions.list_sessions()
    assert len(sessions) == 1
    events = harness.store.read_events(outcome.session_id)
    types = [e.type.value for e in events]
    assert "run.started" in types and "run.completed" in types
    # A checkpoint was saved for resume
    assert harness.store.latest_checkpoint(outcome.session_id) is not None


async def test_run_persists_no_secret_material(repo: Any) -> None:
    # Assembled at runtime so no credential-looking literal exists in source.
    secret_value = "super-secret-" + "live-key-do-not-leak"
    env = {"OPENAI_API_KEY": secret_value}
    harness = Harness(repo_root=repo, env=env)
    await harness.run("some goal")
    # Scan the whole durable state directory for the secret.
    state_dir = repo / ".om-harness"
    for path in state_dir.rglob("*"):
        if path.is_file():
            content = path.read_text(encoding="utf-8", errors="replace")
            assert secret_value not in content, f"secret leaked in {path}"


async def test_resume_uses_latest_session(repo: Any) -> None:
    harness = Harness(repo_root=repo, env={})
    first = await harness.run("first goal")
    harness2 = Harness(repo_root=repo, env={})
    outcome = await harness2.run("second goal", resume=True)
    assert outcome.session_id == first.session_id
    session = harness2.store.load_session(outcome.session_id)
    assert len(session.runs) == 2


async def test_init_repo_prepares_state_dir_and_gitignore(repo: Any) -> None:
    Harness.init_repo(repo)
    assert (repo / ".om-harness").is_dir()
    gitignore = (repo / ".gitignore").read_text()
    assert ".om-harness/" in gitignore
    # Idempotent
    Harness.init_repo(repo)
    assert gitignore.count(".om-harness/") == 1


async def test_doctor_reports_environment(repo: Any) -> None:
    Harness.init_repo(repo)
    harness = Harness(repo_root=repo, env={})
    report = harness.doctor()
    names = {item.name for item in report.items}
    assert {"git_repository", "config", "state_store", "providers"} <= names
    git_item = next(i for i in report.items if i.name == "git_repository")
    assert git_item.ok


async def test_status_summarizes_state(repo: Any) -> None:
    harness = Harness(repo_root=repo, env={})
    await harness.run("a goal")
    status = harness.status()
    assert status["sessions"] == 1
    assert status["checkpoints"] >= 1
    assert status["default_model"] == "mock:echo"


def test_approval_ask_non_interactive_denies_writes(repo: Any) -> None:
    """CI-style default: no approvals possible, so writes are refused."""
    harness = Harness(repo_root=repo, env={}, interactive=False, approval_policy="ask")

    async def attempt() -> object:
        return await harness.executor.execute("write_file", {"path": "x.txt", "content": "nope"})

    result = asyncio.run(attempt())
    assert not result.ok  # type: ignore[attr-defined]
    assert not (repo / "x.txt").exists()


# -- skills integration --------------------------------------------------------


def _write_skill(skills_dir: Any, name: str, description: str, body: str = "Do it.") -> None:
    d = skills_dir / name
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n\n{body}\n",
        encoding="utf-8",
    )


def test_skills_from_user_dir_are_discovered_and_active(
    repo: Any, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    skills_dir = tmp_path / "agents-skills"
    _write_skill(skills_dir, "analyse", "pick a method")
    monkeypatch.setenv("OM_HARNESS_SKILLS_DIR", str(skills_dir))

    harness = Harness(repo_root=repo, env={})
    assert "analyse" in harness.skills
    assert harness.registry.has("skill")
    assert harness.status()["skills"] == ["analyse"]
    assert "analyse" in harness.assembler.system_prompt("chat")


def test_repo_level_skills_override_user_skills(
    repo: Any, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    user_dir = tmp_path / "user-skills"
    _write_skill(user_dir, "shared", "user version")
    monkeypatch.setenv("OM_HARNESS_SKILLS_DIR", str(user_dir))
    _write_skill(repo / ".agents" / "skills", "shared", "repo version")

    harness = Harness(repo_root=repo, env={})
    assert harness.skills["shared"].description == "repo version"
    assert harness.skills["shared"].source == "repo"


def test_skills_disabled_by_config_registers_no_tool(
    repo: Any, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_skill(tmp_path / "s", "analyse", "pick a method")
    monkeypatch.setenv("OM_HARNESS_SKILLS_DIR", str(tmp_path / "s"))
    (repo / "om-harness.toml").write_text("[skills]\nenabled = false\n", encoding="utf-8")

    harness = Harness(repo_root=repo, env={})
    assert harness.skills == {}
    assert not harness.registry.has("skill")


def test_extra_skill_dirs_are_scanned(
    repo: Any, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    extra = tmp_path / "extra-pack"
    _write_skill(extra, "packed", "from extra dir")
    (repo / "om-harness.toml").write_text(
        f"[skills]\nextra_dirs = ['{extra.as_posix()}']\n", encoding="utf-8"
    )

    harness = Harness(repo_root=repo, env={})
    assert harness.skills["packed"].description == "from extra dir"
