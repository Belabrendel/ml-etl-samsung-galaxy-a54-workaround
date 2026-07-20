"""
Camada de TRANSFORMAÇÃO: recebe os dados brutos vindos da API (extract.py)
e devolve estruturas já modeladas, prontas para carga no banco de dados.
Modela 3 conjuntos de dados:
- items                 -> um registro por anúncio
- item_shipping_methods -> um registro por método de envio de cada anúncio
- currency_conversion   -> snapshot da taxa de câmbio usada nesta execução
"""
from datetime import datetime, timezone
def _has_warranty(warranty_field) -> bool:
    if warranty_field is None:
        return False
    text = str(warranty_field).strip().lower()
    if text in ("", "no", "sin garantía", "sin garantia", "none"):
        return False
    return True
def transform_item(raw_item: dict, job_run: datetime, conversion_rate: float, target_currency: str) -> dict:
    """Transforma um item detalhado (vindo de /items) na linha da tabela `items`."""
    price = raw_item.get("price")
    currency_id = raw_item.get("currency_id")
    if currency_id == target_currency:
        price_usd = price
    elif price is not None and conversion_rate:
        price_usd = round(price * conversion_rate, 2)
    else:
        price_usd = None
    shipping = raw_item.get("shipping", {}) or {}
    return {
        "item_id": raw_item.get("id"),
        "job_run": job_run,
        "seller_id": raw_item.get("seller_id"),
        "title": raw_item.get("title"),
        "price": price,
        "currency_id": currency_id,
        "price_usd": price_usd,
        "condition": raw_item.get("condition"),
        "warranty": raw_item.get("warranty"),
        "has_warranty": _has_warranty(raw_item.get("warranty")),
        "sold_quantity": raw_item.get("sold_quantity", 0),
        "available_quantity": raw_item.get("available_quantity", 0),
        "listing_type_id": raw_item.get("listing_type_id"),
        "free_shipping": shipping.get("free_shipping", False),
        "permalink": raw_item.get("permalink"),
    }
def transform_shipping_methods(raw_item: dict, job_run: datetime) -> list[dict]:
    """
    Um item pode oferecer mais de um método/tag de envio.
    Gera uma linha por combinação (item, shipping_mode, tag).
    """
    shipping = raw_item.get("shipping", {}) or {}
    item_id = raw_item.get("id")
    mode = shipping.get("logistic_type") or shipping.get("mode") or "not_specified"
    tags = shipping.get("tags") or ["not_specified"]
    rows = []
    for tag in tags:
        rows.append({
            "item_id": item_id,
            "job_run": job_run,
            "shipping_mode": mode,
            "shipping_tag": tag,
        })
    return rows
def transform_currency_conversion(job_run: datetime, from_currency: str, to_currency: str, rate: float) -> dict:
    return {
        "job_run": job_run,
        "currency_from": from_currency,
        "currency_to": to_currency,
        "conversion_rate": rate,
    }
def new_job_run() -> datetime:
    """Timestamp único (UTC) para identificar todos os registros desta execução do ETL."""
    return datetime.now(timezone.utc).replace(microsecond=0)
