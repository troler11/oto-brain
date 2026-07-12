"""
Deriva paciente_memoria a partir de contatos_whatsapp + agendamentos (mesma base Postgres —
não busca em outro sistema). Bootstrap da Fase 4 do plano: preferências consolidadas por
paciente, prontas pra injetar no contexto do agente sem re-perguntar médico/unidade/convênio.

Idempotente — roda de novo, atualiza tudo (upsert por telefone).

Uso: python scripts/build_paciente_memoria.py
"""

import os
import sys

import psycopg

sys.path.insert(0, __file__.rsplit("scripts", 1)[0])
from app.config import PG_DSN  # noqa: E402


def main():
    schema_path = __file__.replace("build_paciente_memoria.py", "schema.sql")
    sql_path = __file__.replace("build_paciente_memoria.py", "build_paciente_memoria.sql")

    with psycopg.connect(PG_DSN, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(open(schema_path, encoding="utf-8").read())
            cur.execute(open(sql_path, encoding="utf-8").read())
            cur.execute("SELECT COUNT(*) FROM paciente_memoria;")
            total = cur.fetchone()[0]
    print(f"paciente_memoria: {total} pacientes")


if __name__ == "__main__":
    main()
