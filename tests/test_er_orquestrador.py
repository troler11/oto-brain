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


# ---------- deve_resetar_sessao / shadow_check (FIX_DEVE_RESETAR, fechado 12/07) ----------

def test_shadow_check_bypass_false_quando_nenhum_guard_preia_dispara():
    r = _run("oi")
    assert r.shadow_check == {"bypass": False}
    assert r.deve_resetar_sessao is False


def test_shadow_check_bypass_true_no_encaixe_com_match_true():
    # Triagem Determinística (Pre-IA) detecta "encaix" independentemente (guard duplicado de
    # propósito — ver app.triagem_deterministica_preia) e concorda com a decisão final do ER:
    # mesma rota/intenção/bypass_agente_humano.
    r = _run("queria um encaixe pra hoje")
    assert r.shadow_check == {
        "bypass": True,
        "motivo_regra": "encaixe",
        "pre_rota_agente": 5,
        "pre_intencao": "humano",
        "pre_bypass_humano": True,
        "final_rota_agente": 5,
        "final_intencao": "humano",
        "final_bypass_humano": True,
        "match": True,
    }


def test_deve_resetar_sessao_true_quando_recusa_cancelamento():
    b = _base(sessao_intencao="cancelando", sessao_rota=1, nome_dependente="Miguel Bueno")
    r = _run("não quero cancelar", base=b)
    assert r.deve_resetar_sessao is True
    assert r.intencao_rapida == "concluido"
