"""
Reset the demo database to the broken migration state.

Called automatically by demo.sh before each test run.
Ensures the sequence is always just before the conflicting IDs,
so the app fails with ORA-00001 on every run until the fix is deployed.

The "fix" is running this SQL once against the DB:
    DROP SEQUENCE ACCOUNTING_RULES_SEQ;
    CREATE SEQUENCE ACCOUNTING_RULES_SEQ START WITH <max_object_id + 1> ...;
After that, run.py directly (not demo.sh) to confirm success.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from config import AppConfig
from oracle_client import OracleClient

# IDs inserted by the "broken migration script" -- always conflict with sequence
MIGRATED_RECORDS = [
    (6, "RULE-006M", "Budget Allocation Rule - MIGRATED",     "ACC-006", "migration_script"),
    (7, "RULE-007M", "Cost Centre Rule - MIGRATED",           "ACC-007", "migration_script"),
    (8, "RULE-008M", "Intercompany Settlement Rule - MIGRATED","ACC-008", "migration_script"),
]


def reset(oracle_client):
    print("[RESET] Restoring broken migration state...")

    with oracle_client._get_connection() as conn:
        with conn.cursor() as cur:

            # 1. Clear the table
            cur.execute("DELETE FROM ACCOUNTING_RULES")

            # 2. Drop and recreate sequence starting at 1
            try:
                cur.execute("DROP SEQUENCE ACCOUNTING_RULES_SEQ")
            except Exception:
                pass
            cur.execute(
                """CREATE SEQUENCE ACCOUNTING_RULES_SEQ
                   START WITH 1 INCREMENT BY 1 NOCACHE NOCYCLE"""
            )

            # 3. Insert original pre-migration records using the sequence (IDs 1-5)
            original = [
                ("RULE-001", "General Ledger Rule",       "ACC-001"),
                ("RULE-002", "Accounts Payable Rule",     "ACC-002"),
                ("RULE-003", "Accounts Receivable Rule",  "ACC-003"),
                ("RULE-004", "Payroll Processing Rule",   "ACC-004"),
                ("RULE-005", "Tax Computation Rule",      "ACC-005"),
            ]
            for code, desc, acc in original:
                cur.execute(
                    """INSERT INTO ACCOUNTING_RULES
                       (OBJECT_ID, RULE_CODE, RULE_DESCRIPTION, ACCOUNT_ID, CREATED_BY)
                       VALUES (ACCOUNTING_RULES_SEQ.NEXTVAL, :c, :d, :a, 'system')""",
                    {"c": code, "d": desc, "a": acc},
                )

            # 4. Manually insert the "missed" migration records at IDs 6, 7, 8
            #    Sequence is NOT updated -- this is the bug
            for obj_id, code, desc, acc, by in MIGRATED_RECORDS:
                cur.execute(
                    """INSERT INTO ACCOUNTING_RULES
                       (OBJECT_ID, RULE_CODE, RULE_DESCRIPTION, ACCOUNT_ID, CREATED_BY)
                       VALUES (:id, :c, :d, :a, :b)""",
                    {"id": obj_id, "c": code, "d": desc, "a": acc, "b": by},
                )

        conn.commit()

    print("[RESET] Done. Sequence at 6, migrated records at 6/7/8 -- conflict ready.")
    print("[RESET] Next sequence value will collide with migration records.")


def main():
    cfg = AppConfig.from_env()
    if not cfg.oracle.host:
        print("ERROR: ORACLE_HOST not set in .env")
        sys.exit(1)

    client = OracleClient(cfg.oracle)
    if not client.connect():
        print("ERROR: Could not connect to Oracle")
        sys.exit(1)

    reset(client)
    client.close()


if __name__ == "__main__":
    main()
