"""
Configuration management.

Sensitive values (passwords, tokens) are never read from plain text files.
They are resolved in this priority order:

  1. AWS Secrets Manager  — set AWS_SECRET_ORACLE / AWS_SECRET_GITHUB env vars
                            to point to your secrets (no password in any file)
  2. OS environment variables — export in your shell profile (~/.bashrc etc.)
                                 never written to disk as a project file
  3. Sidebar input at runtime  — entered directly in the Streamlit UI

Non-sensitive values (hostnames, region, model name) can still go in .env.
"""
import os
from dataclasses import dataclass

from secrets import resolve


@dataclass
class GitHubConfig:
    personal_access_token: str
    default_repo_owner: str
    default_repo_name: str

    @classmethod
    def from_env(cls) -> "GitHubConfig":
        secret_name = os.environ.get("AWS_SECRET_GITHUB", "")
        return cls(
            # PAT resolved from Secrets Manager ("pat" key) or env var
            personal_access_token=resolve(secret_name, "pat", "GITHUB_PAT"),
            default_repo_owner=os.environ.get("GITHUB_REPO_OWNER", ""),
            default_repo_name=os.environ.get("GITHUB_REPO_NAME", ""),
        )


@dataclass
class OracleConfig:
    host: str
    port: int
    service_name: str
    username: str
    password: str

    @classmethod
    def from_env(cls) -> "OracleConfig":
        secret_name = os.environ.get("AWS_SECRET_ORACLE", "")
        return cls(
            host=os.environ.get("ORACLE_HOST", ""),
            port=int(os.environ.get("ORACLE_PORT", "1521")),
            service_name=os.environ.get("ORACLE_SERVICE_NAME", ""),
            # Username and password resolved from Secrets Manager or env vars
            username=resolve(secret_name, "username", "ORACLE_USERNAME"),
            password=resolve(secret_name, "password", "ORACLE_PASSWORD"),
        )

    @property
    def dsn(self) -> str:
        return f"{self.host}:{self.port}/{self.service_name}"


@dataclass
class CopilotConfig:
    """
    GitHub Copilot configuration using the GitHub Models API.

    The GitHub Models API is OpenAI-compatible and is accessed with your
    GitHub Personal Access Token (same PAT used for GitHub MCP server access).

    Endpoint: https://models.inference.ai.azure.com
    Docs:     https://docs.github.com/en/github-models
    """

    github_token: str
    model: str
    endpoint: str

    @classmethod
    def from_env(cls) -> "CopilotConfig":
        secret_name = os.environ.get("AWS_SECRET_GITHUB", "")
        return cls(
            github_token=resolve(secret_name, "pat", "GITHUB_PAT"),
            model=os.environ.get("COPILOT_MODEL", "gpt-4o"),
            endpoint=os.environ.get(
                "COPILOT_ENDPOINT", "https://models.inference.ai.azure.com"
            ),
        )


@dataclass
class AppConfig:
    github: GitHubConfig
    oracle: OracleConfig
    copilot: CopilotConfig
    tavily_api_key: str = ""

    @classmethod
    def from_env(cls) -> "AppConfig":
        secret_name = os.environ.get("AWS_SECRET_TAVILY", "")
        return cls(
            github=GitHubConfig.from_env(),
            oracle=OracleConfig.from_env(),
            copilot=CopilotConfig.from_env(),
            tavily_api_key=resolve(secret_name, "api_key", "TAVILY_API_KEY"),
        )
