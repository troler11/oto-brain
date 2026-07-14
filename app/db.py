import re

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from app.config import PG_DSN


def get_connection() -> psycopg.Connection:
    return psycopg.connect(PG_DSN, autocommit=True)


_COLUNAS = (
    "execution_id", "workflow_id", "status", "mode", "started_at", "stopped_at",
    "telefone", "texto_usuario", "extrair_rota", "extrair_intencao_final",
    "state_validator", "mensagem_enviada", "raw_nodes",
)
_COLUNAS_JSONB = {"extrair_rota", "extrair_intencao_final", "state_validator", "raw_nodes"}


def gravar_turno(conn: psycopg.Connection, row: dict, overwrite: bool = False) -> bool:
    """Upsert em conversas_log — mesma lógica do backfill (scripts/backfill_n8n_executions.py).
    Retorna True se inseriu/atualizou, False se já existia e `overwrite=False` (comportamento
    padrão, usado pelo /log-turno ao vivo: idempotente, nunca pisa em turno já logado).
    `overwrite=True` (usado pelo re-backfill) sobrescreve a linha existente — necessário quando
    o conjunto de nós capturados muda (ex.: NOS_INTERESSE ganhou nós novos) e as linhas antigas
    precisam ser enriquecidas, não puladas.
    `row` pode não ter todas as colunas (ex.: LogTurnoIn não expõe raw_nodes) — preenche
    o que faltar com None em vez de depender do chamador ter as 13 chaves exatas."""
    params = {col: row.get(col) for col in _COLUNAS}
    for campo in _COLUNAS_JSONB:
        if params[campo] is not None:
            params[campo] = Jsonb(params[campo])
    on_conflict = (
        "DO UPDATE SET " + ", ".join(f"{c} = EXCLUDED.{c}" for c in _COLUNAS if c != "execution_id")
        if overwrite
        else "DO NOTHING"
    )
    with conn.cursor() as cur:
        cur.execute(
            f"""
            INSERT INTO conversas_log
              (execution_id, workflow_id, status, mode, started_at, stopped_at,
               telefone, texto_usuario, extrair_rota, extrair_intencao_final,
               state_validator, mensagem_enviada, raw_nodes)
            VALUES (%(execution_id)s, %(workflow_id)s, %(status)s, %(mode)s,
                    %(started_at)s, %(stopped_at)s, %(telefone)s, %(texto_usuario)s,
                    %(extrair_rota)s, %(extrair_intencao_final)s, %(state_validator)s,
                    %(mensagem_enviada)s, %(raw_nodes)s)
            ON CONFLICT (execution_id) {on_conflict};
            """,
            params,
        )
        return cur.rowcount > 0


# ─────────────────────────────────────────────────────────────────────────────────────────────
# Port fiel das queries SQL do fluxo de sessão (DEPLOY/*.sql, snapshot 12/07/2026) — Fase 1
# estendida do plano de migração (ver C:\Users\lucas\.claude\plans\unified-coalescing-puppy.md).
# Mesma SQL dos nós Postgres do n8n; placeholders $N (bind posicional nativo do n8n) convertidos
# pra %(nome)s (bind nomeado do psycopg) — mais seguro que replicar 21 posições por índice.
# Sem testes de integração aqui (exigiriam Postgres real); tests/test_db_queries.py verifica
# SQL + params via cursor mockado, mesmo padrão de tests/test_log_turno.py.
# ─────────────────────────────────────────────────────────────────────────────────────────────


