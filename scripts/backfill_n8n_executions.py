"""
Backfill do histórico de execuções do n8n (fluxo principal) para a tabela conversas_log.

Por quê: a retenção de execuções do n8n é curta (~7 dias, confirmado 11/07/2026) — esse é o
ÚNICO dado da operação com prazo de expiração (ver plano em
C:\\Users\\lucas\\.claude\\plans\\unified-coalescing-puppy.md, Fase 0). Este script puxa o que
ainda está disponível via API REST nativa do n8n (não a MCP — MCP não serve pra volume alto) e
grava um recorte enxuto por execução: só os nós que carregam estado de conversa, descartando o
`workflowData` (definição do workflow inteiro, ~370KB, redundante em toda resposta).

Uso:
    python scripts/backfill_n8n_executions.py [--since ISO8601] [--limit N] [--dry-run]

Idempotente: upsert por execution_id (ON CONFLICT DO NOTHING) — rodar de novo não duplica.
"""

import argparse
import sys
import time
from datetime import datetime, timezone

import httpx
import psycopg

sys.path.insert(0, __file__.rsplit("scripts", 1)[0])
from app.config import PG_DSN  # noqa: E402
from app.db import gravar_turno  # noqa: E402

import os

N8N_BASE_URL = os.environ.get("OTO_N8N_BASE_URL", "")
N8N_API_KEY = os.environ.get("OTO_N8N_API_KEY", "")
MAIN_WORKFLOW_ID = os.environ.get("OTO_MAIN_WORKFLOW_ID", "")

# Nós cujo output carrega estado de conversa — o resto (nós de infra, sub-agentes de memória
# do LangChain, etc.) não interessa pro corpus de replay do router.
# Montar Contexto / 6. Agrupar Textos1 / AI Agent adicionados 12/07 — são os 3 nós que o
# Extrair Rota lê como INPUT (`$('Montar Contexto').first().json`, `$('6. Agrupar
# Textos1').first().json.mensagem_agrupada`, `$('AI Agent').first().json.output`), confirmado
# grepando `$('...')` no JS fonte. Sem eles o corpus só tem o OUTPUT do turno (serve de gabarito
# pra comparar), não o INPUT (não dá pra rodar app.er.processar() de verdade) — motivo do
# re-backfill com --overwrite sobre as 8.666 linhas já gravadas sem esses 3 nós.
NOS_INTERESSE = {
    "Recebe WhatsApp1",
    "Montar Contexto",
    "6. Agrupar Textos1",
    "AI Agent",
    "Extrair Rota",
    "Extrair Intencao Final1",
    "State Validator",
    "Enviar Mensagem (WhatsApp)2",
}

PAGE_LIMIT = 100  # máximo tolerável por página sem sobrecarregar a API
SLEEP_BETWEEN_CALLS = 0.15  # segundos — throttle pra não martelar a VPS de produção


def _headers() -> dict:
    return {"X-N8N-API-KEY": N8N_API_KEY}


def listar_execucoes(client: httpx.Client, since: str | None):
    """Gera IDs+metadados de execução (sem includeData) via paginação por cursor."""
    cursor = None
    while True:
        params = {"workflowId": MAIN_WORKFLOW_ID, "limit": PAGE_LIMIT}
        if cursor:
            params["cursor"] = cursor
        if since:
            params["startedAfter"] = since
        r = client.get(f"{N8N_BASE_URL}/api/v1/executions", params=params, headers=_headers())
        r.raise_for_status()
        body = r.json()
        for item in body.get("data", []):
            yield item
        cursor = body.get("nextCursor")
        if not cursor:
            break


def extrair_estado(execution_id: str, run_data: dict) -> dict:
    """Pega o PRIMEIRO run de cada nó de interesse (turnos não fazem retry nesses nós)."""
    out = {}
    for nome in NOS_INTERESSE:
        runs = run_data.get(nome)
        if not runs:
            continue
        try:
            out[nome] = runs[0]["data"]["main"][0][0]["json"]
        except (KeyError, IndexError, TypeError):
            out[nome] = None
    return out


