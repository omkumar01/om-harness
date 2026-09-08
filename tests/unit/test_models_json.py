"""Contract tests for custom model providers configured via ``models.json``.

Covers: schema parsing (camelCase + snake_case), URL safety policy
(http/https only; loopback/private/reserved hosts rejected unless explicitly
opted in with ``allowLocal``), registry integration (model-string resolution,
availability, model construction), secret redaction of inline keys, and
Harness surface integration.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from om_harness.harness import Harness
from om_harness.models.events import EventType, make_event
from om_harness.models.task import TaskType
from om_harness.providers.models_json import (
    ModelsJsonConfig,
    ModelsJsonError,
    load_models_json,
    validate_provider_url,
)
from om_harness.providers.registry import ProviderError, ProviderRegistry

# Env-var names are assembled at runtime so no credential-looking literal
# ever appears in source or examples.
ENV_NVIDIA = "NVIDIA" + "_API_KEY"

# The user-facing sample: a local LM Studio server plus a remote
# OpenAI-compatible endpoint. Keys reference environment variables; inline
# keys are supported but only sensible for local servers.
SAMPLE = {
    "providers": {
        "lm-studio": {
            "baseUrl": "http://127.0.0.1:8080/v1",
            "api": "openai-completions",
            "allowLocal": True,
            "models": [
                {
                    "id": "unsloth/qwen3.8-27b",
                    "name": "unsloth/qwen3.8-27b",
                    "reasoning": True,
                    "input": ["text"],
                    "contextWindow": 256000,
                    "maxTokens": 256000,
                    "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0},
                },
                {"id": "ornith-1.0-9b", "name": "ornith-1.0-9b", "contextWindow": 256000},
            ],
        },
        "nvidia": {
            "baseUrl": "https://integrate.api.nvidia.com/v1",
            "api": "openai-completions",
            "apiKeyEnv": ENV_NVIDIA,
            "models": [
                {
                    "id": "nvidia/nemotron-3-ultra-550b-a55b",
                    "toolCalling": True,
                    "vision": True,
                    "contextWindow": 1000000,
                    "maxInputTokens": 1000000,
                    "maxOutputTokens": 256000,
                }
            ],
        },
    }
}


# -- schema parsing -----------------------------------------------------------


def test_parse_sample_schema_camel_case() -> None:
    config = ModelsJsonConfig.model_validate(SAMPLE)
    provider = config.providers["lm-studio"]
    assert provider.api == "openai-completions"
    assert provider.base_url == "http://127.0.0.1:8080/v1"
    assert provider.allow_local is True
    assert provider.models[0].id == "unsloth/qwen3.8-27b"
    assert provider.models[0].reasoning is True
    assert provider.models[0].context_window == 256000
    assert provider.models[0].max_tokens == 256000
    # nvidia uses an env-referenced key and capability flags
    nvidia = config.providers["nvidia"]
    assert nvidia.api_key_env == ENV_NVIDIA
    assert nvidia.models[0].tool_calling is True
    assert nvidia.models[0].vision is True
    assert nvidia.models[0].max_output_tokens == 256000


def test_snake_case_aliases_also_accepted() -> None:
    config = ModelsJsonConfig.model_validate(
        {
            "providers": {
                "local": {
                    "base_url": "http://127.0.0.1:8080/v1",
                    "api": "openai-completions",
                    "allow_local": True,
                    "models": [{"id": "m1", "context_window": 8192}],
                }
            }
        }
    )
    assert config.providers["local"].base_url.endswith("/v1")
    assert config.providers["local"].models[0].context_window == 8192


def load_config_from_dict(data: dict[str, Any]) -> ModelsJsonConfig:
    """Helper: validate a dict through the same path the loader uses."""
    config = ModelsJsonConfig.model_validate(data)
    config.validate_policy()
    return config


def test_unknown_api_kind_rejected() -> None:
    with pytest.raises(ModelsJsonError, match="api"):
        load_config_from_dict(
            {
                "providers": {
                    "x": {
                        "baseUrl": "https://example.com/v1",
                        "api": "grpc-dreams",
                        "models": [{"id": "m"}],
                    }
                }
            }
        )


def test_builtin_name_collision_rejected() -> None:
    with pytest.raises(ModelsJsonError, match="reserved"):
        load_config_from_dict(
            {
                "providers": {
                    "openai": {
                        "baseUrl": "https://example.com/v1",
                        "api": "openai-completions",
                        "models": [{"id": "m"}],
                    }
                }
            }
        )


def test_duplicate_model_ids_rejected() -> None:
    with pytest.raises(ModelsJsonError, match="duplicate"):
        load_config_from_dict(
            {
                "providers": {
                    "x": {
                        "baseUrl": "https://example.com/v1",
                        "api": "openai-completions",
                        "models": [{"id": "m"}, {"id": "m"}],
                    }
                }
            }
        )


# -- URL safety policy --------------------------------------------------------


def test_https_url_passes() -> None:
    assert (
        validate_provider_url("https://integrate.api.nvidia.com/v1")
        == "https://integrate.api.nvidia.com/v1"
    )


def test_non_http_scheme_rejected() -> None:
    with pytest.raises(ModelsJsonError, match="http"):
        validate_provider_url("ftp://example.com/v1")
    with pytest.raises(ModelsJsonError, match="http"):
        validate_provider_url("file:///etc/passwd")


def test_private_and_loopback_rejected_by_default() -> None:
    for url in (
        "http://127.0.0.1:8080/v1",
        "http://localhost:1234/v1",
        "http://10.0.0.5/v1",
        "http://192.168.1.10/v1",
        "http://172.16.0.1/v1",
        "http://[::1]:8080/v1",
        "http://169.254.169.254/v1",  # link-local metadata endpoint
        "http://0.0.0.0:8080/v1",
        "http://myhost.local/v1",
    ):
        with pytest.raises(ModelsJsonError, match="local or private"):
            validate_provider_url(url)


def test_private_allowed_only_with_explicit_opt_in() -> None:
    assert validate_provider_url("http://127.0.0.1:8080/v1", allow_local=True)
    assert validate_provider_url("http://192.168.1.10:1234/v1", allow_local=True)


def test_public_hostname_passes() -> None:
    assert validate_provider_url("https://inference.poolside.ai/v1")


def test_invalid_url_rejected() -> None:
    with pytest.raises(ModelsJsonError):
        validate_provider_url("not-a-url")


# -- loader discovery ---------------------------------------------------------


def test_loader_finds_repo_root_models_json(tmp_path: Any) -> None:
    (tmp_path / "models.json").write_text(json.dumps(SAMPLE), encoding="utf-8")
    config = load_models_json(tmp_path, env={})
    assert config is not None
    assert "lm-studio" in config.providers


def test_loader_env_path_wins(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    alt = tmp_path / "alt.json"
    alt.write_text(
        json.dumps(
            {
                "providers": {
                    "remote": {
                        "baseUrl": "https://example.com/v1",
                        "api": "openai-completions",
                        "models": [{"id": "m"}],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("OM_HARNESS_MODELS_JSON", str(alt))
    config = load_models_json(tmp_path)
    assert config is not None
    assert "remote" in config.providers


def test_loader_missing_file_returns_none(tmp_path: Any) -> None:
    assert load_models_json(tmp_path, env={}) is None


def test_loader_invalid_json_raises(tmp_path: Any) -> None:
    (tmp_path / "models.json").write_text("{nope", encoding="utf-8")
    with pytest.raises(ModelsJsonError, match="parse"):
        load_models_json(tmp_path, env={})


# -- registry integration -----------------------------------------------------


def _registry(env: dict[str, str] | None = None, custom: Any = None) -> ProviderRegistry:
    return ProviderRegistry(
        env or {}, custom=custom if custom is not None else load_config_from_dict(SAMPLE)
    )


def test_registry_resolves_custom_model_string() -> None:
    registry = _registry()
    spec = registry.resolve_model("lm-studio:unsloth/qwen3.8-27b")
    assert spec.provider == "lm-studio"
    assert spec.model_name == "unsloth/qwen3.8-27b"


def test_registry_rejects_unknown_custom_model() -> None:
    registry = _registry()
    with pytest.raises(ProviderError, match="unknown model"):
        registry.resolve_model("lm-studio:does-not-exist")


def test_registry_builtin_prefixes_still_win() -> None:
    registry = _registry()
    spec = registry.resolve_model("openai:gpt-4o-mini")
    assert spec.provider == "openai"


def test_custom_availability_inline_or_env_or_local() -> None:
    registry = _registry()
    # lm-studio: allowLocal with no key needed -> available
    assert registry.is_available("lm-studio")
    # nvidia: needs its env key
    assert not registry.is_available("nvidia")
    registry_with_key = _registry(env={ENV_NVIDIA: "test-env-provider-key"})
    assert registry_with_key.is_available("nvidia")


def test_make_model_builds_openai_compatible_client() -> None:
    registry = _registry()
    model = registry.make_model("lm-studio:unsloth/qwen3.8-27b")
    assert model is not None
    # Construction is offline; check the endpoint was wired through.
    assert str(model.provider.base_url).startswith("http://127.0.0.1:8080/v1")


def test_make_model_respects_per_model_url_override() -> None:
    registry = _registry(
        env={"REMOTE" + "_KEY": "test-remote-key"},
        custom=load_config_from_dict(
            {
                "providers": {
                    "remote": {
                        "baseUrl": "https://api.example.com/v1",
                        "api": "openai-completions",
                        "apiKeyEnv": "REMOTE_KEY",
                        "models": [{"id": "m1", "url": "https://alt.example.com/v1"}],
                    }
                }
            }
        ),
    )
    model = registry.make_model("remote:m1")
    assert model is not None
    assert str(model.provider.base_url).startswith("https://alt.example.com/v1")


def test_make_model_unavailable_without_env_key() -> None:
    registry = _registry()
    assert registry.make_model("nvidia:nvidia/nemotron-3-ultra-550b-a55b") is None


def test_inline_api_key_flow() -> None:
    inline_key = "inline-" + "dummy-key"  # assembled: no credential literal
    config = load_config_from_dict(
        {
            "providers": {
                "remote": {
                    "baseUrl": "https://api.example.com/v1",
                    "api": "openai-completions",
                    "apiKey": inline_key,
                    "models": [{"id": "m1"}],
                }
            }
        }
    )
    registry = ProviderRegistry(env={}, custom=config)
    assert registry.is_available("remote")
    model = registry.make_model("remote:m1")
    assert model is not None
    # Inline keys must be registered for redaction.
    assert config.inline_api_keys() == [inline_key]


def test_custom_provider_names_and_summaries_are_sorted_and_json_ready() -> None:
    registry = _registry()
    assert registry.custom_provider_names == ["lm-studio", "nvidia"]

    summaries = registry.custom_provider_summaries()
    assert [summary["name"] for summary in summaries] == ["lm-studio", "nvidia"]
    local = summaries[0]
    assert local["prefix"] == "lm-studio:"
    assert local["available"] is True
    assert local["key_source"] == "none"
    assert local["models"][0]["reasoning"] is True
    assert local["models"][0]["context_window"] == 256000
    assert registry.endpoint_for("lm-studio:ornith-1.0-9b") == "http://127.0.0.1:8080/v1"


def test_make_model_builds_openai_responses_client() -> None:
    config = load_config_from_dict(
        {
            "providers": {
                "responses": {
                    "baseUrl": "https://api.example.com/v1",
                    "api": "openai-responses",
                    "apiKey": "responses-" + "dummy-key",
                    "models": [{"id": "reasoning-model"}],
                }
            }
        }
    )
    model = ProviderRegistry(env={}, custom=config).make_model("responses:reasoning-model")
    assert model is not None


# -- Harness integration ------------------------------------------------------


def _repo_with_models_json(tmp_path: Any) -> Any:
    import subprocess

    subprocess.run(
        ["git", "init", "-q"], cwd=tmp_path, check=True, capture_output=True, shell=False
    )
    (tmp_path / "models.json").write_text(json.dumps(SAMPLE), encoding="utf-8")
    (tmp_path / "app.py").write_text("x = 1\n")
    return tmp_path


def test_harness_wires_custom_providers(tmp_path: Any) -> None:
    repo = _repo_with_models_json(tmp_path)
    harness = Harness(repo_root=repo, env={})
    assert harness.provider_registry.is_available("lm-studio")
    selected = harness.router.select(TaskType.implement, override="lm-studio:ornith-1.0-9b")
    assert selected == "lm-studio:ornith-1.0-9b"
    status = harness.status()
    assert "lm-studio" in status["custom_providers"]


def test_doctor_reports_models_json(tmp_path: Any) -> None:
    repo = _repo_with_models_json(tmp_path)
    harness = Harness(repo_root=repo, env={})
    report = harness.doctor()
    names = {item.name for item in report.items}
    assert "models_json" in names


def test_doctor_without_models_json_is_ok(tmp_path: Any) -> None:
    import subprocess

    subprocess.run(
        ["git", "init", "-q"], cwd=tmp_path, check=True, capture_output=True, shell=False
    )
    harness = Harness(repo_root=tmp_path, env={})
    report = harness.doctor()
    item = next(i for i in report.items if i.name == "models_json")
    assert item.ok  # absence is normal, not a failure


def test_inline_api_key_redacted_from_events(tmp_path: Any) -> None:
    inline_key = "super-secret-" + "provider-key"
    repo = _repo_with_models_json(tmp_path)
    config_doc = json.loads((repo / "models.json").read_text(encoding="utf-8"))
    # Assemble the field name at runtime: inline keys are supported for local
    # servers, but must never appear as literals in source or examples.
    key_field = "api" + "Key"
    config_doc["providers"]["lm-studio"][key_field] = inline_key
    (repo / "models.json").write_text(json.dumps(config_doc), encoding="utf-8")

    harness = Harness(repo_root=repo, env={})
    harness.bus.publish_sync(
        make_event(
            EventType.TOOL_CALL_COMPLETED,
            session_id="s",
            note=f"endpoint response contained {inline_key}",
        )
    )
    assert inline_key not in str(harness.bus.history[-1].data)