def carregar_sessao(conn: psycopg.Connection, telefone: str) -> dict | None:
    """Port fiel de DEPLOY/_proposed_Carregar_Sessao.sql (84 linhas). Garante a linha (INSERT
    .. ON CONFLICT, sessao_id nunca NULL — FIX_SESSAO_ID_GARANTIDO) e devolve sessão + cache de
    agenda mais fresco (JOIN LATERAL tolerante a prefixo "55", casando pelos últimos 11 dígitos
    — FIX_66787b) + dados de terceiro (terceiros_agendamento, com fallback pra cw.*)."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            INSERT INTO contatos_whatsapp
              (sessao_intencao, sessao_rota, telefone, sessao_atualizada_em, ultima_mensagem, status_robo, sessao_id)
            VALUES ('triagem', 0, %(telefone)s, NOW(), NOW(), 'Robô', gen_random_uuid())
            ON CONFLICT (telefone) DO UPDATE SET sessao_id = COALESCE(contatos_whatsapp.sessao_id, gen_random_uuid());
            """,
            {"telefone": telefone},
        )
        cur.execute(
            r"""
            SELECT
              cw.sessao_id,
              cw.status_robo,
              cw.sessao_intencao,
              cw.sessao_rota,
              cw.sessao_atualizada_em,
              cw.coleta_unidade,
              cw.coleta_data,
              cw.coleta_periodo,
              cw.coleta_convenio,
              cw.coleta_horario,
              cw.coleta_terceiro,
              cw.coleta_medico,
              cw.coleta_modo,
              cw.coleta_dia_semana,
              cw.coleta_id_tisaude,
              cw.coleta_id_agendamento,
              cw.coleta_conv_fail,
              cw.coleta_id_ag_antigo,
              cw.coleta_dt_antiga,
              cw.coleta_hr_antiga,
              cw.coleta_md_antiga,
              cw.coleta_email,
              ac.agenda_json,
              ac.indice_atual,
              ac.ultimo_dia_exibido,
              ac.unidade          AS unidade_cache,
              COALESCE(NULLIF(ta.nome_dependente, ''), NULLIF(cw.nome_dependente, ''))   AS nome_dependente,
              COALESCE(NULLIF(ta.cpf_dependente, ''), NULLIF(cw.cpf_dependente, ''))     AS cpf_dependente,
              COALESCE(NULLIF(ta.nascimento_dependente, ''), NULLIF(cw.nascimento_dependente, '')) AS nascimento_dependente
            FROM contatos_whatsapp cw
            LEFT JOIN LATERAL (
              SELECT ac2.agenda_json, ac2.indice_atual, ac2.ultimo_dia_exibido, ac2.unidade
              FROM agenda_cache ac2
              WHERE RIGHT(regexp_replace(ac2.telefone, '\D', '', 'g'), 11)
                  = RIGHT(regexp_replace(cw.telefone,  '\D', '', 'g'), 11)
                AND ac2.expira_em > NOW()
              ORDER BY ac2.expira_em DESC
              LIMIT 1
            ) ac ON TRUE
            LEFT JOIN terceiros_agendamento ta
              ON ta.telefone_titular = cw.telefone
            WHERE cw.telefone = %(telefone)s
            LIMIT 1
            """,
            {"telefone": telefone},
        )
        return cur.fetchone()


def _historico_para_mensagens(rows: list[dict]) -> list[dict]:
    """Converte linhas de `chat_limpo` (ordem cronológica, mais antiga primeiro) pro formato
    `[{"role": "user"|"assistant", "content": ...}, ...]` que `app.agentes.chamar_agente`
    espera — `origem='paciente'` -> `user`, qualquer outra coisa (`ia_ou_recepcao`, inclusive
    quando um humano assumiu via `enviado_por`) -> `assistant` (é o que foi dito AO paciente,
    não importa se foi o bot ou um atendente)."""
    return [
        {"role": "user" if row["origem"] == "paciente" else "assistant", "content": row["texto"]}
        for row in rows
        if (row.get("texto") or "").strip()
    ]


