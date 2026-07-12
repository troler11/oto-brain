"""
Testes do port de Reask Engine (app/reask_engine.py::processar) —
DEPLOY/_proposed_Reask_Engine.js, 94 linhas.
"""

from app.reask_engine import processar


def _sv(**overrides):
    d = {
        "sv_reason": "",
        "unidade_coleta": "", "medico_coleta": "", "convenio": "",
        "data_coleta": "", "periodo_coleta": "", "dia_semana_coleta": "",
    }
    d.update(overrides)
    return d


def test_confirmacao_sem_horario():
    assert processar(_sv(sv_reason="confirmacao_sem_horario"))["mensagem_final"] == "Qual horário você prefere? 😊"


def test_execucao_sem_horario_mesma_msg():
    assert processar(_sv(sv_reason="execucao_sem_horario"))["mensagem_final"] == "Qual horário você prefere? 😊"


def test_data_no_passado_formata_data():
    r = processar(_sv(sv_reason="data_no_passado", data_coleta="2026-07-01"))
    assert "01/07/2026" in r["mensagem_final"]


def test_dt_ds_inconsistente_calcula_dia_semana():
    # 2026-07-14 é terça
    r = processar(_sv(sv_reason="dt_ds_inconsistente", data_coleta="2026-07-14"))
    assert "14/07/2026 é uma terça-feira" in r["mensagem_final"]


def test_dt_ds_inconsistente_sem_data_generico():
    r = processar(_sv(sv_reason="dt_ds_inconsistente", data_coleta=""))
    assert r["mensagem_final"] == "Pode confirmar a data desejada? 😊"


def test_convenio_invalido_unidade_legado():
    r = processar(_sv(sv_reason="convenio_invalido_unidade", convenio="Bradesco", unidade_coleta="Tatuapé"))
    assert "Bradesco não é aceito em Tatuapé" in r["mensagem_final"]


def test_medico_invalido_unidade():
    r = processar(_sv(sv_reason="medico_invalido_unidade", medico_coleta="Dra. Juliana", unidade_coleta="Tatuapé"))
    assert "Dra. Juliana não atende em Tatuapé" in r["mensagem_final"]


def test_periodo_invalido_medico_dia_manha_rejeitado_oferece_tarde():
    r = processar(_sv(
        sv_reason="periodo_invalido_medico_dia", medico_coleta="Dr. Caio", unidade_coleta="Vila Olímpia",
        periodo_coleta="manha", dia_semana_coleta="ter",
    ))
    assert "atende terça-feira apenas à tarde" in r["mensagem_final"]


def test_periodo_invalido_medico_dia_tarde_rejeitado_oferece_manha():
    r = processar(_sv(
        sv_reason="periodo_invalido_medico_dia", medico_coleta="Dra. Giseli", unidade_coleta="Vila Olímpia",
        periodo_coleta="tarde", dia_semana_coleta="qua",
    ))
    assert "atende quarta-feira apenas à manhã" in r["mensagem_final"]


def test_troca_unidade_ilegal():
    r = processar(_sv(sv_reason="troca_unidade_ilegal", unidade_coleta="Tatuapé"))
    assert "mudar o atendimento para Tatuapé" in r["mensagem_final"]


def test_convenio_interno_vazando():
    r = processar(_sv(sv_reason="convenio_interno_vazando"))
    assert "Qual convênio você vai usar?" in r["mensagem_final"]


def test_nascimento_invalido():
    r = processar(_sv(sv_reason="nascimento_invalido"))
    assert "data de nascimento" in r["mensagem_final"]


def test_cpf_invalido():
    r = processar(_sv(sv_reason="cpf_invalido"))
    assert "11 números" in r["mensagem_final"]


def test_medico_interno_vazando():
    r = processar(_sv(sv_reason="medico_interno_vazando"))
    assert "Com qual médico você prefere?" in r["mensagem_final"]


def test_omint_premium_medico():
    r = processar(_sv(sv_reason="omint_premium_medico"))
    assert "Dra. Giseli" in r["mensagem_final"]


def test_omint_medico_invalido_legado_mesma_msg():
    r = processar(_sv(sv_reason="omint_medico_invalido"))
    assert "Dra. Giseli" in r["mensagem_final"]


def test_omint_skill_torcuato():
    r = processar(_sv(sv_reason="omint_skill_torcuato"))
    assert "Dr. Torcuato Sanchez Rojas Neto" in r["mensagem_final"]


def test_reason_desconhecida_fallback():
    r = processar(_sv(sv_reason="algo_nunca_visto"))
    assert r["mensagem_final"] == "Desculpe, houve um problema. Pode repetir? 😊"


def test_reason_vazia_fallback():
    r = processar(_sv())
    assert r["mensagem_final"] == "Desculpe, houve um problema. Pode repetir? 😊"
