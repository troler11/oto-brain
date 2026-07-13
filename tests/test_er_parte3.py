"""
Testes da Parte 3 do port do ER (app/er.py::processar_convenio_menu_agenda) — linhas
1092-1613 do JS fonte: convenio Omint, particular, menu principal, confirmar presenca,
atraso, ofertas pendentes, promocao pra rota=4, backstop de identidade.
"""

from app.er import _to_int_or_none, processar_convenio_menu_agenda


def _base(**overrides):
    b = {
        "coleta_convenio": "",
        "coleta_medico": "",
        "coleta_unidade": "",
        "coleta_data": "",
        "coleta_periodo": "",
        "coleta_modo": 0,
        "sessao_intencao": "",
        "sessao_rota": 0,
        "pacientes": [],
        "coleta_conv_fail": 0,
        "coleta_id_agendamento": "",
        "cpf_dependente": "",
        "nome_dependente": "",
        "nascimento_dependente": "",
        "coleta_terceiro": "",
        "paciente_encontrado": False,
        "coleta_id_tisaude": "",
        "nome": "",
        "id_tisaude": "",
        "texto_ia": "",
    }
    b.update(overrides)
    return b


def _proc(texto, base=None, intencao_rapida="triagem", rota_agente=0, ia_output=None,
          eh_cancel_real=False, eh_sessao_nova=True, menu_opt=None, ia_rota_original=0,
          eh_mensagem_informativa=False):
    return processar_convenio_menu_agenda(
        base or _base(), texto, intencao_rapida, rota_agente, ia_output or {},
        eh_cancel_real, eh_sessao_nova, menu_opt if menu_opt is not None else texto.strip(),
        ia_rota_original, None, eh_mensagem_informativa,
    )


# ---------- _to_int_or_none (parseInt do JS, achado em replay contra tráfego real) ----------

def test_to_int_or_none_leading_digit_ignora_lixo():
    assert _to_int_or_none("1,23") == 1


def test_to_int_or_none_espacos_e_quebra_de_linha():
    assert _to_int_or_none("1  \n2") == 1


def test_to_int_or_none_sem_digito_lider_none():
    assert _to_int_or_none("quero 2") is None


def test_to_int_or_none_vazio_none():
    assert _to_int_or_none("") is None


# ---------- FIX_OMINT_V2 ----------

def test_omint_premium_medico_valido_confirma():
    # eh_sessao_nova=False: mid-fluxo real (sessao_intencao seria 'coleta'/'agenda', nao
    # 'triagem') -- com eh_sessao_nova=True o MENU PRINCIPAL (que nao tem gate de texto_ia)
    # atropela a resposta do OMINT quando opt=='1'.
    b = _base(coleta_convenio="OMINT?", coleta_medico="Dra. Giseli Rebechi", sessao_rota=2)
    r = _proc("1", base=b, rota_agente=2, eh_sessao_nova=False)
    assert r.base["coleta_convenio"] == "Omint Premium"
    assert "OMINT PREMIUM OK" in r.base["texto_ia"]


def test_omint_premium_medico_invalido_limpa_e_pergunta():
    b = _base(coleta_convenio="OMINT?", coleta_medico="Dra. Stephanie Rugeri de Souza", sessao_rota=2)
    r = _proc("1", base=b, rota_agente=2, eh_sessao_nova=False)
    assert r.base["coleta_medico"] == ""
    assert "Dra. Giseli" in r.base["texto_ia"]


def test_omint_skill_tatuape_pede_troca_unidade():
    b = _base(coleta_convenio="OMINT?", coleta_unidade="Tatuapé", sessao_rota=2)
    r = _proc("2", base=b, rota_agente=2, eh_sessao_nova=False)
    assert r.base["coleta_convenio"] == "Omint Skill"
    assert "SOMENTE na Vila Olimpia" in r.base["texto_ia"]


def test_omint_corporation_fora_tatuape_arma_torcuato():
    b = _base(coleta_convenio="OMINT?", coleta_unidade="", sessao_rota=2)
    r = _proc("3", base=b, rota_agente=2, eh_sessao_nova=False)
    assert r.base["coleta_unidade"] == "Vila Olímpia"
    assert r.base["coleta_medico"] == "Dr. Torcuato Sanchez Rojas Neto"


def test_omint_nao_sabe_categoria_vai_pra_humano():
    b = _base(coleta_convenio="OMINT?", sessao_rota=2)
    r = _proc("nao sei", base=b, rota_agente=2, eh_sessao_nova=False)
    assert r.intencao_rapida == "humano"
    assert "Omint" in r.motivo_humano


def test_omint_skill_tatuape_aceita_trocar():
    b = _base(coleta_convenio="Omint Skill", coleta_unidade="Tatuapé", sessao_rota=2)
    r = _proc("sim", base=b, rota_agente=2, eh_sessao_nova=False)
    assert r.base["coleta_unidade"] == "Vila Olímpia"
    assert "TROCA UNIDADE OMINT" in r.base["texto_ia"]


