#!/bin/bash
# demo.sh
#
# Resets the DB to the broken migration state, then runs the processor.
# Always fails with ORA-00001 until the sequence is fixed in Oracle.
#
# Usage:
#   cd error-resolver
#   bash sample_app/demo.sh
#
# To deploy the fix, run this SQL in DBeaver:
#   SELECT MAX(OBJECT_ID) + 1 AS START_WITH FROM ACCOUNTING_RULES;
#   DROP SEQUENCE ACCOUNTING_RULES_SEQ;
#   CREATE SEQUENCE ACCOUNTING_RULES_SEQ START WITH <START_WITH> INCREMENT BY 1 NOCACHE NOCYCLE;
#
# Then run the app directly (without the reset):
#   python sample_app/run.py

set -e
cd "$(dirname "$0")/.."

echo "========================================"
echo "  Resetting demo state..."
echo "========================================"
python sample_app/reset_demo.py

echo ""
echo "========================================"
echo "  Running Accounting Rules Processor..."
echo "========================================"
python sample_app/run.py
