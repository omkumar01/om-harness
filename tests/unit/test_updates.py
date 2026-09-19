"""Tests for the self-updater: version comparison, PyPI lookup, TTL cache,
the startup update notice, install-channel detection, and release notes."""

from __future__ import annotations

import io
import json
import time
import types
from typing import Any

import pytest

from om_harness import updater
from om_harness.updater import (
    UpdateCheckError,
    fetch_latest_version,
    is_newer,
    notify_if_update_available,
    parse_version,
    read_cached_version,
    write_cached_version,
)


class _FakeResponse(io.BytesIO):
    """Minimal stand-in for the object returned by an opener's open()."""

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()


class _FakeOpener:
    """Stand-in for the OpenerDirector built by build_opener()."""

    def __init__(self, handler: Any) -> None:
        self._handler = handler

    def open(self, req: Any, timeout: float = 0) -> _FakeResponse:
        return self._handler(req, timeout=timeout)


def _patch_fetch(
    monkeypatch: pytest.MonkeyPatch,
    payload: bytes | None = None,
    error: Exception | None = None,
) -> list[dict[str, Any]]:
    """Patch the opener factory; returns the requests the code attempted."""
    calls: list[dict[str, Any]] = []

    def fake_open(req: Any, timeout: float = 0) -> _FakeResponse:
        calls.append({"url": req.full_url, "timeout": timeout})
        if error is not None:
            raise error
        assert payload is not None
        return _FakeResponse(payload)

    monkeypatch.setattr(
        updater.urllib.request, "build_opener", lambda *handlers: _FakeOpener(fake_open)
    )
    return calls


# --- version parsing / comparison -------------------------------------------


@pytest.mark.parametrize(
    ("latest", "current", "expected"),
    [
        ("1.3.0", "1.2.0", True),
        ("1.2.1", "1.2.0", True),
        ("2.0.0", "1.9.9", True),
        ("1.2.0", "1.2.0", False),
        ("1.1.9", "1.2.0", False),
        ("1.10.0", "1.9.0", True),  # numeric, not lexicographic
        ("1.2.0rc1", "1.2.0", False),  # pre-release suffix tolerated
        ("1.2.0.dev0", "1.2.0", False),
        ("1.3.0b1", "1.2.9", True),
    ],
)
def test_is_newer(latest: str, current: str, expected: bool) -> None:
    assert is_newer(latest, current) == expected


@pytest.mark.parametrize(
    ("version", "expected"),
    [
        ("1.2.0", (1, 2, 0)),
        ("1.10.3", (1, 10, 3)),
        ("1.2", (1, 2)),
        ("1.2.0rc1", (1, 2, 0)),
    ],
)
def test_parse_version(version: str, expected: tuple[int, ...]) -> None:
    assert parse_version(version) == expected


# --- PyPI lookup -------------------------------------------------------------


