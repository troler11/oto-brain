"""
Testes de fumaça do orquestrador top-level (app/er.py::processar) — encadeia as 14 partes do
port do ER na mesma ordem do node original. Não repete os testes unitários de cada parte
(tests/test_er_parteN.py); só verifica que a fiação entre elas funciona ponta a ponta pra
alguns cenários realistas.
"""

from app.er import processar

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
        "coleta_convenio": "",
        "coleta_dia_semana": "",
        "coleta_horario": "",
        "coleta_modo": 0,
        "pacientes": [],
        "cpf": "",
        "id_tisaude": "",
        "nome": "",
        "hoje": "2026-07-12",
        "amanha": "2026-07-13",
        "cache_ativo": False,
        "ultimo_dia_exibido": "",
        "medico_candidato_msg": "",
        "motivo_humano": "",
        "texto_ia": "",
        "paciente_encontrado": False,
    }
    b.update(overrides)
    return b


def _run(texto, base=None, ia_output_raw=None):
    return processar(base or _base(), texto, {"output": ia_output_raw or "{}"}, WA_INFO)


def test_saudacao_pura_nao_quebra():
    r = _run("oi")
    assert r.base is not None
    assert isinstance(r.rota_agente, int)
    assert r.telefone == "5511999999999"


def test_triagem_com_intencao_de_agendar_vai_pra_coleta():
    b = _base(sessao_intencao="triagem")
    r = _run("Boa tarde! Gostaria de marcar uma consulta", base=b)
    assert r.rota_agente == 2
    assert r.intencao_rapida == "coleta"


def test_pedido_atendente_em_sessao_ativa_vai_pra_humano():
    b = _base(sessao_intencao="agenda", sessao_rota=4)
    r = _run("quero falar com um atendente", base=b)
    assert r.intencao_rapida == "humano"
    assert r.motivo_humano is not None


def test_encaixe_early_guard_ainda_funciona_via_orquestrador():
    r = _run("queria um encaixe pra hoje")
    assert r.intencao_rapida == "humano"
    assert r.motivo_humano == "Paciente pediu encaixe"
