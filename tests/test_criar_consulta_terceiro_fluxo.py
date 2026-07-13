"""
Testes de app/criar_consulta_terceiro_fluxo.py — port do sub-workflow 'Ferramenta - Criar
Consulta Terceiro' (xfpTs6C4BmnXs3jB). Sem rede/Postgres real.
"""

from unittest.mock import MagicMock

import httpx

from app.criar_consulta_terceiro_fluxo import criar_consulta_terceiro_completo


def _mock_conn():
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cur
    return conn, cur


PACIENTE_API = {
    "id": 9, "name": "MIGUEL BUENO", "cpf": "22233344456", "dateOfBirth": "17/12/2018",
    "cellphone": "11999999999", "email": "",
}


def _handler(medicos=None, pacientes_busca=None, criar_paciente_chamado=None):
    medicos = medicos if medicos is not None else [{"id": 11, "name": "Giseli Rebechi"}]
    pacientes_busca = pacientes_busca if pacientes_busca is not None else [{"id": 9}]

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
            return httpx.Response(200, json={"id": 9})
        if path == "/api/patients/9":
            return httpx.Response(200, json=PACIENTE_API)
        if path == "/api/schedule/new":
            return httpx.Response(200, json={
                "appointment": {"id": 777, "patient": {"name": "MIGUEL BUENO", "cpf": "22233344456", "dateOfBirth": "17/12/2018"}},
            })
        raise AssertionError(f"chamada inesperada: {request.method} {path}")

    return handler


def _chamar(conn, client, **overrides):
    args = {
        "nome_dependente": "Miguel Bueno", "cpf_dependente": "22233344456",
        "nascimento_dependente": "17/12/2018", "nome_titular": "Lucas Bueno",
        "cpf_titular": "11144477735", "nascimento_titular": "01/01/1990",
        "telefone_titular": "11999999999", "email_paciente": "", "unidade": "Vila Olímpia",
        "convenio": "Particular", "nome_medico_escolhido": "Giseli", "data": "2026-07-20",
        "hora": "09:00", "conn": conn, "tisaude_client": client,
    }
    args.update(overrides)
    return criar_consulta_terceiro_completo(**args)


def test_medico_nao_encontrado_retorna_erro_sem_agendar():
    client = httpx.Client(transport=httpx.MockTransport(_handler()))
    conn, cur = _mock_conn()
    r = _chamar(conn, client, nome_medico_escolhido="Stephanie")
    assert r["erro"] == "MEDICO_NAO_ENCONTRADO"
    cur.execute.assert_not_called()


def test_dependente_existente_nao_chama_criar_paciente():
    chamou = []
    client = httpx.Client(transport=httpx.MockTransport(_handler(criar_paciente_chamado=chamou)))
    conn, cur = _mock_conn()
    r = _chamar(conn, client)
    assert chamou == []
    assert "sucesso" in r["resultado"]


def test_dependente_novo_chama_criar_paciente():
    chamou = []
    call_count = {"n": 0}

    def handler(request):
        path = request.url.path
        if path == "/api/login":
            return httpx.Response(200, json={"access_token": "tok"})
        if path == "/api/schedule/doctors":
            return httpx.Response(200, json={"data": [{"id": 11, "name": "Giseli Rebechi"}]})
        if path == "/api/patients" and request.method == "GET":
            call_count["n"] += 1
            return httpx.Response(200, json={"data": [] if call_count["n"] == 1 else [{"id": 9}]})
        if path == "/api/patients/create":
            chamou.append(True)
            return httpx.Response(200, json={"id": 9})
        if path == "/api/patients/9":
            return httpx.Response(200, json=PACIENTE_API)
        if path == "/api/schedule/new":
            return httpx.Response(200, json={"appointment": {"id": 777, "patient": {"name": "MIGUEL BUENO", "cpf": "22233344456", "dateOfBirth": "17/12/2018"}}})
        raise AssertionError(f"chamada inesperada: {request.method} {path}")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    conn, cur = _mock_conn()
    r = _chamar(conn, client)
    assert chamou == [True]
    assert "sucesso" in r["resultado"]


def test_insere_agendamento_com_contato_id_do_titular_e_para_terceiro_true():
    client = httpx.Client(transport=httpx.MockTransport(_handler()))
    conn, cur = _mock_conn()
    _chamar(conn, client)
    sql, params = cur.execute.call_args.args
    assert "INSERT INTO agendamentos" in sql
    assert params["telefone"] == "5511999999999"  # telefone do TITULAR, não do dependente
    assert params["nome_paciente"] == "MIGUEL BUENO"
    assert params["cpf_paciente"] == "22233344456"
    assert params["nascimento"] == "2018-12-17"
    assert params["id_itsaude"] == 777
