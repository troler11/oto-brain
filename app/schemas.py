from datetime import datetime
from typing import Any

from pydantic import BaseModel


class LogTurnoIn(BaseModel):
    """Corpo do nó 'Log Turno' do n8n — fire-and-forget, mesmo shape dos campos
    extraídos pelo backfill (scripts/backfill_n8n_executions.py), pra cair na
    mesma tabela conversas_log sem duplicar lógica de extração."""

    execution_id: str
    workflow_id: str
    status: str | None = None
    mode: str | None = None
    started_at: datetime | None = None
    stopped_at: datetime | None = None
    telefone: str | None = None
    texto_usuario: str | None = None
    extrair_rota: dict[str, Any] | None = None
    extrair_intencao_final: dict[str, Any] | None = None
    state_validator: dict[str, Any] | None = None
    mensagem_enviada: str | None = None
