"""
Testes de app/confirmar_presenca_fluxo.py — orquestração do rota_agente==5 (confirmar presença)
com o client TiSaude real (sem rede: httpx.MockTransport). Escopo só LEITURA (13/07/2026): a
mutação real (tisaude.confirmar_presenca) NUNCA é chamada por este módulo ainda — os testes
abaixo confirmam isso explicitamente (nenhum handler mocka o endpoint de status/update).
"""

import httpx

from app.confirmar_presenca_fluxo import buscar_consultas_paciente, processar_rota5

UDI_TIMELINE = {
    "data": [
        {
            "date": "2026-07-20",
            "data": [
                {
                    "type": "appointment",
                    "id": 999,
                    "date": "2026-07-20",
                    "hour": "10:00",
                    "calendar": {"name": "Giseli Rebechi"},
                    "status": {"id": 1, "name": "Pendente"},
                },
            ],
        },
    ],
}


def _client_login_e_timeline(paciente_id=42):
    def handler(request):
        if request.url.path == "/api/login":
            return httpx.Response(200, json={"access_token": "tok"})
        if request.url.path == f"/api/patients/{paciente_id}/timeline":
            return httpx.Response(200, json=UDI_TIMELINE)
        raise AssertionError(f"chamada inesperada: {request.url.path}")

    return httpx.Client(transport=httpx.MockTransport(handler))


# ---------- buscar_consultas_paciente ----------

def test_buscar_consultas_paciente_loga_busca_e_adapta_shape():
    r = buscar_consultas_paciente(42, client=_client_login_e_timeline())
    assert r == [{
        "id": 999, "dataBR": "20/07/2026", "hora": "10:00", "medico": "Giseli Rebechi",
        "status_nome": "Pendente", "status_id": 1,
    }]


# ---------- processar_rota5 ----------

def test_escolher_titular_nao_chama_tisaude():
    base = {
        "_sub_confirmar": "escolher_titular",
        "pacientes": [{"nome": "Lucas"}, {"nome": "Ana"}],
    }
    r = processar_rota5(base, client=None)
    assert "Para quem você quer confirmar" in r["output"]


def test_verificar_busca_consultas_reais_e_pergunta():
    base = {"_sub_confirmar": "verificar", "id_tisaude": 42}
    r = processar_rota5(base, client=_client_login_e_timeline())
    assert r["auto_confirmar"] is False
    assert "Deseja confirmar sua presença" in r["output"]
    assert "20/07/2026" in r["output"]


def test_verificar_confirma_direto_decide_auto_mas_nao_muta():
    base = {"_sub_confirmar": "verificar", "id_tisaude": 42, "_confirma_direto": True}
    r = processar_rota5(base, client=_client_login_e_timeline())
    assert r["auto_confirmar"] is True
    assert r["id_agendamento"] == "999"
    # nenhuma chamada de mutação (status/update) foi feita — handler do client teria estourado
    # AssertionError se tentasse; chegou até aqui sem erro = só leitura confirmada.


def test_sem_id_tisaude_retorna_none():
    base = {"_sub_confirmar": "verificar"}
    assert processar_rota5(base, client=_client_login_e_timeline()) is None


def test_sub_confirmar_recusou_retorna_none_deixa_pro_legado():
    assert processar_rota5({"_sub_confirmar": "recusou"}, client=None) is None


def test_sub_confirmar_ausente_retorna_none():
    # cobre os rota=5 que na verdade sao bypass humano (encaixe, lista de espera) — sem
    # _sub_confirmar setado, nao devem tentar TiSaude
    assert processar_rota5({}, client=None) is None


def test_falha_de_rede_na_tisaude_nao_derruba_devolve_none():
    def handler(request):
        raise httpx.ConnectError("timeout", request=request)

    base = {"_sub_confirmar": "verificar", "id_tisaude": 42}
    client = httpx.Client(transport=httpx.MockTransport(handler))
    assert processar_rota5(base, client=client) is None
