-- Schema / DDL - ml_etl (Mercado Livre)
-- Todas as tabelas incluem JOB_RUN (DATETIME) para identificar a execução do ETL.

CREATE TABLE IF NOT EXISTS items (
    item_id             VARCHAR(20)     NOT NULL,
    job_run             TIMESTAMP       NOT NULL,
    seller_id           BIGINT          NOT NULL,
    title               TEXT            NOT NULL,
    price               NUMERIC(14,2),
    currency_id         VARCHAR(5),
    price_usd           NUMERIC(14,2),
    condition           VARCHAR(20),
    warranty            TEXT,
    has_warranty        BOOLEAN         NOT NULL DEFAULT FALSE,
    sold_quantity       INTEGER         NOT NULL DEFAULT 0,
    available_quantity  INTEGER         NOT NULL DEFAULT 0,
    listing_type_id     VARCHAR(30),
    free_shipping       BOOLEAN         NOT NULL DEFAULT FALSE,
    permalink           TEXT,
    PRIMARY KEY (item_id, job_run)
);

CREATE TABLE IF NOT EXISTS item_shipping_methods (
    id              SERIAL          PRIMARY KEY,
    item_id         VARCHAR(20)     NOT NULL,
    job_run         TIMESTAMP       NOT NULL,
    shipping_mode   VARCHAR(30)     NOT NULL,
    shipping_tag    VARCHAR(50)     NOT NULL,
    FOREIGN KEY (item_id, job_run) REFERENCES items (item_id, job_run)
);

CREATE TABLE IF NOT EXISTS currency_conversion (
    id                SERIAL          PRIMARY KEY,
    job_run           TIMESTAMP       NOT NULL,
    currency_from     VARCHAR(5)      NOT NULL,
    currency_to       VARCHAR(5)      NOT NULL,
    conversion_rate   NUMERIC(18,10)  NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_items_seller_id ON items (seller_id);
CREATE INDEX IF NOT EXISTS idx_items_job_run ON items (job_run);
CREATE INDEX IF NOT EXISTS idx_shipping_job_run ON item_shipping_methods (job_run);
