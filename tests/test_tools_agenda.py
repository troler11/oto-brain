"""
Testes de app/tools_agenda.py — executores que ligam navegar_agenda/buscar_agenda_fluxo
(já testados isolados) no formato `Callable[[dict], dict]` que app.agentes.chamar_agente espera.
Sem Postgres/rede real: conn e tisaude_client mockados.
"""

from unittest.mock import MagicMock, patch

from app.tools_agenda import TOOLS_AGENDA, construir_executores


def _mock_conn():
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cur
    return conn, cur


def test_tools_agenda_schema_tem_os_dois_nomes():
    nomes = {t["function"]["name"] for t in TOOLS_AGENDA}
    assert nomes == {"buscar_agenda", "navegar_agenda"}


# ---------- executor navegar_agenda ----------

def test_executor_navegar_agenda_le_cache_processa_e_atualiza():
    conn, _ = _mock_conn()
    executores = construir_executores(conn)

    with patch("app.tools_agenda.db.ler_agenda_cache") as ler, \
         patch("app.tools_agenda.navegar_agenda.processar") as processar, \
         patch("app.tools_agenda.db.atualizar_indice_agenda_cache") as atualizar:
        ler.return_value = {"agenda_json": {"dias": []}, "indice_atual": 0}
        processar.return_value = {"status": "OK", "indice_atual": 1, "dia": {"data": "2026-07-20"}}

        r = executores["navegar_agenda"]({"acao": "avancar", "telefone_paciente": "11999999999", "unidade": "Vila Olímpia"})

        ler.assert_called_once_with(conn, "11999999999", "Vila Olímpia")
        processar.assert_called_once_with({"agenda_json": {"dias": []}, "indice_atual": 0}, "avancar", None)
        atualizar.assert_called_once_with(conn, "11999999999", "Vila Olímpia", 1, {"data": "2026-07-20"})
        assert r["status"] == "OK"


def test_executor_navegar_agenda_sem_cache_nao_chama_atualizar():
    conn, _ = _mock_conn()
    executores = construir_executores(conn)

    with patch("app.tools_agenda.db.ler_agenda_cache", return_value=None), \
         patch("app.tools_agenda.db.atualizar_indice_agenda_cache") as atualizar:
        r = executores["navegar_agenda"]({"acao": "ver", "telefone_paciente": "11999999999", "unidade": "Vila Olímpia"})

        assert r["status"] == "SEM_CACHE"
        atualizar.assert_not_called()


def test_executor_navegar_agenda_ir_para_passa_data():
    conn, _ = _mock_conn()
    executores = construir_executores(conn)

    with patch("app.tools_agenda.db.ler_agenda_cache", return_value={"agenda_json": {"dias": []}, "indice_atual": 0}), \
         patch("app.tools_agenda.navegar_agenda.processar", return_value={"status": "OK", "indice_atual": 0, "dia": None}) as processar, \
         patch("app.tools_agenda.db.atualizar_indice_agenda_cache"):
        executores["navegar_agenda"]({"acao": "ir_para", "telefone_paciente": "11999999999", "unidade": "Vila Olímpia", "data": "2026-07-27"})
        processar.assert_called_once_with({"agenda_json": {"dias": []}, "indice_atual": 0}, "ir_para", "2026-07-27")


# ---------- executor buscar_agenda ----------

def test_executor_buscar_agenda_repassa_args_pro_fluxo():
    conn, _ = _mock_conn()
    client = object()
    executores = construir_executores(conn, tisaude_client=client)

    with patch("app.tools_agenda.buscar_agenda_fluxo.buscar_agenda_completo") as busca:
        busca.return_value = {"status": "OK"}
        r = executores["buscar_agenda"]({
            "unidade": "Tatuapé", "data": "2026-07-14", "medico": "Giseli", "periodo": "manha",
            "telefone_paciente": "11999999999", "dia_semana": "segunda", "horario_preferencia": "9",
        })

        busca.assert_called_once_with(
            unidade="Tatuapé", data="2026-07-14", medico="Giseli", periodo="manha",
            telefone_paciente="11999999999", dia_semana="segunda", horario_preferencia="9",
            conn=conn, tisaude_client=client,
        )
        assert r == {"status": "OK"}
