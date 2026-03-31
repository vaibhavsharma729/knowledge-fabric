"""
Error Resolver MCP Server

Exposes error resolution tools to GitHub Copilot Chat (and any MCP-compatible client).
Run locally — Copilot connects via stdio and calls tools when you paste an error or
attach a screenshot in the chat.

Setup:
  1. pip install -r requirements.txt
  2. Copy .env.example to .env and fill in your credentials
  3. Add .vscode/mcp.json to your workspace (see README)
  4. In VS Code Copilot Chat, ask: "@workspace fix this error: <paste error>"
"""
import asyncio
import logging
import os
import sys
from concurrent.futures import ThreadPoolExecutor

from dotenv import load_dotenv
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

load_dotenv()
logging.basicConfig(level=logging.WARNING, stream=sys.stderr)

server = Server("error-resolver")
_executor = ThreadPoolExecutor(max_workers=4)


def _run_sync(fn, *args):
    """Run a blocking function without blocking the async event loop."""
    loop = asyncio.get_event_loop()
    return loop.run_in_executor(_executor, fn, *args)


# ------------------------------------------------------------------
# Tool definitions
# ------------------------------------------------------------------

@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="resolve_error",
            description=(
                "Analyze an error message or stack trace and return a step-by-step fix. "
                "Reads the actual application code from GitHub, queries Oracle DB error logs "
                "for historical occurrences, and searches the web for known solutions. "
                "The AI then determines whether the fix belongs in the application code, "
                "the database (schema or data), or both — and provides the exact change: "
                "file + function to edit, or SQL statement to run. "
                "Use this whenever a user pastes an error, stack trace, or describes a bug."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "error_text": {
                        "type": "string",
                        "description": (
                            "Full error message, stack trace, or description. "
                            "If the user attached a screenshot, extract the error text "
                            "from it and pass it here."
                        ),
                    },
                },
                "required": ["error_text"],
            },
        ),
        Tool(
            name="search_github_code",
            description=(
                "Search the configured GitHub repository for code related to an error. "
                "Returns file snippets most likely to contain the root cause."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "keywords": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "2-4 keywords derived from the error to search for.",
                    },
                },
                "required": ["keywords"],
            },
        ),
        Tool(
            name="query_error_logs",
            description=(
                "Query the Oracle RDS database for historical error log entries "
                "matching the given keywords. Returns recent matching rows."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "keywords": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Keywords to search for in the ERROR_MESSAGE column.",
                    },
                },
                "required": ["keywords"],
            },
        ),
        Tool(
            name="query_database",
            description=(
                "Run any read-only SELECT query against the Oracle RDS database. "
                "Use this to investigate data issues in ANY table — not just error logs. "
                "For example: check for duplicate primary keys, inspect sequence values, "
                "look at table data to find the root cause of an error, verify constraints, "
                "or count records. Only SELECT and WITH queries are allowed (no DML/DDL). "
                "Use this when the error is related to data quality, missing records, "
                "duplicate keys, wrong values, or any database state issue."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "sql": {
                        "type": "string",
                        "description": (
                            "A read-only SELECT or WITH query to run. "
                            "Examples: "
                            "'SELECT MAX(OBJECT_ID), COUNT(*) FROM ACCOUNTING_RULES', "
                            "'SELECT LAST_NUMBER FROM USER_SEQUENCES WHERE SEQUENCE_NAME = :seq_name', "
                            "'SELECT * FROM ACCOUNTING_RULES WHERE CREATED_BY = :created_by'"
                        ),
                    },
                    "params": {
                        "type": "object",
                        "description": "Optional bind parameters as key-value pairs e.g. {\"seq_name\": \"ACCOUNTING_RULES_SEQ\"}",
                    },
                },
                "required": ["sql"],
            },
        ),
    ]


# ------------------------------------------------------------------
# Tool implementations
# ------------------------------------------------------------------

