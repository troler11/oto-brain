"""
Testes de app/pipeline.py::processar_turno — junta os módulos já testados isoladamente
(montar_contexto, classificar_intencao, er, dispatcher, eif1, state_validator) num turno
completo. Sem Postgres real: `sessao`/`historico`/`busca_paciente_*` são passados direto, sem
chamada real à OpenAI: client mockado (2 chamadas por turno normal — classificador + agente
específico; 1 só quando rota_agente==5, que retorna cedo sem chamar agente).
"""

from unittest.mock import MagicMock

import httpx

from app.agentes import EstadoConsulta, IAOutputClassificador, RespostaAgente
from app.pipeline import processar_turno

WA_INFO = {"SenderAlt": "", "Chat": "5511999999999@s.whatsapp.net", "PushName": "Lucas Bueno"}


def _completion(resposta):
    parsed_message = MagicMock()
    parsed_message.parsed = resposta
    completion = MagicMock()
    completion.choices = [MagicMock(message=parsed_message)]
    return completion


def _mock_client(*respostas):
    client = MagicMock()
    client.beta.chat.completions.parse.side_effect = [_completion(r) for r in respostas]
    return client


def test_turno_triagem_simples_chama_classificador_e_agente_triagem():
    ia_output = IAOutputClassificador(intencao_rapida="triagem", rota_agente=0)
    resposta_agente = RespostaAgente(mensagem="Oi! Como posso ajudar? 😊", estado=EstadoConsulta(i="triagem"))
    client = _mock_client(ia_output, resposta_agente)

    r = processar_turno(
        busca_paciente_id1=None, busca_paciente_telefone=None, extrair_medico_timeline=None,
        sessao=None, whatsapp_info=WA_INFO, mensagem_agrupada="oi", historico=[],
        openai_client=client,
    )

    assert r.rota_agente == 0
    assert r.agente_usado == "triagem"
    assert r.intencao == "triagem"
    assert "Oi!" in r.mensagem
    assert client.beta.chat.completions.parse.call_count == 2


def test_turno_rota_5_bypass_humano_chama_agente_humano():
    # FIX_ROTA5_PRIORIDADE_HUMANO: "encaixe" é rota_agente==5 só como reaproveitamento do
    # atalho determinístico — intencao_rapida=="humano" tem prioridade, tem que cair no
    # agente_humano (igual app.dispatcher.escolher_agente já fazia), não retornar cedo vazio.
    ia_output = IAOutputClassificador(intencao_rapida="triagem", rota_agente=0)
    resposta_agente = RespostaAgente(
        mensagem="Vou te passar para uma atendente! 😊", estado=EstadoConsulta(i="humano"),
    )
    client = _mock_client(ia_output, resposta_agente)

    r = processar_turno(
        busca_paciente_id1=None, busca_paciente_telefone=None, extrair_medico_timeline=None,
        sessao=None, whatsapp_info=WA_INFO, mensagem_agrupada="queria um encaixe pra hoje",
        historico=[], openai_client=client,
    )

    assert r.rota_agente == 5
    assert r.agente_usado == "humano"
    assert "atendente" in r.mensagem
    assert client.beta.chat.completions.parse.call_count == 2


def test_turno_rota_5_confirmar_presenca_retorna_cedo_sem_chamar_agente():
    ia_output = IAOutputClassificador(intencao_rapida="triagem", rota_agente=0)
    client = _mock_client(ia_output)  # só 1 resultado — se despachar_turno for chamado, StopIteration

    r = processar_turno(
        busca_paciente_id1=None, busca_paciente_telefone=None, extrair_medico_timeline=None,
        sessao=None, whatsapp_info=WA_INFO, mensagem_agrupada="quero confirmar presença",
        historico=[], openai_client=client,
    )

    assert r.rota_agente == 5
    assert r.agente_usado is None
    assert client.beta.chat.completions.parse.call_count == 1


def test_turno_remarcacao_sem_cpf_retorna_cedo_mensagem_vazia():
    # sem busca_paciente -> cpf ausente -> buscar_e_processar retorna None sem chamar TiSaude
    # (mesmo padrão de rota==5): agente nunca é chamado, mensagem vazia (sem opinião shadow).
    ia_output = IAOutputClassificador(intencao_rapida="triagem", rota_agente=0)
    client = _mock_client(ia_output)  # só 1 resultado — se dispatcher for chamado, StopIteration

    r = processar_turno(
        busca_paciente_id1=None, busca_paciente_telefone=None, extrair_medico_timeline=None,
        sessao=None, whatsapp_info=WA_INFO, mensagem_agrupada="quero remarcar minha consulta",
        historico=[], openai_client=client,
    )

    assert r.agente_usado is None
    assert r.mensagem == ""
    assert client.beta.chat.completions.parse.call_count == 1


