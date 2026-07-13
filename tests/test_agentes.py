"""
Testes de app/agentes.py — Fase 3 (structured output). Sem chamada real à OpenAI: client
mockado. Cobre também o round-trip com app.eif1.processar(), que é o ponto inteiro do design
(RespostaAgente empacotada deve continuar sendo interpretada pelo EIF1 sem mudança nenhuma lá).
"""

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock

from app.agentes import (
    EstadoConsulta,
    IAOutputClassificador,
    RespostaAgente,
    chamar_agente,
    classificar_intencao,
    empacotar_para_eif1,
)
from app.eif1 import processar as processar_eif1

SESSAO_ATIVA = {"sessao_intencao": "coleta", "sessao_atualizada_em": datetime.now(timezone.utc).isoformat()}


def _mock_client(resposta: RespostaAgente) -> MagicMock:
    client = MagicMock()
    parsed_message = MagicMock()
    parsed_message.parsed = resposta
    completion = MagicMock()
    completion.choices = [MagicMock(message=parsed_message)]
    client.beta.chat.completions.parse.return_value = completion
    return client


def test_chamar_agente_retorna_resposta_parseada():
    esperado = RespostaAgente(mensagem="Qual horário prefere? 😊", estado=EstadoConsulta(i="coleta"))
    client = _mock_client(esperado)
    r = chamar_agente("system prompt qualquer", [{"role": "user", "content": "oi"}], client=client)
    assert r is esperado


def test_chamar_agente_manda_system_prompt_e_mensagens_pro_client():
    esperado = RespostaAgente(mensagem="ok", estado=EstadoConsulta(i="triagem"))
    client = _mock_client(esperado)
    chamar_agente("SYSTEM", [{"role": "user", "content": "oi"}], client=client)
    kwargs = client.beta.chat.completions.parse.call_args.kwargs
    assert kwargs["messages"][0] == {"role": "system", "content": "SYSTEM"}
    assert kwargs["messages"][1] == {"role": "user", "content": "oi"}
    assert kwargs["response_format"] is RespostaAgente


def test_chamar_agente_usa_model_customizado():
    esperado = RespostaAgente(mensagem="ok", estado=EstadoConsulta(i="triagem"))
    client = _mock_client(esperado)
    chamar_agente("SYSTEM", [], client=client, model="gpt-4o-mini")
    assert client.beta.chat.completions.parse.call_args.kwargs["model"] == "gpt-4o-mini"


def test_chamar_agente_sem_tools_nunca_manda_none_pro_sdk():
    # O SDK real da OpenAI itera `tools` incondicionalmente em `_validate_input_tools` — mandar
    # `tools=None` quebra com TypeError na hora ('NoneType' object is not iterable). Achado em
    # smoke test real de produção (13/07/2026) — nenhum dos outros testes pegava isso porque o
    # client mockado aqui não reexecuta essa validação do SDK.
    esperado = RespostaAgente(mensagem="ok", estado=EstadoConsulta(i="triagem"))
    client = _mock_client(esperado)
    chamar_agente("SYSTEM", [], client=client)
    assert client.beta.chat.completions.parse.call_args.kwargs["tools"] == []


# ---------- chamar_agente com tool-calling (Fase 3, 13/07/2026) ----------

def _tool_call(id_, name, arguments: dict):
    tc = MagicMock()
    tc.id = id_
    tc.function.name = name
    tc.function.arguments = json.dumps(arguments)
    return tc


def _completion_com_tool_calls(tool_calls):
    msg = MagicMock()
    msg.tool_calls = tool_calls
    msg.content = None
    completion = MagicMock()
    completion.choices = [MagicMock(message=msg)]
    return completion


def _completion_final(resposta):
    msg = MagicMock()
    msg.tool_calls = None
    msg.parsed = resposta
    completion = MagicMock()
    completion.choices = [MagicMock(message=msg)]
    return completion


TOOLS_TESTE = [{"type": "function", "function": {"name": "navegar_agenda", "description": "...", "parameters": {}}}]


