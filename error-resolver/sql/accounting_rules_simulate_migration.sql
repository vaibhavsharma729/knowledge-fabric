-- =============================================================
-- Simulate the broken database migration
--
-- Recreates the exact issue:
--   1. Insert original records using the sequence (on-premises state)
--   2. Simulate migration: manually insert missed records with
--      OBJECT_ID = current_max + 1000 (but sequence NOT updated)
--   3. Sequence is now behind the actual max OBJECT_ID
--      → next INSERT generates a duplicate OBJECT_ID → ORA-00001
--
-- Run each statement separately in DBeaver (Ctrl+Enter)
-- =============================================================

-- STEP 1: Insert original pre-migration records
--         Sequence generates OBJECT_IDs 1, 2, 3, 4, 5
INSERT INTO ACCOUNTING_RULES (OBJECT_ID, RULE_CODE, RULE_DESCRIPTION, ACCOUNT_ID, CREATED_BY)
VALUES (ACCOUNTING_RULES_SEQ.NEXTVAL, 'RULE-001', 'General Ledger Rule', 'ACC-001', 'system');

INSERT INTO ACCOUNTING_RULES (OBJECT_ID, RULE_CODE, RULE_DESCRIPTION, ACCOUNT_ID, CREATED_BY)
VALUES (ACCOUNTING_RULES_SEQ.NEXTVAL, 'RULE-002', 'Accounts Payable Rule', 'ACC-002', 'system');

INSERT INTO ACCOUNTING_RULES (OBJECT_ID, RULE_CODE, RULE_DESCRIPTION, ACCOUNT_ID, CREATED_BY)
VALUES (ACCOUNTING_RULES_SEQ.NEXTVAL, 'RULE-003', 'Accounts Receivable Rule', 'ACC-003', 'system');

INSERT INTO ACCOUNTING_RULES (OBJECT_ID, RULE_CODE, RULE_DESCRIPTION, ACCOUNT_ID, CREATED_BY)
VALUES (ACCOUNTING_RULES_SEQ.NEXTVAL, 'RULE-004', 'Payroll Processing Rule', 'ACC-004', 'system');

INSERT INTO ACCOUNTING_RULES (OBJECT_ID, RULE_CODE, RULE_DESCRIPTION, ACCOUNT_ID, CREATED_BY)
VALUES (ACCOUNTING_RULES_SEQ.NEXTVAL, 'RULE-005', 'Tax Computation Rule', 'ACC-005', 'system');

COMMIT;

-- Verify: sequence = 5, max OBJECT_ID = 5 (in sync — healthy state)
SELECT LAST_NUMBER AS SEQUENCE_CURRENT FROM USER_SEQUENCES WHERE SEQUENCE_NAME = 'ACCOUNTING_RULES_SEQ';
SELECT MAX(OBJECT_ID) AS MAX_OBJECT_ID FROM ACCOUNTING_RULES;


-- STEP 2: Simulate the bad migration
-- Missed records manually inserted with OBJECT_ID = max + 1000
-- Sequence is NOT updated — this is the root cause of the bug
INSERT INTO ACCOUNTING_RULES (OBJECT_ID, RULE_CODE, RULE_DESCRIPTION, ACCOUNT_ID, CREATED_BY)
VALUES (1005, 'RULE-006', 'Budget Allocation Rule - MIGRATED', 'ACC-006', 'migration_script');

INSERT INTO ACCOUNTING_RULES (OBJECT_ID, RULE_CODE, RULE_DESCRIPTION, ACCOUNT_ID, CREATED_BY)
VALUES (1006, 'RULE-007', 'Cost Centre Rule - MIGRATED', 'ACC-007', 'migration_script');

INSERT INTO ACCOUNTING_RULES (OBJECT_ID, RULE_CODE, RULE_DESCRIPTION, ACCOUNT_ID, CREATED_BY)
VALUES (1007, 'RULE-008', 'Intercompany Settlement Rule - MIGRATED', 'ACC-008', 'migration_script');

COMMIT;

-- Verify the gap: sequence stuck at 5, max OBJECT_ID jumped to 1007 (OUT OF SYNC)
-- Sequence will next generate 6, 7, 8 ... eventually reach 1005, 1006, 1007
-- which already exist → ORA-00001 unique constraint violation
SELECT LAST_NUMBER AS SEQUENCE_STUCK_AT FROM USER_SEQUENCES WHERE SEQUENCE_NAME = 'ACCOUNTING_RULES_SEQ';
SELECT MAX(OBJECT_ID) AS MAX_OBJECT_ID_JUMPED_TO FROM ACCOUNTING_RULES;
