"""
Testes do port de Verificar Cadastro3 (app/verificar_cadastro.py::processar) —
DEPLOY/_proposed_Verificar_Cadastro3.js, 69 linhas. Retorna UM ITEM POR PACIENTE.
"""

from app.verificar_cadastro import processar


# ---------- extração de pacientes ----------

def test_fonte_preferencial_id1():
    r = processar([{"id": "1", "name": "Lucas Bueno", "cpf": "11111111111"}], None, "oi")
    assert len(r) == 1
    assert r[0]["nome"] == "Lucas Bueno"
    assert r[0]["id_tisaude"] == "1"


def test_fallback_data_array():
    r = processar([{"data": [{"id": "2", "name": "Ana Souza"}]}], None, "oi")
    assert len(r) == 1
    assert r[0]["nome"] == "Ana Souza"


def test_fallback_item_unico():
    r = processar([{"id": "3", "name": "Bruno"}], None, "oi")
    assert len(r) == 1
    assert r[0]["nome"] == "Bruno"


def test_sem_paciente_lista_vazia():
    r = processar([{}], None, "oi")
    assert r == []


def test_input_vazio():
    r = processar(None, None, "oi")
    assert r == []


def test_item_vazio_na_frente_bloqueia_como_no_js():
    # JS filter(Boolean) mantém {} (truthy) — o primeiro item vazio "vence" e pacientes fica []
    # mesmo com um item válido depois, porque só _inFC[0] é olhado nesse branch.
    r = processar([{}, {"id": "5", "name": "X"}], None, "oi")
    assert r == []


# ---------- múltiplos pacientes: index/total/ordem estável ----------

def test_multi_pacientes_index_e_total():
    r = processar([{"id": 2, "name": "B"}, {"id": 1, "name": "A"}], None, "oi")
    assert len(r) == 2
    # FIX_ORDEM_PACIENTES: ordenado por id
    assert [p["nome"] for p in r] == ["A", "B"]
    assert [p["index_paciente"] for p in r] == [0, 1]
    assert all(p["total_pacientes"] == 2 for p in r)


# ---------- email (FIX_FICHA_COMPLETA) ----------

def test_email_valido():
    r = processar([{"id": "1", "name": "Lucas", "email": "x@x.com"}], None, "oi")
    assert r[0]["email"] == "x@x.com"


def test_email_blacklist_vira_none():
    r = processar([{"id": "1", "name": "Lucas", "email": "x@x.com", "blacklistEmail": True}], None, "oi")
    assert r[0]["email"] is None


# ---------- cache ----------

def test_cache_ativo_via_agenda_json():
    r = processar([{"id": "1", "name": "Lucas"}], {"agenda_json": '{"unidade": "Tatuapé"}'}, "oi")
    assert r[0]["cache_ativo"] is True
    assert r[0]["unidade_cache"] == "Tatuapé"


def test_sem_cache_row():
    r = processar([{"id": "1", "name": "Lucas"}], None, "oi")
    assert r[0]["cache_ativo"] is False


def test_ultimo_dia_texto_mantem_data_iso_sem_reformatar():
    cache_row = {"ultimo_dia_exibido": {"data": "2026-07-15", "medicos": [{"medico": "Giseli", "horarios": "09:00"}]}}
    r = processar([{"id": "1", "name": "Lucas"}], cache_row, "oi")
    # diferente de app.montar_contexto: mantém yyyy-mm-dd, não reformata pra dd/mm/yyyy
    assert r[0]["ultimo_dia_texto"] == "Data: 2026-07-15 | Dr(a). Giseli: 09:00"


def test_ultimo_dia_texto_default_nenhum():
    r = processar([{"id": "1", "name": "Lucas"}], None, "oi")
    assert r[0]["ultimo_dia_texto"] == "NENHUM"


# ---------- texto_ia ----------

def test_texto_ia_usa_mensagem_agrupada():
    r = processar([{"id": "1", "name": "Lucas"}], None, "quero confirmar")
    assert r[0]["texto_ia"] == "quero confirmar"


def test_texto_ia_default_oi_quando_vazio():
    r = processar([{"id": "1", "name": "Lucas"}], None, "")
    assert r[0]["texto_ia"] == "Oi"
