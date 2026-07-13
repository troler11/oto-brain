"""
Port fiel da cadeia determinística "Navegação Direta"/"Troca Direta" do workflow n8n principal
(`oX6ePJbAVF7C0NoX`), mapeada via `get_workflow_details` 13/07/2026 (achada numa auditoria de
fechamento — pergunta do Lucas "valide se tem mais algum pendente"). 15 nós reais, dois ramos que
bypassa o agente de IA quando dá pra responder só com paginação/busca de agenda determinística.

Gatilhos (setados em `Extrair Rota`, já portados em `app.er`/`app.agentes`):
  - `eh_navegacao` — nasce na Mini IA classificadora (`app.agentes.IAOutputClassificador`), pode
    ser sobrescrito por regras determinísticas em `app.er` (ex.: força `False` se paciente citou
    dia da semana diferente de `coleta_data` — `NAVIG_OUTRO_DIA` — ou se `eh_troca_data` também
    está true, que tem prioridade).
  - `eh_troca_data` — 100% determinístico, nasce só dentro de `app.er` (regras de troca de
    período/dia da semana com cache ativo).

⚠️ ACHADO (13/07/2026, validado com `processar_turno()` de ponta a ponta antes de fechar este
port): `eh_navegacao` da Mini IA é rastreado por `app.er.processar_intake` num dict `ia_output`
SEPARADO de `base` (`ia_output["eh_navegacao"] = ...` em vários pontos, nunca `base["eh_navegacao"]
= ...`) — esse dict nunca é fundido de volta em `base` em lugar nenhum do `app.er.processar()`.
Resultado: `r.base.get("eh_navegacao")` é sempre `None`/falsy hoje, então o RAMO NAVEGAÇÃO deste
módulo (via `_detectar_navegacao_final()`) nunca dispara na prática — gap PRÉ-EXISTENTE em
`app.er`, não introduzido aqui, fora do escopo desta port (mexer nisso é decisão separada, toca
um arquivo de 6000+ linhas já testado com 259 casos). `eh_troca_data`, por ser setado direto em
`base` (não em `ia_output`), sobrevive normalmente — confirmado com probe real via
`processar_turno()`. O RAMO TROCA deste módulo está 100% funcional; o ramo Navegação está com
código pronto e testado isoladamente, mas inalcançável até alguém corrigir `app.er` pra fundir
`ia_output` em `base` (ou expor `eh_navegacao` como campo de primeira classe, igual
`rota_agente`/`intencao_rapida` já são).

RAMO NAVEGAÇÃO: `_parsear_acao_navegar()` (parsing de texto livre: "dia NN[/MM]", "amanhã", nome
de dia da semana, "voltar/antes/anterior/mais cedo", default "avancar") → `navegar_agenda.
processar()` (já portado, mesmos 3 passos do sub-workflow real: ler cache → paginar → atualizar
índice) → `_formatar_resposta_navegacao()` (ordena horários por preferência salva na sessão,
`agenda_json.horario_pref`). Se o cache estiver vazio/esgotado (`precisa_buscar=True`), retorna
`None` — MESMO padrão do n8n real (`Precisa Buscar?` IF manda pro `Roteador`/agente de IA
completo quando o atalho não tem dados suficientes). Só esse ramo tem esse fallback.

RAMO TROCA: `buscar_agenda_fluxo.buscar_agenda_completo()` (já portado, só usado pelo efeito
colateral de popular `agenda_cache` — resultado descartado, igual ao node real que não lê a
saída de "Chamar buscar Troca") → `navegar_agenda.processar(acao='ver')` na cache recém-populada
→ `_formatar_resposta_troca()`. SEM fallback pro agente — se não achar nada, responde com
mensagem genérica mesmo (fiel ao node real, que não tem `Precisa Buscar?` equivalente).

Ambos os ramos gravam `agenda_cache.ultimo_dia_exibido` de novo no final (`_salvar_dia_exibido`)
— redundante em cima do que `atualizar_indice_agenda_cache` já grava dentro de `navegar_agenda.
processar()`, MAS não é bug/duplicata inócua: no ramo Navegação, `_formatar_resposta_navegacao`
pode reordenar/truncar os horários (top 3 mais próximos da preferência), então o valor final
gravado por `_salvar_dia_exibido` diverge do valor bruto já gravado — union real, replicado
fielmente (mesma query SQL dos nós `Salvar Dia Exibido`/`Salvar Dia Troca`, com `WHERE telefone =
$1` EXATO, não o filtro tolerante a prefixo/DDI usado no resto do módulo — preservado como está
no node real, não "corrigido").

Ambos os ramos, no n8n real, pulam `Extrair Intencao Final1`/`State Validator` inteiramente e vão
direto pro envio (mesmo padrão do Reask Engine, já mapeado e ligado hoje) — replicado em
`app.pipeline`: quando este módulo retorna um dict (não `None`), o turno termina ali,
`sv_result`/`sv_reason` ficam vazios, sem passar por SV.

Falha de IO (TiSaude/Postgres) é capturada e vira `None` (fall-through pro agente completo) — a
MESMA semântica de "`precisa_buscar`", não a semântica "sem opinião shadow" de
`confirmar_presenca_fluxo`/`processar_remarcacao` (que não têm fallback pra agente no grafo
real). Aqui o fallback pro agente É o design real do node, então uma falha de IO cair no mesmo
caminho é a coisa mais fiel a fazer, não um atalho de segurança inventado.
"""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from datetime import date, timedelta

