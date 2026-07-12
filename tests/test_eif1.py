"""
Testes do port do EIF1 (app/eif1.py). Cobre os casos-fix reais desta sessão (mesmos cenários
dos validate_*.js do scratchpad) + os algoritmos mais arriscados da tradução JS→Python
(CPF, correção de data por dia da semana, acentuação).
"""

from datetime import datetime, timezone

from app.eif1 import _cpf_digitos_validos, _norm, _strip_accents, processar

CPF_VALIDO = "11144477735"  # CPF de teste classico (111.444.777-35), digitos verificadores OK

ER_BASE = {
    "telefone": "5511900000000",
    "intencao_rapida": "coleta",
    "sessao_intencao": "coleta",
    "coleta_terceiro": "",
    "nome_dependente": "",
    "cpf_dependente": "",
    "nascimento_dependente": "",
    "coleta_convenio": "",
    "coleta_unidade": "",
    "coleta_data": "",
    "coleta_periodo": "",
    "coleta_horario": "",
    "coleta_medico": "",
    "coleta_modo": 0,
    "coleta_dia_semana": "",
    "texto_ia": "",
    "pacientes": [],
}


def _er(**overrides):
    return {**ER_BASE, **overrides}


# ---------- helpers de baixo nivel ----------

def test_strip_accents():
    assert _strip_accents("Vila Olímpia") == "Vila Olimpia"
    assert _strip_accents("São Paulo") == "Sao Paulo"


def test_norm():
    assert _norm("  SEM PREFERÊNCIA  ") == "sem preferencia"


def test_cpf_valido():
    assert _cpf_digitos_validos(CPF_VALIDO) is True


def test_cpf_digito_verificador_errado():
    assert _cpf_digitos_validos("11144477736") is False


def test_cpf_todos_digitos_iguais():
    assert _cpf_digitos_validos("11111111111") is False


def test_cpf_tamanho_errado():
    assert _cpf_digitos_validos("123") is False


# ---------- Modo B ($$$) — caminho feliz ----------

# evita FIX_SAUDACAO_PRIMEIRO_CONTATO nos testes que nao testam saudacao — precisa de
# sessao_atualizada_em RECENTE (sem ela, idade_sd=Infinity > 12h e ainda conta como nova,
# igual ao JS: `_sessSD.sessao_atualizada_em ? (...) : Infinity`).
SESSAO_EXISTENTE = {
    "sessao_intencao": "coleta",
    "sessao_atualizada_em": datetime.now(timezone.utc).isoformat(),
}


def test_modo_b_basico():
    raw = 'Confirmado! $$${"i":"concluido","d":"JOAO SILVA","c":"","n":"","conv":"","unid":"","dt":"","per":"","h":"","med":"","modo":0,"ds":""}'
    r = processar(raw, _er(), SESSAO_EXISTENTE)
    assert r.intencao == "concluido"
    assert r.texto_ia == "Confirmado!"
    assert r.ir_concluido is True


def test_saudacao_primeiro_contato_sem_sessao():
    raw = 'Encontrei horários. $$${"i":"agenda","d":"","c":"","n":"","conv":"","unid":"","dt":"","per":"","h":"","med":"","modo":0,"ds":""}'
    r = processar(raw, _er())  # sem carregar_sessao => sessao nova
    assert r.texto_ia.startswith(("Bom dia", "Boa tarde", "Boa noite"))
    assert "assistente virtual da Oto-SP" in r.texto_ia


# ---------- FIX_LEAK_JSON_CLASSIFICADOR ----------

def test_leak_json_classificador():
    raw = '{"intencao_rapida":"triagem","rota_agente":0,"eh_confirmacao":false}'
    r = processar(raw, _er(intencao_rapida="agenda", coleta_medico="Dr. Elias"))
    assert "não entendi" in r.texto_ia
    assert r.dados["i"] == "agenda"


# ---------- FIX_67351 — erro de framework nunca vaza ----------

