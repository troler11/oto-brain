"""
Testes da Parte 10 do port do ER (app/er.py::processar_convenio_e_dia_deterministico) —
linhas 3691-3982 do JS fonte: aceite determinístico de Porto Seguro/Itaú, "qualquer um" pós-
desambiguação, dia da semana sem médico (com data absoluta), período determinístico, guard
anti-assunção-silenciosa de dia, "mesmo médico de sempre", menu P3 inválido, convênio genérico.
"""

from app.er import processar_convenio_e_dia_deterministico


def _base(**overrides):
    b = {
        "coleta_unidade": "",
        "coleta_medico": "",
        "coleta_convenio": "",
        "coleta_periodo": "",
        "coleta_data": "",
        "coleta_dia_semana": "",
        "coleta_horario": "",
        "coleta_modo": 0,
        "paciente_encontrado": True,
        "_ultimo_medico_global": "",
        "_dia_periodo_resolvido": False,
        "_periodo_precomputed": False,
        "hoje": "",
        "texto_ia": "",
        "_clear_pm": {},
    }
    b.update(overrides)
    return b


def _proc(texto, base=None, intencao_rapida="agenda", rota_agente=2, identidade_incompleta=False):
    return processar_convenio_e_dia_deterministico(
        base or _base(), texto, intencao_rapida, rota_agente, identidade_incompleta,
    )


# ---------- FIX_PORTO_ITAU_DETERMINISTIC ----------

def test_porto_seguro_com_coleta_completa_busca_direto():
    b = _base(coleta_unidade="Vila Olímpia", coleta_data="2026-07-20", coleta_periodo="tarde")
    r = _proc("tenho porto seguro", base=b, rota_agente=2)
    assert r.rota_agente == 4
    assert r.base["coleta_convenio"] == "Porto Seguro"
    assert "CONV ACEITO + BUSCAR AGENDA" in r.base["texto_ia"]


def test_porto_seguro_busca_direto_mesmo_sem_match_tisaude_se_identidade_ja_coletada():
    # Regressão exec 67708 (replay 12/07-13/07, 96% concordância): paciente_encontrado=False
    # (TiSaude não achou o CPF ainda) mas nome/CPF/nascimento do dependente já foram coletados
    # — _identidadeIncompleta real (JS linha 1549) é False nesse caso, não True. O port tinha um
    # bug: recomputava `not paciente_encontrado` local em vez de usar o valor threaded do
    # orquestrador, then bloqueava o atalho pra buscar_agenda incorretamente.
    b = _base(
        coleta_unidade="Tatuapé", coleta_medico="Dr. Jose Emmanuel Burle Neto",
        coleta_data="2026-07-14", coleta_periodo="manha", paciente_encontrado=False,
    )
    r = _proc("Convênio porto seguro prata rcq mais", base=b, rota_agente=2, identidade_incompleta=False)
    assert r.rota_agente == 4
    assert r.base["coleta_convenio"] == "Porto Seguro"
    assert "CONV ACEITO + BUSCAR AGENDA" in r.base["texto_ia"]


def test_porto_seguro_nao_busca_direto_se_identidade_realmente_incompleta():
    b = _base(coleta_unidade="Vila Olímpia", coleta_data="2026-07-20", coleta_periodo="tarde")
    r = _proc("tenho porto seguro", base=b, rota_agente=2, identidade_incompleta=True)
    assert r.rota_agente == 2
    assert "CONV ACEITO + BUSCAR AGENDA" not in r.base["texto_ia"]
    assert "CONV ACEITO: Porto Seguro" in r.base["texto_ia"]


# ---------- FIX_QUALQUER_UM_MODO2 ----------

def test_qualquer_um_seta_sem_preferencia_modo2():
    b = _base(coleta_dia_semana="segunda", coleta_medico="")
    r = _proc("qualquer um", base=b)
    assert r.base["coleta_medico"] == "sem preferencia"
    assert r.base["coleta_modo"] == 2
    assert r.base["_modo2_precomputed"] is True


# ---------- FIX_DIA_SEMANA_DISAMBIGUACAO ----------

def test_disambiguacao_medico_unico_tatuape_segunda():
    b = _base(coleta_unidade="Tatuapé")
    r = _proc("segunda", base=b)
    assert r.base["coleta_medico"] == "Elias"
    assert r.base["coleta_modo"] == 3
    assert r.base["coleta_dia_semana"] == "segunda"
    assert r.base["coleta_data"] != ""


