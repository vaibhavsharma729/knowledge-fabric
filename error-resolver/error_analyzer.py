"""
Core error analysis engine using GitHub Copilot (GitHub Models API).

Pipeline:
  1. Extract structured error info from text or screenshot (gpt-4o vision).
  2. Derive smarter repository search terms informed by the extracted error.
  3. Synthesise web knowledge + repository code + DB logs into a step-by-step fix.

Endpoint: https://models.inference.ai.azure.com
Docs:     https://docs.github.com/en/github-models
"""
import base64
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from openai import OpenAI

from config import CopilotConfig

logger = logging.getLogger(__name__)


@dataclass
class ErrorInfo:
    """Structured error information extracted from the raw input."""

    error_type: str = ""
    error_code: str = ""
    error_message: str = ""
    stack_trace: str = ""
    file_path: str = ""
    line_number: str = ""
    keywords: list[str] = field(default_factory=list)
    raw_text: str = ""


@dataclass
class ResolutionResult:
    """Full resolution output returned to the UI."""

    error_info: ErrorInfo
    root_cause: str = ""
    resolution_steps: list[str] = field(default_factory=list)
    code_references: list[str] = field(default_factory=list)
    prevention_tips: list[str] = field(default_factory=list)
    web_sources: list[str] = field(default_factory=list)
    confidence: str = "medium"  # low / medium / high


