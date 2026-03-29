"""
AWS RDS Oracle database client for querying error logs and schema information.

Connects to Oracle DB on AWS RDS using python-oracledb (thin mode — no Oracle
Instant Client required).
"""
import logging
from contextlib import contextmanager
from typing import Optional

import oracledb

from config import OracleConfig

logger = logging.getLogger(__name__)

oracledb.init_oracle_client = lambda **_: None  # thin mode — no Instant Client needed

_MAX_SEARCH_KEYWORDS = 3  # keep searches within API rate limits


class OracleClient:
    """Client for querying AWS RDS Oracle."""

    def __init__(self, config: OracleConfig):
        self.config = config
        self._pool: Optional[oracledb.ConnectionPool] = None

    def connect(self) -> bool:
        """Establish a connection pool. Returns True on success."""
        try:
            self._pool = oracledb.create_pool(
                user=self.config.username,
                password=self.config.password,
                dsn=self.config.dsn,
                min=0,
                max=5,
                increment=1,
                timeout=5,
            )
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

    @staticmethod
    def _cursor_to_dicts(cur) -> list[dict]:
        """Convert cursor rows to a list of column-name-keyed dicts."""
        columns = [desc[0] for desc in cur.description]
        return [dict(zip(columns, row)) for row in cur.fetchall()]

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
        Query APP_ERROR_LOGS for recent errors.

        Expected columns: ERROR_ID, ERROR_CODE, ERROR_MESSAGE, STACK_TRACE,
        CREATED_AT, MODULE_NAME, USER_ID — adjust table name as needed.
        """
        if self._pool is None:
            return []

        where_clauses = []
        params: dict = {}

        if error_code:
            where_clauses.append("ERROR_CODE = :error_code")
            params["error_code"] = error_code

        if error_message_like:
            where_clauses.append("UPPER(ERROR_MESSAGE) LIKE UPPER(:msg_like)")
            params["msg_like"] = f"%{error_message_like}%"

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
        sql = f"""
            SELECT ERROR_ID, ERROR_CODE, ERROR_MESSAGE, STACK_TRACE,
                   CREATED_AT, MODULE_NAME, USER_ID
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
                    return self._cursor_to_dicts(cur)
        except Exception as e:
            logger.error("Error querying error logs: %s", e)
            return []

    def get_table_schema(self, table_name: str, schema: Optional[str] = None) -> list[dict]:
        """Retrieve column definitions from the Oracle data dictionary."""
        if self._pool is None:
            return []

        params: dict = {"table_name": table_name.upper()}
        owner_filter = ""
        if schema:
            owner_filter = "AND OWNER = :owner"
            params["owner"] = schema.upper()

        sql = f"""
            SELECT COLUMN_NAME, DATA_TYPE, DATA_LENGTH, NULLABLE, DATA_DEFAULT
            FROM ALL_TAB_COLUMNS
            WHERE TABLE_NAME = :table_name {owner_filter}
            ORDER BY COLUMN_ID
        """

        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, params)
                    return self._cursor_to_dicts(cur)
        except Exception as e:
            logger.error("Error fetching schema for %s: %s", table_name, e)
            return []

    def execute_diagnostic_query(self, sql: str, params: Optional[dict] = None) -> list[dict]:
        """Execute a read-only SELECT query for diagnostics."""
        if self._pool is None:
            return []

        stripped = sql.strip().upper()
        if not stripped.startswith("SELECT") and not stripped.startswith("WITH"):
            raise ValueError("Only SELECT queries are allowed in diagnostic mode.")

        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, params or {})
                    return self._cursor_to_dicts(cur)
        except Exception as e:
            logger.error("Diagnostic query failed: %s", e)
            return []

    def get_db_context_for_error(
        self, error_keywords: list[str], limit: int = 10
    ) -> str:
        """
        Fetch error log rows matching any of the keywords in a single query,
        then format as a markdown context string for the AI prompt.
        """
        if self._pool is None:
            return "Oracle database not connected."

        keywords = error_keywords[:_MAX_SEARCH_KEYWORDS]
        if not keywords:
            return "No keywords provided."

        # Single batched query with OR clauses instead of N separate queries
        or_clauses = " OR ".join(
            f"UPPER(ERROR_MESSAGE) LIKE UPPER(:kw{i})" for i in range(len(keywords))
        )
        params: dict = {f"kw{i}": f"%{kw}%" for i, kw in enumerate(keywords)}
        params["limit"] = limit

        sql = f"""
            SELECT ERROR_ID, ERROR_CODE, ERROR_MESSAGE, STACK_TRACE,
                   CREATED_AT, MODULE_NAME, USER_ID
            FROM APP_ERROR_LOGS
            WHERE {or_clauses}
            ORDER BY CREATED_AT DESC
            FETCH FIRST :limit ROWS ONLY
        """

        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, params)
                    logs = self._cursor_to_dicts(cur)
        except Exception as e:
            logger.error("Error querying error logs: %s", e)
            return "Database query failed."

        if not logs:
            return "No matching error records found in the database."

        lines = ["### Recent DB Error Logs\n"]
        for log in logs:
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