def test_disambiguacao_multiplos_medicos_vila_olimpia_segunda():
    b = _base(coleta_unidade="Vila Olímpia")
    r = _proc("segunda", base=b)
    assert r.base["coleta_dia_semana"] == "segunda"
    assert r.base["_dia_semana_precomputed"] is True
    assert "MÉDICOS NA SEGUNDA" in r.base["texto_ia"]
    assert "Jose Emmanuel Burle Neto" in r.base["texto_ia"]


# ---------- FIX_PERIODO_DETERMINISTIC ----------

def test_periodo_resolvido_lista_dias():
    b = _base(coleta_unidade="Vila Olímpia", coleta_medico="Dr. Elias Lobo Braga")
    r = _proc("tarde", base=b)
    assert r.base["coleta_periodo"] == "tarde"
    assert "PERIODO RESOLVIDO" in r.base["texto_ia"]


def test_periodo_indisponivel_limpa_periodo():
    b = _base(coleta_unidade="Vila Olímpia", coleta_medico="Dr. Caio Vinicius Saettini")
    r = _proc("tarde", base=b)
    assert r.base["coleta_periodo"] == ""
    assert "PERIODO INDISPONIVEL" in r.base["texto_ia"]


# ---------- FIX_DIA_SEMANA_GUARD ----------

def test_dia_semana_guard_texto_invalido():
    b = _base(coleta_unidade="Vila Olímpia", coleta_medico="Dr. Elias Lobo Braga", coleta_modo=3)
    r = _proc("oi tudo bem", base=b)
    assert "DIA_SEMANA_INVALIDO" in r.base["texto_ia"]


def test_dia_semana_guard_qualquer_vira_proximo_horario():
    b = _base(coleta_unidade="Vila Olímpia", coleta_medico="Dr. Elias Lobo Braga", coleta_modo=3)
    r = _proc("qualquer horario mesmo", base=b, rota_agente=2)
    assert r.rota_agente == 4
    assert r.base["_sub_rota_agenda"] == "navegacao"
    assert "PROXIMO_HORARIO_MEDICO" in r.base["texto_ia"]


def test_dia_semana_guard_data_absoluta_valida():
    b = _base(coleta_unidade="Vila Olímpia", coleta_medico="Dr. Elias Lobo Braga", coleta_modo=3, hoje="2026-07-12")
    r = _proc("dia 15", base=b)
    assert r.base["coleta_data"] == "2026-07-15"
    assert r.base["coleta_dia_semana"] == "qua"
    assert "DATA OK" in r.base["texto_ia"]
    assert "Manhã ou tarde?" in r.base["texto_ia"]


def test_dia_semana_guard_data_absoluta_invalida_pro_medico():
    b = _base(coleta_unidade="Vila Olímpia", coleta_medico="Dr. Elias Lobo Braga", coleta_modo=3, hoje="2026-07-12")
    r = _proc("dia 13", base=b)
    assert "DATA INVALIDA MEDICO" in r.base["texto_ia"]
    assert r.base["coleta_data"] == ""


# ---------- FIX_MESMO_MEDICO ----------

def test_mesmo_medico_resolve_via_ultimo_global():
    b = _base(coleta_unidade="Vila Olímpia", _ultimo_medico_global="Dr. Elias Lobo Braga")
    r = _proc("quero o mesmo medico de sempre", base=b)
    assert r.base["coleta_medico"] == "Dr. Elias Lobo Braga"
    assert r.base["coleta_modo"] == 3
    assert "MESMO MEDICO:" in r.base["texto_ia"]


def test_mesmo_medico_sem_atendimento_anterior():
    b = _base(coleta_unidade="Vila Olímpia", _ultimo_medico_global="")
    r = _proc("quero o mesmo de sempre", base=b)
    assert "SEM MEDICO ANTERIOR" in r.base["texto_ia"]


# ---------- FIX_MENU_P3_INVALIDO ----------

def test_menu_p3_invalido_repete_menu():
    b = _base(coleta_unidade="Vila Olímpia")
    r = _proc("alo?", base=b)
    assert "MENU_P3_INVALIDO" in r.base["texto_ia"]


# ---------- FIX_CONVENIO_GENERICO ----------

def test_convenio_generico_sem_nome_do_plano():
    b = _base(coleta_unidade="Vila Olímpia", coleta_medico="Dr. Elias Lobo Braga", coleta_modo=2,
              coleta_dia_semana="terca")
    r = _proc("e convenio", base=b)
    assert "CONVENIO GENERICO" in r.base["texto_ia"]