import httpx
import psycopg
from psycopg.types.json import Jsonb

from app import buscar_agenda_fluxo, db, navegar_agenda

logger = logging.getLogger("oto-brain.navegacao_direta")

_DIAS_NAVEGAR = (
    (("segunda", "seg"), 1), (("terca", "ter"), 2), (("quarta", "qua"), 3),
    (("quinta", "qui"), 4), (("sexta", "sex"), 5), (("sabado", "sab"), 6), (("domingo", "dom"), 0),
)


def _strip_nfd(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s or "") if unicodedata.category(c) != "Mn")


def _get_day_js(iso_date: str) -> int:
    y, m, d = (int(p) for p in iso_date.split("-"))
    return (date(y, m, d).weekday() + 1) % 7


def _detectar_navegacao_final(base: dict) -> bool:
    """Port fiel do node 'Detectar Navegacao' — refina o `eh_navegacao` cru que a Mini IA
    classificadora emitiu (ver docstring do módulo), ANTES do IF 'É Navegação?' real decidir.
    Dois overrides: NAVIG_OUTRO_DIA (paciente citou um dia da semana diferente do
    `coleta_data` salvo -> não é navegação simples, precisa buscar de novo -> `False`) e
    TROCA_DATA_OVERRIDE_NAV (`eh_troca_data` tem prioridade absoluta sobre `eh_navegacao`)."""
    eh_navegacao = bool(base.get("eh_navegacao"))
    coleta_data = base.get("coleta_data")

    eh_navegacao_final = eh_navegacao
    if eh_navegacao and coleta_data:
        texto_norm = _strip_nfd((base.get("texto_ia") or "").lower())
        coleta_dow = _get_day_js(coleta_data)
        for nomes, num in _DIAS_NAVEGAR:
            if any(n in texto_norm for n in nomes):
                if num != coleta_dow:
                    eh_navegacao_final = False
                break

    if base.get("eh_troca_data"):
        eh_navegacao_final = False

    return eh_navegacao_final


def _parsear_acao_navegar(texto_ia: str, *, hoje: date | None = None) -> dict:
    """Port fiel do node 'Montar Input Navegar' — só a parte de parsing (acao/data); telefone e
    unidade são resolvidos por quem chama, fora desta função pura."""
    hoje = hoje or date.today()
    texto_norm = _strip_nfd((texto_ia or "").lower())

    match_dia = re.search(r"\bdia\s+(\d{1,2})(?:/(\d{1,2}))?", texto_norm)
    if match_dia:
        dia = int(match_dia.group(1))
        mes = int(match_dia.group(2)) if match_dia.group(2) else hoje.month
        ano = hoje.year
        if not match_dia.group(2) and dia < hoje.day:
            mes += 1
            if mes > 12:
                mes = 1
                ano += 1
        return {"acao": "ir_para", "data": f"{ano:04d}-{mes:02d}-{dia:02d}"}

    if "amanha" in texto_norm:
        return {"acao": "ir_para", "data": (hoje + timedelta(days=1)).isoformat()}

    for nomes, _num in _DIAS_NAVEGAR:
        if any(n in texto_norm for n in nomes):
            return {"acao": "ir_para", "data": nomes[0]}

    if any(p in texto_norm for p in ("voltar", "antes", "anterior", "mais cedo")):
        return {"acao": "voltar", "data": None}

    return {"acao": "avancar", "data": None}


