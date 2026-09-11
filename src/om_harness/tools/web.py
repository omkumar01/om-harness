"""Web content fetching tool with SSRF protection and batch sitemap scraping.

``fetch_url`` supports two modes:
- **single**: fetch one URL, optionally extract plain text from HTML, trim to
  ``max_chars``.
- **batch**: given a URL path prefix, fetch the root domain's ``sitemap.xml``,
  discover all URLs matching the prefix, and concurrently fetch each one.

Security model (separate from ``models_json.validate_provider_url``):
- Only ``http``/``https`` schemes are allowed.
- Hosts that are loopback, private, link-local, reserved, or have local
  suffixes (``.local``, ``.internal``, ``.localhost``) are rejected.
- URL-embedded credentials (``user:pass@host``) are rejected.
- XML entity injection is blocked: DOCTYPE/ENTITY declarations in sitemaps
  are rejected before parsing.
- A per-URL output cap (``max_chars``) prevents resource exhaustion.
- Batch mode caps concurrent fetches via ``max_urls``.
"""

from __future__ import annotations

import asyncio
import contextlib
import gzip
import ipaddress
import re
import socket
from html.parser import HTMLParser
from io import BytesIO
from typing import Any
from urllib.parse import urlparse, urlunparse
from urllib.request import Request, urlopen

from defusedxml import ElementTree as ET
from pydantic import BaseModel, Field

from om_harness.tools.base import BaseTool, Permission, ToolError, ToolResult, cap_text

# Schemes accepted by the fetcher.
_ALLOWED_SCHEMES = {"http", "https"}

# TLDs that indicate a local/internal host.
_LOCAL_SUFFIXES = (".localhost", ".local", ".internal")

# Maximum redirect hops before giving up.
_MAX_REDIRECTS = 5

# Pre-check regex for XML entity injection (DOCTYPE / ENTITY declarations).
_XML_ENTITY_RE = re.compile(r"<!DOCTYPE|<!ENTITY", re.IGNORECASE)

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
            "fetch_url is restricted to public web content"
        )
    return urlunparse(parsed)


def _extract_text(html: str) -> str:
    """Strip HTML tags and return plain text."""
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


def _parse_sitemap(sitemap_url: str, path_prefix: str, max_urls: int) -> list[str]:
    """Fetch and parse a sitemap XML, return URLs matching the path prefix.

    Handles both ``urlset`` (returns matching URLs) and ``sitemapindex``
    (recursively fetches referenced sub-sitemaps). Rejects DOCTYPE/ENTITY
    declarations for XML entity injection protection; ``defusedxml`` also
    forbids DTD/entities natively as defense-in-depth.
    """
    try:
        raw = _fetch_url_sync(sitemap_url, max_chars=1_000_000, extract_text=False, timeout=30)
    except ToolError:
        return []
    # Reject XML entity injection: DOCTYPE and ENTITY declarations anywhere
    # in the input (XXE / billion-laughs protection). defusedxml also
    # forbids DTD natively, so this is defense-in-depth.
    if _XML_ENTITY_RE.search(raw):
        raise ToolError(
            "sitemap rejected: DOCTYPE/ENTITY declarations are not allowed (XXE protection)"
        )
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return []
    # Namespace handling: sitemaps use http://www.sitemaps.org/schemas/sitemap/0.9
    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    urls: list[str] = []

    # Check if this is a sitemapindex (references other sitemaps).
    sitemap_elems = root.findall(".//sm:sitemap", ns)
    if sitemap_elems:
        for s in sitemap_elems:
            loc = s.find("sm:loc", ns)
            if loc is not None and loc.text:
                sub_url = loc.text.strip()
                # Recurse into sub-sitemap.
                try:
                    sub_urls = _parse_sitemap(sub_url, path_prefix, max_urls)
                    urls.extend(sub_urls)
                except ToolError:
                    continue
        return urls[:max_urls]

    # It's a urlset — extract matching URLs.
    for url_elem in root.findall(".//sm:url", ns):
        loc = url_elem.find("sm:loc", ns)
        if loc is not None and loc.text:
            u = loc.text.strip()
            # Match against the URL's path component, not the full URL.
            parsed = urlparse(u)
            if parsed.path.startswith(path_prefix):
                urls.append(u)
                if len(urls) >= max_urls:
                    return urls
    return urls


