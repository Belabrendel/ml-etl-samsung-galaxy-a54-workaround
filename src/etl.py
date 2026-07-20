"""
Orquestra o processo completo de ETL:

1. EXTRACT  -> tenta paginar o /search; se indisponível, usa lista seed de
               item_ids. Busca detalhes via /items; se também indisponível,
               usa dataset fixture local. Consulta a taxa de câmbio via
               /currency_conversions.
2. TRANSFORM-> aplica as regras de negócio (moeda, garantia, shipping, JOB_RUN).
3. LOAD     -> grava tudo no PostgreSQL.

Este módulo é o ponto de entrada usado por main.py.

Ver README (seção "Desafios encontrados") para o diagnóstico completo do
motivo pelo qual os fallbacks abaixo foram necessários.
"""
import logging
import sys

import requests
import config
from src import extract, transform, load

logging.basicConfig(
    level=getattr(logging, config.LOGGING["level"]),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[
        logging.FileHandler(config.LOGGING["log_file"]),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)


def run() -> None:
    job_run = transform.new_job_run()
    logger.info("Iniciando ETL | JOB_RUN=%s", job_run.isoformat())

    # 1) EXTRACT - paginação do search (50 registros por página, conforme desafio)
    #    Fallback para lista seed caso o endpoint público esteja indisponível.
    logger.info("Buscando anúncios para: '%s'", config.ETL["search_query"])
    try:
        search_results = list(
            extract.paginate_search(
                query=config.ETL["search_query"],
                condition=config.ETL["condition"],
                page_size=config.ETL["page_size"],
                max_total_records=config.ETL["max_total_records"],
            )
        )
        item_ids = [r["id"] for r in search_results if r.get("id")]
        if not item_ids:
            raise extract.MercadoLibreAPIError("Busca via /search retornou vazio.")
    except (requests.exceptions.HTTPError, extract.MercadoLibreAPIError) as e:
        logger.warning(
            "Endpoint /search indisponível para esta aplicação (%s). "
            "Utilizando lista seed de item_ids como estratégia alternativa.", e
        )
        item_ids = extract.get_seed_item_ids()

    logger.info("Total de anúncios a processar: %d", len(item_ids))

    if not item_ids:
        logger.warning("Nenhum item encontrado. Encerrando execução.")
        return

    # 2) EXTRACT - detalhe completo de cada item (multiget em lotes)
    #    Fallback para dataset fixture caso /items também esteja indisponível.
    logger.info("Buscando detalhes completos dos itens...")
    raw_items = extract.get_items_details(item_ids)
    if not raw_items:
        logger.warning(
            "Endpoint /items indisponível para esta aplicação (acesso de produção "
            "não liberado). Utilizando dataset fixture local como estratégia alternativa."
        )
        raw_items = extract.get_fixture_items()

    # Garantia extra: manter apenas produtos novos (regra do desafio)
    raw_items = [i for i in raw_items if i.get("condition") == config.ETL["condition"]]
    logger.info("Itens novos após filtro de condição: %d", len(raw_items))

    # 3) EXTRACT - taxa de câmbio ARS -> USD desta execução
    logger.info("Consultando taxa de câmbio %s -> %s", config.ETL["source_currency"], config.ETL["target_currency"])
    conversion_rate = extract.get_currency_conversion(
        from_currency=config.ETL["source_currency"],
        to_currency=config.ETL["target_currency"],
    )
    logger.info("Taxa de câmbio obtida: %s", conversion_rate)

    # 4) TRANSFORM
    items_rows = [
        transform.transform_item(raw, job_run, conversion_rate, config.ETL["target_currency"])
        for raw in raw_items
    ]
    shipping_rows = []
    for raw in raw_items:
        shipping_rows.extend(transform.transform_shipping_methods(raw, job_run))

    conversion_row = transform.transform_currency_conversion(
        job_run, config.ETL["source_currency"], config.ETL["target_currency"], conversion_rate
    )

    # 5) LOAD
    conn = load.get_connection()
    try:
        load.load_items(conn, items_rows)
        load.load_shipping_methods(conn, shipping_rows)
        load.load_currency_conversion(conn, conversion_row)
        conn.commit()
        logger.info("ETL finalizado com sucesso. JOB_RUN=%s", job_run.isoformat())
    except Exception:
        conn.rollback()
        logger.exception("Erro durante a carga no banco de dados. Rollback aplicado.")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    run()
