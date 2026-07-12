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


def gravar_turno(conn: psycopg.Connection, row: dict, overwrite: bool = False) -> bool:
    """Upsert em conversas_log — mesma lógica do backfill (scripts/backfill_n8n_executions.py).
    Retorna True se inseriu/atualizou, False se já existia e `overwrite=False` (comportamento
    padrão, usado pelo /log-turno ao vivo: idempotente, nunca pisa em turno já logado).
    `overwrite=True` (usado pelo re-backfill) sobrescreve a linha existente — necessário quando
    o conjunto de nós capturados muda (ex.: NOS_INTERESSE ganhou nós novos) e as linhas antigas
    precisam ser enriquecidas, não puladas.
    `row` pode não ter todas as colunas (ex.: LogTurnoIn não expõe raw_nodes) — preenche
    o que faltar com None em vez de depender do chamador ter as 13 chaves exatas."""
    params = {col: row.get(col) for col in _COLUNAS}
    for campo in _COLUNAS_JSONB:
        if params[campo] is not None:
            params[campo] = Jsonb(params[campo])
    on_conflict = (
        "DO UPDATE SET " + ", ".join(f"{c} = EXCLUDED.{c}" for c in _COLUNAS if c != "execution_id")
        if overwrite
        else "DO NOTHING"
    )
    with conn.cursor() as cur:
        cur.execute(
            f"""
            INSERT INTO conversas_log
              (execution_id, workflow_id, status, mode, started_at, stopped_at,
               telefone, texto_usuario, extrair_rota, extrair_intencao_final,
               state_validator, mensagem_enviada, raw_nodes)
            VALUES (%(execution_id)s, %(workflow_id)s, %(status)s, %(mode)s,
                    %(started_at)s, %(stopped_at)s, %(telefone)s, %(texto_usuario)s,
                    %(extrair_rota)s, %(extrair_intencao_final)s, %(state_validator)s,
                    %(mensagem_enviada)s, %(raw_nodes)s)
            ON CONFLICT (execution_id) {on_conflict};
            """,
            params,
        )
        return cur.rowcount > 0
