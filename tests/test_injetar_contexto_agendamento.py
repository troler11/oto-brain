"""
Testes do port de Injetar Contexto Agendamento (app/injetar_contexto_agendamento.py::processar)
— DEPLOY/_proposed_Injetar_Contexto_Agendamento.js, 315 linhas.
"""

from app.injetar_contexto_agendamento import processar

UDI_VO = {
    "data": "2026-07-14",
    "medicos": [
        {"medico": "Giseli Rebechi", "horarios": "09:00, 10:00", "idLocal": 1, "idCalendar": 11},
        {"medico": "Elias Lobo Braga", "horarios": "10:00, 14:00", "idLocal": 2, "idCalendar": 22},
    ],
}


def _base(**overrides):
    b = {
        "texto_ia": "",
        "ultimo_dia_exibido": None,
        "coleta_medico": "",
        "coleta_horario": "",
        "coleta_data": "",
        "eh_confirmacao": False,
        "pacientes": [],
        "coleta_id_tisaude": "",
        "nome_dependente": "",
        "coleta_terceiro": "",
        "coleta_email": "",
        "ultimo_dia_texto": "",
    }
    b.update(overrides)
    return b


# ---------- guard 0: sem ultimo_dia_exibido ----------

def test_sem_udi_marca_nao_confirmacao():
    r = processar(_base(ultimo_dia_exibido=None))
    assert r["eh_confirmacao"] is False


def test_udi_sem_data_marca_nao_confirmacao():
    r = processar(_base(ultimo_dia_exibido={"medicos": []}))
    assert r["eh_confirmacao"] is False


# ---------- "sim" positivo confirmando slot pendente ----------

def test_sim_positivo_com_email_cadastrado_chama_tool_direto():
    r = processar(_base(
        texto_ia="sim", ultimo_dia_exibido=UDI_VO, eh_confirmacao=True,
        coleta_id_tisaude="1", pacientes=[{"id_tisaude": "1", "email": "lucas@x.com"}],
    ))
    assert "[EMAIL JA CADASTRADO]" in r["texto_ia"]
    assert "lucas@x.com" in r["texto_ia"]
    assert r["medico_agendamento"] == "Giseli Rebechi"
    assert r["data_agendamento"] == "2026-07-14"


def test_sim_positivo_sem_email_pede_email():
    r = processar(_base(texto_ia="sim", ultimo_dia_exibido=UDI_VO, eh_confirmacao=True))
    assert "Qual seu email para confirmação?" in r["texto_ia"]
    assert "[EMAIL JA CADASTRADO]" not in r["texto_ia"]


def test_sim_positivo_resolve_medico_salvo():
    r = processar(_base(
        texto_ia="ok", ultimo_dia_exibido=UDI_VO, eh_confirmacao=True, coleta_medico="Elias Lobo Braga",
    ))
    assert r["medico_agendamento"] == "Elias Lobo Braga"


def test_sim_positivo_usa_horario_salvo_quando_presente():
    r = processar(_base(
        texto_ia="confirmo", ultimo_dia_exibido=UDI_VO, eh_confirmacao=True, coleta_horario="14:00",
    ))
    assert r["hora_agendamento"] == "14:00"


def test_nao_e_confirmacao_pendente_nao_dispara_branch_sim():
    r = processar(_base(texto_ia="sim", ultimo_dia_exibido=UDI_VO, eh_confirmacao=False))
    # cai na resolução principal (fallback pro primeiro médico), não no branch "sim positivo"
    assert "CONFIRMAÇÃO PENDENTE" in r["texto_ia"] or "[EMAIL" in r["texto_ia"]


# ---------- resposta ao pedido de email ----------

def test_resposta_com_email_valido():
    r = processar(_base(
        texto_ia="lucas@exemplo.com", ultimo_dia_exibido=UDI_VO,
        coleta_horario="09:00", coleta_data="2026-07-14",
    ))
    assert "[EMAIL RECEBIDO]" in r["texto_ia"]
    assert 'email: "lucas@exemplo.com"' in r["texto_ia"]


