"""Contract tests for fetch_url: URL validation, text extraction, batch sitemap scraping."""

from __future__ import annotations

import gzip
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from om_harness.tools.base import Permission, ToolContext, ToolError
from om_harness.tools.web import (
    FetchUrl,
    _decompress_response,
    _extract_text,
    _parse_sitemap,
    _validate_url,
)

# -- URL validation ----------------------------------------------------------


def test_validate_url_rejects_file_scheme() -> None:
    with pytest.raises(ToolError, match="scheme"):
        _validate_url("file:///etc/passwd")


def test_validate_url_rejects_ftp() -> None:
    with pytest.raises(ToolError, match="scheme"):
        _validate_url("ftp://example.com/file")


def test_validate_url_rejects_credentials() -> None:
    with pytest.raises(ToolError, match="credentials"):
        _validate_url("https://user:pass@example.com/")


def test_validate_url_rejects_localhost() -> None:
    with pytest.raises(ToolError, match="refusing local"):
        _validate_url("http://localhost/test")


def test_validate_url_rejects_loopback_ip() -> None:
    with pytest.raises(ToolError, match="refusing local"):
        _validate_url("http://127.0.0.1/test")


def test_validate_url_rejects_private_ip() -> None:
    with pytest.raises(ToolError, match="refusing local"):
        _validate_url("http://192.168.1.1/test")


def test_validate_url_rejects_private_range() -> None:
    with pytest.raises(ToolError, match="refusing local"):
        _validate_url("http://10.0.0.1/test")


def test_validate_url_rejects_local_suffix() -> None:
    with pytest.raises(ToolError, match="refusing local"):
        _validate_url("http://example.local/test")


def test_validate_url_accepts_public_url() -> None:
    result = _validate_url("https://example.com/docs/page")
    assert result == "https://example.com/docs/page"


def test_validate_url_strips_userinfo_but_rejects_credentials() -> None:
    with pytest.raises(ToolError, match="credentials"):
        _validate_url("https://user@example.com/")


# -- text extraction ----------------------------------------------------------


def test_extract_text_strips_tags() -> None:
    html = "<html><body><p>Hello <b>world</b></p><script>evil()</script></body></html>"
    text = _extract_text(html)
    assert "Hello" in text
    assert "world" in text
    assert "evil()" not in text
    assert "<" not in text


def test_extract_text_handles_nested_html() -> None:
    html = "<div><p>Line 1</p><div><p>Line 2</p></div><p>Line 3</p></div>"
    text = _extract_text(html)
    assert "Line 1" in text
    assert "Line 2" in text
    assert "Line 3" in text


def test_extract_text_empty_input() -> None:
    assert _extract_text("") == ""
    assert _extract_text("<p></p>") == ""


# -- gzip decompression ------------------------------------------------------


def test_decompress_gzip() -> None:
    raw = b"Hello, World!"
    compressed = gzip.compress(raw)
    result = _decompress_response(compressed, "gzip")
    assert result == raw


def test_decompress_noop_without_encoding() -> None:
    raw = b"Hello, World!"
    result = _decompress_response(raw, None)
    assert result == raw


def test_decompress_noop_non_gzip() -> None:
    raw = b"Hello, World!"
    result = _decompress_response(raw, "identity")
    assert result == raw


# -- sitemap parsing ----------------------------------------------------------


def test_parse_sitemap_urlset_filters_by_prefix() -> None:
    sitemap_xml = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://example.com/docs/ai/overview</loc></url>
  <url><loc>https://example.com/docs/ai/setup</loc></url>
  <url><loc>https://example.com/blog/post1</loc></url>
  <url><loc>https://example.com/docs/guide/intro</loc></url>
</urlset>"""
    # Mock _fetch_url_sync to return the sitemap XML
    with patch(
        "om_harness.tools.web._fetch_url_sync",
        return_value=sitemap_xml,
    ):
        urls = _parse_sitemap("https://example.com/sitemap.xml", "/docs/ai", 50)
    assert len(urls) == 2
    assert "https://example.com/docs/ai/overview" in urls
    assert "https://example.com/docs/ai/setup" in urls
    assert all(u.startswith("https://example.com/docs/ai") for u in urls)


def test_parse_sitemap_respects_max_urls() -> None:
    items = "".join(f"<url><loc>https://example.com/docs/ai/page{i}</loc></url>" for i in range(20))
    sitemap_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  {items}
</urlset>"""
    with patch(
        "om_harness.tools.web._fetch_url_sync",
        return_value=sitemap_xml,
    ):
        urls = _parse_sitemap("https://example.com/sitemap.xml", "/docs/ai", 5)
    assert len(urls) == 5