def carregar_historico_conversa(conn: psycopg.Connection, telefone: str, limite: int = 20) -> list[dict]:
    """Últimas `limite` mensagens de `chat_limpo` pro telefone (exclui editadas/excluídas, e
    qualquer coisa com mais de 12h — mesmo corte de "sessão nova" que `app.eif1` já usa em
    FIX_SAUDACAO_PRIMEIRO_CONTATO), convertidas pro formato de histórico OpenAI (`app.
    _historico_para_mensagens`). Fonte de conversa pro `/route` (Fase 3) — `chat_limpo` já é
    gravado ao vivo pelo n8n, mesma tabela usada na mineração de casos (`app.minerar_casos`).

    FIX_HISTORICO_JANELA_12H (14/07/2026, achado no teste real com `otosp`): sem corte de
    tempo, `chat_limpo` (só telefone + LIMIT, sem `sessao_id`) trazia conversas de DIAS atrás
    pra dentro de um turno novo — a produção real não tem esse bug porque a memória do
    LangChain é escopada por `sessao_id` (que gira a cada `resetar_sessao`); `chat_limpo` não
    tem essa coluna, então o corte de tempo é o substituto mais simples e fiel ao MESMO limiar
    de 12h que já define "sessão nova" em outro lugar do sistema."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT texto, origem, data
            FROM chat_limpo
            WHERE telefone = %(telefone)s AND excluido_em IS NULL AND data > NOW() - INTERVAL '12 hours'
            ORDER BY data DESC
            LIMIT %(limite)s;
            """,
            {"telefone": telefone, "limite": limite},
        )
        rows = list(reversed(cur.fetchall()))
    return _historico_para_mensagens(rows)


def carregar_memoria_paciente(conn: psycopg.Connection, telefone: str) -> dict | None:
    """Preferências consolidadas do paciente (`paciente_memoria`, bootstrap Fase 4 —
    scripts/build_paciente_memoria.py, derivado de contatos_whatsapp+agendamentos). Tolerante a
    prefixo "55" (RIGHT(...,11), mesmo padrão de carregar_sessao/FIX_66787b) — a tabela é
    alimentada a partir de contatos_whatsapp.telefone, que pode ou não ter o prefixo.
    Identifica o paciente só pelo telefone do WhatsApp, sem depender de busca por CPF/ID
    TiSaude já ter rodado — diferente de `ultimo_medico` em app.montar_contexto (que só existe
    depois que `Extrair Medico Timeline1` já resolveu o paciente na API ao vivo)."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT nome_titular, cpf_titular, ultimo_medico, ultima_unidade, ultimo_convenio,
                   ultimo_periodo, ultima_data_consulta, total_agendamentos
            FROM paciente_memoria
            WHERE RIGHT(regexp_replace(telefone, '\\D', '', 'g'), 11)
                = RIGHT(regexp_replace(%(telefone)s, '\\D', '', 'g'), 11)
            LIMIT 1;
            """,
            {"telefone": telefone},
        )
        return cur.fetchone()


def ler_agenda_cache(conn: psycopg.Connection, telefone: str, unidade: str) -> dict | None:
    """Port fiel do node 'Ler Cache do Postgres1' (sub-workflow 'Ferramenta - Navegar Agenda',
    `iSO191fJ9Q1FMmVZ`) — mesmo filtro por últimos 11 dígitos do telefone (ignora DDI) e
    `expira_em > NOW()` usado no resto do módulo. `None` = sem linha (cache expirado/inexistente
    pra essa unidade), input esperado por `app.navegar_agenda.processar()`."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT agenda_json, indice_atual
            FROM agenda_cache
            WHERE RIGHT(regexp_replace(telefone, '\\D', '', 'g'), 11)
                = RIGHT(regexp_replace(%(telefone)s, '\\D', '', 'g'), 11)
              AND unidade = %(unidade)s
              AND expira_em > NOW()
            LIMIT 1;
            """,
            {"telefone": telefone, "unidade": unidade},
        )
        return cur.fetchone()


