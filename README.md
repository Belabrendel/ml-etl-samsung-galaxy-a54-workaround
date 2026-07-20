# ML ETL - Samsung Galaxy A54 (Mercado Livre Argentina) — versão com workaround

ETL em Python que extrai anúncios de "Samsung Galaxy A54" (novos) da API pública
do Mercado Livre, transforma os dados e carrega em um banco PostgreSQL.

> Esta versão inclui **fallbacks** para os endpoints `/sites/{site_id}/search`
> e `/items`, que estão bloqueados (403) para a aplicação usada neste desafio.
> O diagnóstico completo está na seção "Desafios encontrados" abaixo. Se você
> tiver uma aplicação com acesso de produção liberado, use a versão "produção"
> (outro pacote), que é o pipeline sem os fallbacks.

## Arquitetura

```
main.py                -> ponto de entrada
config.py               -> carrega config.yaml + variáveis de ambiente (.env)
config.yaml              -> parâmetros do ETL (query, paginação, endpoints, etc.)
src/
  extract.py            -> EXTRACT: /search, /items, /currency_conversions
                            + fallbacks (seed_item_ids, fixture_items)
  transform.py          -> TRANSFORM: regras de negócio, cálculo de JOB_RUN, USD
  load.py               -> LOAD: grava em PostgreSQL
  etl.py                -> orquestra as 3 etapas, com lógica de fallback
data/
  seed_item_ids.txt     -> item_ids reais coletados manualmente (fallback nível 1)
  fixture_items.json    -> dataset sintético com estrutura real de /items (fallback nível 2)
schema.sql              -> DDL das tabelas
```

## Desafios encontrados (diagnóstico do bloqueio de API)

Durante o desenvolvimento, o endpoint `/sites/{site_id}/search` retornou
sistematicamente `403 forbidden` / `PA_UNAUTHORIZED_RESULT_FROM_POLICIES`,
**mesmo em requisições sem nenhum header de autenticação**, indicando bloqueio
de política de plataforma e não um problema de escopo/permissão da aplicação.

Investigação realizada, em ordem:

1. `/sites/MLA/search` sem token → `403 forbidden`
2. `/sites/MLA/search` com token válido (test user) → `403 forbidden`
3. `/items/{id}` (item real, terceiro) → `403 PA_UNAUTHORIZED_RESULT_FROM_POLICIES`
4. `/users/me` (dados do próprio usuário autenticado) → funcionou normalmente
5. `/users/{id}/items/search` (anúncios do próprio usuário autenticado) →
   funcionou, mas vazio (o usuário de teste não tem publicações)
6. Reautenticação com usuário **real** (não test user) → `/items/{id}` continuou
   retornando `403 access_denied`
7. Teste com site `MLB` (Brasil) em vez de `MLA`, ainda com usuário real →
   mesmo bloqueio em `/search` e `/items`

Conclusão: a aplicação usada não possui acesso de produção às APIs de dados
públicos do marketplace (busca e detalhe de itens de terceiros), independente
de usuário autenticado ou site consultado. Isso é consistente com mudanças de
política da Mercado Livre restringindo acesso de terceiros a esses endpoints
— inclusive projetos de código aberto de integração (ex: servidores MCP da
comunidade) documentam a mesma limitação e tiveram que desativar
funcionalidades de busca por esse motivo.

### Estratégia adotada

Dado o prazo do desafio, o pipeline foi adaptado com dois níveis de fallback,
mantendo toda a arquitetura de EXTRACT/TRANSFORM/LOAD original intacta:

- **Nível 1 — descoberta de itens**: quando `/search` falha, usa uma lista de
  `item_id`s reais (`data/seed_item_ids.txt`), coletados manualmente no site
  público do Mercado Livre.
- **Nível 2 — detalhe dos itens**: quando `/items` também falha para esses
  ids, usa um dataset local (`data/fixture_items.json`) com a **mesma
  estrutura de campos** da resposta real da API (id, seller_id, price,
  currency_id, condition, warranty, shipping, etc.), permitindo validar o
  pipeline completo (transform, load, modelo de dados e queries) mesmo sem
  acesso de produção liberado.

**Importante**: os dados do fixture são sintéticos (não são anúncios reais),
usados apenas para destravar a validação do pipeline dentro do prazo. A
estrutura, porém, é fiel à API real, então o pipeline funciona sem qualquer
alteração assim que o acesso de produção for liberado — basta que `/search`
e `/items` voltem a responder 200, e os fallbacks simplesmente não são
acionados (ver lógica em `src/etl.py`).

## Como executar

Esta seção descreve o passo a passo para executar o pipeline ETL localmente.

---

### 1. Pré-requisitos

Antes de executar o projeto, é necessário possuir instalado:

- Python 3.10 ou superior;
- PostgreSQL 14 ou superior;
- Git.

