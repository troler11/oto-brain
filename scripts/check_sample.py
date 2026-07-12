import io
import os
import sys

import psycopg

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

conn = psycopg.connect(os.environ["OTO_PG_DSN"])
with conn.cursor() as cur:
    cur.execute("""
        SELECT execution_id, status, telefone, texto_usuario, mensagem_enviada,
               extrair_rota IS NOT NULL AS tem_er,
               extrair_intencao_final IS NOT NULL AS tem_eif,
               state_validator IS NOT NULL AS tem_sv
        FROM conversas_log ORDER BY id;
    """)
    for row in cur.fetchall():
        print(row)
conn.close()
