"""Helpers de normalização de texto compartilhados entre os ports (EIF1, ER)."""

import unicodedata


def _strip_accents(s: str) -> str:
    """Equivalente a .normalize('NFD').replace(/[\\u0300-\\u036f]/g, '')."""
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def _norm(s) -> str:
    """Normalização comum: lowercase, sem acento, trim."""
    return _strip_accents(str(s or "")).lower().strip()