Verifique as versões instaladas:

```bash
python --version

psql --version
```

### 2. Clonar o repositório

Clone o projeto:

git clone <URL_DO_REPOSITORIO>

cd ml_etl


### 3. Criar ambiente virtual Python

Recomenda-se utilizar um ambiente virtual isolado:

python -m venv venv

#### Ative o ambiente:
#####  Linux / MacOS
source venv/bin/activate

##### Windows
venv\Scripts\activate

### 4. Instalar dependências

Com o ambiente virtual ativo:

pip install -r requirements.txt

##### As principais bibliotecas utilizadas são:

requests → comunicação com a API Mercado Livre;
python-dotenv → carregamento das variáveis de ambiente;
psycopg2 → conexão com PostgreSQL;
pyyaml → leitura do arquivo de configuração;
tenacity → retry e backoff das chamadas HTTP.

### 5. Configuração das variáveis de ambiente

##### Crie um arquivo .env a partir do exemplo:

cp .env.example .env

Preencha as informações necessárias:

# Mercado Livre API
ML_ACCESS_TOKEN=

# PostgreSQL
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DATABASE=mercadolibre_etl
POSTGRES_USER=postgres
POSTGRES_PASSWORD=

As credenciais não ficam armazenadas no código e são carregadas automaticamente pelo arquivo config.py.

### 6. Configuração do ETL

Os parâmetros do pipeline ficam no arquivo:

config.yaml

Exemplo:

api:
  base_url: https://api.mercadolibre.com

site_id: MLA

search:
  query: Samsung Galaxy A54
  condition: new

pagination:
  limit: 50
  max_total_records: 500

Neste arquivo podem ser alterados:

produto pesquisado;
país/site do Mercado Livre;
limite de paginação;
quantidade máxima de registros;
endpoints utilizados.
### 7. Criar banco de dados PostgreSQL

Crie o banco:

CREATE DATABASE mercadolibre_etl;

Conecte no banco:

psql -U postgres -d mercadolibre_etl

Execute o schema:

psql -U postgres -d mercadolibre_etl -f schema.sql

Após a execução, as tabelas serão criadas:

items
item_shipping_methods
currency_conversion
8. Executar o ETL

Com todas as configurações realizadas:

python main.py

O fluxo executado será:

EXTRACT
   |
   |-- /search
   |-- /items
   |-- /currency_conversions
   |
   v

TRANSFORM
   |
   |-- filtros de negócio
   |-- cálculo de preço USD
   |-- criação do JOB_RUN
   |
   v

LOAD
   |
   v

PostgreSQL
### 9. Funcionamento dos fallbacks

Caso a API esteja disponível, o pipeline utiliza os endpoints oficiais normalmente.

Fluxo:

API Mercado Livre
        |
        v
Transformação
        |
        v
PostgreSQL

Caso os endpoints /search ou /items retornem erro 403, os fallbacks são acionados automaticamente.

Fluxo alternativo:

/search bloqueado
        |
        v
data/seed_item_ids.txt

        |
        v

/items bloqueado

        |
        v

data/fixture_items.json

        |
        v

Transformação

        |
        v

PostgreSQL

Os fallbacks existem apenas para permitir a validação completa do pipeline enquanto o acesso de produção da API não está disponível.

### 10. Validar execução

Após a execução, é possível verificar os dados carregados:

SELECT *
FROM items;

Verificar a última execução:

SELECT MAX(job_run)
FROM items;

Verificar quantidade de anúncios:

SELECT COUNT(*)
FROM items;

Verificar métodos de shipping:

SELECT *
FROM item_shipping_methods;
11. Logs

Durante a execução são gerados logs contendo:

chamadas realizadas na API;
erros encontrados;
retries executados;
ativação dos fallbacks;
status da carga no banco.

Arquivo:

etl_run.log

Além disso, informações importantes também são exibidas no terminal durante a execução.

## Modelo de dados

### `items`
| Campo | Tipo | Descrição |
|---|---|---|
| item_id | VARCHAR(20) | id do anúncio no ML (PK composta com job_run) |
| job_run | TIMESTAMP | data/hora da execução do ETL (PK composta) |
| seller_id | BIGINT | id do vendedor |
| title | TEXT | título do anúncio |
| price | NUMERIC(14,2) | preço na moeda original |
| currency_id | VARCHAR(5) | moeda original (ex: ARS) |
| price_usd | NUMERIC(14,2) | preço convertido para USD |
| condition | VARCHAR(20) | condição do produto (sempre "new" neste ETL) |
| warranty | TEXT | texto de garantia como veio da API |
| has_warranty | BOOLEAN | derivado de `warranty` |
| sold_quantity | INTEGER | quantidade vendida |
| available_quantity | INTEGER | quantidade disponível |
| listing_type_id | VARCHAR(30) | tipo de anúncio (gold_pro, silver, etc.) |
| free_shipping | BOOLEAN | se oferece frete grátis |
| permalink | TEXT | link do anúncio |