def test_chamar_agente_sem_tools_ignora_tool_calls_do_mock():
    # sem `tools`, o loop nem olha pra `message.tool_calls` (MagicMock cria o atributo sozinho,
    # truthy por padrão) — comportamento idêntico a antes de existir tool-calling.
    esperado = RespostaAgente(mensagem="ok", estado=EstadoConsulta(i="triagem"))
    client = _mock_client(esperado)
    r = chamar_agente("SYSTEM", [], client=client)
    assert r is esperado
    assert client.beta.chat.completions.parse.call_count == 1


def test_chamar_agente_executa_tool_call_e_continua_ate_resposta_final():
    esperado = RespostaAgente(mensagem="Horário 09:00 disponível!", estado=EstadoConsulta(i="agenda"))
    tc = _tool_call("call_1", "navegar_agenda", {"acao": "ver", "telefone_paciente": "5511999999999", "unidade": "Vila Olímpia"})
    client = MagicMock()
    client.beta.chat.completions.parse.side_effect = [
        _completion_com_tool_calls([tc]),
        _completion_final(esperado),
    ]
    executor = MagicMock(return_value={"status": "OK", "dia": {"data": "2026-07-20"}})

    r = chamar_agente(
        "SYSTEM", [{"role": "user", "content": "tem horário?"}], client=client,
        tools=TOOLS_TESTE, executores={"navegar_agenda": executor},
    )

    assert r is esperado
    assert client.beta.chat.completions.parse.call_count == 2
    executor.assert_called_once_with({"acao": "ver", "telefone_paciente": "5511999999999", "unidade": "Vila Olímpia"})

    segunda_chamada_msgs = client.beta.chat.completions.parse.call_args_list[1].kwargs["messages"]
    msg_assistant = segunda_chamada_msgs[-2]
    msg_tool = segunda_chamada_msgs[-1]
    assert msg_assistant["role"] == "assistant"
    assert msg_assistant["tool_calls"][0]["id"] == "call_1"
    assert msg_assistant["tool_calls"][0]["function"]["name"] == "navegar_agenda"
    assert msg_tool == {"role": "tool", "tool_call_id": "call_1", "content": json.dumps({"status": "OK", "dia": {"data": "2026-07-20"}}, ensure_ascii=False)}


def test_chamar_agente_tool_call_sem_executor_devolve_erro_pro_modelo():
    esperado = RespostaAgente(mensagem="ok", estado=EstadoConsulta(i="triagem"))
    tc = _tool_call("call_1", "tool_desconhecida", {})
    client = MagicMock()
    client.beta.chat.completions.parse.side_effect = [
        _completion_com_tool_calls([tc]),
        _completion_final(esperado),
    ]

    chamar_agente("SYSTEM", [], client=client, tools=TOOLS_TESTE, executores={})

    msg_tool = client.beta.chat.completions.parse.call_args_list[1].kwargs["messages"][-1]
    assert json.loads(msg_tool["content"]) == {"erro": "tool 'tool_desconhecida' sem executor"}


def test_chamar_agente_excede_max_tool_turns_estoura_erro():
    tc = _tool_call("call_1", "navegar_agenda", {})
    client = MagicMock()
    client.beta.chat.completions.parse.side_effect = [_completion_com_tool_calls([tc]) for _ in range(10)]

    try:
        chamar_agente("SYSTEM", [], client=client, tools=TOOLS_TESTE, executores={"navegar_agenda": lambda a: {}})
        assert False, "deveria ter estourado RuntimeError"
    except RuntimeError as e:
        assert "excedeu" in str(e)


# ---------- empacotar_para_eif1 + round-trip com app.eif1.processar ----------

def test_empacotar_produz_json_com_output_e_meta():
    resposta = RespostaAgente(mensagem="Perfeito! 😊", estado=EstadoConsulta(i="coleta", unid="Vila Olímpia"))
    raw = empacotar_para_eif1(resposta)
    assert '"output"' in raw
    assert '"meta"' in raw
    assert "Perfeito!" in raw


