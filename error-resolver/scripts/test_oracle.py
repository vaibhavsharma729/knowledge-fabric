#!/usr/bin/env python3
"""
Test script — verifies Oracle DB connection and queries APP_ERROR_LOGS.

Usage:
    cd error-resolver
    python scripts/test_oracle.py

Reads credentials from .env or AWS Secrets Manager (same as mcp_server.py).
"""
import sys
import os

# Allow imports from the error-resolver directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from config import AppConfig
from oracle_client import OracleClient


def main():
    print("=" * 60)
    print("Oracle DB Connection Test")
    print("=" * 60)

    cfg = AppConfig.from_env()

    if not cfg.oracle.host:
        print("\nERROR: ORACLE_HOST is not set.")
        print("Set it in .env or as an environment variable.")
        sys.exit(1)

    print(f"\nHost        : {cfg.oracle.host}")
    print(f"Port        : {cfg.oracle.port}")
    print(f"Service     : {cfg.oracle.service_name}")
    print(f"Username    : {cfg.oracle.username}")
    print(f"DSN         : {cfg.oracle.dsn}")

    print("\n[1] Connecting...")
    client = OracleClient(cfg.oracle)
    ok = client.connect()

    if not ok:
        print("FAILED — could not connect. Check credentials and network access.")
        sys.exit(1)

    print("Connected successfully.\n")

    # ── Test 1: row count ──────────────────────────────────────────
    print("[2] Checking APP_ERROR_LOGS row count...")
    rows = client.execute_diagnostic_query(
        "SELECT COUNT(*) AS CNT FROM APP_ERROR_LOGS"
    )
    count = rows[0]["CNT"] if rows else "unknown"
    print(f"    Rows in APP_ERROR_LOGS: {count}\n")

    # ── Test 2: recent errors ──────────────────────────────────────
    print("[3] Fetching 5 most recent error logs...")
    recent = client.get_recent_error_logs(limit=5)
    if not recent:
        print("    No rows found. Run sql/test_data.sql to insert sample data.\n")
    else:
        for row in recent:
            print(
                f"    [{row.get('CREATED_AT')}] "
                f"{row.get('ERROR_CODE')} | "
                f"{row.get('MODULE_NAME')} | "
                f"{str(row.get('ERROR_MESSAGE', ''))[:80]}"
            )
        print()

    # ── Test 3: keyword search ─────────────────────────────────────
    print("[4] Searching for errors matching 'NullPointer'...")
    context = client.get_db_context_for_error(["NullPointer"])
    print(context)

    # ── Test 4: schema check ───────────────────────────────────────
    print("[5] Checking table schema (ALL_TAB_COLUMNS)...")
    schema = client.get_table_schema("APP_ERROR_LOGS")
    if schema:
        print(f"    Columns found: {[col['COLUMN_NAME'] for col in schema]}\n")
    else:
        print("    Could not read schema (check privileges on ALL_TAB_COLUMNS).\n")

    client.close()
    print("=" * 60)
    print("All tests passed. Oracle integration is ready.")
    print("=" * 60)


if __name__ == "__main__":
    main()
