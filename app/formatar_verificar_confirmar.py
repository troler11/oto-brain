"""
Port fiel do nó 'Formatar Verificar Confirmar' — DEPLOY/_proposed_Formatar_Verificar_Confirmar.js
(68 linhas, snapshot 12/07/2026). Fase 1 do plano de migração (ver
C:\\Users\\lucas\\.claude\\plans\\unified-coalescing-puppy.md).

FIX_CONFIRMA_AUTO: decisor da confirmação de presença. Filtra só consultas PENDENTES (as já
confirmadas saem da lista de escolha; se todas já confirmadas → aviso). Sinal FORTE
(`_confirma_direto` do Extrair Rota) + exatamente 1 pendente (ou número escolhido na lista) →
`auto_confirmar=True`, pulando a pergunta "Deseja confirmar...?" — o `output` sempre vem
preenchido com a pergunta como fallback, pra ser seguro independente de existir ou não o IF
"Auto Confirmar?" no grafo do n8n.

Três inputs: `r` (saída da busca de consultas, `$input.first().json`), `extrair_rota`
(`$('Extrair Rota').first().json` — `_confirma_direto`/`sessao_intencao`/`coleta_conv_fail`) e
`indice` (`$('Preparar Verificar').first().json.indice` — resposta numérica a uma lista já
exibida).

Módulo também agrupa 3 nós pequenos do MESMO fluxo "confirmar presença" (DEPLOY não tem
arquivo `_proposed_` isolado que justifique um módulo próprio pra cada um):
  - `preparar_confirmar()` — DEPLOY/_proposed_Preparar_Confirmar.js (7 linhas): resolve o
    `id_agendamento` a passar pro sub-workflow TiSaude (caminho auto vs. legado via sessão).
  - `formatar_escolher_titular()` — DEPLOY/_proposed_Formatar_Escolher_Titular.js (12 linhas):
    lista os titulares/pacientes numerados quando há mais de um, pra escolher de quem confirmar.
  - `formatar_resposta_confirmar()` — DEPLOY/_proposed_Formatar_Resposta_Confirmar.js (15
    linhas): mensagem final de sucesso, detalhada se veio do auto-confirmar, curta no legado.
"""

from __future__ import annotations

import json
import re


def _ja_confirmada(c: dict) -> bool:
    return c.get("status_id") == 3 or bool(re.search(r"confirmad", str(c.get("status_nome")), re.IGNORECASE))


def _linha(c: dict) -> str:
    return f"{c.get('dataBR')} às {c.get('hora')} com Dr(a). {c.get('medico')}"


def _pergunta(c: dict) -> str:
    return f"Deseja confirmar sua presença na consulta do dia {_linha(c)}? 😊"


def _parseint_js(v) -> int:
    m = re.match(r"^\s*[-+]?\d+", str(v if v is not None else ""))
    return int(m.group(0)) if m else 0


def processar(r: dict, extrair_rota: dict | None, indice) -> dict:
    r = r or {}
    consultas = r.get("consultas") or []
    er = extrair_rota or {}
    direto = bool(er.get("_confirma_direto"))
    indice = _parseint_js(indice)

    pend = [c for c in consultas if not _ja_confirmada(c)]

    texto = ""
    i = ""
    id_ = ""
    auto = None

    if not consultas:
        texto = "Não encontrei nenhuma consulta em seu nome para confirmar. Se quiser agendar, é só me dizer! 😊"
        i = "triagem"
    elif indice >= 1:
        c = pend[indice - 1] if 0 <= indice - 1 < len(pend) else None
        if not c:
            texto = "Não entendi qual consulta. Por favor, responda com o número da consulta. 😊"
            i = "confirmar_presenca_lista"
        elif direto:
            auto = c
        else:
            texto = _pergunta(c)
            i = "confirmar_presenca"
            id_ = str(c.get("id"))
    elif not pend:
        if len(consultas) == 1:
            texto = f"Sua presença na consulta do dia {_linha(consultas[0])} já está confirmada! ✅"
        else:
            linhas = "\n".join(f"• {_linha(c)}" for c in consultas)
            texto = f"Todas as suas consultas já estão confirmadas! ✅\n{linhas}"
        i = "concluido"
    elif len(pend) == 1:
        if direto:
            auto = pend[0]
        else:
            texto = _pergunta(pend[0])
            i = "confirmar_presenca"
            id_ = str(pend[0].get("id"))
    else:
        linhas = "\n".join(f"{idx + 1}. {_linha(c)}" for idx, c in enumerate(pend))
        texto = f"Você tem {len(pend)} consultas aguardando confirmação:\n{linhas}\n\nQual deseja confirmar? Responda com o número. 😊"
        i = "confirmar_presenca_lista"

    # FIX_LOOP_CONFIRMAR
    if i == "confirmar_presenca_lista":
        cf = (_parseint_js(er.get("coleta_conv_fail")) + 1) if er.get("sessao_intencao") == "confirmar_presenca_lista" else 1
    else:
        cf = 0

    if auto:
        bloco_fb = "$$$" + json.dumps(
            {"t": False, "i": "confirmar_presenca", "d": "", "c": "", "n": "", "conv": "", "id": str(auto.get("id")), "motivo": "", "cf": 0},
            separators=(",", ":"), ensure_ascii=False,
        )
        return {
            "auto_confirmar": True,
            "id_agendamento": str(auto.get("id")),
            "consulta_dataBR": auto.get("dataBR"),
            "consulta_hora": auto.get("hora"),
            "consulta_medico": auto.get("medico"),
            "output": f"{_pergunta(auto)}\n\n{bloco_fb}",
        }

    bloco = "$$$" + json.dumps(
        {"t": False, "i": i, "d": "", "c": "", "n": "", "conv": "", "id": id_, "motivo": "", "cf": cf},
        separators=(",", ":"), ensure_ascii=False,
    )
    return {"auto_confirmar": False, "output": f"{texto}\n\n{bloco}"}


