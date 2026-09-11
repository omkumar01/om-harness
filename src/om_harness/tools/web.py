"""Web content fetching tool with SSRF protection.

``fetch_url`` fetches a single URL and optionally extracts readable text
from HTML (markdown-like plain text).

``fetch_batch_url`` fetches multiple URLs concurrently with configurable
concurrency, taking an explicit list of URLs rather than discovering them.

Security model (separate from ``models_json.validate_provider_url``):
- Only ``http``/``https`` schemes are allowed.
- Hosts that are loopback, private, link-local, reserved, or have local
  suffixes (``.local``, ``.internal``, ``.localhost``) are rejected.
- URL-embedded credentials (``user:pass@host``) are rejected.
- A per-URL output cap (``max_chars``) prevents resource exhaustion.
- Batch mode caps concurrent fetches via ``max_concurrent``.
"""

from __future__ import annotations

import asyncio
import contextlib
import gzip
import ipaddress
import socket
from html.parser import HTMLParser
from io import BytesIO
from typing import Any
from urllib.parse import urlparse, urlunparse
from urllib.request import Request, urlopen

from pydantic import BaseModel, Field

from om_harness.tools.base import BaseTool, Permission, ToolError, ToolResult, cap_text

# Schemes accepted by the fetcher.
_ALLOWED_SCHEMES = {"http", "https"}

# TLDs that indicate a local/internal host.
_LOCAL_SUFFIXES = (".localhost", ".local", ".internal")

# Maximum redirect hops before giving up.
_MAX_REDIRECTS = 5

# User-Agent used for all outgoing requests.
_USER_AGENT = "om-harness/1.1.0 (+https://github.com/omkumar01/om-harness)"

# Gzip magic bytes.
_GZIP_MAGIC = b"\x1f\x8b"


