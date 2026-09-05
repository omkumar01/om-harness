"""Contract tests for the interactive-shell building blocks: thinking
settings mapping, cycles, completer, status bar, and provider setup."""

from __future__ import annotations

import json
from typing import Any

import pytest

from om_harness.config.loader import HarnessConfig
from om_harness.config.paths import user_models_json
from om_harness.config.user_settings import SettingsError, add_custom_provider
from om_harness.runtime.runner import thinking_settings
from om_harness.ui.slash import (
    SlashCompleter,
    args_hint_for,
    cycle_approval,
    cycle_thinking,
    cycle_verbosity,
    mode_glyph,
    thinking_glyph,
)

# -- thinking settings mapping ------------------------------------------------


def test_thinking_off_sends_nothing() -> None:
    assert thinking_settings("anthropic", "claude-sonnet-4-5", "off") is None


def test_thinking_anthropic_budget_map() -> None:
    assert thinking_settings("anthropic", "claude-sonnet-4-5", "low") == {
        "thinking": {"type": "enabled", "budget_tokens": 2048}
    }
    assert thinking_settings("anthropic", "x", "high") == {
        "thinking": {"type": "enabled", "budget_tokens": 16384}
    }


def test_thinking_google_thinking_config() -> None:
    settings = thinking_settings("google", "gemini-2.5-pro", "medium")
    assert settings is not None
    config = settings["google_thinking_config"]
    assert config["include_thoughts"] is True
    assert config["thinking_budget"] == 10000


def test_thinking_openai_only_for_reasoning_models() -> None:
    assert thinking_settings("openai", "o3-mini", "high") == {"openai_reasoning_effort": "high"}
    assert thinking_settings("openai", "gpt-4o-mini", "high") is None


def test_thinking_unknown_provider_degrades() -> None:
    assert thinking_settings("mock", "echo", "high") is None
    assert thinking_settings("lm-studio", "qwen3-32b", "high") is None


# -- cycles and glyphs --------------------------------------------------------


def test_cycle_approval() -> None:
    assert cycle_approval("ask") == "auto"
    assert cycle_approval("auto") == "deny"
    assert cycle_approval("deny") == "ask"


def test_cycle_thinking() -> None:
    assert cycle_thinking("off") == "low"
    assert cycle_thinking("high") == "off"


def test_cycle_verbosity() -> None:
    assert cycle_verbosity("compact") == "verbose"
    assert cycle_verbosity("debug") == "compact"


def test_glyphs() -> None:
    assert "auto" in mode_glyph("auto")
    assert "thinking:high" in thinking_glyph("high")


# -- status bar / gauge -------------------------------------------------------


def test_usage_bar_rendering() -> None:
    from om_harness.ui.components import usage_bar

    bar = usage_bar(0, 200_000)
    assert "▯" * 10 in bar and "0/200k" in bar
    bar = usage_bar(100_000, 200_000)
    assert bar.count("▮") == 5
    bar = usage_bar(250_000, 200_000)  # clamped
    assert bar.count("▮") == 10


def test_status_bar_always_shows_provider_model_thinking_mode() -> None:
    from om_harness.ui.components import status_bar

    bar = status_bar("lm-studio", "lm-studio:ornith-1.0-9b", "medium", "⏵⏵ auto", 1000, 200_000)
    assert "provider lm-studio" in bar
    assert "model lm-studio:ornith-1.0-9b" in bar
    assert "thinking medium" in bar
    assert "⏵⏵ auto" in bar
    assert "context" in bar
    assert "alt+M model" in bar  # shortcut hint always visible


def test_header_line_shows_state() -> None:
    from om_harness.ui.components import header_line

    header = header_line("openai", "openai:gpt-4o", "⏵⏵ auto", "◐ thinking:med")
    assert header.startswith("╭─")
    assert header.endswith("╮")
    assert "openai:gpt-4o" in header
    assert "auto" in header
    assert "thinking:med" in header


