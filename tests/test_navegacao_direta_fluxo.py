"""
Testes de app/navegacao_direta_fluxo.py — cadeia "Navegação Direta"/"Troca Direta" (15 nós reais,
ver docstring do módulo). Sem rede real (httpx.MockTransport) nem Postgres real (MagicMock).
"""

import re
from datetime import date
from unittest.mock import MagicMock

import httpx

from app.navegacao_direta_fluxo import (
    _detectar_navegacao_final,
    _formatar_resposta_navegacao,
    _formatar_resposta_troca,
    _horario_pref_da_sessao,
    _parsear_acao_navegar,
    navegacao_direta,
    processar,
    troca_direta,
)

HOJE = date(2026, 7, 13)  # segunda-feira


# ---------- _detectar_navegacao_final ----------

def test_detectar_navegacao_true_sem_coleta_data_passa_direto():
    assert _detectar_navegacao_final({"eh_navegacao": True}) is True


def test_detectar_navegacao_false_sempre_false():
    assert _detectar_navegacao_final({"eh_navegacao": False, "coleta_data": "2026-07-13"}) is False


def test_detectar_navegacao_navig_outro_dia_forca_false():
    # coleta_data=2026-07-13 é segunda; paciente pediu "quinta" (dia diferente) -> não é
    # navegação simples, precisa buscar de novo.
    r = _detectar_navegacao_final({"eh_navegacao": True, "coleta_data": "2026-07-13", "texto_ia": "tem vaga na quinta?"})
    assert r is False


def test_detectar_navegacao_dia_igual_mantem_true():
    # coleta_data=2026-07-13 é segunda; paciente citou "segunda" (mesmo dia) -> mantém True.
    r = _detectar_navegacao_final({"eh_navegacao": True, "coleta_data": "2026-07-13", "texto_ia": "na segunda mesmo"})
    assert r is True


def test_detectar_navegacao_troca_data_tem_prioridade():
    r = _detectar_navegacao_final({"eh_navegacao": True, "eh_troca_data": True})
    assert r is False


# ---------- _parsear_acao_navegar ----------

def test_parsear_dia_numero_sem_mes_futuro_no_mes():
    r = _parsear_acao_navegar("quero o dia 20", hoje=HOJE)
    assert r == {"acao": "ir_para", "data": "2026-07-20"}


def test_parsear_dia_numero_ja_passou_avanca_mes():
    r = _parsear_acao_navegar("dia 5", hoje=HOJE)  # hoje é dia 13, "dia 5" já passou
    assert r == {"acao": "ir_para", "data": "2026-08-05"}


def test_parsear_dia_com_mes_nao_avanca_mesmo_passado():
    r = _parsear_acao_navegar("dia 5/07", hoje=HOJE)
    assert r == {"acao": "ir_para", "data": "2026-07-05"}


def test_parsear_amanha():
    r = _parsear_acao_navegar("tem vaga amanhã?", hoje=HOJE)
    assert r == {"acao": "ir_para", "data": "2026-07-14"}


def test_parsear_dia_semana():
    r = _parsear_acao_navegar("prefiro na quinta", hoje=HOJE)
    assert r == {"acao": "ir_para", "data": "quinta"}


def test_parsear_voltar():
    r = _parsear_acao_navegar("quero voltar um pouco", hoje=HOJE)
    assert r == {"acao": "voltar", "data": None}


def test_parsear_default_avancar():
    r = _parsear_acao_navegar("mais opções", hoje=HOJE)
    assert r == {"acao": "avancar", "data": None}


# ---------- _formatar_resposta_navegacao ----------

def test_formatar_navegacao_sem_cache_precisa_buscar():
    r = _formatar_resposta_navegacao({"status": "SEM_CACHE"})
    assert r["precisa_buscar"] is True
    assert r["mensagem_final"] is None


def test_formatar_navegacao_esgotado_precisa_buscar():
    r = _formatar_resposta_navegacao({"status": "ESGOTADO"})
    assert r["precisa_buscar"] is True


def test_formatar_navegacao_ok_monta_mensagem_e_dia_exibido():
    r = _formatar_resposta_navegacao({
        "status": "OK", "dias_restantes": 3, "total_dias": 20,
        "dia": {"data": "2026-07-20", "medicos": [
            {"medico": "Giseli Rebechi", "idLocal": 1, "idCalendar": 11, "horarios": "09:00, 10:00, 14:00"},
        ]},
    })
    assert r["precisa_buscar"] is False
    assert "📅 20/07/2026" in r["mensagem_final"]
    assert "Dr(a). Giseli Rebechi: 09:00, 10:00, 14:00" in r["mensagem_final"]
    assert r["dia_exibido"]["medicos"][0]["idCalendar"] == 11


def test_formatar_navegacao_com_preferencia_horario_filtra_top3():
    r = _formatar_resposta_navegacao({
        "status": "OK",
        "dia": {"data": "2026-07-20", "medicos": [
            {"medico": "Giseli", "horarios": "08:00, 09:00, 10:00, 15:00, 16:00"},
        ]},
    }, horario_pref=15)
    horarios = r["dia_exibido"]["medicos"][0]["horarios"]
    assert horarios == "10:00, 15:00, 16:00"  # 3 mais próximos de 15h, ordenados


# ---------- _formatar_resposta_troca ----------

def test_formatar_troca_sem_dia_mensagem_generica_sem_acento():
    r = _formatar_resposta_troca({"status": "SEM_CACHE"}, data_alvo_troca=None)
    assert r["mensagem_final"] == "Nao encontrei horarios disponiveis nessa data. Quer tentar outro dia? 😊"
    assert r["dia_exibido"] is None


