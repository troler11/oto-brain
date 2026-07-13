"""
Testes de app/criar_consulta_fluxo.py — port do sub-workflow 'Ferramenta - Criar Consulta e
Paciente' (IF5VwPZB6uVVbok4). Sem rede/Postgres real (httpx.MockTransport + conn mockado).
"""

from unittest.mock import MagicMock

import httpx

from app.criar_consulta_fluxo import (
    _extrair_celular_criar_paciente,
    _normalizar_nascimento_pg,
    _telefone_com_55,
    criar_consulta_completo,
)

# ---------- helpers puros ----------

def test_extrair_celular_tira_jid_whatsapp():
    assert _extrair_celular_criar_paciente("5511999999999@s.whatsapp.net") == "11999999999"


def test_extrair_celular_tira_sufixo_device():
    assert _extrair_celular_criar_paciente("5511999999999:12@s.whatsapp.net") == "11999999999"


def test_extrair_celular_lixo_vira_vazio():
    assert _extrair_celular_criar_paciente("x" * 20) == ""


def test_normalizar_nascimento_formato_br():
    assert _normalizar_nascimento_pg("17/12/2018") == "2018-12-17"


def test_normalizar_nascimento_iso_com_hora():
    assert _normalizar_nascimento_pg("2018-12-17T00:00:00.000Z") == "2018-12-17"


def test_normalizar_nascimento_vazio():
    assert _normalizar_nascimento_pg(None) == ""
    assert _normalizar_nascimento_pg("") == ""


def test_telefone_com_55_adiciona():
    assert _telefone_com_55("11999999999") == "5511999999999"


def test_telefone_com_55_nao_duplica():
    assert _telefone_com_55("5511999999999") == "5511999999999"


# ---------- criar_consulta_completo (integração) ----------

def _mock_conn():
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cur
    return conn, cur


PACIENTE_API = {
    "id": 7, "name": "LUCAS BUENO", "cpf": "11144477735", "dateOfBirth": "17/12/2018",
    "cellphone": "11999999999", "email": "lucas@x.com",
}


def _handler(medicos=None, pacientes_busca=None, criar_paciente_chamado=None, appointment=None):
    medicos = medicos if medicos is not None else [{"id": 11, "name": "Giseli Rebechi"}]
    pacientes_busca = pacientes_busca if pacientes_busca is not None else [{"id": 7}]
    appointment = appointment if appointment is not None else {
        "appointment": {"id": 999, "patient": {"name": "LUCAS BUENO", "cpf": "11144477735", "dateOfBirth": "17/12/2018"}},
    }

    def handler(request):
        path = request.url.path
        if path == "/api/login":
            return httpx.Response(200, json={"access_token": "tok"})
        if path == "/api/schedule/doctors":
            return httpx.Response(200, json={"data": medicos})
        if path == "/api/patients" and request.method == "GET":
            return httpx.Response(200, json={"data": pacientes_busca})
        if path == "/api/patients/create":
            if criar_paciente_chamado is not None:
                criar_paciente_chamado.append(True)
            return httpx.Response(200, json={"id": 7})
        if path == "/api/patients/7":
            return httpx.Response(200, json=PACIENTE_API)
        if path == "/api/schedule/new":
            return httpx.Response(200, json=appointment)
        raise AssertionError(f"chamada inesperada: {request.method} {path}")

    return handler


def test_medico_nao_encontrado_retorna_erro_sem_agendar():
    client = httpx.Client(transport=httpx.MockTransport(_handler()))
    conn, cur = _mock_conn()
    r = criar_consulta_completo(
        nome_paciente="Lucas", cpf_paciente="11144477735", nascimento_paciente="17/12/2018",
        telefone_paciente="11999999999", email_paciente="", unidade="Vila Olímpia", convenio="Particular",
        nome_medico_escolhido="Stephanie", data="2026-07-20", hora="09:00", conn=conn, tisaude_client=client,
    )
    assert r["erro"] == "MEDICO_NAO_ENCONTRADO"
    cur.execute.assert_not_called()


