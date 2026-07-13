"""
Testes de app/buscar_agenda_fluxo.py — port do sub-workflow 'Ferramenta - Buscar Agenda TiSaude
(V4 Final)' (gMQaU2CQbwdPUnUA). Pura (filtros/normalização) testada direto; orquestração (loop
de 21 dias + Postgres) via httpx.MockTransport (sem rede) + conn mockado (sem Postgres real).
"""

import re
from unittest.mock import MagicMock

import httpx

from app.buscar_agenda_fluxo import (
    _filtrar_horarios_por_periodo,
    _filtrar_medicos_por_preferencia,
    _limpar_nome_medico,
    _normalizar_telefone_busca,
    _resolver_dia_semana_num,
    _resposta_sem_vaga,
    buscar_agenda_completo,
)

# ---------- _limpar_nome_medico ----------

def test_limpar_nome_medico_remove_titulo_e_acento():
    assert _limpar_nome_medico("Dra. Giséli Rebechi") == "giseli rebechi"


def test_limpar_nome_medico_dr_a_titulo():
    assert _limpar_nome_medico("Dr(a). Elias Braga") == "elias braga"


def test_limpar_nome_medico_colapsa_letra_dobrada():
    # FIX_LETRA_DOBRADA (exec 70777): "Ruggeri" (LLM) vs "Rugeri" (TiSaude real).
    assert _limpar_nome_medico("Ruggeri") == "rugeri"
    assert _limpar_nome_medico("Broetto") == "broeto"


# ---------- _filtrar_medicos_por_preferencia ----------

MEDICOS = [{"idCalendar": 1, "medico": "Giseli Rebechi"}, {"idCalendar": 2, "medico": "Elias Lobo Braga"}]


def test_filtrar_medicos_sem_preferencia_retorna_todos():
    assert _filtrar_medicos_por_preferencia(MEDICOS, "sem preferência") == MEDICOS


def test_filtrar_medicos_vazio_retorna_todos():
    assert _filtrar_medicos_por_preferencia(MEDICOS, "") == MEDICOS


def test_filtrar_medicos_com_preferencia_filtra():
    r = _filtrar_medicos_por_preferencia(MEDICOS, "Dra. Giseli")
    assert r == [MEDICOS[0]]


def test_filtrar_medicos_sem_match_retorna_vazio():
    assert _filtrar_medicos_por_preferencia(MEDICOS, "Stephanie") == []


def test_filtrar_medicos_tolera_letra_dobrada_do_llm():
    # exec 70777: LLM pediu "Stephanie Ruggeri" (2 g), médica real na TiSaude é "Stephanie
    # Rugeri de Souza" (1 g) — sem o fix, filtrava pra zero e a busca real morria.
    medicos = MEDICOS + [{"idCalendar": 6, "medico": "Stephanie Rugeri de Souza"}]
    r = _filtrar_medicos_por_preferencia(medicos, "Stephanie Ruggeri")
    assert r == [medicos[2]]


# ---------- _normalizar_telefone_busca ----------

def test_normalizar_telefone_adiciona_55():
    assert _normalizar_telefone_busca("11963048295") == "5511963048295"


def test_normalizar_telefone_nao_duplica_55():
    assert _normalizar_telefone_busca("5511963048295") == "5511963048295"


def test_normalizar_telefone_limpa_formatacao():
    assert _normalizar_telefone_busca("(11) 96304-8295") == "5511963048295"


def test_normalizar_telefone_vazio():
    assert _normalizar_telefone_busca("") == ""
    assert _normalizar_telefone_busca(None) == ""


# ---------- _resolver_dia_semana_num ----------

def test_resolver_dia_semana_explicito():
    assert _resolver_dia_semana_num("segunda") == 1
    assert _resolver_dia_semana_num("Sábado") == 6


def test_resolver_dia_semana_ausente_retorna_none():
    assert _resolver_dia_semana_num(None) is None
    assert _resolver_dia_semana_num("") is None


