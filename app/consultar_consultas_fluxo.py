"""
Port fiel do sub-workflow n8n 'Ferramenta - Consultar Minhas Consultas' (id `iOhQPjizddY88k4K`),
lido via `get_workflow_details` 13/07/2026 — tool `consultar_minhas_consultas`, única usada pelo
`agente_triagem` (fluxo "ver agendamentos"/"esqueci a data da consulta").

100% LEITURA: login -> busca paciente por CPF -> timeline -> formata texto. Não grava nada no
Postgres, não muta nada na TiSaude — mais simples até que buscar_agenda/navegar_agenda (que
gravam cache). Por isso, diferente de criar_consulta/cancelar_consulta, é seguro ligar direto
(ver app.tools_triagem), sem trava de cutover.

As 3 chamadas HTTP (`login`/`buscar_paciente_por_cpf`/`timeline_paciente`) já existiam em
`app.tisaude`, reaproveitadas aqui sem mudança — só a formatação do node 'Formatar para Agente'
é código novo.
"""

from __future__ import annotations

import httpx

from app import tisaude

_LIMITE_CONSULTAS = 5


def _formatar_consultas(timeline_data: list[dict]) -> str:
    """Port fiel do node 'Formatar para Agente'. `type=='appointment'` só (ignora notas/
    prescrições da timeline), exclui status contendo 'desmarcado' (case-insensitive), cap de 5,
    fallbacks 'Hora Indefinida'/'Médico não informado'."""
    if not timeline_data:
        return "O paciente não possui consultas marcadas para este período."

    linhas = []
    for dia in timeline_data:
        for evento in dia.get("data") or []:
            if evento.get("type") != "appointment":
                continue
            status = (evento.get("status") or {}).get("name") or "Ativo"
            if "desmarcado" in str(status).lower():
                continue

            id_agendamento = evento.get("id")
            data_agendamento = evento.get("date") or dia.get("date") or ""
            hora = evento.get("hour") or "Hora Indefinida"
            medico = (evento.get("calendar") or {}).get("name") or "Médico não informado"
            data_br = "/".join(reversed(data_agendamento.split("-"))) if data_agendamento else ""

            linhas.append(f"- Dia {data_br} às {hora} com Dr(a). {medico}. (ID_AGENDAMENTO: {id_agendamento})")
            if len(linhas) >= _LIMITE_CONSULTAS:
                break
        if len(linhas) >= _LIMITE_CONSULTAS:
            break

    if not linhas:
        return "O paciente possui histórico, mas não há consultas ativas ou futuras cadastradas."
    return "Consultas encontradas para este paciente:\n" + "\n".join(linhas)


def consultar_minhas_consultas(cpf: str, *, tisaude_client: httpx.Client | None = None) -> dict:
    """Orquestra o fluxo completo. Sem paciente encontrado pro CPF, replica o mesmo texto de
    'sem consultas' (o node original não trata CPF-não-encontrado como caso à parte — pega
    `data[0].id` direto; sem resultado, o `.timeline` seguinte falharia. Aqui, tratamos ausência
    de paciente como retorno determinístico equivalente, sem chamada extra que geraria erro)."""
    token = tisaude.login(client=tisaude_client)
    pacientes = tisaude.buscar_paciente_por_cpf(cpf, token, client=tisaude_client)
    if not pacientes:
        return {"resultado": "O paciente não possui consultas marcadas para este período."}

    timeline = tisaude.timeline_paciente(pacientes[0]["id"], token, client=tisaude_client)
    return {"resultado": _formatar_consultas(timeline)}
