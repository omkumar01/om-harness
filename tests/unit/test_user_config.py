"""Contract tests for config precedence (defaults < user < repo < env) and
cross-source models.json merging."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from om_harness.config.loader import load_config
from om_harness.config.paths import user_models_json
from om_harness.providers.models_json import load_models_json

# -- config precedence --------------------------------------------------------


def test_user_config_file_loaded(tmp_path: Any, home: Any) -> None:
    (home / "config").mkdir(parents=True, exist_ok=True)
    (home / "config" / "config.toml").write_text(
        '[routing]\ndefault_model = "openai:gpt-4.1"\n',
        encoding="utf-8",
    )
    config = load_config(tmp_path)
    assert config.routing.default_model == "openai:gpt-4.1"


def test_repo_config_overrides_user_config(tmp_path: Any, home: Any) -> None:
    (home / "config").mkdir(parents=True, exist_ok=True)
    (home / "config" / "config.toml").write_text(
        'max_concurrency = 2\n[routing]\ndefault_model = "openai:gpt-4.1"\n',
        encoding="utf-8",
    )
    (tmp_path / "om-harness.toml").write_text(
        '[routing]\ndefault_model = "openai:gpt-4o"\n',
        encoding="utf-8",
    )
    config = load_config(tmp_path)
    assert config.routing.default_model == "openai:gpt-4o"  # repo wins
    assert config.max_concurrency == 2  # user value survives


def test_env_overrides_both_levels(tmp_path: Any, home: Any, monkeypatch: Any) -> None:
    (home / "config").mkdir(parents=True, exist_ok=True)
    (home / "config" / "config.toml").write_text(
        '[routing]\ndefault_model = "openai:gpt-4.1"\n', encoding="utf-8"
    )
    (tmp_path / "om-harness.toml").write_text(
        '[routing]\ndefault_model = "openai:gpt-4o"\n', encoding="utf-8"
    )
    monkeypatch.setenv("OM_HARNESS_DEFAULT_MODEL", "openai:gpt-4o-mini")
    config = load_config(tmp_path)
    assert config.routing.default_model == "openai:gpt-4o-mini"


def test_nested_table_merge(tmp_path: Any, home: Any) -> None:
    (home / "config").mkdir(parents=True, exist_ok=True)
    (home / "config" / "config.toml").write_text(
        '[routing.task_models]\nexplore = "openai:gpt-4o-mini"\n', encoding="utf-8"
    )
    (tmp_path / "om-harness.toml").write_text(
        '[routing.task_models]\nimplement = "anthropic:claude-sonnet-4-5"\n',
        encoding="utf-8",
    )
    config = load_config(tmp_path)
    assert config.routing.task_models["explore"] == "openai:gpt-4o-mini"
    assert config.routing.task_models["implement"] == "anthropic:claude-sonnet-4-5"


# -- models.json cross-source merge -------------------------------------------


def _write_models_json(path: Path, providers: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"providers": providers}), encoding="utf-8")


def _remote_provider(api_key_env: str = "R_KEY") -> dict[str, Any]:
    return {
        "baseUrl": "https://api.example.com/v1",
        "api": "openai-completions",
        "apiKeyEnv": api_key_env,
        "models": [{"id": "m1"}],
    }


def test_global_and_repo_models_json_merge(tmp_path: Any, home: Any) -> None:
    _write_models_json(
        user_models_json(),
        {"globalprov": _remote_provider(), "shared": _remote_provider()},
    )
    _write_models_json(
        tmp_path / "models.json",
        {"repoprov": _remote_provider(), "shared": _remote_provider("OTHER_KEY")},
    )
    config = load_models_json(tmp_path, env={})
    assert config is not None
    assert set(config.providers) == {"globalprov", "repoprov", "shared"}
    # Repo-level definition overrides the global one for the same name.
    assert config.providers["shared"].api_key_env == "OTHER_KEY"


def test_env_models_json_wins_as_source(tmp_path: Any, home: Any) -> None:
    _write_models_json(user_models_json(), {"globalprov": _remote_provider()})
    env_file = tmp_path / "elsewhere.json"
    _write_models_json(env_file, {"envprov": _remote_provider()})
    config = load_models_json(tmp_path, env={"OM_HARNESS_MODELS_JSON": str(env_file)})
    assert config is not None
    # Env-referenced file is merged in addition to the global one.
    assert set(config.providers) == {"globalprov", "envprov"}


def test_repo_models_json_only(tmp_path: Any, home: Any) -> None:
    _write_models_json(tmp_path / "models.json", {"repoprov": _remote_provider()})
    config = load_models_json(tmp_path, env={})
    assert config is not None
    assert set(config.providers) == {"repoprov"}
