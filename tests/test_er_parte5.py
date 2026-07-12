"""
Testes da Parte 5 do port do ER (app/er.py::processar_troca_unidade_medico) — linhas
1947-2461 do JS fonte: overrides de navegacao, troca de medico/unidade, FIX_DIA_SEM_UNIDADE,
casos Bradesco+Tatuape, lembretes de periodo/convenio obrigatorios.
"""

from app.er import processar_troca_unidade_medico


def _base(**overrides):
    b = {
        "cache_ativo": False,
        "ultimo_dia_exibido": None,
        "sessao_rota": 0,
        "sessao_intencao": "",
        "paciente_encontrado": True,
        "coleta_id_tisaude": "",
        "cpf_dependente": "",
        "coleta_medico": "",
        "coleta_unidade": "",
        "coleta_dia_semana": "",
        "coleta_data": "",
        "coleta_periodo": "",
        "coleta_horario": "",
        "coleta_convenio": "",
        "coleta_terceiro": "",
        "_autoswitch_fired": False,
        "texto_ia": "",
        "_clear_pm": {},
    }
    b.update(overrides)
    return b


def _proc(texto, base=None, intencao_rapida="agenda", rota_agente=4, ia_output=None,
          eh_cancel_real=False, eh_mensagem_informativa=False):
    io = ia_output if ia_output is not None else {}
    r = processar_troca_unidade_medico(
        base or _base(), texto, intencao_rapida, rota_agente, io, eh_cancel_real, eh_mensagem_informativa,
    )
    return r, io


# ---------- overrides de navegacao ----------

def test_data_explicita_com_cache_forca_navegacao():
    b = _base(cache_ativo=True)
    r, io = _proc("dia 15", base=b, rota_agente=2)
    assert io.get("eh_navegacao") is True


def test_dia_diferente_do_cache_descarta_confirmacao():
    b = _base(cache_ativo=True, ultimo_dia_exibido={"data": "2026-07-20"})
    r, io = _proc("quero o dia 22", base=b, rota_agente=4, ia_output={"eh_confirmacao": True})
    assert io["eh_confirmacao"] is False


def test_sem_cache_desativa_navegacao():
    b = _base(cache_ativo=False)
    r, io = _proc("oi", base=b, ia_output={"eh_navegacao": True})
    assert io["eh_navegacao"] is False


def test_pede_outro_dia_em_rota4_desativa_navegacao():
    b = _base(cache_ativo=True)
    r, io = _proc("quero outro dia", base=b, rota_agente=4, ia_output={"eh_navegacao": True})
    assert io["eh_navegacao"] is False


def test_outro_dia_classificado_como_cancelamento_restaura_rota():
    b = _base(sessao_rota=4, sessao_intencao="agenda")
    r, io = _proc("quero outro dia", base=b, rota_agente=1)
    assert r.rota_agente == 4
    assert io.get("intencao_rapida") == "agenda"


# ---------- cancelamento sem identidade ----------

def test_cancelamento_sem_identidade_pede_cpf():
    b = _base(paciente_encontrado=False)
    r, io = _proc("quero cancelar minha consulta", base=b, rota_agente=1)
    assert "CANCELAMENTO SEM IDENTIDADE" in r.base["texto_ia"]
    assert r.base["_cancel_bloqueado_sem_cpf"] is True


# ---------- troca de medico ----------

def test_pedido_generico_de_outro_medico_volta_pra_coleta():
    b = _base(coleta_terceiro="")
    r, io = _proc("quero outro medico", base=b, rota_agente=4)
    assert r.rota_agente == 2
    assert io.get("eh_confirmacao") is False


def test_menciona_nome_de_outro_medico_com_grade():
    b = _base(coleta_medico="Dr. Elias Lobo Braga", coleta_unidade="Vila Olímpia")
    r, io = _proc("prefiro com a giseli", base=b, rota_agente=4)
    assert r.base["coleta_medico"] == "Dra. Giseli Rebechi"
    assert "TROCA MEDICO" in r.base["texto_ia"]
    assert "terça, quarta" in r.base["texto_ia"]


def test_menciona_medico_que_nao_atende_na_unidade_salva():
    b = _base(coleta_medico="Dr. Elias Lobo Braga", coleta_unidade="Tatuapé")
    r, io = _proc("quero a juliana", base=b, rota_agente=4)
    assert "NAO atende na Tatuapé" in r.base["texto_ia"]


# ---------- GUARD_CONFIRMACAO_V2 ----------

def test_confirmacao_com_horario_stale_e_descartada():
    b = _base(coleta_horario="14:00", ultimo_dia_exibido={"data": "2026-07-20", "medicos": [{"horarios": "15:00, 16:00"}]})
    r, io = _proc("sim", base=b, ia_output={"eh_confirmacao": True})
    assert io["eh_confirmacao"] is False


def test_confirmacao_com_horario_explicito_na_msg_mantida():
    b = _base()
    r, io = _proc("as 14:00 mesmo", base=b, ia_output={"eh_confirmacao": True})
    assert io["eh_confirmacao"] is True


# ---------- FIX_TROCA_UNIDADE_INJECT / DIA ----------

