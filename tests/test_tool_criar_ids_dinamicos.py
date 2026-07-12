"""
Testes do port de Tool Criar/Extrair IDs Dinâmicos2 (app/tool_criar_ids_dinamicos.py::processar)
— DEPLOY/_proposed_Tool_Criar_Extrair_IDs_Dinamicos2.js, 84 linhas.
"""

import pytest

from app.tool_criar_ids_dinamicos import MedicoNaoEncontrado, processar


# ---------- mapeamento flexível da estrutura da API ----------

def test_shape_dias_acumulados():
    busca = {"diasAcumulados": {"2026-07-14": {"a": {"medico": "Giseli Rebechi", "idLocal": 1, "idCalendar": 11}}}}
    r = processar({"nome_medico_escolhido": "Giseli"}, busca)
    assert r["idLocal_dinamico"] == 1
    assert r["idCalendar_dinamico"] == 11


def test_shape_array_direto():
    busca = [{"medico": "Elias Lobo Braga", "idLocal": 2, "idCalendar": 22}]
    r = processar({"nome_medico_escolhido": "Elias"}, busca)
    assert r["idCalendar_dinamico"] == 22


def test_shape_objeto_unico_raiz():
    busca = {"medico": "Caio Vinicius Saettini", "idLocal": 3, "idCalendar": 33}
    r = processar({"nome_medico_escolhido": "Caio"}, busca)
    assert r["idCalendar_dinamico"] == 33


def test_shape_agenda_legado():
    busca = {"agenda": [{"medico": "Fernanda Butura", "idLocal": 4, "idCalendar": 44}]}
    r = processar({"nome_medico_escolhido": "Fernanda"}, busca)
    assert r["idCalendar_dinamico"] == 44


def test_shape_desconhecido_lista_vazia():
    r = processar({"nome_medico_escolhido": "Giseli"}, {"algo_aleatorio": True})
    assert r["idCalendar_dinamico"] == 0
    assert r["idLocal_dinamico"] == 2


# ---------- FIX_65707: match bidirecional sem título ----------

def test_match_eco_truncado_com_titulo():
    busca = [{"medico": "STEPHANIE RUGERI DE SOUZA", "idLocal": 1, "idCalendar": 55}]
    r = processar({"nome_medico_escolhido": "Dra. Stephanie Rugeri"}, busca)
    assert r["idCalendar_dinamico"] == 55


def test_match_por_tokens_quando_includes_direto_falha():
    # nome da API tem ordem/forma diferente mas todos os tokens >2 chars batem
    busca = [{"medico": "Rugeri de Souza, Stephanie", "idLocal": 1, "idCalendar": 66}]
    r = processar({"nome_medico_escolhido": "Stephanie Rugeri"}, busca)
    assert r["idCalendar_dinamico"] == 66


# ---------- contingência / erro ----------

def test_sem_preferencia_usa_primeiro_valido():
    busca = [{"medico": "Elias Lobo Braga", "idLocal": 1, "idCalendar": 77}]
    r = processar({"nome_medico_escolhido": "sem preferencia"}, busca)
    assert r["idCalendar_dinamico"] == 77


def test_vazio_usa_primeiro_valido():
    busca = [{"medico": "Elias Lobo Braga", "idLocal": 1, "idCalendar": 88}]
    r = processar({}, busca)
    assert r["idCalendar_dinamico"] == 88


def test_medico_nomeado_sem_match_lanca_erro():
    busca = [{"medico": "Elias Lobo Braga", "idLocal": 1, "idCalendar": 99}]
    with pytest.raises(MedicoNaoEncontrado, match="MEDICO_NAO_ENCONTRADO"):
        processar({"nome_medico_escolhido": "Torcuato"}, busca)


def test_medico_nomeado_lista_vazia_nao_lanca_fallback_default():
    r = processar({"nome_medico_escolhido": "Torcuato"}, [])
    assert r["idCalendar_dinamico"] == 0
    assert r["idLocal_dinamico"] == 2


# ---------- retorno preserva os dados da IA ----------

def test_retorno_preserva_campos_originais():
    busca = [{"medico": "Giseli Rebechi", "idLocal": 1, "idCalendar": 11}]
    r = processar({"nome_medico_escolhido": "Giseli", "data": "2026-07-14", "hora": "09:00"}, busca)
    assert r["data"] == "2026-07-14"
    assert r["hora"] == "09:00"