class FetchUrlArgs(BaseModel):
    url: str = Field(description="URL to fetch (single mode) or base path prefix (batch mode)")
    action: str = Field(
        default="single", description="single: fetch one URL; batch: discover + fetch via sitemap"
    )
    max_chars: int = Field(
        default=5000, ge=1, le=200000, description="Maximum characters of text to return per URL"
    )
    extract_text: bool = Field(default=True, description="Strip HTML tags to extract plain text")
    max_urls: int = Field(
        default=10, ge=1, le=50, description="In batch mode: maximum number of URLs to fetch"
    )
    headers: dict[str, str] = Field(default_factory=dict, description="Custom HTTP headers to send")


class FetchUrl(BaseTool[FetchUrlArgs]):
    name = "fetch_url"
    description = (
        "Fetch web content from a URL (read-only). In 'single' mode, fetches one URL "
        "and optionally extracts plain text from HTML. In 'batch' mode, discovers all "
        "URLs under a path prefix via sitemap.xml and fetches them concurrently."
    )
    permission = Permission.read_only
    Args = FetchUrlArgs

    async def run(self, args: FetchUrlArgs) -> ToolResult:
        if args.action == "batch":
            return await self._run_batch(args)
        return await self._run_single(args)

    async def _run_single(self, args: FetchUrlArgs) -> ToolResult:
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
            data={"url": args.url, "action": "single", "truncated": len(text) >= args.max_chars},
        )

    async def _run_batch(self, args: FetchUrlArgs) -> ToolResult:
        # Validate the base URL and derive root + prefix.
        validated = _validate_url(args.url)
        parsed = urlparse(validated)
        path_prefix = parsed.path.rstrip("/")
        if not path_prefix:
            path_prefix = "/"
        sitemap_url = f"{parsed.scheme}://{parsed.netloc}/sitemap.xml"

        # Discover URLs via sitemap.
        loop = asyncio.get_event_loop()
        try:
            sitemap_urls = await loop.run_in_executor(
                None, _parse_sitemap, sitemap_url, path_prefix, args.max_urls
            )
        except ToolError:
            raise
        if not sitemap_urls:
            return ToolResult(
                ok=True,
                output=f"No URLs found under {args.url} in sitemap.xml.",
                data={"discovered": 0, "fetched": 0, "action": "batch"},
            )

        # Concurrently fetch each discovered URL.
        fetch_tasks = [
            loop.run_in_executor(
                None,
                _fetch_url_sync,
                url,
                args.max_chars,
                args.extract_text,
                self.ctx.tool_timeout_seconds,
            )
            for url in sitemap_urls
        ]
        results: list[dict[str, Any]] = []
        summary_lines: list[str] = []
        for url, future in zip(sitemap_urls, fetch_tasks, strict=False):
            try:
                text = await future
                results.append({"url": url, "ok": True, "text_preview": text[:500]})
                summary_lines.append(f"  ✓ {url}")
            except ToolError as exc:
                results.append({"url": url, "ok": False, "error": str(exc)})
                summary_lines.append(f"  ✗ {url}: {exc}")
                summary_lines.append(f"  ✗ {url}: {exc}")

        summary = f"Fetched {len(results)} URL(s) from sitemap:\n" + "\n".join(summary_lines)
        text, cap_hit = cap_text(summary, self.ctx.max_output_chars, "batch summary")
        return ToolResult(
            ok=True,
            output=text,
            truncated=cap_hit,
            data={
                "discovered": len(sitemap_urls),
                "fetched": len(results),
                "succeeded": sum(1 for r in results if r.get("ok")),
                "failed": sum(1 for r in results if not r.get("ok")),
                "action": "batch",
                "results": results,
            },
        )