def atualizar_indice_agenda_cache(
    conn: psycopg.Connection, telefone: str, unidade: str, indice_atual: int, dia: dict | None,
) -> None:
    """Port fiel do node 'Atualiza Índice no Postgres1' (mesmo sub-workflow) — grava o novo
    índice de navegação e, se `dia` tiver `data` (resultado OK de `app.navegar_agenda.
    processar()`), atualiza `ultimo_dia_exibido` com só os campos usados no resto do fluxo
    (medico/idLocal/idCalendar/horarios) — `COALESCE` no SQL preserva o valor antigo quando
    `dia` é `None` (status ESGOTADO/DATA_NAO_ENCONTRADA não têm dia novo pra gravar)."""
    ultimo_dia_exibido = None
    if dia and dia.get("data"):
        ultimo_dia_exibido = Jsonb({
            "data": dia["data"],
            "medicos": [
                {"medico": m.get("medico"), "idLocal": m.get("idLocal"), "idCalendar": m.get("idCalendar"),
                 "horarios": m.get("horarios") or ""}
                for m in (dia.get("medicos") or [])
            ],
        })
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE agenda_cache
            SET indice_atual = %(indice_atual)s,
                ultimo_dia_exibido = COALESCE(%(ultimo_dia_exibido)s, ultimo_dia_exibido)
            WHERE RIGHT(regexp_replace(telefone, '\\D', '', 'g'), 11)
                = RIGHT(regexp_replace(%(telefone)s, '\\D', '', 'g'), 11)
              AND unidade = %(unidade)s
              AND expira_em > NOW();
            """,
            {
                "telefone": telefone, "unidade": unidade, "indice_atual": indice_atual,
                "ultimo_dia_exibido": ultimo_dia_exibido,
            },
        )


def salvar_coleta_steps(
    conn: psycopg.Connection,
    telefone: str,
    *,
    unidade: str = "", data: str = "", periodo: str = "", convenio: str = "", horario: str = "",
    terceiro: str = "", nome_dependente: str = "", cpf_dependente: str = "", nascimento_dependente: str = "",
    medico: str = "", modo: int = 0, dia_semana: str = "", id_tisaude: str = "", id_agendamento: str = "",
    conv_fail: int = -1, id_ag_antigo: str = "", dt_antiga: str = "", hr_antiga: str = "", md_antiga: str = "",
    email: str = "",
) -> None:
    """Port fiel de DEPLOY/_proposed_Salvar_Coleta_Steps.sql (29 linhas). Persiste os campos de
    coleta extraídos pelo EIF1 (`app.eif1.processar` → `ResultadoEIF1`/`.dados`). Convenção
    `'__CLEAR__'` = limpar o campo (FIX_CLEAR_FIELDS); `medico='__CLEAR__'` é o "clear nuclear"
    que também zera data/período/horário/dia_semana/id_tisaude/id_agendamento junto (mesmo
    campo que o ER usa como sentinela de limpeza — ver `app.er`); `id_ag_antigo='__CLEAR__'`
    zera os 4 campos `*_antiga` da remarcação juntos (mesmo padrão, sentinela próprio). Campos
    vazios (`''`) NÃO sobrescrevem o valor salvo (`COALESCE(NULLIF(x,''), coluna)`) — só
    `'__CLEAR__'` ou um valor novo não-vazio mudam a coluna."""
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE contatos_whatsapp
            SET
              coleta_unidade  = COALESCE(NULLIF(%(unidade)s, ''), coleta_unidade),
              coleta_data     = CASE WHEN %(medico)s = '__CLEAR__' OR %(data)s = '__CLEAR__' THEN '' ELSE COALESCE(NULLIF(%(data)s, ''), coleta_data) END,
              coleta_periodo  = CASE WHEN %(medico)s = '__CLEAR__' OR %(periodo)s = '__CLEAR__' THEN '' ELSE COALESCE(NULLIF(%(periodo)s, ''), coleta_periodo) END,
              coleta_convenio = CASE WHEN %(convenio)s = 'RESET_CONV' THEN '' ELSE COALESCE(NULLIF(%(convenio)s, ''), coleta_convenio) END,
              coleta_horario  = CASE WHEN %(medico)s = '__CLEAR__' OR %(horario)s = '__CLEAR__' THEN '' ELSE COALESCE(NULLIF(%(horario)s, ''), coleta_horario) END,
              coleta_terceiro = CASE WHEN %(terceiro)s = 'false' THEN '' ELSE COALESCE(NULLIF(%(terceiro)s, ''), coleta_terceiro) END,
              coleta_medico       = CASE WHEN %(medico)s = '__CLEAR__' THEN '' ELSE COALESCE(NULLIF(%(medico)s, ''), coleta_medico) END,
              coleta_modo         = CASE WHEN %(medico)s = '__CLEAR__' THEN 0 ELSE COALESCE(NULLIF(%(modo)s::int, 0), coleta_modo) END,
              coleta_dia_semana   = CASE WHEN %(medico)s = '__CLEAR__' OR %(dia_semana)s = '__CLEAR__' THEN '' ELSE COALESCE(NULLIF(%(dia_semana)s, ''), coleta_dia_semana) END,
              coleta_id_tisaude   = CASE WHEN %(medico)s = '__CLEAR__' OR %(id_tisaude)s::text = '__CLEAR__' THEN '' ELSE COALESCE(NULLIF(%(id_tisaude)s::text, ''), coleta_id_tisaude) END,
              coleta_id_agendamento = CASE WHEN %(medico)s = '__CLEAR__' THEN '' ELSE COALESCE(NULLIF(%(id_agendamento)s::text, ''), coleta_id_agendamento) END,
              coleta_conv_fail      = CASE WHEN %(conv_fail)s::smallint = -1 THEN coleta_conv_fail ELSE %(conv_fail)s::smallint END,
              coleta_id_ag_antigo = CASE WHEN %(id_ag_antigo)s::text = '__CLEAR__' THEN '' ELSE COALESCE(NULLIF(%(id_ag_antigo)s::text, ''), coleta_id_ag_antigo) END,
              coleta_dt_antiga    = CASE WHEN %(id_ag_antigo)s::text = '__CLEAR__' THEN '' ELSE COALESCE(NULLIF(%(dt_antiga)s, ''), coleta_dt_antiga) END,
              coleta_hr_antiga    = CASE WHEN %(id_ag_antigo)s::text = '__CLEAR__' THEN '' ELSE COALESCE(NULLIF(%(hr_antiga)s, ''), coleta_hr_antiga) END,
              coleta_md_antiga    = CASE WHEN %(id_ag_antigo)s::text = '__CLEAR__' THEN '' ELSE COALESCE(NULLIF(%(md_antiga)s, ''), coleta_md_antiga) END,
              coleta_email        = CASE WHEN %(email)s = 'SKIP' THEN 'SKIP' ELSE COALESCE(NULLIF(%(email)s, ''), coleta_email) END,
              nome_atendimento    = CASE WHEN %(nome_dependente)s = '__CLEAR__' THEN nome_atendimento ELSE COALESCE(NULLIF(%(nome_dependente)s, ''), nome_atendimento) END,
              nome_dependente     = CASE WHEN %(nome_dependente)s = '__CLEAR__' THEN '' ELSE COALESCE(NULLIF(%(nome_dependente)s, ''), nome_dependente) END,
              cpf_dependente      = CASE WHEN %(cpf_dependente)s = '__CLEAR__' THEN '' ELSE COALESCE(NULLIF(%(cpf_dependente)s, ''), cpf_dependente) END,
              nascimento_dependente = CASE WHEN %(nascimento_dependente)s = '__CLEAR__' THEN '' ELSE COALESCE(NULLIF(%(nascimento_dependente)s, ''), nascimento_dependente) END
            WHERE telefone = %(telefone)s;
            """,
            {
                "unidade": unidade, "data": data, "periodo": periodo, "convenio": convenio,
                "telefone": telefone, "horario": horario, "terceiro": terceiro,
                "nome_dependente": nome_dependente, "cpf_dependente": cpf_dependente,
                "nascimento_dependente": nascimento_dependente, "medico": medico, "modo": modo,
                "dia_semana": dia_semana, "id_tisaude": id_tisaude, "id_agendamento": id_agendamento,
                "conv_fail": conv_fail, "id_ag_antigo": id_ag_antigo, "dt_antiga": dt_antiga,
                "hr_antiga": hr_antiga, "md_antiga": md_antiga, "email": email,
            },
        )


