"""
Camada de LOAD: grava os dados já transformados no PostgreSQL.
As credenciais de conexão vêm de variáveis de ambiente (config.DB_CONFIG),
nunca hard-coded.
"""
import logging
import psycopg2
from psycopg2.extras import execute_values
import config
logger = logging.getLogger(__name__)
def get_connection():
    return psycopg2.connect(
        host=config.DB_CONFIG["host"],
        port=config.DB_CONFIG["port"],
        dbname=config.DB_CONFIG["dbname"],
        user=config.DB_CONFIG["user"],
        password=config.DB_CONFIG["password"],
    )
def load_items(conn, items: list[dict]) -> None:
    if not items:
        logger.info("Nenhum item para carregar em `items`.")
        return
    columns = [
        "item_id", "job_run", "seller_id", "title", "price", "currency_id",
        "price_usd", "condition", "warranty", "has_warranty", "sold_quantity",
        "available_quantity", "listing_type_id", "free_shipping", "permalink",
    ]
    values = [[row[c] for c in columns] for row in items]
    query = f"""
        INSERT INTO items ({", ".join(columns)})
        VALUES %s
        ON CONFLICT (item_id, job_run) DO NOTHING;
    """
    with conn.cursor() as cur:
        execute_values(cur, query, values)
    logger.info("Carregados %d registros em `items`.", len(items))
def load_shipping_methods(conn, rows: list[dict]) -> None:
    if not rows:
        logger.info("Nenhum registro para carregar em `item_shipping_methods`.")
        return
    columns = ["item_id", "job_run", "shipping_mode", "shipping_tag"]
    values = [[row[c] for c in columns] for row in rows]
    query = f"""
        INSERT INTO item_shipping_methods ({", ".join(columns)})
        VALUES %s;
    """
    with conn.cursor() as cur:
        execute_values(cur, query, values)
    logger.info("Carregados %d registros em `item_shipping_methods`.", len(rows))
def load_currency_conversion(conn, row: dict) -> None:
    columns = ["job_run", "currency_from", "currency_to", "conversion_rate"]
    values = [[row[c] for c in columns]]
    query = f"""
        INSERT INTO currency_conversion ({", ".join(columns)})
        VALUES %s;
    """
    with conn.cursor() as cur:
        execute_values(cur, query, values)
    logger.info("Taxa de câmbio registrada: %s -> %s = %s", row["currency_from"], row["currency_to"], row["conversion_rate"])
