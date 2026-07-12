import os

from dotenv import load_dotenv

load_dotenv()

PG_DSN = os.environ.get("OTO_PG_DSN", "")
"""Connection string do Postgres de produção. NUNCA hardcodar — sempre via env var.
Detalhes de host/db: ver memória `reference_oto_postgres_access` (fora deste repo)."""

OPENAI_API_KEY = os.environ.get("OTO_OPENAI_API_KEY", "")
"""Chave da OpenAI pros agentes com structured output (Fase 3). NUNCA hardcodar — sempre via
env var. Ausente em dev: os testes de app/agentes.py usam mocks, não fazem chamada real."""

TISAUDE_LOGIN = os.environ.get("OTO_TISAUDE_LOGIN", "")
TISAUDE_SENHA = os.environ.get("OTO_TISAUDE_SENHA", "")
"""Credenciais da API TiSaude (app.tisaude). NUNCA hardcodar — hoje estão hardcoded em texto
plano nos nós 'Login TiSaude' dos workflows n8n (achado de segurança, rotação pendente com
Lucas); aqui sempre via env var. Ausentes em dev: os testes de app/tisaude.py usam client
httpx mockado, não fazem chamada real."""
