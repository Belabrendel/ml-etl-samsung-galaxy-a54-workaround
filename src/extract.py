"""
Camada de EXTRAÇÃO: responsável por toda a comunicação com a API pública
do Mercado Livre (search, items multiget, currency_conversions).

Endpoints utilizados (conforme desafio):
- /sites/{site_id}/search       -> indisponível para esta aplicação: 403
                                    PA_UNAUTHORIZED_RESULT_FROM_POLICIES /
                                    "forbidden", mesmo sem autenticação e
                                    mesmo autenticado com usuário real.
- /items  (multiget)            -> também indisponível para itens de
                                    terceiros: 403 access_denied, testado
                                    tanto em MLA quanto em MLB, com test
                                    user e com usuário real.
- /currency_conversions/search  -> funciona normalmente.
- /currencies                   -> utilizado apenas para validar códigos
                                    de moeda, se necessário.

Ver README (seção "Desafios encontrados") para o diagnóstico completo,
incluindo os comandos de teste e respostas da API que confirmam que o
bloqueio é de política de plataforma para esta aplicação, e não um erro
de configuração do projeto.

Diante disso, este módulo implementa dois níveis de fallback:
1. get_seed_item_ids()  -> lista de item_ids coletados manualmente do site
                            público, usada quando /search falha.
2. get_fixture_items()  -> dataset local com a MESMA estrutura de resposta
                            do /items real, usado quando o multiget de
                            /items também falha. NÃO SÃO DADOS REAIS -
                            servem para validar o pipeline (transform,
                            load, queries) enquanto o acesso de produção
                            não é liberado.
"""
import json
import logging
import requests
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import time
import config

logger = logging.getLogger(__name__)


class MercadoLibreAPIError(Exception):
    """Erro genérico ao consultar a API do Mercado Livre."""


_ACCESS_TOKEN = config.ML_ACCESS_TOKEN
_EXPIRES_AT = 0


def _refresh_access_token():
    global _ACCESS_TOKEN, _EXPIRES_AT

    if _ACCESS_TOKEN and time.time() < _EXPIRES_AT:
        return _ACCESS_TOKEN

    url = "https://api.mercadolibre.com/oauth/token"

    payload = {
        "grant_type": "refresh_token",
        "client_id": config.ML_CLIENT_ID,
        "client_secret": config.ML_CLIENT_SECRET,
        "refresh_token": config.ML_REFRESH_TOKEN,
    }

    response = requests.post(url, data=payload, timeout=30)
    response.raise_for_status()

    token_data = response.json()

    _ACCESS_TOKEN = token_data["access_token"]
    _EXPIRES_AT = time.time() + token_data.get("expires_in", 21600) - 60

    return _ACCESS_TOKEN


def _session() -> requests.Session:
    s = requests.Session()

    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {_refresh_access_token()}",
    }

    s.headers.update(headers)

    return s


SESSION = _session()


@retry(
    stop=stop_after_attempt(config.API["max_retries"]),
    wait=wait_exponential(multiplier=config.API["retry_backoff_seconds"]),
    retry=retry_if_exception_type((requests.exceptions.RequestException,)),
    reraise=True,
)
def _get(url: str, params: dict | None = None) -> dict:
    """GET genérico com retry/backoff exponencial e tratamento de erros HTTP."""

    global SESSION

    resp = SESSION.get(
        url,
        params=params,
        timeout=config.API["request_timeout_seconds"],
    )

    if resp.status_code == 401:
        logger.info("Access token expirado. Renovando token...")
        SESSION = _session()
        resp = SESSION.get(
            url,
            params=params,
            timeout=config.API["request_timeout_seconds"],
        )

    if resp.status_code != 200:
        logger.warning(
            "Falha na requisição %s | status=%s | body=%s",
            url,
            resp.status_code,
            resp.text[:300],
        )
        resp.raise_for_status()

    return resp.json()


