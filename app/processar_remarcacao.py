"""
Port fiel do nó 'Processar Remarcação' — DEPLOY/_proposed_Processar_Remarcacao.js
(125 linhas, snapshot 12/07/2026). Fase 1 do plano de migração (ver
C:\\Users\\lucas\\.claude\\plans\\unified-coalescing-puppy.md).

⚠️ HERANÇA DO JS FONTE (comentário do autor original, preservado aqui pra não se perder na
migração): os nomes de campo da consulta (dt/data, hr/hora, md/medico, unid/unidade,
conv/convenio, id/id_agendamento) são um PALPITE EDUCADO baseado no que
`Agente_Cancelamento.txt` referencia — não confirmado contra o shape real da resposta do
sub-workflow (dados de execução ficam redigidos na API do n8n). O `pick()` tolerante a
variações de nome existe por causa dessa incerteza. Este port é fiel ao JS como está — a
confirmação do shape real é trabalho pendente de quem ativar este nó em produção, não algo
que dá pra resolver só portando o código.

Dispatcher determinístico do Agente Remarcação. Roda logo após a busca de consultas ativas
(modo listagem, não cancela nada). Três casos: 0 consultas (cai pro fluxo de agendamento
novo) / 1 consulta (auto-seleciona) / 2+ consultas (pergunta qual, ou interpreta a escolha
se já estava em `sessao_intencao='remarcando_escolher'`).
"""

from __future__ import annotations

import json
import re
import unicodedata

_UNIDADE_PICK_NAMES = ("unid", "unidade", "local")


def _strip_nfd(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s or "") if unicodedata.category(c) != "Mn")


def _pick(obj, *names: str):
    if not isinstance(obj, dict):
        return ""
    for n in names:
        if obj.get(n) not in (None, ""):
            return obj[n]
    return ""


def _bloco_base(base: dict, overrides: dict) -> dict:
    d = {
        "t": base.get("coleta_terceiro") == "true",
        "i": "triagem",
        # FIX_REMARCACAO_DONO
        "d": base.get("nome_dependente") or base.get("nome") or "",
        "c": base.get("cpf_dependente") or base.get("cpf") or "",
        "n": base.get("nascimento_dependente") or base.get("nascimento") or "",
        "conv": "", "unid": "", "dt": "", "per": "", "h": "", "med": "", "id": "",
        "motivo": "", "modo": 0, "ds": "",
    }
    d.update(overrides)
    return d


def _dollar_bloco(d: dict) -> str:
    return "$$$" + json.dumps(d, separators=(",", ":"), ensure_ascii=False)


def _normalizar_consultas(sub_workflow_items: list[dict]) -> list[dict]:
    raw_items = sub_workflow_items or []
    if len(raw_items) == 1 and isinstance(raw_items[0], dict) and isinstance(raw_items[0].get("consultas"), list):
        return raw_items[0]["consultas"]
    if len(raw_items) == 1 and isinstance(raw_items[0], list):
        return raw_items[0]
    return [i for i in raw_items if _pick(i, "id", "id_agendamento") != ""]


