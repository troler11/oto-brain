"""
Testes do port do State Validator (app/state_validator.py::validar_estado) —
DEPLOY/_proposed_State_Validator.js, 150 linhas: guards 1-2 (avanço indevido / data válida,
encadeados via elif no JS — mutuamente exclusivos), guard 4 (médico×unidade×período contra
GRADE), guard 5 (FIX_OMINT_V2), FIX_NASCIMENTO_INVALIDO, FIX_CPF_INVALIDO, guard 6 (campos
internos vazando -> BLOCK), guard 7 (troca ilegal de unidade -> BLOCK).
"""

from datetime import date

from app.state_validator import normalizar_ds, validar_estado

HOJE = date(2026, 7, 12)  # domingo


def _inp(**overrides):
    d = {
        "unidade_coleta": "",
        "data_coleta": "",
        "horario_coleta": "",
        "periodo_coleta": "",
        "convenio": "",
        "medico_coleta": "",
        "dia_semana_coleta": "",
        "dados": {},
        "nascimento_dependente": "",
        "cpf_dependente": "",
    }
    d.update(overrides)
    return d


def _run(inp=None, base=None, er_output=None, hoje=HOJE):
    return validar_estado(inp or _inp(), base or {}, er_output or {}, hoje=hoje)


# ---------- 1. Avanço indevido ----------

def test_confirmacao_sem_horario_reask():
    r = _run(_inp(dados={"i": "confirmacao"}))
    assert r.sv_result == "REASK"
    assert r.sv_reason == "confirmacao_sem_horario"
    assert r.sv_field == "h"


def test_execucao_sem_horario_nem_na_base_reask():
    r = _run(_inp(dados={"i": "execucao"}), base={"coleta_horario": ""})
    assert r.sv_result == "REASK"
    assert r.sv_reason == "execucao_sem_horario"


def test_execucao_sem_horario_no_inp_mas_com_horario_na_base_allow():
    r = _run(_inp(dados={"i": "execucao"}), base={"coleta_horario": "14:00"})
    assert r.sv_result == "ALLOW"


# ---------- 2. Data válida (elif do guard 1 — mutuamente exclusivo) ----------

def test_data_no_passado_reask():
    r = _run(_inp(data_coleta="2026-07-01"))
    assert r.sv_result == "REASK"
    assert r.sv_reason == "data_no_passado"


def test_data_dia_semana_inconsistente_reask():
    # 2026-07-13 é segunda; declarar "ter" é inconsistente
    r = _run(_inp(data_coleta="2026-07-13", dia_semana_coleta="ter"))
    assert r.sv_result == "REASK"
    assert r.sv_reason == "dt_ds_inconsistente"
    assert "seg" in r.sv_detail


def test_data_dia_semana_consistente_allow():
    r = _run(_inp(data_coleta="2026-07-13", dia_semana_coleta="seg"))
    assert r.sv_result == "ALLOW"


def test_data_com_ds_clear_nao_valida_allow():
    r = _run(_inp(data_coleta="2026-07-13", dia_semana_coleta="__CLEAR__"))
    assert r.sv_result == "ALLOW"


def test_guard2_nao_roda_se_guard1_ja_disparou():
    # i=confirmacao sem h E data no passado -> guard 1 vence (elif), sv_reason fica o do guard 1
    r = _run(_inp(dados={"i": "confirmacao"}, data_coleta="2026-07-01"))
    assert r.sv_reason == "confirmacao_sem_horario"


# ---------- 4. Médico válido por unidade / período ----------

def test_medico_nao_atende_unidade_reask():
    r = _run(_inp(medico_coleta="Dra. Giseli", unidade_coleta="Tatuapé", dia_semana_coleta="seg"))
    # giseli só atende Tatuapé na quinta -> não é isso que estamos testando aqui;
    # giseli EXISTE no Tatuapé então isso não dispara medico_invalido_unidade.
    assert r.sv_result == "ALLOW"


def test_medico_inexistente_na_unidade_reask():
    r = _run(_inp(medico_coleta="Dra. Juliana", unidade_coleta="Tatuapé"))
    assert r.sv_result == "REASK"
    assert r.sv_reason == "medico_invalido_unidade"


