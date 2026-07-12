-- Deriva paciente_memoria a partir de contatos_whatsapp + agendamentos (mesma base, não é
-- cópia de outro sistema). Pra cada telefone, pega o agendamento mais recente (por
-- data_criacao) via LATERAL JOIN e faz upsert. Idempotente — rodar de novo atualiza tudo.

INSERT INTO paciente_memoria (
  telefone, nome_titular, cpf_titular, ultimo_medico, ultima_unidade,
  ultimo_convenio, ultimo_periodo, ultima_data_consulta, total_agendamentos,
  primeira_interacao, ultima_interacao, atualizado_em
)
SELECT
  cw.telefone,
  cw.nome_titular,
  cw.cpf_titular,
  COALESCE(ag.medico_final, ag.nome_medico),
  ag.unidade,
  ag.pagamento,
  ag.periodo_atendimento,
  ag.data_consulta,
  cnt.total,
  cw.data_cadastro,
  cw.ultima_mensagem,
  NOW()
FROM contatos_whatsapp cw
LEFT JOIN LATERAL (
  -- placeholders de fila pré-confirmação ("A Definir"/"A Combinar"/"a confirmar") não contam
  -- como preferência real — prioriza o agendamento mais recente com dado de verdade.
  SELECT a.medico_final, a.nome_medico, a.unidade, a.pagamento,
         a.periodo_atendimento, a.data_consulta
  FROM agendamentos a
  WHERE a.contato_id = cw.id
  ORDER BY
    (a.unidade IS NOT NULL AND a.unidade NOT ILIKE 'a defin%' AND a.unidade NOT ILIKE 'a confirmar%') DESC,
    a.data_criacao DESC NULLS LAST
  LIMIT 1
) ag ON TRUE
LEFT JOIN LATERAL (
  SELECT COUNT(*)::int AS total FROM agendamentos a2 WHERE a2.contato_id = cw.id
) cnt ON TRUE
WHERE cw.telefone IS NOT NULL
ON CONFLICT (telefone) DO UPDATE SET
  nome_titular         = EXCLUDED.nome_titular,
  cpf_titular          = EXCLUDED.cpf_titular,
  ultimo_medico        = EXCLUDED.ultimo_medico,
  ultima_unidade       = EXCLUDED.ultima_unidade,
  ultimo_convenio      = EXCLUDED.ultimo_convenio,
  ultimo_periodo       = EXCLUDED.ultimo_periodo,
  ultima_data_consulta = EXCLUDED.ultima_data_consulta,
  total_agendamentos   = EXCLUDED.total_agendamentos,
  primeira_interacao   = EXCLUDED.primeira_interacao,
  ultima_interacao     = EXCLUDED.ultima_interacao,
  atualizado_em        = NOW();
