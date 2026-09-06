"""Git-installable plugins that contribute skills to every harness session.

A plugin is a git repository cloned under ``~/.om-harness/plugins/<name>``.
It may carry an optional ``plugin.json`` manifest (``name``, ``description``)
and skills in the conventional ``skills/*/SKILL.md`` or
``.agents/skills/*/SKILL.md`` layouts. Installation records provenance in
``.om-harness-plugin.json`` so ``om-harness plugins`` can show where a
plugin came from and update it later.
"""

from __future__ import annotations

import contextlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from om_harness.config.paths import user_plugins_dir
from om_harness.skills import Skill, discover_skills

PROVENANCE_FILENAME = ".om-harness-plugin.json"
MANIFEST_FILENAME = "plugin.json"


class PluginError(Exception):
    """Raised for bad plugin sources, missing git, or failed installs."""


class Plugin(BaseModel):
    name: str
    path: Path
    description: str = ""
    source: str = ""
    skills: list[Skill] = Field(default_factory=list)


def parse_source(spec: str) -> tuple[str, str]:
    """Normalize an install spec into ``(clone_url, plugin_name)``.

    Accepted forms: ``git:owner/repo`` and bare ``owner/repo`` (GitHub
    shorthand), ``git:https://host/owner/repo`` and ``git:git@host:owner/repo``
    (used as-is), and local paths (used as-is, e.g. in tests).
    """
    text = spec.strip()
    if text.startswith("git:"):
        text = text[len("git:") :]
    if not text:
        raise PluginError("empty plugin source")
    if "://" in text or text.startswith("git@"):
        return text, _name_from_url(text)
    segments = [s for s in text.replace("\\", "/").split("/") if s]
    if len(segments) == 3 and "." in segments[0]:
        # host/owner/repo shorthand, e.g. github.com/obra/superpowers
        return f"https://{text}", segments[-1]
    if len(segments) == 2 and ":" not in segments[0] and "." not in segments[0]:
        # owner/repo GitHub shorthand
        return f"https://github.com/{text}", segments[-1]
    return text, segments[-1] if segments else text


def _name_from_url(url: str) -> str:
    tail = url.rstrip("/").split(":")[-1].split("/")[-1]
    return tail.removesuffix(".git") or "plugin"


def _run_git(args: list[str], cwd: Path | None = None) -> str:
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=120,
            shell=False,
        )
    except FileNotFoundError as exc:
        raise PluginError("git is required to install plugins but was not found") from exc
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).strip().splitlines()
        raise PluginError(
            f"git {' '.join(args)} failed: {detail[-1] if detail else 'unknown error'}"
        )
    return proc.stdout.strip()


def _write_provenance(path: Path, spec: str, url: str) -> None:
    commit = ""
    with contextlib.suppress(PluginError):
        commit = _run_git(["rev-parse", "HEAD"], cwd=path)
    payload = {"source": spec, "url": url, "commit": commit}
    (path / PROVENANCE_FILENAME).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def install_plugin(spec: str, *, plugins_dir: Path | None = None) -> Plugin:
    """Clone (or update) a plugin and return its loaded form."""
    url, name = parse_source(spec)
    target = (plugins_dir or user_plugins_dir()) / name
    if target.exists():
        _run_git(["pull", "--ff-only"], cwd=target)
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        _run_git(["clone", "--depth", "1", url, str(target)])
    _write_provenance(target, spec, url)
    return load_plugin(target)


def uninstall_plugin(name: str, *, plugins_dir: Path | None = None) -> None:
    """Remove an installed plugin, matched by manifest name or directory name."""
    root = plugins_dir or user_plugins_dir()
    for plugin in load_plugins(plugins_dir=root):
        if name in (plugin.name, plugin.path.name):
            _remove_tree(plugin.path)
            return
    raise PluginError(f"plugin {name!r} is not installed at {root}")


def _remove_tree(path: Path) -> None:
    """rmtree that clears read-only files (git objects are often read-only)."""
    import stat

    for entry in path.rglob("*"):
        with contextlib.suppress(OSError):
            entry.chmod(stat.S_IWRITE)
    shutil.rmtree(path)


def load_plugin(path: Path) -> Plugin:
    """Load one installed plugin: manifest (optional) plus its skills."""
    manifest: dict[str, Any] = {}
    manifest_path = path / MANIFEST_FILENAME
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            manifest = {}
    name = str(manifest.get("name") or path.name)
    description = str(manifest.get("description") or "")
    skills = list(
        discover_skills(
            [
                (path / "skills", f"plugin:{name}"),
                (path / ".agents" / "skills", f"plugin:{name}"),
            ]
        ).values()
    )
    source = ""
    provenance = path / PROVENANCE_FILENAME
    if provenance.exists():
        try:
            source = str(json.loads(provenance.read_text(encoding="utf-8")).get("source") or "")
        except (OSError, json.JSONDecodeError):
            source = ""
    return Plugin(
        name=name,
        path=path,
        description=description,
        source=source,
        skills=skills,
    )


def load_plugins(*, plugins_dir: Path | None = None) -> list[Plugin]:
    """Load every installed plugin, ordered by name for stable merging."""
    root = plugins_dir or user_plugins_dir()
    if not root.is_dir():
        return []
    return [load_plugin(entry) for entry in sorted(root.iterdir()) if entry.is_dir()]


def merge_plugin_skills(base: dict[str, Skill], plugins: list[Plugin]) -> dict[str, Skill]:
    """Fold plugin skills into the registry.

    Every skill is registered under its namespaced ``plugin:skill`` name.
    The plain name is also registered when it is still free, so unique
    plugin skills are addressable directly while user/repo skills keep
    precedence over plugins on collisions.
    """
    merged = dict(base)
    for plugin in plugins:
        for skill in plugin.skills:
            namespaced = skill.model_copy(update={"name": f"{plugin.name}:{skill.name}"})
            merged.setdefault(namespaced.name, namespaced)
            merged.setdefault(skill.name, skill)
    return merged


__all__ = [
    "Plugin",
    "PluginError",
    "install_plugin",
    "load_plugin",
    "load_plugins",
    "merge_plugin_skills",
    "parse_source",
    "uninstall_plugin",
]