# -- slash completer ----------------------------------------------------------


class _Doc:
    def __init__(self, text: str) -> None:
        self.text_before_cursor = text


class _Repl:
    harness = HarnessConfig()


def _completions(text: str) -> list[tuple[str, str | None]]:
    completer = SlashCompleter(_Repl())
    return [(c.text, c.display_meta_text) for c in completer.get_completions(_Doc(text), None)]


def test_completer_lists_commands_with_descriptions() -> None:
    completions = _completions("/")
    names = [name for name, _ in completions]
    assert "model" in names and "setup" in names and "thinking" in names
    assert all(meta for _name, meta in completions)


def test_completer_filters_by_prefix() -> None:
    completions = _completions("/con")
    assert [name for name, _ in completions] == ["config"]


def test_completer_arg_completion_for_thinking() -> None:
    completions = _completions("/thinking ")
    values = [name for name, _ in completions]
    assert {"off", "low", "medium", "high"} <= set(values)


def test_completer_config_keys() -> None:
    completions = _completions("/config set ")
    values = [name for name, _ in completions]
    assert "thinking" in values and "task_model.explore" in values


def test_args_hint_for_model() -> None:
    hint = args_hint_for("/model ", ["openai:gpt-4o-mini", "mock:echo"])
    assert hint is not None
    assert "provider:model" in hint


def test_args_hint_ignored_for_plain_text() -> None:
    assert args_hint_for("hello world", []) is None


# -- provider setup -----------------------------------------------------------


def test_add_custom_provider_writes_and_validates(tmp_path: Any, home: Any) -> None:
    message = add_custom_provider(
        name="lm-studio",
        base_url="http://127.0.0.1:8080/v1",
        allow_local=True,
    )
    assert "lm-studio" in message
    config = json.loads(user_models_json().read_text(encoding="utf-8"))
    assert config["providers"]["lm-studio"]["allowLocal"] is True


def test_add_custom_provider_merges_with_existing(tmp_path: Any, home: Any) -> None:
    add_custom_provider(name="a", base_url="https://a.example.com/v1")
    add_custom_provider(name="b", base_url="https://b.example.com/v1")
    config = json.loads(user_models_json().read_text(encoding="utf-8"))
    assert set(config["providers"]) == {"a", "b"}


def test_add_custom_provider_rejects_private_without_optin(tmp_path: Any, home: Any) -> None:
    with pytest.raises(SettingsError, match="local or private"):
        add_custom_provider(name="bad", base_url="http://127.0.0.1:8080/v1")
    assert not user_models_json().exists()


def test_add_custom_provider_rejects_bad_names(tmp_path: Any, home: Any) -> None:
    with pytest.raises(SettingsError, match="invalid provider name"):
        add_custom_provider(name="not a name!", base_url="https://x.example.com/v1")


def test_thinking_persists_via_config_update(tmp_path: Any, home: Any) -> None:
    import subprocess

    subprocess.run(
        ["git", "init", "-q"], cwd=tmp_path, check=True, capture_output=True, shell=False
    )
    from om_harness.config.loader import load_config
    from om_harness.config.user_settings import apply_config_update
    from om_harness.harness import Harness

    harness = Harness(repo_root=tmp_path, env={})
    apply_config_update(harness, "thinking", "high")
    assert harness.config.thinking == "high"
    assert load_config(tmp_path, env={}).thinking == "high"


# -- failure visibility --------------------------------------------------------


def test_failure_events_visible_in_compact_mode() -> None:
    from om_harness.config.loader import Verbosity
    from om_harness.models.events import Event, EventType
    from om_harness.ui.components import event_to_display

    for failure_type in (
        EventType.AGENT_FAILED,
        EventType.TASK_FAILED,
        EventType.TOOL_CALL_FAILED,
    ):
        display = event_to_display(Event(type=failure_type), Verbosity.compact)
        assert display is not None, f"{failure_type} must be visible in compact mode"


