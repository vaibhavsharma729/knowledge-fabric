"""
Run the Accounting Rules Processor.

This script simulates what happens when users try to add new records
after a database migration that left the sequence out of sync with
the actual max OBJECT_ID in the table.

What happens:
  - Users try to insert new accounting rules
  - Oracle generates the next sequence value (e.g. 6, 7, 8...)
  - Those IDs already exist in the table (inserted manually during migration)
  - ORA-00001: unique constraint violated
  - Error is logged to APP_ERROR_LOGS in Oracle

After running, open GitHub Copilot Chat in VS Code and ask:
  "Query the error logs and tell me the root cause and fix"

The MCP server reads the real error from Oracle and the actual app code
from GitHub, then the AI identifies the sequence sync issue and suggests
the exact SQL to fix it.

Usage:
    cd error-resolver
    python sample_app/run.py
"""
import sys
import os
import logging

logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from config import AppConfig
from oracle_client import OracleClient
from sample_app.error_logger import ErrorLogger
from sample_app.accounting_rules_processor import AccountingRulesProcessor


def main():
    print("=" * 50)
    print("  Accounting Rules Processor")
    print("=" * 50)

    cfg = AppConfig.from_env()

    # ── Connect to Oracle ──────────────────────────────────────────
    oracle_client = None
    error_logger = None

    if cfg.oracle.host:
        print("\n[DB] Connecting to Oracle...")
        oracle_client = OracleClient(cfg.oracle)
        connected = oracle_client.connect()
        if connected:
            print("[DB] Connected — errors will be logged to APP_ERROR_LOGS")
            error_logger = ErrorLogger(oracle_client)
        else:
            print("[DB] Could not connect — check ORACLE_HOST / credentials in .env")
            sys.exit(1)
    else:
        print("\n[DB] ORACLE_HOST not set in .env — cannot run.")
        print("[DB] Set ORACLE_HOST, ORACLE_SERVICE_NAME, and credentials, then re-run.")
        sys.exit(1)

    # ── Run the processor ──────────────────────────────────────────
    processor = AccountingRulesProcessor(
        oracle_client=oracle_client,
        error_logger=error_logger,
    )
    result = processor.process_all()

    # ── Summary ────────────────────────────────────────────────────
    print(f"\n{'=' * 50}")
    if result["failed"] > 0:
        print(f"  {result['failed']} errors logged to APP_ERROR_LOGS in Oracle.")
        print()
        print("  Now open GitHub Copilot Chat in VS Code and ask:")
        print('  "Query the error logs and tell me the root cause and fix"')
        print()
        print("  The AI will:")
        print("  1. Read the real errors from APP_ERROR_LOGS")
        print("  2. Read AccountingRulesProcessor code from GitHub")
        print("  3. Identify the sequence sync issue")
        print("  4. Suggest the exact SQL to fix it")
    else:
        print("  All rules inserted successfully.")
    print(f"{'=' * 50}\n")

    if oracle_client:
        oracle_client.close()


if __name__ == "__main__":
    main()
