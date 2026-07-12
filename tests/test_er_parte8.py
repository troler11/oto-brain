"""
Testes da Parte 8 do port do ER (app/er.py::processar_menu_unidade_medico) — linhas
3056-3469 do JS fonte: menu "sem vagas" (3 opções + detecção de dia no catch-all),
pré-computo determinístico de data/horário a partir de números soltos, FIX_P1_TERCEIRO,
menu de unidade (via "1"/"2" ou texto livre), limpeza de resíduo zumbi terceiro==titular,
FIX_MESMO_MEDICO_SIM.
"""

from app.er import processar_menu_unidade_medico


def _base(**overrides):
    b = {
        "ultimo_dia_exibido": None,
        "cache_ativo": False,
        "_sub_rota_agenda": "",
        "coleta_horario": "",
        "coleta_medico": "",
        "coleta_dia_semana": "",
        "coleta_data": "",
        "coleta_terceiro": "",
        "texto_ia": "",
        "grade_med": "",
        "coleta_unidade": "",
        "coleta_modo": 0,
        "coleta_periodo": "",
        "sessao_intencao": "navegacao",
        "sessao_rota": 0,
        "nome_dependente": "",
        "pacientes": [],
        "cpf_dependente": "",
        "nascimento_dependente": "",
        "coleta_id_tisaude": "",
        "_ultimo_medico_global": "",
        "_periodo_precomputed": False,
        "_clear_pm": {},
        "hoje": "",
    }
    b.update(overrides)
    return b


def _proc(texto, base=None, intencao_rapida="agenda", rota_agente=4, ia_output=None,
          eh_cancel_real=False, esta_em_agenda_ativa=True):
    io = ia_output if ia_output is not None else {}
    r = processar_menu_unidade_medico(
        base or _base(), texto, intencao_rapida, rota_agente, io, eh_cancel_real, esta_em_agenda_ativa,
    )
    return r, io


# ---------- FIX_NAV_MENU_OPTIONS ----------

def test_menu_sem_vagas_opcao_1_limpa_medico():
    b = _base(_sub_rota_agenda="navegacao", cache_ativo=True, coleta_terceiro="")
    r, io = _proc("1", base=b, rota_agente=4)
    assert r.base["coleta_medico"] == "__CLEAR__"
    assert r.base["coleta_data"] == ""
    assert r.rota_agente == 2
    assert "TROCAR MEDICO MENU" in r.base["texto_ia"]


def test_menu_sem_vagas_opcao_2_mostra_grade_do_medico():
    b = _base(
        _sub_rota_agenda="navegacao", cache_ativo=True, coleta_medico="Dra. Giseli Rebechi",
        grade_med='GISELI: "terça, quarta e sexta de manhã"',
    )
    r, io = _proc("2", base=b, rota_agente=4)
    assert "VER OUTROS DIAS" in r.base["texto_ia"]
    assert "terça, quarta e sexta de manhã" in r.base["texto_ia"]


def test_menu_sem_vagas_opcao_3_procurar_adiante():
    b = _base(_sub_rota_agenda="navegacao", cache_ativo=True)
    r, io = _proc("3", base=b, rota_agente=4)
    assert "PROCURAR ADIANTE" in r.base["texto_ia"]


def test_menu_sem_vagas_catchall_dia_valido_seleciona():
    b = _base(
        _sub_rota_agenda="navegacao", cache_ativo=True,
        coleta_medico="Dr. Elias Lobo Braga", coleta_unidade="Vila Olímpia",
    )
    r, io = _proc("quarta", base=b, rota_agente=4)
    assert "DIA SELECIONADO" in r.base["texto_ia"]
    assert r.base["coleta_dia_semana"] == "quarta"


def test_menu_sem_vagas_catchall_texto_invalido_repete_menu():
    b = _base(_sub_rota_agenda="navegacao", cache_ativo=True, coleta_medico="Dr. Elias Lobo Braga")
    r, io = _proc("oi", base=b, rota_agente=4)
    assert "OPCAO INVALIDA" in r.base["texto_ia"]


# ---------- FIX_NUMERO_PRECOMPUTE ----------

def test_precompute_dia_n_no_futuro_mesmo_mes():
    b = _base(texto_ia="dia 20", coleta_medico="Dr. X")
    r, io = _proc("dia 20", base=b, rota_agente=4)
    assert r.base["eh_troca_data"] is True
    assert r.base["data_alvo_troca"] == "2026-07-20"


def test_precompute_data_br_passada_rola_pro_proximo_ano():
    b = _base(texto_ia="pode ser 05/07", coleta_medico="Dr. X")
    r, io = _proc("pode ser 05/07", base=b, rota_agente=4)
    assert r.base["eh_troca_data"] is True
    assert r.base["data_alvo_troca"] == "2027-07-05"


def test_precompute_hhmm_vira_horario_provavel():
    b = _base(texto_ia="0820")
    r, io = _proc("0820", base=b, rota_agente=4, esta_em_agenda_ativa=True, eh_cancel_real=False)
    assert "HORARIO PROVAVEL" in r.base["texto_ia"]
    assert "08:20" in r.base["texto_ia"]


def test_precompute_numero_bare_1a4_sem_cache_vira_numero_em_agenda():
    b = _base(texto_ia="3", cache_ativo=False)
    r, io = _proc("3", base=b, rota_agente=4)
    assert "NUMERO EM AGENDA" in r.base["texto_ia"]
    assert "2026-08-03" in r.base["texto_ia"]


