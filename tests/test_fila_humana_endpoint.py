"""Testes do endpoint POST /fila-humana (app/main.py) — DB mockada, só a fiação HTTP + params
repassados corretos pra app.fila_humana/app.db (a lógica de cálculo já é testada em
tests/test_fila_humana.py)."""

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

WHATSAPP_INFO = {"SenderAlt": "5511999999999:1@s.whatsapp.net", "from": ""}

PAYLOAD = {
    "telefone": "5511999999999",
    "whatsapp_info": WHATSAPP_INFO,
    "base": {"intencao_rapida": "humano", "unidade_cache": "Vila Olímpia"},
    "extrair_intencao_final": {
        "intencao": "humano",
        "dados": {},
        "eh_terceiro": False,
        "nome_dependente": "",
        "cpf_dependente": "",
        "nascimento_dependente": "",
        "motivo_cancelamento": "",
        "motivo_humano": "Quer falar com atendente",
    },
}


def test_fila_humana_reseta_sessao_e_cria_fila():
    with patch("app.main.get_connection") as mock_conn, \
         patch("app.main.resetar_sessao_humano") as mock_reset, \
         patch("app.main.criar_fila") as mock_criar:
        mock_conn.return_value.__enter__.return_value = MagicMock()
        r = client.post("/fila-humana", json=PAYLOAD)

    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
    mock_reset.assert_called_once()
    assert mock_reset.call_args.args[1] == "5511999999999"
    mock_criar.assert_called_once()
    params = mock_criar.call_args.args[1]
    assert params["motivo_humano"] == "Quer falar com atendente"
    assert params["telefone"] == "5511999999999"


def test_fila_humana_sem_extrair_intencao_final_usa_fallback_do_base():
    payload = {**PAYLOAD, "extrair_intencao_final": None, "base": {"motivo_humano": "Ligação caiu"}}
    with patch("app.main.get_connection") as mock_conn, \
         patch("app.main.resetar_sessao_humano"), \
         patch("app.main.criar_fila") as mock_criar:
        mock_conn.return_value.__enter__.return_value = MagicMock()
        r = client.post("/fila-humana", json=payload)

    assert r.status_code == 200
    params = mock_criar.call_args.args[1]
    assert params["motivo_humano"] == "Ligação caiu"


def test_fila_humana_campo_obrigatorio_faltando_rejeita():
    r = client.post("/fila-humana", json={"whatsapp_info": WHATSAPP_INFO})
    assert r.status_code == 422


def test_fila_humana_erro_db_propaga_5xx():
    """Diferente de /log-turno: mutação real de fila humana não é fire-and-forget."""
    client_sem_raise = TestClient(app, raise_server_exceptions=False)
    with patch("app.main.get_connection", side_effect=Exception("db down")):
        r = client_sem_raise.post("/fila-humana", json=PAYLOAD)
    assert r.status_code == 500
