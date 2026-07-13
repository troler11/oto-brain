"""
Port fiel de nós de aviso pequenos e independentes (Fase 1 do plano de migração, ver
C:\\Users\\lucas\\.claude\\plans\\unified-coalescing-puppy.md):
  - `aviso_sucesso()` — DEPLOY/Aviso_Sucesso1.js (5 linhas): passthrough puro do texto que o
    EIF1 já gerou (o comentário do JS existe só pra registrar que ISSO NÃO é hardcoded).
  - `aviso_transferencia()` — menu principal (4 opções) exibido ao transferir/reabrir a
    triagem, saudando pelo primeiro nome se conhecido.
  - `dentro_do_expediente()`/`aviso_fora_expediente()` — port dos nós `Fora do Expediente?`
    (IF) + `Aviso Expediente (Fora)` (HTTP WAHA), achados numa auditoria de inventário completo
    do grafo (13/07/2026) que foi além dos 39 nós `code` e catalogou os 157 nós reais do
    workflow. Condição original: `$now.setZone('America/Sao_Paulo').weekday <= 5 && hour >= 8
    && hour < 18`; luxon `weekday` 1=segunda..7=domingo → `<=5` é segunda-sexta. Réplica usa o
    mesmo offset fixo UTC-3 que `app.er._hoje_sp()` já usa (Brasil não tem DST desde 2019).

⚠️ **Sem ponto de chamada no pipeline hoje.** No grafo real esse IF só dispara DEPOIS dos nós
`Cria fila`/`Cria Fila (Falha Confirmar)` (INSERT em `agendamentos` pra fila humana) — ou seja,
é um aviso automático disparado só quando uma conversa é enfileirada pra atendente FORA do
horário comercial, não um gate que bloqueia o bot inteiro. Esses dois nós de fila (`Preparar
Dados para Fila`) continuam NÃO portados (persistência de fila é responsabilidade do n8n
enquanto `/route` for shadow, ver docstring de `app/main.py`) — então estas duas funções ficam
prontas/testadas isoladamente, sem wiring, até o dia em que a fila humana for portada.

⚠️ CORREÇÃO (13/07/2026, `get_workflow_details` direto no node `Aviso Transferencia1` real —
achado numa auditoria de fechamento): a versão anterior deste port tinha 6 opções (incluía
"4️⃣ Consulta pendente" e "6️⃣ Confirmar consulta"), copiadas do arquivo `DEPLOY/
Aviso_Transferencia1.js`, que estava DESATUALIZADO em relação ao node real hoje em produção — o
node real tem só 4 opções (Agendar/Remarcar/Cancelar/Troca de guias e documentos). Corrigido pra
bater com o node ao vivo, não com o snapshot do DEPLOY. Nunca esteve ligado a nenhum
dispatcher/agente (código órfão desde que foi portado), então não havia risco de produção — só
corrigido antes que alguém ligue.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone


def aviso_sucesso(extrair_intencao_final: dict) -> dict:
    return {"mensagem_final": (extrair_intencao_final or {}).get("texto_ia")}


def aviso_transferencia(extrair_rota: dict, pacientes: list[dict] | None) -> dict:
    base = extrair_rota or {}
    pacientes = pacientes or []
    nome = pacientes[0]["nome"].split(" ")[0] if pacientes else ""
    saudacao = f"Olá, {nome}! 👋" if nome else "Olá! 👋"

    mensagem = (
        f"{saudacao}\n\n"
        "Seja bem-vindo(a) à Clínica Oto-SP de Otorrinolaringologia.\n\n"
        "Como podemos ajudá-lo(a) hoje?\n"
        "Digite o número ou escreva o que deseja:\n\n"
        "1️⃣ Agendar consulta\n"
        "2️⃣ Remarcar consulta\n"
        "3️⃣ Cancelar consulta\n"
        "4️⃣ Troca de guias e documentos"
    )
    return {**base, "mensagem_final": mensagem}


def dentro_do_expediente(agora: datetime | None = None) -> bool:
    agora = agora or (datetime.now(timezone.utc) - timedelta(hours=3))
    return agora.weekday() <= 4 and 8 <= agora.hour < 18


def aviso_fora_expediente() -> dict:
    mensagem = (
        "⏰ Só um aviso: nosso time atende de segunda a sexta, das 8h às 18h. Sua solicitação já "
        "ficou registrada — assim que o expediente começar, um atendente te responde! 😊"
    )
    return {"mensagem_final": mensagem}
