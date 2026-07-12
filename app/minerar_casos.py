"""
Fase 4 (mecanismo 2) do plano de migração — pipeline de casos. Minera `chat_limpo` (histórico
completo desde 07/07, ver memória `reference_oto_postgres_access`) em busca de 4 padrões que
viram matéria-prima de aprendizado: transferência pra humano, desistência, loop de re-pergunta,
correção do paciente. Proposta e aprovada por Lucas em 12/07 (heurísticas v1, deliberadamente
simples — "primeira safra", não classificador definitivo).

Casos aprovados (via `status='aprovado'` em `casos_aprendizado`, revisão manual) viram (a) teste
de regressão pytest e (b) exemplo few-shot no prompt do agente correspondente — trabalho futuro,
fora do escopo desta mineração.

Módulo 100% puro (lista de mensagens in, lista de casos out) — sem Postgres, testável direto.
O wrapper de IO (lê `chat_limpo`/`agendamentos`, grava em `casos_aprendizado`) é
`scripts/mine_casos_aprendizado.py`.
"""

from __future__ import annotations

import re
from datetime import timedelta

GAP_SESSAO = timedelta(hours=2)

_RE_CORRECAO = re.compile(
    r"não,?\s*eu (disse|falei)|não é isso|não foi isso|não era isso|"
    r"(tá|ta|está)\s+errado|isso\s+(tá|ta|está)\s+errado|não quis dizer isso|entendeu errado",
    re.IGNORECASE,
)


def _normalizar(texto: str | None) -> str:
    return re.sub(r"\s+", " ", (texto or "")).strip().lower()[:60]


def _sessoes(msgs: list[dict]) -> list[list[dict]]:
    """Agrupa mensagens (já ordenadas por `data`) em sessões — gap > GAP_SESSAO entre duas
    mensagens consecutivas do mesmo telefone marca o início de uma conversa nova."""
    sessoes: list[list[dict]] = []
    atual: list[dict] = []
    anterior = None
    for m in msgs:
        if anterior is not None and m["data"] - anterior > GAP_SESSAO:
            sessoes.append(atual)
            atual = []
        atual.append(m)
        anterior = m["data"]
    if atual:
        sessoes.append(atual)
    return sessoes


def _contexto(sessao: list[dict], idx: int, antes: int = 2, depois: int = 1) -> list[dict]:
    ini = max(0, idx - antes)
    fim = min(len(sessao), idx + depois + 1)
    return [{"origem": m["origem"], "texto": m["texto"], "data": m["data"].isoformat()} for m in sessao[ini:fim]]


def minerar_telefone(telefone: str, msgs: list[dict], tem_agendamento: bool) -> list[dict]:
    """`msgs`: lista de `{telefone, texto, origem, enviado_por, data}` (linhas de `chat_limpo`
    de UM telefone, em qualquer ordem). Retorna casos no shape pronto pra `casos_aprendizado`
    (exceto `id`/`detectado_em`/`status`, que o banco preenche)."""
    msgs = sorted(msgs, key=lambda m: m["data"])
    sessoes = _sessoes(msgs)
    casos: list[dict] = []

    # transferencia_humano: 1 por sessão, na primeira mensagem com enviado_por preenchido
    # (humano assumiu de verdade — não é o bot dizendo "vou te transferir").
    for sessao in sessoes:
        for idx, m in enumerate(sessao):
            if m.get("enviado_por"):
                casos.append({
                    "telefone": telefone,
                    "categoria": "transferencia_humano",
                    "turno_texto": m["texto"],
                    "origem_data": m["data"],
                    "contexto": _contexto(sessao, idx),
                })
                break

    # desistencia: só na ÚLTIMA sessão do telefone (histórico inteiro nunca voltou), termina
    # com pergunta do bot sem resposta, e nunca virou agendamento.
    if sessoes and not tem_agendamento:
        ultima = sessoes[-1]
        if ultima and ultima[-1]["origem"] == "ia_ou_recepcao":
            casos.append({
                "telefone": telefone,
                "categoria": "desistencia",
                "turno_texto": ultima[-1]["texto"],
                "origem_data": ultima[-1]["data"],
                "contexto": _contexto(ultima, len(ultima) - 1),
            })

    # loop_repergunta + correcao: dentro de cada sessão.
    for sessao in sessoes:
        vistos: dict[str, int] = {}
        for idx, m in enumerate(sessao):
            if m["origem"] == "ia_ou_recepcao":
                chave = _normalizar(m["texto"])
                if not chave:
                    continue
                vistos[chave] = vistos.get(chave, 0) + 1
                if vistos[chave] == 2:
                    casos.append({
                        "telefone": telefone,
                        "categoria": "loop_repergunta",
                        "turno_texto": m["texto"],
                        "origem_data": m["data"],
                        "contexto": _contexto(sessao, idx),
                    })
            elif m["origem"] == "paciente" and _RE_CORRECAO.search(m["texto"] or ""):
                casos.append({
                    "telefone": telefone,
                    "categoria": "correcao",
                    "turno_texto": m["texto"],
                    "origem_data": m["data"],
                    "contexto": _contexto(sessao, idx),
                })

    return casos


def minerar_tudo(mensagens_por_telefone: dict[str, list[dict]], telefones_com_agendamento: set[str]) -> list[dict]:
    casos: list[dict] = []
    for telefone, msgs in mensagens_por_telefone.items():
        casos.extend(minerar_telefone(telefone, msgs, telefone in telefones_com_agendamento))
    return casos
