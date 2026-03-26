"""
Web search client for researching errors before looking at repository code.

Uses DuckDuckGo by default (free, no API key). Set TAVILY_API_KEY in .env
for richer results designed specifically for AI agents.
"""
import logging
import os
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


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
    formatted: str = ""  # Ready-to-use context string for the AI prompt


class WebSearchClient:
    """
    Searches the web for error context.

    Backend priority:
    1. Tavily  — if TAVILY_API_KEY is set (best quality for AI agents)
    2. DuckDuckGo — free, no API key required (default fallback)
    """

    def __init__(self, tavily_api_key: str = ""):
        self._tavily_key = tavily_api_key or os.environ.get("TAVILY_API_KEY", "")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def search(self, query: str, max_results: int = 6) -> list[SearchResult]:
        """Run a web search and return a list of results."""
        if self._tavily_key:
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
        Run multiple targeted searches to fully understand the error.

        Searches for:
        - The specific error type + message
        - Known causes and fixes
        - Stack trace identifiers if present

        Returns a formatted context string ready for use in an AI prompt.
        """
        queries = _build_search_queries(error_type, error_message, error_code, stack_trace)
        all_results: list[SearchResult] = []
        seen_urls: set[str] = set()

        for query in queries:
            results = self.search(query, max_results=4)
            for r in results:
                if r.url not in seen_urls:
                    seen_urls.add(r.url)
                    all_results.append(r)

        formatted = _format_web_context(all_results)

        return WebErrorContext(
            query=" | ".join(queries),
            results=all_results,
            formatted=formatted,
        )

    # ------------------------------------------------------------------
    # Backends
    # ------------------------------------------------------------------

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
            from tavily import TavilyClient

            client = TavilyClient(api_key=self._tavily_key)
            response = client.search(
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
            # Tavily can return a synthesised answer — prepend it as a result
            if response.get("answer"):
                results.insert(
                    0,
                    SearchResult(
                        title="Tavily Answer",
                        url="",
                        snippet=response["answer"],
                    ),
                )
            return results
        except Exception as e:
            logger.error("Tavily search failed: %s", e)
            return self._ddg_search(query, max_results)  # Fall back to DDG


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _build_search_queries(
    error_type: str, error_message: str, error_code: str, stack_trace: str
) -> list[str]:
    """Build 2-3 focused search queries for thorough error research."""
    queries: list[str] = []

    # Primary: exact error type + short message
    primary_terms = " ".join(filter(None, [error_type, error_code]))
    if error_message:
        # Trim message to first 80 chars to keep the query tight
        short_msg = error_message[:80].rsplit(" ", 1)[0]
        queries.append(f"{primary_terms} {short_msg}")
    else:
        queries.append(primary_terms)

    # Secondary: causes and fixes
    if error_type:
        queries.append(f"{error_type} root cause fix solution")

    # Tertiary: stack trace top frame if present (often reveals the exact call)
    if stack_trace:
        # Extract first non-blank line of the stack trace
        first_frame = next(
            (ln.strip() for ln in stack_trace.splitlines() if ln.strip()), ""
        )
        if first_frame and first_frame not in queries[0]:
            queries.append(f"{error_type} {first_frame[:100]}")

    return queries[:3]  # Max 3 queries to stay within rate limits


def _format_web_context(results: list[SearchResult]) -> str:
    """Format search results as a context block for the AI prompt."""
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
