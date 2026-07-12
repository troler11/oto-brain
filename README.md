# oto-brain

Serviço Python (FastAPI) que assume o "cérebro" do chatbot de agendamento da Clínica Oto-SP —
roteamento de estado, validação e agentes — mantendo o n8n como transporte (webhook WAHA, envio
de mensagens, UI de execuções, lembretes).

Plano completo: ver `C:\Users\lucas\.claude\plans\unified-coalescing-puppy.md` (ou a versão
arquivada nesta pasta em `PLANO.md`, se copiada).

## Por quê

Diagnóstico de ~45 fixes na temporada 07/07→11/07 apontou 4 causas estruturais recorrentes:
estado como texto livre ecoado pelo LLM (`$$$`), decisões que deveriam ser código delegadas ao
LLM, um monolito de ~375KB colado manualmente em 2 workflows sem testes, e validação que roda
depois do agente já ter agido (ex.: consulta criada em data errada, exec 67553).

## Fases

0. Fundação + backfill do histórico (execuções n8n + Postgres) — **em andamento**
1. Cérebro em shadow (replay offline + shadow vivo)
2. Cutover do roteamento
3. Agentes com structured output
4. Memória por paciente + pipeline de casos de aprendizado
5. (opcional) Enxugar o n8n

## Estrutura

```
app/
  routes/     # endpoints FastAPI (/route, /health, ...)
  guards/     # port dos guards do Extrair Rota
tests/        # pytest — port dos validate_*.js (sims viram testes reais)
scripts/      # backfill, migrações, utilitários
```

## Acesso a dados de produção

Ver memória `reference_oto_postgres_access` (Claude) — host, DB certa (`postgres`, não `otosp`)
e schema das tabelas. Credencial NUNCA fica em arquivo do repo — só em variável de ambiente.
