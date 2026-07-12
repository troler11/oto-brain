"""
Testes da Parte 4 do port do ER (app/er.py::processar_sub_rota_agenda) — linhas 1615-1945
do JS fonte: maquina de sub-rota da agenda (navegacao -> confirmacao -> execucao),
carencia de convenio, gate de convenio/email na entrada da execucao.
"""

from app.er import processar_sub_rota_agenda


def _base(**overrides):
    b = {
        "coleta_horario": "",
        "coleta_data": "",
        "coleta_periodo": "",
        "coleta_unidade": "",
        "coleta_medico": "",
        "coleta_convenio": "",
        "cache_ativo": False,
        "ultimo_dia_exibido": None,
        "sessao_intencao": "navegacao",
        "sessao_rota": 4,
        "coleta_terceiro": "",
        "pacientes": [],
        "coleta_email": "",
        "data_minima_carencia": "",
        "data_minima_carencia_br": "",
        "texto_ia": "",
        "prox_seg": "",
        "_clear_pm": {},
        "_ultimo_convenio_global": "",
        "_pergunta_convenio_global": "A consulta será Particular ou Convênio? 😊",
    }
    b.update(overrides)
    return b


def _proc(texto, base=None, intencao_rapida="agenda", rota_agente=4, ia_output=None,
          eh_cancel_real=False, eh_pergunta_ver=False, eh_mensagem_informativa=False,
          all_coleta_confirmed=True, esta_em_agenda_ativa=True, sub_rota_agenda="navegacao"):
    return processar_sub_rota_agenda(
        base or _base(), texto, intencao_rapida, rota_agente, ia_output or {},
        eh_cancel_real, eh_pergunta_ver, eh_mensagem_informativa, all_coleta_confirmed,
        esta_em_agenda_ativa, sub_rota_agenda,
    )


# ---------- FIX_59204 / backtracking ----------

def test_horario_e_data_escolhidos_vira_confirmacao():
    b = _base(coleta_horario="14:00", coleta_data="2026-07-20")
    r = _proc("oi", base=b, sub_rota_agenda="navegacao")
    assert r.sub_rota_agenda == "confirmacao"


def test_backtracking_rejeita_horario_volta_navegacao():
    b = _base(coleta_data="2026-07-20", coleta_horario="14:00", coleta_periodo="tarde",
              coleta_unidade="Vila Olímpia", coleta_medico="Dr. X")
    r = _proc("outro horario, esse nao serve", base=b, sub_rota_agenda="confirmacao")
    assert r.sub_rota_agenda == "navegacao"
    assert r.base["coleta_data"] == ""
    assert r.base["coleta_horario"] == ""
    assert "VOLTA NAVEGACAO" in r.base["texto_ia"]


def test_backtracking_pede_outro_dia_calcula_proxima_data():
    b = _base(coleta_data="2026-07-20", coleta_horario="14:00", coleta_unidade="Vila Olímpia",
              coleta_medico="Dr. X")
    r = _proc("quero outro dia, esse nao serve", base=b, sub_rota_agenda="confirmacao")
    assert "OUTRO DIA APOS REJEICAO" in r.base["texto_ia"]
    assert "2026-07-21" in r.base["texto_ia"]


def test_backtracking_confirmacao_positiva_vira_execucao():
    b = _base(coleta_data="2026-07-20", coleta_horario="14:00")
    r = _proc("perfeito, pode confirmar", base=b, sub_rota_agenda="confirmacao")
    assert r.sub_rota_agenda == "execucao"


# ---------- FIX_PROCURAR_MAIS_FRENTE ----------

def test_procurar_mais_frente_com_cache_e_opcao_3():
    b = _base(coleta_medico="Dr. X", cache_ativo=True, ultimo_dia_exibido=None)
    r = _proc("3", base=b, sub_rota_agenda="navegacao")
    assert "PROCURAR MAIS PARA FRENTE" in r.base["texto_ia"]
    assert r.base["coleta_data"] != ""


