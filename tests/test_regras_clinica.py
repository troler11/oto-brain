"""Testes de app/regras_clinica.py — Fase 4 (mecanismo 3): fonte única de trechos de prompt
byte-idênticos que hoje estão duplicados em vários arquivos."""

from app.regras_clinica import REGRAS, aplicar_regras


def test_aplicar_regras_substitui_token_conhecido():
    texto = "antes {{REGRAS:convenios_lista}} depois"
    resultado = aplicar_regras(texto)
    assert "{{REGRAS:" not in resultado
    assert REGRAS["convenios_lista"] in resultado
    assert resultado.startswith("antes ")
    assert resultado.endswith(" depois")


def test_aplicar_regras_ignora_texto_sem_token():
    texto = "nada pra trocar aqui"
    assert aplicar_regras(texto) == texto


def test_aplicar_regras_substitui_varios_tokens_no_mesmo_texto():
    texto = "{{REGRAS:convenios_lista}}\n{{REGRAS:info_particular}}\n{{REGRAS:omint_categorias}}"
    resultado = aplicar_regras(texto)
    assert REGRAS["convenios_lista"] in resultado
    assert REGRAS["info_particular"] in resultado
    assert REGRAS["omint_categorias"] in resultado


def test_token_desconhecido_nao_e_alterado():
    texto = "{{REGRAS:nao_existe}}"
    assert aplicar_regras(texto) == texto
