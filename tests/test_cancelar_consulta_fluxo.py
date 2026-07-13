"""
Testes de app/cancelar_consulta_fluxo.py — port do sub-workflow 'Ferramenta - Cancelar Consulta'
(i4m4RaNI7E0RkgXp). Sem rede real (httpx.MockTransport).
"""

import httpx

from app.cancelar_consulta_fluxo import (
    _filtrar_consultas_ativas_cancelamento,
    _resolver_id_real,
    cancelar_consulta_completo,
)

TIMELINE = [
    {"date": "2026-07-14", "data": [
        {"type": "appointment", "id": 111, "date": "2026-07-14", "hour": "09:00",
         "calendar": {"name": "Giseli Rebechi"}, "status": {"name": "Pendente"}},
    ]},
    {"date": "2026-07-20", "data": [
        {"type": "appointment", "id": 222, "date": "2026-07-20", "hour": "10:00",
         "calendar": {"name": "Elias Lobo Braga"}, "status": {"name": "Confirmado"}},
        {"type": "appointment", "id": 333, "date": "2026-07-20", "hour": "11:00",
         "calendar": {"name": "Giseli Rebechi"}, "status": {"name": "Desmarcado"}},
    ]},
]


# ---------- _filtrar_consultas_ativas_cancelamento ----------

def test_filtra_desmarcadas_e_passadas():
    r = _filtrar_consultas_ativas_cancelamento(TIMELINE, hoje="2026-07-01")
    assert [c["id"] for c in r] == [111, 222]
    assert r[0]["dataBR"] == "14/07/2026"
    assert "status_id" not in r[0]


def test_filtra_data_passada():
    r = _filtrar_consultas_ativas_cancelamento(TIMELINE, hoje="2026-07-15")
    assert [c["id"] for c in r] == [222]


# ---------- _resolver_id_real ----------

def test_resolve_numero_via_consultas_args():
    args = [{"id": 999}, {"id": 888}]
    assert _resolver_id_real("2", args, []) == "888"


def test_resolve_numero_via_consultas_fresh_sem_args():
    fresh = [{"id": 111}, {"id": 222}]
    assert _resolver_id_real("1", None, fresh) == "111"


def test_id_fora_do_range_1_5_usado_direto():
    assert _resolver_id_real("48213", None, []) == "48213"


# ---------- cancelar_consulta_completo (integração) ----------

def _handler(pacientes=None, timeline=None, cancelar_resp=None):
    pacientes = pacientes if pacientes is not None else [{"id": 55, "name": "Lucas"}]
    timeline = timeline if timeline is not None else TIMELINE
    cancelar_resp = cancelar_resp if cancelar_resp is not None else {"success": True}

    def handler(request):
        path = request.url.path
        if path == "/api/login":
            return httpx.Response(200, json={"access_token": "tok"})
        if path == "/api/patients":
            return httpx.Response(200, json={"data": pacientes})
        if path == "/api/patients/55/timeline":
            return httpx.Response(200, json={"data": timeline})
        if path.startswith("/api/schedule/status/update/"):
            return httpx.Response(200, json=cancelar_resp)
        raise AssertionError(f"chamada inesperada: {path}")

    return handler


def test_cpf_nao_encontrado():
    client = httpx.Client(transport=httpx.MockTransport(_handler(pacientes=[])))
    r = cancelar_consulta_completo(cpf="12345678900", tisaude_client=client, hoje=__import__("datetime").date(2026, 7, 1))
    assert r["status"] == "CPF_NAO_ENCONTRADO"


def test_sem_id_agendamento_lista_consultas():
    client = httpx.Client(transport=httpx.MockTransport(_handler()))
    r = cancelar_consulta_completo(cpf="12345678900", tisaude_client=client, hoje=__import__("datetime").date(2026, 7, 1))
    assert r["status"] == "AGUARDANDO_ESCOLHA"
    assert r["id_paciente"] == 55
    assert len(r["consultas"]) == 2
    assert "1. 14/07/2026 às 09:00 com Dr(a). Giseli Rebechi (ID: 111)" in r["resultado"]


def test_sem_consultas_ativas():
    client = httpx.Client(transport=httpx.MockTransport(_handler(timeline=[])))
    r = cancelar_consulta_completo(cpf="12345678900", tisaude_client=client)
    assert r["status"] == "SEM_CONSULTAS"


def test_cancelar_com_numero_da_lista_sucesso():
    client = httpx.Client(transport=httpx.MockTransport(_handler()))
    r = cancelar_consulta_completo(
        cpf="12345678900", id_agendamento="2", tisaude_client=client, hoje=__import__("datetime").date(2026, 7, 1),
    )
    assert r["status"] == "CANCELADO"


def test_cancelar_falha_retorna_erro():
    client = httpx.Client(transport=httpx.MockTransport(_handler(cancelar_resp={})))
    r = cancelar_consulta_completo(cpf="12345678900", id_agendamento="1", tisaude_client=client, hoje=__import__("datetime").date(2026, 7, 1))
    assert r["status"] == "ERRO"
