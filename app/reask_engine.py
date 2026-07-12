"""
Port fiel do nó 'Reask Engine' — DEPLOY/_proposed_Reask_Engine.js (94 linhas, snapshot
12/07/2026). Fase 1 do plano de migração (ver
C:\\Users\\lucas\\.claude\\plans\\unified-coalescing-puppy.md).

Gera a mensagem determinística que o paciente recebe quando o State Validator bloqueia
(REASK) um campo. Único input: a saída de `app.state_validator.validar_estado` (mais os
campos de coleta espalhados nela). Mapa `sv_reason` → texto fixo, com dois casos que fazem
conta em cima do `sv_detail`/campos (dia da semana da data, período válido oposto ao rejeitado).

Casos `convenio_invalido_unidade` e `omint_medico_invalido` no switch nunca são de fato
emitidos por `app.state_validator` hoje (o guard 3 do SV foi removido — ver docstring de
`validar_estado`; `omint_medico_invalido` é nome legado que nem chegou a existir no SV atual)
— mantidos aqui mesmo assim, fiéis ao JS original, não removidos por conta própria.
"""

from __future__ import annotations

import re
from datetime import date

_DSN = {0: "domingo", 1: "segunda", 2: "terça", 3: "quarta", 4: "quinta", 5: "sexta", 6: "sábado"}
_DSN2 = {
    "seg": "segunda", "ter": "terça", "qua": "quarta", "qui": "quinta", "sex": "sexta",
    "segunda": "segunda", "terca": "terça", "quarta": "quarta", "quinta": "quinta", "sexta": "sexta",
}


def _fmt_dt(d: str) -> str:
    if not d or not re.match(r"^\d{4}-\d{2}-\d{2}$", d):
        return d
    y, m, day = d.split("-")
    return f"{day}/{m}/{y}"


def _get_day_js(iso_date: str) -> int:
    y, m, d = (int(p) for p in iso_date.split("-"))
    return (date(y, m, d).weekday() + 1) % 7


def processar(sv: dict) -> dict:
    sv = sv or {}
    reason = sv.get("sv_reason") or ""

    unid = sv.get("unidade_coleta") or ""
    med = sv.get("medico_coleta") or ""
    conv = sv.get("convenio") or ""
    dt = sv.get("data_coleta") or ""
    per = sv.get("periodo_coleta") or ""
    ds = sv.get("dia_semana_coleta") or ""

    if reason in ("confirmacao_sem_horario", "execucao_sem_horario"):
        msg = "Qual horário você prefere? 😊"

    elif reason == "data_no_passado":
        msg = f"Não consigo agendar em datas passadas ({_fmt_dt(dt)}). Qual data prefere? 😊"

    elif reason == "dt_ds_inconsistente":
        dc = _DSN[_get_day_js(dt)] if dt else ""
        msg = (
            f"Só para confirmar: {_fmt_dt(dt)} é uma {dc}-feira. Confirma? 😊"
            if dc
            else "Pode confirmar a data desejada? 😊"
        )

    elif reason == "convenio_invalido_unidade":
        msg = f"{conv} não é aceito em {unid}. Prefere:\n1️⃣ Mudar para Vila Olímpia\n2️⃣ Usar outro convênio 😊"

    elif reason == "medico_invalido_unidade":
        msg = f"{med} não atende em {unid}. Deseja:\n1️⃣ Escolher outro médico em {unid}\n2️⃣ Mudar para a outra unidade 😊"

    elif reason == "periodo_invalido_medico_dia":
        # FIX_65922: 'per' é o período REJEITADO pelo validator — o médico atende o OPOSTO.
        per_valida = "tarde" if per == "manha" else "manhã"
        ds_n = _DSN2.get(ds, ds)
        msg = f"{med} atende {ds_n}-feira apenas à {per_valida} em {unid}. Pode ser? 😊"

    elif reason == "troca_unidade_ilegal":
        msg = f"Só para confirmar: você quer mudar o atendimento para {unid}? 😊"

    elif reason == "convenio_interno_vazando":
        msg = "Qual convênio você vai usar?\n• Porto Seguro\n• Itaú\n• Bradesco\n• Omint\n• Particular 😊"

    elif reason == "nascimento_invalido":
        msg = "Não entendi essa data de nascimento 😅 Pode informar no formato dia/mês/ano? Ex: 17/12/1998"

    elif reason == "cpf_invalido":
        msg = "Esse CPF não parece completo (precisa ter 11 números) 😅 Pode conferir e reenviar?"

    elif reason == "medico_interno_vazando":
        msg = "Com qual médico você prefere?\n1️⃣ Primeiro horário disponível\n2️⃣ Escolher especialista\n3️⃣ Já tenho médico de preferência 😊"

    elif reason in ("omint_medico_invalido", "omint_premium_medico"):
        msg = "Pelo Omint Premium atendemos com a Dra. Giseli, o Dr. Elias ou o Dr. José Emmanuel — nas duas unidades 😊 Com qual deles prefere?"

    elif reason == "omint_skill_torcuato":
        msg = "O Omint Skill e Corporation são atendidos apenas pelo Dr. Torcuato Sanchez Rojas Neto, na Vila Olímpia 😊 Deseja agendar com ele?"

    else:
        msg = "Desculpe, houve um problema. Pode repetir? 😊"

    return {"mensagem_final": msg}
