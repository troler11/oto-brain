"""
Testes do port de Preparar Input Agenda (app/preparar_input_agenda.py::processar) —
DEPLOY/_proposed_Preparar_Input_Agenda.js, 147 linhas.
"""

from app.preparar_input_agenda import processar

UDE = {
    "data": "2026-07-14",  # terça
    "medicos": [{"medico": "Giseli Rebechi", "horarios": "09:00, 10:00"}],
}


def _ctx(**overrides):
    c = {
        "texto_ia": "quero ver horarios",
        "eh_confirmacao": False,
        "cache_ativo": False,
        "ultimo_dia_exibido": None,
        "coleta_data": "",
        "coleta_medico": "",
        "coleta_convenio": "",
        "ultimo_convenio": "",
        "data_minima_carencia": "",
        "data_minima_carencia_br": "",
        "coleta_modo": 0,
        "coleta_dia_semana": "",
    }
    c.update(overrides)
    return c


# ---------- injeção de [SLOTS_AGENDA] ----------

def test_injeta_slots_quando_cache_ativo_e_valido():
    r = processar(_ctx(cache_ativo=True, ultimo_dia_exibido=UDE, coleta_medico="Dra. Giseli Rebechi"))
    assert "[SLOTS_AGENDA]" in r["texto_ia_agenda"]
    assert "Dr(a). Giseli Rebechi: 09:00, 10:00" in r["texto_ia_agenda"]
    assert "14/07/2026" in r["texto_ia_agenda"]


def test_nao_injeta_quando_eh_confirmacao():
    r = processar(_ctx(eh_confirmacao=True, cache_ativo=True, ultimo_dia_exibido=UDE, texto_ia="[CONFIRMAÇÃO PENDENTE] blah"))
    assert r["texto_ia_agenda"] == "[CONFIRMAÇÃO PENDENTE] blah"


def test_nao_injeta_sem_cache_ativo():
    r = processar(_ctx(cache_ativo=False, ultimo_dia_exibido=UDE))
    assert "[SLOTS_AGENDA]" not in r["texto_ia_agenda"]


def test_nao_injeta_quando_pede_outro_dia():
    r = processar(_ctx(cache_ativo=True, ultimo_dia_exibido=UDE, texto_ia="tem outro dia?"))
    assert "[SLOTS_AGENDA]" not in r["texto_ia_agenda"]


def test_nao_injeta_quando_pede_dia_semana_diferente_do_coleta_data():
    r = processar(_ctx(cache_ativo=True, ultimo_dia_exibido=UDE, coleta_data="2026-07-14", texto_ia="pode ser quarta?"))
    assert "[SLOTS_AGENDA]" not in r["texto_ia_agenda"]


def test_injeta_quando_dia_semana_mencionado_bate_com_coleta_data():
    r = processar(_ctx(cache_ativo=True, ultimo_dia_exibido=UDE, coleta_data="2026-07-14", texto_ia="pode ser terca mesmo"))
    assert "[SLOTS_AGENDA]" in r["texto_ia_agenda"]


def test_cache_invalido_quando_medico_nao_bate_com_slots():
    r = processar(_ctx(cache_ativo=True, ultimo_dia_exibido=UDE, coleta_medico="Dr. Torcuato Sanchez Rojas Neto"))
    assert "[SLOTS_AGENDA]" not in r["texto_ia_agenda"]
    assert r["cache_ativo"] is False


def test_mensagem_vazia_vira_placeholder():
    r = processar(_ctx(texto_ia=""))
    assert r["texto_ia_agenda"] == "[mensagem sem texto]"


# ---------- FIX_CARENCIA_DETERMINISTICA ----------

def test_carencia_empurra_coleta_data_e_avisa():
    r = processar(_ctx(
        coleta_data="2026-07-10", coleta_convenio="Porto Seguro", ultimo_convenio="Porto Seguro",
        data_minima_carencia="2026-07-21", data_minima_carencia_br="21/07/2026",
    ))
    assert r["coleta_data"] == "2026-07-21"
    assert "[CARENCIA:" in r["texto_ia_agenda"]
    assert "21/07/2026" in r["texto_ia_agenda"]


def test_carencia_nao_aplica_se_convenio_diferente():
    r = processar(_ctx(
        coleta_data="2026-07-10", coleta_convenio="Itaú", ultimo_convenio="Porto Seguro",
        data_minima_carencia="2026-07-21",
    ))
    assert r["coleta_data"] == "2026-07-10"
    assert "[CARENCIA:" not in r["texto_ia_agenda"]


def test_carencia_nao_aplica_se_data_ja_posterior():
    r = processar(_ctx(
        coleta_data="2026-07-25", coleta_convenio="Porto Seguro", ultimo_convenio="Porto Seguro",
        data_minima_carencia="2026-07-21",
    ))
    assert r["coleta_data"] == "2026-07-25"


# ---------- pré-computes ----------

def test_proximas_calcula_todos_dias():
    r = processar(_ctx(coleta_data="2026-07-14"))  # terça
    assert r["proximas"]["seg"] == "2026-07-20"
    assert r["proximas"]["ter"] == "2026-07-21"  # nunca hoje, sempre a PRÓXIMA
    assert r["proximas"]["sab"] == "2026-07-18"


def test_dia_slots_do_ultimo_dia_exibido():
    r = processar(_ctx(ultimo_dia_exibido=UDE))
    assert r["dia_slots"] == "terca"


def test_dia_semana_coleta_com_acento():
    r = processar(_ctx(coleta_data="2026-07-14"))
    assert r["dia_semana_coleta"] == "terça"


def test_modo_agenda_medico_especifico():
    r = processar(_ctx(coleta_medico="Dra. Giseli Rebechi"))
    assert r["modo_agenda"] == 3


def test_modo_agenda_sem_preferencia_com_dia():
    r = processar(_ctx(coleta_medico="sem preferencia", coleta_dia_semana="terca"))
    assert r["modo_agenda"] == 2


def test_modo_agenda_sem_preferencia_sem_dia():
    r = processar(_ctx(coleta_medico="sem preferencia"))
    assert r["modo_agenda"] == 1


def test_modo_agenda_preserva_valor_explicito():
    r = processar(_ctx(coleta_modo=2, coleta_medico=""))
    assert r["modo_agenda"] == 2


def test_proximo_mesmo_dia_soma_7():
    r = processar(_ctx(ultimo_dia_exibido=UDE))
    assert r["proximo_mesmo_dia"] == "2026-07-21"


def test_data_estendida_soma_21():
    r = processar(_ctx(coleta_data="2026-07-01"))
    assert r["data_estendida"] == "2026-07-22"
