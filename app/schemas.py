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


class RouteIn(BaseModel):
    """Corpo do endpoint /route (Fase 3, cérebro do turno). n8n continua fazendo o transporte
    (webhook WAHA, buffer/dedup, as 3 buscas TiSaude, envio da resposta) — só troca o Extrair
    Rota + Agente + EIF1 + State Validator (Code/LangChain nodes) por esta chamada HTTP."""

    telefone: str
    mensagem_agrupada: str
    busca_paciente_id1: list[dict[str, Any]] | None = None
    busca_paciente_telefone: dict[str, Any] | None = None
    extrair_medico_timeline: list[dict[str, Any]] | None = None
    whatsapp_info: dict[str, Any] | None = None
    has_media: bool = False


class RouteOut(BaseModel):
    """Resposta do /route: o que n8n precisa pra mandar a mensagem e persistir a sessão (com
    os nós SQL que já existem em produção — Salvar Sessao etc; este endpoint não persiste)."""

    mensagem: str
    intencao: str
    sv_result: str
    sv_reason: str
    rota_agente: int
    agente_usado: str | None
    deve_resetar_sessao: bool
    dados: dict[str, Any] = {}