def preparar_confirmar(input_item: dict | None, extrair_rota: dict | None) -> dict:
    """DEPLOY/_proposed_Preparar_Confirmar.js — resolve o id_agendamento a passar pro
    sub-workflow TiSaude: caminho auto (id vem do próprio item de Formatar Verificar Confirmar)
    ou caminho legado (id vem da sessão, via Extrair Rota)."""
    j = input_item or {}
    er = extrair_rota or {}
    id_ = (j.get("id_agendamento") if (j.get("auto_confirmar") and j.get("id_agendamento")) else "") or er.get("coleta_id_agendamento") or ""
    return {"id_agendamento": str(id_).strip()}


def formatar_escolher_titular(extrair_rota: dict | None, pacientes: list[dict] | None) -> dict:
    """DEPLOY/_proposed_Formatar_Escolher_Titular.js — lista os titulares/pacientes numerados
    quando há mais de um, pra escolher de quem confirmar a presença. FIX_LOOP_CONFIRMAR: cf
    conta as exibições (1ª = 1, re-exibição +1) — Extrair Rota transfere pra atendente quando a
    seleção inválida chega com cf >= 2."""
    er = extrair_rota or {}
    pacientes = pacientes or []
    linhas = "\n".join(f"{i + 1}. {p.get('nome') or f'Titular {i + 1}'}" for i, p in enumerate(pacientes))
    texto = f"Para quem você quer confirmar a presença? 😊\n{linhas}\n\nResponda com o número."
    cf = (_parseint_js(er.get("coleta_conv_fail")) + 1) if er.get("sessao_intencao") == "confirmar_presenca_escolher" else 1
    bloco = "$$$" + json.dumps(
        {"t": False, "i": "confirmar_presenca_escolher", "d": "", "c": "", "n": "", "conv": "", "id": "", "motivo": "", "cf": cf},
        separators=(",", ":"), ensure_ascii=False,
    )
    return {"output": f"{texto}\n\n{bloco}"}


def formatar_resposta_confirmar(formatar_verificar_confirmar_out: dict | None, extrair_rota: dict | None) -> dict:
    """DEPLOY/_proposed_Formatar_Resposta_Confirmar.js — mensagem final de sucesso: detalhada
    (data/hora/médico) quando veio do auto-confirmar, curta no caminho legado."""
    v = formatar_verificar_confirmar_out or {}
    det = v if v.get("auto_confirmar") else None
    er = extrair_rota or {}
    id_ = (det.get("id_agendamento") if det else "") or er.get("coleta_id_agendamento") or ""
    id_ = str(id_).strip()
    texto = (
        f"Prontinho! Presença confirmada para o dia {det['consulta_dataBR']} às {det['consulta_hora']} "
        f"com Dr(a). {det['consulta_medico']} ✅ Até lá!"
        if det
        else "Presença confirmada! ✅ Até logo!"
    )
    bloco = "$$$" + json.dumps(
        {"t": False, "i": "concluido", "d": "", "c": "", "n": "", "conv": "", "id": id_, "motivo": ""},
        separators=(",", ":"), ensure_ascii=False,
    )
    return {"output": f"{texto}\n\n{bloco}"}
