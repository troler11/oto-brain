"""
Testes de app/consultar_consultas_fluxo.py — port do sub-workflow 'Ferramenta - Consultar
Minhas Consultas' (iOhQPjizddY88k4K). Sem rede real (httpx.MockTransport).
"""

import httpx

from app.consultar_consultas_fluxo import _formatar_consultas, consultar_minhas_consultas


# ---------- _formatar_consultas ----------

def test_sem_dias_retorna_texto_padrao():
    assert _formatar_consultas([]) == "O paciente não possui consultas marcadas para este período."


def test_dias_sem_appointment_ativo_retorna_texto_historico():
    timeline = [{"date": "2026-07-14", "data": [{"type": "note"}]}]
    assert _formatar_consultas(timeline) == "O paciente possui histórico, mas não há consultas ativas ou futuras cadastradas."


def test_filtra_desmarcadas():
    timeline = [{"date": "2026-07-14", "data": [
        {"type": "appointment", "id": 1, "date": "2026-07-14", "hour": "09:00",
         "calendar": {"name": "Giseli Rebechi"}, "status": {"name": "Desmarcado pelo paciente"}},
    ]}]
    assert _formatar_consultas(timeline) == "O paciente possui histórico, mas não há consultas ativas ou futuras cadastradas."


def test_formata_consultas_encontradas():
    timeline = [{"date": "2026-07-14", "data": [
        {"type": "appointment", "id": 111, "date": "2026-07-14", "hour": "09:00",
         "calendar": {"name": "Giseli Rebechi"}, "status": {"name": "Pendente"}},
    ]}]
    r = _formatar_consultas(timeline)
    assert r == "Consultas encontradas para este paciente:\n- Dia 14/07/2026 às 09:00 com Dr(a). Giseli Rebechi. (ID_AGENDAMENTO: 111)"


def test_fallbacks_hora_e_medico():
    timeline = [{"date": "2026-07-14", "data": [
        {"type": "appointment", "id": 1, "date": "2026-07-14"},
    ]}]
    r = _formatar_consultas(timeline)
    assert "Hora Indefinida" in r
    assert "Médico não informado" in r


def test_cap_de_5_consultas():
    eventos = [
        {"type": "appointment", "id": i, "date": "2026-07-14", "hour": "09:00", "calendar": {"name": "X"}, "status": {"name": "Pendente"}}
        for i in range(8)
    ]
    timeline = [{"date": "2026-07-14", "data": eventos}]
    r = _formatar_consultas(timeline)
    assert r.count("ID_AGENDAMENTO") == 5


# ---------- consultar_minhas_consultas (integração) ----------

def _handler(pacientes=None, timeline=None):
    pacientes = pacientes if pacientes is not None else [{"id": 7}]
    timeline = timeline if timeline is not None else [{"date": "2026-07-14", "data": [
        {"type": "appointment", "id": 1, "date": "2026-07-14", "hour": "09:00", "calendar": {"name": "Giseli Rebechi"}, "status": {"name": "Pendente"}},
    ]}]

    def handler(request):
        path = request.url.path
        if path == "/api/login":
            return httpx.Response(200, json={"access_token": "tok"})
        if path == "/api/patients":
            return httpx.Response(200, json={"data": pacientes})
        if path == "/api/patients/7/timeline":
            return httpx.Response(200, json={"data": timeline})
        raise AssertionError(f"chamada inesperada: {path}")

    return handler


def test_consultar_minhas_consultas_sucesso():
    client = httpx.Client(transport=httpx.MockTransport(_handler()))
    r = consultar_minhas_consultas("11144477735", tisaude_client=client)
    assert "Giseli Rebechi" in r["resultado"]


def test_consultar_minhas_consultas_paciente_nao_encontrado():
    client = httpx.Client(transport=httpx.MockTransport(_handler(pacientes=[])))
    r = consultar_minhas_consultas("11144477735", tisaude_client=client)
    assert r["resultado"] == "O paciente não possui consultas marcadas para este período."