def test_unavailable_provider_surfaces_error_in_chat(tmp_path: Any, home: Any) -> None:
    """Selecting a model whose provider is unavailable must produce a clear
    error in the chat reply — never a silent empty response."""
    import asyncio
    import subprocess

    subprocess.run(
        ["git", "init", "-q"], cwd=tmp_path, check=True, capture_output=True, shell=False
    )
    from om_harness.config.user_settings import apply_config_update
    from om_harness.harness import Harness

    harness = Harness(repo_root=tmp_path, env={})
    apply_config_update(harness, "model", "openai:gpt-4o")  # no API key configured
    session = harness.sessions.create(repo_root=str(tmp_path))
    reply = asyncio.run(harness.chat_turn(session.session_id, "hi"))
    assert reply.startswith("error")
    assert "not available" in reply


# -- prompt chrome (hermetic, no TTY needed) ----------------------------------


def _repl_for(tmp_path: Any, home: Any) -> Any:
    import subprocess

    subprocess.run(
        ["git", "init", "-q"], cwd=tmp_path, check=True, capture_output=True, shell=False
    )
    (tmp_path / "app.py").write_text("x = 1\n")
    from om_harness.harness import Harness
    from om_harness.ui.repl import ChatRepl

    harness = Harness(repo_root=tmp_path, env={})
    session = harness.sessions.create(repo_root=str(tmp_path))
    return ChatRepl(harness, session_id=session.session_id)


def test_prompt_message_contains_header_and_input_marker(tmp_path: Any, home: Any) -> None:
    repl = _repl_for(tmp_path, home)
    message = repl._prompt_message()
    assert message.startswith("╭─ om · ")
    assert "\n│ ❯ " in message  # noqa: RUF001 - box glyph is intentional


def test_status_bar_contains_live_state(tmp_path: Any, home: Any) -> None:
    repl = _repl_for(tmp_path, home)
    bar = repl._status_bar()
    # The bar shows what the next turn will actually use (router-resolved):
    # with no keys configured, the default openai model falls back to mock.
    assert "provider mock" in bar
    assert "model mock:echo" in bar
    assert f"thinking {repl.thinking}" in bar
    assert "context" in bar
    assert "alt+M model" in bar