def _formatar_horarios(horarios_str: str, *, horario_pref: int = 0) -> list[str]:
    horarios = [h.strip() for h in (horarios_str or "").split(",") if h.strip()]
    if horario_pref > 0 and horarios:
        def _diff(h: str) -> int:
            return abs(int(h.split(":")[0]) - horario_pref)
        horarios = sorted(horarios, key=lambda h: (_diff(h), h))[:3]
        horarios.sort()
    return horarios


def _formatar_resposta_navegacao(r: dict, *, horario_pref: int = 0) -> dict:
    """Port fiel do node 'Formatar Resposta Navegacao'."""
    if not r or r.get("status") in ("SEM_CACHE", "ESGOTADO"):
        return {
            "mensagem_final": None, "precisa_buscar": True,
            "motivo": r.get("status") if r else "SEM_RETORNO",
            "aviso": (r.get("aviso") if r else "Sem retorno da ferramenta"),
        }

    dia = r.get("dia")
    if not dia:
        return {
            "mensagem_final": "Não encontrei horários disponíveis nessa data 😔\nQuer ver o próximo dia disponível? 😊",
            "precisa_buscar": False, "motivo": "SEM_DIA",
        }

    data_iso = dia.get("data")
    data_formatada = "/".join(reversed(data_iso.split("-"))) if data_iso else data_iso

    linhas = [f"📅 {data_formatada}"]
    medicos_exibidos = []
    for m in dia.get("medicos") or []:
        horarios = _formatar_horarios(m.get("horarios") or "", horario_pref=horario_pref)
        if horarios:
            linhas.append(f"🩺 Dr(a). {m.get('medico')}: {', '.join(horarios)}")
            medicos_exibidos.append({
                "medico": m.get("medico"), "idLocal": m.get("idLocal"), "idCalendar": m.get("idCalendar"),
                "horarios": ", ".join(horarios),
            })

    linhas.append("Qual horário prefere?")

    return {
        "mensagem_final": "\n".join(linhas), "precisa_buscar": False,
        "status": r.get("status"), "dias_restantes": r.get("dias_restantes"),
        "total_dias": r.get("total_dias"),
        "dia_exibido": {"data": dia.get("data"), "medicos": medicos_exibidos},
    }


def _formatar_resposta_troca(r: dict, *, data_alvo_troca: str | None) -> dict:
    """Port fiel do node 'Formatar Resposta Troca' (mensagem de fallback sem acentos, fiel ao JS)."""
    if not r or r.get("status") in ("SEM_CACHE", "ESGOTADO") or not r.get("dia"):
        return {"mensagem_final": "Nao encontrei horarios disponiveis nessa data. Quer tentar outro dia? 😊", "dia_exibido": None}

    dia = r["dia"]
    data_fmt = "/".join(reversed(dia["data"].split("-"))) if dia.get("data") else ""
    linhas = [f"Encontrei horarios para {data_fmt}:"]
    for m in dia.get("medicos") or []:
        horarios = _formatar_horarios(m.get("horarios") or "")
        if horarios:
            linhas.append(f"🩺 Dr(a). {m.get('medico')}: {', '.join(horarios)}")
    linhas.append("Qual prefere? 😊")

    prefixo = ""
    data_retornada = dia.get("data")
    if data_alvo_troca and data_retornada != data_alvo_troca:
        ano_a, mes_a, dia_a = data_alvo_troca.split("-")
        prefixo = f"No dia {dia_a}/{mes_a} nao encontramos horarios disponiveis para o periodo solicitado.\n"

    return {"mensagem_final": prefixo + "\n".join(linhas), "dia_exibido": dia}


def _horario_pref_da_sessao(sessao: dict | None) -> int:
    if not sessao:
        return 0
    aj = sessao.get("agenda_json")
    if isinstance(aj, str):
        try:
            aj = json.loads(aj)
        except (ValueError, TypeError):
            aj = {}
    aj = aj or {}
    try:
        return int(aj.get("horario_pref") or aj.get("horario_pref_num") or 0)
    except (TypeError, ValueError):
        return 0