def test_formatar_troca_data_diferente_da_alvo_prefixa_aviso():
    r = _formatar_resposta_troca(
        {"status": "OK", "dia": {"data": "2026-07-21", "medicos": [{"medico": "Elias", "horarios": "10:00"}]}},
        data_alvo_troca="2026-07-20",
    )
    assert "No dia 20/07 nao encontramos horarios" in r["mensagem_final"]
    assert "Encontrei horarios para 21/07/2026" in r["mensagem_final"]


def test_formatar_troca_data_igual_sem_prefixo():
    r = _formatar_resposta_troca(
        {"status": "OK", "dia": {"data": "2026-07-20", "medicos": [{"medico": "Elias", "horarios": "10:00"}]}},
        data_alvo_troca="2026-07-20",
    )
    assert not r["mensagem_final"].startswith("No dia")


# ---------- _horario_pref_da_sessao ----------

def test_horario_pref_sessao_ausente():
    assert _horario_pref_da_sessao(None) == 0


def test_horario_pref_de_agenda_json_string():
    assert _horario_pref_da_sessao({"agenda_json": '{"horario_pref": 14}'}) == 14


def test_horario_pref_de_agenda_json_dict():
    assert _horario_pref_da_sessao({"agenda_json": {"horario_pref_num": 9}}) == 9


# ---------- navegacao_direta (integração, Postgres mockado) ----------

def _mock_conn(cache_row=None):
    conn = MagicMock()
    cur = MagicMock()
    cur.fetchone.return_value = cache_row
    conn.cursor.return_value.__enter__.return_value = cur
    return conn, cur


def test_navegacao_direta_sem_cache_retorna_none():
    conn, cur = _mock_conn(cache_row=None)
    r = navegacao_direta({"unidade_cache": "Vila Olímpia", "texto_ia": "mais horarios"}, telefone="11999999999", conn=conn)
    assert r is None


def test_navegacao_direta_com_cache_retorna_mensagem_e_salva_dia_exibido():
    agenda_json = {"dias": [
        {"data": "2026-07-13", "medicos": [{"medico": "Giseli", "idLocal": 1, "idCalendar": 11, "horarios": "09:00"}]},
        {"data": "2026-07-14", "medicos": [{"medico": "Giseli", "idLocal": 1, "idCalendar": 11, "horarios": "10:00"}]},
    ]}
    conn, cur = _mock_conn(cache_row={"agenda_json": agenda_json, "indice_atual": 0})
    r = navegacao_direta({"unidade_cache": "Vila Olímpia", "texto_ia": "proximo dia"}, telefone="11999999999", conn=conn)
    assert r is not None
    assert "14/07/2026" in r["mensagem_final"]
    # 3 chamadas: ler_agenda_cache (SELECT) + atualizar_indice_agenda_cache (UPDATE) + _salvar_dia_exibido (UPDATE)
    assert cur.execute.call_count == 3


# ---------- troca_direta (integração, TiSaude + Postgres mockados) ----------

def _handler_busca_vazia():
    def handler(request):
        path = request.url.path
        if path == "/api/login":
            return httpx.Response(200, json={"access_token": "tok"})
        if path == "/api/schedule/doctors":
            return httpx.Response(200, json={"data": [{"id": 11, "name": "Giseli Rebechi"}]})
        if re.match(r"^/api/schedule/\d{4}-\d{2}-\d{2}$", path):
            return httpx.Response(200, json={"dayAvailable": False})
        raise AssertionError(f"chamada inesperada: {path}")

    return handler


def test_troca_direta_sem_horarios_mensagem_generica():
    client = httpx.Client(transport=httpx.MockTransport(_handler_busca_vazia()))
    conn, cur = _mock_conn(cache_row=None)
    r = troca_direta(
        {"coleta_unidade": "Vila Olímpia", "data_alvo_troca": "2026-07-20", "medico_troca": "Giseli", "coleta_periodo": "manha"},
        telefone="11999999999", conn=conn, tisaude_client=client, hoje=HOJE,
    )
    assert "Nao encontrei horarios disponiveis" in r["mensagem_final"]


# ---------- processar (ponto de entrada) ----------

def test_processar_nem_navegacao_nem_troca_retorna_none():
    conn, _ = _mock_conn()
    assert processar({}, telefone="11999999999", sessao=None, conn=conn) is None


def test_processar_troca_data_tem_prioridade_quando_ambos_setados():
    # eh_troca_data vence sobre eh_navegacao dentro de app.er (Detectar Navegacao real já garante
    # isso — TROCA_DATA_OVERRIDE_NAV zera eh_navegacao); este módulo só documenta a prioridade,
    # não recalcula — confia no que Extrair Rota já decidiu. Testa o caminho eh_navegacao=False.
    client = httpx.Client(transport=httpx.MockTransport(_handler_busca_vazia()))
    conn, cur = _mock_conn(cache_row=None)
    r = processar(
        {"eh_navegacao": False, "eh_troca_data": True, "coleta_unidade": "Vila Olímpia", "data_alvo_troca": "2026-07-20"},
        telefone="11999999999", sessao=None, conn=conn, tisaude_client=client, hoje=HOJE,
    )
    assert r is not None
    assert "mensagem_final" in r


def test_processar_falha_de_io_retorna_none():
    def handler(request):
        raise httpx.ConnectError("timeout", request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    conn, cur = _mock_conn(cache_row=None)
    r = processar(
        {"eh_troca_data": True, "coleta_unidade": "Vila Olímpia", "data_alvo_troca": "2026-07-20"},
        telefone="11999999999", sessao=None, conn=conn, tisaude_client=client,
    )
    assert r is None
