"""
Testes de app/tisaude.py — sem rede real: IO usa httpx.MockTransport (client injetável),
lógica pura (resolução de IDs, filtro de consultas, match de médico) testada direto.
"""

import json

import httpx
import pytest

from app.tisaude import (
    STATUS_CANCELAR,
    STATUS_CONFIRMAR,
    buscar_paciente_por_cpf,
    buscar_paciente_por_id,
    cancelar_consulta,
    confirmar_presenca,
    criar_consulta,
    criar_paciente,
    dia_disponivel,
    extrair_lista_medicos,
    filtrar_consultas_ativas,
    horarios_do_dia,
    login,
    medicos_por_unidade,
    resolver_id_health_insurance,
    resolver_id_local,
    resolver_medico,
    timeline_paciente,
)


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


# ---------- resolver_id_local ----------

def test_resolver_id_local_tatuape():
    assert resolver_id_local("Tatuapé") == 2


def test_resolver_id_local_padrao_vila_olimpia():
    assert resolver_id_local("Vila Olímpia") == 1


def test_resolver_id_local_desconhecida_cai_no_padrao():
    assert resolver_id_local("") == 1


# ---------- resolver_id_health_insurance ----------

@pytest.mark.parametrize("convenio,unidade,esperado", [
    ("Porto Seguro", "Vila Olímpia", 30475),
    ("Porto Seguro", "Tatuapé", 30493),
    ("Omint", "Vila Olímpia", 30491),
    ("Omint", "Tatuapé", 30491),
    ("Bradesco Saúde", "Tatuapé", 30490),
    ("Sami", "Vila Olímpia", 32423),
    ("Sami", "Tatuapé", 30492),
    ("Mediservice", "Tatuapé", 47355),
    ("Itaú Seguros", "Tatuapé", 47355),
    ("Particular", "Vila Olímpia", 32285),
    ("Particular", "Tatuapé", 1),
    ("Convênio Desconhecido", "Tatuapé", 1),
])
def test_resolver_id_health_insurance(convenio, unidade, esperado):
    assert resolver_id_health_insurance(convenio, unidade) == esperado


# ---------- resolver_medico ----------

MEDICOS = [
    {"idCalendar": 10, "medico": "STEPHANIE RUGERI DE SOUZA"},
    {"idCalendar": 20, "medico": "ELIAS BUENO"},
]


def test_resolver_medico_match_com_titulo_e_truncamento():
    assert resolver_medico("Dra. Stephanie Rugeri", MEDICOS)["idCalendar"] == 10


def test_resolver_medico_match_por_tokens():
    assert resolver_medico("Rugeri Stephanie", MEDICOS)["idCalendar"] == 10


def test_resolver_medico_sem_preferencia_pega_primeiro():
    assert resolver_medico("sem preferência", MEDICOS)["idCalendar"] == 10


def test_resolver_medico_nome_vazio_pega_primeiro():
    assert resolver_medico("", MEDICOS)["idCalendar"] == 10


def test_resolver_medico_nomeado_sem_match_retorna_none():
    # exec 65707: NUNCA cai no primeiro da lista quando um nome específico foi pedido e não bate
    assert resolver_medico("Dr. Fulano de Tal", MEDICOS) is None


def test_resolver_medico_lista_vazia_retorna_none():
    assert resolver_medico("qualquer", []) is None


# ---------- extrair_lista_medicos ----------

def test_extrair_lista_medicos_formato_data():
    resp = {"data": [{"id": 1, "name": "Dr. A"}, {"id": 2, "name": "Dr. B"}]}
    r = extrair_lista_medicos(resp)
    assert [m["idCalendar"] for m in r] == [1, 2]
    assert [m["medico"] for m in r] == ["Dr. A", "Dr. B"]


def test_extrair_lista_medicos_lista_direta():
    resp = [{"id": 1, "name": "Dr. A"}]
    assert extrair_lista_medicos(resp)[0]["idCalendar"] == 1


def test_extrair_lista_medicos_objeto_unico():
    resp = {"id": 5, "name": "Dr. Único"}
    r = extrair_lista_medicos(resp)
    assert len(r) == 1 and r[0]["idCalendar"] == 5


def test_extrair_lista_medicos_formato_desconhecido_retorna_vazio():
    assert extrair_lista_medicos({"algo": "inesperado"}) == []


# ---------- filtrar_consultas_ativas ----------

TIMELINE = [
    {"date": "2026-07-15", "data": [
        {"type": "appointment", "id": 1, "date": "2026-07-15", "hour": "10:00",
         "calendar": {"name": "Dra. X"}, "status": {"name": "Ativo", "id": 1}},
        {"type": "appointment", "id": 2, "date": "2026-07-15", "hour": "11:00",
         "calendar": {"name": "Dra. Y"}, "status": {"name": "Desmarcado", "id": 4}},
        {"type": "note", "id": 3},
    ]},
    {"date": "2026-07-10", "data": [
        {"type": "appointment", "id": 4, "date": "2026-07-10", "hour": "09:00",
         "calendar": {"name": "Dra. Z"}, "status": {"name": "Ativo", "id": 1}},
    ]},
]


def test_filtrar_consultas_ativas_ignora_desmarcado_e_passado():
    r = filtrar_consultas_ativas(TIMELINE, hoje="2026-07-12")
    assert [c["id"] for c in r] == [1]
    assert r[0]["data_br"] == "15/07/2026"