def buscar_execucao_completa(client: httpx.Client, execution_id: str) -> dict | None:
    r = client.get(
        f"{N8N_BASE_URL}/api/v1/executions/{execution_id}",
        params={"includeData": "true"},
        headers=_headers(),
    )
    if r.status_code == 404:
        return None
    r.raise_for_status()
    body = r.json()
    run_data = (body.get("data") or {}).get("resultData", {}).get("runData", {})
    estado = extrair_estado(execution_id, run_data)
    return {
        "execution_id": str(body["id"]),
        "workflow_id": body["workflowId"],
        "status": body.get("status"),
        "mode": body.get("mode"),
        "started_at": body.get("startedAt"),
        "stopped_at": body.get("stoppedAt"),
        "telefone": (estado.get("Extrair Rota") or {}).get("telefone"),
        "texto_usuario": _extrair_texto_usuario(estado.get("Recebe WhatsApp1")),
        "extrair_rota": estado.get("Extrair Rota"),
        "extrair_intencao_final": estado.get("Extrair Intencao Final1"),
        "state_validator": estado.get("State Validator"),
        "mensagem_enviada": _extrair_texto_enviado(estado.get("Enviar Mensagem (WhatsApp)2")),
        "raw_nodes": estado,
    }


def _extrair_texto_enviado(node_json) -> str | None:
    if not node_json:
        return None
    try:
        return node_json["_data"]["Message"]["extendedTextMessage"]["text"]
    except (KeyError, TypeError):
        return None


def _extrair_texto_usuario(node_json) -> str | None:
    """Best-effort: shape do webhook WAHA varia (texto/mídia/etc). Guarda o dict cru em
    raw_nodes de qualquer forma — isso aqui só popula a coluna de leitura rápida."""
    if not node_json:
        return None
    payload = (node_json.get("body") or {}).get("payload") or {}
    for caminho in (
        lambda p: p.get("body"),
        lambda p: p["_data"]["Message"]["conversation"],
        lambda p: p["_data"]["Message"]["extendedTextMessage"]["text"],
    ):
        try:
            v = caminho(payload)
            if isinstance(v, str) and v:
                return v
        except (KeyError, TypeError):
            continue
    return None


# gravar() foi absorvido por app.db.gravar_turno — mesma função usada pelo endpoint
# POST /log-turno, pra não duplicar a lista de colunas em dois lugares (foi exatamente essa
# duplicação que causou o bug do "query parameter missing: raw_nodes" no live logging).
gravar = gravar_turno


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default=None, help="ISO8601 — só execuções a partir daqui")
    ap.add_argument("--limit", type=int, default=None, help="máximo de execuções a processar (teste)")
    ap.add_argument("--dry-run", action="store_true", help="não grava no Postgres, só mostra contagem")
    ap.add_argument("--overwrite", action="store_true",
                     help="sobrescreve linhas já existentes (ON CONFLICT DO UPDATE) em vez de pular — "
                          "necessário quando NOS_INTERESSE ganha nós novos e as linhas antigas precisam "
                          "ser reenriquecidas")
    args = ap.parse_args()

    if not (N8N_BASE_URL and N8N_API_KEY and MAIN_WORKFLOW_ID):
        print("faltam env vars OTO_N8N_BASE_URL / OTO_N8N_API_KEY / OTO_MAIN_WORKFLOW_ID (.env)")
        sys.exit(1)

    conn = None
    if not args.dry_run:
        conn = psycopg.connect(PG_DSN, autocommit=True)
        with conn.cursor() as cur:
            schema_path = __file__.replace("backfill_n8n_executions.py", "schema.sql")
            cur.execute(open(schema_path, encoding="utf-8").read())

    inseridos = pulados = erros = total = 0
    t0 = time.time()

    with httpx.Client(timeout=30.0) as client:
        for meta in listar_execucoes(client, args.since):
            if args.limit and total >= args.limit:
                break
            total += 1
            try:
                row = buscar_execucao_completa(client, meta["id"])
            except httpx.HTTPStatusError as e:
                print(f"[erro] exec {meta['id']}: {e}")
                erros += 1
                continue
            if row is None:
                pulados += 1
                continue
            if args.dry_run:
                inseridos += 1
            else:
                if gravar(conn, row, overwrite=args.overwrite):
                    inseridos += 1
                else:
                    pulados += 1
            if total % 200 == 0:
                dt = time.time() - t0
                print(f"...{total} processadas ({inseridos} novas, {pulados} já existiam, {erros} erros) em {dt:.0f}s")
            time.sleep(SLEEP_BETWEEN_CALLS)

    dt = time.time() - t0
    print(f"FIM: {total} execuções vistas | {inseridos} gravadas | {pulados} puladas | {erros} erros | {dt:.0f}s")
    if conn:
        conn.close()


if __name__ == "__main__":
    main()
