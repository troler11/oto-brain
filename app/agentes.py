"""
Fase 3 do plano de migração (ver C:\\Users\\lucas\\.claude\\plans\\unified-coalescing-puppy.md):
agentes MINI saem dos nós LangChain do n8n pro serviço, via OpenAI SDK com structured output —
schema validado pelo próprio provedor, não mais o eco de bloco `$$$` em texto livre que causava
telefone/data/convênio ecoados errado (causa raiz #1 do diagnóstico original do plano).

`RespostaAgente` espelha os mesmos campos curtos do bloco `$$$` legado (i/t/d/c/n/conv/unid/dt/
per/h/med/id/motivo/modo/ds/cf/email) DE PROPÓSITO — `empacotar_para_eif1()` embrulha a
resposta no shape `{"output": ..., "meta": {...}}` que `app.eif1.processar()` (Modo A: JSON
puro) já sabe interpretar, então o parsing/canonicalização que já existe e está testado em
app/eif1.py continua funcionando sem NENHUMA mudança — só troca a origem do "raw" (texto cru
de um nó LangChain do n8n → JSON validado por schema desta chamada).

Os 9 prompts de agente (`prompts/agente_*.txt`) e o classificador (`IAOutputClassificador`,
port do nó "AI Agent" que roda ANTES do Extrair Rota, `prompts/ai_agent_classificador.txt`)
foram adaptados desse jeito e aprovados por Lucas — ver `app.dispatcher` pro roteamento dos 9,
e `classificar_intencao()` abaixo pro classificador.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from openai import OpenAI
from pydantic import BaseModel, Field

from app.config import OPENAI_API_KEY
from app.template_engine import renderizar

MODEL_PADRAO = "gpt-4o-2024-08-06"


class EstadoConsulta(BaseModel):
    """Mesmos campos curtos do bloco `$$$` legado — nomes mantidos de propósito pra bater 1:1
    com o que `app.eif1.processar()` já extrai (`extraido.get("i")`, `.get("d")`, etc.)."""

    i: str = Field(description="Intenção emitida pelo agente: triagem/coleta/agenda/navegacao/confirmacao/execucao/cancelando/humano/concluido/oferta_humano/oferta_agendar/remarcando/confirmar_presenca/...")
    t: bool = False
    d: str = ""
    c: str = ""
    n: str = ""
    conv: str = ""
    unid: str = ""
    dt: str = ""
    per: str = ""
    h: str = ""
    med: str = ""
    id: str = ""
    motivo: str = ""
    modo: int = 0
    ds: str = ""
    cf: int = -1
    email: str = ""
    nome_paciente: str = ""  # usado só pelo Agente Humano, na confirmação de transferência


class RespostaAgente(BaseModel):
    mensagem: str
    estado: EstadoConsulta


MAX_TOOL_TURNS = 6


def chamar_agente(
    system_prompt: str,
    mensagens: list[dict],
    *,
    client: OpenAI | None = None,
    model: str = MODEL_PADRAO,
    tools: list[dict] | None = None,
    executores: dict[str, Callable[[dict], dict]] | None = None,
) -> RespostaAgente:
    """Chama o agente com structured output. `mensagens` = histórico da conversa
    (`[{"role": "user"|"assistant", "content": ...}, ...]`, sem o system prompt, que vai
    separado). `client` é injetável pra teste (mock) — sem isso, cria um `OpenAI()` de
    verdade usando `OPENAI_API_KEY` do .env.

    `tools`/`executores` (Fase 3, 13/07/2026 — loop de function-calling real, réplica do que os
    nós LangChain do n8n faziam com as tool sub-workflows): `tools` é o schema OpenAI
    (`[{"type": "function", "function": {"name", "description", "parameters"}}, ...]`),
    `executores` mapeia `nome da tool -> callable(args: dict) -> dict` (o resultado, serializável
    em JSON, que volta pro modelo como mensagem `role="tool"`). Sem `tools`, comportamento
    idêntico a antes (1 chamada, resposta final direto) — retrocompatível com todo o resto do
    port que já chama `chamar_agente` sem essa opção."""
    client = client or OpenAI(api_key=OPENAI_API_KEY)
    msgs = [{"role": "system", "content": system_prompt}, *mensagens]

    for _ in range(MAX_TOOL_TURNS):
        completion = client.beta.chat.completions.parse(
            # `tools=tools or []`: o SDK real da OpenAI itera `tools` incondicionalmente em
            # `_validate_input_tools` — `tools=None` quebra com `TypeError: 'NoneType' object is
            # not iterable` (só apareceu no smoke test real em produção, 13/07/2026; os 821
            # testes mockam o client, então nunca exercitaram essa validação do SDK de verdade).
            model=model, messages=msgs, response_format=RespostaAgente, tools=tools or [],
        )
        msg = completion.choices[0].message
        # `tools` só é checado quando o CHAMADOR passou tools de verdade — sem isso, um
        # MagicMock de teste tem `.tool_calls` auto-criado (truthy) mesmo sem ninguém setar
        # nada, o que quebraria todo o resto do port que já mocka `chamar_agente` sem tools.
        tool_calls = getattr(msg, "tool_calls", None) if tools else None
        if not tool_calls:
            return msg.parsed

        msgs.append({
            "role": "assistant",
            "content": msg.content,
            "tool_calls": [
                {"id": tc.id, "type": "function", "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                for tc in tool_calls
            ],
        })
        for tc in tool_calls:
            executor = (executores or {}).get(tc.function.name)
            args = json.loads(tc.function.arguments or "{}")
            resultado = executor(args) if executor else {"erro": f"tool '{tc.function.name}' sem executor"}
            msgs.append({"role": "tool", "tool_call_id": tc.id, "content": json.dumps(resultado, ensure_ascii=False)})

    raise RuntimeError(f"chamar_agente: excedeu {MAX_TOOL_TURNS} turnos de tool-calling sem resposta final")


def empacotar_para_eif1(resposta: RespostaAgente) -> str:
    """Converte `RespostaAgente` pro shape `{"output": ..., "meta": {...}}` que
    `app.eif1.processar()` já sabe interpretar (Modo A: JSON puro) — sem tocar no EIF1."""
    return json.dumps(
        {"output": resposta.mensagem, "meta": resposta.estado.model_dump()},
        ensure_ascii=False,
    )


class IAOutputClassificador(BaseModel):
    """Port do nó "AI Agent" (DEPLOY, classificador fixo que roda ANTES do Extrair Rota) —
    mesmos campos e nomes do JSON que o node original retornava (`ia_output` que
    `app.er.processar()` recebe como parâmetro `ai_agent_json`). Roteador puro: não gera texto
    pro paciente, só um palpite de intenção/rota que o ER confirma ou sobrescreve via guards."""

    intencao_rapida: str = "triagem"
    rota_agente: int = 0
    eh_confirmacao: bool = False
    eh_navegacao: bool = False
    eh_confirmacao_cancelamento: bool = False
    eh_resposta_generica: bool = False
    bypass_agente_humano: bool = False
    precisa_agente_completo: bool = True


_PROMPT_CLASSIFICADOR = (
    Path(__file__).resolve().parent.parent / "prompts" / "ai_agent_classificador.txt"
).read_text(encoding="utf-8")


def classificar_intencao(
    contexto: dict,
    *,
    client: OpenAI | None = None,
    model: str = MODEL_PADRAO,
) -> IAOutputClassificador:
    """Chama o classificador (port do nó "AI Agent"). `contexto` precisa ter
    `sessao_intencao`/`sessao_rota`/`cache_ativo` (lidos como `$('Montar Contexto')...`) e
    `mensagem_agrupada` (lido como `$('6. Agrupar Textos1')...`) — ver `app.template_engine`
    pra como esses refs são resolvidos. `client` injetável pra teste, igual `chamar_agente`."""
    client = client or OpenAI(api_key=OPENAI_API_KEY)
    prompt = renderizar(_PROMPT_CLASSIFICADOR, contexto, {})
    completion = client.beta.chat.completions.parse(
        model=model,
        messages=[{"role": "system", "content": prompt}],
        response_format=IAOutputClassificador,
    )
    return completion.choices[0].message.parsed
