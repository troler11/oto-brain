import os

from dotenv import load_dotenv

load_dotenv()

PG_DSN = os.environ.get("OTO_PG_DSN", "")
"""Connection string do Postgres de produção. NUNCA hardcodar — sempre via env var.
Detalhes de host/db: ver memória `reference_oto_postgres_access` (fora deste repo)."""
