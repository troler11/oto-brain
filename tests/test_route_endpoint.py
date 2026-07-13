"""Testes do endpoint POST /route (app/main.py) — DB e pipeline mockados, só a fiação HTTP."""

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.pipeline import ResultadoTurno

client = TestClient(app)

PAYLOAD = {
    "telefone": "5511999999999",
    "mensagem_agrupada": "oi",
    "whatsapp_info": {"SenderAlt": "", "Chat": "5511999999999@s.whatsapp.net"},
}


def test_route_chama_pipeline_e_devolve_resultado():
    resultado = ResultadoTurno(
        mensagem="Oi! Como posso ajudar? 😊", intencao="triagem", sv_result="ALLOW", sv_reason="",
        rota_agente=0, agente_usado="triagem", deve_resetar_sessao=False, dados={"unidade_coleta": ""},
    )
    with patch("app.main.get_connection") as mock_conn, \
         patch("app.main.carregar_sessao", return_value=None), \
         patch("app.main.carregar_historico_conversa", return_value=[]), \
         patch("app.main.carregar_memoria_paciente", return_value=None), \
         patch("app.main.processar_turno", return_value=resultado) as mock_pipeline:
        mock_conn.return_value.__enter__.return_value = MagicMock()
        r = client.post("/route", json=PAYLOAD)

    assert r.status_code == 200
    body = r.json()
    assert body["mensagem"] == "Oi! Como posso ajudar? 😊"
    assert body["intencao"] == "triagem"
    assert body["rota_agente"] == 0
    assert body["agente_usado"] == "triagem"
    assert body["deve_resetar_sessao"] is False
    mock_pipeline.assert_called_once()
    kwargs = mock_pipeline.call_args.kwargs
    assert kwargs["mensagem_agrupada"] == "oi"
    assert kwargs["sessao"] is None
    assert kwargs["historico"] == []
    assert kwargs["memoria_paciente"] is None


def test_route_passa_sessao_e_historico_carregados_pro_pipeline():
    sessao = {"sessao_intencao": "coleta", "sessao_rota": 2}
    historico = [{"role": "user", "content": "mensagem antiga"}]
    resultado = ResultadoTurno(
        mensagem="ok", intencao="coleta", sv_result="ALLOW", sv_reason="", rota_agente=2,
        agente_usado="coleta_0pac", deve_resetar_sessao=False,
    )
    with patch("app.main.get_connection") as mock_conn, \
         patch("app.main.carregar_sessao", return_value=sessao), \
         patch("app.main.carregar_historico_conversa", return_value=historico), \
         patch("app.main.carregar_memoria_paciente", return_value=None), \
         patch("app.main.processar_turno", return_value=resultado) as mock_pipeline:
        mock_conn.return_value.__enter__.return_value = MagicMock()
        r = client.post("/route", json=PAYLOAD)

    assert r.status_code == 200
    kwargs = mock_pipeline.call_args.kwargs
    assert kwargs["sessao"] == sessao
    assert kwargs["historico"] == historico


def test_route_campo_obrigatorio_faltando_rejeita():
    r = client.post("/route", json={"telefone": "5511999999999"})
    assert r.status_code == 422


def test_route_5_sem_agente_devolve_agente_usado_none():
    resultado = ResultadoTurno(
        mensagem="", intencao="confirmar_presenca", sv_result="", sv_reason="", rota_agente=5,
        agente_usado=None, deve_resetar_sessao=False,
    )
    with patch("app.main.get_connection") as mock_conn, \
         patch("app.main.carregar_sessao", return_value=None), \
         patch("app.main.carregar_historico_conversa", return_value=[]), \
         patch("app.main.carregar_memoria_paciente", return_value=None), \
         patch("app.main.processar_turno", return_value=resultado):
        mock_conn.return_value.__enter__.return_value = MagicMock()
        r = client.post("/route", json={**PAYLOAD, "mensagem_agrupada": "queria um encaixe"})

    assert r.status_code == 200
    assert r.json()["agente_usado"] is None
    assert r.json()["rota_agente"] == 5