# ---------- FIX_MAIS_HORARIO_MESMO_DIA ----------

def test_mais_horario_mesmo_dia_oferece_outro_dia():
    b = _base(ultimo_dia_exibido={"data": "2026-07-20", "medicos": [{"horarios": "14:00, 15:00"}]},
              coleta_periodo="tarde")
    r = _proc("tem mais horario?", base=b, sub_rota_agenda="navegacao")
    assert r.intencao_rapida == "oferecer_outro_dia"
    assert "MAIS HORARIO MESMO DIA" in r.base["texto_ia"]
    assert "20/07/2026" in r.base["texto_ia"]


# ---------- FIX_59198 ----------

def test_ver_outro_dia_afirmativa_navega():
    b = _base(cache_ativo=True, ultimo_dia_exibido={"data": "2026-07-20"}, coleta_horario="")
    r = _proc("sim quero outro", base=b)
    assert "VER OUTRO DIA CONFIRMADO" in r.base["texto_ia"]


def test_ver_outro_dia_negativa_fica_no_dia():
    b = _base(cache_ativo=True, coleta_horario="",
              ultimo_dia_exibido={"data": "2026-07-20", "medicos": [{"horarios": "14:00, 15:00"}]})
    r = _proc("nao", base=b)
    assert "FICAR NO DIA ATUAL" in r.base["texto_ia"]
    assert "14:00, 15:00" in r.base["texto_ia"]


# ---------- FIX_67635: desistencia ----------

def test_desistencia_forte_encerra_com_dica_tatuape():
    b = _base(coleta_unidade="Vila Olímpia", coleta_medico="", ultimo_dia_exibido=None)
    r = _proc("muito longe pra mim, obrigada", base=b)
    assert r.intencao_rapida == "concluido"
    assert "Tatuapé" in r.base["texto_ia"]
    assert "DESISTENCIA AGENDA" in r.base["texto_ia"]


def test_nenhum_serviu_com_lista_exibida_oferece_outro_dia():
    b = _base(coleta_medico="", cache_ativo=True, coleta_horario="",
              ultimo_dia_exibido={"data": "2026-07-20"})
    r = _proc("nenhum desses", base=b)
    assert r.intencao_rapida == "oferecer_outro_dia"
    assert "NENHUM HORARIO SERVIU" in r.base["texto_ia"]


# ---------- FIX_COLETA_PROTECTION ----------

def test_coleta_completa_com_convenio_na_msg_promove_navegacao():
    b = _base(sessao_intencao="coleta", coleta_medico="Dr. X", coleta_convenio="",
              coleta_unidade="Vila Olímpia", coleta_data="2026-07-20", coleta_periodo="tarde")
    r = _proc("quero usar porto seguro", base=b, all_coleta_confirmed=True, esta_em_agenda_ativa=False)
    assert r.intencao_rapida == "agenda"
    assert r.base["_sub_rota_agenda"] == "navegacao"
    assert r.base["coleta_convenio"] == "Porto Seguro"
    assert "CONVENIO CONFIRMADO" in r.base["texto_ia"]


def test_coleta_incompleta_mantem_no_agente_coleta():
    b = _base(sessao_intencao="coleta", coleta_medico="")
    r = _proc("oi", base=b, all_coleta_confirmed=False, esta_em_agenda_ativa=False)
    assert r.intencao_rapida == "coleta"
    assert r.rota_agente == 2


# ---------- FIX_67553: carencia ----------

def test_carencia_aceita_particular_mantem_data():
    b = _base(coleta_convenio="Omint", coleta_data="2026-07-10",
              data_minima_carencia="2026-07-29", data_minima_carencia_br="29/07/2026",
              _ultimo_convenio_global="Omint")
    r = _proc("quero manter particular", base=b, sub_rota_agenda="execucao",
              esta_em_agenda_ativa=False)
    assert r.base["coleta_convenio"] == "Particular"
    assert "CONVENIO PARTICULAR CONFIRMADO" in r.base["texto_ia"]


