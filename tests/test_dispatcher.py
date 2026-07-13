"""
Testes de app/dispatcher.py — mapeamento rota_agente/intencao_rapida -> agente, extraído do
grafo real do n8n (nós "Roteador"/"Roteador de Agente"/"Switch Pacientes"/"Sub-Rota Agenda").
Sem chamada real à OpenAI: client mockado (mesmo padrão de tests/test_agentes.py).
"""

from unittest.mock import MagicMock

import pytest

from app.agentes import EstadoConsulta, RespostaAgente
from app.dispatcher import carregar_prompt, despachar_turno, escolher_agente
from app.er import ResultadoER


def _resultado(rota_agente: int, intencao_rapida: str = "triagem", base: dict | None = None) -> ResultadoER:
    return ResultadoER(
        base=base or {},
        intencao_rapida=intencao_rapida,
        rota_agente=rota_agente,
        texto_usuario="oi",
        ia_output={},
        telefone="5511999999999",
    )


def _mock_client(resposta: RespostaAgente) -> MagicMock:
    client = MagicMock()
    parsed_message = MagicMock()
    parsed_message.parsed = resposta
    completion = MagicMock()
    completion.choices = [MagicMock(message=parsed_message)]
    client.beta.chat.completions.parse.return_value = completion
    return client


# ---------- escolher_agente ----------

def test_humano_tem_prioridade_sobre_rota_agente():
    assert escolher_agente(_resultado(rota_agente=2, intencao_rapida="humano")) == "humano"


def test_rota_5_e_deterministica_retorna_none():
    assert escolher_agente(_resultado(rota_agente=5)) is None


def test_rota_0_triagem():
    assert escolher_agente(_resultado(rota_agente=0)) == "triagem"


def test_rota_1_cancelamento():
    assert escolher_agente(_resultado(rota_agente=1)) == "cancelamento"


def test_rota_3_coleta_terceiro():
    assert escolher_agente(_resultado(rota_agente=3)) == "coleta_terceiro"


@pytest.mark.parametrize(
    "n_pacientes,esperado",
    [(0, "coleta_0pac"), (1, "coleta_1pac"), (2, "coleta_titular"), (5, "coleta_titular")],
)
def test_rota_2_por_numero_de_pacientes(n_pacientes, esperado):
    assert escolher_agente(_resultado(rota_agente=2), n_pacientes=n_pacientes) == esperado


@pytest.mark.parametrize(
    "sub_rota,esperado",
    [
        ("navegacao", "navegacao"),
        ("confirmacao", "confirmacao"),
        ("execucao", "executor"),
        (None, "agenda"),
        ("sub_rota_desconhecida", "agenda"),
    ],
)
def test_rota_4_por_sub_rota_agenda(sub_rota, esperado):
    base = {"_sub_rota_agenda": sub_rota} if sub_rota is not None else {}
    assert escolher_agente(_resultado(rota_agente=4, base=base)) == esperado


def test_rota_desconhecida_cai_pra_triagem():
    assert escolher_agente(_resultado(rota_agente=99)) == "triagem"


# ---------- carregar_prompt ----------

def test_carregar_prompt_le_arquivo_certo():
    conteudo = carregar_prompt("triagem")
    assert "FASE3_STRUCTURED_OUTPUT" in conteudo


def test_carregar_prompt_todos_os_agentes_existem():
    for agente in [
        "triagem", "cancelamento", "coleta_terceiro", "coleta_0pac", "coleta_1pac",
        "coleta_titular", "agenda", "navegacao", "confirmacao", "executor", "humano",
    ]:
        assert carregar_prompt(agente)


def test_carregar_prompt_resolve_tokens_regras_clinica():
    for agente in ["coleta_1pac", "coleta_terceiro", "coleta_titular"]:
        conteudo = carregar_prompt(agente)
        assert "{{REGRAS:" not in conteudo
        assert "A Oto-SP atende os seguintes convênios" in conteudo


# ---------- despachar_turno ----------

def test_despachar_turno_retorna_none_pra_rota_5():
    assert despachar_turno(_resultado(rota_agente=5), [], base_mc={}) is None


def test_despachar_turno_chama_agente_certo_e_retorna_par():
    esperado = RespostaAgente(mensagem="ok", estado=EstadoConsulta(i="triagem"))
    client = _mock_client(esperado)
    resultado = despachar_turno(
        _resultado(rota_agente=0), [{"role": "user", "content": "oi"}], base_mc={}, client=client,
    )
    assert resultado == ("triagem", esperado)
    kwargs = client.beta.chat.completions.parse.call_args.kwargs
    assert "FASE3_STRUCTURED_OUTPUT" in kwargs["messages"][0]["content"]
    assert "{{" not in kwargs["messages"][0]["content"]


# ---------- despachar_turno + tools de agenda (Fase 3 peça C, 13/07/2026) ----------

def test_despachar_turno_sem_conn_nao_liga_tools_mesmo_pra_agenda():
    esperado = RespostaAgente(mensagem="ok", estado=EstadoConsulta(i="agenda"))
    client = _mock_client(esperado)
    despachar_turno(_resultado(rota_agente=4), [], base_mc={}, client=client)
    kwargs = client.beta.chat.completions.parse.call_args.kwargs
    assert "tools" not in kwargs or kwargs["tools"] is None


def test_despachar_turno_com_conn_liga_tools_pro_agente_agenda():
    esperado = RespostaAgente(mensagem="ok", estado=EstadoConsulta(i="agenda"))
    client = _mock_client(esperado)
    # sem tool_calls (resposta final direto) — precisa setar explícito, senão o MagicMock
    # auto-cria `.tool_calls` truthy e o loop de tool-calling nunca para (ver app.agentes).
    client.beta.chat.completions.parse.return_value.choices[0].message.tool_calls = None
    conn = MagicMock()
    despachar_turno(_resultado(rota_agente=4), [], base_mc={}, client=client, conn=conn)
    kwargs = client.beta.chat.completions.parse.call_args.kwargs
    nomes = {t["function"]["name"] for t in kwargs["tools"]}
    assert nomes == {"buscar_agenda", "navegar_agenda"}


def test_despachar_turno_com_conn_nao_liga_tools_pro_agente_navegacao():
    # "Agente Navegacao" tem tools com o MESMO nome no n8n mas sub-workflow ainda não
    # confirmado como sendo o mesmo — não deve ganhar as tools por engano.
    esperado = RespostaAgente(mensagem="ok", estado=EstadoConsulta(i="navegacao"))
    client = _mock_client(esperado)
    conn = MagicMock()
    despachar_turno(
        _resultado(rota_agente=4, base={"_sub_rota_agenda": "navegacao"}), [], base_mc={}, client=client, conn=conn,
    )
    kwargs = client.beta.chat.completions.parse.call_args.kwargs
    assert "tools" not in kwargs or kwargs["tools"] is None
