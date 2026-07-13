"""
Port fiel do nó 'Verificar Cadastro3' — DEPLOY/_proposed_Verificar_Cadastro3.js (69 linhas,
snapshot 12/07/2026). Fase 1 do plano de migração (ver
C:\\Users\\lucas\\.claude\\plans\\unified-coalescing-puppy.md).

⚠️ CORREÇÃO (13/07/2026, `get_workflow_details` completo no grafo real — a premissa abaixo, de
uma fase anterior desta migração, estava ERRADA): NÃO roda condicionalmente num fluxo "Ver"
separado, nem é gateado por `intencao_rapida=="ver"`. Roda **incondicionalmente em toda
mensagem recebida** — é a fase de identificação de paciente (`Login TiSaude (Inicial)` → `Buscar
Paciente por Telefone` → `Achou Paciente?` → `BUSCAR PACIENTE ID1`/fallback → **este node**) que
antecede `Carregar Sessao`/`Montar Contexto`/`AI Agent`/`Extrair Rota` no grafo real — ou seja, é
estrutural, não um atalho. Recebe a lista de pacientes já buscados (fonte preferencial = fichas
completas do "BUSCAR PACIENTE ID1"; fallback = busca por telefone) e devolve UM ITEM POR PACIENTE
(n8n `.map()` — por isso `processar()` retorna `list[dict]`, não um dict único como os outros
ports desta leva).

⚠️ NÃO LIGADO DE PROPÓSITO (mesma investigação, decisão explícita — não é gap/pendência): o dado
diferencial que este node produz (`index_paciente`/`total_pacientes`, lista numerada de
pacientes) **não é lido por nenhum consumidor no grafo real** — nem pelo `AI Agent`, nem por
`Agente Triagem/Ver`, nem por `Montar Contexto`. É vestigial mesmo no n8n original. Ligar isso no
port Python exigiria portar toda a cadeia de identificação de paciente acima (login TiSaude +
busca por telefone + busca por ID) só pra alimentar um resultado que ninguém consome — sem valor,
não é prioridade. Se o pipeline Python já resolve identificação de paciente de outra forma (via
`busca_paciente_id1`/`busca_paciente_telefone` passados prontos pro `app.pipeline.processar_turno`
por quem chama), esse é o motivo: a etapa foi resolvida fora deste módulo.

⚠️ BUG achado em produção (n8n real, não é do port): o JS original referencia
`$items('Carregar Cache1')[0]?.json`, mas **não existe nenhum node `Carregar Cache1`** no grafo
— a chamada está dentro de um try/catch vazio, falha silenciosa, `cache_ativo`/`unidade_cache`/
`ultimo_dia_exibido` sempre saem `false`/`''`/`null` em produção. Reportado a Lucas separadamente
(fora do escopo desta migração corrigir workflow ativo sem aprovação explícita — ver
CLAUDE.local.md). Este port replica o parâmetro `cache_row` como recebido (fiel ao código, que já
está sempre vazio na prática).

Tem um bloco de cache (`cache_ativo`/`unidade_cache`/`ultimo_dia_exibido`/`ultimo_dia_texto`)
parecido com o de `app.montar_contexto`, mas NÃO byte-idêntico — `ultimo_dia_texto` aqui mantém
a data em ISO (`yyyy-mm-dd`), enquanto Montar Contexto reformata pra `dd/mm/yyyy`. Mantido
separado, fiel a cada JS, não unificado (regra: só reusar quando idêntico, não quando parecido).
"""

from __future__ import annotations

import json


def _extrair_pacientes(input_items: list[dict] | None) -> list[dict]:
    # JS `.filter(Boolean)`: objeto vazio `{}` é truthy em JS (diferente de Python, onde
    # `bool({})` é False) — `is not None` replica a semântica de truthiness de objeto do JS.
    in_fc = [i for i in (input_items or []) if i is not None]
    if in_fc and in_fc[0].get("id") and not in_fc[0].get("data"):
        return in_fc
    resposta_paciente = in_fc[0] if in_fc else {}
    if resposta_paciente.get("data"):
        return resposta_paciente["data"]
    if resposta_paciente.get("id"):
        return [resposta_paciente]
    return []


def processar(input_items: list[dict] | None, cache_row: dict | None, mensagem_agrupada: str) -> list[dict]:
    pacientes = _extrair_pacientes(input_items)

    cache_ativo = False
    unidade_cache = ""
    ultimo_dia_exibido = None

    if cache_row:
        if cache_row.get("agenda_json"):
            cache_ativo = True
            try:
                aj = json.loads(cache_row["agenda_json"]) if isinstance(cache_row["agenda_json"], str) else cache_row["agenda_json"]
                unidade_cache = aj.get("unidade") or ""
            except (ValueError, TypeError, AttributeError):
                pass
        if cache_row.get("ultimo_dia_exibido") is not None:
            raw = cache_row["ultimo_dia_exibido"]
            try:
                if isinstance(raw, str) and raw.strip().startswith("{"):
                    ultimo_dia_exibido = json.loads(raw)
                elif isinstance(raw, dict):
                    ultimo_dia_exibido = raw
            except (ValueError, TypeError):
                pass

    ultimo_dia_texto = "NENHUM"
    if ultimo_dia_exibido and ultimo_dia_exibido.get("data"):
        medicos = " | ".join(
            f"Dr(a). {m.get('medico')}: {m.get('horarios')}" for m in (ultimo_dia_exibido.get("medicos") or [])
        )
        ultimo_dia_texto = f"Data: {ultimo_dia_exibido['data']} | {medicos}"

    wpp_msg = mensagem_agrupada or "Oi"

    # FIX_ORDEM_PACIENTES
    pacientes = sorted(pacientes, key=lambda p: p.get("id") or 0)

    return [
        {
            "paciente_encontrado": True,
            "index_paciente": index,
            "total_pacientes": len(pacientes),
            "id_tisaude": paciente.get("id"),
            "nome": paciente.get("name"),
            "cpf": paciente.get("cpf"),
            "nascimento": paciente.get("dateOfBirth") or paciente.get("nascimento"),
            "email": paciente.get("email") if (paciente.get("email") and not paciente.get("blacklistEmail")) else None,
            "texto_ia": wpp_msg,
            "cache_ativo": cache_ativo,
            "unidade_cache": unidade_cache,
            "ultimo_dia_exibido": ultimo_dia_exibido,
            "ultimo_dia_texto": ultimo_dia_texto,
        }
        for index, paciente in enumerate(pacientes)
    ]