def test_medico_sem_preferencia_nao_valida():
    r = _run(_inp(medico_coleta="sem preferência", unidade_coleta="Tatuapé"))
    assert r.sv_result == "ALLOW"


def test_medico_clear_nao_valida_aqui_cai_no_block_depois():
    r = _run(_inp(medico_coleta="__CLEAR__", unidade_coleta="Tatuapé"))
    assert r.sv_result == "BLOCK"
    assert r.sv_reason == "medico_interno_vazando"


def test_periodo_invalido_pro_medico_no_dia_reask():
    # Giseli na Vila Olímpia atende quarta só de manhã -> pedir tarde nesse dia é inválido.
    r = _run(_inp(
        medico_coleta="Dra. Giseli", unidade_coleta="Vila Olímpia",
        dia_semana_coleta="qua", periodo_coleta="tarde",
    ))
    assert r.sv_result == "REASK"
    assert r.sv_reason == "periodo_invalido_medico_dia"


def test_dia_ausente_do_schedule_do_medico_nao_valida_periodo():
    # Quirk fiel do JS: se o dia nem existe no schedule do médico (persDia undefined), o guard
    # de período NÃO dispara (só valida quando o dia existe mas o período não bate) — segunda
    # não está no schedule da Giseli em VO, então isso passa direto sem REASK.
    r = _run(_inp(
        medico_coleta="Dra. Giseli", unidade_coleta="Vila Olímpia",
        dia_semana_coleta="seg", periodo_coleta="manha",
    ))
    assert r.sv_result == "ALLOW"


def test_periodo_valido_pro_medico_no_dia_allow():
    r = _run(_inp(
        medico_coleta="Dra. Giseli", unidade_coleta="Vila Olímpia",
        dia_semana_coleta="qua", periodo_coleta="manha",
    ))
    assert r.sv_result == "ALLOW"


def test_periodo_derivado_do_horario_ignora_periodo_coleta_stale():
    # horario 15:20 -> per="tarde" (FIX_PER_FROM_HORARIO), mesmo com periodo_coleta="manha" stale.
    # Giseli não atende tarde na quarta em VO -> deve REASK usando "tarde", não "manha".
    r = _run(_inp(
        medico_coleta="Dra. Giseli", unidade_coleta="Vila Olímpia",
        dia_semana_coleta="qua", periodo_coleta="manha", horario_coleta="15:20",
    ))
    assert r.sv_result == "REASK"
    assert "tarde" in r.sv_detail


def test_periodo_clear_nao_valida_marcador_de_limpeza():
    r = _run(_inp(
        medico_coleta="Dra. Giseli", unidade_coleta="Vila Olímpia",
        dia_semana_coleta="__CLEAR__", periodo_coleta="manha",
    ))
    assert r.sv_result == "ALLOW"


# ---------- 5. FIX_OMINT_V2 ----------

def test_omint_premium_medico_valido_allow():
    r = _run(_inp(medico_coleta="Dr. Elias", convenio="Omint Premium"))
    assert r.sv_result == "ALLOW"


def test_omint_premium_medico_invalido_reask():
    r = _run(_inp(medico_coleta="Dra. Juliana", convenio="Omint Premium"))
    assert r.sv_result == "REASK"
    assert r.sv_reason == "omint_premium_medico"


def test_omint_skill_so_torcuato_reask_se_outro():
    r = _run(_inp(medico_coleta="Dra. Giseli", convenio="Omint Skill"))
    assert r.sv_result == "REASK"
    assert r.sv_reason == "omint_skill_torcuato"


def test_omint_skill_torcuato_allow():
    r = _run(_inp(medico_coleta="Dr. Torcuato", convenio="Omint Skill"))
    assert r.sv_result == "ALLOW"


def test_omint_categoria_pendente_nao_valida_medico():
    r = _run(_inp(medico_coleta="Dra. Juliana", convenio="Omint"))
    assert r.sv_result == "ALLOW"


# ---------- FIX_NASCIMENTO_INVALIDO ----------

def test_nascimento_sem_digitos_reask():
    r = _run(_inp(nascimento_dependente="jjjj"))
    assert r.sv_result == "REASK"
    assert r.sv_reason == "nascimento_invalido"


