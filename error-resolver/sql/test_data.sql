-- =============================================================
-- Error Resolver — Sample test data for APP_ERROR_LOGS
-- Run after setup.sql.
--
-- Usage:
--   sqlplus <user>/<password>@<host>:1521/<service> @test_data.sql
-- =============================================================

INSERT INTO APP_ERROR_LOGS (ERROR_CODE, ERROR_MESSAGE, STACK_TRACE, CREATED_AT, MODULE_NAME, USER_ID)
VALUES (
    'NPE-001',
    'NullPointerException: Cannot invoke "String.length()" because str is null',
    'java.lang.NullPointerException: Cannot invoke "String.length()" because "str" is null
    at com.example.UserService.processName(UserService.java:42)
    at com.example.UserController.handleRequest(UserController.java:87)
    at sun.reflect.NativeMethodAccessorImpl.invoke0(Native Method)',
    SYSTIMESTAMP - INTERVAL '2' HOUR,
    'UserService',
    'user_001'
);

INSERT INTO APP_ERROR_LOGS (ERROR_CODE, ERROR_MESSAGE, STACK_TRACE, CREATED_AT, MODULE_NAME, USER_ID)
VALUES (
    'DB-500',
    'ORA-00942: table or view does not exist',
    'java.sql.SQLException: ORA-00942: table or view does not exist
    at oracle.jdbc.driver.T4CTTIoer11.processError(T4CTTIoer11.java:509)
    at oracle.jdbc.driver.T4CTTIoer11.processError(T4CTTIoer11.java:461)
    at com.example.dao.ReportDAO.fetchSummary(ReportDAO.java:112)',
    SYSTIMESTAMP - INTERVAL '5' HOUR,
    'ReportDAO',
    'user_002'
);

INSERT INTO APP_ERROR_LOGS (ERROR_CODE, ERROR_MESSAGE, STACK_TRACE, CREATED_AT, MODULE_NAME, USER_ID)
VALUES (
    'AUTH-403',
    'AccessDeniedException: User does not have permission to access resource /api/admin/users',
    'org.springframework.security.access.AccessDeniedException: Access is denied
    at org.springframework.security.access.vote.AffirmativeBased.decide(AffirmativeBased.java:84)
    at com.example.security.AuthFilter.doFilter(AuthFilter.java:56)
    at com.example.api.AdminController.listUsers(AdminController.java:33)',
    SYSTIMESTAMP - INTERVAL '1' DAY,
    'AdminController',
    'user_003'
);

INSERT INTO APP_ERROR_LOGS (ERROR_CODE, ERROR_MESSAGE, STACK_TRACE, CREATED_AT, MODULE_NAME, USER_ID)
VALUES (
    'CONN-001',
    'Connection timeout: Unable to connect to database after 30000ms',
    'com.zaxxer.hikari.pool.HikariPool$PoolInitializationException: Failed to initialize pool
    at com.zaxxer.hikari.pool.HikariPool.checkFailFast(HikariPool.java:554)
    at com.example.config.DataSourceConfig.dataSource(DataSourceConfig.java:45)',
    SYSTIMESTAMP - INTERVAL '3' DAY,
    'DataSourceConfig',
    'system'
);

INSERT INTO APP_ERROR_LOGS (ERROR_CODE, ERROR_MESSAGE, STACK_TRACE, CREATED_AT, MODULE_NAME, USER_ID)
VALUES (
    'NPE-002',
    'NullPointerException: Cannot read field "customerId" because order is null',
    'java.lang.NullPointerException: Cannot read field "customerId" because "order" is null
    at com.example.OrderService.processPayment(OrderService.java:98)
    at com.example.PaymentController.checkout(PaymentController.java:61)',
    SYSTIMESTAMP - INTERVAL '6' HOUR,
    'OrderService',
    'user_004'
);

INSERT INTO APP_ERROR_LOGS (ERROR_CODE, ERROR_MESSAGE, STACK_TRACE, CREATED_AT, MODULE_NAME, USER_ID)
VALUES (
    'IO-001',
    'FileNotFoundException: No such file or directory: /data/reports/monthly_summary.csv',
    'java.io.FileNotFoundException: /data/reports/monthly_summary.csv (No such file or directory)
    at java.io.FileInputStream.open0(Native Method)
    at com.example.report.ReportExporter.exportCSV(ReportExporter.java:77)',
    SYSTIMESTAMP - INTERVAL '12' HOUR,
    'ReportExporter',
    'user_005'
);

INSERT INTO APP_ERROR_LOGS (ERROR_CODE, ERROR_MESSAGE, STACK_TRACE, CREATED_AT, MODULE_NAME, USER_ID)
VALUES (
    'OOM-001',
    'OutOfMemoryError: Java heap space — failed to allocate 512MB for image processing',
    'java.lang.OutOfMemoryError: Java heap space
    at java.util.Arrays.copyOf(Arrays.java:3236)
    at com.example.image.ImageProcessor.resizeBatch(ImageProcessor.java:203)
    at com.example.api.UploadController.handleBatchUpload(UploadController.java:55)',
    SYSTIMESTAMP - INTERVAL '2' DAY,
    'ImageProcessor',
    'user_006'
);

INSERT INTO APP_ERROR_LOGS (ERROR_CODE, ERROR_MESSAGE, STACK_TRACE, CREATED_AT, MODULE_NAME, USER_ID)
VALUES (
    'HTTP-500',
    'Internal Server Error: Unexpected exception in payment gateway integration',
    'org.springframework.web.util.NestedServletException: Request processing failed
    at com.example.payment.StripeGateway.charge(StripeGateway.java:88)
    at com.example.service.PaymentService.processCard(PaymentService.java:134)',
    SYSTIMESTAMP - INTERVAL '4' HOUR,
    'PaymentService',
    'user_007'
);

COMMIT;

SELECT COUNT(*) AS ROWS_INSERTED FROM APP_ERROR_LOGS;
