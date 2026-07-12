"""
Replay offline do corpus real (`conversas_log`) contra o port Python do ER (app.er.processar)
e do State Validator (app.state_validator.validar_estado). Fase 1 do plano de migração (ver
C:\\Users\\lucas\\.claude\\plans\\unified-coalescing-puppy.md) — "corpus de regressão instantâneo,
sem esperar tráfego novo".

Reconstrói, por turno, exatamente o que os nós originais receberam:
  ER   <- Montar Contexto (base), 6. Agrupar Textos1 (mensagem_agrupada), AI Agent (ai_agent_json),
          Recebe WhatsApp1 (whatsapp_info + hasMedia)   [confere com os `$('...')` do JS fonte]
  SV   <- Extrair Intencao Final1 (inp, passado por `normalizar_ds()` antes de validar — o
          pipeline real é EIF1 -> Normalizar DS -> State Validator, confirmado via
          get_workflow_details do workflow principal 12/07/2026; Normalizar DS recalcula
          dia_semana_coleta a partir de data_coleta e não tem arquivo _proposed_ no DEPLOY),
          Montar Contexto (base), Extrair Rota (er_output, mesmo turno)
Compara contra o gabarito real gravado (`extrair_rota`/`state_validator`). Usa `hoje_fixado`
(app.er) pra rodar cada turno com a data REAL do turno (campo `base.hoje`, setado por Montar
Contexto em SP-local), não o wall-clock de quem roda o replay — sem isso todo guard sensível a
data (próxima segunda, carência, etc) divergiria por motivo espúrio, não por bug de port.

Só compara turnos cujos 5 nós de interesse relevantes estão presentes (turnos que não chegaram
lá — erro, transferência antecipada, mensagem só de mídia sem texto — são contados à parte como
"incompletos", não como mismatch).

Não escreve nada no Postgres — só leitura.

Uso:
    python scripts/replay_offline.py [--limit N] [--since ISO] [--verbose] [--mismatches-only]
"""

import argparse
import json
import sys
from collections import Counter
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8")  # console cp1252 quebra em acento/seta (→) dos textos PT-BR

import psycopg
from psycopg.rows import dict_row

sys.path.insert(0, __file__.rsplit("scripts", 1)[0])
from app.config import PG_DSN  # noqa: E402
from app.er import hoje_fixado, processar  # noqa: E402
from app.state_validator import normalizar_ds, validar_estado  # noqa: E402

CAMPOS_ER_COMPARADOS = (
    "intencao_rapida", "rota_agente", "texto_ia", "coleta_unidade", "coleta_medico",
    "coleta_convenio", "coleta_data", "coleta_periodo", "coleta_dia_semana", "coleta_horario",
    "coleta_modo", "nome_dependente", "coleta_terceiro", "deve_resetar_sessao",
)
# `_shadow_check` NÃO entra aqui: depende do nó "Triagem Determinística (Pre-IA)" da mesma
# execução, que não está em NOS_INTERESSE (scripts/backfill_n8n_executions.py) — precisaria de
# novo re-backfill pra validar contra gabarito real. `deve_resetar_sessao` já é validável porque
# é campo direto do JSON gravado pelo nó Extrair Rota (fechado 12/07, ver app/er.py::processar).
CAMPOS_SV_COMPARADOS = ("sv_result", "sv_reason")


def _extrair_whatsapp_info(recebe_whatsapp: dict | None) -> tuple[dict, bool]:
    """Espelha `$('Recebe WhatsApp1').first().json.body?.payload?._data?.Info` e
    `.body.payload.hasMedia === true` do JS fonte (topo do Extrair Rota)."""
    if not recebe_whatsapp:
        return {}, False
    payload = ((recebe_whatsapp.get("body") or {}).get("payload") or {})
    info = ((payload.get("_data") or {}).get("Info") or {})
    has_media = payload.get("hasMedia") is True
    return info, has_media


def _hoje_do_turno(montar_contexto: dict) -> datetime:
    hoje_str = (montar_contexto or {}).get("hoje")
    if hoje_str:
        try:
            return datetime.strptime(hoje_str + " 12:00:00", "%Y-%m-%d %H:%M:%S")
        except ValueError:
            pass
    return datetime.now()


def _resultado_er(r_base: dict, intencao_rapida: str, rota_agente: int, deve_resetar_sessao: bool) -> dict:
    out = dict(r_base)
    out["intencao_rapida"] = intencao_rapida
    out["rota_agente"] = rota_agente
    out["deve_resetar_sessao"] = deve_resetar_sessao
    return out


