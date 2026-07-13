"""
Testes de app/navegar_agenda.py::processar — port fiel do node 'Calcular Índice e Montar
Resposta1' (+ 'Sem Cache Ativo1') do sub-workflow 'Ferramenta - Navegar Agenda'
(iSO191fJ9Q1FMmVZ). Função pura, sem Postgres/rede.
"""

from app.navegar_agenda import processar

DIAS = [
    {"data": "2026-07-20", "medicos": [{"medico": "Giseli Rebechi", "horarios": "09:00"}]},
    {"data": "2026-07-21", "medicos": [{"medico": "Elias Lobo Braga", "horarios": "10:00"}]},
    {"data": "2026-07-27", "medicos": [{"medico": "Giseli Rebechi", "horarios": "14:00"}]},
]


def _cache(indice=0, dias=DIAS):
    return {"agenda_json": {"dias": dias}, "indice_atual": indice}


# ---------- SEM_CACHE ----------

def test_sem_cache_row_retorna_sem_cache():
    r = processar(None, "ver")
    assert r["status"] == "SEM_CACHE"


def test_cache_sem_agenda_json_retorna_sem_cache():
    r = processar({"agenda_json": None, "indice_atual": 0}, "ver")
    assert r["status"] == "SEM_CACHE"


# ---------- ver ----------

def test_ver_mantem_indice_atual():
    r = processar(_cache(indice=1), "ver")
    assert r == {"status": "OK", "indice_atual": 1, "total_dias": 3, "dias_restantes": 1, "dia": DIAS[1]}


def test_aceita_proximos_dias_formato_antigo():
    cache = {"agenda_json": {"proximos_dias": DIAS}, "indice_atual": 0}
    r = processar(cache, "ver")
    assert r["dia"] == DIAS[0]


# ---------- avancar ----------

def test_avancar_incrementa_indice():
    r = processar(_cache(indice=0), "avancar")
    assert r["status"] == "OK"
    assert r["indice_atual"] == 1
    assert r["dia"] == DIAS[1]


def test_avancar_alem_do_ultimo_dia_retorna_esgotado():
    r = processar(_cache(indice=2), "avancar")
    assert r["status"] == "ESGOTADO"
    assert r["indice_atual"] == 2
    assert r["proxima_data_busca"] == "2026-07-27"
    assert r["total_dias"] == 3


# ---------- voltar ----------

def test_voltar_decrementa_indice():
    r = processar(_cache(indice=2), "voltar")
    assert r["indice_atual"] == 1


def test_voltar_no_indice_0_nao_fica_negativo():
    r = processar(_cache(indice=0), "voltar")
    assert r["indice_atual"] == 0


# ---------- ir_para (data exata) ----------

def test_ir_para_data_exata_no_cache():
    r = processar(_cache(indice=0), "ir_para", "2026-07-27")
    assert r["status"] == "OK"
    assert r["indice_atual"] == 2


def test_ir_para_data_fora_do_cache_retorna_data_nao_encontrada():
    r = processar(_cache(indice=0), "ir_para", "2026-08-15")
    assert r["status"] == "DATA_NAO_ENCONTRADA"
    assert r["data_solicitada"] == "2026-08-15"
    assert r["dia"] is None


# ---------- ir_para (nome de dia da semana) ----------

def test_ir_para_nome_dia_semana_resolve_primeira_data():
    # 2026-07-20 é segunda-feira
    r = processar(_cache(indice=0), "ir_para", "segunda")
    assert r["status"] == "OK"
    assert r["dia"]["data"] == "2026-07-20"


def test_ir_para_nome_dia_semana_sem_match_no_cache():
    r = processar(_cache(indice=0), "ir_para", "domingo")
    assert r["status"] == "DATA_NAO_ENCONTRADA"


# ---------- cache vazio ----------

def test_cache_com_dias_vazio_retorna_esgotado():
    r = processar(_cache(indice=0, dias=[]), "ver")
    assert r["status"] == "ESGOTADO"
    assert r["proxima_data_busca"] is None


def test_acao_desconhecida_cai_no_default_ver():
    r = processar(_cache(indice=1), "qualquer_coisa")
    assert r["status"] == "OK"
    assert r["indice_atual"] == 1
