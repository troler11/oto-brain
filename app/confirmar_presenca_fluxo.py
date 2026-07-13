"""
Orquestra o fluxo determinístico de confirmar presença (rota_agente==5, `base['_sub_confirmar']`
setado em app.er) chamando o client TiSaude (app.tisaude) pra buscar as consultas reais do
paciente, e delega a decisão pro port já existente (app.formatar_verificar_confirmar).

Escopo decidido com Lucas (13/07/2026): só LEITURA por enquanto. `/route` ainda roda em shadow
(n8n decide de verdade — Fase 2/cutover pendente, ver
C:\\Users\\lucas\\.claude\\plans\\unified-coalescing-puppy.md). Chamar a mutação real
(`tisaude.confirmar_presenca`, POST que confirma presença de verdade na TiSaude) a cada turno de
shadow confirmaria presença de paciente sem essa ser a resposta real dada a ele — por isso o
caminho "auto_confirmar" aqui NÃO chama `tisaude.confirmar_presenca` ainda, só decide e loga o
que FARIA. Ativar a mutação real fica pro cutover, decisão explícita futura.

Shape da consulta esperado por `app.formatar_verificar_confirmar` (dataBR/hora/medico/
status_nome/status_id/id) é o confirmado via execução real 58313 (mesma fonte usada em
`app.processar_remarcacao`) — adapta aqui a partir do shape (data_br/status/status_id) que
`app.tisaude.filtrar_consultas_ativas()` já produz.

IO real (login + timeline) é envolvido em try/except: falha de rede/API na TiSaude durante um
turno de shadow não pode derrubar `/route` — cai pro mesmo fallback de antes da integração
(mensagem vazia, caminho legado n8n decide).
"""

from __future__ import annotations

import logging

import httpx

from app import formatar_verificar_confirmar as fvc
from app import tisaude

logger = logging.getLogger("oto-brain.confirmar_presenca")

_SUB_COM_TISAUDE = ("verificar", "executar")


def _adaptar_consulta(c: dict) -> dict:
    return {
        "id": c.get("id"),
        "dataBR": c.get("data_br"),
        "hora": c.get("hora"),
        "medico": c.get("medico"),
        "status_nome": c.get("status"),
        "status_id": c.get("status_id"),
    }


def buscar_consultas_paciente(id_tisaude, *, client: httpx.Client | None = None) -> list[dict]:
    """IO: loga na TiSaude, busca timeline do paciente, filtra ativas, adapta pro shape que
    app.formatar_verificar_confirmar espera."""
    token = tisaude.login(client=client)
    bruto = tisaude.timeline_paciente(int(id_tisaude), token, client=client)
    ativas = tisaude.filtrar_consultas_ativas(bruto)
    return [_adaptar_consulta(c) for c in ativas]


def processar_rota5(base: dict, *, client: httpx.Client | None = None) -> dict | None:
    """Orquestra o turno rota_agente==5 conforme `base['_sub_confirmar']`:
      - "escolher_titular" -> lista titulares, sem chamada TiSaude
      - "verificar"/"executar" -> busca consultas reais e decide (pergunta/lista/auto) via
        app.formatar_verificar_confirmar.processar()
      - qualquer outro valor (recusou/despedida/None — inclui os rota=5 que na verdade são
        bypass pra humano, ex. encaixe/lista de espera) -> None, deixa pro caminho de sempre.

    Retorna dict no formato de app.formatar_verificar_confirmar.processar() (`output`/
    `auto_confirmar`/...), ou None se não há TiSaude envolvida ou a chamada falhou."""
    sub = base.get("_sub_confirmar")

    if sub == "escolher_titular":
        return fvc.formatar_escolher_titular(base, base.get("pacientes"))

    if sub in _SUB_COM_TISAUDE:
        id_tisaude = base.get("id_tisaude") or (base.get("pacientes") or [{}])[0].get("id_tisaude")
        if not id_tisaude:
            return None
        try:
            consultas = buscar_consultas_paciente(id_tisaude, client=client)
        except Exception:
            logger.exception("rota5: falha ao buscar consultas na TiSaude (id_tisaude=%s)", id_tisaude)
            return None

        resultado = fvc.processar({"consultas": consultas}, base, base.get("_indice_consulta"))
        if resultado.get("auto_confirmar"):
            logger.info(
                "rota5: auto_confirmar decidido (id_agendamento=%s) — mutação real NÃO disparada "
                "(shadow, aguardando cutover Fase 2)", resultado.get("id_agendamento"),
            )
        return resultado

    return None
