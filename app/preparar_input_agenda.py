"""
Port fiel do nó 'Preparar Input Agenda' — DEPLOY/_proposed_Preparar_Input_Agenda.js
(147 linhas, snapshot 12/07/2026). Fase 1 do plano de migração (ver
C:\\Users\\lucas\\.claude\\plans\\unified-coalescing-puppy.md).

Roda antes do agente de navegação/agenda. Só depende de UM input (`$input.first().json` =
`ctx`, tipicamente a saída de `app.injetar_contexto_agendamento.processar`) — sem outros
`$('...')` no JS fonte.

Duas coisas:
  1. Se `eh_confirmacao=False`, `cache_ativo=True` e o cache não ficou obsoleto (médico salvo
     bate com os médicos do `ultimo_dia_exibido`, paciente não pediu outro dia/dia-da-semana
     diferente), injeta `[SLOTS_AGENDA]` no `texto_ia_agenda` — o agente ganha a agenda pronta
     sem precisar chamar `navegar_agenda`. Se `eh_confirmacao=True`, passa o texto que
     `Injetar Contexto Agendamento` já montou, sem tocar.
  2. `AGENDA_SLIM_PRECOMPUTE`: aplica a carência determinística (empurra `coleta_data` pra
     frente se o convênio escolhido bate com o último convênio e a data pedida é anterior à
     carência) e pré-computa datas auxiliares (`proximas` por dia da semana, `dia_slots`,
     `dia_semana_coleta`, `modo_agenda`, `proximo_mesmo_dia`, `data_estendida`) que os agentes
     de agenda/navegação usam pra não ter que fazer conta de data.

Toda aritmética de data usa `date + timedelta` puro (sem fuso): o JS ancora em meio-dia
(`T12:00:00`) exatamente pra evitar cruzar fronteira de UTC ao converter — resultado idêntico
a operar em `date` puro do Python, então não precisei replicar o truque do meio-dia aqui.
"""

from __future__ import annotations

import re
from datetime import date, timedelta

from app.text_utils import _norm

_PADROES_OUTRO = ("tem outro", "outro dia", "outra semana", "outra data", "proxima semana", "semana que vem", "quero outro")

_DIAS_SEMANA = (
    (("segunda", "seg"), 1),
    (("terca", "ter"), 2),
    (("quarta", "qua"), 3),
    (("quinta", "qui"), 4),
    (("sexta", "sex"), 5),
    (("sabado", "sab"), 6),
    (("domingo", "dom"), 0),
)

_DAYS_MAP = ("domingo", "segunda", "terça", "quarta", "quinta", "sexta", "sábado")
_DAYS_MAP_NO_ACCENT = ("domingo", "segunda", "terca", "quarta", "quinta", "sexta", "sabado")
_DOW_KEYS = ("", "seg", "ter", "qua", "qui", "sex", "sab")


def _get_day_js(iso_date: str) -> int:
    """getDay() de `new Date(iso+'T12:00:00')`: domingo=0..sábado=6."""
    y, m, d = (int(p) for p in iso_date.split("-"))
    return (date(y, m, d).weekday() + 1) % 7


def _norm_medico_sem_prefixo(s: str) -> str:
    return re.sub(r"^dr[a]?\.\s*", "", _norm(s)).strip()