def test_troca_unidade_medico_so_vo_fica_invalido():
    b = _base(coleta_unidade="Vila Olímpia", coleta_medico="Dra. Stephanie Rugeri de Souza")
    r, io = _proc("pode ser no tatuape", base=b, rota_agente=2)
    assert r.base["coleta_unidade"] == "Tatuapé"
    assert r.base["coleta_medico"] == ""


def test_troca_unidade_com_dia_periodo_ambos_pergunta_periodo():
    b = _base(coleta_unidade="Tatuapé", coleta_medico="Dr. Jose Emmanuel Burle Neto")
    r, io = _proc("pode ser na vila olimpia segunda", base=b, rota_agente=2)
    assert r.base["coleta_unidade"] == "Vila Olímpia"
    assert "TROCA UNIDADE + DIA:" in r.base["texto_ia"]
    assert "Manha ou tarde?" in r.base["texto_ia"]


# ---------- FIX_PERGUNTA_DIA_CONFIRM ----------

def test_confirma_troca_sugerida_com_dia_salvo():
    b = _base(coleta_medico="Dra. Fernanda Butura Broetto", coleta_unidade="Vila Olímpia", coleta_dia_semana="sexta")
    r, io = _proc("pode ser", base=b, rota_agente=2)
    assert r.base["coleta_unidade"] == "Tatuapé"
    assert "TROCA UNIDADE CONFIRMADA" in r.base["texto_ia"]
    assert r.base.get("intencao_rapida") == "agenda"


# ---------- FIX_BRADESCO_TA_AUTOSWITCH ----------

def test_bradesco_tatuape_aceita_mudar_unidade():
    # "1" (nao "vila olimpia" por extenso): o guard generico FIX_TROCA_UNIDADE_INJECT roda
    # ANTES do autoswitch do Bradesco e tambem reconhece mencoes a "olimpia" -- com texto livre
    # ele intercepta a troca de unidade primeiro e o path1 do Bradesco nunca dispara.
    b = _base(coleta_unidade="Tatuapé", coleta_convenio="Bradesco", coleta_medico="Dr. Elias Lobo Braga")
    r, io = _proc("1", base=b, rota_agente=2)
    assert r.base["coleta_unidade"] == "Vila Olímpia"
    assert r.base["coleta_convenio"] == "Bradesco"
    assert "TROCA UNIDADE ACEITA" in r.base["texto_ia"]
    assert r.base["_autoswitch_fired"] is True


def test_bradesco_tatuape_pede_particular_vai_pra_humano():
    b = _base(coleta_unidade="Tatuapé", coleta_convenio="Bradesco")
    r, io = _proc("quero particular", base=b, rota_agente=2)
    assert r.intencao_rapida == "humano"
    assert "Bradesco" in r.base["motivo_humano"]


def test_bradesco_tatuape_confirmacao_ambigua_reask():
    b = _base(coleta_unidade="Tatuapé", coleta_convenio="Bradesco")
    r, io = _proc("sim", base=b, rota_agente=2)
    assert "BRADESCO TATUAPE REASK" in r.base["texto_ia"]


# ---------- FIX_BRADESCO_TA_DETERMINISTIC ----------

def test_bradesco_mencionado_pela_primeira_vez_em_tatuape():
    b = _base(coleta_unidade="Tatuapé", coleta_convenio="")
    r, io = _proc("tenho bradesco", base=b, rota_agente=2)
    assert "RESTRITO — SO VILA OLIMPIA" in r.base["texto_ia"]


# ---------- FIX_DIA_SEM_UNIDADE ----------

def test_dia_sem_unidade_resolve_unidade_via_grade():
    b = _base(coleta_medico="Dr. Elias Lobo Braga", coleta_unidade="", prox_seg="2026-07-13")
    r, io = _proc("pode ser segunda", base=b, rota_agente=2)
    assert r.base["coleta_unidade"] == "Tatuapé"
    assert r.base["coleta_data"] == "2026-07-13"
    assert "manha e tarde" in r.base["texto_ia"]


def test_dia_sem_unidade_fim_de_semana():
    b = _base(coleta_medico="Dr. Elias Lobo Braga", coleta_unidade="")
    r, io = _proc("pode ser sabado", base=b, rota_agente=2)
    assert "DIA FIM DE SEMANA" in r.base["texto_ia"]


def test_dia_sem_unidade_dia_invalido_pro_medico():
    b = _base(coleta_medico="Dr. Elias Lobo Braga", coleta_unidade="")
    r, io = _proc("pode ser quinta", base=b, rota_agente=2)
    assert "DIA INVALIDO" in r.base["texto_ia"]


# ---------- FIX_PERIODO_OBRIGATORIO / FIX_CONV_OBRIGATORIO ----------

def test_periodo_obrigatorio_lembra_de_perguntar():
    b = _base(coleta_medico="Dr. X", coleta_dia_semana="terca")
    r, io = _proc("pode ser", base=b, rota_agente=2)
    assert "PERIODO OBRIGATORIO" in r.base["texto_ia"]
    assert r.base["coleta_data"] != ""


def test_convenio_obrigatorio_lembra_de_perguntar():
    b = _base(coleta_medico="Dr. X", coleta_data="2026-07-20")
    r, io = _proc("de manha mesmo", base=b, rota_agente=2)
    assert "CONVENIO OBRIGATORIO" in r.base["texto_ia"]
