"""
Testes do port de Formatar Verificar Confirmar (app/formatar_verificar_confirmar.py::processar)
— DEPLOY/_proposed_Formatar_Verificar_Confirmar.js, 68 linhas (FIX_CONFIRMA_AUTO).
"""

import json

from app.formatar_verificar_confirmar import (
    formatar_escolher_titular,
    formatar_resposta_confirmar,
    preparar_confirmar,
    processar,
)

C1 = {"id": "1", "dataBR": "15/07/2026", "hora": "09:00", "medico": "Dra. Giseli Rebechi", "status_id": 1, "status_nome": "pendente"}
C2 = {"id": "2", "dataBR": "16/07/2026", "hora": "14:00", "medico": "Dr. Elias Lobo Braga", "status_id": 1, "status_nome": "pendente"}
C_CONF = {"id": "3", "dataBR": "10/07/2026", "hora": "10:00", "medico": "Dr. Jose", "status_id": 3, "status_nome": "confirmado"}


def _bloco(output: str) -> dict:
    return json.loads(output.split("$$$", 1)[1])


# ---------- zero consultas ----------

def test_zero_consultas():
    r = processar({"consultas": []}, {}, 0)
    assert "Não encontrei nenhuma consulta" in r["output"]
    assert r["auto_confirmar"] is False
    assert _bloco(r["output"])["i"] == "triagem"


# ---------- todas confirmadas ----------

def test_uma_consulta_ja_confirmada():
    r = processar({"consultas": [C_CONF]}, {}, 0)
    assert "já está confirmada" in r["output"]
    assert _bloco(r["output"])["i"] == "concluido"


def test_todas_confirmadas_multipla():
    r = processar({"consultas": [C_CONF, {**C_CONF, "id": "4"}]}, {}, 0)
    assert "Todas as suas consultas já estão confirmadas!" in r["output"]


# ---------- 1 pendente ----------

def test_uma_pendente_pergunta():
    r = processar({"consultas": [C1]}, {}, 0)
    assert r["auto_confirmar"] is False
    assert "Deseja confirmar sua presença" in r["output"]
    d = _bloco(r["output"])
    assert d["i"] == "confirmar_presenca"
    assert d["id"] == "1"


def test_uma_pendente_com_sinal_direto_auto_confirma():
    r = processar({"consultas": [C1]}, {"_confirma_direto": True}, 0)
    assert r["auto_confirmar"] is True
    assert r["id_agendamento"] == "1"
    assert r["consulta_medico"] == "Dra. Giseli Rebechi"


# ---------- 2+ pendentes: lista ----------

def test_duas_pendentes_lista_numerada():
    r = processar({"consultas": [C1, C2]}, {}, 0)
    assert "Você tem 2 consultas aguardando confirmação" in r["output"]
    assert "1. 15/07/2026 às 09:00 com Dr(a). Dra. Giseli Rebechi" in r["output"]
    assert "2. 16/07/2026" in r["output"]
    assert _bloco(r["output"])["i"] == "confirmar_presenca_lista"


def test_confirmadas_saem_da_lista_de_escolha():
    r = processar({"consultas": [C1, C_CONF]}, {}, 0)
    # só 1 pendente (C1) -> vira o caso "1 pendente", não lista
    d = _bloco(r["output"])
    assert d["i"] == "confirmar_presenca"


# ---------- resposta a lista já exibida (indice) ----------

def test_indice_valido_seleciona_pendente():
    r = processar({"consultas": [C1, C2]}, {}, 2)
    d = _bloco(r["output"])
    assert d["id"] == "2"
    assert "16/07/2026" in r["output"]


def test_indice_valido_com_direto_auto_confirma():
    r = processar({"consultas": [C1, C2]}, {"_confirma_direto": True}, 1)
    assert r["auto_confirmar"] is True
    assert r["id_agendamento"] == "1"


def test_indice_fora_do_range_nao_entendi():
    r = processar({"consultas": [C1, C2]}, {}, 9)
    assert "Não entendi qual consulta" in r["output"]
    assert _bloco(r["output"])["i"] == "confirmar_presenca_lista"


# ---------- FIX_LOOP_CONFIRMAR ----------

def test_cf_incrementa_na_reexibicao_da_lista():
    r = processar({"consultas": [C1, C2]}, {"sessao_intencao": "confirmar_presenca_lista", "coleta_conv_fail": 1}, 9)
    assert _bloco(r["output"])["cf"] == 2


def test_cf_comeca_em_1_na_primeira_lista():
    r = processar({"consultas": [C1, C2]}, {}, 0)
    assert _bloco(r["output"])["cf"] == 1


def test_cf_zero_fora_da_lista():
    r = processar({"consultas": [C1]}, {}, 0)
    assert _bloco(r["output"])["cf"] == 0


# ---------- preparar_confirmar ----------

def test_preparar_confirmar_caminho_auto():
    r = preparar_confirmar({"auto_confirmar": True, "id_agendamento": "42"}, {"coleta_id_agendamento": "99"})
    assert r["id_agendamento"] == "42"


def test_preparar_confirmar_caminho_legado():
    r = preparar_confirmar({"auto_confirmar": False}, {"coleta_id_agendamento": "99"})
    assert r["id_agendamento"] == "99"


def test_preparar_confirmar_sem_nada():
    r = preparar_confirmar({}, {})
    assert r["id_agendamento"] == ""


# ---------- formatar_escolher_titular ----------

def test_formatar_escolher_titular_lista_numerada():
    r = formatar_escolher_titular({}, [{"nome": "Lucas Bueno"}, {"nome": "Miguel Bueno"}])
    assert "1. Lucas Bueno" in r["output"]
    assert "2. Miguel Bueno" in r["output"]
    d = _bloco(r["output"])
    assert d["i"] == "confirmar_presenca_escolher"
    assert d["cf"] == 1


def test_formatar_escolher_titular_sem_nome_usa_titular_n():
    r = formatar_escolher_titular({}, [{}])
    assert "1. Titular 1" in r["output"]


def test_formatar_escolher_titular_cf_incrementa_na_reexibicao():
    r = formatar_escolher_titular({"sessao_intencao": "confirmar_presenca_escolher", "coleta_conv_fail": 2}, [{"nome": "A"}])
    assert _bloco(r["output"])["cf"] == 3


# ---------- formatar_resposta_confirmar ----------

def test_formatar_resposta_confirmar_auto_detalhado():
    r = formatar_resposta_confirmar(
        {"auto_confirmar": True, "id_agendamento": "1", "consulta_dataBR": "15/07/2026", "consulta_hora": "09:00", "consulta_medico": "Dra. Giseli"},
        {},
    )
    assert "Prontinho! Presença confirmada para o dia 15/07/2026 às 09:00 com Dr(a). Dra. Giseli ✅" in r["output"]
    assert _bloco(r["output"])["id"] == "1"


def test_formatar_resposta_confirmar_legado_curto():
    r = formatar_resposta_confirmar({"auto_confirmar": False}, {"coleta_id_agendamento": "7"})
    assert r["output"].startswith("Presença confirmada! ✅ Até logo!")
    assert _bloco(r["output"])["id"] == "7"