def test_omint_skill_tatuape_recusa_trocar_vai_pra_humano():
    b = _base(coleta_convenio="Omint Skill", coleta_unidade="Tatuapé", sessao_rota=2)
    r = _proc("nao", base=b, rota_agente=2, eh_sessao_nova=False)
    assert r.intencao_rapida == "humano"


# ---------- FIX_PARTICULAR_BLOQUEADO / FIX_PARTICULAR_PRECO ----------

def test_particular_bloqueado_convenio_restrito():
    b = _base(coleta_convenio="Bradesco")
    r = _proc("quero particular", base=b)
    assert r.intencao_rapida == "humano"
    assert "Bradesco" in r.motivo_humano


def test_particular_preco_sem_convenio_mostra_precos():
    b = _base(coleta_convenio="", sessao_rota=2)
    r = _proc("quero particular", base=b, rota_agente=2)
    assert "PARTICULAR PRECO" in r.base["texto_ia"]
    assert "600,00" in r.base["texto_ia"]


def test_particular_preco_mensagem_informativa_nao_dispara_guard():
    # Achado em replay contra tráfego real (exec 68015): "gostaria de saber o valor, no caso
    # seria particular" é pergunta informativa — quem deve responder é o FAQ tag=PART, não esse
    # guard (que assume o paciente ESCOLHEU particular, não está só perguntando o preço).
    b = _base(coleta_convenio="", sessao_rota=2)
    r = _proc("mas antes gostaria de saber o valor, no caso seria particular", base=b, rota_agente=2,
              eh_mensagem_informativa=True)
    assert "PARTICULAR PRECO" not in r.base["texto_ia"]


# ---------- MENU PRINCIPAL ----------

def test_menu_opcao_1_pergunta_para_quem():
    b = _base(sessao_intencao="triagem")
    r = _proc("1", base=b)
    assert r.rota_agente == 2
    assert r.intencao_rapida == "coleta"
    assert "para você ou para outra pessoa" in r.base["texto_ia"]


def test_menu_opcao_4_paciente_unico_vai_direto():
    b = _base(sessao_intencao="triagem", pacientes=[{"nome": "ANA", "id_tisaude": "1"}])
    r = _proc("4", base=b)
    assert r.intencao_rapida == "ver"
    assert "VER CONSULTAS" in r.base["texto_ia"]


def test_menu_opcao_4_multi_paciente_pede_escolha():
    b = _base(sessao_intencao="triagem", pacientes=[{"nome": "ANA"}, {"nome": "BIA"}])
    r = _proc("4", base=b)
    assert r.intencao_rapida == "ver_escolher"


def test_menu_opcao_6_confirmar_presenca_direto():
    b = _base(sessao_intencao="triagem", pacientes=[{"nome": "ANA", "id_tisaude": "1"}])
    r = _proc("6", base=b)
    assert r.intencao_rapida == "confirmar_presenca"
    assert r.base["_sub_confirmar"] == "verificar"
    assert r.base.get("_confirma_direto") is True


# ---------- FIX_VER_FRASE_LIVRE ----------

def test_frase_livre_esqueci_data_ativa_ver():
    b = _base(sessao_intencao="triagem", pacientes=[{"nome": "ANA"}])
    r = _proc("esqueci a data da minha consulta", base=b)
    assert r.intencao_rapida == "ver"
    assert "VER CONSULTAS" in r.base["texto_ia"]


# ---------- FIX_CONFIRMAR_PRESENCA_ESCOLHER ----------

def test_confirmar_presenca_escolher_numero_valido():
    b = _base(sessao_intencao="confirmar_presenca_escolher",
              pacientes=[{"nome": "A", "id_tisaude": "1", "cpf": "111"}, {"nome": "B", "id_tisaude": "2", "cpf": "222"}])
    r = _proc("2", base=b, eh_sessao_nova=False)
    assert r.rota_agente == 5
    assert r.intencao_rapida == "confirmar_presenca"
    assert r.base["nome_dependente"] == "B"


def test_confirmar_presenca_escolher_numero_com_lixo_apos_virgula():
    # Achado em replay contra tráfego real (exec 68785): paciente respondeu "1,23" — JS
    # parseInt lê o "1" líder e ignora o resto; _to_int_or_none precisa fazer o mesmo.
    b = _base(sessao_intencao="confirmar_presenca_escolher",
              pacientes=[{"nome": "A", "id_tisaude": "1", "cpf": "111"}, {"nome": "B", "id_tisaude": "2", "cpf": "222"}])
    r = _proc("1,23", base=b, eh_sessao_nova=False)
    assert r.rota_agente == 5
    assert r.intencao_rapida == "confirmar_presenca"
    assert r.base["nome_dependente"] == "A"


