"""Self-update support: version checks, the startup update notice, and the
``om-harness update`` upgrade flow.

The latest released version comes from the PyPI JSON API for ``om-harness``;
"what's new" content comes from the GitHub release notes of
``omkumar01/om-harness``. The lookup is cached under
``~/.om-harness/cache/latest-version.json`` for ``DEFAULT_TTL_SECONDS`` so
startup stays offline-fast, and any failure is silent by design — a version
check must never break a command. Users can opt out entirely with
``OM_HARNESS_NO_UPDATE_CHECK=1``.
"""

from __future__ import annotations

import dataclasses
import ipaddress
import json
import re
import socket
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from rich.console import Console

from om_harness import __version__

PYPI_JSON_URL = "https://pypi.org/pypi/om-harness/json"
GITHUB_RELEASE_URL = "https://api.github.com/repos/omkumar01/om-harness/releases/tags/v{version}"
GITHUB_LATEST_RELEASE_URL = "https://api.github.com/repos/omkumar01/om-harness/releases/latest"
CACHE_FILENAME = "latest-version.json"
DEFAULT_TTL_SECONDS = 24 * 3600.0
NO_CHECK_ENV_VAR = "OM_HARNESS_NO_UPDATE_CHECK"
DEFAULT_LOOKUP_TIMEOUT = 2.0
NOTICE_MAX_NOTES_CHARS = 2000

# Argv tokens for which the startup notice is suppressed: anything that is
# itself about versioning/help, machine-readable output, or the updater.
_SKIP_ARGV_FLAGS = {"--version", "--help", "-h", "--json"}
_SKIP_COMMANDS = {"update"}

# Update checks talk to exactly two pinned, https-only, public hosts. Both the
# initial URL and any redirect target are validated against this allowlist and
# resolved-IP boundary checks, so the fetcher cannot be pointed at loopback,
# private, link-local, or otherwise non-global addresses.
_ALLOWED_HOSTS = frozenset({"pypi.org", "api.github.com"})

notice_console = Console(stderr=True)


class UpdateCheckError(Exception):
    """The latest-version lookup failed (offline, bad payload, ...)."""


def parse_version(version: str) -> tuple[int, ...]:
    """Parse ``X.Y.Z`` into a comparable tuple; non-numeric suffix chunks dropped."""
    parts: list[int] = []
    for chunk in version.strip().split("."):
        match = re.match(r"\d+", chunk)
        if not match:
            break
        parts.append(int(match.group()))
    return tuple(parts)


def is_newer(latest: str, current: str) -> bool:
    """True when ``latest`` is a strictly newer release than ``current``."""
    return parse_version(latest) > parse_version(current)


