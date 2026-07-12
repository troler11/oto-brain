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