def processar(ctx: dict) -> dict:
    ctx = dict(ctx or {})
    NL = "\n"

    texto_ia_agenda = ctx.get("texto_ia") or ""

    texto_norm = _norm(ctx.get("texto_ia") or "")
    eh_outro_dia = any(p in texto_norm for p in _PADROES_OUTRO)

    eh_outro_dia_semana = False
    if ctx.get("coleta_data"):
        coleta_dow = _get_day_js(ctx["coleta_data"])
        for nomes, num in _DIAS_SEMANA:
            if any(n in texto_norm for n in nomes):
                if num != coleta_dow:
                    eh_outro_dia_semana = True
                break

    # FIX_51313: cache de OUTRO médico não pode servir slots obsoletos.
    med_coleta = _norm_medico_sem_prefixo(ctx.get("coleta_medico") or "")
    cache_valido_medico = True
    if med_coleta and med_coleta != "sem preferencia" and ctx.get("ultimo_dia_exibido"):
        meds = ctx["ultimo_dia_exibido"].get("medicos") or []
        fn_coleta = med_coleta.split(" ")[0]
        cache_valido_medico = any(
            (lambda mn: fn_coleta in mn or (mn.split(" ")[0] in fn_coleta))(_norm_medico_sem_prefixo(m.get("medico") or ""))
            for m in meds
        )

    if (
        not ctx.get("eh_confirmacao") and ctx.get("cache_ativo") and cache_valido_medico
        and ctx.get("ultimo_dia_exibido") and ctx["ultimo_dia_exibido"].get("data")
        and not eh_outro_dia and not eh_outro_dia_semana
    ):
        ude = ctx["ultimo_dia_exibido"]
        ano, mes, dia = ude["data"].split("-")
        medicos_txt = NL.join(f"- Dr(a). {m['medico']}: {m['horarios']}" for m in (ude.get("medicos") or []))
        texto_ia_agenda = NL.join([
            "[SLOTS_AGENDA]",
            f"Data: {dia}/{mes}/{ano}",
            medicos_txt,
            "[FIM_SLOTS]",
            "",
            f"Mensagem: {texto_ia_agenda}",
        ])

    if not texto_ia_agenda.strip():
        texto_ia_agenda = "[mensagem sem texto]"

    # ── AGENDA_SLIM_PRECOMPUTE ──────────────────────────────────────────
    cd = ctx.get("coleta_data") or ""

    # FIX_CARENCIA_DETERMINISTICA
    c_esc = _norm(ctx.get("coleta_convenio"))
    c_ult = _norm(ctx.get("ultimo_convenio"))
    if (
        ctx.get("data_minima_carencia") and c_esc and c_ult
        and (c_esc in c_ult or c_ult in c_esc)
        and (not cd or cd < ctx["data_minima_carencia"])
    ):
        cd = ctx["data_minima_carencia"]
        carencia_br = ctx.get("data_minima_carencia_br") or ctx["data_minima_carencia"]
        texto_ia_agenda += (
            NL + f"[CARENCIA: o convênio {ctx.get('coleta_convenio') or ''} tem carência — a busca deve começar em "
            f"{carencia_br}. ⛔ NAO ofereça nem busque datas antes disso. Se o paciente pedir data anterior, "
            "explique a carência.]"
        )

    # PROXIMAS (próxima data de cada dia da semana a partir de cd)
    proximas: dict[str, str] = {}
    if cd:
        y, m, d = (int(p) for p in cd.split("-"))
        base_date = date(y, m, d)
        base_dow = (base_date.weekday() + 1) % 7
        for dow in range(1, 7):
            diff = ((dow - base_dow + 7) % 7) or 7
            proximas[_DOW_KEYS[dow]] = (base_date + timedelta(days=diff)).strftime("%Y-%m-%d")

    # DIA_SLOTS
    dia_slots = ""
    if ctx.get("ultimo_dia_exibido") and ctx["ultimo_dia_exibido"].get("data"):
        dia_slots = _DAYS_MAP_NO_ACCENT[_get_day_js(ctx["ultimo_dia_exibido"]["data"])]

    # DIA_SEMANA_COLETA
    dia_semana_coleta = ""
    if cd:
        dia_semana_coleta = _DAYS_MAP[_get_day_js(cd)]

    # MODO
    modo_agenda = ctx.get("coleta_modo") or 0
    if modo_agenda == 0:
        med = (ctx.get("coleta_medico") or "").lower().strip()
        if med and med not in ("sem preferencia", "sem preferência"):
            modo_agenda = 3
        elif ctx.get("coleta_dia_semana"):
            modo_agenda = 2
        else:
            modo_agenda = 1

    # PROXIMO_MESMO_DIA
    proximo_mesmo_dia = ""
    ude_data = (ctx.get("ultimo_dia_exibido") or {}).get("data") or cd
    if ude_data:
        y, m, d = (int(p) for p in ude_data.split("-"))
        proximo_mesmo_dia = (date(y, m, d) + timedelta(days=7)).strftime("%Y-%m-%d")

    # DATA_ESTENDIDA
    data_estendida = ""
    if cd:
        y, m, d = (int(p) for p in cd.split("-"))
        data_estendida = (date(y, m, d) + timedelta(days=21)).strftime("%Y-%m-%d")

    return {
        **ctx,
        "coleta_data": cd,
        "texto_ia_agenda": texto_ia_agenda,
        "proximas": proximas,
        "dia_slots": dia_slots,
        "dia_semana_coleta": dia_semana_coleta,
        "modo_agenda": modo_agenda,
        "proximo_mesmo_dia": proximo_mesmo_dia,
        "data_estendida": data_estendida,
        "cache_ativo": bool(ctx.get("cache_ativo")) and cache_valido_medico,
    }