def test_filtrar_consultas_ativas_respeita_limite():
    timeline_grande = [{"date": "2026-07-20", "data": [
        {"type": "appointment", "id": i, "date": "2026-07-20", "hour": "10:00",
         "calendar": {"name": "Dr."}, "status": {"name": "Ativo"}} for i in range(10)
    ]}]
    r = filtrar_consultas_ativas(timeline_grande, hoje="2026-07-12", limite=5)
    assert len(r) == 5


# ---------- login ----------

def test_login_extrai_access_token():
    def handler(request):
        assert request.url.path == "/api/login"
        body = json.loads(request.content)
        assert "login" in body and "senha" in body
        return httpx.Response(200, json={"access_token": "tok123"})

    assert login(client=_client(handler)) == "tok123"


def test_login_fallback_data_token():
    def handler(request):
        return httpx.Response(200, json={"data": {"token": "tok456"}})

    assert login(client=_client(handler)) == "tok456"


# ---------- buscar_paciente_por_cpf ----------

def test_buscar_paciente_por_cpf_limpa_formatacao_e_manda_bearer():
    def handler(request):
        assert request.url.params["search"] == "12345678900"
        assert request.headers["Authorization"] == "Bearer tok"
        return httpx.Response(200, json={"data": [{"id": 1}]})

    r = buscar_paciente_por_cpf("123.456.789-00", "tok", client=_client(handler))
    assert r == [{"id": 1}]


def test_buscar_paciente_por_id():
    def handler(request):
        assert request.url.path == "/api/patients/42"
        return httpx.Response(200, json={"id": 42, "name": "Fulano"})

    assert buscar_paciente_por_id(42, "tok", client=_client(handler))["name"] == "Fulano"


# ---------- criar_paciente ----------

def test_criar_paciente_converte_nascimento_iso_para_br():
    def handler(request):
        body = json.loads(request.content)
        assert body["dateOfBirth"] == "17/12/2018"
        assert body["name"] == "Miguel"
        return httpx.Response(200, json={"id": 99})

    r = criar_paciente(
        nome="Miguel", cpf="11122233344", celular="11999999999",
        nascimento_iso="2018-12-17", email="", token="tok", client=_client(handler),
    )
    assert r["id"] == 99


# ---------- timeline_paciente ----------

def test_timeline_paciente_manda_datas():
    def handler(request):
        assert request.url.path == "/api/patients/7/timeline"
        assert "startDate" in request.url.params and "endDate" in request.url.params
        return httpx.Response(200, json={"data": [{"date": "2026-07-15"}]})

    r = timeline_paciente(7, "tok", client=_client(handler))
    assert r == [{"date": "2026-07-15"}]


# ---------- medicos_por_unidade ----------

def test_medicos_por_unidade_usa_id_local_certo():
    def handler(request):
        assert request.url.params["local"] == "2"
        return httpx.Response(200, json={"data": [{"id": 1, "name": "Dr. A"}]})

    r = medicos_por_unidade("Tatuapé", "tok", client=_client(handler))
    assert r[0]["idCalendar"] == 1


# ---------- dia_disponivel ----------

def test_dia_disponivel_true():
    def handler(request):
        return httpx.Response(200, json={"dayAvailable": True})

    assert dia_disponivel(10, 1, "2026-07-15", "tok", client=_client(handler)) is True


def test_dia_disponivel_false_quando_ausente():
    def handler(request):
        return httpx.Response(200, json={})

    assert dia_disponivel(10, 1, "2026-07-15", "tok", client=_client(handler)) is False


# ---------- horarios_do_dia ----------

def test_horarios_do_dia_filtra_e_ordena():
    def handler(request):
        return httpx.Response(200, json={"schedules": [{"hour": "14:00:00"}, {"hour": "09:30:00"}]})

    r = horarios_do_dia(10, 1, "2026-07-15", "tok", client=_client(handler))
    assert r == ["09:30", "14:00"]


# ---------- criar_consulta ----------

def test_criar_consulta_monta_body_com_health_insurance_e_data_br():
    def handler(request):
        body = json.loads(request.content)
        assert body["idHealthInsurance"] == 30491  # omint
        assert body["schedule"][0]["dateSchudule"] == "15/07/2026"
        assert body["schedule"][0]["hour"] == "09:00:00"
        return httpx.Response(200, json={"appointment": {"id": 555}})

    r = criar_consulta(
        id_paciente=1, nome="Fulano", cpf="123", nascimento="15/03/1990", celular="11999999999",
        email="", convenio="Omint", unidade="Vila Olímpia", id_calendar=10, id_local=1,
        data_iso="2026-07-15", hora="09:00", token="tok", client=_client(handler),
    )
    assert r["appointment"]["id"] == 555


# ---------- cancelar_consulta / confirmar_presenca ----------

def test_cancelar_consulta_usa_status_code_correto():
    def handler(request):
        assert request.url.path == "/api/schedule/status/update/321/-2"
        body = json.loads(request.content)
        assert body["reasonUnchecked"] == "Paciente desmarcou"
        return httpx.Response(200, json={"success": True})

    r = cancelar_consulta(321, "tok", client=_client(handler))
    assert r == {"success": True}


def test_confirmar_presenca_usa_status_code_correto():
    def handler(request):
        assert request.url.path == f"/api/schedule/status/update/321/{STATUS_CONFIRMAR}"
        return httpx.Response(200, json={"success": True})

    confirmar_presenca(321, "tok", client=_client(handler))


def test_status_cancelar_e_confirmar_sao_os_codigos_certos():
    assert STATUS_CANCELAR == -2
    assert STATUS_CONFIRMAR == 3
