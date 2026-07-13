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

0. Fundação + backfill do histórico (execuções n8n + Postgres) — ✅ feito
1. Cérebro em shadow (replay offline + shadow vivo) — ✅ feito, ≥99% de concordância atingido
2. Cutover do roteamento — pendente, decisão de produção (Lucas)
3. Agentes com structured output — ✅ feito (9 prompts + classificador + tools TiSaude)
4. Memória por paciente + pipeline de casos de aprendizado — scaffolding completo
5. (opcional) Enxugar o n8n

## Estrutura

```
app/          # todo o serviço — flat, sem subpastas (main.py = FastAPI, pipeline.py = orquestrador)
prompts/      # prompts dos 9 agentes LLM + classificador (copiados no Docker image)
tests/        # pytest — 821 testes, port fiel dos guards/queries/prompts
scripts/      # backfill, replay offline, migrações (não vão pro Docker image)
```

## Acesso a dados de produção

Ver memória `reference_oto_postgres_access` (Claude) — host, DB certa (`postgres`, não `otosp`)
e schema das tabelas. Credencial NUNCA fica em arquivo do repo — só em variável de ambiente.

## Deploy

`/route` e `/log-turno` são shadow-only hoje — nenhum node do n8n em produção chama esse
serviço. Subir uma instância (mesmo na VPS de produção) não afeta o Fluxo Principal enquanto
nada estiver configurado pra chamá-la; é seguro pra testes internos em paralelo.

### Env vars (só 4, ver `.env.example`)

| Var | Usada por | Obrigatória pra `/route` funcionar de ponta a ponta? |
|---|---|---|
| `OTO_PG_DSN` | `app/db.py` (sessão, histórico, memória, cache de agenda) | Sim |
| `OTO_OPENAI_API_KEY` | `app/agentes.py` (9 agentes + classificador, structured output) | Sim |
| `OTO_TISAUDE_LOGIN` / `OTO_TISAUDE_SENHA` | `app/tisaude.py` (tools de agenda/consulta) | Sim (o agente `agenda` chama a TiSaude de verdade via tool-calling) |

Sem `OTO_OPENAI_API_KEY`/TiSaude o serviço sobe normal e `/health` responde, mas `/route`
falha em qualquer turno que precise chamar agente ou tool.

### Build/run local (Docker)

```
docker build -t oto-brain .
docker run --rm -p 8000:8000 --env-file .env oto-brain
curl http://localhost:8000/health   # {"status":"ok"}
```

### EasyPanel (mesma VPS do n8n, ver comentário no `Dockerfile`)

1. Novo app → source = este repo (branch `main`) → build via Dockerfile (já commitado na raiz).
2. Env vars: as 4 acima, direto na UI do EasyPanel — nunca no repo.
3. Porta interna `8000` (já é o `EXPOSE`/`uvicorn --port` do Dockerfile).
4. Domínio: escolher um subdomínio de teste (ex. `oto-brain-teste.<domínio da VPS>`) — não
   precisa apontar `n8n.otoflow.com.br` pra nada, os dois serviços ficam lado a lado.
5. Verificar: `GET /health` → `{"status":"ok"}`; depois `POST /route` com um payload de teste
   (ver `RouteIn` em `app/schemas.py`) pra confirmar que Postgres/OpenAI/TiSaude estão
   alcançáveis a partir do container.

Passos 1-4 dependem de acesso ao EasyPanel/VPS — fora do que dá pra fazer por aqui.

### Testar de ponta a ponta sem mexer no n8n de produção

O jeito mais direto de bater WhatsApp real contra essa instância, sem tocar no workflow ativo
(`oX6ePJbAVF7C0NoX`), é duplicar o Fluxo Principal num workflow separado (webhook próprio,
Extrair Rota trocado por HTTP → `/route`) — número de teste, zero risco pra produção. Isso
mexe no n8n, então é um passo separado, com proposta antes de criar (ver `CLAUDE.local.md`).
