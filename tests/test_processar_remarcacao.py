"""
Testes do port de Processar Remarcação (app/processar_remarcacao.py::processar) —
DEPLOY/_proposed_Processar_Remarcacao.js, 125 linhas.

Nota (do JS fonte, preservada): os nomes de campo da consulta (dt/hr/md/unid/conv/id) são
palpite educado, não confirmados contra o shape real do sub-workflow — os testes cobrem as
variações que o `pick()` tolera.
"""

import json

from app.processar_remarcacao import processar


def _base(**overrides):
    b = {
        "sessao_intencao": "",
        "coleta_terceiro": "",
        "nome_dependente": "", "nome": "",
        "cpf_dependente": "", "cpf": "",
        "nascimento_dependente": "", "nascimento": "",
    }
    b.update(overrides)
    return b


def _bloco(output: str) -> dict:
    return json.loads(output.split("$$$", 1)[1])


# ---------- CASO 0: nenhuma consulta ----------

def test_zero_consultas_oferece_agendar_novo():
    r = processar(_base(nome="Lucas Bueno", cpf="11111111111"), "quero remarcar", [])
    assert "Não encontrei nenhuma consulta ativa" in r["output"]
    d = _bloco(r["output"])
    assert d["i"] == "coleta"
    assert d["d"] == "Lucas Bueno"
    assert d["c"] == "11111111111"


# ---------- CASO 1: consulta única (auto-seleciona) ----------

def test_uma_consulta_com_unidade_conhecida():
    consultas = [{"dataBR": "15/07/2026", "hr": "09:00", "md": "Dra. Giseli Rebechi", "id": "99", "unidade": "Vila Olímpia", "conv": "Itaú"}]
    r = processar(_base(), "quero remarcar", consultas)
    assert "Vamos remarcar sua consulta de 15/07/2026 às 09:00 com Dr(a). Dra. Giseli Rebechi" in r["output"]
    assert "Prefere de manhã ou de tarde?" in r["output"]
    d = _bloco(r["output"])
    assert d["unid"] == "Vila Olímpia"
    assert d["i"] == "coleta"
    assert d["id_ag_antigo"] == "99"


def test_uma_consulta_sem_unidade_pergunta_unidade():
    consultas = [{"dt": "15/07/2026", "hora": "09:00", "medico": "Dr. Elias Lobo Braga", "id_agendamento": "5"}]
    r = processar(_base(), "quero remarcar", consultas)
    assert "qual a melhor unidade para você?" in r["output"]
    d = _bloco(r["output"])
    assert d["i"] == "coleta"
    assert "unid" not in d or d.get("unid") == ""


def test_periodo_detectado_na_mensagem_pula_pra_agenda():
    consultas = [{"dataBR": "15/07/2026", "hr": "09:00", "md": "Giseli", "id": "1", "unid": "vila olimpia"}]
    r = processar(_base(), "quero remarcar para de manha", consultas)
    d = _bloco(r["output"])
    assert d["i"] == "agenda"
    assert d["per"] == "manha"
    assert "Vou buscar horários pra você!" in r["output"]


def test_periodo_tarde_detectado():
    consultas = [{"dataBR": "15/07/2026", "hr": "09:00", "md": "Giseli", "id": "1", "unid": "tatuape"}]
    r = processar(_base(), "prefiro a tarde", consultas)
    d = _bloco(r["output"])
    assert d["per"] == "tarde"
    assert d["unid"] == "Tatuapé"


def test_terceiro_preenche_dados_do_titular():
    r = processar(_base(nome_dependente="Miguel Bueno", cpf_dependente="22222222222"), "remarcar", [])
    d = _bloco(r["output"])
    assert d["d"] == "Miguel Bueno"
    assert d["c"] == "22222222222"


# ---------- CASO 2+: múltiplas consultas ----------

def test_duas_consultas_pede_escolha():
    consultas = [
        {"dt": "10/07/2026", "hr": "09:00", "md": "Giseli", "id": "1"},
        {"dt": "12/07/2026", "hr": "14:00", "md": "Elias", "id": "2"},
    ]
    r = processar(_base(), "quero remarcar", consultas)
    assert "Você tem mais de uma consulta marcada." in r["output"]
    assert "1. 10/07/2026 às 09:00 com Dr(a). Giseli" in r["output"]
    assert "2. 12/07/2026 às 14:00 com Dr(a). Elias" in r["output"]
    d = _bloco(r["output"])
    assert d["i"] == "remarcando_escolher"


def test_escolha_valida_processa_a_selecionada():
    consultas = [
        {"dataBR": "10/07/2026", "hr": "09:00", "md": "Giseli", "id": "1", "unid": "vila olimpia"},
        {"dataBR": "12/07/2026", "hr": "14:00", "md": "Elias", "id": "2", "unid": "tatuape"},
    ]
    r = processar(_base(sessao_intencao="remarcando_escolher"), "2", consultas)
    assert "12/07/2026 às 14:00 com Dr(a). Elias" in r["output"]
    d = _bloco(r["output"])
    assert d["md_antiga"] == "Elias"


def test_escolha_invalida_relista_com_nao_entendi():
    consultas = [
        {"dt": "10/07/2026", "hr": "09:00", "md": "Giseli", "id": "1"},
        {"dt": "12/07/2026", "hr": "14:00", "md": "Elias", "id": "2"},
    ]
    r = processar(_base(sessao_intencao="remarcando_escolher"), "99", consultas)
    assert "Não entendi." in r["output"]


def test_escolha_nao_numerica_relista():
    consultas = [
        {"dt": "10/07/2026", "hr": "09:00", "md": "Giseli", "id": "1"},
        {"dt": "12/07/2026", "hr": "14:00", "md": "Elias", "id": "2"},
    ]
    r = processar(_base(sessao_intencao="remarcando_escolher"), "a giseli", consultas)
    assert "Não entendi." in r["output"]


# ---------- normalização do shape de entrada ----------

def test_shape_wrapped_em_consultas():
    r = processar(_base(), "remarcar", [{"consultas": [{"dt": "10/07/2026", "hr": "09:00", "md": "Giseli", "id": "1", "unid": "vila"}]}])
    assert "10/07/2026" in r["output"]


def test_shape_array_direto():
    r = processar(_base(), "remarcar", [[{"dt": "10/07/2026", "hr": "09:00", "md": "Giseli", "id": "1", "unid": "vila"}]])
    assert "10/07/2026" in r["output"]
