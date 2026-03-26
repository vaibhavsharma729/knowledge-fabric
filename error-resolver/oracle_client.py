"""
AWS RDS Oracle database client for querying error logs and schema information.

Connects to Oracle DB on AWS RDS using python-oracledb (thin mode — no Oracle
Instant Client required). Provides helpers to retrieve error logs, stack traces,
and relevant schema/table information to aid in error resolution.
"""
import logging
from contextlib import contextmanager
from typing import Optional

import oracledb

from config import OracleConfig

logger = logging.getLogger(__name__)

# Use thin mode — no Oracle client libraries required
oracledb.init_oracle_client = lambda **_: None  # ensure thin mode is used


class OracleClient:
    """Client for querying AWS RDS Oracle."""

    def __init__(self, config: OracleConfig):
        self.config = config
        self._pool: Optional[oracledb.ConnectionPool] = None

    def connect(self) -> bool:
        """
        Establish a connection pool to the Oracle database.
        Returns True on success, False on failure.
        """
        try:
            self._pool = oracledb.create_pool(
                user=self.config.username,
                password=self.config.password,
                dsn=self.config.dsn,
                min=1,
                max=5,
                increment=1,
            )
            # Verify connectivity with a test query
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1 FROM DUAL")
            logger.info("Oracle connection pool created successfully.")
            return True
        except Exception as e:
            logger.error("Oracle connection failed: %s", e)
            self._pool = None
            return False

    def close(self):
        """Close the connection pool."""
        if self._pool:
            self._pool.close()
            self._pool = None

    @contextmanager
    def _get_connection(self):
        if self._pool is None:
            raise RuntimeError("Not connected. Call connect() first.")
        conn = self._pool.acquire()
        try:
            yield conn
        finally:
            self._pool.release(conn)

    # ------------------------------------------------------------------
    # Error log queries
    # ------------------------------------------------------------------

    def get_recent_error_logs(
        self,
        error_code: Optional[str] = None,
        error_message_like: Optional[str] = None,
        limit: int = 20,
        log_table: str = "APP_ERROR_LOGS",
    ) -> list[dict]:
        """
        Query the application error log table for recent errors.

        Expects a table with columns: ERROR_ID, ERROR_CODE, ERROR_MESSAGE,
        STACK_TRACE, CREATED_AT, MODULE_NAME, USER_ID (adjust as needed).
        """
        if self._pool is None:
            return []

        where_clauses = []
        params = {}

        if error_code:
            where_clauses.append("ERROR_CODE = :error_code")
            params["error_code"] = error_code

        if error_message_like:
            where_clauses.append("UPPER(ERROR_MESSAGE) LIKE UPPER(:msg_like)")
            params["msg_like"] = f"%{error_message_like}%"

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        sql = f"""
            SELECT
                ERROR_ID,
                ERROR_CODE,
                ERROR_MESSAGE,
                STACK_TRACE,
                CREATED_AT,
                MODULE_NAME,
                USER_ID
            FROM {log_table}
            {where_sql}
            ORDER BY CREATED_AT DESC
            FETCH FIRST :limit ROWS ONLY
        """
        params["limit"] = limit

        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, params)
                    columns = [desc[0] for desc in cur.description]
                    return [dict(zip(columns, row)) for row in cur.fetchall()]
        except Exception as e:
            logger.error("Error querying error logs: %s", e)
            return []

    def get_table_schema(self, table_name: str, schema: Optional[str] = None) -> list[dict]:
        """
        Retrieve column definitions for a table from Oracle data dictionary.
        Useful for understanding DB schema context when resolving SQL errors.
        """
        if self._pool is None:
            return []

        params: dict = {"table_name": table_name.upper()}
        owner_filter = ""
        if schema:
            owner_filter = "AND OWNER = :owner"
            params["owner"] = schema.upper()

        sql = f"""
            SELECT
                COLUMN_NAME,
                DATA_TYPE,
                DATA_LENGTH,
                NULLABLE,
                DATA_DEFAULT
            FROM ALL_TAB_COLUMNS
            WHERE TABLE_NAME = :table_name
            {owner_filter}
            ORDER BY COLUMN_ID
        """

        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, params)
                    columns = [desc[0] for desc in cur.description]
                    return [dict(zip(columns, row)) for row in cur.fetchall()]
        except Exception as e:
            logger.error("Error fetching schema for %s: %s", table_name, e)
            return []

    def execute_diagnostic_query(self, sql: str, params: Optional[dict] = None) -> list[dict]:
        """
        Execute a read-only diagnostic SQL query.
        Only SELECT statements are permitted.
        """
        if self._pool is None:
            return []

        stripped = sql.strip().upper()
        if not stripped.startswith("SELECT") and not stripped.startswith("WITH"):
            raise ValueError("Only SELECT queries are allowed in diagnostic mode.")

        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, params or {})
                    columns = [desc[0] for desc in cur.description]
                    return [dict(zip(columns, row)) for row in cur.fetchall()]
        except Exception as e:
            logger.error("Diagnostic query failed: %s", e)
            return []

    def get_db_context_for_error(
        self, error_keywords: list[str], limit: int = 10
    ) -> str:
        """
        Retrieve error log entries related to the given keywords and format
        as a context string for the AI resolver.
        """
        if self._pool is None:
            return "Oracle database not connected."

        all_logs: list[dict] = []
        seen_ids: set = set()

        for keyword in error_keywords[:3]:
            logs = self.get_recent_error_logs(
                error_message_like=keyword, limit=limit
            )
            for log in logs:
                eid = log.get("ERROR_ID")
                if eid not in seen_ids:
                    seen_ids.add(eid)
                    all_logs.append(log)

        if not all_logs:
            return "No matching error records found in the database."

        lines = ["### Recent DB Error Logs\n"]
        for log in all_logs[:limit]:
            lines.append(
                f"- **ID**: {log.get('ERROR_ID')} | "
                f"**Code**: {log.get('ERROR_CODE')} | "
                f"**Module**: {log.get('MODULE_NAME')}\n"
                f"  **Message**: {log.get('ERROR_MESSAGE')}\n"
                f"  **Time**: {log.get('CREATED_AT')}\n"
            )
            stack = log.get("STACK_TRACE", "")
            if stack:
                lines.append(f"  **Stack Trace**:\n  ```\n  {stack[:500]}\n  ```\n")

        return "\n".join(lines)
