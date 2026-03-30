"""
Error Logger — writes application errors to Oracle APP_ERROR_LOGS table.

This is the bridge between your application code and the Error Resolver MCP tool.
When your app catches an exception, call log_error() to store it in Oracle.
The MCP server will then query these real logs when resolving errors in Copilot Chat.
"""
import sys
import os
import traceback
import logging
from datetime import datetime
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger(__name__)


class ErrorLogger:
    """Logs application errors to Oracle APP_ERROR_LOGS."""

    def __init__(self, oracle_client):
        self._oracle = oracle_client

    def log_error(
        self,
        error: Exception,
        error_code: str,
        module_name: str,
        user_id: str = "system",
        extra_context: Optional[str] = None,
    ) -> bool:
        """
        Write an exception to APP_ERROR_LOGS.
        Returns True if logged successfully.
        """
        if not self._oracle._pool:
            logger.warning("Oracle not connected — error not logged to DB.")
            return False

        error_message = str(error)
        if extra_context:
            error_message = f"{error_message} | Context: {extra_context}"

        stack = "".join(traceback.format_exception(type(error), error, error.__traceback__))

        sql = """
            INSERT INTO APP_ERROR_LOGS
                (ERROR_CODE, ERROR_MESSAGE, STACK_TRACE, CREATED_AT, MODULE_NAME, USER_ID)
            VALUES
                (:error_code, :error_message, :stack_trace, :created_at, :module_name, :user_id)
        """
        params = {
            "error_code": error_code[:50],
            "error_message": error_message[:4000],
            "stack_trace": stack[:10000],
            "created_at": datetime.utcnow(),
            "module_name": module_name[:200],
            "user_id": user_id[:100],
        }

        try:
            with self._oracle._get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, params)
                conn.commit()
            logger.info("Logged error [%s] to APP_ERROR_LOGS", error_code)
            return True
        except Exception as e:
            logger.error("Failed to log error to Oracle: %s", e)
            return False
