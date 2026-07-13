"""
Testes da Parte 1 do port do ER (app/er.py) — setup + guards deterministicos de
transferencia humana + protecoes de contexto de sessao (linhas 1-736 do JS fonte).
"""

from app.er import processar_intake

WA_INFO = {"SenderAlt": "", "Chat": "5511999999999@s.whatsapp.net", "PushName": "Paciente Teste"}


def _base(**overrides):
    b = {
        "sessao_intencao": "",
        "sessao_rota": 0,
        "coleta_unidade": "",
        "coleta_data": "",
        "coleta_periodo": "",
        "coleta_medico": "",
        "coleta_terceiro": "",
        "nome_dependente": "",
        "cpf_dependente": "",
        "nascimento_dependente": "",
        "coleta_id_tisaude": "",
        "pacientes": [],
        "cpf": "",
        "id_tisaude": "",
        "nome": "",
        "hoje": "2026-07-12",
        "amanha": "2026-07-13",
        "cache_ativo": False,
        "ultimo_dia_exibido": "",
        "coleta_horario": "",
        "coleta_modo": 0,
        "coleta_convenio": "",
        "medico_candidato_msg": "",
        "motivo_humano": "",
        "texto_ia": "",
        "coleta_dia_semana": "",
    }
    b.update(overrides)
    return b


def _proc(texto, base=None, ia_output=None):
    return processar_intake(base or _base(), texto, {"output": "{}"} if ia_output is None else ia_output, WA_INFO)


# ---------- telefone / nome_titular ----------

def test_telefone_extraido():
    r = _proc("oi")
    assert r.telefone == "5511999999999"


def test_nome_titular_capitalizado():
    r = _proc("oi")
    assert r.base["nome_titular"] == "Paciente"


# ---------- FIX_CLEAR_DIA_COMO_MEDICO ----------

def test_dia_como_medico_e_limpo():
    r = _proc("terca", base=_base(coleta_medico="terca"))
    assert r.base["coleta_medico"] == ""


# ---------- FIX_TITULAR_ID_INJECT ----------

def test_titular_id_inject_recupera_dados():
    b = _base(coleta_id_tisaude="123", pacientes=[{"id_tisaude": "123", "nome": "MARIA SILVA", "cpf": "111", "nascimento": "01/01/1990"}])
    r = _proc("oi", base=b)
    assert r.base["nome_dependente"] == "MARIA SILVA"


# ---------- FIX_ENCAIXE ----------

def test_encaixe_vai_pra_humano():
    r = _proc("queria um encaixe pra hoje")
    assert r.intencao_rapida == "humano"
    assert r.rota_agente == 5
    assert r.motivo_humano == "Paciente pediu encaixe"
    assert "NAO diga que VOCE vai verificar" in r.base["texto_ia"]


# ---------- FIX_LISTA_ESPERA_ROBUSTA ----------

def test_lista_espera_vai_pra_humano():
    r = _proc("pode me avisar quando abrir uma vaga?")
    assert r.intencao_rapida == "humano"
    assert r.motivo_humano == "Paciente pediu lista de espera / aviso de vagas"


def test_desistencia_vai_pra_humano():
    r = _proc("tem lista de espera?")
    assert r.intencao_rapida == "humano"


# ---------- FIX_DOC_HUMANO ----------

def test_pedido_receita_vai_pra_humano():
    r = _proc("preciso de uma segunda via da receita")
    assert r.intencao_rapida == "humano"
    assert "Documento" in r.motivo_humano


# ---------- FIX_TELE_HUMANO ----------

def test_teleconsulta_vai_pra_humano():
    r = _proc("queria uma teleconsulta")
    assert r.intencao_rapida == "humano"
    assert r.motivo_humano == "Telemedicina"


def test_presencial_nao_dispara_tele_humano():
    r = _proc("prefiro presencial mesmo")
    assert r.intencao_rapida != "humano"


# ---------- FIX_REEMBOLSO_HUMANO ----------

def test_reembolso_vai_pra_humano():
    r = _proc("como faço para pedir reembolso?")
    assert r.intencao_rapida == "humano"
    assert r.motivo_humano == "Reembolso/nota fiscal"


# ---------- FIX_REMARCA_MULTI ----------

def test_remarcar_consulta_da_esposa_vai_pra_humano():
    r = _proc("queria remarcar a consulta da minha esposa")
    assert r.intencao_rapida == "humano"
    assert r.motivo_humano == "Remarcacao multipla/terceiro"


def test_remarcar_propria_consulta_nao_vai_pra_humano():
    r = _proc("queria remarcar minha consulta")  # sessao fresca (triagem/rota 0)
    assert r.intencao_rapida == "remarcando"


# ---------- FIX_65739 agendamento multiplo ----------

def test_dois_cpfs_em_coleta_vai_pra_humano():
    b = _base(sessao_rota=2)
    r = _proc("111.444.777-35 e 222.555.888-96", base=b)
    assert r.intencao_rapida == "humano"
    assert r.motivo_humano == "Agendamento multiplo (2+ pacientes)"


# ---------- FIX_CANCELAR_LEMBRETE ----------

def test_cancelar_isolado_em_sessao_ociosa():
    r = _proc("cancelar")
    assert r.intencao_rapida == "cancelando"
    assert r.rota_agente == 1