def test_turno_remarcacao_busca_consulta_real_e_retorna_cedo_sem_chamar_agente():
    ia_output = IAOutputClassificador(intencao_rapida="triagem", rota_agente=0)
    client = _mock_client(ia_output)  # só 1 resultado — se dispatcher for chamado, StopIteration

    def handler(request):
        path = request.url.path
        if path == "/api/login":
            return httpx.Response(200, json={"access_token": "tok"})
        if path == "/api/patients":
            return httpx.Response(200, json={"data": [{"id": 55, "name": "Lucas Bueno", "cpf": "11111111111"}]})
        if path == "/api/patients/55/timeline":
            return httpx.Response(200, json={"data": [
                {"date": "2026-07-20", "data": [
                    {"type": "appointment", "id": 999, "date": "2026-07-20", "hour": "10:00",
                     "calendar": {"name": "Giseli Rebechi"}, "status": {"name": "Pendente"},
                     "local": {"name": "Vila Olímpia"}, "healthInsurance": {"name": "Itaú"}},
                ]},
            ]})
        raise AssertionError(f"chamada inesperada (mutação não deveria acontecer aqui): {path}")

    tisaude_client = httpx.Client(transport=httpx.MockTransport(handler))

    r = processar_turno(
        busca_paciente_id1=[{"id": "55", "name": "Lucas Bueno", "cpf": "11111111111"}],
        busca_paciente_telefone=None, extrair_medico_timeline=None,
        sessao=None, whatsapp_info=WA_INFO, mensagem_agrupada="quero remarcar minha consulta",
        historico=[], openai_client=client, tisaude_client=tisaude_client,
    )

    assert r.agente_usado is None
    assert "20/07/2026 às 10:00 com Dr(a). Giseli Rebechi" in r.mensagem
    assert "$$$" not in r.mensagem  # eif1 já stripou o bloco de estado, igual qualquer agente
    assert client.beta.chat.completions.parse.call_count == 1


def test_turno_rota_4_enriquece_base_antes_do_agente():
    ia_output = IAOutputClassificador(intencao_rapida="agenda", rota_agente=2)
    resposta_agente = RespostaAgente(
        mensagem="Vou buscar os horários! 😊",
        estado=EstadoConsulta(i="agenda", unid="Vila Olímpia", conv="Porto Seguro", per="tarde"),
    )
    client = _mock_client(ia_output, resposta_agente)

    sessao = {
        "sessao_intencao": "agenda", "sessao_rota": 4, "coleta_unidade": "Vila Olímpia",
        "coleta_data": "2026-07-20", "coleta_periodo": "tarde", "coleta_convenio": "Porto Seguro",
        "sessao_atualizada_em": "2026-07-12T10:00:00+00:00",
    }

    r = processar_turno(
        busca_paciente_id1=None, busca_paciente_telefone=None, extrair_medico_timeline=None,
        sessao=sessao, whatsapp_info=WA_INFO, mensagem_agrupada="quero ver os horários",
        historico=[{"role": "user", "content": "oi"}], openai_client=client,
    )

    assert r.rota_agente == 4
    # só presente se injetar_contexto_agendamento + preparar_input_agenda rodaram antes do agente
    assert "modo_agenda" in r.base_final
    assert "dia_slots" in r.base_final


def test_turno_passa_historico_pro_agente():
    ia_output = IAOutputClassificador(intencao_rapida="triagem", rota_agente=0)
    resposta_agente = RespostaAgente(mensagem="ok", estado=EstadoConsulta(i="triagem"))
    client = _mock_client(ia_output, resposta_agente)
    historico = [{"role": "user", "content": "mensagem antiga"}, {"role": "assistant", "content": "resposta antiga"}]

    processar_turno(
        busca_paciente_id1=None, busca_paciente_telefone=None, extrair_medico_timeline=None,
        sessao=None, whatsapp_info=WA_INFO, mensagem_agrupada="oi de novo", historico=historico,
        openai_client=client,
    )

    kwargs_agente = client.beta.chat.completions.parse.call_args_list[1].kwargs
    mensagens = kwargs_agente["messages"]
    assert {"role": "user", "content": "mensagem antiga"} in mensagens
    assert {"role": "assistant", "content": "resposta antiga"} in mensagens


def test_turno_repassa_memoria_paciente_pro_base_final():
    ia_output = IAOutputClassificador(intencao_rapida="triagem", rota_agente=0)
    resposta_agente = RespostaAgente(mensagem="ok", estado=EstadoConsulta(i="triagem"))
    client = _mock_client(ia_output, resposta_agente)
    memoria = {"ultimo_medico": "Dra. Giseli Rebechi", "ultima_unidade": "Vila Olímpia"}

    r = processar_turno(
        busca_paciente_id1=None, busca_paciente_telefone=None, extrair_medico_timeline=None,
        sessao=None, whatsapp_info=WA_INFO, mensagem_agrupada="oi", historico=[],
        memoria_paciente=memoria, openai_client=client,
    )

    assert r.base_final.get("memoria_paciente") == memoria