def test_status_bar_reflects_selected_model(tmp_path: Any, home: Any) -> None:
    import json
    import subprocess

    subprocess.run(
        ["git", "init", "-q"], cwd=tmp_path, check=True, capture_output=True, shell=False
    )
    (tmp_path / "models.json").write_text(
        json.dumps(
            {
                "providers": {
                    "lm-studio": {
                        "baseUrl": "http://127.0.0.1:8080/v1",
                        "api": "openai-completions",
                        "allowLocal": True,
                        "models": [{"id": "ornith-1.0-9b"}],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    from om_harness.config.user_settings import apply_config_update
    from om_harness.harness import Harness
    from om_harness.ui.repl import ChatRepl

    harness = Harness(repo_root=tmp_path, env={})
    session = harness.sessions.create(repo_root=str(tmp_path))
    repl = ChatRepl(harness, session_id=session.session_id)
    apply_config_update(harness, "model", "lm-studio:ornith-1.0-9b")

    bar = repl._status_bar()
    assert "provider lm-studio" in bar
    assert "model lm-studio:ornith-1.0-9b" in bar


def test_show_welcome_prints_panel(tmp_path: Any, home: Any, capsys: Any) -> None:
    repl = _repl_for(tmp_path, home)
    repl._show_welcome()
    out = capsys.readouterr().out
    assert "om-harness" in out


# -- diagnostics and terminal fallback ------------------------------------------


def test_endpoint_for_custom_provider(tmp_path: Any, home: Any) -> None:
    import subprocess

    subprocess.run(
        ["git", "init", "-q"], cwd=tmp_path, check=True, capture_output=True, shell=False
    )
    (tmp_path / "models.json").write_text(
        json.dumps(
            {
                "providers": {
                    "lm-studio": {
                        "baseUrl": "http://127.0.0.1:8080/v1",
                        "api": "openai-completions",
                        "allowLocal": True,
                        "models": [{"id": "ornith-1.0-9b"}],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    from om_harness.harness import Harness

    harness = Harness(repo_root=tmp_path, env={})
    assert (
        harness.provider_registry.endpoint_for("lm-studio:ornith-1.0-9b")
        == "http://127.0.0.1:8080/v1"
    )


def test_connection_error_includes_endpoint_hint(tmp_path: Any, home: Any) -> None:
    import asyncio
    import subprocess

    subprocess.run(
        ["git", "init", "-q"], cwd=tmp_path, check=True, capture_output=True, shell=False
    )
    (tmp_path / "models.json").write_text(
        json.dumps(
            {
                "providers": {
                    "lm-studio": {
                        "baseUrl": "http://127.0.0.1:8080/v1",
                        "api": "openai-completions",
                        "allowLocal": True,
                        "models": [{"id": "ornith-1.0-9b"}],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    from om_harness.config.user_settings import apply_config_update
    from om_harness.harness import Harness

    harness = Harness(repo_root=tmp_path, env={})
    apply_config_update(harness, "model", "lm-studio:ornith-1.0-9b")

    def failing_factory(_model_str: str) -> Any:
        raise Exception("Connection error.")

    harness.runner.model_factory = failing_factory
    session = harness.sessions.create(repo_root=str(tmp_path))
    reply = asyncio.run(harness.chat_turn(session.session_id, "hi"))
    assert "127.0.0.1:8080" in reply
    assert "server running" in reply


def test_plain_session_still_shows_header_and_status(
    tmp_path: Any, home: Any, capsys: Any, monkeypatch: Any
) -> None:
    """Even without prompt_toolkit, the header + status render per prompt."""
    repl = _repl_for(tmp_path, home)
    from om_harness.ui.repl import _PlainSession

    session = _PlainSession(repl)
    monkeypatch.setattr("builtins.input", lambda _prompt: "exit")
    session.prompt()
    out = capsys.readouterr().out
    assert "╭─ om · " in out
    assert "provider" in out
    assert "thinking" in out


# -- keybinding regression ------------------------------------------------------


def test_shift_tab_binding_key_is_valid() -> None:
    """Regression: 'backtab' is an invalid key name on some platforms and
    used to abort building the entire rich session; 's-tab' is correct."""
    from prompt_toolkit.key_binding import KeyBindings

    kb = KeyBindings()
    kb.add("s-tab")(lambda event: None)  # must not raise


def test_no_binding_conflicts_with_enter() -> None:
    """Ctrl+M is physically the same key as Enter; binding the model
    selector to it made every Enter press crash the prompt. Guard: the
    model selector must only bind to keys other than enter/c-m, and every
    configured key name must be valid."""
    from prompt_toolkit.key_binding import KeyBindings

    from om_harness.ui.repl import KEYBINDINGS

    for action, groups in KEYBINDINGS.items():
        for group in groups:
            if action == "model_selector":
                assert "enter" not in group and "c-m" not in group
        # The primary (first) key group must be valid on this platform;
        # fallback aliases may be invalid elsewhere.
        kb = KeyBindings()
        kb.add(*groups[0])(lambda event: None)

    # Submit and the selector must not share any key group.
    submit_groups = {frozenset(g) for g in KEYBINDINGS["submit"]}
    selector_groups = {frozenset(g) for g in KEYBINDINGS["model_selector"]}
    assert not submit_groups & selector_groups


def test_slash_mode_cycles_approval(tmp_path: Any, home: Any) -> None:
    repl = _repl_for(tmp_path, home)
    harness = repl.harness
    before = harness.config.approval.policy.value
    assert repl._slash_command("/mode")
    after = harness.config.approval.policy.value
    assert after != before