def search_items(query: str, condition: str, offset: int, limit: int) -> dict:
    """
    Busca anúncios via /sites/{site_id}/search.
    NOTA: este endpoint retorna 403 (PA_UNAUTHORIZED_RESULT_FROM_POLICIES)
    para esta aplicação, mesmo com token válido e mesmo sem autenticação
    alguma. Mantido aqui como tentativa primária; ver get_seed_item_ids()
    para o fallback usado pelo etl.py quando esta chamada falha.
    """
    url = config.API["base_url"] + config.API["search_endpoint"].format(site_id=config.API["site_id"])
    params = {
        "q": query,
        "condition": condition,
        "offset": offset,
        "limit": limit,
    }
    return _get(url, params=params)


def paginate_search(query: str, condition: str, page_size: int, max_total_records: int | None):
    """
    Generator que percorre todas as páginas de resultado do /search,
    respeitando o limite de paginação e o limite total opcional.
    """
    offset = 0
    total_fetched = 0

    while True:
        data = search_items(query=query, condition=condition, offset=offset, limit=page_size)
        results = data.get("results", [])
        if not results:
            break

        for item in results:
            if max_total_records is not None and total_fetched >= max_total_records:
                return
            yield item
            total_fetched += 1

        offset += page_size
        paging = data.get("paging", {})
        total_available = paging.get("total", 0)

        if offset >= total_available:
            break
        if max_total_records is not None and total_fetched >= max_total_records:
            break


def get_seed_item_ids() -> list[str]:
    """
    Fallback de descoberta de itens (nível 1).

    Usado quando /sites/{site_id}/search falha. Lista de item_ids reais,
    coletados manualmente a partir do site público do Mercado Livre.
    """
    path = config.ETL["seed_items_file"]
    with open(path, "r", encoding="utf-8") as f:
        ids = [line.strip() for line in f if line.strip()]
    logger.info("Carregados %d item_ids da lista seed (%s)", len(ids), path)
    return ids


def get_fixture_items() -> list[dict]:
    """
    Fallback de dados (nível 2).

    Usado quando o multiget /items também falha (403 access_denied em
    itens de terceiros). Dataset local sintético, com a MESMA estrutura
    de campos da resposta real do /items (id, seller_id, price,
    currency_id, condition, warranty, shipping, etc.), permitindo validar
    o pipeline completo (transform + load + queries) mesmo sem acesso de
    produção liberado pela Mercado Livre para esta aplicação.
    """
    path = config.ETL["fixture_items_file"]
    with open(path, "r", encoding="utf-8") as f:
        items = json.load(f)
    logger.info("Carregados %d itens do fixture local (%s)", len(items), path)
    return items


def get_items_details(item_ids: list[str]) -> list[dict]:
    """
    Busca o detalhe completo de uma lista de itens via multiget /items?ids=...
    A API do Mercado Livre limita a quantidade de ids por chamada
    (config.ETL['items_batch_size']), então dividimos em lotes.
    """
    batch_size = config.ETL["items_batch_size"]
    url = config.API["base_url"] + config.API["items_endpoint"]
    details = []

    for i in range(0, len(item_ids), batch_size):
        batch = item_ids[i : i + batch_size]
        params = {"ids": ",".join(batch)}
        data = _get(url, params=params)
        for idx, entry in enumerate(data):
            if entry.get("code") == 200 and "body" in entry:
                details.append(entry["body"])
            else:
                logger.warning(
                    "Item não retornado corretamente | id=%s | code=%s",
                    batch[idx],
                    entry.get("code"),
                )

    return details


def get_currency_conversion(from_currency: str, to_currency: str) -> float:
    """
    Consulta /currency_conversions/search para obter a taxa de conversão
    entre a moeda de origem (ex: ARS) e a moeda de destino (ex: USD).
    """
    url = config.API["base_url"] + config.API["currency_conversions_endpoint"]
    params = {"from": from_currency, "to": to_currency}
    data = _get(url, params=params)
    rate = data.get("ratio") or data.get("rate")
    if rate is None:
        raise MercadoLibreAPIError(f"Não foi possível obter taxa de conversão {from_currency}->{to_currency}: {data}")
    return float(rate)
