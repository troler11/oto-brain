"""
Testes do port de Triagem Determinística Pre-IA (app/triagem_deterministica_preia.py::processar)
— DEPLOY/_new_Triagem_Deterministica_PreIA.js, 99 linhas. Nó-sombra: só calcula `_preRota`,
não desvia nada de verdade.
"""

from app.triagem_deterministica_preia import processar


def _base(**overrides):
    b = {
        "sessao_intencao": "",
        "sessao_rota": 0,
        "coleta_terceiro": "",
        "nome_dependente": "",
        "cpf_dependente": "",
        "nascimento_dependente": "",
        "coleta_unidade": "",
        "coleta_data": "",
        "coleta_periodo": "",
        "coleta_convenio": "",
        "coleta_medico": "",
    }
    b.update(overrides)
    return b


def test_sem_guard_bypass_false():
    r = processar(_base(), "oi tudo bem")
    assert r["_preRota"] == {"bypass": False, "motivo_regra": None}


# ---------- FIX_REMARCAR_V2 ----------

def test_remarcar_dispara():
    r = processar(_base(), "quero remarcar minha consulta")
    assert r["_preRota"] == {"bypass": True, "motivo_regra": "remarcar", "intencao_rapida": "remarcando"}


def test_remarcar_nao_dispara_em_sessao_coleta():
    r = processar(_base(sessao_intencao="coleta"), "quero remarcar")
    assert r["_preRota"]["bypass"] is False


def test_remarcar_nao_dispara_se_sessao_era_agenda_com_coleta():
    r = processar(_base(sessao_rota=2, sessao_intencao="agenda", coleta_unidade="Vila Olímpia"), "quero remarcar")
    assert r["_preRota"]["bypass"] is False


# ---------- FIX_ENCAIXE ----------

def test_encaixe_dispara():
    r = processar(_base(), "queria um encaixe pra hoje")
    assert r["_preRota"] == {"bypass": True, "motivo_regra": "encaixe", "rota_agente": 5, "intencao_rapida": "humano", "bypass_agente_humano": True}


# ---------- lista de espera / desistência ----------

def test_desistencia_dispara():
    r = processar(_base(), "vou desistir da consulta")
    assert r["_preRota"]["motivo_regra"] == "desistencia"
    assert r["_preRota"]["rota_agente"] == 5


def test_lista_espera_por_frase_direta():
    r = processar(_base(), "quero entrar na lista de espera")
    assert r["_preRota"]["motivo_regra"] == "lista_espera"


def test_lista_espera_por_aviso_mais_vaga():
    r = processar(_base(), "pode me avisar se abrir uma vaga mais cedo?")
    assert r["_preRota"]["motivo_regra"] == "lista_espera"


def test_aviso_sem_contexto_vaga_nao_dispara_lista_espera():
    r = processar(_base(), "pode me avisar quando confirmar")
    assert r["_preRota"]["bypass"] is False


# ---------- menu numérico ----------

def test_menu_opcao_1_agendar():
    r = processar(_base(), "1")
    assert r["_preRota"] == {"bypass": True, "motivo_regra": "menu_1_agendar", "rota_agente": 2, "intencao_rapida": "coleta"}


def test_menu_opcao_2_cancelar():
    r = processar(_base(), "2")
    assert r["_preRota"]["motivo_regra"] == "menu_2_3_cancelar"
    assert r["_preRota"]["rota_agente"] == 1


def test_menu_opcao_3_cancelar():
    r = processar(_base(), "3")
    assert r["_preRota"]["motivo_regra"] == "menu_2_3_cancelar"


def test_menu_opcao_repetida_normaliza():
    r = processar(_base(), "1 1 1")
    assert r["_preRota"]["motivo_regra"] == "menu_1_agendar"


def test_menu_invalido_fora_de_1_a_6():
    r = processar(_base(), "9")
    assert r["_preRota"]["motivo_regra"] == "menu_invalido"
    assert r["_preRota"]["intencao_rapida"] == "triagem"


def test_menu_invalido_nao_dispara_com_unidade_ja_escolhida():
    r = processar(_base(coleta_unidade="Vila Olímpia"), "9")
    assert r["_preRota"]["bypass"] is False


def test_menu_4_a_6_nao_dispara_nada():
    r = processar(_base(), "4")
    assert r["_preRota"]["bypass"] is False


def test_menu_nao_dispara_fora_de_sessao_nova():
    r = processar(_base(sessao_intencao="coleta"), "1")
    assert r["_preRota"]["bypass"] is False


def test_mensagem_informativa_conta_como_sessao_nova():
    r = processar(_base(sessao_intencao="coleta"), "quais convenios voces aceitam")
    # não é "1"/"2"/"3", então não dispara bypass — mas não deve quebrar (eh_sessao_nova=True via informativa)
    assert r["_preRota"]["bypass"] is False


# ---------- FIX_ATRASO_HUMANO ----------

def test_atraso_liga_bypass_humano_sem_mudar_rota():
    r = processar(_base(), "vou chegar mais tarde, presa no transito")
    assert r["_preRota"] == {"bypass": True, "motivo_regra": "atraso", "bypass_agente_humano": True}
    assert "rota_agente" not in r["_preRota"]
    assert "intencao_rapida" not in r["_preRota"]


# ---------- sanitização do texto ----------

def test_sanitiza_digito_final_e_espacos():
    r = processar(_base(), "encaixe1   por   favor")
    assert r["_preRota"]["motivo_regra"] == "encaixe"
