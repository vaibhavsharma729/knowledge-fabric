"""
AWS Secrets Manager helper.

Fetches secrets at runtime so no passwords are stored in files or env vars.
Credentials are stored once in Secrets Manager and retrieved via IAM role —
no username/password needed in .env, code, or version control.

Setup (one-time, done in AWS Console or CLI):
    aws secretsmanager create-secret \
        --name error-resolver/oracle \
        --secret-string '{"username":"app_user","password":"s3cr3t"}'

    aws secretsmanager create-secret \
        --name error-resolver/github \
        --secret-string '{"pat":"ghp_xxxx"}'

IAM policy required on the role running this app:
    {
        "Effect": "Allow",
        "Action": "secretsmanager:GetSecretValue",
        "Resource": "arn:aws:secretsmanager:<region>:<account>:secret:error-resolver/*"
    }
"""
import json
import logging
import os
from functools import lru_cache
from typing import Optional

logger = logging.getLogger(__name__)

_AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")


@lru_cache(maxsize=32)
def get_secret(secret_name: str) -> dict:
    """
    Fetch a JSON secret from AWS Secrets Manager.

    Results are cached in-process so the API is only called once per secret
    per application lifetime.

    Returns an empty dict if the secret cannot be fetched (logs the error).
    """
    try:
        import boto3
        from botocore.config import Config

        client = boto3.client(
            "secretsmanager",
            region_name=_AWS_REGION,
            config=Config(connect_timeout=3, read_timeout=3, retries={"max_attempts": 1}),
        )
        response = client.get_secret_value(SecretId=secret_name)
        raw = response.get("SecretString", "{}")
        return json.loads(raw)
    except Exception as e:
        logger.warning("Could not fetch secret '%s': %s", secret_name, e)
        return {}


def resolve(
    secret_name: Optional[str],
    secret_key: str,
    env_var: str,
    default: str = "",
) -> str:
    """
    Resolve a sensitive value using this priority order:

      1. AWS Secrets Manager  — if SECRET_NAME env var points to a secret
      2. OS environment variable — set in shell profile, never written to a file
      3. Default value (usually empty string)

    Args:
        secret_name: Name of the Secrets Manager secret (may be None/empty).
        secret_key:  Key inside the JSON secret object, e.g. "password".
        env_var:     Fallback OS environment variable name, e.g. "ORACLE_PASSWORD".
        default:     Value of last resort.
    """
    # 1. Try Secrets Manager
    if secret_name:
        secret_data = get_secret(secret_name)
        value = secret_data.get(secret_key, "")
        if value:
            return value

    # 2. Try OS environment variable
    return os.environ.get(env_var, default)
