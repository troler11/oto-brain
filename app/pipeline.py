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

`conn` (13/07/2026, Fase 3 peça C): opcional, só repassado até `app.dispatcher.despachar_turno`
pro agente "agenda" ligar as tools reais `buscar_agenda`/`navegar_agenda` (`app.tools_agenda`) —
sem `conn`, comportamento idêntico a antes (sem tool-calling). `app.main` precisa manter a
conexão aberta durante `processar_turno()` agora (antes fechava antes de chamar).

rota_agente == 5 (confirmar presença) é 100% determinístico (`app.formatar_verificar_confirmar`,
orquestrado por `app.confirmar_presenca_fluxo`), ligado à tool TiSaude real desde 13/07/2026 —
mas só LEITURA (buscar consultas): a mutação real (`tisaude.confirmar_presenca`) fica pendente
do cutover (Fase 2, `/route` ainda roda em shadow — ver docstring de
app.confirmar_presenca_fluxo). Sub-casos que na verdade são bypass pra humano (encaixe, lista de
espera — `base['_sub_confirmar']` não setado) continuam sem tratamento aqui (ver achado
separado, `intencao_rapida=="humano"` deveria ter prioridade sobre o corte de rota==5, igual já
acontece em `app.dispatcher.escolher_agente` — pendente de decisão do Lucas).
`processar_turno()` retorna cedo com `rota_agente=5` e `agente_usado=None` nesse caso.

`intencao_rapida in ("remarcando", "remarcando_escolher")` (13/07/2026, ver
`app.processar_remarcacao`) é outro atalho 100% determinístico, também ligado à tool TiSaude real
mas só LEITURA (busca consultas ativas via o mesmo sub-workflow de `cancelar_consulta`, em modo
listagem — nunca cancela nada). Roda ANTES do corte de rota==5 (espelha o grafo real: `É
Remarcação?` é avaliado logo após Extrair Rota, independente de rota_agente). `agente_usado=None`
nesse caso também.

Reask Engine (13/07/2026, achado como código órfão numa auditoria — `app.reask_engine` já
existia, portado mas nunca chamado): ligado no fim do turno normal (fora dos atalhos acima).
No n8n real, 'SV Router' manda pro Reask Engine sempre que `sv_result != 'ALLOW'` (cobre REASK E
BLOCK, mesmo caminho) — a `mensagem_final` dele SOBREPÕE a do agente. Persistência em
`chat_messages` ("Salvar Reask Memory") fica de fora — nenhum módulo Python grava histórico de
conversa hoje, isso é só do n8n enquanto `/route` for shadow.

Navegação/Troca Direta (13/07/2026, ver `app.navegacao_direta_fluxo`) é outro atalho 100%
determinístico, checa `eh_navegacao`/`eh_troca_data` logo após o corte de rota==5. Precisa de
`conn` (Postgres) — sem `conn`, comportamento idêntico a antes (pula o atalho, vai direto pro
despacho normal). Diferente dos outros atalhos: TEM fallback pro agente completo quando o cache
está vazio/esgotado (`None` do módulo = cai pro despacho normal), fiel ao node real
('Precisa Buscar?' -> 'Roteador'). ⚠️ Na prática, só o ramo TROCA dispara hoje — o ramo
NAVEGAÇÃO depende de `eh_navegacao` sobreviver em `r.base`, o que `app.er` ainda não faz (gap
pré-existente, ver docstring de `app.navegacao_direta_fluxo`).
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

import httpx
import psycopg
from openai import OpenAI