def replay_turno(row: dict) -> dict | None:
    """Retorna dict com divergências (vazio = concordância total) ou None se o turno não tem
    os nós necessários pra reconstruir o input (turno incompleto, não é mismatch de lógica)."""
    raw = row.get("raw_nodes") or {}
    montar_contexto = raw.get("Montar Contexto")
    agrupar_textos = raw.get("6. Agrupar Textos1")
    ai_agent = raw.get("AI Agent")
    recebe_whatsapp = raw.get("Recebe WhatsApp1")
    er_gabarito = row.get("extrair_rota")

    if not (montar_contexto and agrupar_textos and er_gabarito):
        return None

    mensagem_agrupada = agrupar_textos.get("mensagem_agrupada") or ""
    whatsapp_info, has_media = _extrair_whatsapp_info(recebe_whatsapp)
    hoje = _hoje_do_turno(montar_contexto)

    with hoje_fixado(hoje):
        r = processar(montar_contexto, mensagem_agrupada, ai_agent, whatsapp_info, has_media)

    er_python = _resultado_er(r.base, r.intencao_rapida, r.rota_agente, r.deve_resetar_sessao)
    diffs = {}
    for campo in CAMPOS_ER_COMPARADOS:
        esperado = er_gabarito.get(campo)
        obtido = er_python.get(campo)
        if esperado != obtido:
            diffs[f"er.{campo}"] = {"esperado": esperado, "obtido": obtido}

    sv_gabarito = row.get("state_validator")
    eif1 = row.get("extrair_intencao_final")
    if sv_gabarito and eif1:
        sv = validar_estado(normalizar_ds(eif1), montar_contexto, er_gabarito, hoje=hoje.date())
        for campo in CAMPOS_SV_COMPARADOS:
            esperado = sv_gabarito.get(campo)
            obtido = getattr(sv, campo)
            if esperado != obtido:
                diffs[f"sv.{campo}"] = {"esperado": esperado, "obtido": obtido}

    return diffs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--since", default=None, help="ISO8601 — só turnos a partir daqui (started_at)")
    ap.add_argument("--verbose", action="store_true", help="imprime cada mismatch (não só o resumo)")
    ap.add_argument("--mismatches-only", action="store_true", help="não imprime progresso, só o relatório final")
    args = ap.parse_args()

    conn = psycopg.connect(PG_DSN, row_factory=dict_row)
    query = "SELECT * FROM conversas_log WHERE status = 'success' ORDER BY started_at ASC"
    params = []
    if args.since:
        query = "SELECT * FROM conversas_log WHERE status = 'success' AND started_at >= %s ORDER BY started_at ASC"
        params.append(args.since)
    if args.limit:
        query += " LIMIT %s"
        params.append(args.limit)

    total = incompletos = concordantes = divergentes = 0
    contagem_campos = Counter()
    exemplos_por_campo: dict[str, list] = {}

    with conn.cursor() as cur:
        cur.execute(query, params)
        for row in cur:
            total += 1
            try:
                diffs = replay_turno(row)
            except Exception as e:
                diffs = {"__erro__": {"esperado": None, "obtido": f"{type(e).__name__}: {e}"}}

            if diffs is None:
                incompletos += 1
                continue
            if not diffs:
                concordantes += 1
                continue

            divergentes += 1
            for campo, detalhe in diffs.items():
                contagem_campos[campo] += 1
                if campo not in exemplos_por_campo:
                    exemplos_por_campo[campo] = []
                if len(exemplos_por_campo[campo]) < 5:
                    exemplos_por_campo[campo].append({
                        "execution_id": row["execution_id"],
                        "telefone": row.get("telefone"),
                        "texto_usuario": row.get("texto_usuario"),
                        **detalhe,
                    })
                if args.verbose:
                    print(f"[MISMATCH] exec={row['execution_id']} campo={campo} "
                          f"esperado={detalhe['esperado']!r} obtido={detalhe['obtido']!r}")

            if not args.mismatches_only and total % 500 == 0:
                print(f"...{total} turnos vistos ({concordantes} concordantes, {divergentes} divergentes, "
                      f"{incompletos} incompletos)")

    conn.close()

    comparaveis = concordantes + divergentes
    print("\n" + "=" * 70)
    print("REPLAY OFFLINE — RELATÓRIO")
    print("=" * 70)
    print(f"Total de turnos vistos:      {total}")
    print(f"Incompletos (sem nós):       {incompletos}")
    print(f"Comparáveis:                 {comparaveis}")
    print(f"  Concordantes:              {concordantes}")
    print(f"  Divergentes:               {divergentes}")
    if comparaveis:
        print(f"  Taxa de concordância:      {100 * concordantes / comparaveis:.2f}%")

    if contagem_campos:
        print("\nDivergências por campo (turnos podem divergir em mais de um campo):")
        for campo, n in contagem_campos.most_common():
            print(f"  {campo}: {n}")
        print("\nExemplos (até 5 por campo):")
        for campo, exemplos in exemplos_por_campo.items():
            print(f"\n--- {campo} ---")
            for ex in exemplos:
                print(f"  exec={ex['execution_id']} tel={ex['telefone']} texto={ex['texto_usuario']!r}")
                print(f"    esperado={ex['esperado']!r}")
                print(f"    obtido=  {ex['obtido']!r}")


if __name__ == "__main__":
    main()
