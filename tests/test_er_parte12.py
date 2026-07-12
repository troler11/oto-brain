"""
Testes da Parte 12 do port do ER (app/er.py::processar_particular_dados_med_triagem) —
linhas 4196-4409 do JS fonte: FIX_PARTICULAR_DETERMINISTIC, FIX_PARTICULAR_CONFIRMADO,
FIX_MODO1_SEM_DIA_SEMANA, FIX_0PAC_CADASTRO_INTRO, FIX_GRADE_MED_EXPLICITO/DADOS_MED_INJECT,
FIX_RETOMAR_ESPECIALISTA, FIX_DUVIDA_GENERICA, FIX_RESPOSTA_CURTA_TRIAGEM.
"""

from app.er import processar_particular_dados_med_triagem


def _base(**overrides):
    b = {
        "coleta_unidade": "",
        "coleta_medico": "",
        "coleta_convenio": "",
        "coleta_periodo": "",
        "coleta_data": "",
        "coleta_dia_semana": "",
        "coleta_modo": 0,
        "paciente_encontrado": True,
        "nome_dependente": "",
        "sessao_intencao": "",
        "pacientes": [],
        "lista_med": "",
        "texto_ia": "",
        "motivo_humano": None,
    }
    b.update(overrides)
    return b


def _proc(texto, base=None, intencao_rapida="triagem", rota_agente=2, ia_output=None,
          eh_texto_terceiro=False, eh_mensagem_informativa=False, eh_sessao_nova=False, faq_tag=""):
    io = ia_output if ia_output is not None else {}
    r = processar_particular_dados_med_triagem(
        base or _base(), texto, intencao_rapida, rota_agente, io,
        eh_texto_terceiro, eh_mensagem_informativa, eh_sessao_nova, faq_tag,
    )
    return r, io


# ---------- FIX_PARTICULAR_DETERMINISTIC ----------

def test_particular_detectado_exibe_precos():
    b = _base(coleta_unidade="Vila Olímpia")
    r, io = _proc("sera no particular", base=b, rota_agente=2)
    assert r.base["coleta_convenio"] == "PART?"
    assert "PARTICULAR DETECTADO" in r.base["texto_ia"]


# ---------- FIX_PARTICULAR_CONFIRMADO ----------

def test_particular_confirmado_coleta_completa_busca_direto():
    b = _base(coleta_convenio="PART?", coleta_data="2026-07-20", coleta_periodo="tarde",
              coleta_unidade="Vila Olímpia")
    r, io = _proc("sim, pode confirmar", base=b, rota_agente=2)
    assert r.rota_agente == 4
    assert r.base["coleta_convenio"] == "Particular"
    assert "PARTICULAR CONFIRMADO + BUSCAR AGENDA" in r.base["texto_ia"]


def test_particular_pendente_sem_confirmacao_clara():
    b = _base(coleta_convenio="PART?")
    r, io = _proc("qual horario disponivel", base=b, rota_agente=2)
    assert "PARTICULAR PENDENTE" in r.base["texto_ia"]


def test_particular_recusa_forte_vai_pra_humano():
    b = _base(coleta_convenio="PART?")
    r, io = _proc("nao", base=b, rota_agente=2)
    assert r.intencao_rapida == "humano"
    assert io["bypass_agente_humano"] is True
    assert r.base["motivo_humano"] == "Recusou particular"
    assert "RECUSA PARTICULAR" in r.base["texto_ia"]


# ---------- FIX_MODO1_SEM_DIA_SEMANA ----------

def test_modo1_limpa_dia_semana():
    b = _base(coleta_modo=1, coleta_dia_semana="qua")
    r, io = _proc("oi", base=b, rota_agente=2)
    assert r.base["coleta_dia_semana"] == ""


# ---------- FIX_0PAC_CADASTRO_INTRO ----------

def test_0pac_cadastro_intro_para_mim():
    b = _base(paciente_encontrado=False, nome_dependente="")
    r, io = _proc("para mim", base=b, rota_agente=2)
    assert "CADASTRO NOVO" in r.base["texto_ia"]
    assert "t=false" in r.base["texto_ia"]


def test_0pac_cadastro_intro_terceiro_marca_t_true():
    b = _base(paciente_encontrado=False, nome_dependente="")
    r, io = _proc("joao silva", base=b, rota_agente=2, eh_texto_terceiro=True)
    assert "t=true" in r.base["texto_ia"]


# ---------- FIX_GRADE_MED_EXPLICITO / DADOS_MED_INJECT ----------

def test_grade_med_bare_1_sem_medico_vira_modo1():
    b = _base(coleta_unidade="Vila Olímpia", coleta_medico="")
    r, io = _proc("1", base=b, rota_agente=2)
    assert r.base["coleta_medico"] == "sem preferencia"
    assert r.base["coleta_modo"] == 1
    assert r.base["_modo1_precomputed"] is True
    assert "[DADOS_MED]" not in r.base["texto_ia"]


def test_grade_med_injeta_dados_med_tatuape():
    b = _base(coleta_unidade="Tatuapé", coleta_medico="Dr. Elias Lobo Braga")
    r, io = _proc("quero segunda", base=b, rota_agente=2)
    assert r.base["texto_ia"].startswith("[DADOS_MED]")
    assert "Elias→segunda" in r.base["texto_ia"]


# ---------- FIX_RETOMAR_ESPECIALISTA ----------

def test_retomar_especialista_reexibe_lista():
    b = _base(coleta_unidade="Vila Olímpia", coleta_modo=2, lista_med="LISTA COMPLETA DE MEDICOS")
    r, io = _proc("sim", base=b, rota_agente=2, eh_mensagem_informativa=False)
    assert "RETOMAR ESCOLHA ESPECIALISTA" in r.base["texto_ia"]
    assert "LISTA COMPLETA DE MEDICOS" in r.base["texto_ia"]
    assert "[DADOS_MED]" not in r.base["texto_ia"]


# ---------- FIX_DUVIDA_GENERICA ----------

def test_duvida_generica_pergunta_qual_e():
    b = _base()
    r, io = _proc("tenho uma duvida", base=b, rota_agente=0, eh_sessao_nova=True, faq_tag="")
    assert "DUVIDA GENERICA" in r.base["texto_ia"]


# ---------- FIX_RESPOSTA_CURTA_TRIAGEM ----------

def test_resposta_curta_fraca_pede_confirmacao():
    b = _base()
    r, io = _proc("ok", base=b, rota_agente=0, eh_sessao_nova=True, faq_tag="")
    assert "CONFIRMACAO FRACA" in r.base["texto_ia"]


def test_resposta_sim_forte_inicia_agendamento():
    b = _base(pacientes=[{"nome": "Ana Souza"}])
    r, io = _proc("sim", base=b, rota_agente=0, eh_sessao_nova=True, faq_tag="")
    assert r.rota_agente == 2
    assert r.intencao_rapida == "coleta"
    assert "INICIO AGENDA CONFIRMADO" in r.base["texto_ia"]
    assert "Ana Souza" in r.base["texto_ia"]