def test_resposta_sem_email_nao_tenho():
    r = processar(_base(
        texto_ia="nao tenho", ultimo_dia_exibido=UDI_VO,
        coleta_horario="09:00", coleta_data="2026-07-14",
    ))
    assert "[EMAIL RECEBIDO]" in r["texto_ia"]
    assert 'email: ""' in r["texto_ia"]


def test_sem_coleta_horario_nao_dispara_branch_email():
    r = processar(_base(texto_ia="nao tenho", ultimo_dia_exibido=UDI_VO, coleta_horario="", coleta_data="2026-07-14"))
    assert "[EMAIL RECEBIDO]" not in r["texto_ia"]


# ---------- desambiguação por nome (hora ambígua) ----------

def test_desambiguacao_por_nome_quando_hora_ambigua():
    r = processar(_base(texto_ia="giseli", ultimo_dia_exibido=UDI_VO))
    assert "CONFIRMAÇÃO PENDENTE" in r["texto_ia"]
    assert r["medico_agendamento"] == "Giseli Rebechi"
    assert r["hora_agendamento"] == "09:00"


def test_desambiguacao_recupera_hora_do_ultimo_dia_texto():
    r = processar(_base(
        texto_ia="elias", ultimo_dia_exibido=UDI_VO, ultimo_dia_texto="Data: 2026-07-14 | Dr(a). X: 14:00",
    ))
    assert r["hora_agendamento"] == "14:00"


# ---------- resolução principal médico × hora ----------

def test_medico_por_nome_com_hora_disponivel():
    r = processar(_base(texto_ia="quero com giseli as 10h", ultimo_dia_exibido=UDI_VO))
    assert r["medico_agendamento"] == "Giseli Rebechi"
    assert r["hora_agendamento"] == "10:00"


def test_medico_por_nome_hora_indisponivel_usa_mais_proxima():
    r = processar(_base(texto_ia="giseli as 11h", ultimo_dia_exibido=UDI_VO))
    assert r["medico_agendamento"] == "Giseli Rebechi"
    assert r["hora_agendamento"] == "10:00"


def test_hora_sem_medico_nenhum_candidato():
    r = processar(_base(texto_ia="pode ser as 8h", ultimo_dia_exibido=UDI_VO))
    assert "Não encontrei o horário 08:00 disponível" in r["texto_ia"]
    assert r["eh_confirmacao"] is False
    assert r["data_agendamento"] is None


def test_hora_com_dois_candidatos_pede_escolha():
    r = processar(_base(texto_ia="as 10h", ultimo_dia_exibido=UDI_VO))
    assert "está disponível com mais de um médico" in r["texto_ia"]
    assert "Giseli Rebechi" in r["texto_ia"]
    assert "Elias Lobo Braga" in r["texto_ia"]


def test_hora_com_um_candidato_unico():
    r = processar(_base(texto_ia="pode ser as 14h", ultimo_dia_exibido=UDI_VO))
    assert r["medico_agendamento"] == "Elias Lobo Braga"
    assert r["hora_agendamento"] == "14:00"


def test_sem_nome_sem_hora_fallback_primeiro_medico():
    r = processar(_base(texto_ia="qualquer horario", ultimo_dia_exibido=UDI_VO))
    assert r["medico_agendamento"] == "Giseli Rebechi"
    assert r["hora_agendamento"] == "09:00"


def test_confirmacao_texto_usa_nome_dependente():
    r = processar(_base(texto_ia="qualquer horario", ultimo_dia_exibido=UDI_VO, nome_dependente="Miguel Bueno"))
    assert "para Miguel Bueno" in r["texto_ia"]


def test_confirmacao_texto_usa_voce_sem_dependente():
    r = processar(_base(texto_ia="qualquer horario", ultimo_dia_exibido=UDI_VO))
    assert "para você" in r["texto_ia"]