class _TextExtractor(HTMLParser):
    """Strip HTML tags, keeping text content with readable whitespace."""

    def __init__(self) -> None:
        super().__init__()
        self._chunks: list[str] = []
        self._skip = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("script", "style", "noscript", "svg"):
            self._skip = True

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style", "noscript", "svg"):
            self._skip = False
        elif tag in ("p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "br"):
            self._chunks.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self._chunks.append(data)

    def get_text(self) -> str:
        raw = "".join(self._chunks)
        # Collapse runs of whitespace into single spaces / newlines.
        lines = raw.splitlines()
        cleaned: list[str] = []
        for line in lines:
            stripped = line.strip()
            if stripped:
                cleaned.append(stripped)
        return "\n".join(cleaned)


def _is_blocked_host(hostname: str) -> bool:
    """True if ``hostname`` is local, private, reserved, or a local-suffix domain."""
    if not hostname:
        return True
    lowered = hostname.lower().rstrip(".")
    if lowered in ("localhost", "local", "internal"):
        return True
    if lowered.endswith(_LOCAL_SUFFIXES):
        return True
    # Try to parse as an IP address.
    try:
        ip = ipaddress.ip_address(lowered)
    except ValueError:
        # Not an IP — it's a domain name. Check if it resolves to a private IP.
        try:
            addrinfo = socket.getaddrinfo(lowered, None)
        except socket.gaierror:
            return False  # Can't resolve — let the fetch fail naturally.
        for _family, _stype, _proto, _canon, sockaddr in addrinfo:
            ip_str = sockaddr[0]
            try:
                ip = ipaddress.ip_address(ip_str)
            except ValueError:
                continue
            if (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_reserved
                or ip.is_multicast
                or ip.is_unspecified
            ):
                return True
        return False
    # It is a literal IP address.
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def _validate_url(url: str) -> str:
    """Validate a URL for safe fetching. Returns the cleaned URL."""
    if not url or not url.strip():
        raise ToolError("URL must not be empty")
    parsed = urlparse(url.strip())
    if parsed.scheme.lower() not in _ALLOWED_SCHEMES:
        raise ToolError(f"URL scheme must be http or https, got {parsed.scheme!r}")
    if parsed.username or parsed.password:
        raise ToolError("URL-embedded credentials are not allowed")
    if not parsed.hostname:
        raise ToolError("URL must include a hostname")
    if _is_blocked_host(parsed.hostname):
        raise ToolError(
            f"refusing local or private host {parsed.hostname!r}; "
            "fetch is restricted to public web content"
        )
    return urlunparse(parsed)


def _extract_text(html: str) -> str:
    """Strip HTML tags and return plain text (markdown-like)."""
    parser = _TextExtractor()
    parser.feed(html)
    parser.close()
    return parser.get_text()


def _decompress_response(data: bytes, content_encoding: str | None) -> bytes:
    """Handle gzip-compressed response bodies."""
    if content_encoding and content_encoding.lower() == "gzip" and data[:2] == _GZIP_MAGIC:
        with gzip.GzipFile(fileobj=BytesIO(data)) as gz:
            return gz.read()
    return data


def _parse_charset(content_type: str | None) -> str:
    """Extract charset from a Content-Type header, default to utf-8."""
    if not content_type:
        return "utf-8"
    for part in content_type.split(";"):
        part = part.strip()
        if part.lower().startswith("charset="):
            return part.split("=", 1)[1].strip().lower()
    return "utf-8"


def _fetch_url_sync(url: str, max_chars: int, extract_text: bool, timeout: float | None) -> str:
    """Synchronous fetch — wrapped in a thread for batch concurrency."""
    validated = _validate_url(url)
    req = Request(validated, headers={"User-Agent": _USER_AGENT, "Accept-Encoding": "gzip"})
    try:
        with urlopen(req, timeout=timeout or 30) as resp:
            charset = _parse_charset(resp.headers.get("Content-Type"))
            content_encoding = resp.headers.get("Content-Encoding")
            data = resp.read()
            data = _decompress_response(data, content_encoding)
            text = data.decode(charset, errors="replace")
    except Exception as exc:
        raise ToolError(f"failed to fetch {url!r}: {exc}") from exc
    if extract_text:
        with contextlib.suppress(Exception):
            text = _extract_text(text)
    trimmed, _ = cap_text(text, max_chars, "fetched content")
    return trimmed


class FetchUrlArgs(BaseModel):
    url: str = Field(description="URL to fetch")
    max_chars: int = Field(
        default=50000, ge=1, le=200000, description="Maximum characters of text to return"
    )
    extract_text: bool = Field(
        default=True, description="Strip HTML tags to extract plain text (markdown-like)"
    )


class FetchUrl(BaseTool[FetchUrlArgs]):
    name = "fetch_url"
    description = (
        "Fetch a single URL and optionally extract readable text "
        "from HTML (markdown-like plain text)."
    )
    permission = Permission.read_only
    Args = FetchUrlArgs

    async def run(self, args: FetchUrlArgs) -> ToolResult:
        loop = asyncio.get_event_loop()
        try:
            text = await loop.run_in_executor(
                None,
                _fetch_url_sync,
                args.url,
                args.max_chars,
                args.extract_text,
                self.ctx.tool_timeout_seconds,
            )
        except ToolError:
            raise
        return ToolResult(
            ok=True,
            output=text,
            data={
                "url": args.url,
                "content_truncated": len(text) >= args.max_chars,
            },
        )


class FetchBatchUrlArgs(BaseModel):
    urls: list[str] = Field(
        min_length=1, max_length=100, description="List of URLs to fetch concurrently"
    )
    max_chars: int = Field(
        default=5000, ge=1, le=200000, description="Maximum characters of text to return per URL"
    )
    extract_text: bool = Field(default=True, description="Strip HTML tags to extract plain text")
    max_concurrent: int = Field(default=10, ge=1, le=20, description="Maximum concurrent fetches")


class FetchBatchUrl(BaseTool[FetchBatchUrlArgs]):
    name = "fetch_batch_url"
    description = (
        "Fetch multiple URLs concurrently (read-only). Takes a list of URLs and fetches "
        "them concurrently with optional HTML text extraction."
    )
    permission = Permission.read_only
    Args = FetchBatchUrlArgs

    async def run(self, args: FetchBatchUrlArgs) -> ToolResult:
        # Validate all URLs first
        validated_urls: list[str] = []
        for url in args.urls:
            validated = _validate_url(url)
            validated_urls.append(validated)

        # Limit concurrency
        semaphore = asyncio.Semaphore(args.max_concurrent)

        async def fetch_one(url: str) -> dict[str, Any]:
            async with semaphore:
                try:
                    text = _fetch_url_sync(
                        url,
                        args.max_chars,
                        args.extract_text,
                        self.ctx.tool_timeout_seconds,
                    )
                    return {"url": url, "ok": True, "text": text}
                except ToolError as exc:
                    return {"url": url, "ok": False, "error": str(exc)}

        # Fetch all URLs concurrently
        tasks = [fetch_one(url) for url in validated_urls]
        results = await asyncio.gather(*tasks)

        succeeded = sum(1 for r in results if r.get("ok"))
        failed = len(results) - succeeded

        # Build summary output
        summary_lines = [f"Fetched {len(results)} URL(s):"]
        for r in results:
            if r.get("ok"):
                summary_lines.append(f"  ✓ {r['url']}")
            else:
                summary_lines.append(f"  ✗ {r['url']}: {r.get('error', 'unknown error')}")

        summary = "\n".join(summary_lines)
        text, cap_hit = cap_text(summary, self.ctx.max_output_chars, "batch summary")

        return ToolResult(
            ok=True,
            output=text,
            truncated=cap_hit,
            data={
                "total": len(results),
                "succeeded": succeeded,
                "failed": failed,
                "results": [
                    {
                        "url": r["url"],
                        "ok": r.get("ok", False),
                        "text": r.get("text") if r.get("ok") else None,
                        "error": r.get("error") if not r.get("ok") else None,
                    }
                    for r in results
                ],
            },
        )
