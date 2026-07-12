"""
Testes da Parte 9 do port do ER (app/er.py::processar_menu_p3_e_faq) — linhas 3470-3689
do JS fonte: FIX_59087 (menu P3 numérico com resposta literal por opção),
FIX_NOME_INJECT_TITULAR (pré-identificação de paciente titular via fuzzy match) e o bloco
FAQ_INJECT (14 categorias de FAQ com retomada determinística).
"""

from app.er import processar_menu_p3_e_faq


def _base(**overrides):
    b = {
        "sessao_intencao": "triagem",
        "sessao_rota": 0,
        "coleta_unidade": "",
        "coleta_medico": "",
        "coleta_data": "",
        "cache_ativo": False,
        "coleta_id_tisaude": "",
        "cpf_dependente": "",
        "nascimento_dependente": "",
        "nome_dependente": "",
        "pacientes": [],
        "coleta_convenio": "",
        "texto_ia": "",
        "hoje": "",
        "amanha": "",
        "lista_med": "",
    }
    b.update(overrides)
    return b


def _proc(texto, base=None, intencao_rapida="agenda", rota_agente=2, ia_output=None,
          sessao_era_agenda_com_coleta=False, tem_identidade_em_andamento=False, tem_terceiro_completo=False):
    io = ia_output if ia_output is not None else {}
    r = processar_menu_p3_e_faq(
        base or _base(), texto, intencao_rapida, rota_agente, io,
        sessao_era_agenda_com_coleta, tem_identidade_em_andamento, tem_terceiro_completo,
    )
    return r, io


# ---------- FIX_59087 ----------

def test_menu_p3_opcao_1_primeiro_horario():
    b = _base(sessao_intencao="coleta", coleta_unidade="Vila Olímpia", coleta_id_tisaude="123")
    r, io = _proc("1", base=b, rota_agente=2)
    assert "MENU P3 OPCAO 1" in r.base["texto_ia"]


def test_menu_p3_opcao_2_lista_medicos_literal():
    b = _base(sessao_intencao="coleta", coleta_unidade="Vila Olímpia", coleta_id_tisaude="123",
              lista_med="lista completa de medicos")
    r, io = _proc("2", base=b, rota_agente=2)
    assert "MENU P3 OPCAO 2" in r.base["texto_ia"]
    assert "lista completa de medicos" in r.base["texto_ia"]


def test_menu_p3_opcao_3_ja_tem_medico():
    b = _base(sessao_intencao="coleta", coleta_unidade="Vila Olímpia", coleta_id_tisaude="123")
    r, io = _proc("3", base=b, rota_agente=2)
    assert "MENU P3 OPCAO 3" in r.base["texto_ia"]


# ---------- FIX_NOME_INJECT_TITULAR ----------

def test_nome_inject_titular_match_exato_substring():
    b = _base(pacientes=[
        {"nome": "Lucas Bueno", "cpf": "111", "nascimento": "01/01/1990"},
        {"nome": "Maria Silva", "cpf": "222", "nascimento": "02/02/1980"},
    ])
    r, io = _proc("lucas", base=b, rota_agente=2)
    assert r.base["nome_dependente"] == "Lucas Bueno"
    assert r.base["cpf_dependente"] == "111"
    assert "PACIENTE IDENTIFICADO" in r.base["texto_ia"]


def test_nome_inject_titular_fuzzy_typo():
    b = _base(pacientes=[
        {"nome": "Ana", "cpf": "1", "nascimento": "n1"},
        {"nome": "Beto Souza", "cpf": "2", "nascimento": "n2"},
    ])
    r, io = _proc("ann", base=b, rota_agente=2)
    assert r.base["nome_dependente"] == "Ana"
    assert r.base["cpf_dependente"] == "1"


def test_nome_inject_titular_nao_dispara_com_1_paciente():
    b = _base(pacientes=[{"nome": "Lucas Bueno", "cpf": "111", "nascimento": "01/01/1990"}])
    r, io = _proc("lucas", base=b, rota_agente=2)
    assert r.base["nome_dependente"] == ""
    assert r.base["texto_ia"] == ""


# ---------- FAQ_INJECT ----------

def test_faq_convenio_generico_retomada_padrao():
    b = _base()
    r, io = _proc("quais convenios voces aceitam", base=b)
    assert "Itaú" in r.base["texto_ia"]
    assert "Posso te ajudar a agendar? 😊" in r.base["texto_ia"]


def test_faq_particular_com_retomada_identidade_em_andamento():
    b = _base(nome_dependente="Roberto", cpf_dependente="")
    r, io = _proc("qual o valor da consulta particular", base=b,
                   sessao_era_agenda_com_coleta=True, tem_identidade_em_andamento=True)
    assert "Consulta no Particular" in r.base["texto_ia"]
    assert "CPF de Roberto" in r.base["texto_ia"]


def test_faq_verbo_de_acao_suprime_trata():
    b = _base()
    r, io = _proc("quero marcar uma consulta pra tratar zumbido", base=b)
    assert r.base["texto_ia"] == ""


def test_faq_conv_com_verbo_agendar_injeta_convenio_direto():
    b = _base(coleta_convenio="")
    r, io = _proc("quero marcar consulta com convenio porto seguro", base=b)
    assert "AGENDAMENTO COM CONVENIO INFORMADO" in r.base["texto_ia"]
    assert "Porto Seguro" in r.base["texto_ia"]


def test_faq_suprimida_durante_agenda_ativa_com_coleta():
    b = _base()
    r, io = _proc("quais convenios voces aceitam", base=b, sessao_era_agenda_com_coleta=True)
    assert r.base["texto_ia"] == ""