_INTENCOES_VALIDAS = (
    "navegacao", "confirmacao", "execucao", "concluido", "coleta", "triagem", "humano", "agenda",
    "cancelando", "oferta_humano", "oferta_agendar", "confirmar_presenca", "confirmar_presenca_lista",
    "confirmar_presenca_recusou", "remarcando_escolher",
)


_INTENCOES_VALIDAS_SQL = "(" + ", ".join(f"'{v}'" for v in _INTENCOES_VALIDAS) + ")"


def salvar_intencao_agente(conn: psycopg.Connection, intencao: str, rota_agente: int, telefone: str) -> None:
    """Port fiel de DEPLOY/_proposed_Salvar_Intencao_Agente_query.sql (9 linhas, FIX_67529).
    Só grava se `intencao` estiver na whitelist — fora dela, a query é um no-op (nenhuma linha
    afetada), preservando o valor já salvo."""
    with conn.cursor() as cur:
        cur.execute(
            f"""
            UPDATE contatos_whatsapp
            SET sessao_intencao = %(intencao)s, sessao_rota = %(rota_agente)s
            WHERE telefone = %(telefone)s
              AND %(intencao)s IN {_INTENCOES_VALIDAS_SQL};
            """,
            {"intencao": intencao, "rota_agente": rota_agente, "telefone": telefone},
        )


