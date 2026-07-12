"""
Testes de app/template_engine.py. Duas camadas:
  1. Cobertura de verdade: roda `renderizar()` sobre os 9 arquivos REAIS de prompts/ com um
     `base`/`base_mc` sintético cobrindo todo campo catalogado — se sobrar qualquer `{{ }}` sem
     resolver, `_resolver()` levanta ValueError e o teste falha. É a garantia de que nenhuma
     expressão nova escapa despercebida (como aconteceu até agora).
  2. Unitários dos resolvedores "ricos" (ternários, .replace, .split/.reverse/.join, .map/.join,
     JSON.stringify) — tradução fiel da semântica JS, testada isoladamente.
"""

import json
from pathlib import Path

import pytest

from app.dispatcher import PASTA_PROMPTS
from app.regras_clinica import aplicar_regras
from app.template_engine import renderizar

PACIENTES = [
    {"nome": "Miguel Bueno", "cpf": "11144477735", "nascimento": "17/12/2018",
     "id_tisaude": "999", "ultimo_medico": "Dra. Giseli Rebechi"},
    {"nome": "Ana Bueno", "cpf": "22233344456", "nascimento": "01/01/1990",
     "id_tisaude": "998", "ultimo_medico": ""},
]

BASE_MC = {
    "amanha": "2026-07-13", "hoje": "2026-07-12", "lista_med": "lista de médicos",
    "p1_section": "", "p3_menu": "", "prox_qua": "2026-07-15", "prox_qui": "2026-07-16",
    "prox_seg": "2026-07-13", "prox_sex": "2026-07-17", "prox_ter": "2026-07-14",
    "saudacao_section": "", "telefone": "5511999999999", "pacientes": PACIENTES,
}

BASE = {
    "cache_ativo": True, "unidade_cache": "Vila Olímpia", "coleta_conv_fail": 0,
    "coleta_convenio": "Omint Premium", "coleta_data": "2026-07-20", "coleta_dia_semana": "segunda",
    "coleta_dt_antiga": "2026-07-10", "coleta_email": "paciente@ex.com", "coleta_horario": "14:00",
    "coleta_hr_antiga": "10:00", "coleta_id_ag_antigo": "123", "coleta_md_antiga": "Dr. Elias",
    "coleta_medico": "Dra. Giseli Rebechi", "coleta_modo": 2, "coleta_periodo": "tarde",
    "coleta_terceiro": "true", "coleta_unidade": "Vila Olímpia", "cpf_dependente": "11144477735",
    "data_estendida": "2026-08-20", "data_ultima_consulta": "2026-06-01",
    "dia_semana_coleta": "segunda", "dia_slots": "14:00, 15:00", "grade_med": "grade texto",
    "medico_candidato_msg": "", "modo_agenda": 1, "motivo_humano": "",
    "nascimento_dependente": "17/12/2018", "nome_dependente": "Miguel Bueno", "nome": "Lucas Bueno",
    "proximas": {"qua": "2026-07-15", "qui": "2026-07-16", "seg": "2026-07-13",
                 "sex": "2026-07-17", "ter": "2026-07-14"},
    "proximo_mesmo_dia": "2026-07-27", "sessao_intencao": "coleta", "ultimo_convenio": "Omint",
    "ultimo_dia_texto": "segunda-feira, 20/07", "pacientes": PACIENTES,
}


@pytest.mark.parametrize("nome_arquivo", [p.name for p in PASTA_PROMPTS.glob("agente_*.txt")])
def test_renderiza_todos_os_prompts_reais_sem_sobra(nome_arquivo):
    # ordem real do pipeline: aplicar_regras() (tokens {{REGRAS:x}}) roda ANTES de renderizar()
    # (expressões {{ $json... }}), igual app.dispatcher.carregar_prompt().
    texto = aplicar_regras((PASTA_PROMPTS / nome_arquivo).read_text(encoding="utf-8"))
    resultado = renderizar(texto, BASE_MC, BASE)
    assert "{{" not in resultado, f"{nome_arquivo}: sobrou expressão não resolvida"


def test_campo_simples_com_default():
    assert renderizar("{{ $json.coleta_unidade || '' }}", {}, {}) == ""
    assert renderizar("{{ $json.coleta_unidade || '' }}", {}, {"coleta_unidade": "Tatuapé"}) == "Tatuapé"


def test_campo_montar_contexto():
    assert renderizar("{{ $('Montar Contexto').first().json.telefone }}", {"telefone": "5511988887777"}, {}) \
        == "5511988887777"


def test_default_numerico():
    assert renderizar("{{ $json.coleta_modo || 1 }}", {}, {}) == "1"
    assert renderizar("{{ $json.coleta_modo || 1 }}", {}, {"coleta_modo": 3}) == "3"


def test_cache_ativo_ternario_com_cache():
    texto = "{{ $json.cache_ativo ? '✅ ' + $json.unidade_cache + ' pronto' : '⬜ sem cache' }}"
    assert renderizar(texto, {}, {"cache_ativo": True, "unidade_cache": "Tatuapé"}) == "✅ Tatuapé pronto"


def test_cache_ativo_ternario_sem_cache():
    texto = "{{ $json.cache_ativo ? '✅ ' + $json.unidade_cache + ' pronto' : '⬜ sem cache' }}"
    assert renderizar(texto, {}, {"cache_ativo": False}) == "⬜ sem cache"


def test_data_br_com_valor():
    texto = "{{ $json.coleta_data ? $json.coleta_data.split('-').reverse().join('/') : '' }}"
    assert renderizar(texto, {}, {"coleta_data": "2026-07-20"}) == "20/07/2026"


