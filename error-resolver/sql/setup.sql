-- =============================================================
-- Error Resolver — APP_ERROR_LOGS table setup
-- Run this once against your Oracle RDS instance.
--
-- Usage (SQL*Plus or SQLcl):
--   sqlplus <user>/<password>@<host>:1521/<service> @setup.sql
-- =============================================================

-- Drop if already exists (comment out if you want to preserve data)
BEGIN
    EXECUTE IMMEDIATE 'DROP TABLE APP_ERROR_LOGS';
EXCEPTION
    WHEN OTHERS THEN
        IF SQLCODE != -942 THEN RAISE; END IF;
END;
/

-- Create the table
CREATE TABLE APP_ERROR_LOGS (
    ERROR_ID        NUMBER          GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ERROR_CODE      VARCHAR2(50),
    ERROR_MESSAGE   VARCHAR2(4000)  NOT NULL,
    STACK_TRACE     CLOB,
    CREATED_AT      TIMESTAMP       DEFAULT SYSTIMESTAMP NOT NULL,
    MODULE_NAME     VARCHAR2(200),
    USER_ID         VARCHAR2(100)
);

-- Index for fast keyword searches on ERROR_MESSAGE
CREATE INDEX IDX_APP_ERR_MSG  ON APP_ERROR_LOGS (UPPER(ERROR_MESSAGE));
CREATE INDEX IDX_APP_ERR_CODE ON APP_ERROR_LOGS (ERROR_CODE);
CREATE INDEX IDX_APP_ERR_TIME ON APP_ERROR_LOGS (CREATED_AT DESC);

COMMIT;

SELECT 'APP_ERROR_LOGS table created successfully.' AS STATUS FROM DUAL;