def test_paciente_existente_nao_chama_criar_paciente():
    chamou = []
    client = httpx.Client(transport=httpx.MockTransport(_handler(criar_paciente_chamado=chamou)))
    conn, cur = _mock_conn()
    r = criar_consulta_completo(
        nome_paciente="Lucas", cpf_paciente="11144477735", nascimento_paciente="17/12/2018",
        telefone_paciente="11999999999", email_paciente="", unidade="Vila Olímpia", convenio="Particular",
        nome_medico_escolhido="Giseli", data="2026-07-20", hora="09:00", conn=conn, tisaude_client=client,
    )
    assert chamou == []
    assert "sucesso" in r["resultado"]
    cur.execute.assert_called_once()


def test_paciente_novo_chama_criar_paciente():
    chamou = []
    client = httpx.Client(transport=httpx.MockTransport(_handler(pacientes_busca=[], criar_paciente_chamado=chamou)))
    conn, cur = _mock_conn()

    # após criar, a 2ª busca por CPF precisa achar o paciente — ajusta handler manualmente
    call_count = {"n": 0}

    def handler(request):
        path = request.url.path
        if path == "/api/login":
            return httpx.Response(200, json={"access_token": "tok"})
        if path == "/api/schedule/doctors":
            return httpx.Response(200, json={"data": [{"id": 11, "name": "Giseli Rebechi"}]})
        if path == "/api/patients" and request.method == "GET":
            call_count["n"] += 1
            return httpx.Response(200, json={"data": [] if call_count["n"] == 1 else [{"id": 7}]})
        if path == "/api/patients/create":
            chamou.append(True)
            return httpx.Response(200, json={"id": 7})
        if path == "/api/patients/7":
            return httpx.Response(200, json=PACIENTE_API)
        if path == "/api/schedule/new":
            return httpx.Response(200, json={"appointment": {"id": 999, "patient": {"name": "LUCAS BUENO", "cpf": "11144477735", "dateOfBirth": "17/12/2018"}}})
        raise AssertionError(f"chamada inesperada: {request.method} {path}")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    r = criar_consulta_completo(
        nome_paciente="Lucas", cpf_paciente="11144477735", nascimento_paciente="17/12/2018",
        telefone_paciente="11999999999", email_paciente="", unidade="Vila Olímpia", convenio="Particular",
        nome_medico_escolhido="Giseli", data="2026-07-20", hora="09:00", conn=conn, tisaude_client=client,
    )
    assert chamou == [True]
    assert "sucesso" in r["resultado"]


def test_insere_agendamento_com_para_terceiro_bug_preservado():
    client = httpx.Client(transport=httpx.MockTransport(_handler()))
    conn, cur = _mock_conn()
    criar_consulta_completo(
        nome_paciente="Lucas", cpf_paciente="11144477735", nascimento_paciente="17/12/2018",
        telefone_paciente="11999999999", email_paciente="", unidade="Vila Olímpia", convenio="Particular",
        nome_medico_escolhido="Giseli", data="2026-07-20", hora="09:00", terceiro="terceiro_false",
        conn=conn, tisaude_client=client,
    )
    sql, params = cur.execute.call_args.args
    assert "INSERT INTO agendamentos" in sql
    # bug preservado do JS: terceiro="terceiro_false" (string não-vazia) -> para_terceiro=False
    assert params["para_terceiro"] is False
    assert params["telefone"] == "5511999999999"
    assert params["nome_paciente"] == "LUCAS BUENO"
    assert params["nascimento"] == "2018-12-17"
    assert params["id_itsaude"] == 999


def test_insere_agendamento_para_terceiro_true_quando_terceiro_vazio():
    client = httpx.Client(transport=httpx.MockTransport(_handler()))
    conn, cur = _mock_conn()
    criar_consulta_completo(
        nome_paciente="Lucas", cpf_paciente="11144477735", nascimento_paciente="17/12/2018",
        telefone_paciente="11999999999", email_paciente="", unidade="Vila Olímpia", convenio="Particular",
        nome_medico_escolhido="Giseli", data="2026-07-20", hora="09:00", terceiro=None,
        conn=conn, tisaude_client=client,
    )
    params = cur.execute.call_args.args[1]
    assert params["para_terceiro"] is True
