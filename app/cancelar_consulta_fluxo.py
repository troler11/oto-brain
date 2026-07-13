"""
Port fiel do sub-workflow n8n 'Ferramenta - Cancelar Consulta' (id `i4m4RaNI7E0RkgXp`), lido via
`get_workflow_details` 13/07/2026. Nós portados: 'Buscar Paciente1' (CPF), 'GET Timeline
Paciente1' + 'Filtrar Consultas Ativas1' (shape PRÓPRIO deste node — `dataBR`/`unidade`/
`convenio`, SEM `status_id`, diferente do que `app.tisaude.filtrar_consultas_ativas` já produz;
não reaproveitado de propósito, cada um fiel ao seu node de origem), 'Verificar Acao1' (decide
listar vs. executar cancelamento), 'Cancelar Consulta1' (`app.tisaude.cancelar_consulta`, já
existia) e 'Formatar Retorno Cancelamento2'.

⚠️ ESCOPO (13/07/2026, decisão Lucas): só CÓDIGO — MUTA agendamento real (cancela de verdade na
TiSaude). NÃO ligado a nenhum dispatcher/agente/tool ainda. Só entra em uso depois do cutover
(Fase 2, `/route` ainda roda em shadow) — ligar agora significaria cancelar consulta de paciente
de verdade num turno que nem é a resposta real dada a ele.
"""

from __future__ import annotations

import re
from datetime import date

import httpx

from app import tisaude


def _filtrar_consultas_ativas_cancelamento(timeline_data: list[dict], *, hoje: str | None = None, limite: int = 5) -> list[dict]:
    """Port fiel de 'Filtrar Consultas Ativas1' — shape PRÓPRIO (dataBR, unidade, convenio, sem
    status_id), não confundir com `app.tisaude.filtrar_consultas_ativas` (node diferente,
    'Cancelar Consulta1' aqui é sobre CRIAR o cancelamento, não sobre confirmar presença)."""
    hoje = hoje or date.today().isoformat()
    consultas: list[dict] = []
    for dia in timeline_data:
        for evento in dia.get("data") or []:
            if evento.get("type") != "appointment":
                continue
            status_nome = (evento.get("status") or {}).get("name") or ""
            if "desmarcad" in status_nome.lower():
                continue
            data_evento = evento.get("date") or dia.get("date") or ""
            if data_evento < hoje:
                continue
            consultas.append({
                "id": evento.get("id"),
                "data": data_evento,
                "dataBR": "/".join(reversed(data_evento.split("-"))) if data_evento else "",
                "hora": evento.get("hour") or "?",
                "medico": (evento.get("calendar") or {}).get("name") or "Médico não informado",
                "status": status_nome or "Ativo",
                "unidade": (
                    (evento.get("local") or {}).get("name") or (evento.get("place") or {}).get("name")
                    or (evento.get("location") or {}).get("name") or (evento.get("company") or {}).get("name")
                    or (evento.get("unit") or {}).get("name") or ""
                ),
                "convenio": (evento.get("healthInsurance") or {}).get("name") or (evento.get("covenant") or {}).get("name") or "",
            })
            if len(consultas) >= limite:
                return consultas
    return consultas


def _parseint_js(v) -> int | None:
    m = re.match(r"^\s*[-+]?\d+", str(v if v is not None else ""))
    return int(m.group(0)) if m else None


def _resolver_id_real(id_agendamento, consultas_args: list[dict] | None, consultas_fresh: list[dict]) -> str:
    """Port de 'Verificar Acao1' (2ª chamada): número 1-5 vira índice na lista (prioridade pros
    `consultas` que a IA já tinha nos args, senão a lista fresh do timeline); qualquer outro
    valor é usado como ID real direto."""
    numero = _parseint_js(id_agendamento)
    if numero is not None and 1 <= numero <= 5:
        lst = consultas_args or []
        if len(lst) >= numero:
            return str(lst[numero - 1]["id"])
        if len(consultas_fresh) >= numero:
            return str(consultas_fresh[numero - 1]["id"])
    return str(id_agendamento)


def cancelar_consulta_completo(
    *,
    cpf: str,
    id_agendamento: str | None = None,
    motivo: str | None = None,
    consultas: list[dict] | None = None,
    tisaude_client: httpx.Client | None = None,
    hoje: date | None = None,
) -> dict:
    """Orquestra o fluxo completo: busca paciente por CPF, lista consultas ativas (1ª chamada,
    sem `id_agendamento`) ou executa o cancelamento (2ª chamada, com `id_agendamento` — número
    1-5 da lista OU ID real). `conn`/Postgres não entram aqui — este sub-workflow não grava
    nada, diferente de 'Criar Consulta e Paciente' (ver app.criar_consulta_fluxo)."""
    token = tisaude.login(client=tisaude_client)
    pacientes = tisaude.buscar_paciente_por_cpf(cpf, token, client=tisaude_client)
    if not pacientes:
        return {
            "status": "CPF_NAO_ENCONTRADO",
            "resultado": "Não encontrei nenhum paciente com esse CPF no sistema. Verifique se o CPF está correto e tente novamente.",
        }

    id_paciente = pacientes[0].get("id")
    timeline = tisaude.timeline_paciente(id_paciente, token, client=tisaude_client)
    ativas = _filtrar_consultas_ativas_cancelamento(timeline, hoje=(hoje or date.today()).isoformat())

    if not id_agendamento:
        if not ativas:
            return {"status": "SEM_CONSULTAS", "resultado": "Não encontrei consultas agendadas para cancelar."}
        linhas = "\n".join(f"{i + 1}. {c['dataBR']} às {c['hora']} com Dr(a). {c['medico']} (ID: {c['id']})" for i, c in enumerate(ativas))
        return {
            "status": "AGUARDANDO_ESCOLHA",
            "resultado": f"Encontrei {len(ativas)} consulta(s) agendada(s):\n{linhas}\nQual deseja cancelar? Informe o número.",
            "consultas": ativas, "id_paciente": id_paciente,
        }

    id_real = _resolver_id_real(id_agendamento, consultas, ativas)
    resultado_api = tisaude.cancelar_consulta(int(id_real), token, client=tisaude_client)
    sucesso = bool(resultado_api.get("success") or resultado_api.get("id") or resultado_api.get("status") == "ok" or resultado_api.get("message"))
    if sucesso:
        return {"status": "CANCELADO", "resultado": "Consulta cancelada com sucesso! Se precisar reagendar, é só me avisar. 😊"}
    return {"status": "ERRO", "resultado": "Não foi possível cancelar a consulta. Por favor, fale com uma atendente."}
