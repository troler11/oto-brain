import psycopg
from psycopg.types.json import Jsonb

from app.config import PG_DSN


def get_connection() -> psycopg.Connection:
    return psycopg.connect(PG_DSN, autocommit=True)


def gravar_turno(conn: psycopg.Connection, row: dict) -> bool:
    """Upsert idempotente em conversas_log — mesma lógica do backfill (scripts/backfill_n8n_executions.py).
    Retorna True se inseriu, False se já existia (ex.: turno já veio do backfill)."""
    params = dict(row)
    for campo in ("extrair_rota", "extrair_intencao_final", "state_validator", "raw_nodes"):
        if campo in params and params[campo] is not None:
            params[campo] = Jsonb(params[campo])
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO conversas_log
              (execution_id, workflow_id, status, mode, started_at, stopped_at,
               telefone, texto_usuario, extrair_rota, extrair_intencao_final,
               state_validator, mensagem_enviada, raw_nodes)
            VALUES (%(execution_id)s, %(workflow_id)s, %(status)s, %(mode)s,
                    %(started_at)s, %(stopped_at)s, %(telefone)s, %(texto_usuario)s,
                    %(extrair_rota)s, %(extrair_intencao_final)s, %(state_validator)s,
                    %(mensagem_enviada)s, %(raw_nodes)s)
            ON CONFLICT (execution_id) DO NOTHING;
            """,
            params,
        )
        return cur.rowcount > 0