def test_fetch_latest_version_parses_pypi_json(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = json.dumps({"info": {"version": "9.9.9"}}).encode()
    calls = _patch_fetch(monkeypatch, payload=payload)
    assert fetch_latest_version() == "9.9.9"
    assert calls[0]["url"] == updater.PYPI_JSON_URL
    assert calls[0]["url"].startswith("https://pypi.org/")


def test_fetch_latest_version_raises_on_bad_json(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_fetch(monkeypatch, payload=b"not json")
    with pytest.raises(UpdateCheckError):
        fetch_latest_version()


def test_fetch_latest_version_raises_on_missing_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_fetch(monkeypatch, payload=json.dumps({"info": {}}).encode())
    with pytest.raises(UpdateCheckError):
        fetch_latest_version()


def test_fetch_latest_version_wraps_network_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_fetch(monkeypatch, error=OSError("no network"))
    with pytest.raises(UpdateCheckError):
        fetch_latest_version()


# --- TTL cache ---------------------------------------------------------------


def test_cache_round_trip(home: Any) -> None:
    assert read_cached_version() is None
    write_cached_version("1.3.0")
    assert read_cached_version() == "1.3.0"


def test_cache_expired_after_ttl(home: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    write_cached_version("1.3.0")
    cache_file = home / "cache" / updater.CACHE_FILENAME
    data = json.loads(cache_file.read_text(encoding="utf-8"))
    data["checked_at"] = time.time() - (updater.DEFAULT_TTL_SECONDS + 1)
    cache_file.write_text(json.dumps(data), encoding="utf-8")
    assert read_cached_version() is None


def test_cache_corrupt_file_treated_as_missing(home: Any) -> None:
    cache_file = home / "cache" / updater.CACHE_FILENAME
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text("{broken", encoding="utf-8")
    assert read_cached_version() is None


def test_cache_missing_version_field_treated_as_missing(home: Any) -> None:
    cache_file = home / "cache" / updater.CACHE_FILENAME
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps({"checked_at": time.time()}), encoding="utf-8")
    assert read_cached_version() is None


# --- combined lookup (cache-first, silent network) ---------------------------


def test_latest_version_uses_fresh_cache_without_network(
    home: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_cached_version("1.3.0")

    def fail_fetch(timeout: float = 0) -> str:
        raise AssertionError("network must not be hit when cache is fresh")

    monkeypatch.setattr(updater, "fetch_latest_version", fail_fetch)
    assert updater.latest_version() == "1.3.0"


def test_latest_version_fetches_and_caches_when_stale(
    home: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(updater, "fetch_latest_version", lambda timeout=2.0: "1.3.0")
    assert updater.latest_version() == "1.3.0"
    assert read_cached_version() == "1.3.0"


def test_latest_version_returns_none_when_fetch_fails(
    home: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(timeout: float = 2.0) -> str:
        raise UpdateCheckError("offline")

    monkeypatch.setattr(updater, "fetch_latest_version", boom)
    assert updater.latest_version() is None


# --- startup notice ----------------------------------------------------------


def _notice(capsys: pytest.CaptureFixture[str], argv: list[str]) -> str:
    notify_if_update_available(argv)
    return capsys.readouterr().err


def test_notice_prints_when_newer_version_available(
    home: Any, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(updater, "latest_version", lambda cache_dir=None: "1.3.0")
    out = _notice(capsys, ["status"])
    assert "1.3.0" in out
    assert "om-harness update" in out


def test_notice_silent_when_up_to_date(
    home: Any, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(updater, "latest_version", lambda cache_dir=None: "1.2.0")
    assert _notice(capsys, ["status"]) == ""


def test_notice_silent_when_check_unavailable(
    home: Any, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(updater, "latest_version", lambda cache_dir=None: None)
    assert _notice(capsys, ["status"]) == ""


def test_notice_skipped_for_version_and_help_flags(
    home: Any, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(updater, "latest_version", lambda cache_dir=None: "1.3.0")
    for argv in (["--version"], ["--help"], ["-h"], ["run", "--json"], ["update"]):
        assert _notice(capsys, argv) == "", f"expected silence for {argv}"


def test_notice_silent_on_unexpected_error(
    home: Any, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def boom(cache_dir: Any = None) -> str:
        raise RuntimeError("unexpected")

    monkeypatch.setattr(updater, "latest_version", boom)
    assert _notice(capsys, ["status"]) == ""


# --- URL policy (SSRF hardening) ---------------------------------------------


def test_validate_url_rejects_non_https_and_non_allowlisted_hosts() -> None:
    with pytest.raises(UpdateCheckError):
        updater._validate_update_url("http://pypi.org/pypi/om-harness/json")
    with pytest.raises(UpdateCheckError):
        updater._validate_update_url("https://evil.example.com/pypi/om-harness/json")
    with pytest.raises(UpdateCheckError):
        updater._validate_update_url("https://localhost/pypi/om-harness/json")


def test_validate_url_accepts_allowlisted_host() -> None:
    updater._validate_update_url(updater.PYPI_JSON_URL)


def test_validate_url_rejects_non_global_resolved_ips(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for bad in ((127, 0, 0, 1), (10, 0, 0, 5), (169, 254, 169, 254)):
        monkeypatch.setattr(
            updater.socket,
            "getaddrinfo",
            lambda *a, _bad=bad, **k: [(2, 1, 6, "", (*_bad, 0))],  # type: ignore[operator]
        )
        with pytest.raises(UpdateCheckError):
            updater._validate_update_url(updater.PYPI_JSON_URL)


# --- release notes -----------------------------------------------------------


def test_fetch_release_notes_returns_body(monkeypatch: pytest.MonkeyPatch) -> None:
    body = "### Added\n- om-harness update command"
    payload = json.dumps({"body": body}).encode()
    calls = _patch_fetch(monkeypatch, payload=payload)
    assert updater.fetch_release_notes("1.3.0") == body
    assert calls[0]["url"] == updater.GITHUB_RELEASE_URL.format(version="1.3.0")


def test_fetch_release_notes_uses_latest_endpoint_without_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _patch_fetch(monkeypatch, payload=json.dumps({"body": "notes"}).encode())
    assert updater.fetch_release_notes(None) == "notes"
    assert calls[0]["url"] == updater.GITHUB_LATEST_RELEASE_URL


def test_fetch_release_notes_returns_none_on_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_fetch(monkeypatch, error=OSError("offline"))
    assert updater.fetch_release_notes("1.3.0") is None


# --- install channel detection ------------------------------------------------


def _dist_info(tmp_path: Any, layout: str) -> Any:
    """Build a fake dist-info under a venv-style layout; return its path."""
    site_packages = tmp_path / layout / "om-harness" / "lib" / "python3.12" / "site-packages"
    dist = site_packages / "om_harness-1.2.0.dist-info"
    dist.mkdir(parents=True)
    return dist


def test_detect_channel_uv(tmp_path: Any) -> None:
    dist = _dist_info(tmp_path, "uv-tools")
    channel = updater.detect_install_channel(
        dist, uv_tools_dir=tmp_path / "uv-tools", pipx_venvs_dir=tmp_path / "pipx" / "venvs"
    )
    assert channel.kind == "uv"
    assert channel.command == ["uv", "tool", "upgrade", "om-harness"]


def test_detect_channel_pipx(tmp_path: Any) -> None:
    dist = (
        tmp_path / "pipx" / "venvs" / "om-harness" / "lib" / "py3" / "site-packages" / "d.dist-info"
    )
    dist.mkdir(parents=True)
    channel = updater.detect_install_channel(
        dist, uv_tools_dir=tmp_path / "uv-tools", pipx_venvs_dir=tmp_path / "pipx" / "venvs"
    )
    assert channel.kind == "pipx"
    assert channel.command == ["pipx", "upgrade", "om-harness"]


def test_detect_channel_pip_default(tmp_path: Any) -> None:
    dist = tmp_path / "somevenv" / "lib" / "py3" / "site-packages" / "d.dist-info"
    dist.mkdir(parents=True)
    channel = updater.detect_install_channel(
        dist, uv_tools_dir=tmp_path / "uv-tools", pipx_venvs_dir=tmp_path / "pipx" / "venvs"
    )
    assert channel.kind == "pip"
    assert channel.command is not None
    assert channel.command[-4:] == ["pip", "install", "--upgrade", "om-harness"]


def test_detect_channel_editable_is_manual(tmp_path: Any) -> None:
    dist = tmp_path / "somevenv" / "lib" / "py3" / "site-packages" / "d.dist-info"
    dist.mkdir(parents=True)
    (dist / "direct_url.json").write_text(
        json.dumps({"url": "file:///repo", "editable": True}), encoding="utf-8"
    )
    channel = updater.detect_install_channel(
        dist, uv_tools_dir=tmp_path / "uv-tools", pipx_venvs_dir=tmp_path / "pipx" / "venvs"
    )
    assert channel.kind == "manual"
    assert channel.command is None


def test_run_upgrade_captures_result(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(command: Any, **kwargs: Any) -> Any:
        assert command == ["echo", "upgrade"]
        return types.SimpleNamespace(returncode=0, stdout="done", stderr="")

    monkeypatch.setattr(updater.subprocess, "run", fake_run)
    channel = updater.UpdateChannel(kind="pip", command=["echo", "upgrade"], label="pip")
    result = updater.run_upgrade(channel)
    assert result.returncode == 0
    assert result.stdout == "done"


# --- `om-harness update` command -----------------------------------------------


def _invoke_update(args: list[str]) -> Any:
    from typer.testing import CliRunner

    from om_harness.cli.app import app

    return CliRunner().invoke(app, ["update", *args], catch_exceptions=False)


def test_update_command_already_up_to_date(home: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(updater, "latest_version", lambda cache_dir=None: "1.2.0")
    result = _invoke_update([])
    assert result.exit_code == 0
    assert "up to date" in result.output


def test_update_command_success_prints_notes(home: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(updater, "latest_version", lambda cache_dir=None: "1.3.0")
    monkeypatch.setattr(
        updater,
        "detect_install_channel",
        lambda *a, **k: updater.UpdateChannel(
            kind="pip", command=["pip", "install", "--upgrade", "om-harness"], label="pip"
        ),
    )

    def fake_upgrade(channel: Any, timeout: float = 0) -> updater.UpgradeResult:
        return updater.UpgradeResult(channel.command or [], 0, "", "")

    monkeypatch.setattr(updater, "run_upgrade", fake_upgrade)
    monkeypatch.setattr(
        updater, "fetch_release_notes", lambda version, timeout=0: "### Added\n- new stuff"
    )

    result = _invoke_update([])
    assert result.exit_code == 0
    assert "1.3.0" in result.output
    assert "new stuff" in result.output
    assert "estart" in result.output
    assert read_cached_version() == "1.3.0"


def test_update_command_failure_exits_nonzero(home: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(updater, "latest_version", lambda cache_dir=None: "1.3.0")
    monkeypatch.setattr(
        updater,
        "detect_install_channel",
        lambda *a, **k: updater.UpdateChannel(kind="pip", command=["pip"], label="pip"),
    )

    def fake_upgrade(channel: Any, timeout: float = 0) -> updater.UpgradeResult:
        return updater.UpgradeResult(channel.command or [], 1, "", "pip exploded")

    monkeypatch.setattr(updater, "run_upgrade", fake_upgrade)
    result = _invoke_update([])
    assert result.exit_code == 1
    assert "pip exploded" in result.output


def test_update_command_json_payload(home: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(updater, "latest_version", lambda cache_dir=None: "1.3.0")
    monkeypatch.setattr(
        updater,
        "detect_install_channel",
        lambda *a, **k: updater.UpdateChannel(kind="pip", command=["pip"], label="pip"),
    )
    monkeypatch.setattr(
        updater,
        "run_upgrade",
        lambda channel, timeout=0: updater.UpgradeResult(channel.command or [], 0, "", ""),
    )
    monkeypatch.setattr(updater, "fetch_release_notes", lambda version, timeout=0: "- note")

    result = _invoke_update(["--json"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["current"] == "1.2.0"
    assert payload["latest"] == "1.3.0"
    assert payload["channel"] == "pip"
    assert payload["upgraded"] is True
    assert payload["notes"] == "- note"


def test_update_command_manual_channel_gives_instructions(
    home: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(updater, "latest_version", lambda cache_dir=None: "1.3.0")
    monkeypatch.setattr(
        updater,
        "detect_install_channel",
        lambda *a, **k: updater.UpdateChannel(
            kind="manual", command=None, label="update with git pull, then reinstall"
        ),
    )

    def fail_upgrade(channel: Any, timeout: float = 0) -> None:
        raise AssertionError("manual channel must not run a subprocess")

    monkeypatch.setattr(updater, "run_upgrade", fail_upgrade)
    result = _invoke_update([])
    assert result.exit_code == 0
    assert "git pull" in result.output


# --- run_app wiring ------------------------------------------------------------


def test_run_app_checks_for_updates_before_dispatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import sys

    from om_harness.cli import app as app_module

    seen: dict[str, Any] = {}
    monkeypatch.setattr(
        updater,
        "notify_if_update_available",
        lambda argv=None: seen.update(argv=argv),
    )
    monkeypatch.setattr(sys, "argv", ["om-harness", "--version"])
    with pytest.raises(SystemExit):
        app_module.run_app()
    assert seen["argv"] == ["--version"]
