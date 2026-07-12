"""
Port fiel do nó 'Verificar Cadastro3' — DEPLOY/_proposed_Verificar_Cadastro3.js (69 linhas,
snapshot 12/07/2026). Fase 1 do plano de migração (ver
C:\\Users\\lucas\\.claude\\plans\\unified-coalescing-puppy.md).

Roda no fluxo "Ver" (menu de confirmação de presença), não no fluxo principal do Extrair Rota.
Recebe a lista de pacientes já buscados (fonte preferencial = fichas completas do "BUSCAR
PACIENTE ID1"; fallback = busca por telefone) e devolve UM ITEM POR PACIENTE (n8n `.map()` —
por isso `processar()` retorna `list[dict]`, não um dict único como os outros ports desta leva).

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
