"""
Carrega o arquivo config.yaml e as variáveis de ambiente (.env).
Nenhuma credencial fica hard-coded no código-fonte.
"""
import os
import yaml
from dotenv import load_dotenv

load_dotenv()  # carrega o arquivo .env, se existir

_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.yaml")

with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
    _raw_config = yaml.safe_load(f)

API = _raw_config["api"]
ETL = _raw_config["etl"]
LOGGING = _raw_config["logging"]

# Credenciais de banco de dados (variáveis de ambiente, nunca no código)
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": os.getenv("DB_PORT", "5432"),
    "dbname": os.getenv("DB_NAME", "mercadolibre_etl"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", ""),
}

ML_CLIENT_ID = os.getenv("ML_CLIENT_ID")
ML_CLIENT_SECRET = os.getenv("ML_CLIENT_SECRET")
ML_REFRESH_TOKEN = os.getenv("ML_REFRESH_TOKEN")
ML_ACCESS_TOKEN = os.getenv("ML_ACCESS_TOKEN")
