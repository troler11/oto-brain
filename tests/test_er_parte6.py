"""
Testes da Parte 6 do port do ER (app/er.py::processar_medico_dia_periodo) — linhas
2462-2792 do JS fonte: "para mim" com paciente unico, cancelamento automatico, atalho de
medico, resolucao medico->dia (unico/multi), injecao de periodo, resolvedor
dia+periodo deterministico.
"""

from app.er import processar_medico_dia_periodo


def _base(**overrides):
    b = {
        "pacientes": [],
        "coleta_terceiro": "",
        "coleta_unidade": "",
        "coleta_medico": "",
        "coleta_modo": 0,
        "coleta_dia_semana": "",
        "coleta_data": "",
        "coleta_periodo": "",
        "coleta_convenio": "",
        "sessao_intencao": "",
        "nome_dependente": "",
        "cpf_dependente": "",
        "nascimento_dependente": "",
        "coleta_id_tisaude": "",
        "id_tisaude": "",
        "cpf": "",
        "texto_ia": "",
    }
    b.update(overrides)
    return b


def _proc(texto, base=None, intencao_rapida="agenda", rota_agente=2, ia_output=None,
          identidade_incompleta=False):
    r = processar_medico_dia_periodo(
        base or _base(), texto, intencao_rapida, rota_agente, ia_output or {}, identidade_incompleta,
    )
    return r


# ---------- FIX_PARA_MIM ----------

def test_para_mim_com_paciente_unico_preenche_titular():
    b = _base(pacientes=[{"nome": "JOAO SILVA", "cpf": "111", "nascimento": "01/01/1990", "id_tisaude": "5"}])
    r = _proc("para mim", base=b)
    assert r.base["nome_dependente"] == "JOAO SILVA"
    assert r.base["coleta_terceiro"] == "false"
    assert "QUEM CONFIRMADO TITULAR" in r.base["texto_ia"]


# ---------- FIX_CANCELAMENTO_PACIENTE_AUTO / QUEM_SKIP / RECUSA ----------

def test_cancelamento_1_paciente_preenche_dependente_auto():
    b = _base(pacientes=[{"nome": "ANA", "cpf": "222", "nascimento": "02/02/1980", "id_tisaude": "9"}])
    r = _proc("quero cancelar", base=b, rota_agente=1)
    assert r.base["nome_dependente"] == "ANA"


def test_cancelamento_quem_skip_nao_repete_pergunta():
    b = _base(nome_dependente="ANA", cpf_dependente="222", sessao_intencao="cancelando")
    r = _proc("1", base=b, rota_agente=1)
    assert "QUEM CONFIRMADO" in r.base["texto_ia"]
    assert "NAO reliste" in r.base["texto_ia"]


def test_recusa_cancelamento_encerra():
    b = _base(sessao_intencao="cancelando")
    r = _proc("nao quero cancelar", base=b, rota_agente=1)
    assert r.intencao_rapida == "concluido"
    assert "RECUSA CANCELAMENTO" in r.base["texto_ia"]


def test_ja_resolveu_cancelamento_encerra_educado():
    b = _base(sessao_intencao="cancelando")
    r = _proc("ja resolvi, obrigada", base=b, rota_agente=1)
    assert r.intencao_rapida == "concluido"
    assert "ENCERRAMENTO CANCELAMENTO RESOLVIDO" in r.base["texto_ia"]


# ---------- FIX_MEDICO_ATALHO_INJECT ----------

def test_atalho_medico_periodo_unico():
    # coleta_modo=1 ("sem preferencia"): desliga o FIX_MEDICO_UNICO_DIA (que roda logo depois
    # e, para os 3 mesmos medicos do atalho, sempre teria a palavra final -- ver nota no commit).
    b = _base(coleta_unidade="Vila Olímpia", coleta_periodo="", coleta_modo=1)
    r = _proc("quero com o caio", base=b)
    assert "ATALHO MEDICO" in r.base["texto_ia"]


# ---------- FIX_MEDICO_UNICO_DIA ----------

def test_medico_unico_dia_com_periodo_unico():
    b = _base(coleta_unidade="Vila Olímpia")
    r = _proc("quero com a fernanda", base=b)
    assert r.base["coleta_medico"] == "Dra. Fernanda Butura Broetto"
    assert r.base["coleta_periodo"] == "tarde"
    assert "MEDICO DIA+PERIODO UNICO" in r.base["texto_ia"]


def test_medico_unico_dia_ambos_periodos_pergunta():
    b = _base(coleta_unidade="Tatuapé")
    r = _proc("quero com a giseli", base=b)
    assert r.base["coleta_dia_semana"] == "quinta"
    assert "MEDICO DIA UNICO" in r.base["texto_ia"]
    assert "Deseja manha ou tarde?" in r.base["texto_ia"]


# ---------- FIX_MEDICO_MULTI_DIA ----------

def test_medico_multi_dia_pergunta_dia():
    b = _base(coleta_unidade="Vila Olímpia")
    r = _proc("quero com o elias", base=b)
    assert r.base["coleta_medico"] == "Dr. Elias Lobo Braga"
    assert "MEDICO MULTI DIA" in r.base["texto_ia"]


# ---------- FIX_DIA_PERIODO_DETERMINISTICO ----------

def test_dia_invalido_para_medico():
    b = _base(coleta_medico="Dra. Giseli Rebechi", coleta_unidade="Vila Olímpia")
    r = _proc("pode ser segunda", base=b)
    assert "DIA INVALIDO MEDICO" in r.base["texto_ia"]


def test_dia_periodo_resolvido_completo_promove_rota4():
    b = _base(coleta_medico="Dra. Giseli Rebechi", coleta_unidade="Vila Olímpia", coleta_convenio="Particular")
    r = _proc("pode ser quarta", base=b, identidade_incompleta=False)
    assert r.rota_agente == 4
    assert r.intencao_rapida == "agenda"
    assert "coleta COMPLETA" in r.base["texto_ia"]


def test_dia_periodo_resolvido_sem_convenio_pergunta_convenio():
    b = _base(coleta_medico="Dra. Giseli Rebechi", coleta_unidade="Vila Olímpia", coleta_convenio="")
    r = _proc("pode ser quarta", base=b, rota_agente=2)
    assert r.rota_agente == 2
    assert "Particular ou Convênio" in r.base["texto_ia"]


def test_dia_com_dois_periodos_sem_especificar_pede_periodo():
    b = _base(coleta_medico="Dr. Jose Emmanuel Burle Neto", coleta_unidade="Vila Olímpia")
    r = _proc("pode ser segunda", base=b)
    assert "FALTA PERIODO" in r.base["texto_ia"]


def test_dia_e_periodo_juntos_resolve_completo():
    b = _base(coleta_medico="Dr. Jose Emmanuel Burle Neto", coleta_unidade="Vila Olímpia", coleta_convenio="Particular")
    r = _proc("pode ser segunda de manha", base=b, identidade_incompleta=False)
    assert r.rota_agente == 4
    assert "coleta COMPLETA" in r.base["texto_ia"]


def test_periodo_respondido_separado_apos_dia_salvo():
    b = _base(coleta_medico="Dr. Jose Emmanuel Burle Neto", coleta_unidade="Vila Olímpia",
              coleta_data="2026-07-13", coleta_dia_semana="segunda")
    r = _proc("de tarde", base=b)
    assert r.base["coleta_periodo"] == "tarde"
    assert "PERIODO RESOLVIDO" in r.base["texto_ia"]