def test_parse_sitemap_rejects_doctype() -> None:
    sitemap_xml = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE foo [<!ENTITY xxe "evil">]>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://example.com/docs/ai/page1</loc></url>
</urlset>"""
    with (
        patch(
            "om_harness.tools.web._fetch_url_sync",
            return_value=sitemap_xml,
        ),
        pytest.raises(ToolError, match="DOCTYPE"),
    ):
        _parse_sitemap("https://example.com/sitemap.xml", "/docs/ai", 50)


def test_parse_sitemap_handles_sitemapindex() -> None:
    # A sitemapindex that points to sub-sitemaps
    index_xml = """<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap><loc>https://example.com/docs-sitemap.xml</loc></sitemap>
  <sitemap><loc>https://example.com/blog-sitemap.xml</loc></sitemap>
</sitemapindex>"""
    sub_sitemap_xml = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://example.com/docs/ai/overview</loc></url>
  <url><loc>https://example.com/docs/ai/setup</loc></url>
  <url><loc>https://example.com/blog/post1</loc></url>
</urlset>"""

    call_count = [0]

    def fake_fetch(url, **kwargs: object):
        call_count[0] += 1
        if "sitemap.xml" in url and call_count[0] == 1:
            return index_xml
        elif "docs-sitemap" in url:
            return sub_sitemap_xml
        else:
            # blog-sitemap — no matching URLs
            return """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
</urlset>"""

    with patch("om_harness.tools.web._fetch_url_sync", side_effect=fake_fetch):
        urls = _parse_sitemap("https://example.com/sitemap.xml", "/docs/ai", 50)
    assert len(urls) == 2
    assert any("docs/ai" in u for u in urls)


def test_parse_sitemap_empty_or_error() -> None:
    with patch(
        "om_harness.tools.web._fetch_url_sync",
        side_effect=ToolError("network error"),
    ):
        urls = _parse_sitemap("https://example.com/sitemap.xml", "/docs", 50)
    assert urls == []


# -- fetch_url tool (single mode) --------------------------------------------


@pytest.fixture
def ctx(tmp_path: Any) -> ToolContext:
    (tmp_path / "README.md").write_text("# test\n")
    return ToolContext(repo_root=tmp_path)


def _make_mock_response(
    body: bytes, status: int = 200, content_type: str | None = "text/html; charset=utf-8"
) -> MagicMock:
    """Create a mock HTTP response object."""
    resp = MagicMock()
    resp.status = status
    resp.url = None
    resp.headers = {"Content-Type": content_type or "text/html; charset=utf-8"}
    resp.__enter__ = MagicMock(return_value=resp)
    resp.__exit__ = MagicMock(return_value=False)
    resp.read.return_value = body
    return resp


