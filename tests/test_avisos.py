"""
Testes dos avisos pequenos (app/avisos.py) — Aviso_Sucesso1.js (5L) e Aviso_Transferencia1.js (31L).
"""

from app.avisos import aviso_sucesso, aviso_transferencia


def test_aviso_sucesso_passthrough():
    r = aviso_sucesso({"texto_ia": "Consulta criada com sucesso! ✅"})
    assert r["mensagem_final"] == "Consulta criada com sucesso! ✅"


def test_aviso_sucesso_sem_dados():
    r = aviso_sucesso({})
    assert r["mensagem_final"] is None


def test_aviso_transferencia_com_paciente_sauda_pelo_primeiro_nome():
    r = aviso_transferencia({"telefone": "5511999999999"}, [{"nome": "Lucas Bueno"}])
    assert r["mensagem_final"].startswith("Olá, Lucas! 👋")
    assert "6️⃣ Confirmar consulta" in r["mensagem_final"]
    assert r["telefone"] == "5511999999999"


def test_aviso_transferencia_sem_paciente_saudacao_generica():
    r = aviso_transferencia({}, [])
    assert r["mensagem_final"].startswith("Olá! 👋")


def test_aviso_transferencia_preserva_base():
    r = aviso_transferencia({"coleta_unidade": "Tatuapé"}, None)
    assert r["coleta_unidade"] == "Tatuapé"