def _salvar_dia_exibido(conn: psycopg.Connection, telefone: str, unidade: str, dia_exibido: dict) -> None:
    """Port fiel dos nós 'Salvar Dia Exibido'/'Salvar Dia Troca' — mesma query nos dois. Nota:
    `WHERE telefone = $1` é comparação EXATA no node real, diferente do filtro tolerante a
    prefixo/DDI (`RIGHT(regexp_replace(...), 11)`) usado no resto deste módulo — preservado como
    está, não "corrigido" por conta própria."""
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE agenda_cache
            SET ultimo_dia_exibido = %(dia_exibido)s
            WHERE telefone = %(telefone)s AND unidade = %(unidade)s AND expira_em > NOW();
            """,
            {"telefone": telefone, "unidade": unidade, "dia_exibido": Jsonb(dia_exibido)},
        )


def navegacao_direta(
    base: dict, *, telefone: str, conn: psycopg.Connection, sessao: dict | None = None, hoje: date | None = None,
) -> dict | None:
    """Orquestra o ramo 'Navegação': replica os 3 passos internos do sub-workflow
    'navegar_agenda' (ler cache → paginar → atualizar índice, mesmos de `app.tools_agenda.
    _executor_navegar_agenda`) + a camada de parsing/formatação que só existe no atalho direto.
    `None` = 'precisa_buscar' (cache vazio/esgotado) — cai pro agente de IA completo, MESMO
    fallback do node real."""
    unidade = base.get("unidade_cache") or ""
    parse = _parsear_acao_navegar(base.get("texto_ia") or "", hoje=hoje)

    cache_row = db.ler_agenda_cache(conn, telefone, unidade)
    r = navegar_agenda.processar(cache_row, parse["acao"], parse.get("data"))
    if r.get("status") != "SEM_CACHE":
        db.atualizar_indice_agenda_cache(conn, telefone, unidade, r.get("indice_atual") or 0, r.get("dia"))

    resultado = _formatar_resposta_navegacao(r, horario_pref=_horario_pref_da_sessao(sessao))
    if resultado.get("precisa_buscar"):
        return None

    if resultado.get("dia_exibido"):
        _salvar_dia_exibido(conn, telefone, unidade, resultado["dia_exibido"])

    return resultado


def troca_direta(
    base: dict, *, telefone: str, conn: psycopg.Connection, tisaude_client: httpx.Client | None = None,
    hoje: date | None = None,
) -> dict:
    """Orquestra o ramo 'Troca': busca agenda de verdade (só pelo efeito colateral de popular o
    cache — resultado descartado, fiel ao node real que não lê a saída de 'Chamar buscar Troca')
    + navega no cache recém-populado (`acao='ver'`). SEM fallback pro agente — sempre retorna uma
    mensagem, mesmo genérica quando não acha nada (fiel ao node real)."""
    unidade = base.get("coleta_unidade") or ""
    buscar_agenda_fluxo.buscar_agenda_completo(
        unidade=unidade, data=base.get("data_alvo_troca") or "",
        medico=base.get("medico_troca") or "sem preferencia", periodo=base.get("coleta_periodo") or "",
        telefone_paciente=telefone, dia_semana=base.get("dia_semana_troca") or "", horario_preferencia="",
        conn=conn, tisaude_client=tisaude_client, hoje=hoje,
    )

    cache_row = db.ler_agenda_cache(conn, telefone, unidade)
    r = navegar_agenda.processar(cache_row, "ver")
    if r.get("status") != "SEM_CACHE":
        db.atualizar_indice_agenda_cache(conn, telefone, unidade, r.get("indice_atual") or 0, r.get("dia"))

    resultado = _formatar_resposta_troca(r, data_alvo_troca=base.get("data_alvo_troca"))
    if resultado.get("dia_exibido"):
        _salvar_dia_exibido(conn, telefone, unidade, resultado["dia_exibido"])

    return {"mensagem_final": resultado["mensagem_final"]}


def processar(
    base: dict, *, telefone: str, sessao: dict | None, conn: psycopg.Connection,
    tisaude_client: httpx.Client | None = None, hoje: date | None = None,
) -> dict | None:
    """Ponto de entrada único pra `app.pipeline`: aplica `_detectar_navegacao_final()` (port do
    node 'Detectar Navegacao' — refina `eh_navegacao` antes de checar) e `eh_troca_data`. `None` =
    nenhum dos dois ativo, OU o ramo escolhido decidiu cair pro agente completo, OU falha de IO
    — em todos os casos, `app.pipeline` deve seguir pro despacho normal."""
    if _detectar_navegacao_final(base):
        try:
            return navegacao_direta(base, telefone=telefone, conn=conn, sessao=sessao, hoje=hoje)
        except Exception:
            logger.exception("navegacao_direta: falha de IO, caindo pro agente completo (telefone=%s)", telefone)
            return None

    if base.get("eh_troca_data"):
        try:
            return troca_direta(base, telefone=telefone, conn=conn, tisaude_client=tisaude_client, hoje=hoje)
        except Exception:
            logger.exception("troca_direta: falha de IO, caindo pro agente completo (telefone=%s)", telefone)
            return None

    return None