async def test_fetch_url_single_extracts_text(
    ctx: ToolContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    html = b"<html><body><h1>Title</h1><p>Hello world</p></body></html>"
    monkeypatch.setattr(
        "om_harness.tools.web.urlopen", lambda req, timeout=None: _make_mock_response(html)
    )
    result = await FetchUrl(ctx).run(
        FetchUrl.Args(url="https://example.com/page", action="single", max_chars=1000)
    )
    assert result.ok
    assert "Title" in result.output
    assert "Hello world" in result.output
    assert "<" not in result.output
    assert FetchUrl.permission == Permission.read_only


async def test_fetch_url_single_raw_html(ctx: ToolContext, monkeypatch: pytest.MonkeyPatch) -> None:
    html = b"<html><body><p>Test</p></body></html>"
    monkeypatch.setattr(
        "om_harness.tools.web.urlopen", lambda req, timeout=None: _make_mock_response(html)
    )
    result = await FetchUrl(ctx).run(
        FetchUrl.Args(url="https://example.com/page", action="single", extract_text=False)
    )
    assert result.ok
    assert "<html>" in result.output


async def test_fetch_url_single_trims_output(
    ctx: ToolContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    html = b"<p>" + b"x" * 10000 + b"</p>"
    monkeypatch.setattr(
        "om_harness.tools.web.urlopen", lambda req, timeout=None: _make_mock_response(html)
    )
    result = await FetchUrl(ctx).run(
        FetchUrl.Args(url="https://example.com/page", action="single", max_chars=100)
    )
    assert result.ok
    # Output is trimmed to max_chars; truncation notice is appended beyond it.
    assert "truncated" in result.output
    assert result.data["truncated"] is True
    # The content portion (before notice) should be at most max_chars.
    content_part = result.output.split("\n...")[0] if "\n..." in result.output else result.output
    assert len(content_part) <= 100


async def test_fetch_url_single_gzip(ctx: ToolContext, monkeypatch: pytest.MonkeyPatch) -> None:
    html = b"<html><body><p>Hello</p></body></html>"
    compressed = gzip.compress(html)
    resp = _make_mock_response(compressed, content_type="text/html; charset=utf-8")
    resp.headers["Content-Encoding"] = "gzip"
    monkeypatch.setattr("om_harness.tools.web.urlopen", lambda req, timeout=None: resp)
    result = await FetchUrl(ctx).run(
        FetchUrl.Args(url="https://example.com/page", action="single", max_chars=1000)
    )
    assert result.ok
    assert "Hello" in result.output


async def test_fetch_url_rejects_localhost(ctx: ToolContext) -> None:
    with pytest.raises(ToolError, match="refusing local"):
        await FetchUrl(ctx).run(FetchUrl.Args(url="http://127.0.0.1/test"))


async def test_fetch_url_rejects_file_scheme(ctx: ToolContext) -> None:
    with pytest.raises(ToolError, match="scheme"):
        await FetchUrl(ctx).run(FetchUrl.Args(url="file:///etc/passwd"))


# -- fetch_url tool (batch mode) ---------------------------------------------


async def test_fetch_url_batch_discovers_and_fetches(
    ctx: ToolContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    sitemap_xml = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://example.com/docs/ai/overview</loc></url>
  <url><loc>https://example.com/docs/ai/setup</loc></url>
  <url><loc>https://example.com/blog/post1</loc></url>
</urlset>"""

    def fake_urlopen(req, timeout=None):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if "sitemap.xml" in url:
            return _make_mock_response(sitemap_xml.encode())
        elif "docs/ai/overview" in url:
            return _make_mock_response(b"<html><body><p>Overview content</p></body></html>")
        elif "docs/ai/setup" in url:
            return _make_mock_response(b"<html><body><p>Setup content</p></body></html>")
        return _make_mock_response(b"<html><body><p>Other</p></body></html>")

    monkeypatch.setattr("om_harness.tools.web.urlopen", fake_urlopen)
    result = await FetchUrl(ctx).run(
        FetchUrl.Args(
            url="https://example.com/docs/ai",
            action="batch",
            max_urls=10,
            max_chars=1000,
        )
    )
    assert result.ok
    assert result.data["action"] == "batch"
    assert result.data["discovered"] == 2
    assert result.data["fetched"] == 2
    assert result.data["succeeded"] == 2


async def test_fetch_url_batch_no_sitemap(
    ctx: ToolContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "om_harness.tools.web.urlopen",
        lambda req, timeout=None: (_ for _ in ()).throw(ToolError("sitemap not found")),
    )
    result = await FetchUrl(ctx).run(
        FetchUrl.Args(url="https://example.com/docs/ai", action="batch", max_urls=10)
    )
    assert result.ok
    assert "No URLs found" in result.output


async def test_fetch_url_batch_respects_max_urls(
    ctx: ToolContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Create a sitemap with many URLs
    items = "".join(f"<url><loc>https://example.com/docs/ai/page{i}</loc></url>" for i in range(20))
    sitemap_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  {items}
</urlset>"""

    call_count = [0]

    def fake_urlopen(req, timeout=None):
        call_count[0] += 1
        return _make_mock_response(sitemap_xml.encode())

    monkeypatch.setattr("om_harness.tools.web.urlopen", fake_urlopen)
    result = await FetchUrl(ctx).run(
        FetchUrl.Args(
            url="https://example.com/docs/ai",
            action="batch",
            max_urls=5,
            max_chars=100,
        )
    )
    assert result.ok
    assert result.data["discovered"] == 5
    assert result.data["fetched"] == 5
