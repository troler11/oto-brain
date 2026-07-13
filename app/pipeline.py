"""
Fase 3 (peça final de fiação, 12/07): junta as peças já portadas e testadas isoladamente num
único fluxo por turno, espelhando a ordem real do n8n (`get_workflow_details` do workflow
`oX6ePJbAVF7C0NoX`):

    Montar Contexto -> AI Agent (classificador) -> Extrair Rota -> Roteador de Agente ->
    [rota=4: Injetar Contexto Agendamento + Preparar Input Agenda] -> [agente específico] ->
    Extrair Intencao Final1 -> Normalizar DS -> State Validator

Função pura o suficiente pra testar sem FastAPI/Postgres/rede: recebe tudo já buscado
(`sessao`, `historico`, `busca_paciente_*`) como argumento, só a chamada OpenAI (`classificar_
intencao`/`chamar_agente`, via `openai_client` injetável) faz IO de verdade. Quem busca sessão/
histórico no Postgres é `app.main` (o endpoint HTTP), não este módulo — mesma separação
pura/IO do resto do port (ex.: `app.er` vs `scripts/replay_offline.py`).

rota_agente == 5 (confirmar presença) é 100% determinístico (`app.formatar_verificar_confirmar`,
orquestrado por `app.confirmar_presenca_fluxo`), ligado à tool TiSaude real desde 13/07/2026 —
mas só LEITURA (buscar consultas): a mutação real (`tisaude.confirmar_presenca`) fica pendente
do cutover (Fase 2, `/route` ainda roda em shadow — ver docstring de
app.confirmar_presenca_fluxo). Sub-casos que na verdade são bypass pra humano (encaixe, lista de
espera — `base['_sub_confirmar']` não setado) continuam sem tratamento aqui (ver achado
separado, `intencao_rapida=="humano"` deveria ter prioridade sobre o corte de rota==5, igual já
acontece em `app.dispatcher.escolher_agente` — pendente de decisão do Lucas).
`processar_turno()` retorna cedo com `rota_agente=5` e `agente_usado=None` nesse caso.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

import httpx
from openai import OpenAI

from app import confirmar_presenca_fluxo, dispatcher, eif1, er, injetar_contexto_agendamento, montar_contexto, preparar_input_agenda, state_validator
from app.agentes import classificar_intencao, empacotar_para_eif1


@dataclass
class ResultadoTurno:
    mensagem: str
    intencao: str
    sv_result: str
    sv_reason: str
    rota_agente: int
    agente_usado: str | None
    deve_resetar_sessao: bool
    dados: dict = field(default_factory=dict)
    base_final: dict = field(default_factory=dict)


def processar_turno(
    *,
    busca_paciente_id1: list[dict] | None,
    busca_paciente_telefone: dict | None,
    extrair_medico_timeline: list[dict] | None,
    sessao: dict | None,
    whatsapp_info: dict | None,
    mensagem_agrupada: str,
    historico: list[dict],
    has_media: bool = False,
    memoria_paciente: dict | None = None,
    openai_client: OpenAI | None = None,
    tisaude_client: httpx.Client | None = None,
) -> ResultadoTurno:
    mc = montar_contexto.processar(
        busca_paciente_id1, busca_paciente_telefone, extrair_medico_timeline,
        sessao, whatsapp_info, mensagem_agrupada, memoria_paciente,
    )
    base_mc = mc.to_dict()
    # Campo extra, fora do port fiel de Montar Contexto — bootstrap Fase 4 (paciente_memoria,
    # carregar_memoria_paciente). Além de alimentar saudacao_section acima, fica disponível pro
    # template engine ({{ $('Montar Contexto').first().json.memoria_paciente... }}) pra usos
    # futuros ainda não propostos.
    base_mc["memoria_paciente"] = memoria_paciente

    ia_output = classificar_intencao(
        {
            "sessao_intencao": base_mc.get("sessao_intencao", ""),
            "sessao_rota": base_mc.get("sessao_rota", 0),
            "cache_ativo": base_mc.get("cache_ativo", False),
            "mensagem_agrupada": mensagem_agrupada,
        },
        client=openai_client,
    ).model_dump()

    r = er.processar(dict(base_mc), mensagem_agrupada, ia_output, whatsapp_info, has_media)

    # FIX_ROTA5_PRIORIDADE_HUMANO: rota_agente==5 é reusado tanto pro fluxo real de confirmar
    # presença quanto pra bypass determinístico pra humano (encaixe, lista de espera,
    # agendamento duplo — ver app.er). intencao_rapida=="humano" tem prioridade sobre rota==5,
    # igual app.dispatcher.escolher_agente() já respeita — sem esse guard aqui, esses 3 casos
    # voltavam mensagem vazia em vez de cair no agente_humano (achado 13/07/2026, revisão do
    # wiring do confirmar_presenca_fluxo).
    if r.rota_agente == 5 and r.intencao_rapida != "humano":
        resultado_rota5 = confirmar_presenca_fluxo.processar_rota5(r.base, client=tisaude_client)
        mensagem_rota5 = resultado_rota5.get("output", "") if resultado_rota5 else ""
        return ResultadoTurno(
            mensagem=mensagem_rota5, intencao="confirmar_presenca", sv_result="", sv_reason="",
            rota_agente=5, agente_usado=None, deve_resetar_sessao=r.deve_resetar_sessao,
            base_final=r.base,
        )

    base_agente = r.base
    if r.rota_agente == 4:
        base_agente = preparar_input_agenda.processar(injetar_contexto_agendamento.processar(base_agente))
    r_para_dispatch = replace(r, base=base_agente)

    n_pacientes = len(base_mc.get("pacientes") or [])
    # despachar_turno só retorna None quando rota_agente==5 (interceptado acima) — fora desse
    # caso, escolher_agente() sempre resolve pra algum agente.
    agente, resposta = dispatcher.despachar_turno(
        r_para_dispatch, historico, base_mc=base_mc, n_pacientes=n_pacientes, client=openai_client,
    )
    raw = empacotar_para_eif1(resposta)
    resultado_eif1 = eif1.processar(raw, extrair_rota=base_agente, carregar_sessao=sessao)

    inp = state_validator.normalizar_ds(resultado_eif1.to_dict())
    sv = state_validator.validar_estado(inp, base=base_mc, er_output=base_agente)

    return ResultadoTurno(
        mensagem=resultado_eif1.texto_ia,
        intencao=resultado_eif1.intencao,
        sv_result=sv.sv_result,
        sv_reason=sv.sv_reason,
        rota_agente=r.rota_agente,
        agente_usado=agente,
        deve_resetar_sessao=r.deve_resetar_sessao,
        dados=sv.inp,
        base_final=base_agente,
    )
