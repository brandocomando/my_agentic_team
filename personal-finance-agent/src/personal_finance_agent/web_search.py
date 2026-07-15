from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
from urllib import parse, request
from urllib.error import URLError


@dataclass(frozen=True)
class WebSearchResult:
    title: str
    url: str
    snippet: str


def search_web(query: str, max_results: int = 3, timeout: int = 8) -> list[WebSearchResult]:
    if not query.strip():
        return []
    url = "https://html.duckduckgo.com/html/?" + parse.urlencode({"q": query})
    req = request.Request(
        url,
        headers={
            "User-Agent": "personal-finance-agent/0.1 (+local user initiated merchant lookup)",
        },
    )
    try:
        with request.urlopen(req, timeout=timeout) as response:
            html = response.read().decode("utf-8", errors="replace")
    except (OSError, URLError):
        return []
    parser = _DuckDuckGoParser(max_results=max_results)
    parser.feed(html)
    return parser.results


class _DuckDuckGoParser(HTMLParser):
    def __init__(self, max_results: int) -> None:
        super().__init__()
        self.max_results = max_results
        self.results: list[WebSearchResult] = []
        self._in_link = False
        self._in_snippet = False
        self._current_url = ""
        self._title_parts: list[str] = []
        self._snippet_parts: list[str] = []
        self._pending_title = ""
        self._pending_url = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {key: value or "" for key, value in attrs}
        class_name = attrs_dict.get("class", "")
        if tag == "a" and "result__a" in class_name:
            self._in_link = True
            self._current_url = _clean_duckduckgo_url(attrs_dict.get("href", ""))
            self._title_parts = []
        if "result__snippet" in class_name:
            self._in_snippet = True
            self._snippet_parts = []

    def handle_data(self, data: str) -> None:
        if self._in_link:
            self._title_parts.append(data)
        if self._in_snippet:
            self._snippet_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._in_link:
            self._in_link = False
            self._pending_title = _clean_text(" ".join(self._title_parts))
            self._pending_url = self._current_url
        if self._in_snippet and tag in {"a", "div"}:
            self._in_snippet = False
            snippet = _clean_text(" ".join(self._snippet_parts))
            if self._pending_title and len(self.results) < self.max_results:
                self.results.append(
                    WebSearchResult(
                        title=self._pending_title,
                        url=self._pending_url,
                        snippet=snippet,
                    )
                )
            self._pending_title = ""
            self._pending_url = ""


def _clean_text(value: str) -> str:
    return " ".join(value.split())


def _clean_duckduckgo_url(value: str) -> str:
    if not value:
        return ""
    parsed = parse.urlparse(value)
    query = parse.parse_qs(parsed.query)
    if "uddg" in query and query["uddg"]:
        return query["uddg"][0]
    return value