def test_resolver_dia_semana_desconhecido_retorna_none():
    assert _resolver_dia_semana_num("feriado") is None


# ---------- _filtrar_horarios_por_periodo ----------

def test_filtrar_horarios_manha():
    assert _filtrar_horarios_por_periodo(["08:00", "11:59", "12:00", "15:00"], "manha") == ["08:00", "11:59"]


def test_filtrar_horarios_tarde():
    assert _filtrar_horarios_por_periodo(["08:00", "12:00", "17:59", "18:00"], "tarde") == ["12:00", "17:59"]


def test_filtrar_horarios_noite():
    assert _filtrar_horarios_por_periodo(["08:00", "17:59", "18:00", "20:00"], "noite") == ["18:00", "20:00"]


def test_filtrar_horarios_indiferente_mantem_todos():
    assert _filtrar_horarios_por_periodo(["08:00", "14:00", "20:00"], "indiferente") == ["08:00", "14:00", "20:00"]


# ---------- _resposta_sem_vaga ----------

def test_resposta_sem_vaga_sem_filtro_dia_semana():
    r = _resposta_sem_vaga(None, "2026-07-14")
    assert r["status"] == "SEM_VAGA"
    assert r["proxima_busca_opcao2"] is None


def test_resposta_sem_vaga_com_filtro_dia_semana():
    r = _resposta_sem_vaga(1, "2026-07-14", hoje=__import__("datetime").date(2026, 7, 13))
    assert r["status"] == "FILTRO_SEM_RESULTADO"
    assert r["dia_semana_pedido"] == "segunda"
    assert r["proxima_busca_opcao2"] == {"data": "2026-07-13"}
    assert r["proxima_busca_opcao3"] == {"data": "2026-08-04", "dia_semana": "segunda"}


# ---------- buscar_agenda_completo (integração, sem rede/Postgres real) ----------

def _mock_conn():
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cur
    return conn, cur


def _handler_com_vagas(vagas: dict, medicos=None):
    """`vagas` = {'2026-07-14': ['09:00','14:00'], ...} — dias com disponibilidade; horários
    fora do dict = dia indisponível. `medicos` = lista bruta (formato /schedule/doctors)."""
    medicos = medicos or [{"id": 11, "name": "Giseli Rebechi"}]

    def handler(request):
        path = request.url.path
        if path == "/api/login":
            return httpx.Response(200, json={"access_token": "tok"})
        if path == "/api/schedule/doctors":
            return httpx.Response(200, json={"data": medicos})
        if path == "/api/schedule/filter/calendar/hours":
            data = request.url.params["date"]
            horas = vagas.get(data, [])
            return httpx.Response(200, json={"schedules": [{"hour": h} for h in horas]})
        m = re.match(r"^/api/schedule/(\d{4}-\d{2}-\d{2})$", path)
        if m:
            return httpx.Response(200, json={"dayAvailable": m.group(1) in vagas})
        raise AssertionError(f"chamada inesperada: {path}")

    return handler


def test_buscar_agenda_completo_acha_vaga_e_monta_dias():
    vagas = {"2026-07-14": ["09:00", "14:00"], "2026-07-20": ["10:00"]}
    client = httpx.Client(transport=httpx.MockTransport(_handler_com_vagas(vagas)))
    conn, cur = _mock_conn()

    r = buscar_agenda_completo(
        unidade="Vila Olímpia", data="2026-07-14", medico=None, periodo=None,
        telefone_paciente="11999999999", conn=conn, tisaude_client=client,
    )

    assert r["status"] == "OK"
    assert r["total_dias_com_vaga"] == 2
    assert r["dia"]["data"] == "2026-07-14"
    assert r["dia"]["medicos"] == [{"medico": "Giseli Rebechi", "idLocal": 1, "idCalendar": 11, "horarios": "09:00, 14:00"}]
    assert r["dias_restantes"] == 1

    # cache gravado
    assert cur.execute.called
    sql, params = cur.execute.call_args.args
    assert "INSERT INTO agenda_cache" in sql
    assert params["telefone"] == "5511999999999"
    assert params["unidade"] == "Vila Olímpia"
    assert params["agenda_json"].obj["total_dias_com_vaga"] == 2
    assert params["ultimo_dia_exibido"].obj == {"data": "2026-07-14", "medicos": r["dia"]["medicos"]}


