"""
Testes da Parte 13 do port do ER (app/er.py::processar_agradecimento_triagem_multidados) —
linhas 4411-4661 do JS fonte: FIX_AGRADECIMENTO_CONCLUIDO, FIX_TRIAGEM_AGENDA,
FIX_TRIAGEM_SIM_AGENDA e FIX_MULTI_ENTIDADES (captura multi-entidade + validação contra a
grade + persistência via _pmsg + próxima pergunta ou busca completa).
"""

from app.er import processar_agradecimento_triagem_multidados


def _base(**overrides):
    b = {
        "sessao_intencao": "",
        "coleta_unidade": "",
        "coleta_medico": "",
        "coleta_convenio": "",
        "coleta_periodo": "",
        "coleta_data": "",
        "coleta_dia_semana": "",
        "coleta_modo": 0,
        "paciente_encontrado": True,
        "nome_dependente": "",
        "coleta_id_tisaude": "",
        "pacientes": [],
        "texto_ia": "",
        "_clear_pm": {},
        "hoje": "",
        "amanha": "",
        "prox_seg": "", "prox_ter": "", "prox_qua": "", "prox_qui": "", "prox_sex": "",
        "_ultimo_medico_global": "",
        "_pergunta_convenio_global": "A consulta será Particular ou Convênio? 😊",
    }
    b.update(overrides)
    return b


def _proc(texto, base=None, intencao_rapida="triagem", rota_agente=0, ia_output=None, identidade_incompleta=False):
    io = ia_output if ia_output is not None else {}
    r = processar_agradecimento_triagem_multidados(
        base or _base(), texto, intencao_rapida, rota_agente, io, identidade_incompleta,
    )
    return r, io


# ---------- FIX_AGRADECIMENTO_CONCLUIDO ----------

def test_agradecimento_apos_concluido_encerra():
    b = _base(sessao_intencao="concluido")
    r, io = _proc("muito obrigada", base=b)
    assert r.rota_agente == 0
    assert r.intencao_rapida == "triagem"
    assert r.deve_resetar_agradecimento is True
    assert "ENCERRAMENTO" in r.base["texto_ia"]


# ---------- FIX_TRIAGEM_AGENDA ----------

def test_triagem_agenda_saudacao_com_intencao_nao_reativa_menu():
    b = _base(sessao_intencao="triagem")
    r, io = _proc("Boa tarde! Gostaria de marcar uma consulta", base=b, rota_agente=0)
    assert r.rota_agente == 2
    assert r.intencao_rapida == "coleta"
    assert "INICIO AGENDA" in r.base["texto_ia"]


# ---------- FIX_TRIAGEM_SIM_AGENDA ----------

def test_triagem_sim_puro_inicia_agendamento():
    b = _base(sessao_intencao="triagem", pacientes=[{"nome": "Bruno Lima"}])
    r, io = _proc("sim", base=b, rota_agente=0)
    assert r.rota_agente == 2
    assert r.intencao_rapida == "coleta"
    assert "INICIO AGENDA CONFIRMADO" in r.base["texto_ia"]
    assert "Bruno Lima" in r.base["texto_ia"]


# ---------- FIX_MULTI_ENTIDADES ----------

def test_multi_entidades_captura_parcial_pergunta_proximo_campo():
    b = _base(prox_qua="2026-07-15")
    r, io = _proc(
        "quero com a giseli quarta de manha na vila olimpia", base=b,
        intencao_rapida="coleta", rota_agente=2,
    )
    assert r.base["coleta_unidade"] == "Vila Olímpia"
    assert r.base["coleta_medico"] == "Dra. Giseli Rebechi"
    assert r.base["coleta_data"] == "2026-07-15"
    assert r.base["coleta_periodo"] == "manha"
    assert "MULTI DADOS:" in r.base["texto_ia"]
    assert "MULTI DADOS COMPLETO" not in r.base["texto_ia"]
    assert "A consulta será para você ou para outra pessoa?" in r.base["texto_ia"]


def test_multi_entidades_coleta_completa_busca_direto():
    b = _base(nome_dependente="Carlos Souza", prox_qui="2026-07-16")
    r, io = _proc(
        "quero com o jose quinta de manha no porto seguro vila olimpia", base=b,
        intencao_rapida="coleta", rota_agente=2,
    )
    assert r.rota_agente == 4
    assert r.base["coleta_convenio"] == "Porto Seguro"
    assert "MULTI DADOS COMPLETO" in r.base["texto_ia"]


def test_multi_entidades_medico_nao_atende_dia_limpa_e_reask():
    b = _base(nome_dependente="Ana Paula", prox_seg="2026-07-13")
    r, io = _proc(
        "quero com a giseli segunda de manha na vila olimpia", base=b,
        intencao_rapida="coleta", rota_agente=2,
    )
    assert r.base["coleta_data"] == ""
    assert "não atende segunda" in r.base["texto_ia"]
    assert "Qual dia prefere?" in r.base["texto_ia"]


def test_multi_entidades_captura_unica_sem_tag_toma_o_turno():
    b = _base()
    r, io = _proc("pode ser na vila olimpia", base=b, intencao_rapida="coleta", rota_agente=2)
    assert r.base["coleta_unidade"] == "Vila Olímpia"
    assert "MULTI DADOS:" in r.base["texto_ia"]
