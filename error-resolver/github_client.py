"""
GitHub MCP Server client for accessing repository code.

Uses the GitHub MCP server (github/github-mcp-server) via the MCP Python SDK
to search code, browse files, and retrieve context relevant to errors.
"""
import asyncio
import base64
import json
import logging
from typing import Optional

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from config import GitHubConfig

logger = logging.getLogger(__name__)

_MAX_SEARCH_KEYWORDS = 3   # keep within GitHub API rate limits
_MAX_FILES = 3             # files fetched per analysis
_MAX_FILE_LINES = 100      # lines included per file snippet


class GitHubMCPClient:
    """
    Client that connects to the GitHub MCP server via stdio transport.

    The MCP server is started as a subprocess (npx @modelcontextprotocol/server-github)
    and communicates via stdin/stdout using the MCP protocol.
    """

    def __init__(self, config: GitHubConfig):
        self.config = config
        self._server_params = StdioServerParameters(
            command="npx",
            args=["-y", "@modelcontextprotocol/server-github"],
            env={"GITHUB_PERSONAL_ACCESS_TOKEN": config.personal_access_token},
        )

    def _resolve_repo(
        self, owner: Optional[str], repo: Optional[str]
    ) -> tuple[str, str]:
        """Apply config defaults for owner/repo when not explicitly provided."""
        return (
            owner or self.config.default_repo_owner,
            repo or self.config.default_repo_name,
        )

    async def _call_tool(self, tool_name: str, arguments: dict) -> dict:
        """Open a session, call a single tool, and return the parsed result."""
        async with stdio_client(self._server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(tool_name, arguments)
                if result.content:
                    raw = result.content[0].text
                    try:
                        return json.loads(raw)
                    except (json.JSONDecodeError, AttributeError):
                        return {"raw": raw}
                return {}

    def call_tool_sync(self, tool_name: str, arguments: dict) -> dict:
        """Synchronous wrapper around _call_tool for use in non-async contexts."""
        return asyncio.run(self._call_tool(tool_name, arguments))

    # ------------------------------------------------------------------
    # High-level helpers
    # ------------------------------------------------------------------

    def search_code(
        self,
        query: str,
        owner: Optional[str] = None,
        repo: Optional[str] = None,
        max_results: int = 10,
    ) -> list[dict]:
        """Search for code in GitHub repositories matching the query."""
        owner, repo = self._resolve_repo(owner, repo)

        search_q = query
        if owner and repo:
            search_q = f"{query} repo:{owner}/{repo}"
        elif owner:
            search_q = f"{query} user:{owner}"

        try:
            result = self.call_tool_sync(
                "search_code",
                {"q": search_q, "per_page": max_results},
            )
            return [
                {
                    "repo": item.get("repository", {}).get("full_name", ""),
                    "path": item.get("path", ""),
                    "url": item.get("html_url", ""),
                    "sha": item.get("sha", ""),
                }
                for item in result.get("items", [])
            ]
        except Exception as e:
            logger.error("GitHub code search failed: %s", e)
            return []

    def get_file_contents(
        self,
        path: str,
        owner: Optional[str] = None,
        repo: Optional[str] = None,
        ref: str = "main",
    ) -> Optional[str]:
        """Retrieve the decoded text content of a file from a GitHub repository."""
        owner, repo = self._resolve_repo(owner, repo)

        if not owner or not repo:
            logger.warning("Owner and repo must be set to fetch file contents.")
            return None

        try:
            result = self.call_tool_sync(
                "get_file_contents",
                {"owner": owner, "repo": repo, "path": path, "ref": ref},
            )
            content = result.get("content", "")
            if result.get("encoding") == "base64":
                content = base64.b64decode(content).decode("utf-8", errors="replace")
            return content
        except Exception as e:
            logger.error("Failed to fetch file %s: %s", path, e)
            return None

    def list_repository_files(
        self,
        path: str = "",
        owner: Optional[str] = None,
        repo: Optional[str] = None,
        ref: str = "main",
    ) -> list[dict]:
        """List files and directories at a given path in the repository."""
        owner, repo = self._resolve_repo(owner, repo)

        if not owner or not repo:
            return []

        try:
            result = self.call_tool_sync(
                "get_file_contents",
                {"owner": owner, "repo": repo, "path": path, "ref": ref},
            )
            if isinstance(result, list):
                return result
            return [result] if result else []
        except Exception as e:
            logger.error("Failed to list files at %s: %s", path, e)
            return []

    def get_relevant_code_context(
        self,
        error_keywords: list[str],
        owner: Optional[str] = None,
        repo: Optional[str] = None,
    ) -> str:
        """
        Search for code related to error keywords and return combined context.

        Searches GitHub for each keyword, fetches matching file snippets,
        and returns a formatted string for use in AI prompts.
        """
        owner, repo = self._resolve_repo(owner, repo)

        all_matches: list[dict] = []
        seen_paths: set[str] = set()

        for keyword in error_keywords[:_MAX_SEARCH_KEYWORDS]:
            for match in self.search_code(query=keyword, owner=owner, repo=repo):
                key = f"{match['repo']}:{match['path']}"
                if key not in seen_paths:
                    seen_paths.add(key)
                    all_matches.append(match)

        if not all_matches:
            return "No relevant code found in GitHub repository."

        context_parts: list[str] = []
        for match in all_matches[:_MAX_FILES]:
            repo_parts = match["repo"].split("/", 1)
            file_owner = repo_parts[0] if len(repo_parts) > 0 else owner
            file_repo = repo_parts[1] if len(repo_parts) > 1 else repo

            content = self.get_file_contents(
                path=match["path"], owner=file_owner, repo=file_repo
            )
            if content:
                snippet = "\n".join(content.splitlines()[:_MAX_FILE_LINES])
                context_parts.append(
                    f"### File: {match['repo']}/{match['path']}\n"
                    f"URL: {match['url']}\n\n"
                    f"```\n{snippet}\n```"
                )

        return "\n\n".join(context_parts) if context_parts else "No file content retrieved."