def test_nascimento_valido_allow():
    r = _run(_inp(nascimento_dependente="17/12/1998"))
    assert r.sv_result == "ALLOW"


def test_nascimento_clear_passa_direto():
    r = _run(_inp(nascimento_dependente="__CLEAR__"))
    assert r.sv_result == "ALLOW"


# ---------- FIX_CPF_INVALIDO ----------

def test_cpf_com_8_digitos_reask():
    r = _run(_inp(cpf_dependente="12345678"))
    assert r.sv_result == "REASK"
    assert r.sv_reason == "cpf_invalido"
    assert "8 digitos" in r.sv_detail


def test_cpf_com_11_digitos_allow_mesmo_que_invalido_no_dv():
    # port fiel: só checa contagem de dígitos, NÃO o dígito verificador oficial.
    r = _run(_inp(cpf_dependente="11111111111"))
    assert r.sv_result == "ALLOW"


def test_cpf_clear_passa_direto():
    r = _run(_inp(cpf_dependente="__CLEAR__"))
    assert r.sv_result == "ALLOW"


# ---------- 6. Campos internos não persistem ----------

def test_convenio_reset_conv_block():
    r = _run(_inp(convenio="RESET_CONV"))
    assert r.sv_result == "BLOCK"
    assert r.sv_reason == "convenio_interno_vazando"


def test_convenio_part_interrogacao_nao_bloqueia():
    r = _run(_inp(convenio="PART?"))
    assert r.sv_result == "ALLOW"


# ---------- 7. Troca ilegal de unidade ----------

def test_troca_unidade_sem_tag_block():
    r = _run(
        _inp(unidade_coleta="Tatuapé"),
        base={"coleta_unidade": "Vila Olímpia"},
        er_output={"coleta_unidade": "Vila Olímpia", "texto_ia": ""},
    )
    assert r.sv_result == "BLOCK"
    assert r.sv_reason == "troca_unidade_ilegal"


def test_troca_unidade_com_tag_allow():
    r = _run(
        _inp(unidade_coleta="Tatuapé"),
        base={"coleta_unidade": "Vila Olímpia"},
        er_output={"coleta_unidade": "Vila Olímpia", "texto_ia": "[TROCA UNIDADE detectada]"},
    )
    assert r.sv_result == "ALLOW"


def test_mesma_unidade_allow():
    r = _run(
        _inp(unidade_coleta="Vila Olímpia"),
        base={"coleta_unidade": "Vila Olímpia"},
        er_output={"coleta_unidade": "Vila Olímpia", "texto_ia": ""},
    )
    assert r.sv_result == "ALLOW"


# ---------- fallback geral ----------

def test_tudo_vazio_allow():
    r = _run()
    assert r.sv_result == "ALLOW"
    assert r.sv_reason == ""


# ---------- normalizar_ds (nó 'Normalizar DS', pipeline real EIF1 -> Normalizar DS -> SV) ----------

def test_normalizar_ds_recalcula_a_partir_da_data():
    # 2026-07-13 é segunda; dia_semana_coleta cru (errado) vem "ter"
    out = normalizar_ds({"data_coleta": "2026-07-13", "dia_semana_coleta": "ter"})
    assert out["dia_semana_coleta"] == "seg"


def test_normalizar_ds_sem_data_nao_mexe_no_ds():
    out = normalizar_ds({"data_coleta": "", "dia_semana_coleta": "ter"})
    assert out["dia_semana_coleta"] == "ter"


def test_normalizar_ds_data_invalida_nao_mexe_no_ds():
    out = normalizar_ds({"data_coleta": "não é data", "dia_semana_coleta": "ter"})
    assert out["dia_semana_coleta"] == "ter"


def test_normalizar_ds_elimina_falso_reask_no_state_validator():
    # antes do normalizador, dt=segunda + ds=terça cru dispararia dt_ds_inconsistente
    inp_cru = _inp(data_coleta="2026-07-13", dia_semana_coleta="ter")
    assert _run(inp_cru).sv_result == "REASK"
    # depois do normalizador (pipeline real), ds passa a bater com dt -> ALLOW
    assert _run(normalizar_ds(inp_cru)).sv_result == "ALLOW"