### `item_shipping_methods`
| Campo | Tipo | Descrição |
|---|---|---|
| id | SERIAL | PK |
| item_id | VARCHAR(20) | FK composta -> items |
| job_run | TIMESTAMP | FK composta -> items |
| shipping_mode | VARCHAR(30) | modo logístico (fulfillment, drop_off, etc.) |
| shipping_tag | VARCHAR(50) | tag de shipping retornada pela API |

### `currency_conversion`
| Campo | Tipo | Descrição |
|---|---|---|
| id | SERIAL | PK |
| job_run | TIMESTAMP | execução do ETL |
| currency_from | VARCHAR(5) | moeda de origem (ARS) |
| currency_to | VARCHAR(5) | moeda de destino (USD) |
| conversion_rate | NUMERIC(18,10) | taxa usada nesta execução |

## Queries que respondem as perguntas do desafio

**1) Há algum vendedor com múltiplas publicações? Quantas?**
```sql
SELECT seller_id, COUNT(DISTINCT item_id) AS total_publicaciones
FROM items
WHERE job_run = (SELECT MAX(job_run) FROM items)
GROUP BY seller_id
HAVING COUNT(DISTINCT item_id) > 1
ORDER BY total_publicaciones DESC;
```

**2) Média de vendas por seller**
```sql
SELECT seller_id, ROUND(AVG(sold_quantity), 2) AS promedio_ventas
FROM items
WHERE job_run = (SELECT MAX(job_run) FROM items)
GROUP BY seller_id
ORDER BY promedio_ventas DESC;
```

**3) Preço médio em dólares**
```sql
SELECT ROUND(AVG(price_usd), 2) AS precio_promedio_usd
FROM items
WHERE job_run = (SELECT MAX(job_run) FROM items);
```

**4) Percentual de artigos com garantia**
```sql
SELECT
  ROUND(100.0 * SUM(CASE WHEN has_warranty THEN 1 ELSE 0 END) / COUNT(*), 2) AS pct_con_garantia
FROM items
WHERE job_run = (SELECT MAX(job_run) FROM items);
```

**5) Métodos de shipping oferecidos**
```sql
SELECT shipping_mode, shipping_tag, COUNT(*) AS cantidad
FROM item_shipping_methods
WHERE job_run = (SELECT MAX(job_run) FROM item_shipping_methods)
GROUP BY shipping_mode, shipping_tag
ORDER BY cantidad DESC;
```
## Requisitos do desafio atendidos

| Requisito | Implementação |
|---|---|
| Linguagem Python | Pipeline desenvolvido em Python |
| Tipo ETL | Separação das etapas Extract, Transform e Load |
| API Mercado Livre | Uso dos endpoints `/search`, `/items` e `/currency_conversions` |
| Paginação | Consulta paginada em lotes de 50 registros |
| Produtos novos | Filtro `condition=new` aplicado na extração |
| Banco de dados | PostgreSQL local |
| JOB_RUN | Campo timestamp gerado no início da execução e replicado em todas as tabelas |
| Configuração externa | Variáveis em `config.yaml` |
| Credenciais seguras | Variáveis de ambiente via `.env` |
| DDL | Disponível em `schema.sql` |
| Queries analíticas | Disponíveis neste README |

## Decisões de arquitetura

- **Fallback em camadas**: cada nível de fallback só é acionado se o nível
  anterior (o caminho "oficial" via API) falhar — o código sempre tenta a
  API real primeiro.
- **Paginação**: `/search` é paginado em lotes de 50 (exigência do desafio),
  com limite de segurança configurável (`max_total_records`).
- **Retry/backoff**: todas as chamadas HTTP usam `tenacity` com backoff
  exponencial (3 tentativas por padrão) antes de acionar qualquer fallback.
- **JOB_RUN**: gerado uma única vez no início da execução e propagado para
  todas as tabelas.
- **Idempotência**: `items` tem PK composta (`item_id`, `job_run`) com
  `ON CONFLICT DO NOTHING`.
- **Credenciais**: 100% via variáveis de ambiente (`.env`).

## Oportunidades de melhoria

- Solicitar formalmente ao suporte da Mercado Livre a liberação de acesso de produção para a aplicação, e remover os fallbacks assim que confirmado.
- Ampliar `data/seed_item_ids.txt` (atualmente ~15 ids) para uma amostra
  maior, melhorando a robustez das métricas caso o fallback nível 1 precise ser usado sozinho (com `/items` funcionando).
- Paralelizar as chamadas de multiget de `/items`.
- Testes automatizados cobrindo tanto o caminho feliz quanto os fallbacks.