from app import confirmar_presenca_fluxo, dispatcher, eif1, er, injetar_contexto_agendamento, montar_contexto, navegacao_direta_fluxo, preparar_input_agenda, processar_remarcacao, reask_engine, state_validator
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
    conn: psycopg.Connection | None = None,
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

    # WIRING_REMARCACAO (13/07/2026): 'É Remarcação?' no n8n real é avaliado logo após Extrair
    # Rota, em paralelo ao roteador de rota_agente — independente de rota_agente, sempre desvia
    # dos Agentes LLM nesse turno (ver docstring de app.processar_remarcacao). None ->
    # sem opinião shadow (CPF ausente ou falha de IO), mensagem vazia, mesmo padrão de rota==5.
    if r.intencao_rapida in ("remarcando", "remarcando_escolher"):
        resultado_remarc = processar_remarcacao.buscar_e_processar(r.base, mensagem_agrupada, tisaude_client=tisaude_client)
        if resultado_remarc is None:
            return ResultadoTurno(
                mensagem="", intencao=r.intencao_rapida, sv_result="", sv_reason="",
                rota_agente=r.rota_agente, agente_usado=None,
                deve_resetar_sessao=r.deve_resetar_sessao, base_final=r.base,
            )
        resultado_eif1_remarc = eif1.processar(resultado_remarc["output"], extrair_rota=r.base, carregar_sessao=sessao)
        inp_remarc = state_validator.normalizar_ds(resultado_eif1_remarc.to_dict())
        sv_remarc = state_validator.validar_estado(inp_remarc, base=base_mc, er_output=r.base)
        return ResultadoTurno(
            mensagem=resultado_eif1_remarc.texto_ia, intencao=resultado_eif1_remarc.intencao,
            sv_result=sv_remarc.sv_result, sv_reason=sv_remarc.sv_reason,
            rota_agente=r.rota_agente, agente_usado=None,
            deve_resetar_sessao=r.deve_resetar_sessao, dados=sv_remarc.inp, base_final=r.base,
        )

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

    # WIRING_NAVEGACAO_DIRETA (13/07/2026): 'Precisa Agente Completo?' -> 'Detectar Navegacao' no
    # n8n real roda em paralelo aos ramos acima, também direto na saída de Extrair Rota — checa
    # eh_navegacao/eh_troca_data (ambos determinísticos, ver docstring de
    # app.navegacao_direta_fluxo) e responde SEM Agente LLM quando dá. None -> nem ativo, nem
    # decidiu (precisa_buscar) ou falhou -> cai pro despacho normal, MESMO fallback do node real
    # (diferente dos 2 atalhos acima, que não têm fallback pro agente no grafo real).
    if conn is not None:
        resultado_nav = navegacao_direta_fluxo.processar(
            r.base, telefone=base_mc.get("telefone") or "", sessao=sessao, conn=conn, tisaude_client=tisaude_client,
        )
        if resultado_nav is not None:
            return ResultadoTurno(
                mensagem=resultado_nav.get("mensagem_final") or "", intencao="navegacao_direta",
                sv_result="", sv_reason="", rota_agente=r.rota_agente, agente_usado=None,
                deve_resetar_sessao=r.deve_resetar_sessao, base_final=r.base,
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
        conn=conn, tisaude_client=tisaude_client,
    )
    raw = empacotar_para_eif1(resposta)
    resultado_eif1 = eif1.processar(raw, extrair_rota=base_agente, carregar_sessao=sessao)

    inp = state_validator.normalizar_ds(resultado_eif1.to_dict())
    sv = state_validator.validar_estado(inp, base=base_mc, er_output=base_agente)

    # WIRING_REASK_ENGINE (13/07/2026): no n8n real, 'SV Router' (IF em sv_result=='ALLOW') manda
    # pro Reask Engine em QUALQUER resultado != ALLOW (REASK e BLOCK, mesmo caminho) — a mensagem
    # dele SOBREPÕE a do agente (`mensagem_final || texto_ia` no node de envio real). `sv.inp` já
    # carrega os campos de coleta que app.reask_engine.processar() precisa; só falta `sv_reason`,
    # que vive em `sv.sv_reason` (fora do dict `inp`). Persistência em `chat_messages` ("Salvar
    # Reask Memory") fica de fora — nenhum módulo Python grava histórico de conversa hoje, `/route`
    # é shadow e n8n é quem possui essa persistência de verdade.
    mensagem = resultado_eif1.texto_ia
    if sv.sv_result != "ALLOW":
        mensagem = reask_engine.processar({**sv.inp, "sv_reason": sv.sv_reason})["mensagem_final"]

    return ResultadoTurno(
        mensagem=mensagem,
        intencao=resultado_eif1.intencao,
        sv_result=sv.sv_result,
        sv_reason=sv.sv_reason,
        rota_agente=r.rota_agente,
        agente_usado=agente,
        deve_resetar_sessao=r.deve_resetar_sessao,
        dados=sv.inp,
        base_final=base_agente,
    )
