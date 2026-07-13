"""
Testes de app/pipeline.py::processar_turno — junta os módulos já testados isoladamente
(montar_contexto, classificar_intencao, er, dispatcher, eif1, state_validator) num turno
completo. Sem Postgres real: `sessao`/`historico`/`busca_paciente_*` são passados direto, sem
chamada real à OpenAI: client mockado (2 chamadas por turno normal — classificador + agente
específico; 1 só quando rota_agente==5, que retorna cedo sem chamar agente).
"""

from unittest.mock import MagicMock

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


def test_turno_rota_5_retorna_cedo_sem_chamar_agente():
    ia_output = IAOutputClassificador(intencao_rapida="triagem", rota_agente=0)
    client = _mock_client(ia_output)  # só 1 resultado — se despachar_turno for chamado, StopIteration

    r = processar_turno(
        busca_paciente_id1=None, busca_paciente_telefone=None, extrair_medico_timeline=None,
        sessao=None, whatsapp_info=WA_INFO, mensagem_agrupada="queria um encaixe pra hoje",
        historico=[], openai_client=client,
    )

    assert r.rota_agente == 5
    assert r.agente_usado is None
    assert r.mensagem == ""
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
