"""Skill discovery: SKILL.md files parsed into small, loadable units.

A skill is a directory containing ``SKILL.md`` with a tiny YAML-ish
frontmatter (``name``, ``description``, optional ``argument-hint``) followed
by markdown instructions. Discovery is cheap (frontmatter only); the body is
loaded on demand by the ``skill`` tool, keeping context small by default.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from pydantic import BaseModel


class Skill(BaseModel):
    """One discovered skill: identifying frontmatter plus its SKILL.md path."""

    name: str
    description: str
    path: Path
    source: str = ""
    argument_hint: str | None = None
    # Body characters, recorded at discovery so UIs can show size without
    # re-reading the file.
    body_chars: int = 0


def _split_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Split leading ``---`` frontmatter into key/value pairs plus the body."""
    if not text.startswith("---"):
        return {}, text
    lines = text.splitlines()
    meta: dict[str, str] = {}
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            body = "\n".join(lines[index + 1 :]).lstrip("\n")
            return meta, body
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        meta[key.strip()] = value.strip()
    return {}, text


def parse_skill_md(path: Path, source: str = "") -> Skill | None:
    """Parse one SKILL.md; returns None for missing files or bad frontmatter."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    meta, body = _split_frontmatter(text)
    description = meta.get("description", "").strip()
    if not description:
        return None
    name = meta.get("name", "").strip() or path.parent.name
    hint = meta.get("argument-hint", "").strip() or None
    return Skill(
        name=name,
        description=description,
        path=path,
        source=source,
        argument_hint=hint,
        body_chars=len(body),
    )


def load_skill_body(skill: Skill) -> str:
    """Read the skill's instructions: everything after the frontmatter."""
    try:
        text = skill.path.read_text(encoding="utf-8")
    except OSError as exc:
        return f"error: could not read skill {skill.name!r}: {exc}"
    _, body = _split_frontmatter(text)
    return body


def discover_skills(sources: Sequence[tuple[Path, str]]) -> dict[str, Skill]:
    """Scan ``(dir, source_label)`` pairs in order; later sources win on name.

    Only immediate subdirectories containing a ``SKILL.md`` are considered;
    malformed or missing entries are skipped so one bad skill never breaks
    discovery.
    """
    skills: dict[str, Skill] = {}
    for directory, source in sources:
        if not directory.is_dir():
            continue
        for entry in sorted(directory.iterdir()):
            if not entry.is_dir():
                continue
            skill = parse_skill_md(entry / "SKILL.md", source=source)
            if skill is not None:
                skills[skill.name] = skill
    return skills


def render_skill_list(skills: dict[str, Skill]) -> str:
    """Compact prompt-ready listing: one line per skill."""
    lines = []
    for skill in skills.values():
        hint = f" (args: {skill.argument_hint})" if skill.argument_hint else ""
        lines.append(f"- {skill.name}{hint}: {skill.description}")
    return "\n".join(lines)


__all__ = [
    "Skill",
    "discover_skills",
    "load_skill_body",
    "parse_skill_md",
    "render_skill_list",
]
