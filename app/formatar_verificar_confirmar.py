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