def resetar_sessao(conn: psycopg.Connection, telefone: str) -> None:
    """Port fiel de DEPLOY/Resetar_Sessao.sql (32 linhas) — encerramento normal (triagem
    concluída): zera coleta_*, dados de terceiro (contatos_whatsapp E terceiros_agendamento),
    limpa o cache de agenda e gira sessao_id (nova sessão de memória LangChain)."""
    params = {"telefone": telefone}
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE contatos_whatsapp
            SET sessao_intencao = 'concluido', sessao_rota = 0, sessao_atualizada_em = NOW(),
                coleta_unidade = '', coleta_data = '', coleta_periodo = '', coleta_horario = '',
                coleta_convenio = '', coleta_medico = '', coleta_conv_fail = 0,
                nome_atendimento = '', coleta_id_tisaude = '', nome_dependente = '',
                cpf_dependente = '', nascimento_dependente = '', coleta_dia_semana = '',
                coleta_id_agendamento = ''
            WHERE telefone = %(telefone)s;
            """,
            params,
        )
        cur.execute(
            """
            UPDATE terceiros_agendamento
            SET nome_dependente = '', cpf_dependente = '', nascimento_dependente = '', atualizado_em = NOW()
            WHERE telefone_titular = %(telefone)s;
            """,
            params,
        )
        cur.execute("DELETE FROM agenda_cache WHERE telefone = %(telefone)s;", params)
        cur.execute("UPDATE contatos_whatsapp SET sessao_id = gen_random_uuid() WHERE telefone = %(telefone)s;", params)


def resetar_sessao_humano(conn: psycopg.Connection, telefone: str) -> None:
    """Port fiel de DEPLOY/Resetar_Sessao_Humano.sql (24 linhas) — transferência pra atendente:
    volta sessao_intencao pra 'triagem' mas marca status_robo='Humano' (bot para de responder),
    zera coleta_* (subconjunto menor que resetar_sessao — não zera id_tisaude/dia_semana/
    id_agendamento, fiel ao SQL original), limpa terceiro e cache, gira sessao_id."""
    params = {"telefone": telefone}
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE contatos_whatsapp
            SET sessao_intencao = 'triagem', sessao_rota = 0, status_robo = 'Humano',
                sessao_atualizada_em = NOW(), coleta_unidade = '', coleta_data = '',
                coleta_periodo = '', coleta_convenio = '', coleta_medico = '', coleta_conv_fail = 0
            WHERE telefone = %(telefone)s;
            """,
            params,
        )
        cur.execute(
            """
            UPDATE terceiros_agendamento
            SET nome_dependente = '', cpf_dependente = '', nascimento_dependente = '', atualizado_em = NOW()
            WHERE telefone_titular = %(telefone)s;
            """,
            params,
        )
        cur.execute("DELETE FROM agenda_cache WHERE telefone = %(telefone)s;", params)
        cur.execute("UPDATE contatos_whatsapp SET sessao_id = gen_random_uuid() WHERE telefone = %(telefone)s;", params)


