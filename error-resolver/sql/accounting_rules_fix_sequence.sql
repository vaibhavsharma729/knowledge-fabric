-- =============================================================
-- FIX: Reset sequence to current max OBJECT_ID + 1
--
-- This is the resolution the AI model should identify and suggest.
-- Run this after the duplicate key errors start appearing.
--
-- Replace 1008 below with the result of STEP 1's SEQUENCE_SHOULD_START_AT.
-- =============================================================

-- STEP 1: Check the gap (run this first to get the correct START WITH value)
SELECT
    s.LAST_NUMBER                 AS SEQUENCE_CURRENT,
    MAX(r.OBJECT_ID)              AS MAX_OBJECT_ID,
    MAX(r.OBJECT_ID) + 1         AS SEQUENCE_SHOULD_START_AT
FROM ACCOUNTING_RULES r, USER_SEQUENCES s
WHERE s.SEQUENCE_NAME = 'ACCOUNTING_RULES_SEQ'
GROUP BY s.LAST_NUMBER;

-- STEP 2: Drop the out-of-sync sequence
DROP SEQUENCE ACCOUNTING_RULES_SEQ;

-- STEP 3: Recreate starting from max OBJECT_ID + 1
-- Update START WITH based on SEQUENCE_SHOULD_START_AT from STEP 1
CREATE SEQUENCE ACCOUNTING_RULES_SEQ
    START WITH 1008
    INCREMENT BY 1
    NOCACHE
    NOCYCLE;

-- STEP 4: Verify the fix — new inserts should now work
SELECT 'Sequence reset. Next value:' AS STATUS, ACCOUNTING_RULES_SEQ.NEXTVAL AS NEXT_ID FROM DUAL;
