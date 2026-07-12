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

Ainda não tem prompts portados aqui (os 9 `_proposed_Agente_*_systemMessage.txt` do DEPLOY
continuam como referência de conteúdo, não copiados 1:1 — adaptar um prompt de "responda nesse
formato de texto com $$$ no final" pra "responda dentro deste schema" é trabalho de prompt
engineering, não tradução mecânica de código, e fica pra quando Lucas revisar/aprovar cada um).
"""

from __future__ import annotations

import json

from openai import OpenAI
from pydantic import BaseModel, Field

from app.config import OPENAI_API_KEY

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


def chamar_agente(
    system_prompt: str,
    mensagens: list[dict],
    *,
    client: OpenAI | None = None,
    model: str = MODEL_PADRAO,
) -> RespostaAgente:
    """Chama o agente com structured output. `mensagens` = histórico da conversa
    (`[{"role": "user"|"assistant", "content": ...}, ...]`, sem o system prompt, que vai
    separado). `client` é injetável pra teste (mock) — sem isso, cria um `OpenAI()` de
    verdade usando `OPENAI_API_KEY` do .env."""
    client = client or OpenAI(api_key=OPENAI_API_KEY)
    completion = client.beta.chat.completions.parse(
        model=model,
        messages=[{"role": "system", "content": system_prompt}, *mensagens],
        response_format=RespostaAgente,
    )
    return completion.choices[0].message.parsed


def empacotar_para_eif1(resposta: RespostaAgente) -> str:
    """Converte `RespostaAgente` pro shape `{"output": ..., "meta": {...}}` que
    `app.eif1.processar()` já sabe interpretar (Modo A: JSON puro) — sem tocar no EIF1."""
    return json.dumps(
        {"output": resposta.mensagem, "meta": resposta.estado.model_dump()},
        ensure_ascii=False,
    )