def test_precompute_numero_fora_clinica_vira_troca_data():
    b = _base(texto_ia="20", coleta_medico="Dr. X")
    r, io = _proc("20", base=b, rota_agente=4)
    assert r.base["eh_troca_data"] is True
    assert r.base["data_alvo_troca"] == "2026-07-20"


def test_precompute_numero_ambiguo_sem_data_ja_definida():
    b = _base(texto_ia="10", coleta_periodo="manha", sessao_intencao="navegacao")
    r, io = _proc("10", base=b, rota_agente=4)
    assert "NUMERO AMBIGUO" in r.base["texto_ia"]


def test_precompute_numero_com_data_definida_vira_horario():
    b = _base(texto_ia="10", coleta_periodo="manha", sessao_intencao="agenda",
              coleta_data="2026-07-20", coleta_horario="")
    r, io = _proc("10", base=b, rota_agente=4)
    assert "HORARIO PROVAVEL" in r.base["texto_ia"]
    assert "10:00" in r.base["texto_ia"]


# ---------- FIX_P1_TERCEIRO ----------

def test_p1_terceiro_nome_nao_cadastrado_forca_rota3():
    b = _base(sessao_intencao="coleta", pacientes=[{"nome": "Maria Silva"}])
    r, io = _proc("roberto", base=b, rota_agente=2)
    assert r.rota_agente == 3
    assert io.get("rota_agente") == 3
    assert r.intencao_rapida == "coleta"
    assert r.base["coleta_terceiro"] == "true"
    assert "TERCEIRO CONFIRMADO" in r.base["texto_ia"]


def test_p1_nome_cadastrado_nao_dispara():
    b = _base(sessao_intencao="coleta", pacientes=[{"nome": "Maria Silva"}])
    r, io = _proc("maria", base=b, rota_agente=2)
    assert r.rota_agente == 2
    assert r.base["texto_ia"] == ""


# ---------- FIX_P3_MENU_GUARD ----------

def test_p3_menu_guard_medico_ja_escolhido_com_grade():
    b = _base(nome_dependente="Roberto", coleta_medico="Dra. Giseli Rebechi")
    r, io = _proc("1", base=b, rota_agente=2)
    assert r.base["coleta_unidade"] == "Vila Olímpia"
    assert "MEDICO JA ESCOLHIDO" in r.base["texto_ia"]


def test_p3_menu_guard_medico_nao_atende_na_unidade():
    b = _base(nome_dependente="Roberto", coleta_medico="Dra. Juliana Paulino do Amaral")
    r, io = _proc("2", base=b, rota_agente=2)
    assert r.base["coleta_medico"] == ""
    assert r.base["coleta_modo"] == 0
    assert "NAO atende nessa" in r.base["texto_ia"]


def test_p3_menu_guard_ultimo_medico_oferecido():
    b = _base(nome_dependente="Roberto", coleta_medico="", _ultimo_medico_global="Dr. Elias Lobo Braga")
    r, io = _proc("1", base=b, rota_agente=2)
    assert "P3 ULTIMO MEDICO" in r.base["texto_ia"]
    assert "Elias" in r.base["texto_ia"]


def test_p3_menu_guard_default_menu_generico():
    b = _base(nome_dependente="Roberto", coleta_medico="", _ultimo_medico_global="")
    r, io = _proc("1", base=b, rota_agente=2)
    assert "escolha da UNIDADE" in r.base["texto_ia"]


# ---------- FIX_58755: residual zumbi ----------

def test_zumbi_cpf_igual_titular_limpa_terceiro():
    b = _base(
        coleta_terceiro="true", cpf_dependente="11122233344", coleta_unidade="Vila Olímpia",
        pacientes=[{"cpf": "11122233344", "id_tisaude": "5"}],
    )
    r, io = _proc("oi", base=b, rota_agente=1)
    assert r.base["nome_dependente"] == ""
    assert r.base["cpf_dependente"] == ""
    assert r.base["nascimento_dependente"] == ""
    assert r.base["_clear_pm"]["c"] == 1
    assert "id" not in r.base["_clear_pm"]


# ---------- FIX_UNIDADE_TEXTO_OU_INVALIDA ----------

def test_unidade_texto_livre_reconhece_tatuape():
    b = _base(sessao_intencao="coleta", nome_dependente="Roberto", coleta_id_tisaude="123")
    r, io = _proc("tatuape", base=b, rota_agente=2)
    assert r.base["coleta_unidade"] == "Tatuapé"
    assert "P3 MENU OBRIGATORIO" in r.base["texto_ia"]


def test_unidade_texto_invalido():
    b = _base(sessao_intencao="coleta", nome_dependente="Roberto", coleta_id_tisaude="123")
    r, io = _proc("banana", base=b, rota_agente=2)
    assert "UNIDADE INVALIDA" in r.base["texto_ia"]


# ---------- FIX_MESMO_MEDICO_SIM ----------

def test_mesmo_medico_sim_confirma():
    b = _base(coleta_unidade="Vila Olímpia", coleta_medico="", _ultimo_medico_global="Dr. Elias Lobo Braga")
    r, io = _proc("sim", base=b, rota_agente=2)
    assert r.base["coleta_medico"] == "Dr. Elias Lobo Braga"
    assert r.base["coleta_modo"] == 2
    assert "MESMO MEDICO CONFIRMADO" in r.base["texto_ia"]


def test_mesmo_medico_nao_oferece_menu():
    b = _base(coleta_unidade="Vila Olímpia", coleta_medico="", _ultimo_medico_global="Dr. Elias Lobo Braga")
    r, io = _proc("nao", base=b, rota_agente=2)
    assert "NAO quer o medico anterior" in r.base["texto_ia"]
