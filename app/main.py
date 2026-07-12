import logging

from fastapi import FastAPI

from app.db import get_connection, gravar_turno
from app.schemas import LogTurnoIn

logger = logging.getLogger("oto-brain")

app = FastAPI(title="oto-brain")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/log-turno")
def log_turno(turno: LogTurnoIn) -> dict:
    """Fire-and-forget do n8n (nó 'Log Turno'). Falha aqui NUNCA deve derrubar o turno do
    paciente — o n8n chama isso com 'Continue on Fail' / execução em paralelo. Erro é só
    logado, nunca propagado como 5xx que travaria o fluxo principal."""
    try:
        with get_connection() as conn:
            inseriu = gravar_turno(conn, turno.model_dump())
        return {"status": "ok", "inserted": inseriu}
    except Exception:
        logger.exception("falha ao gravar turno %s", turno.execution_id)
        return {"status": "erro_logado"}
