"""
Web search client for researching errors before looking at repository code.

Uses DuckDuckGo by default (free, no API key). Set TAVILY_API_KEY in .env
for richer results designed specifically for AI agents.
"""
import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

_MAX_QUERIES = 3       # stay within search API rate limits
_MAX_RESULTS = 4       # results per query


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str


@dataclass
class WebErrorContext:
    """Aggregated web research about an error."""

    query: str
    results: list[SearchResult] = field(default_factory=list)
    formatted: str = ""


class WebSearchClient:
    """
    Searches the web for error context.

    Backend priority:
    1. Tavily  — if TAVILY_API_KEY is set (best quality for AI agents)
    2. DuckDuckGo — free, no API key required (default fallback)
    """

    def __init__(self, tavily_api_key: str = ""):
        self._tavily_key = tavily_api_key or os.environ.get("TAVILY_API_KEY", "")
        # Cache the client so it isn't reconstructed on every search call
        self._tavily_client = None
        if self._tavily_key:
            try:
                from tavily import TavilyClient
                self._tavily_client = TavilyClient(api_key=self._tavily_key)
            except Exception as e:
                logger.warning("Tavily client init failed, falling back to DuckDuckGo: %s", e)

    def search(self, query: str, max_results: int = _MAX_RESULTS) -> list[SearchResult]:
        """Run a web search and return a list of results."""
        if self._tavily_client:
            return self._tavily_search(query, max_results)
        return self._ddg_search(query, max_results)

    def research_error(
        self,
        error_type: str,
        error_message: str,
        error_code: str = "",
        stack_trace: str = "",
    ) -> WebErrorContext:
        """
        Run multiple targeted searches in parallel to fully understand the error.

        Returns a formatted context string ready for use in an AI prompt.
        """
        queries = _build_search_queries(error_type, error_message, error_code, stack_trace)
        all_results: list[SearchResult] = []
        seen_urls: set[str] = set()

        # Queries are independent — run them in parallel
        with ThreadPoolExecutor(max_workers=len(queries)) as pool:
            futures = {pool.submit(self.search, q): q for q in queries}
            for future in as_completed(futures):
                for r in future.result():
                    if r.url not in seen_urls:
                        seen_urls.add(r.url)
                        all_results.append(r)

        return WebErrorContext(
            query=" | ".join(queries),
            results=all_results,
            formatted=_format_web_context(all_results),
        )

    def _ddg_search(self, query: str, max_results: int) -> list[SearchResult]:
        """DuckDuckGo search — free, no API key needed."""
        try:
            from duckduckgo_search import DDGS
            raw = DDGS().text(query, max_results=max_results)
            return [
                SearchResult(
                    title=r.get("title", ""),
                    url=r.get("href", ""),
                    snippet=r.get("body", ""),
                )
                for r in (raw or [])
            ]
        except Exception as e:
            logger.error("DuckDuckGo search failed: %s", e)
            return []

    def _tavily_search(self, query: str, max_results: int) -> list[SearchResult]:
        """Tavily search — higher quality results, designed for AI agents."""
        try:
            response = self._tavily_client.search(
                query=query,
                max_results=max_results,
                search_depth="advanced",
                include_answer=True,
            )
            results = [
                SearchResult(
                    title=r.get("title", ""),
                    url=r.get("url", ""),
                    snippet=r.get("content", ""),
                )
                for r in response.get("results", [])
            ]
            if response.get("answer"):
                results.insert(0, SearchResult(
                    title="Tavily Answer", url="", snippet=response["answer"]
                ))
            return results
        except Exception as e:
            logger.error("Tavily search failed: %s", e)
            return self._ddg_search(query, max_results)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _build_search_queries(
    error_type: str, error_message: str, error_code: str, stack_trace: str
) -> list[str]:
    """Build up to _MAX_QUERIES focused search queries for error research."""
    queries: list[str] = []

    primary_terms = " ".join(filter(None, [error_type, error_code]))
    if error_message:
        short_msg = error_message[:80].rsplit(" ", 1)[0]
        queries.append(f"{primary_terms} {short_msg}")
    else:
        queries.append(primary_terms)

    if error_type:
        queries.append(f"{error_type} root cause fix solution")

    if stack_trace:
        first_frame = next(
            (ln.strip() for ln in stack_trace.splitlines() if ln.strip()), ""
        )
        if first_frame and first_frame not in queries[0]:
            queries.append(f"{error_type} {first_frame[:100]}")

    return queries[:_MAX_QUERIES]


def _format_web_context(results: list[SearchResult]) -> str:
    """Format search results as a markdown context block for the AI prompt."""
    if not results:
        return "No web search results found."

    lines = ["### Web Research Results\n"]
    for i, r in enumerate(results, 1):
        lines.append(f"**[{i}] {r.title}**")
        if r.url:
            lines.append(f"Source: {r.url}")
        lines.append(r.snippet)
        lines.append("")

    return "\n".join(lines)
