--********************************************************************
-- DB2 TABLE DEFINITIONS FOR INVESTMENT PORTFOLIO MANAGEMENT SYSTEM
-- VERSION: 1.0
-- DATE: 2024
--********************************************************************

--====================================================================
-- PORTFOLIO MASTER TABLE
--====================================================================
CREATE TABLE PORTFOLIO_MASTER (
    PORTFOLIO_ID      CHAR(8)         NOT NULL,
    ACCOUNT_TYPE      CHAR(2)         NOT NULL,
    BRANCH_ID         CHAR(2)         NOT NULL,
    CLIENT_ID         CHAR(10)        NOT NULL,
    PORTFOLIO_NAME    VARCHAR(50)     NOT NULL,
    CURRENCY_CODE     CHAR(3)         NOT NULL,
    RISK_LEVEL        CHAR(1)         NOT NULL,
    STATUS            CHAR(1)         NOT NULL,
    OPEN_DATE         DATE            NOT NULL,
    CLOSE_DATE        DATE,
    LAST_MAINT_DATE   TIMESTAMP       NOT NULL,
    LAST_MAINT_USER   VARCHAR(8)      NOT NULL,
    PRIMARY KEY (PORTFOLIO_ID)
);

--====================================================================
-- INVESTMENT POSITIONS TABLE
--====================================================================
CREATE TABLE INVESTMENT_POSITIONS (
    PORTFOLIO_ID      CHAR(8)         NOT NULL,
    INVESTMENT_ID     CHAR(10)        NOT NULL,
    POSITION_DATE     DATE            NOT NULL,
    QUANTITY          DECIMAL(18,4)   NOT NULL,
    COST_BASIS        DECIMAL(18,2)   NOT NULL,
    MARKET_VALUE      DECIMAL(18,2)   NOT NULL,
    CURRENCY_CODE     CHAR(3)         NOT NULL,
    LAST_MAINT_DATE   TIMESTAMP       NOT NULL,
    LAST_MAINT_USER   VARCHAR(8)      NOT NULL,
    PRIMARY KEY (PORTFOLIO_ID, INVESTMENT_ID, POSITION_DATE),
    FOREIGN KEY (PORTFOLIO_ID) REFERENCES PORTFOLIO_MASTER(PORTFOLIO_ID)
);

--====================================================================
-- TRANSACTION HISTORY TABLE
--====================================================================
CREATE TABLE TRANSACTION_HISTORY (
    TRANSACTION_ID    CHAR(20)        NOT NULL,
    PORTFOLIO_ID      CHAR(8)         NOT NULL,
    TRANSACTION_DATE  DATE            NOT NULL,
    TRANSACTION_TIME  TIME            NOT NULL,
    INVESTMENT_ID     CHAR(10)        NOT NULL,
    TRANSACTION_TYPE  CHAR(2)         NOT NULL,
    QUANTITY          DECIMAL(18,4)   NOT NULL,
    PRICE            DECIMAL(18,4)   NOT NULL,
    AMOUNT           DECIMAL(18,2)   NOT NULL,
    CURRENCY_CODE    CHAR(3)         NOT NULL,
    STATUS           CHAR(1)         NOT NULL,
    PROCESS_DATE     TIMESTAMP       NOT NULL,
    PROCESS_USER     VARCHAR(8)      NOT NULL,
    PRIMARY KEY (TRANSACTION_ID),
    FOREIGN KEY (PORTFOLIO_ID) REFERENCES PORTFOLIO_MASTER(PORTFOLIO_ID)
);

--====================================================================
-- INDEXES
--====================================================================
CREATE INDEX IDX_PORT_MASTER_CLIENT 
    ON PORTFOLIO_MASTER (CLIENT_ID, STATUS);

CREATE INDEX IDX_POSITIONS_DATE 
    ON INVESTMENT_POSITIONS (POSITION_DATE, PORTFOLIO_ID);

CREATE INDEX IDX_TRANS_HIST_PORT 
    ON TRANSACTION_HISTORY (PORTFOLIO_ID, TRANSACTION_DATE);

CREATE INDEX IDX_TRANS_HIST_DATE 
    ON TRANSACTION_HISTORY (TRANSACTION_DATE, PORTFOLIO_ID);

--====================================================================
-- VIEWS
--====================================================================
CREATE VIEW ACTIVE_PORTFOLIOS AS
    SELECT *
    FROM PORTFOLIO_MASTER
    WHERE STATUS = 'A'
    AND (CLOSE_DATE IS NULL OR CLOSE_DATE > CURRENT DATE);

CREATE VIEW CURRENT_POSITIONS AS
    SELECT p.*, pm.PORTFOLIO_NAME, pm.CLIENT_ID
    FROM INVESTMENT_POSITIONS p
    JOIN PORTFOLIO_MASTER pm ON p.PORTFOLIO_ID = pm.PORTFOLIO_ID
    WHERE p.POSITION_DATE = CURRENT DATE - 1 DAY;

--====================================================================
-- NOTES:
--====================================================================
-- 1. All tables include audit fields (LAST_MAINT_DATE, LAST_MAINT_USER)
-- 2. TRANSACTION_ID format: YYYYMMDDHHMMSS + 6-digit sequence
-- 3. Status codes:
--    - Portfolio: 'A'=Active, 'C'=Closed, 'S'=Suspended
--    - Transaction: 'P'=Processed, 'F'=Failed, 'R'=Reversed
-- 4. Transaction types:
--    - 'BU'=Buy, 'SL'=Sell, 'TR'=Transfer, 'FE'=Fee
-- 5. Indexes optimized for common query patterns
--******************************************************************** 