def test_agent_stopped_max_iterations():
    raw = "Agent stopped due to max iterations."
    r = processar(raw, _er(nome_dependente="Heitor Didone Alzani", coleta_medico="Dra. Juliana Paulino do Amaral"))
    assert r.intencao == "humano"
    assert "max iterations" not in r.texto_ia
    assert "problema técnico" in r.texto_ia
    assert "ERRO TECNICO" in r.dados["motivo"]
    assert r.medico_coleta == "Dra. Juliana Paulino do Amaral"  # dados preservados


def test_agent_stopped_variante():
    r = processar("Agent stopped due to early stopping.", _er())
    assert r.intencao == "humano"


# ---------- FIX_FALLBACK_SEM_BBB ----------

def test_fallback_sem_bbb_texto_livre():
    r = processar(
        "Encontrei horários para 24/07: 15:00, 15:20. Qual prefere?",
        _er(intencao_rapida="execucao"),
        SESSAO_EXISTENTE,
    )
    assert r.texto_ia.startswith("Encontrei horários")
    assert r.intencao == "execucao"


# ---------- FIX_OFERTA_HUMANO_CANONICO / FIX_67529 ----------

def test_oferta_humano_marcador():
    raw = 'Infelizmente não tenho essa informação. Deseja falar com um atendente? $$${"i":"triagem","d":"","c":"","n":"","conv":"","unid":"","dt":"","per":"","h":"","med":"","modo":0,"ds":""}'
    r = processar(raw, _er())
    assert r.intencao == "oferta_humano"


def test_oferta_agendar_marcador():
    raw = 'Atendemos Porto Seguro e Itaú. Posso te ajudar a agendar? $$${"i":"triagem","d":"","c":"","n":"","conv":"","unid":"","dt":"","per":"","h":"","med":"","modo":0,"ds":""}'
    r = processar(raw, _er())
    assert r.intencao == "oferta_agendar"


def test_oferta_agendar_nao_sobrescreve_humano():
    raw = 'Posso te ajudar a agendar? $$${"i":"humano","d":"","c":"","n":"","conv":"","unid":"","dt":"","per":"","h":"","med":"","modo":0,"ds":""}'
    r = processar(raw, _er())
    assert r.intencao == "humano"


# ---------- FIX_65707 — canonicalização de médico truncado ----------

def test_medico_truncado_canonicaliza():
    raw = 'Ok! $$${"i":"agenda","d":"X","c":"","n":"","conv":"","unid":"Vila Olímpia","dt":"2026-07-20","per":"tarde","h":"","med":"Dra. Stephanie Rugeri","modo":3,"ds":"seg"}'
    r = processar(raw, _er())
    assert r.dados["med"] == "Dra. Stephanie Rugeri de Souza"


def test_medico_sem_preferencia_nao_canonicaliza():
    raw = 'Ok! $$${"i":"agenda","d":"X","c":"","n":"","conv":"","unid":"","dt":"","per":"","h":"","med":"sem preferencia","modo":1,"ds":""}'
    r = processar(raw, _er())
    assert r.dados["med"] == "sem preferencia"


# ---------- FIX_64079 / FIX_65038 — ENCERRAMENTO vence eco do LLM ----------

def test_encerramento_forca_concluido():
    raw = 'Prontinho! $$${"i":"triagem","d":"","c":"","n":"","conv":"","unid":"","dt":"","per":"","h":"","med":"","modo":0,"ds":""}'
    r = processar(raw, _er(texto_ia="[ENCERRAMENTO CANCELAMENTO RESOLVIDO] obrigada"))
    assert r.intencao == "concluido"
    assert r.dados["i"] == "concluido"


def test_encerramento_nao_sobrescreve_humano():
    raw = 'Ok $$${"i":"humano","d":"","c":"","n":"","conv":"","unid":"","dt":"","per":"","h":"","med":"","modo":0,"ds":""}'
    r = processar(raw, _er(texto_ia="[ENCERRAMENTO] x"))
    assert r.intencao == "humano"


# ---------- CPF/nascimento — backstops de segurança ----------