def test_confirmar_presenca_escolher_numero_com_quebra_de_linha():
    # exec 68992: "1  \n2" — mesmo padrão, lixo depois do dígito líder.
    b = _base(sessao_intencao="confirmar_presenca_escolher",
              pacientes=[{"nome": "A", "id_tisaude": "1", "cpf": "111"}, {"nome": "B", "id_tisaude": "2", "cpf": "222"}])
    r = _proc("1  \n2", base=b, eh_sessao_nova=False)
    assert r.intencao_rapida == "confirmar_presenca"
    assert r.base["nome_dependente"] == "A"


def test_confirmar_presenca_escolher_loop_guard_vai_pra_humano():
    # "5" fora do range (so 1 titular): nao casa a recusa nem um numero valido, cai no
    # loop-guard. Texto com "nao" (ex: "nao entendi") seria lido como RECUSA antes do guard.
    b = _base(sessao_intencao="confirmar_presenca_escolher", pacientes=[{"nome": "A"}], coleta_conv_fail=2)
    r = _proc("5", base=b, eh_sessao_nova=False)
    assert r.intencao_rapida == "humano"


# ---------- FIX_CONFIRMAR_PRESENCA (turno 2) ----------

def test_confirmar_presenca_sim_com_id_executa_direto():
    b = _base(sessao_intencao="confirmar_presenca", coleta_id_agendamento="999")
    r = _proc("sim", base=b, eh_sessao_nova=False)
    assert r.base["_sub_confirmar"] == "executar"
    assert r.rota_agente == 5


def test_confirmar_presenca_nao_pede_cancelar_ou_remarcar():
    b = _base(sessao_intencao="confirmar_presenca")
    r = _proc("nao quero", base=b, eh_sessao_nova=False)
    assert r.intencao_rapida == "confirmar_presenca_recusou"


# ---------- FIX_CONFIRMAR_PRESENCA_RECUSOU ----------

def test_confirmar_presenca_recusou_quer_cancelar():
    b = _base(sessao_intencao="confirmar_presenca_recusou")
    r = _proc("quero cancelar", base=b, eh_sessao_nova=False)
    assert r.intencao_rapida == "cancelando"
    assert r.rota_agente == 1


# ---------- FIX_ATRASO_HUMANO ----------

def test_atraso_sempre_transfere_independente_do_contexto():
    b = _base(sessao_intencao="agenda")
    r = _proc("vou chegar atrasado, desculpa", base=b, eh_sessao_nova=False, rota_agente=2)
    assert "vai se atrasar" in r.base["texto_ia"]
    assert r.motivo_humano == "Paciente avisou que vai se atrasar para a consulta"


# ---------- FIX_67529 / FIX_CONFIRMA_HUMANO ----------

def test_oferta_agendar_sim_inicia_coleta():
    b = _base(sessao_intencao="oferta_agendar")
    r = _proc("sim", base=b, eh_sessao_nova=False)
    assert r.rota_agente == 2
    assert r.intencao_rapida == "coleta"


def test_oferta_humano_sim_transfere():
    b = _base(sessao_intencao="oferta_humano")
    r = _proc("sim", base=b, eh_sessao_nova=False)
    assert r.intencao_rapida == "humano"
    assert "Duvida" in r.motivo_humano


# ---------- ROTA 4 / PROTEÇÃO COLETA AGENDA / FIX_IDENTIDADE_0PAC ----------

def test_promove_rota4_quando_coleta_completa():
    b = _base(coleta_convenio="Particular", coleta_data="2026-07-20", coleta_unidade="Vila Olímpia",
              coleta_periodo="tarde", paciente_encontrado=True)
    r = _proc("ok", base=b, rota_agente=2, eh_sessao_nova=False)
    assert r.rota_agente == 4


def test_downgrade_rota4_sem_coleta_completa():
    b = _base(coleta_convenio="", coleta_data="", coleta_unidade="", coleta_periodo="")
    r = _proc("ok", base=b, rota_agente=4, eh_sessao_nova=False)
    assert r.rota_agente == 2


def test_identidade_incompleta_bloqueia_rota4():
    b = _base(coleta_convenio="Particular", coleta_data="2026-07-20", coleta_unidade="Vila Olímpia",
              coleta_periodo="tarde", paciente_encontrado=False, nome_dependente="")
    r = _proc("ok", base=b, rota_agente=2, eh_sessao_nova=False)
    assert r.rota_agente in (2, 3)
    assert "IDENTIDADE OBRIGATORIA" in r.base["texto_ia"]


# ---------- FIX_OUTRO_DIA_BREADCRUMB ----------

def test_outro_dia_confirmado_navega():
    b = _base(sessao_intencao="oferecer_outro_dia")
    r = _proc("sim quero ver outro", base=b, eh_sessao_nova=False)
    assert r.base["sessao_intencao"] == "navegacao"
    assert "VER OUTRO DIA CONFIRMADO" in r.base["texto_ia"]