def test_turno_reask_engine_sobrepoe_mensagem_do_agente_quando_sv_bloqueia():
    # State Validator REASK (data no passado) -> Reask Engine assume a mensagem final, igual ao
    # 'SV Router' + fallback `mensagem_final || texto_ia` do node de envio real (ver docstring).
    ia_output = IAOutputClassificador(intencao_rapida="triagem", rota_agente=0)
    resposta_agente = RespostaAgente(
        mensagem="Beleza, marcando pra 01/01/2020!", estado=EstadoConsulta(i="coleta", dt="2020-01-01"),
    )
    client = _mock_client(ia_output, resposta_agente)

    r = processar_turno(
        busca_paciente_id1=None, busca_paciente_telefone=None, extrair_medico_timeline=None,
        sessao=None, whatsapp_info=WA_INFO, mensagem_agrupada="quero pra 01/01/2020",
        historico=[], openai_client=client,
    )

    assert r.sv_result == "REASK"
    assert r.sv_reason == "data_no_passado"
    assert "Não consigo agendar em datas passadas" in r.mensagem
    assert "01/01/2020" in r.mensagem
    assert "marcando" not in r.mensagem


def test_turno_troca_direta_responde_sem_chamar_agente():
    # FIX_TROCA_PERIODO (app.er): pediu período oposto ao salvo, com cache ativo e rota_agente==4
    # -> eh_troca_data=True. app.navegacao_direta_fluxo assume o turno, sem chamar o agente.
    ia_output = IAOutputClassificador(intencao_rapida="agenda", rota_agente=4)
    client = _mock_client(ia_output)  # só 1 resultado — se dispatcher for chamado, StopIteration

    def handler(request):
        path = request.url.path
        if path == "/api/login":
            return httpx.Response(200, json={"access_token": "tok"})
        if path == "/api/schedule/doctors":
            return httpx.Response(200, json={"data": [{"id": 11, "name": "Giseli Rebechi"}]})
        if path.startswith("/api/schedule/20"):
            return httpx.Response(200, json={"dayAvailable": False})
        raise AssertionError(f"chamada inesperada: {path}")

    tisaude_client = httpx.Client(transport=httpx.MockTransport(handler))

    conn = MagicMock()
    cur = MagicMock()
    cur.fetchone.return_value = None
    conn.cursor.return_value.__enter__.return_value = cur

    sessao = {
        "sessao_intencao": "agenda", "sessao_rota": 4, "coleta_unidade": "Vila Olímpia",
        "coleta_data": "2026-07-20", "coleta_periodo": "manha", "coleta_convenio": "Porto Seguro",
        "coleta_medico": "Giseli", "sessao_atualizada_em": "2026-07-12T10:00:00+00:00",
        "agenda_json": {"unidade": "Vila Olímpia", "dias": []},
    }

    r = processar_turno(
        busca_paciente_id1=None, busca_paciente_telefone=None, extrair_medico_timeline=None,
        sessao=sessao, whatsapp_info=WA_INFO, mensagem_agrupada="quero de tarde",
        historico=[], openai_client=client, tisaude_client=tisaude_client, conn=conn,
    )

    assert r.agente_usado is None
    assert r.intencao == "navegacao_direta"
    assert "Nao encontrei horarios disponiveis" in r.mensagem
    assert client.beta.chat.completions.parse.call_count == 1


def test_turno_sem_conn_pula_navegacao_direta_despacha_normal():
    # conn=None -> app.navegacao_direta_fluxo nunca é chamado, comportamento idêntico a antes.
    ia_output = IAOutputClassificador(intencao_rapida="agenda", rota_agente=4)
    resposta_agente = RespostaAgente(mensagem="ok", estado=EstadoConsulta(i="agenda"))
    client = _mock_client(ia_output, resposta_agente)

    sessao = {
        "sessao_intencao": "agenda", "sessao_rota": 4, "coleta_unidade": "Vila Olímpia",
        "coleta_data": "2026-07-20", "coleta_periodo": "manha", "coleta_convenio": "Porto Seguro",
        "coleta_medico": "Giseli", "sessao_atualizada_em": "2026-07-12T10:00:00+00:00",
        "agenda_json": {"unidade": "Vila Olímpia", "dias": []},
    }

    r = processar_turno(
        busca_paciente_id1=None, busca_paciente_telefone=None, extrair_medico_timeline=None,
        sessao=sessao, whatsapp_info=WA_INFO, mensagem_agrupada="quero de tarde",
        historico=[], openai_client=client,
    )

    assert r.agente_usado is not None  # despachou pro agente normal, não ficou preso em None
    assert client.beta.chat.completions.parse.call_count == 2
