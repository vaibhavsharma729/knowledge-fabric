-- =============================================================
-- Error Resolver — APP_ERROR_LOGS table setup
-- Run this once against your Oracle RDS instance.
--
-- Run each statement individually in DBeaver / RDS Query Editor,
-- or use SQL*Plus / SQLcl to run the whole file at once:
--   sqlplus <user>/<password>@<host>:1521/<service> @setup.sql
--
-- If the table already exists, run the DROP first (step 0),
-- otherwise skip it and start from step 1.
-- =============================================================

-- STEP 0: Drop existing table (skip if first-time setup)
-- DROP TABLE APP_ERROR_LOGS;

-- STEP 1: Create the table
CREATE TABLE APP_ERROR_LOGS (
    ERROR_ID        NUMBER          GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ERROR_CODE      VARCHAR2(50),
    ERROR_MESSAGE   VARCHAR2(4000)  NOT NULL,
    STACK_TRACE     CLOB,
    CREATED_AT      TIMESTAMP       DEFAULT SYSTIMESTAMP NOT NULL,
    MODULE_NAME     VARCHAR2(200),
    USER_ID         VARCHAR2(100)
);

-- STEP 2: Create indexes for fast searches
CREATE INDEX IDX_APP_ERR_MSG  ON APP_ERROR_LOGS (UPPER(ERROR_MESSAGE));
CREATE INDEX IDX_APP_ERR_CODE ON APP_ERROR_LOGS (ERROR_CODE);
CREATE INDEX IDX_APP_ERR_TIME ON APP_ERROR_LOGS (CREATED_AT DESC);

-- STEP 3: Verify
SELECT 'APP_ERROR_LOGS created successfully.' AS STATUS FROM DUAL;
