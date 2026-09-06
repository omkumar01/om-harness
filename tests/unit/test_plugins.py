"""Contract tests for git-installable plugins and their active skills."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from om_harness.harness import Harness
from om_harness.plugins import (
    PluginError,
    install_plugin,
    load_plugins,
    parse_source,
    uninstall_plugin,
)


def _make_skill(dir_: Path, name: str, description: str, body: str = "Do the thing.") -> None:
    d = dir_ / name
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n\n{body}\n",
        encoding="utf-8",
    )


@pytest.fixture
def origin(tmp_path: Path) -> Path:
    """A local git repo shaped like a plugin (manifest + skills/)."""
    repo = tmp_path / "superpowers"
    (repo / "skills" / "brainstorm").mkdir(parents=True)
    (repo / "skills" / "brainstorm" / "SKILL.md").write_text(
        "---\nname: brainstorm\ndescription: refine rough ideas\n---\n\nAsk questions.\n",
        encoding="utf-8",
    )
    (repo / "plugin.json").write_text(
        '{"name": "superpowers", "description": "A collection of skills"}\n',
        encoding="utf-8",
    )
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    return repo


class TestParseSource:
    def test_git_shorthand(self) -> None:
        url, name = parse_source("git:github.com/obra/superpowers")
        assert url == "https://github.com/obra/superpowers"
        assert name == "superpowers"

    def test_git_full_url(self) -> None:
        url, name = parse_source("git:https://github.com/obra/superpowers")
        assert url == "https://github.com/obra/superpowers"
        assert name == "superpowers"

    def test_git_full_url_with_dot_git_suffix(self) -> None:
        url, name = parse_source("git:https://gitlab.com/group/thing.git")
        assert url == "https://gitlab.com/group/thing.git"
        assert name == "thing"

    def test_ssh_remote(self) -> None:
        url, name = parse_source("git:git@github.com:obra/superpowers.git")
        assert url == "git@github.com:obra/superpowers.git"
        assert name == "superpowers"

    def test_bare_shorthand_without_prefix(self) -> None:
        url, name = parse_source("obra/superpowers")
        assert url == "https://github.com/obra/superpowers"
        assert name == "superpowers"

    def test_local_path_source(self, tmp_path: Path) -> None:
        url, name = parse_source(str(tmp_path / "superpowers"))
        assert url == str(tmp_path / "superpowers")
        assert name == "superpowers"


class TestInstallUninstall:
    def test_install_clones_and_collects_skills(
        self, origin: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("OM_HARNESS_PLUGINS_DIR", str(tmp_path / "plugins"))
        plugin = install_plugin(str(origin))
        assert plugin.name == "superpowers"
        assert plugin.description == "A collection of skills"
        assert [s.name for s in plugin.skills] == ["brainstorm"]
        provenance = plugin.path / ".om-harness-plugin.json"
        assert provenance.exists()
        assert "superpowers" in provenance.read_text(encoding="utf-8")

    def test_reinstall_updates_existing_clone(
        self, origin: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("OM_HARNESS_PLUGINS_DIR", str(tmp_path / "plugins"))
        install_plugin(str(origin))
        # Add a new skill to the origin, then reinstall to pick it up.
        _make_skill(origin / "skills", "new-skill", "brand new")
        subprocess.run(["git", "add", "."], cwd=origin, check=True, capture_output=True)
        subprocess.run(
            ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "new skill"],
            cwd=origin,
            check=True,
            capture_output=True,
        )
        plugin = install_plugin(str(origin))
        assert "new-skill" in [s.name for s in plugin.skills]

    def test_uninstall_removes_plugin(
        self, origin: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("OM_HARNESS_PLUGINS_DIR", str(tmp_path / "plugins"))
        install_plugin(str(origin))
        uninstall_plugin("superpowers")
        assert load_plugins() == []

    def test_uninstall_unknown_plugin_raises(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("OM_HARNESS_PLUGINS_DIR", str(tmp_path / "plugins"))
        with pytest.raises(PluginError):
            uninstall_plugin("ghost")


class TestLoadPlugins:
    def test_loads_manifest_and_skills_dir(self, origin: Path, tmp_path: Path) -> None:
        origin.rename(tmp_path / "installed-superpowers")
        plugins = load_plugins(plugins_dir=tmp_path)
        assert len(plugins) == 1
        plugin = plugins[0]
        assert plugin.name == "superpowers"
        assert plugin.skills[0].name == "brainstorm"
        assert plugin.skills[0].source == "plugin:superpowers"

    def test_loads_skills_from_dot_agents_layout(self, tmp_path: Path) -> None:
        (tmp_path / "myplugin" / ".agents" / "skills" / "helper").mkdir(parents=True)
        (tmp_path / "myplugin" / ".agents" / "skills" / "helper" / "SKILL.md").write_text(
            "---\ndescription: helps out\n---\nbody", encoding="utf-8"
        )
        plugins = load_plugins(plugins_dir=tmp_path)
        assert [s.name for s in plugins[0].skills] == ["helper"]

    def test_plugin_without_manifest_falls_back_to_dir_name(self, tmp_path: Path) -> None:
        _make_skill(tmp_path / "bare" / "skills", "s1", "desc")
        plugins = load_plugins(plugins_dir=tmp_path)
        assert plugins[0].name == "bare"
        assert plugins[0].description == ""

    def test_empty_plugins_dir(self, tmp_path: Path) -> None:
        assert load_plugins(plugins_dir=tmp_path / "missing") == []


class TestPluginSkillsAreActive:
    """Installed plugins are used by the running harness, not just listed."""

    def test_harness_registers_namespaced_and_plain_names(
        self, origin: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("OM_HARNESS_PLUGINS_DIR", str(tmp_path / "plugins"))
        install_plugin(str(origin))

        repo = tmp_path / "repo"
        repo.mkdir()
        harness = Harness(repo_root=repo, env={})
        # Namespaced name always present; plain name present when unique.
        assert "superpowers:brainstorm" in harness.skills
        assert "brainstorm" in harness.skills
        assert harness.registry.has("skill")
        assert "superpowers:brainstorm" in harness.assembler.system_prompt("chat")
        assert harness.status()["skills"] == ["brainstorm", "superpowers:brainstorm"]

    def test_user_skill_wins_plain_name_over_plugin(
        self, origin: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("OM_HARNESS_PLUGINS_DIR", str(tmp_path / "plugins"))
        install_plugin(str(origin))
        user_dir = tmp_path / "user-skills"
        _make_skill(user_dir, "brainstorm", "user version")
        monkeypatch.setenv("OM_HARNESS_SKILLS_DIR", str(user_dir))

        repo = tmp_path / "repo"
        repo.mkdir()
        harness = Harness(repo_root=repo, env={})
        assert harness.skills["brainstorm"].description == "user version"
        assert harness.skills["superpowers:brainstorm"].description == "refine rough ideas"


async def test_agent_turn_loads_plugin_skill_via_tool(
    origin: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End-to-end: an agent turn invokes the `skill` tool for a plugin skill."""
    from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart
    from pydantic_ai.models.function import FunctionModel

    from om_harness.models.events import EventType
    from om_harness.models.task import Task, TaskStatus
    from om_harness.providers.registry import ProviderRegistry
    from om_harness.providers.router import ModelRouter
    from om_harness.runtime.bus import EventBus
    from om_harness.runtime.runner import AgentRunner
    from om_harness.tools.approval import ApprovalEngine
    from om_harness.tools.registry import GuardedToolExecutor

    monkeypatch.setenv("OM_HARNESS_PLUGINS_DIR", str(tmp_path / "plugins"))
    # The plugin skill body carries a unique marker the scripted model echoes.
    _make_skill(
        origin / "skills",
        "marker-skill",
        "has a marker",
        body="MARKER-ZEBRA-9137: follow this exact instruction.",
    )
    subprocess.run(["git", "add", "."], cwd=origin, check=True, capture_output=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "marker"],
        cwd=origin,
        check=True,
        capture_output=True,
    )
    install_plugin(str(origin))

    repo = tmp_path / "repo"
    repo.mkdir()
    harness = Harness(repo_root=repo, env={})
    assert "demo:marker-skill" not in harness.skills  # sanity: fresh origin name
    skill_name = "superpowers:marker-skill"
    assert skill_name in harness.skills

    async def respond(messages, agent_info):  # type: ignore[no-untyped-def]
        saw_tool_result = any(
            getattr(part, "part_kind", "") == "tool-return"
            for m in messages
            for part in getattr(m, "parts", [])
        )
        if not saw_tool_result:
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_name="skill",
                        args={"skill": skill_name},
                        tool_call_id="c1",
                    )
                ]
            )
        # Echo the skill body the tool returned, proving it reached the model.
        returned = [
            part.content
            for m in messages
            for part in getattr(m, "parts", [])
            if getattr(part, "part_kind", "") == "tool-return"
        ]
        return ModelResponse(parts=[TextPart(content=" ".join(returned))])

    bus = EventBus()
    runner = AgentRunner(
        executor=GuardedToolExecutor(
            registry=harness.registry,
            approval=ApprovalEngine(harness.config.approval, interactive=False),
            bus=bus,
        ),
        assembler=harness.assembler,
        router=ModelRouter(harness.config.routing, ProviderRegistry(env={})),
        provider_registry=ProviderRegistry(env={}),
        config=harness.config,
        bus=bus,
        model_factory=lambda _model_str: FunctionModel(respond),
    )
    task = Task(id="t1", title="use skill", instruction="follow the plugin skill")
    result = await runner.run_task(task)

    assert result.status == TaskStatus.completed
    assert "MARKER-ZEBRA-9137" in result.summary
    types = [e.type for e in bus.history]
    assert EventType.TOOL_CALL_COMPLETED in types
    # The system prompt the agent received listed the plugin skill.
    assert skill_name in harness.assembler.system_prompt("implementer")
