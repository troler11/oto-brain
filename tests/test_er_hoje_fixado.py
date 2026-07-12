"""Teste do override `app.er.hoje_fixado` — necessário pro replay offline (scripts/replay_offline.py)
rodar turnos históricos com a data REAL do turno, não o wall-clock do processo."""

from datetime import datetime, timedelta, timezone

from app.er import _hoje_sp, hoje_fixado


def test_hoje_sp_sem_override_usa_relogio_real():
    antes = datetime.now(timezone.utc) - timedelta(hours=3)
    depois = _hoje_sp()
    assert abs((depois - antes).total_seconds()) < 5


def test_hoje_fixado_sobrescreve_durante_o_bloco():
    fixo = datetime(2026, 7, 5, 12, 0, 0)
    with hoje_fixado(fixo):
        assert _hoje_sp() == fixo


def test_hoje_fixado_restaura_depois_do_bloco():
    fixo = datetime(2026, 7, 5, 12, 0, 0)
    with hoje_fixado(fixo):
        pass
    assert _hoje_sp() != fixo


def test_hoje_fixado_aninhado_restaura_o_anterior():
    fixo1 = datetime(2026, 7, 1, 12, 0, 0)
    fixo2 = datetime(2026, 7, 9, 12, 0, 0)
    with hoje_fixado(fixo1):
        with hoje_fixado(fixo2):
            assert _hoje_sp() == fixo2
        assert _hoje_sp() == fixo1