def test_data_br_vazio():
    texto = "{{ $json.coleta_data ? $json.coleta_data.split('-').reverse().join('/') : '' }}"
    assert renderizar(texto, {}, {"coleta_data": ""}) == ""


def test_medico_ternario_com_fallback_texto():
    texto = "{{ $json.coleta_medico ? $json.coleta_medico : 'sem preferência' }}"
    assert renderizar(texto, {}, {"coleta_medico": "Dr. Elias"}) == "Dr. Elias"
    assert renderizar(texto, {}, {"coleta_medico": ""}) == "sem preferência"


def test_modo_e_dia_semana_combinado():
    texto = "{{ $json.coleta_modo == 2 && $json.coleta_dia_semana ? $json.coleta_dia_semana : '' }}"
    assert renderizar(texto, {}, {"coleta_modo": 2, "coleta_dia_semana": "terca"}) == "terca"
    assert renderizar(texto, {}, {"coleta_modo": 1, "coleta_dia_semana": "terca"}) == ""
    assert renderizar(texto, {}, {"coleta_modo": 2, "coleta_dia_semana": ""}) == ""


def test_nome_dependente_com_fallback_pro_primeiro_nome():
    texto = "{{ $json.nome_dependente || ($json.nome ? $json.nome.split('\\n')[0].split(' ')[0] : '') }}"
    assert renderizar(texto, {}, {"nome_dependente": "Miguel"}) == "Miguel"
    assert renderizar(texto, {}, {"nome_dependente": "", "nome": "Lucas Bueno\nOutraLinha"}) == "Lucas"
    assert renderizar(texto, {}, {"nome_dependente": "", "nome": ""}) == ""


def test_convenio_omint_categoria_vira_omint_puro():
    texto = "{{ ($json.coleta_convenio || '').replace(/^Omint\\s.+$/i, 'Omint') }}"
    assert renderizar(texto, {}, {"coleta_convenio": "Omint Premium"}) == "Omint"
    assert renderizar(texto, {}, {"coleta_convenio": "Porto Seguro"}) == "Porto Seguro"


def test_email_skip_vira_vazio():
    texto = "{{ ($json.coleta_email && $json.coleta_email !== 'SKIP') ? $json.coleta_email : '' }}"
    assert renderizar(texto, {}, {"coleta_email": "a@b.com"}) == "a@b.com"
    assert renderizar(texto, {}, {"coleta_email": "SKIP"}) == ""
    assert renderizar(texto, {}, {"coleta_email": ""}) == ""


def test_proximas_subcampo_com_e_sem_optional_chaining():
    base = {"proximas": {"seg": "2026-07-13"}}
    assert renderizar("{{ $json.proximas.seg || '' }}", {}, base) == "2026-07-13"
    assert renderizar("{{ $json.proximas?.qua || '' }}", {}, base) == ""


def test_json_stringify_pacientes():
    texto = "{{ JSON.stringify($json.pacientes || []) }}"
    resultado = renderizar(texto, {}, {"pacientes": PACIENTES})
    assert json.loads(resultado) == PACIENTES
    assert '": "' not in resultado and '", "' not in resultado  # compacto, sem espaço após : ou ,


def test_pacientes_map_join_nomes():
    texto = "{{ ($('Montar Contexto').first().json.pacientes || []).map(p => p.nome).join(', ') }}"
    assert renderizar(texto, BASE_MC, {}) == "Miguel Bueno, Ana Bueno"


def test_pacientes_map_join_para_qual():
    texto = "{{ 'Para qual? ' + ($('Montar Contexto').first().json.pacientes || []).map(p => p.nome).join(' ou ') + '? 😊' }}"
    assert renderizar(texto, BASE_MC, {}) == "Para qual? Miguel Bueno ou Ana Bueno? 😊"


def test_pacientes_map_join_detalhe():
    texto = (
        "{{ ($('Montar Contexto').first().json.pacientes || []).map(p => p.nome + ' → CPF: ' "
        "+ (p.cpf || '') + ' | NASC: ' + (p.nascimento || '') + ' | ID: ' + (p.id_tisaude || '') "
        "+ ' | ULTIMO_MED: ' + (p.ultimo_medico || '')).join('\\n') }}"
    )
    resultado = renderizar(texto, BASE_MC, {})
    linhas = resultado.split("\n")
    assert linhas[0] == "Miguel Bueno → CPF: 11144477735 | NASC: 17/12/2018 | ID: 999 | ULTIMO_MED: Dra. Giseli Rebechi"
    assert linhas[1] == "Ana Bueno → CPF: 22233344456 | NASC: 01/01/1990 | ID: 998 | ULTIMO_MED: "


def test_primeiro_paciente_campo_com_default():
    texto = "{{ (($('Montar Contexto').first().json.pacientes || [])[0] || {}).email || '' }}"
    assert renderizar(texto, {"pacientes": [{"email": "a@b.com"}]}, {}) == "a@b.com"
    assert renderizar(texto, {"pacientes": []}, {}) == ""
    assert renderizar(texto, {"pacientes": [{"nome": "sem email aqui"}]}, {}) == ""


def test_primeiro_paciente_nome_default_voce():
    texto = "{{ (($('Montar Contexto').first().json.pacientes || [])[0] || {}).nome || 'você' }}"
    assert renderizar(texto, {"pacientes": [{"nome": "Miguel"}]}, {}) == "Miguel"
    assert renderizar(texto, {"pacientes": []}, {}) == "você"


def test_expressao_sem_resolvedor_falha_alto():
    with pytest.raises(ValueError):
        renderizar("{{ $json.algumCampoComExpressaoNuncaVista().foo() }}", {}, {})
