"""
Core error analysis engine using AWS Bedrock (Claude multimodal).

Accepts error text or a screenshot image, extracts error details,
enriches context from GitHub and Oracle, and returns step-by-step resolution.
"""
import base64
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Optional

import boto3

from config import BedrockConfig

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
    db_references: list[str] = field(default_factory=list)
    prevention_tips: list[str] = field(default_factory=list)
    confidence: str = "medium"  # low / medium / high


class ErrorAnalyzer:
    """
    Analyzes errors using AWS Bedrock Claude.

    Supports both text input and image (screenshot) input via
    Claude's multimodal capabilities.
    """

    def __init__(self, config: BedrockConfig):
        self.config = config
        self._client = boto3.client(
            service_name="bedrock-runtime",
            region_name=config.region,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract_error_info_from_text(self, error_text: str) -> ErrorInfo:
        """
        Use Claude to extract structured error details from raw error text.
        """
        prompt = _EXTRACT_PROMPT.format(error_text=error_text)
        response_text = self._invoke_text(prompt)
        return _parse_error_info(response_text, raw_text=error_text)

    def extract_error_info_from_image(self, image_bytes: bytes, media_type: str = "image/png") -> ErrorInfo:
        """
        Use Claude's vision capability to extract error details from a screenshot.
        """
        prompt = _EXTRACT_PROMPT_IMAGE
        response_text = self._invoke_with_image(prompt, image_bytes, media_type)
        return _parse_error_info(response_text, raw_text=f"[Image input - {media_type}]")

    def generate_resolution(
        self,
        error_info: ErrorInfo,
        github_context: str = "",
        db_context: str = "",
    ) -> ResolutionResult:
        """
        Generate step-by-step resolution steps given error info and optional
        code/DB context retrieved from GitHub and Oracle.
        """
        prompt = _RESOLUTION_PROMPT.format(
            error_type=error_info.error_type,
            error_code=error_info.error_code,
            error_message=error_info.error_message,
            stack_trace=error_info.stack_trace or "N/A",
            file_path=error_info.file_path or "N/A",
            line_number=error_info.line_number or "N/A",
            github_context=github_context or "No GitHub code context available.",
            db_context=db_context or "No database context available.",
        )

        response_text = self._invoke_text(prompt)
        return _parse_resolution(response_text, error_info)

    def analyze(
        self,
        text_input: Optional[str] = None,
        image_bytes: Optional[bytes] = None,
        image_media_type: str = "image/png",
        github_context: str = "",
        db_context: str = "",
    ) -> ResolutionResult:
        """
        End-to-end analysis: extract error info then generate resolution.

        Accepts either text or image input (image takes precedence if both given).
        """
        if image_bytes:
            error_info = self.extract_error_info_from_image(image_bytes, image_media_type)
        elif text_input:
            error_info = self.extract_error_info_from_text(text_input)
        else:
            raise ValueError("Either text_input or image_bytes must be provided.")

        return self.generate_resolution(
            error_info=error_info,
            github_context=github_context,
            db_context=db_context,
        )

    # ------------------------------------------------------------------
    # Bedrock invocation helpers
    # ------------------------------------------------------------------

    def _invoke_text(self, prompt: str) -> str:
        """Invoke Claude on Bedrock with a text-only prompt."""
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 4096,
            "messages": [{"role": "user", "content": prompt}],
        }
        return self._invoke(body)

    def _invoke_with_image(self, prompt: str, image_bytes: bytes, media_type: str) -> str:
        """Invoke Claude on Bedrock with an image + text prompt."""
        image_b64 = base64.standard_b64encode(image_bytes).decode("utf-8")
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 4096,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": image_b64,
                            },
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
        }
        return self._invoke(body)

    def _invoke(self, body: dict) -> str:
        try:
            response = self._client.invoke_model(
                modelId=self.config.model_id,
                body=json.dumps(body),
                contentType="application/json",
                accept="application/json",
            )
            result = json.loads(response["body"].read())
            return result["content"][0]["text"]
        except Exception as e:
            logger.error("Bedrock invocation failed: %s", e)
            return f"Error: Bedrock invocation failed — {e}"


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

_RESOLUTION_PROMPT = """\
You are a senior software engineer and database administrator. Your job is to diagnose \
and resolve the following error with clear, actionable steps.

## Error Details
- **Type**: {error_type}
- **Code**: {error_code}
- **Message**: {error_message}
- **Stack Trace**:
{stack_trace}
- **File**: {file_path} (line {line_number})

## Relevant Source Code (from GitHub)
{github_context}

## Relevant Database Logs (from Oracle RDS)
{db_context}

---

Based on all the above context, provide:

1. **Root Cause** — A concise explanation of why this error occurs (2-4 sentences).
2. **Resolution Steps** — A numbered list of exact steps to fix the error. Be specific: include \
file names, SQL statements, config changes, or commands where applicable.
3. **Code References** — List any specific files, functions, or DB objects the developer \
should inspect or modify.
4. **Prevention Tips** — 2-3 tips to prevent this error in future.
5. **Confidence** — Your confidence level: low, medium, or high.

Respond with a JSON object (and nothing else) in this exact format:
{{
  "root_cause": "<explanation>",
  "resolution_steps": ["<step 1>", "<step 2>", ...],
  "code_references": ["<file or function>", ...],
  "prevention_tips": ["<tip 1>", "<tip 2>", ...],
  "confidence": "low|medium|high"
}}
"""


# ------------------------------------------------------------------
# Response parsers
# ------------------------------------------------------------------

def _parse_error_info(response_text: str, raw_text: str = "") -> ErrorInfo:
    """Parse Claude's JSON response into an ErrorInfo object."""
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
        # Fallback: treat the whole input as the message
        return ErrorInfo(
            error_type="Unknown",
            error_message=raw_text[:500],
            raw_text=raw_text,
            keywords=_simple_keywords(raw_text),
        )


def _parse_resolution(response_text: str, error_info: ErrorInfo) -> ResolutionResult:
    """Parse Claude's JSON resolution response into a ResolutionResult."""
    try:
        data = _extract_json(response_text)
        return ResolutionResult(
            error_info=error_info,
            root_cause=data.get("root_cause", ""),
            resolution_steps=data.get("resolution_steps", []),
            code_references=data.get("code_references", []),
            prevention_tips=data.get("prevention_tips", []),
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
    """Extract a JSON object from text that may contain markdown fences."""
    # Strip markdown code fences if present
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        return json.loads(match.group(1))
    # Try raw JSON object
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        return json.loads(match.group(0))
    raise ValueError("No JSON object found in response")


def _simple_keywords(text: str) -> list[str]:
    """Extract a few keywords from error text as a fallback."""
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