def test_carencia_pede_busca_a_partir_da_minima():
    b = _base(coleta_convenio="Omint", coleta_data="2026-07-10",
              data_minima_carencia="2026-07-29", data_minima_carencia_br="29/07/2026",
              _ultimo_convenio_global="Omint")
    r = _proc("pode buscar a partir dessa data", base=b, sub_rota_agenda="execucao",
              esta_em_agenda_ativa=False)
    assert r.rota_agente == 4
    assert r.base["_sub_rota_agenda"] == "navegacao"
    assert r.base["coleta_data"] == ""
    assert "CARENCIA BUSCAR" in r.base["texto_ia"]


def test_carencia_primeiro_turno_pergunta():
    b = _base(coleta_convenio="Omint", coleta_data="2026-07-10",
              data_minima_carencia="2026-07-29", data_minima_carencia_br="29/07/2026",
              _ultimo_convenio_global="Omint")
    r = _proc("ok", base=b, sub_rota_agenda="execucao", esta_em_agenda_ativa=False)
    assert "CARENCIA CONVENIO" in r.base["texto_ia"]
    assert "Quer que eu busque horários" in r.base["texto_ia"]


# ---------- FIX_66512: gate de convenio ----------

def test_gate_convenio_reusa_ultimo_convenio():
    b = _base(coleta_convenio="", sessao_intencao="execucao", _ultimo_convenio_global="Bradesco")
    r = _proc("sim, pode usar o mesmo", base=b, sub_rota_agenda="execucao", esta_em_agenda_ativa=False)
    assert r.base["coleta_convenio"] == "Bradesco"
    assert "CONVENIO RECEBIDO" in r.base["texto_ia"]


def test_gate_convenio_pergunta_personalizada_na_confirmacao():
    b = _base(coleta_convenio="", sessao_intencao="confirmacao",
              _pergunta_convenio_global="Sua última consulta foi como Bradesco. Deseja usar Bradesco novamente, ou prefere outra forma? 😊")
    r = _proc("ok", base=b, sub_rota_agenda="execucao", esta_em_agenda_ativa=False)
    assert "GATE CONVENIO" in r.base["texto_ia"]
    assert "Bradesco" in r.base["texto_ia"]


# ---------- FIX_59124: gate de email ----------

def test_gate_email_recebe_email_e_manda_criar():
    # coleta_convenio precisa estar preenchido: FIX_66512 (gate de convenio) roda ANTES do
    # gate de email e, com convenio vazio, consumiria o texto_ia_livre primeiro.
    b = _base(coleta_email="", coleta_convenio="Particular", pacientes=[{"nome": "X"}], coleta_terceiro="")
    r = _proc("meu email e joao@teste.com", base=b, sub_rota_agenda="execucao", esta_em_agenda_ativa=False)
    assert r.base["coleta_email"] == "joao@teste.com"
    assert "EMAIL RECEBIDO" in r.base["texto_ia"]


def test_gate_email_paciente_recusa_prossegue_sem_email():
    b = _base(coleta_email="", coleta_convenio="Particular", pacientes=[{"nome": "X"}])
    r = _proc("pular", base=b, sub_rota_agenda="execucao", esta_em_agenda_ativa=False)
    assert "SEM EMAIL" in r.base["texto_ia"]
    assert r.base["coleta_email"] == ""


def test_gate_email_primeiro_turno_pede_com_endereco():
    b = _base(coleta_email="", coleta_convenio="Particular", sessao_intencao="confirmacao",
              coleta_unidade="Vila Olímpia")
    r = _proc("correto, qual o endereco?", base=b, sub_rota_agenda="execucao", esta_em_agenda_ativa=False)
    assert "GATE EMAIL" in r.base["texto_ia"]
    assert "Rua Alvorada" in r.base["texto_ia"]