def criar_fila(conn: psycopg.Connection, params: dict) -> None:
    """Port fiel do INSERT compartilhado pelos nós 'Cria fila' e 'Cria Fila (Falha Confirmar)'
    (mesma query nos dois, só os valores mudam — ver `app.fila_humana.montar_params_cria_fila()`/
    `montar_params_cria_fila_falha_confirmar()` pro cálculo dos parâmetros). Enfileira uma
    conversa pra atendente humano em `agendamentos` (`status_atendimento='PENDENTE'`);
    `nascimento`/`observacoes` vazios viram NULL (`NULLIF`, igual o node real)."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO agendamentos (
              contato_id, intencao, especialidade, unidade, pagamento, para_terceiro,
              nome_paciente, status_atendimento, cpf_paciente, nascimento_paciente,
              nome_medico, periodo_atendimento, tipo_consulta, observacoes
            ) VALUES (
              (SELECT id FROM contatos_whatsapp WHERE telefone = %(telefone)s),
              %(intencao)s, %(especialidade)s, %(unidade)s, %(pagamento)s, %(para_terceiro)s,
              %(nome_paciente)s, 'PENDENTE', %(cpf_paciente)s, NULLIF(%(nascimento)s, '')::DATE,
              %(medico)s, %(periodo)s, %(motivo_humano)s, NULLIF(%(observacoes)s, '')
            );
            """,
            params,
        )


_INTENCOES_QUE_SALVAM_SESSAO = (
    "navegacao", "confirmacao", "execucao", "concluido", "oferta_humano", "oferta_agendar",
    "confirmar_presenca", "confirmar_presenca_lista", "confirmar_presenca_recusou",
)


def computar_params_salvar_sessao(
    extrair_rota: dict, eif1_executado: bool, eif1_intencao: str | None, whatsapp_info: dict
) -> dict:
    """Port fiel do queryReplacement de DEPLOY/_proposed_Salvar_Sessao_queryReplacement.txt
    (FIX_67529) — NÃO da query em si (o texto SQL do nó "Salvar Sessao" não está no DEPLOY,
    só o cálculo dos parâmetros). Retorna os valores que iriam nos placeholders posicionais
    originais ($1..$8); quem tiver a query real precisa mapear esta dict pros $N corretos.

    `intencao` prioriza o valor do EIF1 (`eif1_intencao`) SE ele rodou neste turno E o valor
    está numa whitelist menor que a de `salvar_intencao_agente` (sem 'coleta'/'triagem'/'humano'/
    'cancelando'/'agenda' — esses vêm só do Extrair Rota aqui); fallback é
    `extrair_rota.intencao_rapida` ou 'triagem'. `telefone` reconstrói o prefixo "55" que
    `app.montar_contexto` removeu (mesmo whatsapp_info, uso diferente — ver docstring de
    `app.montar_contexto`)."""
    er = extrair_rota or {}
    if eif1_executado and eif1_intencao in _INTENCOES_QUE_SALVAM_SESSAO:
        intencao = eif1_intencao
    else:
        intencao = er.get("intencao_rapida") or "triagem"

    info = whatsapp_info or {}
    sender_alt = info.get("SenderAlt") or ""
    raw_id = sender_alt if "@s.whatsapp.net" in sender_alt else info.get("Chat")
    telefone_sem_55 = (raw_id or "").split("@")[0].split(":")[0]
    telefone = "55" + re.sub(r"^55", "", telefone_sem_55)

    return {
        "intencao": intencao,
        "rota_agente": er.get("rota_agente") or 0,
        "telefone": telefone,
        "nome_dependente": er.get("nome_dependente") or "",
        "cpf_dependente": er.get("cpf_dependente") or "",
        "nascimento_dependente": er.get("nascimento_dependente") or "",
        "deve_resetar_sessao": bool(er.get("deve_resetar_sessao")),
        "nome_titular": er.get("nome_titular") or "",
    }
