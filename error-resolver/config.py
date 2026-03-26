"""
Configuration management via environment variables.
Copy .env.example to .env and fill in your values.
"""
import os
from dataclasses import dataclass


@dataclass
class GitHubConfig:
    personal_access_token: str
    default_repo_owner: str
    default_repo_name: str

    @classmethod
    def from_env(cls) -> "GitHubConfig":
        return cls(
            personal_access_token=os.environ.get("GITHUB_PAT", ""),
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
        return cls(
            host=os.environ.get("ORACLE_HOST", ""),
            port=int(os.environ.get("ORACLE_PORT", "1521")),
            service_name=os.environ.get("ORACLE_SERVICE_NAME", ""),
            username=os.environ.get("ORACLE_USERNAME", ""),
            password=os.environ.get("ORACLE_PASSWORD", ""),
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
    Docs: https://docs.github.com/en/github-models
    """

    github_token: str
    # gpt-4o supports vision (screenshot analysis); swap for gpt-4o-mini to reduce cost
    model: str
    endpoint: str

    @classmethod
    def from_env(cls) -> "CopilotConfig":
        return cls(
            github_token=os.environ.get("GITHUB_PAT", ""),
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
    tavily_api_key: str = ""  # Optional — DuckDuckGo is used when blank

    @classmethod
    def from_env(cls) -> "AppConfig":
        return cls(
            github=GitHubConfig.from_env(),
            oracle=OracleConfig.from_env(),
            copilot=CopilotConfig.from_env(),
            tavily_api_key=os.environ.get("TAVILY_API_KEY", ""),
        )