def _processar_escolha(base: dict, texto_usuario: str, consulta: dict) -> dict:
    dt_antiga = _pick(consulta, "dataBR", "dt", "data")  # dataBR: shape real confirmado no 58313
    hr_antiga = _pick(consulta, "hr", "hora")
    md_antigo = _pick(consulta, "md", "medico", "nome_medico")
    id_antigo = _pick(consulta, "id", "id_agendamento")
    # FIX_UNIDADE_REMARCACAO
    unid_raw = str(_pick(consulta, *_UNIDADE_PICK_NAMES)).lower()
    unid_raw = re.sub(r"[̀-ͯ]", "", _strip_nfd(unid_raw))
    unid_antiga = "Vila Olímpia" if "vila" in unid_raw else ("Tatuapé" if "tatu" in unid_raw else "")
    conv_antigo = _pick(consulta, "conv", "convenio")

    txt_per = _strip_nfd(texto_usuario)
    periodo_detectado = ""
    if re.search(r"manha|cedo|antes do almoco", txt_per):
        periodo_detectado = "manha"
    elif re.search(r"tarde|final do dia|depois do almoco", txt_per):
        periodo_detectado = "tarde"

    # FIX_REMARC_PERGUNTA_UNIDADE (58435, decisão Lucas)
    if not unid_antiga:
        texto_u = (
            f"Beleza! Vamos remarcar sua consulta de {dt_antiga} às {hr_antiga} com Dr(a). {md_antigo} 😊\n"
            "Temos dois endereços de atendimento, qual a melhor unidade para você?\n"
            "Digite o número correspondente:\n\n1️⃣ Vila Olímpia\n2️⃣ Tatuapé"
        )
        bloco_u = _dollar_bloco(_bloco_base(base, {
            "i": "coleta", "med": md_antigo, "conv": conv_antigo, "per": periodo_detectado,
            "id_ag_antigo": id_antigo, "dt_antiga": dt_antiga, "hr_antiga": hr_antiga, "md_antiga": md_antigo,
        }))
        return {"output": f"{texto_u}\n\n{bloco_u}"}

    texto = (
        f"Beleza! Vamos remarcar sua consulta de {dt_antiga} às {hr_antiga} com Dr(a). {md_antigo}. "
        + ("Vou buscar horários pra você! 😊" if periodo_detectado else "Prefere de manhã ou de tarde? 😊")
    )
    bloco = _dollar_bloco(_bloco_base(base, {
        "i": "agenda" if periodo_detectado else "coleta",
        "unid": unid_antiga, "med": md_antigo, "conv": conv_antigo, "per": periodo_detectado,
        "id_ag_antigo": id_antigo, "dt_antiga": dt_antiga, "hr_antiga": hr_antiga, "md_antiga": md_antigo,
    }))
    return {"output": f"{texto}\n\n{bloco}"}


def processar(extrair_rota: dict, mensagem_agrupada: str, sub_workflow_items: list[dict] | None) -> dict:
    base = extrair_rota or {}
    texto_usuario = (mensagem_agrupada or "").lower().strip()

    is_escolher_turn = base.get("sessao_intencao") == "remarcando_escolher"
    consultas = _normalizar_consultas(sub_workflow_items)

    # CASO 0: nenhuma consulta ativa
    if not consultas:
        texto = (
            "Não encontrei nenhuma consulta ativa no seu nome pra remarcar. Vamos agendar uma nova! 😊\n\n"
            "Temos dois endereços de atendimento, qual a melhor unidade para você?\n"
            "Digite o número correspondente:\n\n1️⃣ Vila Olímpia\n2️⃣ Tatuapé"
        )
        bloco = _dollar_bloco(_bloco_base(base, {"i": "coleta"}))
        return {"output": f"{texto}\n\n{bloco}"}

    # CASO 2+: precisa perguntar qual (ou processar a resposta dessa pergunta)
    if len(consultas) >= 2:
        if is_escolher_turn:
            try:
                sel = int(texto_usuario.strip())
            except ValueError:
                sel = None
            if sel is not None and 1 <= sel <= len(consultas):
                return _processar_escolha(base, texto_usuario, consultas[sel - 1])
            # seleção inválida → re-lista

        menu = "\n".join(
            f"{idx + 1}. {_pick(c, 'dt', 'data')} às {_pick(c, 'hr', 'hora')} com Dr(a). {_pick(c, 'md', 'medico', 'nome_medico')}"
            for idx, c in enumerate(consultas)
        )
        texto = (
            ("Não entendi. " if is_escolher_turn else "Você tem mais de uma consulta marcada. ")
            + f"Qual delas você quer remarcar? Digite o número:\n\n{menu}"
        )
        bloco = _dollar_bloco(_bloco_base(base, {"i": "remarcando_escolher"}))
        return {"output": f"{texto}\n\n{bloco}"}

    # CASO 1: consulta única
    return _processar_escolha(base, texto_usuario, consultas[0])
