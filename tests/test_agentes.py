"""
Testes de app/agentes.py — Fase 3 (structured output). Sem chamada real à OpenAI: client
mockado. Cobre também o round-trip com app.eif1.processar(), que é o ponto inteiro do design
(RespostaAgente empacotada deve continuar sendo interpretada pelo EIF1 sem mudança nenhuma lá).
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock

from app.agentes import EstadoConsulta, RespostaAgente, chamar_agente, empacotar_para_eif1
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
