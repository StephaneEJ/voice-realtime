"""web.search tool — parsing + allowlist with httpx mocked."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from voice_realtime.tools.web_search import _decode_ddg_href, _matches_allowlist, web_search


# ─── DDG redirect decoder ──────────────────────────────────────────────────


def test_decode_ddg_redirect_unwraps() -> None:
    href = "//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fpage&rut=xyz"
    assert _decode_ddg_href(href) == "https://example.com/page"


def test_decode_direct_link_passthrough() -> None:
    href = "https://github.com/anthropics/claude-code"
    assert _decode_ddg_href(href) == href


def test_decode_empty_returns_empty() -> None:
    assert _decode_ddg_href("") == ""


# ─── Allowlist suffix matching ─────────────────────────────────────────────


def test_allowlist_exact_match() -> None:
    assert _matches_allowlist("github.com", ["github.com"])


def test_allowlist_subdomain_match() -> None:
    assert _matches_allowlist("raw.github.com", ["github.com"])


def test_allowlist_leading_dot_stripped() -> None:
    assert _matches_allowlist("api.openai.com", [".openai.com"])


def test_allowlist_no_match() -> None:
    assert not _matches_allowlist("evil.com", ["github.com", "openai.com"])


def test_allowlist_substring_not_enough() -> None:
    """`badgithub.com` must NOT match `github.com`."""
    assert not _matches_allowlist("badgithub.com", ["github.com"])


# ─── End-to-end with mocked httpx ──────────────────────────────────────────


_HTML_FIXTURE = """
<html><body>
<div class="result">
  <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fpage1">Result <b>one</b></a>
</div>
<div class="result">
  <a class="result__a" href="https://github.com/anthropics/claude-code">claude-code on GitHub</a>
</div>
<div class="result">
  <a class="result__a" href="https://evil.com/spam">Spam &amp; eggs</a>
</div>
</body></html>
"""


def _mock_response(text: str, status: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status
    resp.text = text
    return resp


def test_web_search_parses_and_returns_top_n() -> None:
    with patch("voice_realtime.tools.web_search.httpx.post", return_value=_mock_response(_HTML_FIXTURE)):
        r = web_search("anything", max_results=2)
    assert r.ok, r.error
    assert r.data["query"] == "anything"
    assert len(r.data["results"]) == 2
    # First result: DDG redirect was unwrapped, HTML entities + tags stripped
    assert r.data["results"][0]["url"] == "https://example.com/page1"
    assert r.data["results"][0]["title"] == "Result one"
    # Second: direct link preserved
    assert r.data["results"][1]["url"].startswith("https://github.com/")


def test_web_search_allowlist_filters() -> None:
    with patch("voice_realtime.tools.web_search.httpx.post", return_value=_mock_response(_HTML_FIXTURE)):
        r = web_search("x", max_results=5, allowlist=["github.com"])
    assert r.ok
    assert len(r.data["results"]) == 1
    assert "github.com" in r.data["results"][0]["url"]


def test_web_search_html_entities_decoded() -> None:
    """`&amp;` in title text must be decoded to `&`."""
    with patch("voice_realtime.tools.web_search.httpx.post", return_value=_mock_response(_HTML_FIXTURE)):
        r = web_search("x", max_results=10)
    titles = [res["title"] for res in r.data["results"]]
    assert "Spam & eggs" in titles


def test_web_search_empty_query_rejected() -> None:
    r = web_search("")
    assert not r.ok


def test_web_search_http_error_returns_error_result() -> None:
    import httpx
    with patch("voice_realtime.tools.web_search.httpx.post", side_effect=httpx.ConnectError("boom")):
        r = web_search("q")
    assert not r.ok
    assert "http" in (r.error or "").lower()


def test_web_search_non_200_returns_error() -> None:
    with patch("voice_realtime.tools.web_search.httpx.post", return_value=_mock_response("", status=503)):
        r = web_search("q")
    assert not r.ok
    assert "503" in (r.error or "")


def test_web_search_max_results_clamped() -> None:
    """max_results > 10 should be clamped, < 1 should snap to 1."""
    with patch("voice_realtime.tools.web_search.httpx.post", return_value=_mock_response(_HTML_FIXTURE)):
        r_big = web_search("x", max_results=100)
        r_zero = web_search("x", max_results=0)
    # 3 results in fixture, all returned (capped at 10 internally then bounded by fixture size)
    assert len(r_big.data["results"]) == 3
    # max_results=0 -> snap to 1
    assert len(r_zero.data["results"]) == 1
