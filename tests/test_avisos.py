"""
Testes dos avisos pequenos (app/avisos.py) — Aviso_Sucesso1.js (5L), Aviso_Transferencia1.js (31L)
e o gate Fora do Expediente?/Aviso Expediente (Fora).
"""

from datetime import datetime, timezone

from app.avisos import aviso_fora_expediente, aviso_sucesso, aviso_transferencia, dentro_do_expediente


def test_aviso_sucesso_passthrough():
    r = aviso_sucesso({"texto_ia": "Consulta criada com sucesso! ✅"})
    assert r["mensagem_final"] == "Consulta criada com sucesso! ✅"


def test_aviso_sucesso_sem_dados():
    r = aviso_sucesso({})
    assert r["mensagem_final"] is None


def test_aviso_transferencia_com_paciente_sauda_pelo_primeiro_nome():
    r = aviso_transferencia({"telefone": "5511999999999"}, [{"nome": "Lucas Bueno"}])
    assert r["mensagem_final"].startswith("Olá, Lucas! 👋")
    assert "4️⃣ Troca de guias e documentos" in r["mensagem_final"]
    assert "5️⃣" not in r["mensagem_final"]
    assert r["telefone"] == "5511999999999"


def test_aviso_transferencia_sem_paciente_saudacao_generica():
    r = aviso_transferencia({}, [])
    assert r["mensagem_final"].startswith("Olá! 👋")


def test_aviso_transferencia_preserva_base():
    r = aviso_transferencia({"coleta_unidade": "Tatuapé"}, None)
    assert r["coleta_unidade"] == "Tatuapé"


def test_dentro_do_expediente_segunda_10h_sp():
    # 2026-07-13 é segunda; 13h UTC = 10h SP (offset fixo -3).
    agora = datetime(2026, 7, 13, 13, 0, tzinfo=timezone.utc)
    assert dentro_do_expediente(agora) is True


def test_fora_do_expediente_segunda_19h_sp():
    agora = datetime(2026, 7, 13, 22, 0, tzinfo=timezone.utc)  # 19h SP
    assert dentro_do_expediente(agora) is False


def test_fora_do_expediente_sabado():
    agora = datetime(2026, 7, 18, 13, 0, tzinfo=timezone.utc)  # sábado, 10h SP
    assert dentro_do_expediente(agora) is False


def test_dentro_do_expediente_limite_8h_inclusivo():
    agora = datetime(2026, 7, 13, 11, 0, tzinfo=timezone.utc)  # 8h SP em ponto
    assert dentro_do_expediente(agora) is True


def test_fora_do_expediente_limite_18h_exclusivo():
    agora = datetime(2026, 7, 13, 21, 0, tzinfo=timezone.utc)  # 18h SP em ponto
    assert dentro_do_expediente(agora) is False


def test_aviso_fora_expediente_mensagem():
    r = aviso_fora_expediente()
    assert "segunda a sexta" in r["mensagem_final"]
    assert "8h às 18h" in r["mensagem_final"]
