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
class BedrockConfig:
    region: str
    model_id: str

    @classmethod
    def from_env(cls) -> "BedrockConfig":
        return cls(
            region=os.environ.get("AWS_REGION", "us-east-1"),
            model_id=os.environ.get(
                "BEDROCK_MODEL_ID", "anthropic.claude-3-5-sonnet-20241022-v2:0"
            ),
        )


@dataclass
class AppConfig:
    github: GitHubConfig
    oracle: OracleConfig
    bedrock: BedrockConfig

    @classmethod
    def from_env(cls) -> "AppConfig":
        return cls(
            github=GitHubConfig.from_env(),
            oracle=OracleConfig.from_env(),
            bedrock=BedrockConfig.from_env(),
        )