class ErrorAnalyzer:
    """
    Analyses errors using GitHub Copilot via the GitHub Models API.

    The client is an OpenAI-compatible SDK instance pointed at the GitHub
    Models endpoint and authenticated with your GitHub PAT.
    """

    def __init__(self, config: CopilotConfig):
        self.config = config
        self._client = OpenAI(
            base_url=config.endpoint,
            api_key=config.github_token,
        )

    # ------------------------------------------------------------------
    # Step 1 — Extract error info
    # ------------------------------------------------------------------

    def extract_error_info_from_text(self, error_text: str) -> ErrorInfo:
        """Extract structured error details from raw error text."""
        prompt = _EXTRACT_PROMPT.format(error_text=error_text)
        response_text = self._chat([{"role": "user", "content": prompt}])
        return _parse_error_info(response_text, raw_text=error_text)

    def extract_error_info_from_image(
        self, image_bytes: bytes, media_type: str = "image/png"
    ) -> ErrorInfo:
        """
        Extract error details from a screenshot using gpt-4o vision.
        The image is base64-encoded and sent as a multimodal message.
        """
        image_b64 = base64.standard_b64encode(image_bytes).decode("utf-8")
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{media_type};base64,{image_b64}",
                            "detail": "high",
                        },
                    },
                    {"type": "text", "text": _EXTRACT_PROMPT_IMAGE},
                ],
            }
        ]
        response_text = self._chat(messages)
        return _parse_error_info(
            response_text, raw_text=f"[Screenshot — {media_type}]"
        )

    # ------------------------------------------------------------------
    # Step 2 — Derive smarter repo search terms from error info
    # ------------------------------------------------------------------

    def derive_repo_search_terms(self, error_info: ErrorInfo, web_context: str = "") -> list[str]:
        """
        Ask Copilot to suggest targeted search terms for the codebase.

        Web context (if available) enriches this — e.g. the web may reveal
        that ORA-00942 is a missing table, so the terms would be table names
        and the SQL query, not just "ORA-00942".
        """
        prompt = _SEARCH_TERMS_PROMPT.format(
            error_type=error_info.error_type,
            error_code=error_info.error_code,
            error_message=error_info.error_message,
            stack_trace=error_info.stack_trace or "N/A",
            web_context=web_context or "Not available.",
        )
        response_text = self._chat([{"role": "user", "content": prompt}])
        try:
            data = _extract_json(response_text)
            return data.get("search_terms", error_info.keywords)
        except Exception:
            return error_info.keywords

    # ------------------------------------------------------------------
    # Step 3 — Generate resolution
    # ------------------------------------------------------------------

    def generate_resolution(
        self,
        error_info: ErrorInfo,
        web_context: str = "",
        github_context: str = "",
        db_context: str = "",
    ) -> ResolutionResult:
        """
        Generate step-by-step resolution.

        Resolution is grounded in this priority order:
          1. Web knowledge (what the error is, established fixes)
          2. Repository code (where it occurs in *this* codebase)
          3. DB error logs (historical occurrences in *this* environment)
        """
        prompt = _RESOLUTION_PROMPT.format(
            error_type=error_info.error_type,
            error_code=error_info.error_code,
            error_message=error_info.error_message,
            stack_trace=error_info.stack_trace or "N/A",
            file_path=error_info.file_path or "N/A",
            line_number=error_info.line_number or "N/A",
            web_context=web_context or "Not available.",
            github_context=github_context or "No repository code context available.",
            db_context=db_context or "No database context available.",
        )
        response_text = self._chat([{"role": "user", "content": prompt}])
        return _parse_resolution(response_text, error_info)

    # ------------------------------------------------------------------
    # GitHub Copilot (GitHub Models API) invocation
    # ------------------------------------------------------------------

    def _chat(self, messages: list[dict]) -> str:
        """Call the GitHub Models API via the OpenAI-compatible client."""
        try:
            response = self._client.chat.completions.create(
                model=self.config.model,
                messages=messages,
                max_tokens=4096,
                temperature=0.2,
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            logger.error("GitHub Copilot API call failed: %s", e)
            return f"Error: GitHub Copilot API call failed — {e}"


# ------------------------------------------------------------------
# Prompts
# ------------------------------------------------------------------

_EXTRACT_PROMPT = """\
You are an expert software engineer. Analyze the following error and extract structured information.

ERROR INPUT:
{error_text}

Respond with a JSON object (and nothing else) in this exact format:
{{
  "error_type": "<e.g. NullPointerException, ORA-01017, ImportError, etc.>",
  "error_code": "<numeric or string error code if present, else empty string>",
  "error_message": "<the core error message, 1-2 sentences>",
  "stack_trace": "<the stack trace if present, else empty string>",
  "file_path": "<source file path if mentioned, else empty string>",
  "line_number": "<line number if mentioned, else empty string>",
  "keywords": ["<3-6 short keywords useful for searching the codebase>"]
}}
"""

_EXTRACT_PROMPT_IMAGE = """\
You are an expert software engineer. The image shows an error message or error screen.

Carefully read all text visible in the image and extract the error information.

Respond with a JSON object (and nothing else) in this exact format:
{
  "error_type": "<e.g. NullPointerException, ORA-01017, ImportError, etc.>",
  "error_code": "<numeric or string error code if present, else empty string>",
  "error_message": "<the core error message, 1-2 sentences>",
  "stack_trace": "<the stack trace if visible in the image, else empty string>",
  "file_path": "<source file path if visible, else empty string>",
  "line_number": "<line number if visible, else empty string>",
  "keywords": ["<3-6 short keywords useful for searching the codebase>"]
}
"""

_SEARCH_TERMS_PROMPT = """\
You are a senior developer. Based on the error details and web research below, suggest the \
best search terms to find the relevant code in the application's GitHub repository.

## Error
- Type: {error_type}
- Code: {error_code}
- Message: {error_message}
- Stack Trace: {stack_trace}

## Web Research (what we know about this error)
{web_context}

Generate 4-8 specific search terms that a developer would use to find the exact code \
responsible for this error — e.g. function names, class names, SQL table names, config keys, \
exception class names, specific string literals from the stack trace, etc.

Respond with a JSON object (and nothing else):
{{
  "search_terms": ["<term1>", "<term2>", ...]
}}
"""

_RESOLUTION_PROMPT = """\
You are a senior software engineer and database administrator providing a step-by-step fix \
for an error. You have three sources of context — use them in this order of priority:

  1. **Web knowledge** — what is known about this error globally (authoritative)
  2. **Repository code** — where and how the error manifests in THIS specific codebase
  3. **Database logs** — historical occurrences in THIS specific environment

## Error Details
- **Type**: {error_type}
- **Code**: {error_code}
- **Message**: {error_message}
- **Stack Trace**:
{stack_trace}
- **File**: {file_path} (line {line_number})

## Web Research (global knowledge about this error)
{web_context}

## Repository Code (from GitHub — the actual application code)
{github_context}

## Database Logs (from Oracle RDS)
{db_context}

---

Using ALL of the above, provide:

1. **Root Cause** — explain exactly why this error occurs, combining global knowledge with \
what you can see in the repository code (2-4 sentences).
2. **Resolution Steps** — numbered, specific, actionable steps referencing actual file names, \
function names, SQL statements, or config values found in the repository code where possible.
3. **Code References** — exact files, functions, or DB objects in the repository that need \
to be changed or inspected.
4. **Prevention Tips** — 2-3 tips specific to this codebase to prevent recurrence.
5. **Web Sources** — list the URLs from the web research that were most relevant.
6. **Confidence** — low, medium, or high.

Respond with a JSON object (and nothing else):
{{
  "root_cause": "<explanation>",
  "resolution_steps": ["<step 1>", "<step 2>", ...],
  "code_references": ["<file or function>", ...],
  "prevention_tips": ["<tip>", ...],
  "web_sources": ["<url>", ...],
  "confidence": "low|medium|high"
}}
"""


# ------------------------------------------------------------------
# Response parsers
# ------------------------------------------------------------------

def _parse_error_info(response_text: str, raw_text: str = "") -> ErrorInfo:
    try:
        data = _extract_json(response_text)
        return ErrorInfo(
            error_type=data.get("error_type", "Unknown"),
            error_code=data.get("error_code", ""),
            error_message=data.get("error_message", ""),
            stack_trace=data.get("stack_trace", ""),
            file_path=data.get("file_path", ""),
            line_number=data.get("line_number", ""),
            keywords=data.get("keywords", []),
            raw_text=raw_text,
        )
    except Exception as e:
        logger.warning("Failed to parse error info JSON: %s", e)
        return ErrorInfo(
            error_type="Unknown",
            error_message=raw_text[:500],
            raw_text=raw_text,
            keywords=_simple_keywords(raw_text),
        )


def _parse_resolution(response_text: str, error_info: ErrorInfo) -> ResolutionResult:
    try:
        data = _extract_json(response_text)
        return ResolutionResult(
            error_info=error_info,
            root_cause=data.get("root_cause", ""),
            resolution_steps=data.get("resolution_steps", []),
            code_references=data.get("code_references", []),
            prevention_tips=data.get("prevention_tips", []),
            web_sources=data.get("web_sources", []),
            confidence=data.get("confidence", "medium"),
        )
    except Exception as e:
        logger.warning("Failed to parse resolution JSON: %s", e)
        return ResolutionResult(
            error_info=error_info,
            root_cause="Unable to parse resolution.",
            resolution_steps=[response_text],
        )


def _extract_json(text: str) -> dict:
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        return json.loads(match.group(1))
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        return json.loads(match.group(0))
    raise ValueError("No JSON object found in response")


def _simple_keywords(text: str) -> list[str]:
    words = re.findall(r"\b[A-Za-z][A-Za-z0-9_]{3,}\b", text)
    seen: set[str] = set()
    result: list[str] = []
    for w in words:
        lw = w.lower()
        if lw not in seen and lw not in {"error", "exception", "line", "file", "traceback"}:
            seen.add(lw)
            result.append(w)
        if len(result) >= 5:
            break
    return result
