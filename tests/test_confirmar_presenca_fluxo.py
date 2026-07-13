"""
Testes de app/confirmar_presenca_fluxo.py — orquestração do rota_agente==5 (confirmar presença)
com o client TiSaude real (sem rede: httpx.MockTransport).

`processar_rota5`/`buscar_consultas_paciente` (leitura, ligados ao pipeline): a mutação real
NUNCA é chamada por eles — os testes correspondentes abaixo confirmam isso explicitamente
(nenhum handler mocka o endpoint de status/update). `confirmar_presenca_completo` (mutação, NÃO
ligado a nenhum dispatcher/agente/tool — ver docstring do módulo) tem seção própria de testes.
"""

from unittest.mock import MagicMock

import httpx

from app.confirmar_presenca_fluxo import buscar_consultas_paciente, confirmar_presenca_completo, processar_rota5

TIMELINE = {
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


def _client_login_busca_e_timeline(paciente_id=7, pacientes=None):
    pacientes = pacientes if pacientes is not None else [{"id": paciente_id}]

    def handler(request):
        if request.url.path == "/api/login":
            return httpx.Response(200, json={"access_token": "tok"})
        if request.url.path == "/api/patients":
            return httpx.Response(200, json={"data": pacientes})
        if request.url.path == f"/api/patients/{paciente_id}/timeline":
            return httpx.Response(200, json=TIMELINE)
        raise AssertionError(f"chamada inesperada: {request.url.path}")

    return httpx.Client(transport=httpx.MockTransport(handler))


# ---------- buscar_consultas_paciente ----------

def test_buscar_consultas_paciente_busca_por_cpf_e_formata_shape():
    r = buscar_consultas_paciente("11144477735", client=_client_login_busca_e_timeline())
    assert r == [{
        "id": 999, "dataISO": "2026-07-20", "dataBR": "20/07/2026", "hora": "10:00",
        "medico": "Giseli Rebechi", "status_id": 1, "status_nome": "Pendente",
    }]


def test_buscar_consultas_paciente_sem_paciente_retorna_vazio():
    r = buscar_consultas_paciente("11144477735", client=_client_login_busca_e_timeline(pacientes=[]))
    assert r == []


# ---------- processar_rota5 ----------

def test_escolher_titular_nao_chama_tisaude():
    base = {
        "_sub_confirmar": "escolher_titular",
        "pacientes": [{"nome": "Lucas"}, {"nome": "Ana"}],
    }
    r = processar_rota5(base, client=None)
    assert "Para quem você quer confirmar" in r["output"]


def test_verificar_busca_consultas_reais_e_pergunta():
    base = {"_sub_confirmar": "verificar", "cpf": "11144477735"}
    r = processar_rota5(base, client=_client_login_busca_e_timeline())
    assert r["auto_confirmar"] is False
    assert "Deseja confirmar sua presença" in r["output"]
    assert "20/07/2026" in r["output"]


def test_verificar_confirma_direto_decide_auto_mas_nao_muta():
    base = {"_sub_confirmar": "verificar", "cpf": "11144477735", "_confirma_direto": True}
    r = processar_rota5(base, client=_client_login_busca_e_timeline())
    assert r["auto_confirmar"] is True
    assert r["id_agendamento"] == "999"
    # nenhuma chamada de mutação (status/update, UPDATE agendamentos) foi feita — handler do
    # client teria estourado AssertionError se tentasse; chegou até aqui sem erro = só leitura.


def test_cpf_vem_do_paciente_da_lista_quando_ausente_na_base():
    base = {"_sub_confirmar": "verificar", "pacientes": [{"cpf": "11144477735"}]}
    r = processar_rota5(base, client=_client_login_busca_e_timeline())
    assert r["auto_confirmar"] is False


def test_sem_cpf_retorna_none():
    base = {"_sub_confirmar": "verificar"}
    assert processar_rota5(base, client=_client_login_busca_e_timeline()) is None


def test_sub_confirmar_recusou_retorna_none_deixa_pro_legado():
    assert processar_rota5({"_sub_confirmar": "recusou"}, client=None) is None


def test_sub_confirmar_ausente_retorna_none():
    # cobre os rota=5 que na verdade sao bypass humano (encaixe, lista de espera) — sem
    # _sub_confirmar setado, nao devem tentar TiSaude
    assert processar_rota5({}, client=None) is None


def test_falha_de_rede_na_tisaude_nao_derruba_devolve_none():
    def handler(request):
        raise httpx.ConnectError("timeout", request=request)

    base = {"_sub_confirmar": "verificar", "cpf": "11144477735"}
    client = httpx.Client(transport=httpx.MockTransport(handler))
    assert processar_rota5(base, client=client) is None


# ---------- confirmar_presenca_completo (mutação, NÃO ligado a nenhum dispatcher) ----------

def _mock_conn(row=(999,)):
    conn = MagicMock()
    cur = MagicMock()
    cur.fetchone.return_value = row
    conn.cursor.return_value.__enter__.return_value = cur
    return conn, cur


def _handler_confirmar(status_resp=None):
    status_resp = status_resp if status_resp is not None else {"success": True}

    def handler(request):
        path = request.url.path
        if path == "/api/login":
            return httpx.Response(200, json={"access_token": "tok"})
        if path == "/api/schedule/status/update/999/3":
            return httpx.Response(200, json=status_resp)
        raise AssertionError(f"chamada inesperada: {path}")

    return handler


def test_confirmar_presenca_completo_sucesso_chama_tisaude_e_atualiza_postgres():
    client = httpx.Client(transport=httpx.MockTransport(_handler_confirmar()))
    conn, cur = _mock_conn(row=(999,))
    r = confirmar_presenca_completo("999", conn=conn, tisaude_client=client)
    assert r == {"status": "CONFIRMADO", "id_agendamento": "999", "resultado": "Presença confirmada com sucesso!"}
    update_sql, update_params = cur.execute.call_args_list[1].args
    assert "UPDATE agendamentos" in update_sql
    assert "status_atendimento = 'CONFIRMADO'" in update_sql
    assert update_params == (999,)


def test_confirmar_presenca_completo_sem_id_nao_chama_tisaude():
    def handler(request):
        raise AssertionError(f"não deveria chamar TiSaude sem id_agendamento: {request.url.path}")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    conn, cur = _mock_conn()
    r = confirmar_presenca_completo(None, conn=conn, tisaude_client=client)
    assert r["status"] == "ERRO_INPUT"
    cur.execute.assert_not_called()


def test_confirmar_presenca_completo_linha_local_ausente_atualiza_com_none():
    # 'Buscar agendamento' não achou a linha localmente (Postgres dessincronizado da TiSaude) —
    # UPDATE roda com id_itsaude=None (no-op, 0 linhas), mas a função ainda retorna sucesso: a
    # TiSaude já confirmou de verdade, é isso que importa pro paciente (fiel ao node real).
    client = httpx.Client(transport=httpx.MockTransport(_handler_confirmar()))
    conn, cur = _mock_conn(row=None)
    r = confirmar_presenca_completo("999", conn=conn, tisaude_client=client)
    assert r["status"] == "CONFIRMADO"
    update_params = cur.execute.call_args_list[1].args[1]
    assert update_params == (None,)


def test_confirmar_presenca_completo_falha_tisaude_propaga_excecao():
    # node HTTP real não tem onError/continueOnFail -> falha para a execução inteira, sem
    # mensagem de erro graciosa. Preservado: sem try/except em volta de tisaude.confirmar_presenca.
    def handler(request):
        if request.url.path == "/api/login":
            return httpx.Response(200, json={"access_token": "tok"})
        return httpx.Response(500, json={"error": "falha"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    conn, cur = _mock_conn()
    try:
        confirmar_presenca_completo("999", conn=conn, tisaude_client=client)
        assert False, "deveria ter propagado exceção"
    except httpx.HTTPStatusError:
        pass
    cur.execute.assert_not_called()
