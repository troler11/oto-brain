"""
Testes das queries SQL portadas em app/db.py (DEPLOY/*.sql, snapshot 12/07/2026) — sem
Postgres real, cursor mockado (mesmo padrão de tests/test_log_turno.py). Verifica que o SQL
certo roda com os params certos, não o resultado de uma query real.
"""

from unittest.mock import MagicMock

from app.db import (
    carregar_sessao,
    computar_params_salvar_sessao,
    resetar_sessao,
    resetar_sessao_humano,
    salvar_coleta_steps,
    salvar_intencao_agente,
)

WA_INFO = {"SenderAlt": "", "Chat": "11999999999@s.whatsapp.net"}


def _mock_conn():
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cur
    return conn, cur


# ---------- carregar_sessao ----------

def test_carregar_sessao_garante_linha_e_retorna_select():
    conn, cur = _mock_conn()
    cur.fetchone.return_value = {"sessao_id": "abc", "coleta_unidade": "Vila Olímpia"}
    r = carregar_sessao(conn, "5511999999999")
    assert r == {"sessao_id": "abc", "coleta_unidade": "Vila Olímpia"}
    assert cur.execute.call_count == 2
    insert_sql, insert_params = cur.execute.call_args_list[0].args
    assert "ON CONFLICT (telefone)" in insert_sql
    assert insert_params == {"telefone": "5511999999999"}
    select_sql, select_params = cur.execute.call_args_list[1].args
    assert "FROM contatos_whatsapp cw" in select_sql
    assert "LEFT JOIN terceiros_agendamento ta" in select_sql
    assert select_params == {"telefone": "5511999999999"}


def test_carregar_sessao_sem_linha_retorna_none():
    conn, cur = _mock_conn()
    cur.fetchone.return_value = None
    assert carregar_sessao(conn, "5511999999999") is None


# ---------- salvar_coleta_steps ----------

def test_salvar_coleta_steps_passa_todos_os_params():
    conn, cur = _mock_conn()
    salvar_coleta_steps(conn, "5511999999999", unidade="Vila Olímpia", medico="Dra. Giseli Rebechi", modo=3)
    sql, params = cur.execute.call_args.args
    assert params["telefone"] == "5511999999999"
    assert params["unidade"] == "Vila Olímpia"
    assert params["medico"] == "Dra. Giseli Rebechi"
    assert params["modo"] == 3
    assert params["conv_fail"] == -1  # default preserva o valor salvo


def test_salvar_coleta_steps_clear_nuclear_via_medico():
    conn, cur = _mock_conn()
    salvar_coleta_steps(conn, "5511999999999", medico="__CLEAR__")
    sql, params = cur.execute.call_args.args
    assert params["medico"] == "__CLEAR__"
    assert "coleta_medico" in sql and "'__CLEAR__'" in sql


def test_salvar_coleta_steps_email_skip():
    conn, cur = _mock_conn()
    salvar_coleta_steps(conn, "5511999999999", email="SKIP")
    sql, params = cur.execute.call_args.args
    assert params["email"] == "SKIP"


# ---------- salvar_intencao_agente ----------

def test_salvar_intencao_agente_whitelist_no_sql():
    conn, cur = _mock_conn()
    salvar_intencao_agente(conn, "coleta", 2, "5511999999999")
    sql, params = cur.execute.call_args.args
    assert "'coleta'" in sql
    assert "'remarcando_escolher'" in sql
    assert params == {"intencao": "coleta", "rota_agente": 2, "telefone": "5511999999999"}


# ---------- resetar_sessao / resetar_sessao_humano ----------

def test_resetar_sessao_roda_4_statements():
    conn, cur = _mock_conn()
    resetar_sessao(conn, "5511999999999")
    assert cur.execute.call_count == 4
    for call in cur.execute.call_args_list:
        assert call.args[1] == {"telefone": "5511999999999"}
    primeira_sql = cur.execute.call_args_list[0].args[0]
    assert "sessao_intencao = 'concluido'" in primeira_sql


def test_resetar_sessao_humano_marca_status_robo():
    conn, cur = _mock_conn()
    resetar_sessao_humano(conn, "5511999999999")
    assert cur.execute.call_count == 4
    primeira_sql = cur.execute.call_args_list[0].args[0]
    assert "status_robo = 'Humano'" in primeira_sql
    assert "sessao_intencao = 'triagem'" in primeira_sql


# ---------- computar_params_salvar_sessao ----------

def test_intencao_do_eif1_vence_quando_na_whitelist():
    r = computar_params_salvar_sessao({"intencao_rapida": "triagem"}, True, "confirmacao", WA_INFO)
    assert r["intencao"] == "confirmacao"


def test_intencao_do_eif1_fora_da_whitelist_cai_pro_er():
    r = computar_params_salvar_sessao({"intencao_rapida": "coleta"}, True, "coleta", WA_INFO)
    assert r["intencao"] == "coleta"  # vem do fallback ER, não do EIF1 direto (mesmo valor, fonte diferente)


def test_eif1_nao_executado_usa_er():
    r = computar_params_salvar_sessao({"intencao_rapida": "agenda"}, False, None, WA_INFO)
    assert r["intencao"] == "agenda"


def test_sem_intencao_nenhuma_fallback_triagem():
    r = computar_params_salvar_sessao({}, False, None, WA_INFO)
    assert r["intencao"] == "triagem"


def test_telefone_reconstroi_prefixo_55():
    r = computar_params_salvar_sessao({}, False, None, {"SenderAlt": "", "Chat": "11999999999@s.whatsapp.net"})
    assert r["telefone"] == "5511999999999"


def test_telefone_ja_com_55_nao_duplica():
    r = computar_params_salvar_sessao({}, False, None, {"SenderAlt": "", "Chat": "5511999999999@s.whatsapp.net"})
    assert r["telefone"] == "5511999999999"


def test_deve_resetar_sessao_vira_bool():
    r = computar_params_salvar_sessao({"deve_resetar_sessao": True}, False, None, WA_INFO)
    assert r["deve_resetar_sessao"] is True
