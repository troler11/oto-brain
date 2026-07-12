import psycopg
from psycopg.types.json import Jsonb

from app.config import PG_DSN


def get_connection() -> psycopg.Connection:
    return psycopg.connect(PG_DSN, autocommit=True)


_COLUNAS = (
    "execution_id", "workflow_id", "status", "mode", "started_at", "stopped_at",
    "telefone", "texto_usuario", "extrair_rota", "extrair_intencao_final",
    "state_validator", "mensagem_enviada", "raw_nodes",
)
_COLUNAS_JSONB = {"extrair_rota", "extrair_intencao_final", "state_validator", "raw_nodes"}


def gravar_turno(conn: psycopg.Connection, row: dict) -> bool:
    """Upsert idempotente em conversas_log — mesma lógica do backfill (scripts/backfill_n8n_executions.py).
    Retorna True se inseriu, False se já existia (ex.: turno já veio do backfill).
    `row` pode não ter todas as colunas (ex.: LogTurnoIn não expõe raw_nodes) — preenche
    o que faltar com None em vez de depender do chamador ter as 13 chaves exatas."""
    params = {col: row.get(col) for col in _COLUNAS}
    for campo in _COLUNAS_JSONB:
        if params[campo] is not None:
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
