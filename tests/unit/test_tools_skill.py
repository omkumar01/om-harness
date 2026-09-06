"""Contract tests for the skill tool: on-demand SKILL.md loading."""

from __future__ import annotations

from pathlib import Path

import pytest

from om_harness.skills import discover_skills
from om_harness.tools.base import Permission, ToolContext
from om_harness.tools.skill import SkillTool


@pytest.fixture
def skills_dir(tmp_path: Path) -> Path:
    d = tmp_path / "skills"
    (d / "analyse").mkdir(parents=True)
    (d / "analyse" / "SKILL.md").write_text(
        "---\nname: analyse\ndescription: pick a method\n---\n\n# Smart Analysis\nDo the thing.\n",
        encoding="utf-8",
    )
    (d / "brainstorm").mkdir()
    (d / "brainstorm" / "SKILL.md").write_text(
        "---\ndescription: refine ideas\n---\n\n# Brainstorm\nAsk questions.\n",
        encoding="utf-8",
    )
    return d


@pytest.fixture
def tool(tmp_path: Path, skills_dir: Path) -> SkillTool:
    skills = discover_skills([(skills_dir, "user")])
    return SkillTool(ToolContext(repo_root=tmp_path), skills=skills)


async def test_permission_is_read_only(tool: SkillTool) -> None:
    assert tool.permission == Permission.read_only


async def test_loads_known_skill_body(tool: SkillTool) -> None:
    result = await tool.run(SkillTool.Args(skill="analyse"))
    assert result.ok
    assert "# Smart Analysis" in result.output
    assert "description:" not in result.output


async def test_unknown_skill_lists_available(tool: SkillTool) -> None:
    result = await tool.run(SkillTool.Args(skill="nope"))
    assert not result.ok
    assert "nope" in (result.error or "")
    assert "analyse" in (result.error or "")
    assert "brainstorm" in (result.error or "")


async def test_args_field_is_included_in_output(tool: SkillTool) -> None:
    result = await tool.run(SkillTool.Args(skill="analyse", args="auth flow"))
    assert result.ok
    assert "auth flow" in result.output


async def test_empty_registry_fails_gracefully(tmp_path: Path) -> None:
    tool = SkillTool(ToolContext(repo_root=tmp_path), skills={})
    result = await tool.run(SkillTool.Args(skill="anything"))
    assert not result.ok