@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    # Import here so module-level failures don't crash the server
    from config import AppConfig
    from error_analyzer import ErrorAnalyzer
    from github_client import GitHubMCPClient
    from oracle_client import OracleClient
    from web_search import WebSearchClient

    cfg = AppConfig.from_env()

    # ── resolve_error ──────────────────────────────────────────────
    if name == "resolve_error":
        error_text: str = arguments["error_text"]

        analyzer = ErrorAnalyzer(cfg.copilot)
        web_client = WebSearchClient(cfg.tavily_api_key)

        # Step 1: extract structured error info
        error_info = await _run_sync(analyzer.extract_error_info_from_text, error_text)

        # Step 2: web research
        web_result = await _run_sync(
            web_client.research_error,
            error_info.error_type,
            error_info.error_message,
            error_info.error_code,
            error_info.stack_trace,
        )

        # Step 3: GitHub code search (optional)
        github_context = ""
        if cfg.github.personal_access_token:
            search_terms = await _run_sync(
                analyzer.derive_repo_search_terms, error_info, web_result.formatted
            )
            github_client = GitHubMCPClient(cfg.github)
            github_context = await _run_sync(
                github_client.get_relevant_code_context, search_terms
            )

        # Step 4: Oracle DB (optional)
        db_context = ""
        if cfg.oracle.host:
            oracle_client = OracleClient(cfg.oracle)
            connected = await _run_sync(oracle_client.connect)
            if connected:
                db_context = await _run_sync(
                    oracle_client.get_db_context_for_error, error_info.keywords
                )

        # Step 5: generate resolution
        resolution = await _run_sync(
            analyzer.generate_resolution,
            error_info,
            web_result.formatted,
            github_context,
            db_context,
        )

        lines = [
            f"## {error_info.error_type or 'Error'} Analysis",
            "",
            f"**Root Cause:** {resolution.root_cause}",
            "",
            "**Resolution Steps:**",
        ]
        for i, step in enumerate(resolution.resolution_steps, 1):
            lines.append(f"{i}. {step}")

        if resolution.code_references:
            lines += ["", "**Code References:**"]
            lines += [f"- `{r}`" for r in resolution.code_references]

        if resolution.prevention_tips:
            lines += ["", "**Prevention Tips:**"]
            lines += [f"- {t}" for t in resolution.prevention_tips]

        lines += ["", f"**Confidence:** {resolution.confidence.upper()}"]

        if web_result.results:
            lines += ["", "**Web Sources:**"]
            lines += [f"- {r.url}" for r in web_result.results[:3]]

        return [TextContent(type="text", text="\n".join(lines))]

    # ── search_github_code ─────────────────────────────────────────
    if name == "search_github_code":
        keywords: list[str] = arguments["keywords"]
        if not cfg.github.personal_access_token:
            return [TextContent(type="text", text="GITHUB_PAT not configured.")]
        github_client = GitHubMCPClient(cfg.github)
        context = await _run_sync(github_client.get_relevant_code_context, keywords)
        return [TextContent(type="text", text=context)]

    # ── query_error_logs ───────────────────────────────────────────
    if name == "query_error_logs":
        keywords: list[str] = arguments["keywords"]
        if not cfg.oracle.host:
            return [TextContent(type="text", text="ORACLE_HOST not configured.")]
        oracle_client = OracleClient(cfg.oracle)
        connected = await _run_sync(oracle_client.connect)
        if not connected:
            return [TextContent(type="text", text="Could not connect to Oracle DB.")]
        context = await _run_sync(oracle_client.get_db_context_for_error, keywords)
        return [TextContent(type="text", text=context)]

    # ── query_database ─────────────────────────────────────────────
    if name == "query_database":
        sql: str = arguments["sql"]
        params: dict = arguments.get("params", {})
        if not cfg.oracle.host:
            return [TextContent(type="text", text="ORACLE_HOST not configured.")]
        oracle_client = OracleClient(cfg.oracle)
        connected = await _run_sync(oracle_client.connect)
        if not connected:
            return [TextContent(type="text", text="Could not connect to Oracle DB.")]
        rows = await _run_sync(oracle_client.execute_diagnostic_query, sql, params)
        if not rows:
            return [TextContent(type="text", text="Query returned no rows.")]
        # Format as a readable table
        headers = list(rows[0].keys())
        lines = ["| " + " | ".join(headers) + " |"]
        lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
        for row in rows:
            lines.append("| " + " | ".join(str(row.get(h, "")) for h in headers) + " |")
        lines.append(f"\n_{len(rows)} row(s) returned._")
        return [TextContent(type="text", text="\n".join(lines))]

    return [TextContent(type="text", text=f"Unknown tool: {name}")]


# ------------------------------------------------------------------
# Entry point
# ------------------------------------------------------------------

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())
