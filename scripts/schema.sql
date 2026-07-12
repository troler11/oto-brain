-- Tabela de backfill/log de turnos — corpus de replay pro router (Fase 1) e matéria-prima
-- pro pipeline de aprendizado (Fase 4). Roda no Postgres de produção existente (ver
-- memória `reference_oto_postgres_access`), schema public, ao lado de contatos_whatsapp etc.

CREATE TABLE IF NOT EXISTS conversas_log (
  id              BIGSERIAL PRIMARY KEY,
  execution_id    TEXT UNIQUE NOT NULL,
  workflow_id     TEXT NOT NULL,
  status          TEXT,
  mode            TEXT,
  started_at      TIMESTAMPTZ,
  stopped_at      TIMESTAMPTZ,
  telefone        TEXT,
  texto_usuario   TEXT,
  extrair_rota          JSONB,  -- output do nó Extrair Rota (estado + tag)
  extrair_intencao_final JSONB, -- output do EIF1 (dados $$$ + texto_ia)
  state_validator       JSONB,  -- output do State Validator (sv_result/sv_reason)
  mensagem_enviada      TEXT,   -- texto que de fato saiu no WhatsApp
  raw_nodes             JSONB,  -- fallback: todos os nós capturados, crus (sem workflowData)
  fetched_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_conversas_log_telefone   ON conversas_log (telefone);
CREATE INDEX IF NOT EXISTS idx_conversas_log_started_at ON conversas_log (started_at);
CREATE INDEX IF NOT EXISTS idx_conversas_log_status     ON conversas_log (status);

-- Pipeline de casos (Fase 4, mecanismo 2) — minerado de chat_limpo (histórico completo desde
-- 07/07). Casos aprovados por Lucas viram (a) teste de regressão pytest e (b) few-shot no
-- prompt do agente correspondente. UNIQUE evita duplicar em re-mineração (job diário).
CREATE TABLE IF NOT EXISTS casos_aprendizado (
  id             BIGSERIAL PRIMARY KEY,
  telefone       TEXT NOT NULL,
  categoria      TEXT NOT NULL, -- transferencia_humano | desistencia | loop_repergunta | correcao
  turno_texto    TEXT,          -- mensagem que disparou a detecção
  contexto       JSONB,         -- janela de mensagens ao redor, ordenada
  origem_data    TIMESTAMPTZ,   -- quando o caso aconteceu de verdade
  detectado_em   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  status         TEXT NOT NULL DEFAULT 'pendente', -- pendente | aprovado | rejeitado
  revisado_por   TEXT,
  revisado_em    TIMESTAMPTZ,
  UNIQUE (telefone, categoria, origem_data)
);

CREATE INDEX IF NOT EXISTS idx_casos_aprendizado_status ON casos_aprendizado (status);

-- Memória por paciente (Fase 4, bootstrap) — derivada de contatos_whatsapp + agendamentos,
-- que JÁ vivem nesta mesma base (não é cópia de outro sistema). Preferências consolidadas
-- pra injetar no contexto do agente sem re-perguntar ("agendar com a Dra. X de novo?").
CREATE TABLE IF NOT EXISTS paciente_memoria (
  telefone              TEXT PRIMARY KEY,
  nome_titular          TEXT,
  cpf_titular            TEXT,
  ultimo_medico         TEXT,
  ultima_unidade        TEXT,
  ultimo_convenio       TEXT,
  ultimo_periodo        TEXT,
  ultima_data_consulta  DATE,
  total_agendamentos    INTEGER NOT NULL DEFAULT 0,
  primeira_interacao    TIMESTAMPTZ,
  ultima_interacao      TIMESTAMPTZ,
  atualizado_em         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
