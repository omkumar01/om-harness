"""User-level storage layout under ``~/.om-harness`` (config + caches).

Layout::

    ~/.om-harness/
    ├── config/
    │   ├── config.toml     # user-level harness configuration
    │   └── models.json     # user-level custom providers
    └── cache/
        └── repo-index/     # persisted repository index caches

Sessions/checkpoints stay repository-local (``<repo>/.om-harness/``) by
design. ``OM_HARNESS_HOME`` overrides the root (used by tests).
"""

from __future__ import annotations

import os
from pathlib import Path

HOME_ENV_VAR = "OM_HARNESS_HOME"


def user_home() -> Path:
    """The om-harness user root: $OM_HARNESS_HOME or ~/.om-harness."""
    override = os.environ.get(HOME_ENV_VAR)
    if override:
        return Path(override).expanduser()
    return Path.home() / ".om-harness"


def user_config_dir() -> Path:
    return user_home() / "config"


def user_models_json() -> Path:
    return user_config_dir() / "models.json"


def user_config_file() -> Path:
    return user_config_dir() / "config.toml"


def user_cache_dir() -> Path:
    return user_home() / "cache"


def ensure_user_dirs() -> bool:
    """Create the user directory layout; returns True on the first run."""
    first_run = not user_config_dir().exists()
    user_config_dir().mkdir(parents=True, exist_ok=True)
    user_cache_dir().mkdir(parents=True, exist_ok=True)
    return first_run
