"""
Dispatcher da Fase 3 (ver C:\\Users\\lucas\\.claude\\plans\\unified-coalescing-puppy.md): decide
qual prompt de agente chamar por turno, a partir de `rota_agente`/`intencao_rapida`/
`base["_sub_rota_agenda"]` que `app.er.processar()` já calcula — a peça de fiação que faltava
depois dos 9 prompts (Fase 3) e do port completo do determinístico (Fase 1 estendida).

Mapeamento extraído do grafo real do workflow n8n `oX6ePJbAVF7C0NoX` (nós "Roteador",
"Roteador de Agente", "Switch Pacientes", "Sub-Rota Agenda", via `get_workflow_details`):

    intencao_rapida == "humano"        -> agente_humano (prioridade sobre rota_agente)
    rota_agente == 5                   -> None (fluxo "confirmar presença", 100% determinístico,
                                           já portado em app.formatar_verificar_confirmar — não
                                           passa por LLM, dispatcher não se aplica)
    rota_agente == 4                   -> base["_sub_rota_agenda"]: navegacao/confirmacao/
                                           execucao, fallback "agenda"
    rota_agente == 0                   -> agente_triagem
    rota_agente == 1                   -> agente_cancelamento
    rota_agente == 2                   -> por nº de pacientes (Switch Pacientes): 0->0pac,
                                           1->1pac, >=2->titular
    rota_agente == 3                   -> agente_coleta_terceiro

`PASTA_PROMPTS` aponta pra `prompts/` (ao lado de `app/`, não dentro) — os 9 arquivos
adaptados pra structured output, revisados e aprovados por Lucas.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from openai import OpenAI

from app.agentes import RespostaAgente, chamar_agente
from app.er import ResultadoER

PASTA_PROMPTS = Path(__file__).resolve().parent.parent / "prompts"

AGENTES_POR_ROTA = {
    0: "triagem",
    1: "cancelamento",
    3: "coleta_terceiro",
}

AGENTES_SUB_ROTA_AGENDA = {
    "navegacao": "navegacao",
    "confirmacao": "confirmacao",
    "execucao": "executor",
}


def escolher_agente(resultado: ResultadoER, n_pacientes: int = 0) -> str | None:
    """Retorna a chave do agente (usada em `prompts/agente_{chave}.txt`) pro turno, ou `None`
    se a rota é o fluxo determinístico de confirmar presença (rota_agente == 5), que não chama
    LLM nenhum."""
    if resultado.intencao_rapida == "humano":
        return "humano"

    rota = resultado.rota_agente

    if rota == 5:
        return None

    if rota == 4:
        sub = resultado.base.get("_sub_rota_agenda")
        return AGENTES_SUB_ROTA_AGENDA.get(sub, "agenda")

    if rota == 2:
        if n_pacientes <= 0:
            return "coleta_0pac"
        if n_pacientes == 1:
            return "coleta_1pac"
        return "coleta_titular"

    return AGENTES_POR_ROTA.get(rota, "triagem")


@lru_cache(maxsize=None)
def carregar_prompt(agente: str) -> str:
    """Lê `prompts/agente_{agente}.txt`. Cacheado — os arquivos não mudam em runtime; um
    restart do serviço é o mecanismo de deploy de prompt (igual ao resto do código)."""
    caminho = PASTA_PROMPTS / f"agente_{agente}.txt"
    return caminho.read_text(encoding="utf-8")


def despachar_turno(
    resultado: ResultadoER,
    mensagens: list[dict],
    *,
    n_pacientes: int = 0,
    client: OpenAI | None = None,
) -> tuple[str, RespostaAgente] | None:
    """Escolhe o agente pro turno e chama a OpenAI com o prompt correspondente. Retorna
    `(agente, resposta)`, ou `None` se a rota é determinística (rota_agente == 5 — ver
    `app.formatar_verificar_confirmar`, que quem chama deve invocar nesse caso em vez desta
    função)."""
    agente = escolher_agente(resultado, n_pacientes)
    if agente is None:
        return None
    prompt = carregar_prompt(agente)
    resposta = chamar_agente(prompt, mensagens, client=client)
    return agente, resposta
