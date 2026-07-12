"""
Port fiel do nó 'State Validator' — DEPLOY/_proposed_State_Validator.js (150 linhas, snapshot
12/07/2026). Fase 1 do plano de migração (ver
C:\\Users\\lucas\\.claude\\plans\\unified-coalescing-puppy.md).

Roda DEPOIS do agente executor (valida o que o agente extraiu de `inp` antes de deixar seguir
pra tool/persistência). Decide ALLOW / REASK (pede de novo ao paciente) / BLOCK (descarta o
campo interno vazado, sem re-perguntar). Guards, em ordem:
  1. Avanço indevido: i=confirmacao sem horário, ou i=execucao sem horário nenhum lugar.
  2. Data válida: não pode ser no passado; se dia_semana veio junto, tem que bater com a data
     (senão o agente alucinou um dos dois). ENCADEADO via elif do guard 1 no JS original — só
     roda se nenhuma das duas condições do guard 1 disparou. Preservado aqui com a mesma
     exclusividade mútua (bloco único ALLOW/REASK, não dois ifs independentes).
  3. (removido no JS fonte — convênio inválido por unidade agora é 100% resolvido no Extrair
     Rota; comentário mantido pra rastrear o motivo, sem código correspondente aqui.)
  4. Médico válido pra unidade + período válido pro médico naquele dia da semana (contra GRADE).
  5. FIX_OMINT_V2: Omint Premium só Giseli/Elias/Jose; Skill/Corporation só Torcuato (Vila
     Olímpia — Torcuato em Tatuapé já cai no guard 4).
  6. FIX_NASCIMENTO_INVALIDO / FIX_CPF_INVALIDO: sentinelas de formato solto (não é o dígito
     verificador oficial — de propósito, ver comentário do JS: aqui só bate 11 dígitos, não
     valida o CPF de fato; a validação forte fica pros guards de identidade do ER).
  7. Campos internos não podem vazar pro paciente (RESET_CONV, __CLEAR__ como médico) → BLOCK.
  8. Troca de unidade sem a tag `[TROCA UNIDADE` do ER autorizando → BLOCK.

`GRADE`/`OMINT_MEDICOS`/`DS_MAP` são tabelas PRÓPRIAS deste node — não são byte-idênticas às
tabelas de grade do ER (lá são pra formatação de texto; aqui é estrutura médico→dia→períodos
pra validação), então não foram reaproveitadas de `er.py` (regra: só reusar quando idêntico,
não quando só parecido). `CONV_INVALIDO` existe no JS mas nunca é lido em lugar nenhum
(dead code do guard 3 removido) — portado como constante não usada, fiel ao original, não
"limpo" por conta própria.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

from app.text_utils import _norm

GRADE = {
    "Vila Olímpia": {
        "giseli": {"ter": ["manha", "tarde"], "qua": ["manha"], "sex": ["manha"]},
        "elias": {"ter": ["tarde"], "qua": ["manha", "tarde"]},
        "jose": {"seg": ["manha", "tarde"], "qua": ["manha"], "qui": ["manha", "tarde"]},
        "stephanie": {"seg": ["manha", "tarde"], "ter": ["manha"], "qua": ["tarde"]},
        "juliana": {"seg": ["tarde"], "sex": ["tarde"]},
        "torcuato": {"qua": ["tarde"], "qui": ["manha", "tarde"], "sex": ["manha", "tarde"]},
        "fernanda": {"qui": ["tarde"]},
        "caio": {"ter": ["manha"]},
    },
    "Tatuapé": {
        "elias": {"seg": ["manha", "tarde"], "sex": ["manha"]},
        "jose": {"ter": ["manha", "tarde"]},
        "caio": {"qua": ["manha", "tarde"]},
        "giseli": {"qui": ["manha", "tarde"]},
        "fernanda": {"sex": ["tarde"]},
    },
}
CONV_INVALIDO = {"Tatuapé": ["bradesco"]}  # FIX_OMINT_AMBAS: Omint aceito no Tatuape (com restrição de médico)
OMINT_MEDICOS = ("giseli", "elias", "jose")  # FIX_OMINT_MEDICO: Omint só com estes 3
DS_MAP = {0: "dom", 1: "seg", 2: "ter", 3: "qua", 4: "qui", 5: "sex", 6: "sab"}


def _norm_med(s: str) -> str:
    sem_prefixo = re.sub(r"^dr[a]?\.?\s*", "", _norm(s), flags=re.IGNORECASE)
    return sem_prefixo.split(" ")[0]


def _eh_sem_pref(s: str) -> bool:
    return _norm(s) == "sem preferencia"


@dataclass
class ResultadoStateValidator:
    sv_result: str
    sv_reason: str
    sv_field: str
    sv_detail: str
    inp: dict = field(default_factory=dict)


def validar_estado(
    inp: dict,
    base: dict,
    er_output: dict,
    hoje: date | None = None,
) -> ResultadoStateValidator:
    """`inp` = saída do agente executor a validar. `base` = contexto carregado no início do
    turno ('Montar Contexto'). `er_output` = saída do Extrair Rota NESTE turno ('Extrair
    Rota') — usado só pro guard 8 (troca de unidade)."""
    if hoje is None:
        hoje = date.today()

    unid = inp.get("unidade_coleta") or ""
    dt = inp.get("data_coleta") or ""
    # FIX_PER_FROM_HORARIO: se ha horario especifico (ex "15:20", de lista real), derivar periodo
    # do horario (>=12h=tarde) em vez de confiar no per emitido pelo agente (vinha stale "manha"
    # => REASK falso).
    _h_match_per = re.match(r"^(\d{1,2}):(\d{2})", inp.get("horario_coleta") or "")
    per = ("tarde" if int(_h_match_per.group(1)) >= 12 else "manha") if _h_match_per else (inp.get("periodo_coleta") or "")
    conv = inp.get("convenio") or ""
    h = inp.get("horario_coleta") or ""
    med = inp.get("medico_coleta") or ""
    ds = inp.get("dia_semana_coleta") or ""
    i = (inp.get("dados") or {}).get("i") or ""

    sv_result = "ALLOW"
    sv_reason = ""
    sv_field = ""
    sv_detail = ""

    # 1. Avanço indevido / 2. Data válida — mesmo if/elif do JS: guard 2 só roda se guard 1 não disparou.
    if i == "confirmacao" and not h:
        sv_result, sv_reason, sv_field, sv_detail = "REASK", "confirmacao_sem_horario", "h", "i=confirmacao sem h"
    elif i == "execucao" and not base.get("coleta_horario") and not h:
        sv_result, sv_reason, sv_field, sv_detail = "REASK", "execucao_sem_horario", "h", "execucao sem coleta_horario"
    elif dt and re.match(r"^\d{4}-\d{2}-\d{2}$", dt):
        dt_date = date.fromisoformat(dt)
        if dt_date < hoje:
            sv_result, sv_reason, sv_field, sv_detail = "REASK", "data_no_passado", "dt", f"Data {dt} anterior a hoje"
        elif ds and ds != "__CLEAR__":  # FIX_66232: __CLEAR__ e marcador de limpeza, nao valor
            dt_ds = DS_MAP[(dt_date.weekday() + 1) % 7]  # Python Mon=0..Sun=6 -> JS getDay() Sun=0..Sat=6
            if dt_ds and dt_ds != ds:
                sv_result, sv_reason, sv_field, sv_detail = "REASK", "dt_ds_inconsistente", "ds", f"{dt} é {dt_ds} mas ds={ds}"

    # 3. Convenio invalido por unidade -> REMOVIDO (fix loop 50241):
    # Bradesco/Omint + Tatuape agora e tratado 100% no Extrair Rota
    # (FIX_BRADESCO_TA_DETERMINISTIC + FIX_AUTOSWITCH_3CAMINHOS), que persiste o
    # convenio (via ALLOW) e resolve a troca no turno seguinte. O REASK aqui
    # duplicava a mensagem E impedia a persistencia -> causava loop.

    # 4. Medico valido por unidade
    if sv_result == "ALLOW" and med and unid and not _eh_sem_pref(med) and med != "__CLEAR__":
        uk = "Tatuapé" if "Tatu" in unid else "Vila Olímpia"
        gu = GRADE.get(uk, {})
        mk = _norm_med(med)
        key = next((k for k in gu if k.startswith(mk) or mk.startswith(k)), None)
        if not key:
            sv_result, sv_reason, sv_field, sv_detail = "REASK", "medico_invalido_unidade", "med", f"{med} não atende em {unid}"
        # FIX_66232 (exec 66232): per='__CLEAR__' (canal de limpeza do EIF1) era validado como
        # periodo literal → sv_detail "nao atende __CLEAR__ na seg" → REASK indevido em cima de
        # uma resposta CERTA (lista de horarios do FIX_66201). So manha/tarde validam; ds tambem
        # exclui o marcador.
        elif per in ("manha", "tarde") and ds and ds != "__CLEAR__" and gu.get(key):
            pers_dia = gu[key].get(ds)
            if pers_dia and per not in pers_dia:
                sv_result, sv_reason, sv_field, sv_detail = (
                    "REASK", "periodo_invalido_medico_dia", "per", f"{med} não atende {per} na {ds} em {unid}",
                )

    # 5. FIX_OMINT_V2: validacao por CATEGORIA do plano Omint.
    # Premium → Giseli/Elias/Jose (ambas unidades). Skill/Corporation → SOMENTE Torcuato (Vila
    # Olimpia; Torcuato em Tatuape ja e barrado pela regra 4). 'Omint' puro ou 'OMINT?' = categoria
    # ainda pendente (Extrair Rota esta perguntando) → NAO validar medico aqui.
    if sv_result == "ALLOW" and conv and "omint" in conv.lower() and med and not _eh_sem_pref(med) and med != "__CLEAR__":
        _conv_o = conv.lower()
        mk_o = _norm_med(med)
        if "premium" in _conv_o:
            if not any(mk_o.startswith(m) or m.startswith(mk_o) for m in OMINT_MEDICOS):
                sv_result, sv_reason, sv_field, sv_detail = (
                    "REASK", "omint_premium_medico", "med", f"{med} nao atende Omint Premium (so Giseli/Elias/Jose)",
                )
        elif "skill" in _conv_o or "corporation" in _conv_o:
            if not (mk_o.startswith("torcuato") or "torcuato".startswith(mk_o)):
                sv_result, sv_reason, sv_field, sv_detail = (
                    "REASK", "omint_skill_torcuato", "med", f"{med} nao atende {conv} (so Dr. Torcuato, Vila Olimpia)",
                )

    # FIX_NASCIMENTO_INVALIDO: nascimento sem digitos (ex "jjjj") nao e uma data valida.
    # Aceita formatos livres (17/12/1998, 1998-12-17, "17 de dezembro de 1998") desde que
    # tenha digitos plausiveis de data. So dispara se o campo veio preenchido neste turno.
    # FIX_58730: '__CLEAR__' e sentinela INTERNA de limpeza (terceiro puro limpa residual —
    # FIX_TERCEIRO_LIMPA_RESIDUAL), nao input do paciente: passa direto (o CASE do SQL zera a
    # coluna). Sem isso o REASK "Nao entendi essa data" atropelava o pedido de dados do terceiro.
    if sv_result == "ALLOW" and inp.get("nascimento_dependente") and str(inp["nascimento_dependente"]) != "__CLEAR__":
        nasc = str(inp["nascimento_dependente"]).strip()
        tem_digitos = bool(re.search(r"\d", nasc))
        parece_data = bool(re.search(r"\d{1,2}\D{1,3}\d{1,2}\D{1,3}\d{2,4}", nasc)) or bool(re.search(r"\d{4}", nasc))
        if not tem_digitos or not parece_data:
            sv_result, sv_reason, sv_field, sv_detail = "REASK", "nascimento_invalido", "n", f'"{nasc}" nao parece data valida'

    # FIX_CPF_INVALIDO: CPF sem 11 digitos nao e CPF valido (comum: paciente manda a data de
    # nascimento em DDMMYYYY, 8 digitos, no campo errado, ex exec 56939). Bloqueia e pede de novo.
    if sv_result == "ALLOW" and inp.get("cpf_dependente") and str(inp["cpf_dependente"]) != "__CLEAR__":  # FIX_58730: sentinela de limpeza passa
        _cpf_dig = re.sub(r"\D", "", str(inp["cpf_dependente"]))
        if len(_cpf_dig) != 11:
            sv_result, sv_reason, sv_field, sv_detail = (
                "REASK", "cpf_invalido", "c", f'"{inp["cpf_dependente"]}" tem {len(_cpf_dig)} digitos, CPF precisa ter 11',
            )

    # 6. Campos internos nao persistem
    # FIX_50654: 'PART?' NAO entra mais no BLOCK. 'PART?' e' estado transitorio legitimo
    # (paciente escolheu particular, aguardando confirmacao do preco). Os prompts tratam
    # CONV_SALVO='PART?' (GATE SALVO o exclui; Excecao "sim"->Particular depende dele).
    # Bloquear PART? descartava a mensagem de precos do agente e disparava reask
    # "Qual convenio?" via Reask Engine -> loop. RESET_CONV mantido (reask e' apropriado).
    if sv_result == "ALLOW" and conv == "RESET_CONV":
        sv_result, sv_reason, sv_field, sv_detail = "BLOCK", "convenio_interno_vazando", "conv", conv
    if sv_result == "ALLOW" and med == "__CLEAR__":
        sv_result, sv_reason, sv_field, sv_detail = "BLOCK", "medico_interno_vazando", "med", "__CLEAR__"

    # 7. Troca ilegal de unidade
    unid_salva = (er_output or {}).get("coleta_unidade") or base.get("coleta_unidade") or ""
    _tag_troca = "[TROCA UNIDADE" in ((er_output or {}).get("texto_ia") or "")
    if sv_result == "ALLOW" and unid and unid_salva and unid != unid_salva and not _tag_troca:
        sv_result, sv_reason, sv_field, sv_detail = "BLOCK", "troca_unidade_ilegal", "unid", f"{unid_salva} → {unid} sem tag"

    return ResultadoStateValidator(sv_result, sv_reason, sv_field, sv_detail, inp)
