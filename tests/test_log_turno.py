from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

PAYLOAD = {
    "execution_id": "12345",
    "workflow_id": "oX6ePJbAVF7C0NoX",
    "status": "success",
    "mode": "webhook",
    "telefone": "5511999999999",
    "texto_usuario": "sim",
    "extrair_rota": {"texto_ia": "[TAG] sim"},
    "extrair_intencao_final": {"intencao": "agenda"},
    "state_validator": {"sv_result": "ALLOW"},
    "mensagem_enviada": "Qual horário prefere?",
}


def test_log_turno_grava_com_sucesso():
    with patch("app.main.get_connection") as mock_conn, \
         patch("app.main.gravar_turno", return_value=True) as mock_gravar:
        mock_conn.return_value.__enter__.return_value = MagicMock()
        r = client.post("/log-turno", json=PAYLOAD)
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "inserted": True}
    mock_gravar.assert_called_once()


def test_log_turno_campos_minimos():
    with patch("app.main.get_connection") as mock_conn, \
         patch("app.main.gravar_turno", return_value=True):
        mock_conn.return_value.__enter__.return_value = MagicMock()
        r = client.post("/log-turno", json={"execution_id": "1", "workflow_id": "w"})
    assert r.status_code == 200


def test_log_turno_falha_db_nao_propaga_erro():
    """Regra de ouro: erro de DB nunca vira 5xx que travaria o fire-and-forget do n8n."""
    with patch("app.main.get_connection", side_effect=Exception("db down")):
        r = client.post("/log-turno", json=PAYLOAD)
    assert r.status_code == 200
    assert r.json() == {"status": "erro_logado"}


def test_log_turno_sem_execution_id_rejeita():
    r = client.post("/log-turno", json={"workflow_id": "w"})
    assert r.status_code == 422
