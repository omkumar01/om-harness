"""Skill discovery: SKILL.md frontmatter parsing, directory scan, body loading."""

from __future__ import annotations

from pathlib import Path

from om_harness.skills import discover_skills, load_skill_body, parse_skill_md


def _make_skill(root: Path, name: str, text: str) -> Path:
    skill_dir = root / name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(text, encoding="utf-8")
    return skill_dir


SKILL_TEXT = """\
---
name: analyse
description: Picks the best analysis method for a target
argument-hint: target description
---

# Smart Analysis

Step-by-step instructions here.
"""


class TestParseSkillMd:
    def test_parses_frontmatter_fields(self, tmp_path: Path) -> None:
        skill_dir = _make_skill(tmp_path, "analyse", SKILL_TEXT)
        skill = parse_skill_md(skill_dir / "SKILL.md", source="user")
        assert skill is not None
        assert skill.name == "analyse"
        assert skill.description == "Picks the best analysis method for a target"
        assert skill.argument_hint == "target description"
        assert skill.source == "user"
        assert skill.path == skill_dir / "SKILL.md"

    def test_name_defaults_to_directory_name(self, tmp_path: Path) -> None:
        skill_dir = _make_skill(
            tmp_path,
            "dir-name",
            "---\ndescription: no explicit name\n---\nbody",
        )
        skill = parse_skill_md(skill_dir / "SKILL.md")
        assert skill is not None
        assert skill.name == "dir-name"

    def test_argument_hint_defaults_to_none(self, tmp_path: Path) -> None:
        skill_dir = _make_skill(tmp_path, "s", "---\ndescription: d\n---\nbody")
        skill = parse_skill_md(skill_dir / "SKILL.md")
        assert skill is not None
        assert skill.argument_hint is None

    def test_missing_description_is_skipped(self, tmp_path: Path) -> None:
        skill_dir = _make_skill(tmp_path, "s", "---\nname: s\n---\nbody")
        assert parse_skill_md(skill_dir / "SKILL.md") is None

    def test_no_frontmatter_is_skipped(self, tmp_path: Path) -> None:
        skill_dir = _make_skill(tmp_path, "s", "# just markdown, no frontmatter")
        assert parse_skill_md(skill_dir / "SKILL.md") is None

    def test_missing_file_is_skipped(self, tmp_path: Path) -> None:
        assert parse_skill_md(tmp_path / "nope" / "SKILL.md") is None


class TestDiscoverSkills:
    def test_discovers_skill_md_in_subdirectories(self, tmp_path: Path) -> None:
        _make_skill(tmp_path, "analyse", SKILL_TEXT)
        _make_skill(tmp_path, "brainstorm", "---\ndescription: refine ideas\n---\nbody")
        skills = discover_skills([(tmp_path, "user")])
        assert set(skills) == {"analyse", "brainstorm"}
        assert skills["analyse"].source == "user"

    def test_ignores_plain_files_and_missing_dirs(self, tmp_path: Path) -> None:
        (tmp_path / "not-a-dir").write_text("x", encoding="utf-8")
        skills = discover_skills([(tmp_path, "user"), (tmp_path / "missing", "repo")])
        assert skills == {}

    def test_later_sources_override_earlier(self, tmp_path: Path) -> None:
        user_dir = tmp_path / "user-skills"
        repo_dir = tmp_path / "repo-skills"
        _make_skill(user_dir, "shared", "---\ndescription: user version\n---\nuser")
        _make_skill(user_dir, "only-user", "---\ndescription: only in user\n---\nuser")
        _make_skill(repo_dir, "shared", "---\ndescription: repo version\n---\nrepo")
        skills = discover_skills([(user_dir, "user"), (repo_dir, "repo")])
        assert skills["shared"].description == "repo version"
        assert skills["shared"].source == "repo"
        assert set(skills) == {"shared", "only-user"}

    def test_malformed_entries_are_skipped(self, tmp_path: Path) -> None:
        _make_skill(tmp_path, "good", "---\ndescription: fine\n---\nbody")
        _make_skill(tmp_path, "bad", "# no frontmatter")
        skills = discover_skills([(tmp_path, "user")])
        assert set(skills) == {"good"}


class TestLoadSkillBody:
    def test_strips_frontmatter(self, tmp_path: Path) -> None:
        skill_dir = _make_skill(tmp_path, "analyse", SKILL_TEXT)
        skill = parse_skill_md(skill_dir / "SKILL.md")
        assert skill is not None
        body = load_skill_body(skill)
        assert "# Smart Analysis" in body
        assert "description:" not in body
        assert "---" not in body.split("# Smart Analysis")[0]

    def test_body_matches_recorded_size(self, tmp_path: Path) -> None:
        skill_dir = _make_skill(tmp_path, "analyse", SKILL_TEXT)
        skill = parse_skill_md(skill_dir / "SKILL.md")
        assert skill is not None
        assert len(load_skill_body(skill)) == skill.body_chars
