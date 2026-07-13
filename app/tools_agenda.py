"""
Schemas OpenAI (function-calling) + executores das duas tools de agenda já portadas
(app.navegar_agenda, app.buscar_agenda_fluxo) — a peça que liga o loop de tool-calling genérico
(app.agentes.chamar_agente, `tools`/`executores`) nas duas funções já testadas isoladas.

Descrições/schemas copiados literalmente dos nós `Tool Buscar (Agenda)`/`Tool Navegar (Agenda)`
(workflow n8n `oX6ePJbAVF7C0NoX`, nó "Agente Agenda"), lidos via `get_workflow_details`
13/07/2026 — é o texto que o modelo vê pra decidir quando chamar cada tool, preservado 1:1.

Só ligado no dispatcher pro agente "agenda" (prompt `agente_agenda.txt`) — o "Agente Navegacao"
tem tools com os MESMOS nomes mas sub-workflows ainda não confirmados como sendo os mesmos
(não investigado), não assumir sem checar.
"""

from __future__ import annotations

from typing import Callable

import httpx
import psycopg

from app import buscar_agenda_fluxo, db, navegar_agenda

BUSCAR_AGENDA_SCHEMA = {
    "type": "function",
    "function": {
        "name": "buscar_agenda",
        "description": (
            "Busca horários disponíveis nos próximos 20 dias e salva no cache.\n"
            "Retorna APENAS o primeiro dia disponível. Para ver os próximos dias, use navegar_agenda.\n\n"
            "🛑 NÃO USE se o cache estiver ativo (✅) — use navegar_agenda diretamente.\n"
            "Use APENAS quando: sem cache, troca de médico, troca de unidade, ou cache esgotado."
        ),
        # `strict: true` + `additionalProperties: false` são exigidos pelo client.beta.chat.
        # completions.parse() da OpenAI pra tools coexistirem com response_format (structured
        # output) — descoberto na validação manual 13/07/2026 (ValueError: "only strict function
        # tools can be auto-parsed"), não documentado nos schemas originais do n8n (LangChain
        # tool node não passa por essa validação). Campos opcionais no JS (`horario_preferencia`/
        # `dia_semana`/`data` em ir_para) viram `["string","null"]` + `required` — convenção do
        # modo strict, que não aceita propriedade ausente sem estar em `required`.
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "unidade": {"type": "string", "description": "Vila Olímpia ou Tatuapé"},
                "data": {"type": "string", "description": "YYYY-MM-DD"},
                "medico": {"type": "string", "description": "nome ou 'sem preferência'"},
                "periodo": {"type": "string", "description": "manha/tarde/noite"},
                "telefone_paciente": {"type": "string", "description": "só dígitos, telefone do titular"},
                "horario_preferencia": {"type": ["string", "null"], "description": "hora específica ou null"},
                "dia_semana": {"type": ["string", "null"], "description": "segunda..sexta (obrigatório em modos 2/3), null se não aplicável"},
            },
            "required": ["unidade", "data", "medico", "periodo", "telefone_paciente", "horario_preferencia", "dia_semana"],
            "additionalProperties": False,
        },
    },
}

NAVEGAR_AGENDA_SCHEMA = {
    "type": "function",
    "function": {
        "name": "navegar_agenda",
        "description": (
            "Navega pelos dias do cache de agenda. Ações: acao='ver' → retorna dia atual sem "
            "avançar. acao='avancar' → próximo dia. acao='voltar' → dia anterior. acao='ir_para' "
            "+ data='YYYY-MM-DD' → navega até a data específica no cache. CHAME SEMPRE após "
            "buscar_agenda. Paciente pediu data específica (dia 23, 30/06) → use ir_para com "
            "data=YYYY-MM-DD."
        ),
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "acao": {"type": "string", "enum": ["ver", "avancar", "voltar", "ir_para"]},
                "telefone_paciente": {"type": "string", "description": "só dígitos"},
                "unidade": {"type": "string", "description": "Vila Olímpia ou Tatuapé"},
                "data": {"type": ["string", "null"], "description": "YYYY-MM-DD, obrigatório só se acao=ir_para, null caso contrário"},
            },
            "required": ["acao", "telefone_paciente", "unidade", "data"],
            "additionalProperties": False,
        },
    },
}

TOOLS_AGENDA = [BUSCAR_AGENDA_SCHEMA, NAVEGAR_AGENDA_SCHEMA]


def _executor_navegar_agenda(conn: psycopg.Connection) -> Callable[[dict], dict]:
    def executor(args: dict) -> dict:
        telefone = args.get("telefone_paciente") or ""
        unidade = args.get("unidade") or ""
        cache_row = db.ler_agenda_cache(conn, telefone, unidade)
        resultado = navegar_agenda.processar(cache_row, args.get("acao") or "ver", args.get("data"))
        if resultado.get("status") != "SEM_CACHE":
            db.atualizar_indice_agenda_cache(conn, telefone, unidade, resultado.get("indice_atual") or 0, resultado.get("dia"))
        return resultado

    return executor


def _executor_buscar_agenda(conn: psycopg.Connection, tisaude_client: httpx.Client | None) -> Callable[[dict], dict]:
    def executor(args: dict) -> dict:
        return buscar_agenda_fluxo.buscar_agenda_completo(
            unidade=args.get("unidade") or "", data=args.get("data"), medico=args.get("medico"),
            periodo=args.get("periodo"), telefone_paciente=args.get("telefone_paciente") or "",
            dia_semana=args.get("dia_semana"), horario_preferencia=args.get("horario_preferencia"),
            conn=conn, tisaude_client=tisaude_client,
        )

    return executor


def construir_executores(conn: psycopg.Connection, tisaude_client: httpx.Client | None = None) -> dict[str, Callable[[dict], dict]]:
    return {
        "navegar_agenda": _executor_navegar_agenda(conn),
        "buscar_agenda": _executor_buscar_agenda(conn, tisaude_client),
    }