def test_cpf_valido_passa_intacto():
    raw = f'Ok $$${{"i":"coleta","d":"X","c":"{CPF_VALIDO}","n":"","conv":"","unid":"","dt":"","per":"","h":"","med":"","modo":0,"ds":""}}'
    r = processar(raw, _er())
    assert r.cpf_dependente == CPF_VALIDO


def test_cpf_invalido_e_descartado():
    raw = 'Ok $$${"i":"coleta","d":"X","c":"11144477736","n":"","conv":"","unid":"","dt":"","per":"","h":"","med":"","modo":0,"ds":""}'
    r = processar(raw, _er())
    assert r.cpf_dependente == ""


def test_cpf_formatado_normaliza_para_digitos():
    raw = 'Ok $$${"i":"coleta","d":"X","c":"111.444.777-35","n":"","conv":"","unid":"","dt":"","per":"","h":"","med":"","modo":0,"ds":""}'
    r = processar(raw, _er())
    assert r.cpf_dependente == CPF_VALIDO


def test_nascimento_valido_normaliza():
    raw = 'Ok $$${"i":"coleta","d":"X","c":"","n":"5/1/1990","conv":"","unid":"","dt":"","per":"","h":"","med":"","modo":0,"ds":""}'
    r = processar(raw, _er())
    assert r.nascimento_dependente == "05/01/1990"


def test_nascimento_lixo_e_descartado():
    raw = 'Ok $$${"i":"coleta","d":"X","c":"","n":"LUCAS BURNO","conv":"","unid":"","dt":"","per":"","h":"","med":"","modo":0,"ds":""}'
    r = processar(raw, _er())
    assert r.nascimento_dependente == ""


def test_nascimento_futuro_e_descartado():
    raw = 'Ok $$${"i":"coleta","d":"X","c":"","n":"01/01/2099","conv":"","unid":"","dt":"","per":"","h":"","med":"","modo":0,"ds":""}'
    r = processar(raw, _er())
    assert r.nascimento_dependente == ""


# ---------- FIX_DT_DS_MISMATCH ----------

def test_dt_ds_mismatch_corrige_para_frente():
    # 2026-07-20 e uma segunda-feira; paciente/ER pediu "quarta" -> corrige pra 22/07
    raw = 'Ok $$${"i":"agenda","d":"X","c":"","n":"","conv":"","unid":"","dt":"2026-07-20","per":"","h":"","med":"","modo":0,"ds":"quarta"}'
    r = processar(raw, _er())
    assert r.data_coleta == "2026-07-22"


# ---------- FIX_MODO1_DT_AMANHA ----------

def test_modo1_sem_data_forca_amanha():
    raw = 'Ok $$${"i":"agenda","d":"X","c":"","n":"","conv":"","unid":"","dt":"","per":"","h":"","med":"sem preferencia","modo":1,"ds":""}'
    r = processar(raw, _er())
    assert r.data_coleta != ""
    assert r.modo_coleta == 1


# ---------- FIX_CLEAR_FIELDS ----------

def test_clear_fields_propaga_marcador():
    raw = 'Buscando $$${"i":"agenda","d":"","c":"","n":"","conv":"","unid":"","dt":"","per":"","h":"","med":"","modo":0,"ds":""}'
    er = _er(_clear_pm={"dt": 1, "ds": 1, "per": 1})
    r = processar(raw, er)
    assert r.data_coleta == "__CLEAR__"
    assert r.dia_semana_coleta == "__CLEAR__"
    assert r.periodo_coleta == "__CLEAR__"


# ---------- FIX_TITULAR_DCN ----------

def test_titular_dcn_preenche_paciente_unico():
    raw = 'Ok $$${"i":"agenda","d":"","c":"","n":"","conv":"","unid":"Vila Olímpia","dt":"","per":"","h":"","med":"","modo":0,"ds":""}'
    er = _er(pacientes=[{"nome": "MARIA SILVA", "cpf": CPF_VALIDO, "nascimento": "01/01/1990", "id_tisaude": 123}])
    r = processar(raw, er)
    assert r.nome_dependente == "MARIA SILVA"
    assert r.cpf_dependente == CPF_VALIDO
    assert r.id_tisaude_coleta == "123"