def _validate_update_url(url: str) -> None:
    """Allow only pinned https hosts resolving to globally-routable IPs."""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in _ALLOWED_HOSTS:
        raise UpdateCheckError(f"refusing non-allowlisted update URL: {url}")
    try:
        infos = socket.getaddrinfo(parsed.hostname, 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise UpdateCheckError(f"cannot resolve update host {parsed.hostname}") from exc
    for info in infos:
        address = ipaddress.ip_address(info[4][0])
        if not address.is_global:
            raise UpdateCheckError(
                f"update host {parsed.hostname} resolved to non-public address {address}"
            )


class _ValidatingRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Re-validate every redirect target against the update URL policy."""

    def redirect_request(
        self, req: Any, fp: Any, code: Any, msg: Any, headers: Any, newurl: Any
    ) -> Any:
        _validate_update_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _fetch_json(url: str, timeout: float) -> dict[str, Any]:
    _validate_update_url(url)
    request = urllib.request.Request(url, headers={"User-Agent": f"om-harness/{__version__}"})
    opener = urllib.request.build_opener(_ValidatingRedirectHandler())
    try:
        with opener.open(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except UpdateCheckError:
        raise
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise UpdateCheckError(f"update check failed: {exc}") from exc
    if not isinstance(payload, dict):
        raise UpdateCheckError("unexpected payload from update check")
    return payload


def fetch_latest_version(timeout: float = DEFAULT_LOOKUP_TIMEOUT) -> str:
    """Latest published version from PyPI. Raises UpdateCheckError on failure."""
    version = _fetch_json(PYPI_JSON_URL, timeout).get("info", {}).get("version")
    if not version or not isinstance(version, str):
        raise UpdateCheckError("PyPI response did not include a version")
    return version


def fetch_release_notes(version: str | None, timeout: float = 5.0) -> str | None:
    """Release-notes body for a version (or the latest release); None on failure."""
    url = GITHUB_RELEASE_URL.format(version=version) if version else GITHUB_LATEST_RELEASE_URL
    try:
        body = _fetch_json(url, timeout).get("body")
    except Exception:  # notes are best-effort, never fatal
        return None
    if not isinstance(body, str) or not body.strip():
        return None
    return body[:NOTICE_MAX_NOTES_CHARS]


# --- TTL cache ----------------------------------------------------------------


def _cache_file(cache_dir: Path | None = None) -> Path:
    from om_harness.config.paths import user_cache_dir

    return (cache_dir or user_cache_dir()) / CACHE_FILENAME


def read_cached_version(
    cache_dir: Path | None = None, ttl: float = DEFAULT_TTL_SECONDS
) -> str | None:
    """Cached latest version if present and fresh; None otherwise."""
    path = _cache_file(cache_dir)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        checked_at = float(data["checked_at"])
        version = data["latest_version"]
        if not isinstance(version, str) or not version:
            return None
        if time.time() - checked_at > ttl:
            return None
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return version


def write_cached_version(version: str, cache_dir: Path | None = None) -> None:
    """Record a successful lookup; best-effort, never raises."""
    path = _cache_file(cache_dir)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"checked_at": time.time(), "latest_version": version}) + "\n",
            encoding="utf-8",
        )
    except OSError:
        pass


def latest_version(cache_dir: Path | None = None) -> str | None:
    """Latest version from cache or (on stale cache) PyPI; None when unknown.

    Never raises: a failed or opted-out check simply yields no version.
    """
    import os

    if os.environ.get(NO_CHECK_ENV_VAR):
        return None
    cached = read_cached_version(cache_dir)
    if cached is not None:
        return cached
    try:
        version = fetch_latest_version()
    except Exception:  # offline/blocked must never break startup
        return None
    write_cached_version(version, cache_dir)
    return version


# --- startup notice ------------------------------------------------------------


def should_skip_notice(argv: list[str]) -> bool:
    """True when this invocation should not print the update notice."""
    if any(arg in _SKIP_ARGV_FLAGS for arg in argv):
        return True
    positional = next((arg for arg in argv if not arg.startswith("-")), None)
    return positional in _SKIP_COMMANDS


def notify_if_update_available(
    argv: list[str] | None = None,
    *,
    console: Console | None = None,
    cache_dir: Path | None = None,
) -> None:
    """Print a one-line notice when a newer release exists. Never raises."""
    import sys

    argv = sys.argv[1:] if argv is None else argv
    if should_skip_notice(argv):
        return
    try:
        latest = latest_version(cache_dir)
    except Exception:  # belt and braces: notice is best-effort
        return
    if latest and is_newer(latest, __version__):
        (console or notice_console).print(
            f"[dim]Update available: {latest} (you have {__version__}) — run: om-harness update[/]"
        )


# --- install channels ----------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class UpdateChannel:
    """How this om-harness install should be upgraded."""

    kind: str  # "uv" | "pipx" | "pip" | "manual"
    command: list[str] | None
    label: str


def _dist_dir() -> Path | None:
    """The installed ``om_harness`` dist-info directory, if metadata exists."""
    import importlib.metadata

    try:
        dist = importlib.metadata.distribution("om-harness")
    except importlib.metadata.PackageNotFoundError:
        return None
    path = getattr(dist, "_path", None)
    return Path(path) if path else None


def _under_tools_dir(dist_info: Path, tools_dir: Path) -> bool:
    """True when some ancestor of ``dist_info`` sits directly in ``tools_dir``.

    Checking ancestors (rather than computing a venv root) stays correct across
    layouts: uv/pipx use ``<root>/<tool>/lib/pythonX.Y/site-packages`` on Unix
    and ``<root>/<tool>/Lib/site-packages`` on Windows.
    """
    tools_dir = tools_dir.resolve()
    return any(ancestor.parent == tools_dir for ancestor in dist_info.resolve().parents)


def _default_uv_tools_dir() -> Path:
    import os
    import sys

    override = os.environ.get("UV_TOOL_DIR")
    if override:
        return Path(override)
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / "uv" / "tools"
    return Path.home() / ".local" / "share" / "uv" / "tools"


def _default_pipx_venvs_dir() -> Path:
    import os

    pipx_home = os.environ.get("PIPX_HOME")
    base = Path(pipx_home) if pipx_home else Path.home() / ".local" / "pipx"
    return base / "venvs"


def detect_install_channel(
    dist_info: Path | None = None,
    *,
    uv_tools_dir: Path | None = None,
    pipx_venvs_dir: Path | None = None,
) -> UpdateChannel:
    """Classify the install and return the matching upgrade command."""
    dist_info = dist_info or _dist_dir()
    if dist_info is None:
        return UpdateChannel(
            kind="pip",
            command=["python", "-m", "pip", "install", "--upgrade", "om-harness"],
            label="pip",
        )
    uv_dir = uv_tools_dir if uv_tools_dir is not None else _default_uv_tools_dir()
    pipx_dir = pipx_venvs_dir if pipx_venvs_dir is not None else _default_pipx_venvs_dir()
    if _under_tools_dir(dist_info, uv_dir):
        return UpdateChannel(
            kind="uv",
            command=["uv", "tool", "upgrade", "om-harness"],
            label="uv tool",
        )
    if _under_tools_dir(dist_info, pipx_dir):
        return UpdateChannel(
            kind="pipx",
            command=["pipx", "upgrade", "om-harness"],
            label="pipx",
        )
    direct_url = dist_info / "direct_url.json"
    if direct_url.exists():
        try:
            info = json.loads(direct_url.read_text(encoding="utf-8"))
            if info.get("editable") or str(info.get("url", "")).startswith("file:"):
                return UpdateChannel(
                    kind="manual",
                    command=None,
                    label="editable/git install (update with git pull, then reinstall)",
                )
        except (OSError, ValueError):
            pass
    import sys

    return UpdateChannel(
        kind="pip",
        command=[sys.executable, "-m", "pip", "install", "--upgrade", "om-harness"],
        label="pip",
    )


@dataclasses.dataclass(frozen=True)
class UpgradeResult:
    command: list[str]
    returncode: int
    stdout: str
    stderr: str


def run_upgrade(channel: UpdateChannel, timeout: float = 600.0) -> UpgradeResult:
    """Execute the channel's upgrade command and capture the outcome."""
    assert channel.command is not None
    proc = subprocess.run(
        channel.command,
        capture_output=True,
        text=True,
        timeout=timeout,
        shell=False,
        check=False,
    )
    return UpgradeResult(channel.command, proc.returncode, proc.stdout, proc.stderr)
