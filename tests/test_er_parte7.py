"""
Testes da Parte 7 do port do ER (app/er.py::processar_dia_periodo_avancado) — linhas
2794-3055 do JS fonte: deteccao de dia nao negado, FIX_DIA_CROSS_UNIT, FIX_ATENDENTE_SUBSTRING,
FIX_PERGUNTA_DIA, FIX_TROCA_PERIODO, FIX_PROXIMO_HORARIO, FIX_DIA_SEMANA_INJECT.
"""

from app.er import _dia_nao_negado_ok, processar_dia_periodo_avancado


def _base(**overrides):
    b = {
        "coleta_medico": "",
        "coleta_unidade": "",
        "coleta_dia_semana": "",
        "coleta_terceiro": "",
        "coleta_periodo": "",
        "coleta_modo": 0,
        "coleta_data": "",
        "cache_ativo": False,
        "ultimo_dia_exibido": None,
        "texto_ia": "",
        "grade_med": "",
    }
    b.update(overrides)
    return b


def _proc(texto, base=None, intencao_rapida="agenda", rota_agente=2, ia_output=None):
    io = ia_output if ia_output is not None else {}
    r = processar_dia_periodo_avancado(base or _base(), texto, intencao_rapida, rota_agente, io)
    return r, io


# ---------- helper _dia_nao_negado_ok ----------

def test_dia_nao_negado_ignora_dia_negado():
    m = _dia_nao_negado_ok("nao posso na terca, tem quarta?", "segunda|seg|terca|ter|quarta|qua|quinta|qui|sexta|sex")
    assert m.group(1) == "quarta"


# ---------- FIX_DIA_CROSS_UNIT ----------

def test_cross_unit_sugere_outra_unidade():
    # "quero segunda" (nao "tem segunda"/"atende segunda"): evita tambem casar a frase-gatilho
    # do FIX_PERGUNTA_DIA (que roda logo depois e reescreveria coleta_dia_semana pro nome
    # completo em vez da abreviacao que o CROSS_UNIT usa).
    b = _base(coleta_medico="Dra. Juliana Paulino do Amaral", coleta_unidade="Tatuapé")
    r, io = _proc("quero segunda", base=b, rota_agente=2)
    assert r.intencao_rapida == "pergunta_troca"
    assert r.base["coleta_dia_semana"] == "seg"
    assert "OUTRA UNIDADE" in r.base["texto_ia"]


def test_cross_unit_nenhuma_unidade_atende():
    b = _base(coleta_medico="Dra. Juliana Paulino do Amaral", coleta_unidade="Vila Olímpia")
    r, io = _proc("quero quarta", base=b, rota_agente=2)
    assert "NENHUMA UNIDADE" in r.base["texto_ia"]


# ---------- FIX_ATENDENTE_SUBSTRING ----------

def test_atendente_nao_e_lido_como_pergunta_de_dia():
    b = _base(coleta_medico="Dr. Elias Lobo Braga")
    r, io = _proc("quero falar com atendente", base=b, rota_agente=4)
    assert r.rota_agente == 4
    assert io.get("eh_navegacao") is None


# ---------- FIX_PERGUNTA_DIA ----------

def test_pergunta_dia_que_medico_atende_promove_rota4():
    b = _base(coleta_medico="Dr. Elias Lobo Braga", coleta_unidade="Vila Olímpia")
    r, io = _proc("ela atende terca?", base=b, rota_agente=4)
    assert r.rota_agente == 4
    assert r.intencao_rapida == "agenda"
    assert "TROCA DIA" in r.base["texto_ia"]
    assert r.base["coleta_dia_semana"] == "ter"


def test_pergunta_dia_generica_lista_grade_completa():
    b = _base(coleta_medico="Dr. Elias Lobo Braga", coleta_unidade="Vila Olímpia")
    r, io = _proc("ela atende bastante?", base=b, rota_agente=2)
    assert "PERGUNTA DIA GENERICA" in r.base["texto_ia"]
    assert "terça (só tarde), quarta" in r.base["texto_ia"]


# ---------- FIX_TROCA_PERIODO ----------

def test_troca_periodo_invalida_cache():
    b = _base(coleta_periodo="manha", cache_ativo=True, ultimo_dia_exibido={"data": "2026-07-20"})
    r, io = _proc("pode ser a tarde", base=b, rota_agente=4)
    assert r.base["coleta_periodo"] == "tarde"
    assert r.base["eh_troca_data"] is True
    assert r.base["data_alvo_troca"] == "2026-07-20"


# ---------- FIX_PROXIMO_HORARIO ----------

def test_proximo_horario_limpa_periodo():
    b = _base(coleta_medico="Dr. Elias Lobo Braga", coleta_unidade="Vila Olímpia")
    r, io = _proc("quero o proximo horario disponivel", base=b, rota_agente=2)
    assert "PROXIMO HORARIO DISPONIVEL" in r.base["texto_ia"]
    assert r.base["coleta_periodo"] == ""


# ---------- FIX_DIA_SEMANA_INJECT ----------

def test_dia_semana_inject_le_tag_e_seta_troca_data():
    b = _base(coleta_medico="Dr. Jose Emmanuel Burle Neto", coleta_unidade="Tatuapé", coleta_modo=3,
              texto_ia="quero terça")
    r, io = _proc("sim", base=b, rota_agente=4)
    assert r.base["eh_troca_data"] is True
    assert r.base["dia_semana_troca"] == "terca"
    assert r.base["coleta_periodo"] == "manha"


def test_dia_semana_inject_cross_unit_sugere_troca():
    b = _base(coleta_medico="Dra. Fernanda Butura Broetto", coleta_unidade="Vila Olímpia", coleta_modo=3,
              texto_ia="sexta")
    r, io = _proc("sim", base=b, rota_agente=4)
    assert r.intencao_rapida == "pergunta_troca"
    assert r.rota_agente == 2
    assert r.base["coleta_dia_semana"] == "sex"
    assert "PERGUNTA DIA" in r.base["texto_ia"]
