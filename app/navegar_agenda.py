"""
Port fiel dos nós 'Calcular Índice e Montar Resposta1' + 'Sem Cache Ativo1' + 'Retornar para
IA1' do sub-workflow n8n 'Ferramenta - Navegar Agenda' (id `iSO191fJ9Q1FMmVZ`, lido via
`get_workflow_details` 13/07/2026 — sem arquivo `_proposed_` no DEPLOY pra esta tool, snapshot
direto do node JS). Confirmado por leitura do código real: NÃO chama a API TiSaude — é
paginação pura sobre o cache gravado em `agenda_cache` (Postgres) por `buscar_agenda`
(orquestração ainda não portada, ver app.tisaude). Ver `app.db.ler_agenda_cache`/
`atualizar_indice_agenda_cache` pro SELECT/UPDATE que cercam esta função pura.

`cache_row` é o resultado de 'Ler Cache do Postgres1' (`{"agenda_json": {...}, "indice_atual":
int}` ou `None`/sem `agenda_json` quando não há linha — replica o IF 'Cache Existe?1').
"""

from __future__ import annotations

import unicodedata
from datetime import date

_DIAS_MAP = {
    "segunda": 1, "segunda-feira": 1, "seg": 1,
    "terca": 2, "terca-feira": 2, "ter": 2,
    "quarta": 3, "quarta-feira": 3, "qua": 3,
    "quinta": 4, "quinta-feira": 4, "qui": 4,
    "sexta": 5, "sexta-feira": 5, "sex": 5,
    "sabado": 6, "sabado-feira": 6, "sab": 6,
    "domingo": 0, "dom": 0,
}

_AVISO_DATA_NAO_ENCONTRADA = "Data não encontrada no cache. Tente avancar ou chame buscar_agenda com nova data."


def _get_day_js(iso_date: str) -> int:
    """getDay() de `new Date(iso+'T12:00:00')`: domingo=0..sábado=6 (mesmo helper usado em
    app.preparar_input_agenda)."""
    y, m, d = (int(p) for p in iso_date.split("-"))
    return (date(y, m, d).weekday() + 1) % 7


def _norm_nfd(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def _data_nao_encontrada(data_solicitada, total_dias: int, indice: int) -> dict:
    return {
        "status": "DATA_NAO_ENCONTRADA", "data_solicitada": data_solicitada, "total_dias": total_dias,
        "indice_atual": indice, "dia": None, "aviso": _AVISO_DATA_NAO_ENCONTRADA,
    }


def _esgotado(dias: list[dict], indice: int) -> dict:
    ultima_data = dias[-1]["data"] if dias else None
    return {
        "status": "ESGOTADO", "total_dias": len(dias), "indice_atual": indice,
        "proxima_data_busca": ultima_data,
        "aviso": ("Nao ha mais dias no cache. Chame buscar_agenda AGORA com data = proxima_data_busca "
                  "+ 1 dia (mantendo unidade/medico/periodo) para buscar mais vagas. NAO repita os "
                  "dias ja mostrados."),
    }


def processar(cache_row: dict | None, acao: str, data: str | None = None) -> dict:
    if not cache_row or not cache_row.get("agenda_json"):
        return {
            "status": "SEM_CACHE",
            "aviso": "Nenhum cache ativo para esta unidade. Chame buscar_agenda primeiro para carregar a agenda.",
        }

    agenda_json = cache_row.get("agenda_json") or {}
    dias = agenda_json.get("dias") or agenda_json.get("proximos_dias") or []

    try:
        indice = int(cache_row.get("indice_atual") or 0)
    except (TypeError, ValueError):
        indice = 0
    acao = str(acao or "ver").lower().strip()

    if acao == "avancar":
        indice += 1
        if indice >= len(dias):
            return _esgotado(dias, max(0, len(dias) - 1))
    elif acao == "voltar":
        indice = max(0, indice - 1)
    elif acao == "ir_para" and data:
        alvo = str(data or "").strip()
        nome_norm = _norm_nfd(alvo.lower()).strip()
        if nome_norm in _DIAS_MAP:
            alvo_dow = _DIAS_MAP[nome_norm]
            match = next((d for d in dias if _get_day_js(d["data"]) == alvo_dow), None)
            alvo = match["data"] if match else ""

        if not alvo:
            return _data_nao_encontrada(data, len(dias), indice)

        idx = next((i for i, d in enumerate(dias) if d.get("data") == alvo), -1)
        if idx < 0:
            return _data_nao_encontrada(data, len(dias), indice)
        indice = idx

    if indice >= len(dias):
        indice = len(dias) - 1
    if indice < 0:
        indice = 0

    dia_atual = dias[indice] if 0 <= indice < len(dias) else None
    if not dia_atual or not dias:
        return _esgotado(dias, indice)

    return {
        "status": "OK", "indice_atual": indice, "total_dias": len(dias),
        "dias_restantes": len(dias) - indice - 1, "dia": dia_atual,
    }