def test_buscar_agenda_completo_filtra_por_periodo():
    vagas = {"2026-07-14": ["09:00", "15:00"]}
    client = httpx.Client(transport=httpx.MockTransport(_handler_com_vagas(vagas)))
    conn, _ = _mock_conn()

    r = buscar_agenda_completo(
        unidade="Vila Olímpia", data="2026-07-14", medico=None, periodo="manha",
        telefone_paciente="11999999999", conn=conn, tisaude_client=client,
    )

    assert r["dia"]["medicos"][0]["horarios"] == "09:00"


def test_buscar_agenda_completo_filtra_por_dia_semana():
    # 2026-07-14 é terça; só pede segunda — terça deve ser pulada mesmo tendo vaga
    vagas = {"2026-07-14": ["09:00"], "2026-07-20": ["10:00"]}  # 07-20 é segunda
    client = httpx.Client(transport=httpx.MockTransport(_handler_com_vagas(vagas)))
    conn, _ = _mock_conn()

    r = buscar_agenda_completo(
        unidade="Vila Olímpia", data="2026-07-14", medico=None, periodo=None,
        dia_semana="segunda", telefone_paciente="11999999999", conn=conn, tisaude_client=client,
    )

    assert r["status"] == "OK"
    assert r["total_dias_com_vaga"] == 1
    assert r["dia"]["data"] == "2026-07-20"


def test_buscar_agenda_completo_sem_vaga_retorna_sem_vaga():
    client = httpx.Client(transport=httpx.MockTransport(_handler_com_vagas({})))
    conn, cur = _mock_conn()

    r = buscar_agenda_completo(
        unidade="Vila Olímpia", data="2026-07-14", medico=None, periodo=None,
        telefone_paciente="11999999999", conn=conn, tisaude_client=client,
    )

    assert r["status"] == "SEM_VAGA"
    # cache ainda é gravado (dias=[]), com ultimo_dia_exibido None
    params = cur.execute.call_args.args[1]
    assert params["ultimo_dia_exibido"] is None


def test_buscar_agenda_completo_filtro_dia_semana_sem_match_retorna_filtro_sem_resultado():
    vagas = {"2026-07-14": ["09:00"]}  # terça, mas paciente pediu domingo
    client = httpx.Client(transport=httpx.MockTransport(_handler_com_vagas(vagas)))
    conn, _ = _mock_conn()

    r = buscar_agenda_completo(
        unidade="Vila Olímpia", data="2026-07-14", medico=None, periodo=None,
        dia_semana="domingo", telefone_paciente="11999999999", conn=conn, tisaude_client=client,
    )

    assert r["status"] == "FILTRO_SEM_RESULTADO"
    assert r["dia_semana_pedido"] == "domingo"


def test_buscar_agenda_completo_filtra_medico_preferido():
    medicos = [{"id": 11, "name": "Giseli Rebechi"}, {"id": 22, "name": "Elias Lobo Braga"}]
    vagas = {"2026-07-14": ["09:00"]}
    client = httpx.Client(transport=httpx.MockTransport(_handler_com_vagas(vagas, medicos=medicos)))
    conn, _ = _mock_conn()

    r = buscar_agenda_completo(
        unidade="Vila Olímpia", data="2026-07-14", medico="Elias", periodo=None,
        telefone_paciente="11999999999", conn=conn, tisaude_client=client,
    )

    assert r["dia"]["medicos"] == [{"medico": "Elias Lobo Braga", "idLocal": 1, "idCalendar": 22, "horarios": "09:00"}]
