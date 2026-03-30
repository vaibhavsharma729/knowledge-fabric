"""
Run the Order Data Processor.

This script:
  1. Connects to Oracle (optional — errors still print if Oracle is unavailable)
  2. Processes orders.csv — validates each row
  3. Logs real errors to APP_ERROR_LOGS in Oracle
  4. Prints a summary report

After running, open GitHub Copilot Chat in VS Code and ask:
  "Query the error logs and help me fix the data processing errors"

The MCP server will query APP_ERROR_LOGS and return AI-generated fixes
based on the actual errors that just occurred.

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
from sample_app.data_processor import OrderProcessor


def main():
    print("=" * 50)
    print("  Order Data Processor")
    print("=" * 50)

    cfg = AppConfig.from_env()

    # ── Connect to Oracle (optional) ──────────────────────────────
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
            print("[DB] Could not connect — errors will print only (not logged to DB)")
    else:
        print("\n[DB] ORACLE_HOST not set — skipping DB logging.")
        print("[DB] Set ORACLE_HOST in .env to enable error logging to Oracle.\n")

    # ── Process orders ─────────────────────────────────────────────
    processor = OrderProcessor(error_logger=error_logger)
    result = processor.process_csv()
    processor.print_summary(result)

    # ── Prompt user to use Copilot Chat ───────────────────────────
    if result.failed_rows and oracle_client:
        print("Errors logged to Oracle APP_ERROR_LOGS.")
        print("\nNow open GitHub Copilot Chat in VS Code and ask:")
        print('  "Query the error logs and help me fix the order processing errors"\n')
    elif result.failed_rows:
        print(f"{len(result.failed_rows)} errors found (not logged — Oracle not connected).")
        print("\nTo log errors to Oracle, set ORACLE_HOST in .env and re-run.\n")

    # ── Cleanup ────────────────────────────────────────────────────
    if oracle_client:
        oracle_client.close()


if __name__ == "__main__":
    main()
