"""
Port fiel do nó 'Tool Criar/Extrair IDs Dinâmicos2' —
DEPLOY/_proposed_Tool_Criar_Extrair_IDs_Dinamicos2.js (84 linhas, snapshot 12/07/2026).
Fase 1 do plano de migração (ver C:\\Users\\lucas\\.claude\\plans\\unified-coalescing-puppy.md).

Roda dentro da tool `criar_consulta`/`criar_consulta_terceiro`: resolve `idLocal`/`idCalendar`
do médico escolhido a partir do resultado da busca de agenda (formatos variados — API mudou de
shape mais de uma vez, daí o mapeamento flexível no passo 1). Dois inputs: os argumentos que o
agente passou pra tool (`dados_da_ia`) e o resultado da busca de agenda (`resultado_busca`).

FIX_65707 (exec 65707): "sem preferência"/vazio pode cair no primeiro médico válido da lista;
médico NOMEADO sem match precisa dar ERRO (`MedicoNaoEncontrado`) — nunca agendar com o médico
errado. Preservado o `raise` do JS (era `throw new Error(...)`) com a mensagem idêntica, que o
framework da tool usa pra informar o agente do que aconteceu.
"""

from __future__ import annotations

import re
import unicodedata


class MedicoNaoEncontrado(Exception):
    """Espelha o `throw new Error('MEDICO_NAO_ENCONTRADO: ...')` do JS."""


def _norm(s) -> str:
    s = unicodedata.normalize("NFD", str(s or ""))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = s.lower()
    s = re.sub(r"\b(dr|dra|doutor|doutora)\.?\s*", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def _extrair_lista_medicos(resultado_busca) -> list[dict]:
    resultado_busca = resultado_busca or {}
    if isinstance(resultado_busca, dict) and resultado_busca.get("diasAcumulados"):
        lista = []
        for medicos_do_dia in resultado_busca["diasAcumulados"].values():
            lista.extend(medicos_do_dia.values())
        return lista
    if isinstance(resultado_busca, list):
        return resultado_busca
    if isinstance(resultado_busca, dict) and resultado_busca.get("idCalendar"):
        return [resultado_busca]
    if isinstance(resultado_busca, dict) and isinstance(resultado_busca.get("agenda"), list):
        return resultado_busca["agenda"]
    return []


def processar(dados_da_ia: dict, resultado_busca) -> dict:
    dados_da_ia = dados_da_ia or {}
    lista_medicos = _extrair_lista_medicos(resultado_busca)

    nome_desejado = _norm(dados_da_ia.get("nome_medico_escolhido"))

    id_local = None
    id_calendar = None

    match_tokens = None
    for item in lista_medicos:
        nome_medico_api = _norm(item.get("medico") or item.get("name"))
        if not nome_medico_api or not nome_desejado:
            continue
        if nome_medico_api in nome_desejado or nome_desejado in nome_medico_api:
            id_local = item.get("idLocal")
            id_calendar = item.get("idCalendar")
            break
        if not match_tokens:
            toks = [t for t in nome_desejado.split(" ") if len(t) > 2]
            if toks and all(t in nome_medico_api for t in toks):
                match_tokens = item

    if id_calendar is None and match_tokens:
        id_local = match_tokens.get("idLocal")
        id_calendar = match_tokens.get("idCalendar")

    # FIX_65707: contingência só pra "sem preferência"/vazio; médico nomeado sem match = erro.
    sem_pref = not nome_desejado or "sem preferencia" in nome_desejado or "qualquer" in nome_desejado
    if id_calendar is None:
        if sem_pref and lista_medicos:
            medico_fallback = next((m for m in lista_medicos if m.get("idCalendar")), None)
            if medico_fallback:
                id_local = medico_fallback.get("idLocal")
                id_calendar = medico_fallback.get("idCalendar")
        elif nome_desejado and lista_medicos:
            raise MedicoNaoEncontrado(
                f'MEDICO_NAO_ENCONTRADO: "{dados_da_ia.get("nome_medico_escolhido") or ""}" nao esta na agenda '
                "retornada para essa data/unidade. NAO agende. Informe o paciente que o horario nao esta mais "
                "disponivel para esse medico e ofereca buscar novamente ou falar com um atendente."
            )

    return {
        **dados_da_ia,
        "idLocal_dinamico": id_local or 2,
        "idCalendar_dinamico": id_calendar or 0,
    }
