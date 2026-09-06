"""Skill tool: load a discovered skill's full instructions on demand.

The system prompt only lists skill names and descriptions; this read-only
tool fetches the SKILL.md body when the agent (or a /skill command) needs
it. Paths come exclusively from the discovery registry, so the repo-root
confinement rule is not bypassable: there is no user-supplied path argument.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, Field

from om_harness.skills import Skill, load_skill_body, render_skill_list
from om_harness.tools.base import BaseTool, Permission, ToolResult


class SkillTool(BaseTool["SkillTool.Args"]):
    name = "skill"
    description = (
        "Load the full instructions of a named skill (from the available-skills "
        "list) and follow them. Use before attempting a task covered by a skill."
    )
    permission = Permission.read_only

    class Args(BaseModel):
        skill: str = Field(description="Name of the skill to load")
        args: str = Field(
            default="",
            description="Optional arguments or context for the skill",
        )

    def __init__(self, ctx: Any, *, skills: Mapping[str, Skill]) -> None:
        super().__init__(ctx)
        self.skills = dict(skills)

    async def run(self, args: SkillTool.Args) -> ToolResult:
        skill = self.skills.get(args.skill)
        if skill is None:
            available = render_skill_list(self.skills) or "(none available)"
            return ToolResult.fail(f"unknown skill {args.skill!r}. Available skills:\n{available}")
        body = load_skill_body(skill)
        header = f"Skill: {skill.name}"
        if args.args:
            header += f"\nArguments: {args.args}"
        return ToolResult(
            ok=True,
            output=f"{header}\n\nFollow these instructions:\n\n{body}",
            data={"skill": skill.name, "source": skill.source},
        )
