"""
Wrapper de IO da mineração de casos (Fase 4, mecanismo 2 — ver app/minerar_casos.py pra lógica
e heurísticas). Lê chat_limpo + agendamentos do Postgres de produção, grava casos novos em
casos_aprendizado (ON CONFLICT DO NOTHING — idempotente, seguro rodar como job diário).

Uso: python scripts/mine_casos_aprendizado.py
"""

import sys

import psycopg
from psycopg.types.json import Jsonb

sys.path.insert(0, __file__.rsplit("scripts", 1)[0])
from app.config import PG_DSN  # noqa: E402
from app.minerar_casos import minerar_tudo  # noqa: E402


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    schema_path = __file__.replace("mine_casos_aprendizado.py", "schema.sql")

    with psycopg.connect(PG_DSN, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(open(schema_path, encoding="utf-8").read())

            cur.execute("""
                SELECT telefone, texto, origem, enviado_por, data
                FROM chat_limpo
                WHERE excluido_em IS NULL AND telefone IS NOT NULL
                ORDER BY telefone, data;
            """)
            mensagens_por_telefone = {}
            for telefone, texto, origem, enviado_por, data in cur.fetchall():
                mensagens_por_telefone.setdefault(telefone, []).append({
                    "telefone": telefone, "texto": texto, "origem": origem,
                    "enviado_por": enviado_por, "data": data,
                })

            cur.execute("""
                SELECT DISTINCT cw.telefone
                FROM contatos_whatsapp cw
                JOIN agendamentos a ON a.contato_id = cw.id;
            """)
            telefones_com_agendamento = {row[0] for row in cur.fetchall()}

        casos = minerar_tudo(mensagens_por_telefone, telefones_com_agendamento)

        with conn.cursor() as cur:
            for c in casos:
                cur.execute(
                    """
                    INSERT INTO casos_aprendizado (telefone, categoria, turno_texto, contexto, origem_data)
                    VALUES (%(telefone)s, %(categoria)s, %(turno_texto)s, %(contexto)s, %(origem_data)s)
                    ON CONFLICT (telefone, categoria, origem_data) DO NOTHING;
                    """,
                    {**c, "contexto": Jsonb(c["contexto"])},
                )
            cur.execute("SELECT categoria, COUNT(*) FROM casos_aprendizado GROUP BY categoria ORDER BY categoria;")
            print(f"casos minerados nesta rodada: {len(casos)}")
            print("total em casos_aprendizado por categoria:")
            for categoria, total in cur.fetchall():
                print(f"  {categoria}: {total}")


if __name__ == "__main__":
    main()
