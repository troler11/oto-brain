import os

from dotenv import load_dotenv

load_dotenv()

PG_DSN = os.environ.get("OTO_PG_DSN", "")
"""Connection string do Postgres de produção. NUNCA hardcodar — sempre via env var.
Ver memória `reference_oto_postgres_access`: host 163.176.167.116, db `postgres` (não `otosp`)."""
