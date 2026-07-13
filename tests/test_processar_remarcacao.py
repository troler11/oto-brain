"""
Testes do port de Processar Remarcação (app/processar_remarcacao.py::processar) —
DEPLOY/_proposed_Processar_Remarcacao.js, 125 linhas.

Nota (do JS fonte, preservada): os nomes de campo da consulta (dt/hr/md/unid/conv/id) são
palpite educado, não confirmados contra o shape real do sub-workflow — os testes cobrem as
variações que o `pick()` tolera.
"""

import json

import httpx

from app.processar_remarcacao import buscar_e_processar, processar


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


# ---------- buscar_e_processar (integração IO, modo listagem só-leitura) ----------

def _handler(pacientes=None, timeline=None):
    pacientes = pacientes if pacientes is not None else [{"id": 55, "name": "Lucas"}]
    timeline = timeline if timeline is not None else [
        {"date": "2026-07-20", "data": [
            {"type": "appointment", "id": 999, "date": "2026-07-20", "hour": "10:00",
             "calendar": {"name": "Giseli Rebechi"}, "status": {"name": "Pendente"},
             "local": {"name": "Vila Olímpia"}, "healthInsurance": {"name": "Itaú"}},
        ]},
    ]

    def handler(request):
        path = request.url.path
        if path == "/api/login":
            return httpx.Response(200, json={"access_token": "tok"})
        if path == "/api/patients":
            return httpx.Response(200, json={"data": pacientes})
        if path == "/api/patients/55/timeline":
            return httpx.Response(200, json={"data": timeline})
        raise AssertionError(f"chamada inesperada (mutação não deveria acontecer aqui): {path}")

    return handler


def test_buscar_e_processar_uma_consulta_pergunta_periodo():
    client = httpx.Client(transport=httpx.MockTransport(_handler()))
    r = buscar_e_processar(_base(cpf="12345678900"), "quero remarcar", tisaude_client=client)
    assert "20/07/2026 às 10:00 com Dr(a). Giseli Rebechi" in r["output"]
    d = _bloco(r["output"])
    assert d["unid"] == "Vila Olímpia"
    assert d["id_ag_antigo"] == 999  # id vem como int do JSON da TiSaude, preservado sem cast


def test_buscar_e_processar_sem_consultas_oferece_agendar_novo():
    client = httpx.Client(transport=httpx.MockTransport(_handler(timeline=[])))
    r = buscar_e_processar(_base(cpf="12345678900"), "quero remarcar", tisaude_client=client)
    assert "Não encontrei nenhuma consulta ativa" in r["output"]


def test_buscar_e_processar_cpf_do_dependente_tem_prioridade():
    client = httpx.Client(transport=httpx.MockTransport(_handler()))
    r = buscar_e_processar(_base(cpf="00000000000", cpf_dependente="12345678900"), "quero remarcar", tisaude_client=client)
    assert r is not None  # chegou até aqui sem AssertionError = usou cpf_dependente, não cpf


def test_buscar_e_processar_sem_cpf_retorna_none():
    assert buscar_e_processar(_base(), "quero remarcar", tisaude_client=None) is None


def test_buscar_e_processar_falha_de_rede_retorna_none():
    def handler(request):
        raise httpx.ConnectError("timeout", request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    assert buscar_e_processar(_base(cpf="12345678900"), "quero remarcar", tisaude_client=client) is None