# ---------- FIX_CONV_RECUSADO_TRIAGEM ----------

def test_amil_transfere_direto_sem_oferta_particular():
    r = _proc("eu tenho amil")
    assert r.intencao_rapida == "humano"
    assert "Amil" in r.motivo_humano
    assert "PART?" not in (r.base.get("coleta_convenio") or "")


def test_unimed_oferece_particular():
    r = _proc("tenho unimed")
    assert r.base["coleta_convenio"] == "PART?"
    assert r.intencao_rapida != "humano"


# ---------- FIX_TRIAGEM_MENU_GUARD ----------

def test_opcao_menu_invalida_repete_menu():
    b = _base(sessao_intencao="triagem")
    r = _proc("9", base=b)
    assert "OPCAO INVALIDA TRIAGEM" in r.base["texto_ia"]


def test_opcao_menu_valida_nao_repete():
    b = _base(sessao_intencao="triagem")
    r = _proc("1", base=b)
    assert "OPCAO INVALIDA TRIAGEM" not in r.base["texto_ia"]


# ---------- FIX_VER_ESCOLHER_TITULAR ----------

def test_ver_escolher_titular_numero_valido():
    b = _base(sessao_intencao="ver_escolher", pacientes=[{"nome": "JOAO", "id_tisaude": "1"}, {"nome": "MARIA", "id_tisaude": "2"}])
    r = _proc("2", base=b)
    assert r.intencao_rapida == "ver"
    assert "MARIA" in r.base["texto_ia"]


def test_ver_escolher_titular_numero_invalido():
    b = _base(sessao_intencao="ver_escolher", pacientes=[{"nome": "JOAO", "id_tisaude": "1"}])
    r = _proc("9", base=b)
    assert r.intencao_rapida == "ver_escolher"


def test_ver_escolher_titular_invalido_ecoa_mensagem_original():
    # JS: '"] ' + textoUsuario — o port tinha cortado esse eco (achado em replay contra tráfego
    # real, exec 68907).
    b = _base(sessao_intencao="ver_escolher", pacientes=[{"nome": "JOAO"}, {"nome": "MARIA"}])
    r = _proc("quero saber o horário do número 2", base=b)
    assert r.base["texto_ia"].endswith("quero saber o horário do número 2")


# ---------- HORARIO AMBIGUO ----------

def test_horario_solto_sem_contexto():
    r = _proc("15h")
    assert "HORARIO AMBIGUO" in r.base["texto_ia"]


# ---------- FIX_STEPHANIE_TELE ----------

def test_stephanie_segunda_manha_vai_pra_humano():
    # coleta_dia_semana em vez de coleta_data: evita colidir com a PROTEÇÃO COLETA
    # INCOMPLETA (linha 407 do JS), que não checa texto_ia e roda logo depois — ver nota
    # sobre a colisão STEPHANIE_TELE x PROTEÇÃO COLETA INCOMPLETA reportada ao Lucas.
    b = _base(coleta_medico="Dra. Stephanie Rugeri de Souza", coleta_unidade="Vila Olímpia",
              coleta_dia_semana="segunda")
    r = _proc("confirma de manha", base=b)
    assert r.intencao_rapida == "humano"
    assert r.motivo_humano == "Teleconsulta Dra. Stephanie"


def test_stephanie_segunda_tarde_nao_vai_pra_humano():
    b = _base(coleta_medico="Dra. Stephanie Rugeri de Souza", coleta_unidade="Vila Olímpia",
              coleta_dia_semana="segunda")
    r = _proc("confirma de tarde", base=b)
    assert r.intencao_rapida != "humano"


def test_stephanie_tatuape_nao_dispara():
    b = _base(coleta_medico="Dra. Stephanie Rugeri de Souza", coleta_unidade="Tatuapé",
              coleta_dia_semana="segunda")
    r = _proc("confirma de manha", base=b)
    assert r.intencao_rapida != "humano"


# ---------- PROTEÇÃO: fluxo de agenda ativo preserva contexto ----------

def test_sessao_agenda_ativa_preserva_contexto_quando_ia_volta_triagem():
    b = _base(sessao_intencao="agenda", sessao_rota=2)
    r = _proc("ok", base=b, ia_output={"output": '{"intencao_rapida":"triagem","rota_agente":0}'})
    assert r.intencao_rapida == "agenda"
    assert r.rota_agente == 2


# ---------- PROTEÇÃO COLETA INCOMPLETA/INTERROMPIDA ----------

def test_coleta_incompleta_forca_rota_agenda():
    b = _base(coleta_unidade="Vila Olímpia", coleta_data="2026-07-20", coleta_periodo="tarde")
    r = _proc("oi", base=b)
    assert r.rota_agente == 2
    assert r.intencao_rapida == "agenda"


# ---------- FIX_TRIAGEM_HANDOFF_COLETA ----------

def test_triagem_handoff_coleta_inicia_agenda():
    b = _base(sessao_intencao="coleta", sessao_rota=0)
    r = _proc("pode ser", base=b)
    assert r.rota_agente == 2
    assert r.intencao_rapida == "coleta"
    assert "INICIO AGENDA" in r.base["texto_ia"]
