import logging

from fastapi import FastAPI

from app.db import carregar_historico_conversa, carregar_memoria_paciente, carregar_sessao, get_connection, gravar_turno
from app.pipeline import processar_turno
from app.schemas import LogTurnoIn, RouteIn, RouteOut

logger = logging.getLogger("oto-brain")

app = FastAPI(title="oto-brain")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/route", response_model=RouteOut)
def route(turno: RouteIn) -> RouteOut:
    """Fase 3 (cérebro do turno): Montar Contexto -> classificador -> Extrair Rota -> agente
    específico -> EIF1 -> State Validator (ver app.pipeline.processar_turno). Não persiste nada
    — n8n continua salvando sessão com os nós SQL que já existem em produção."""
    with get_connection() as conn:
        sessao = carregar_sessao(conn, turno.telefone)
        historico = carregar_historico_conversa(conn, turno.telefone)
        memoria_paciente = carregar_memoria_paciente(conn, turno.telefone)

        # conn segue aberta pro agente "agenda" poder chamar as tools reais
        # (buscar_agenda/navegar_agenda, app.tools_agenda) durante processar_turno — antes a
        # conexão fechava aqui, antes de existir tool-calling (13/07/2026, Fase 3 peça C).
        resultado = processar_turno(
            busca_paciente_id1=turno.busca_paciente_id1,
            busca_paciente_telefone=turno.busca_paciente_telefone,
            extrair_medico_timeline=turno.extrair_medico_timeline,
            sessao=sessao,
            whatsapp_info=turno.whatsapp_info,
            mensagem_agrupada=turno.mensagem_agrupada,
            historico=historico,
            has_media=turno.has_media,
            memoria_paciente=memoria_paciente,
            conn=conn,
        )
    return RouteOut(
        mensagem=resultado.mensagem,
        intencao=resultado.intencao,
        sv_result=resultado.sv_result,
        sv_reason=resultado.sv_reason,
        rota_agente=resultado.rota_agente,
        agente_usado=resultado.agente_usado,
        deve_resetar_sessao=resultado.deve_resetar_sessao,
        dados=resultado.dados,
    )


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
