"""
Testes das queries SQL portadas em app/db.py (DEPLOY/*.sql, snapshot 12/07/2026) — sem
Postgres real, cursor mockado (mesmo padrão de tests/test_log_turno.py). Verifica que o SQL
certo roda com os params certos, não o resultado de uma query real.
"""

from unittest.mock import MagicMock

from app.db import (
    atualizar_indice_agenda_cache,
    carregar_historico_conversa,
    carregar_memoria_paciente,
    carregar_sessao,
    computar_params_salvar_sessao,
    criar_fila,
    ler_agenda_cache,
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


# ---------- carregar_historico_conversa ----------

def test_carregar_historico_converte_origem_pra_role_e_reordena_cronologico():
    conn, cur = _mock_conn()
    # fetchall vem em ordem DESC (mais recente primeiro) — função deve inverter pra cronológico
    cur.fetchall.return_value = [
        {"texto": "Consulta agendada!", "origem": "ia_ou_recepcao", "data": "3"},
        {"texto": "amanhã de manhã", "origem": "paciente", "data": "2"},
        {"texto": "oi", "origem": "paciente", "data": "1"},
    ]
    historico = carregar_historico_conversa(conn, "5511999999999")
    assert historico == [
        {"role": "user", "content": "oi"},
        {"role": "user", "content": "amanhã de manhã"},
        {"role": "assistant", "content": "Consulta agendada!"},
    ]
    sql, params = cur.execute.call_args.args
    assert "FROM chat_limpo" in sql
    assert "excluido_em IS NULL" in sql
    assert params == {"telefone": "5511999999999", "limite": 20}


def test_carregar_historico_respeita_limite_customizado():
    conn, cur = _mock_conn()
    cur.fetchall.return_value = []
    carregar_historico_conversa(conn, "5511999999999", limite=5)
    assert cur.execute.call_args.args[1]["limite"] == 5


def test_carregar_historico_ignora_mensagem_vazia():
    conn, cur = _mock_conn()
    cur.fetchall.return_value = [
        {"texto": "", "origem": "paciente", "data": "1"},
        {"texto": None, "origem": "ia_ou_recepcao", "data": "2"},
        {"texto": "oi", "origem": "paciente", "data": "3"},
    ]
    assert carregar_historico_conversa(conn, "5511999999999") == [{"role": "user", "content": "oi"}]


def test_carregar_historico_humano_via_enviado_por_vira_assistant():
    conn, cur = _mock_conn()
    cur.fetchall.return_value = [
        {"texto": "Vou te conectar", "origem": "ia_ou_recepcao", "data": "1", "enviado_por": "Lucas Bueno"},
    ]
    assert carregar_historico_conversa(conn, "5511999999999") == [
        {"role": "assistant", "content": "Vou te conectar"},
    ]


# ---------- carregar_memoria_paciente ----------

def test_carregar_memoria_paciente_retorna_row():
    conn, cur = _mock_conn()
    cur.fetchone.return_value = {
        "nome_titular": "Maria Silva", "cpf_titular": "12345678900",
        "ultimo_medico": "Dra. Giseli Rebechi", "ultima_unidade": "Vila Olímpia",
        "ultimo_convenio": "Porto Seguro", "ultimo_periodo": "tarde",
        "ultima_data_consulta": "2026-06-01", "total_agendamentos": 3,
    }
    r = carregar_memoria_paciente(conn, "5511999999999")
    assert r["ultimo_medico"] == "Dra. Giseli Rebechi"
    sql, params = cur.execute.call_args.args
    assert "FROM paciente_memoria" in sql
    assert "RIGHT(regexp_replace(telefone" in sql
    assert params == {"telefone": "5511999999999"}


def test_carregar_memoria_paciente_sem_linha_retorna_none():
    conn, cur = _mock_conn()
    cur.fetchone.return_value = None
    assert carregar_memoria_paciente(conn, "5511999999999") is None


# ---------- ler_agenda_cache / atualizar_indice_agenda_cache ----------

def test_ler_agenda_cache_retorna_row():
    conn, cur = _mock_conn()
    cur.fetchone.return_value = {"agenda_json": {"dias": []}, "indice_atual": 2}
    r = ler_agenda_cache(conn, "5511999999999", "Vila Olímpia")
    assert r == {"agenda_json": {"dias": []}, "indice_atual": 2}
    sql, params = cur.execute.call_args.args
    assert "FROM agenda_cache" in sql
    assert "expira_em > NOW()" in sql
    assert params == {"telefone": "5511999999999", "unidade": "Vila Olímpia"}


def test_ler_agenda_cache_sem_linha_retorna_none():
    conn, cur = _mock_conn()
    cur.fetchone.return_value = None
    assert ler_agenda_cache(conn, "5511999999999", "Tatuapé") is None


def test_atualizar_indice_agenda_cache_com_dia_grava_ultimo_dia_exibido():
    conn, cur = _mock_conn()
    dia = {"data": "2026-07-20", "medicos": [{"medico": "Giseli Rebechi", "idLocal": 1, "idCalendar": 11, "horarios": "09:00"}]}
    atualizar_indice_agenda_cache(conn, "5511999999999", "Vila Olímpia", 3, dia)
    sql, params = cur.execute.call_args.args
    assert "UPDATE agenda_cache" in sql
    assert params["indice_atual"] == 3
    assert params["ultimo_dia_exibido"].obj == {
        "data": "2026-07-20",
        "medicos": [{"medico": "Giseli Rebechi", "idLocal": 1, "idCalendar": 11, "horarios": "09:00"}],
    }


def test_atualizar_indice_agenda_cache_sem_dia_preserva_ultimo_dia_exibido():
    conn, cur = _mock_conn()
    atualizar_indice_agenda_cache(conn, "5511999999999", "Vila Olímpia", 0, None)
    _, params = cur.execute.call_args.args
    assert params["ultimo_dia_exibido"] is None


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


# ---------- criar_fila ----------

def test_criar_fila_insere_com_status_pendente():
    conn, cur = _mock_conn()
    params = {
        "telefone": "5511999999999", "intencao": "humano", "especialidade": "Não informada",
        "unidade": "A confirmar", "pagamento": "A confirmar", "para_terceiro": False,
        "nome_paciente": "A confirmar", "cpf_paciente": "A confirmar", "nascimento": "",
        "medico": "A confirmar", "periodo": "A confirmar", "motivo_humano": "Atendimento Humano",
        "observacoes": "",
    }
    criar_fila(conn, params)
    cur.execute.assert_called_once()
    sql, sent = cur.execute.call_args.args
    assert "status_atendimento" in sql
    assert "'PENDENTE'" in sql
    assert sent == params
