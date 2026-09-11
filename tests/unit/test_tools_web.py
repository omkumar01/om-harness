"""Contract tests for fetch_url and fetch_batch_url: URL validation, text extraction, concurrent fetching."""

from __future__ import annotations

import gzip
from typing import Any
from unittest.mock import MagicMock

import pytest

from om_harness.tools.base import Permission, ToolContext, ToolError
from om_harness.tools.web import (
    FetchBatchUrl,
    FetchUrl,
    _decompress_response,
    _extract_text,
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


# -- fetch_url tool (single mode only) ---------------------------------------


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
    result = await FetchUrl(ctx).run(FetchUrl.Args(url="https://example.com/page", max_chars=1000))
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
        FetchUrl.Args(url="https://example.com/page", extract_text=False)
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
    result = await FetchUrl(ctx).run(FetchUrl.Args(url="https://example.com/page", max_chars=100))
    assert result.ok
    # Output is trimmed to max_chars; truncation notice is appended beyond it.
    assert "truncated" in result.output
    assert result.data["content_truncated"] is True
    # The content portion (before notice) should be at most max_chars.
    content_part = result.output.split("\n...")[0] if "\n..." in result.output else result.output
    assert len(content_part) <= 100


async def test_fetch_url_single_gzip(ctx: ToolContext, monkeypatch: pytest.MonkeyPatch) -> None:
    html = b"<html><body><p>Hello</p></body></html>"
    compressed = gzip.compress(html)
    resp = _make_mock_response(compressed, content_type="text/html; charset=utf-8")
    resp.headers["Content-Encoding"] = "gzip"
    monkeypatch.setattr("om_harness.tools.web.urlopen", lambda req, timeout=None: resp)
    result = await FetchUrl(ctx).run(FetchUrl.Args(url="https://example.com/page", max_chars=1000))
    assert result.ok
    assert "Hello" in result.output


async def test_fetch_url_rejects_localhost(ctx: ToolContext) -> None:
    with pytest.raises(ToolError, match="refusing local"):
        await FetchUrl(ctx).run(FetchUrl.Args(url="http://127.0.0.1/test"))


async def test_fetch_url_rejects_file_scheme(ctx: ToolContext) -> None:
    with pytest.raises(ToolError, match="scheme"):
        await FetchUrl(ctx).run(FetchUrl.Args(url="file:///etc/passwd"))


# -- fetch_batch_url tool (batch mode) ---------------------------------------


async def test_fetch_batch_url_fetches_multiple(
    ctx: ToolContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_fetch_one(url: str, max_chars: int, extract_text: bool, timeout: float | None) -> str:
        if "page1" in url:
            return "<html><body><p>Page 1 content</p></body></html>"
        elif "page2" in url:
            return "<html><body><p>Page 2 content</p></body></html>"
        elif "page3" in url:
            return "<html><body><p>Page 3 content</p></body></html>"
        return "<html><body><p>Other</p></body></html>"

    monkeypatch.setattr("om_harness.tools.web._fetch_url_sync", fake_fetch_one)

    result = await FetchBatchUrl(ctx).run(
        FetchBatchUrl.Args(
            urls=[
                "https://example.com/page1",
                "https://example.com/page2",
                "https://example.com/page3",
            ],
            max_chars=1000,
        )
    )
    assert result.ok
    assert result.data["total"] == 3
    assert result.data["succeeded"] == 3
    assert result.data["failed"] == 0
    assert len(result.data["results"]) == 3
    assert all(r["ok"] for r in result.data["results"])
    assert "Page 1 content" in result.data["results"][0]["text"]
    assert "Page 2 content" in result.data["results"][1]["text"]


async def test_fetch_batch_url_handles_errors(
    ctx: ToolContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_fetch_one(url: str, max_chars: int, extract_text: bool, timeout: float | None) -> str:
        if "fail" in url:
            raise ToolError("connection refused")
        return "<html><body><p>Success</p></body></html>"

    monkeypatch.setattr("om_harness.tools.web._fetch_url_sync", fake_fetch_one)

    result = await FetchBatchUrl(ctx).run(
        FetchBatchUrl.Args(
            urls=[
                "https://example.com/success1",
                "https://example.com/fail1",
                "https://example.com/success2",
            ],
            max_chars=1000,
        )
    )
    assert result.ok
    assert result.data["total"] == 3
    assert result.data["succeeded"] == 2
    assert result.data["failed"] == 1
    assert result.data["results"][0]["ok"] is True
    assert result.data["results"][1]["ok"] is False
    assert result.data["results"][2]["ok"] is True
    assert "connection refused" in result.data["results"][1]["error"]


async def test_fetch_batch_url_respects_max_concurrent(
    ctx: ToolContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify max_concurrent parameter is accepted and tool runs without errors."""

    def fake_fetch_one(url: str, max_chars: int, extract_text: bool, timeout: float | None) -> str:
        return "<html><body><p>Content</p></body></html>"

    monkeypatch.setattr("om_harness.tools.web._fetch_url_sync", fake_fetch_one)

    result = await FetchBatchUrl(ctx).run(
        FetchBatchUrl.Args(
            urls=[
                "https://example.com/page1",
                "https://example.com/page2",
                "https://example.com/page3",
                "https://example.com/page4",
            ],
            max_concurrent=2,
            max_chars=1000,
        )
    )
    assert result.ok
    assert result.data["total"] == 4
    assert result.data["succeeded"] == 4


async def test_fetch_batch_url_respects_max_chars(
    ctx: ToolContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    from om_harness.tools.base import cap_text

    def fake_fetch_one(url: str, max_chars: int, extract_text: bool, timeout: float | None) -> str:
        # Simulate what _fetch_url_sync does: apply cap_text
        text = "<p>" + "x" * 10000 + "</p>"
        truncated, _ = cap_text(text, max_chars, "fetched content")
        return truncated

    monkeypatch.setattr("om_harness.tools.web._fetch_url_sync", fake_fetch_one)

    result = await FetchBatchUrl(ctx).run(
        FetchBatchUrl.Args(
            urls=["https://example.com/page1", "https://example.com/page2"],
            max_chars=100,
        )
    )
    assert result.ok
    assert result.data["total"] == 2
    for r in result.data["results"]:
        assert r["ok"] is True
        # The text is truncated to max_chars, but cap_text adds a truncation notice
        # So we just verify the content part (before truncation notice) is at most max_chars
        content_part = r["text"].split("\n...")[0] if "\n..." in r["text"] else r["text"]
        assert len(content_part) <= 100


async def test_fetch_batch_url_validates_all_urls(ctx: ToolContext) -> None:
    with pytest.raises(ToolError, match="refusing local"):
        await FetchBatchUrl(ctx).run(FetchBatchUrl.Args(urls=["http://127.0.0.1/test"]))

    with pytest.raises(ToolError, match="scheme"):
        await FetchBatchUrl(ctx).run(FetchBatchUrl.Args(urls=["file:///etc/passwd"]))


async def test_fetch_batch_url_extract_text_option(
    ctx: ToolContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    from om_harness.tools.web import _extract_text

    def fake_fetch_one(url: str, max_chars: int, extract_text: bool, timeout: float | None) -> str:
        # The mock receives raw HTML. The actual _fetch_url_sync applies extraction
        # based on extract_text flag. We need to simulate that behavior.
        raw_html = "<html><body><h1>Title</h1><p>Content</p></body></html>"
        if extract_text:
            return _extract_text(raw_html)
        return raw_html

    monkeypatch.setattr("om_harness.tools.web._fetch_url_sync", fake_fetch_one)

    # With extract_text=True (default)
    result = await FetchBatchUrl(ctx).run(
        FetchBatchUrl.Args(urls=["https://example.com/page1"], extract_text=True)
    )
    assert result.ok
    assert "Title" in result.data["results"][0]["text"]
    assert "Content" in result.data["results"][0]["text"]
    assert "<" not in result.data["results"][0]["text"]

    # With extract_text=False
    result = await FetchBatchUrl(ctx).run(
        FetchBatchUrl.Args(urls=["https://example.com/page1"], extract_text=False)
    )
    assert result.ok
    assert "<html>" in result.data["results"][0]["text"]


async def test_fetch_batch_url_rejects_localhost(ctx: ToolContext) -> None:
    with pytest.raises(ToolError, match="refusing local"):
        await FetchBatchUrl(ctx).run(FetchBatchUrl.Args(urls=["http://127.0.0.1/test"]))


async def test_fetch_batch_url_rejects_file_scheme(ctx: ToolContext) -> None:
    with pytest.raises(ToolError, match="scheme"):
        await FetchBatchUrl(ctx).run(FetchBatchUrl.Args(urls=["file:///etc/passwd"]))
