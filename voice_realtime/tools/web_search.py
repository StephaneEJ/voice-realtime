"""web.search tool — DuckDuckGo HTML scrape, no API key required.

We target `html.duckduckgo.com/html/` which returns server-rendered HTML
(no JS, no token, no rate-limit headers as long as we keep volume low).
Result anchors carry class `result__a` and contain the title text.

Why not the JSON Instant Answer API: it only returns abstract/knowledge
boxes, not actual web results — useless for "search the web for X".

Fragility: DuckDuckGo can change the HTML at any time. The extractor is
written to fail soft (returns no results rather than crashing) and the
model just gets `{"results": [], "query": "..."}` to verbalize.

Domain allowlist: when present, results whose host isn't in the list are
filtered out post-fetch. Allowlist is matched as suffix (".github.com"
also catches "raw.github.com").
"""

from __future__ import annotations

import re
from html import unescape
from urllib.parse import parse_qs, urlparse

import httpx

from .registry import ToolResult, ToolSafetyLevel, ToolSpec


DDG_HTML_URL = "https://html.duckduckgo.com/html/"
# A real-browser UA — DDG occasionally serves a blank page to libcurl-shaped UAs.
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# `<a class="result__a" href="...">Title</a>` — non-greedy, dotall for
# titles that span lines.
_RESULT_RE = re.compile(
    r'<a[^>]+class="[^"]*\bresult__a\b[^"]*"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)
# Strip residual tags from the title text (DDG may wrap query terms in <b>).
_TAG_RE = re.compile(r"<[^>]+>")


def _decode_ddg_href(href: str) -> str:
    """DDG wraps real URLs in `//duckduckgo.com/l/?uddg=<encoded>` redirects.
    Strip the wrapper if present, return the raw target.
    """
    if not href:
        return href
    if href.startswith("//"):
        href = "https:" + href
    try:
        parsed = urlparse(href)
    except ValueError:
        return href
    if parsed.netloc.endswith("duckduckgo.com") and parsed.path.startswith("/l/"):
        qs = parse_qs(parsed.query)
        uddg = qs.get("uddg")
        if uddg:
            return uddg[0]
    return href


def _host(url: str) -> str:
    try:
        return urlparse(url).netloc.lower()
    except ValueError:
        return ""


def _matches_allowlist(host: str, allowlist: list[str]) -> bool:
    """Suffix match — `.github.com` allows `raw.github.com`."""
    if not host:
        return False
    for d in allowlist:
        d = d.lower().lstrip(".")
        if host == d or host.endswith("." + d):
            return True
    return False


def web_search(
    query: str,
    max_results: int = 5,
    allowlist: list[str] | None = None,
    timeout: float = 6.0,
) -> ToolResult:
    """Return top `max_results` web results for `query`, optionally filtered
    by `allowlist`. Each result = {"title": str, "url": str}.
    """
    if not query or not query.strip():
        return ToolResult(ok=False, error="empty query")
    # Distinguish "user passed 0" (clamp to 1) from "default value 5" — using
    # `or 5` would silently rewrite 0 to 5 which surprises the caller.
    if max_results is None:
        max_results = 5
    max_results = max(1, min(int(max_results), 10))

    try:
        resp = httpx.post(
            DDG_HTML_URL,
            data={"q": query, "kl": "fr-fr"},
            headers={"User-Agent": _UA, "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8"},
            timeout=timeout,
            follow_redirects=True,
        )
    except httpx.HTTPError as exc:
        return ToolResult(ok=False, error=f"http: {type(exc).__name__}: {exc}")

    if resp.status_code != 200:
        return ToolResult(ok=False, error=f"http status {resp.status_code}")

    results: list[dict] = []
    for m in _RESULT_RE.finditer(resp.text):
        href = _decode_ddg_href(m.group(1).strip())
        title_raw = _TAG_RE.sub("", m.group(2)).strip()
        title = unescape(title_raw)
        if not href or not title:
            continue
        if allowlist and not _matches_allowlist(_host(href), allowlist):
            continue
        results.append({"title": title, "url": href})
        if len(results) >= max_results:
            break

    return ToolResult(ok=True, data={"query": query, "results": results})


WEB_SEARCH_SPEC = ToolSpec(
    name="web_search",
    description=(
        "Recherche web via DuckDuckGo (HTML, sans API key). Retourne les meilleurs "
        "résultats {title, url}. Optionnel : `allowlist` pour ne garder que certains "
        "domaines (suffix match, ex. ['claude.ai','github.com'])."
    ),
    safety=ToolSafetyLevel.READ_ONLY,
    parameters_schema={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Termes de recherche"},
            "max_results": {"type": "integer", "default": 5, "description": "Nb max résultats (1-10)"},
            "allowlist": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Domaines autorisés (suffix). Vide = tout autorisé.",
            },
        },
        "required": ["query"],
    },
    handler=web_search,
)