def test_round_trip_com_eif1_extrai_campos_corretamente():
    resposta = RespostaAgente(
        mensagem="Show, vou agendar!",
        estado=EstadoConsulta(i="coleta", unid="Tatuapé", med="Dra. Giseli Rebechi", per="manha", dt="2026-07-15"),
    )
    raw = empacotar_para_eif1(resposta)
    # carregar_sessao com sessao_intencao preenchida evita o FIX_SAUDACAO_PRIMEIRO_CONTATO do
    # EIF1 (sessão "nova" ganha saudação prefixada — comportamento correto, não é o que este
    # teste quer verificar).
    r = processar_eif1(raw, extrair_rota={}, carregar_sessao=SESSAO_ATIVA)
    assert r.intencao == "coleta"
    assert r.unidade_coleta == "Tatuapé"
    assert r.medico_coleta == "Dra. Giseli Rebechi"
    assert r.periodo_coleta == "manha"
    assert r.data_coleta == "2026-07-15"
    assert r.texto_ia == "Show, vou agendar!"


def test_round_trip_terceiro_e_dados_pessoais():
    # CPF de teste clássico (111.444.777-35), dígitos verificadores OK — mesma constante de
    # tests/test_eif1.py::CPF_VALIDO; "11111111111" seria rejeitado pelo FIX_CPF_DV_BACKSTOP
    # (dígitos repetidos nunca são CPF real).
    resposta = RespostaAgente(
        mensagem="Certo, e o CPF?",
        estado=EstadoConsulta(i="coleta", t=True, d="Miguel Bueno", c="11144477735", n="17/12/2018"),
    )
    raw = empacotar_para_eif1(resposta)
    r = processar_eif1(raw, extrair_rota={})
    assert r.eh_terceiro is True
    assert r.nome_dependente == "Miguel Bueno"
    assert r.cpf_dependente == "11144477735"
    assert r.nascimento_dependente == "17/12/2018"


# ---------- classificar_intencao (port do nó "AI Agent") ----------

def test_classificar_intencao_retorna_resposta_parseada():
    esperado = IAOutputClassificador(intencao_rapida="agenda", rota_agente=2)
    client = _mock_client(esperado)
    contexto = {
        "sessao_intencao": "", "sessao_rota": 0, "cache_ativo": False,
        "mensagem_agrupada": "quero agendar uma consulta",
    }
    r = classificar_intencao(contexto, client=client)
    assert r is esperado


def test_classificar_intencao_resolve_placeholders_no_prompt():
    esperado = IAOutputClassificador()
    client = _mock_client(esperado)
    contexto = {
        "sessao_intencao": "coleta", "sessao_rota": 2, "cache_ativo": True,
        "mensagem_agrupada": "quero para minha filha",
    }
    classificar_intencao(contexto, client=client)
    prompt_enviado = client.beta.chat.completions.parse.call_args.kwargs["messages"][0]["content"]
    assert "{{" not in prompt_enviado
    assert "quero para minha filha" in prompt_enviado
    assert "Intenção Atual: coleta" in prompt_enviado
    assert "Rota Atual: 2" in prompt_enviado


def test_classificar_intencao_usa_response_format_correto():
    esperado = IAOutputClassificador()
    client = _mock_client(esperado)
    classificar_intencao({"sessao_intencao": "", "sessao_rota": 0, "cache_ativo": False, "mensagem_agrupada": "oi"}, client=client)
    kwargs = client.beta.chat.completions.parse.call_args.kwargs
    assert kwargs["response_format"] is IAOutputClassificador


def test_ia_output_classificador_defaults_fieis_ao_no_original():
    d = IAOutputClassificador().model_dump()
    assert d == {
        "intencao_rapida": "triagem", "rota_agente": 0, "eh_confirmacao": False,
        "eh_navegacao": False, "eh_confirmacao_cancelamento": False,
        "eh_resposta_generica": False, "bypass_agente_humano": False,
        "precisa_agente_completo": True,
    }
