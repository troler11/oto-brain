"""
Schema OpenAI + executor da tool `consultar_minhas_consultas` — liga app.consultar_consultas_fluxo
no loop de tool-calling genérico (app.agentes.chamar_agente), mesmo padrão de app.tools_agenda.

Description/schema copiados literalmente do node 'Tool Ver (Triagem)' (workflow n8n
`oX6ePJbAVF7C0NoX`, nó "Agente Triagem/Ver"), lidos via `get_workflow_details` 13/07/2026.
"""

from __future__ import annotations

from typing import Callable

import httpx

from app import consultar_consultas_fluxo

CONSULTAR_MINHAS_CONSULTAS_SCHEMA = {
    "type": "function",
    "function": {
        "name": "consultar_minhas_consultas",
        "description": "Busca agendamentos futuros que o paciente já possua marcados usando o CPF.",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "cpf": {"type": "string", "description": "CPF completo e apenas os números do paciente que está a solicitar a informação."},
            },
            "required": ["cpf"],
            "additionalProperties": False,
        },
    },
}

TOOLS_TRIAGEM = [CONSULTAR_MINHAS_CONSULTAS_SCHEMA]


def construir_executores(tisaude_client: httpx.Client | None = None) -> dict[str, Callable[[dict], dict]]:
    def executor(args: dict) -> dict:
        return consultar_consultas_fluxo.consultar_minhas_consultas(args.get("cpf") or "", tisaude_client=tisaude_client)

    return {"consultar_minhas_consultas": executor}
