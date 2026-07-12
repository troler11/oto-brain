"""Helpers de normalização de texto e validação compartilhados entre os ports (EIF1, ER)."""

import re
import unicodedata


def _strip_accents(s: str) -> str:
    """Equivalente a .normalize('NFD').replace(/[\\u0300-\\u036f]/g, '')."""
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def _norm(s) -> str:
    """Normalização comum: lowercase, sem acento, trim."""
    return _strip_accents(str(s or "")).lower().strip()


def _cpf_digitos_validos(digs: str) -> bool:
    """Algoritmo oficial de dígito verificador da Receita — usado em EIF1 e nos guards de
    coleta de identidade do ER (FIX_MULTI_DADOS, FIX_IDENTIDADE_RESIDUAL, etc)."""
    if not re.fullmatch(r"\d{11}", digs) or re.fullmatch(r"(\d)\1{10}", digs):
        return False
    s1 = sum(int(digs[i]) * (10 - i) for i in range(9))
    d1 = (s1 * 10) % 11
    if d1 == 10:
        d1 = 0
    s2 = sum(int(digs[i]) * (11 - i) for i in range(10))
    d2 = (s2 * 10) % 11
    if d2 == 10:
        d2 = 0
    return d1 == int(digs[9]) and d2 == int(digs[10])
