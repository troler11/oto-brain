"""
Testes da Parte 11 do port do ER (app/er.py::processar_convenio_omint_e_ultimo) — linhas
3984-4194 do JS fonte: FIX_CONVENIO_ACEITO (Bradesco/Porto/Itaú determinísticos),
FIX_OMINT_V2 parte 2 (categoria + backstop + menção a médico fora do credenciamento),
FIX_67650b (desarme de bypass_agente_humano), FIX_ULTIMO_CONV, FIX_PROTECAO_COLETA_CONVENIO.
"""

from app.er import processar_convenio_omint_e_ultimo


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
        "_periodo_precomputed": False,
        "_autoswitch_fired": False,
        "_dia_periodo_resolvido": False,
        "sessao_rota": 0,
        "_ultimo_convenio_global": "",
        "pacientes": [],
        "texto_ia": "",
        "_clear_pm": {},
    }
    b.update(overrides)
    return b


def _proc(texto, base=None, intencao_rapida="agenda", rota_agente=2, ia_output=None):
    io = ia_output if ia_output is not None else {}
    r = processar_convenio_omint_e_ultimo(base or _base(), texto, intencao_rapida, rota_agente, io)
    return r, io


# ---------- FIX_CONVENIO_ACEITO ----------

def test_convenio_aceito_bradesco_vo_coleta_completa_busca_direto():
    b = _base(coleta_unidade="Vila Olímpia", coleta_medico="Dr. Elias Lobo Braga",
              coleta_data="2026-07-20", coleta_periodo="tarde")
    r, io = _proc("tenho bradesco", base=b, rota_agente=2)
    assert r.rota_agente == 4
    assert r.base["coleta_convenio"] == "Bradesco"
    assert "CONV ACEITO + BUSCAR AGENDA" in r.base["texto_ia"]


def test_convenio_aceito_bradesco_bloqueado_em_tatuape():
    b = _base(coleta_unidade="Tatuapé", coleta_medico="Dr. Elias Lobo Braga")
    r, io = _proc("tenho bradesco", base=b, rota_agente=2)
    assert r.base["coleta_convenio"] == ""
    assert r.base["texto_ia"] == ""


# ---------- FIX_OMINT_V2 parte 2 ----------

def test_omint_pergunta_categoria():
    b = _base(coleta_unidade="Vila Olímpia", coleta_medico="Dr. Elias Lobo Braga")
    r, io = _proc("tenho omint", base=b, rota_agente=2)
    assert r.base["coleta_convenio"] == "OMINT?"
    assert "OMINT CATEGORIA" in r.base["texto_ia"]
    assert "Premium" in r.base["texto_ia"]


def test_omint_premium_medico_invalido_limpa_medico():
    b = _base(coleta_unidade="Vila Olímpia", coleta_medico="Dra. Stephanie Rugeri de Souza",
              coleta_convenio="Omint Premium")
    r, io = _proc("quero com a stephanie mesmo", base=b, rota_agente=2)
    assert r.base["coleta_medico"] == ""
    assert r.base["coleta_modo"] == 0
    assert "OMINT PREMIUM MEDICO INVALIDO" in r.base["texto_ia"]


def test_omint_skill_tatuape_restrito_vila_olimpia():
    b = _base(coleta_unidade="Tatuapé", coleta_medico="Dra. Giseli Rebechi", coleta_convenio="Omint Skill")
    r, io = _proc("quero manter", base=b, rota_agente=2)
    assert r.base["coleta_medico"] == ""
    assert "OMINT SO VILA OLIMPIA" in r.base["texto_ia"]


def test_omint_corporation_atribui_torcuato():
    b = _base(coleta_unidade="Vila Olímpia", coleta_medico="Dra. Giseli Rebechi", coleta_convenio="Omint Corporation")
    r, io = _proc("prefiro a giseli", base=b, rota_agente=2)
    assert r.base["coleta_medico"] == "Dr. Torcuato Sanchez Rojas Neto"
    assert r.base["coleta_modo"] == 3
    assert "OMINT TORCUATO" in r.base["texto_ia"]
    assert "Giseli" in r.base["texto_ia"]


def test_omint_mencao_medico_fora_credenciamento():
    b = _base(coleta_unidade="Vila Olímpia", coleta_medico="", coleta_convenio="Omint Skill")
    r, io = _proc("a giseli atende?", base=b, rota_agente=2)
    assert "OMINT MEDICO FORA DO CONVENIO" in r.base["texto_ia"]
    assert "Torcuato" in r.base["texto_ia"]


# ---------- FIX_67650b ----------

def test_bypass_desarmado_por_resposta_valida_de_convenio():
    b = _base(sessao_rota=2, coleta_convenio="")
    r, io = _proc("porto seguro", base=b, rota_agente=1, ia_output={"bypass_agente_humano": True})
    assert io["bypass_agente_humano"] is False
    assert r.rota_agente == 2
    assert r.intencao_rapida == "coleta"


# ---------- FIX_ULTIMO_CONV ----------

def test_ultimo_convenio_sim_particular():
    b = _base(_ultimo_convenio_global="Particular", coleta_data="2026-07-20", coleta_periodo="tarde")
    r, io = _proc("sim, mesma forma", base=b, rota_agente=2)
    assert r.base["coleta_convenio"] == "PART?"
    assert "ULTIMO CONVENIO PARTICULAR" in r.base["texto_ia"]


def test_ultimo_convenio_sim_omint_pergunta_categoria():
    b = _base(_ultimo_convenio_global="Omint", coleta_data="2026-07-20", coleta_periodo="manha")
    r, io = _proc("sim", base=b, rota_agente=2)
    assert r.base["coleta_convenio"] == "OMINT?"
    assert "ULTIMO CONVENIO OMINT" in r.base["texto_ia"]


def test_ultimo_convenio_sim_regular_promove_rota4():
    b = _base(_ultimo_convenio_global="Bradesco", coleta_data="2026-07-20", coleta_periodo="tarde",
              coleta_unidade="Vila Olímpia", paciente_encontrado=True)
    r, io = _proc("pode ser a mesma forma", base=b, rota_agente=2)
    assert r.rota_agente == 4
    assert r.base["coleta_convenio"] == "Bradesco"
    assert "ULTIMO CONVENIO ACEITO" in r.base["texto_ia"]


def test_ultimo_convenio_recusado_mostra_opcoes():
    b = _base(_ultimo_convenio_global="Bradesco", coleta_data="2026-07-20", coleta_periodo="tarde")
    r, io = _proc("quero outro", base=b, rota_agente=2)
    assert "ULTIMO CONVENIO RECUSADO" in r.base["texto_ia"]


# ---------- FIX_PROTECAO_COLETA_CONVENIO ----------

def test_protecao_coleta_convenio_confirmacao_continuar():
    b = _base(coleta_medico="Dr. Elias Lobo Braga", coleta_unidade="Vila Olímpia", coleta_periodo="tarde")
    r, io = _proc("sim quero continuar", base=b, rota_agente=2)
    assert "CONTINUAR COLETA CONVENIO" in r.base["texto_ia"]


def test_protecao_coleta_convenio_invalido_preserva_campos():
    b = _base(coleta_medico="Dr. Elias Lobo Braga", coleta_unidade="Vila Olímpia", coleta_periodo="tarde")
    r, io = _proc("abacate", base=b, rota_agente=2)
    assert "CONVENIO INVALIDO" in r.base["texto_ia"]
    assert r.base["coleta_medico"] == "Dr. Elias Lobo Braga"
