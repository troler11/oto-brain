"""
Port fiel do sub-workflow n8n 'Ferramenta - Buscar Agenda TiSaude (V4 Final)' (id
`gMQaU2CQbwdPUnUA`), lido via `get_workflow_details` 13/07/2026 — sem arquivo `_proposed_` no
DEPLOY pra esta tool, snapshot direto do node JS. Nós portados: 'Configurar Busca2' (config +
normalização), 'Separar Medicos2' (filtro de preferência), o loop de 21 dias ('Validar Dia2' +
'Filtrar Disponiveis2' + 'GET Horarios2' + 'Acumular Dia1' + 'Avançar 1 Dia2', bound por
'Limite 20 Dias?1': `$runIndex <= 20`), 'Montar Resposta Final1' e 'Fim - Retornar IA1'. As
chamadas HTTP unitárias (médicos/disponibilidade/horários) já existiam em `app.tisaude` — esta
peça é só a ORQUESTRAÇÃO que faltava (loop, acumulador, filtros, resposta final + cache).

O node 'Salvar Primeiro Dia Exibido' existe no workflow mas está DESCONECTADO do grafo de
conexões (não aparece em nenhum lado de `connections` como source nem target de fluxo real) —
não portado de propósito, é código morto no n8n.

Escopo (13/07/2026, mesma decisão do wiring de rota=5/navegar_agenda): esta função só faz
LEITURA (busca real na TiSaude) + grava o cache em `agenda_cache` — não muta nenhum agendamento,
segura de rodar em shadow. Ainda não ligada a nenhum dispatcher/agente (peça C, pendente).
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date, timedelta

import httpx
import psycopg
from psycopg.types.json import Jsonb

from app import tisaude

_DIAS_MAP_BUSCA = {
    "domingo": 0, "dom": 0, "segunda": 1, "seg": 1, "terca": 2, "ter": 2, "quarta": 3, "qua": 3,
    "quinta": 4, "qui": 4, "sexta": 5, "sex": 5, "sabado": 6, "sab": 6,
}
_DIAS_LONGO = ["domingo", "segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado"]
_DIAS_CURTO = ["domingo", "segunda", "terça", "quarta", "quinta", "sexta", "sábado"]

_AVISO_SEM_VAGA_GENERICO = "Nenhuma vaga nos próximos 20 dias. Ofereça trocar unidade ou período."
_AVISO_CACHE_SALVO = (
    "✅ Cache salvo. Para ver próximas datas use navegar_agenda(acao=avancar). Ao exibir datas, "
    "escreva o dia da semana EXATAMENTE como em dia.dia_semana_nome — ⛔ NUNCA deduza o dia da "
    "semana do pedido original, do histórico ou de cálculo próprio."
)


# ─── Pura ───────────────────────────────────────────────────────────────────────────────────

def _get_day_js(iso_date: str) -> int:
    """getDay() de `new Date(iso+'T12:00:00[-03:00]')`: domingo=0..sábado=6 — mesmo helper de
    app.preparar_input_agenda/app.navegar_agenda (aritmética de data pura, sem fuso, resultado
    idêntico ao original)."""
    y, m, d = (int(p) for p in iso_date.split("-"))
    return (date(y, m, d).weekday() + 1) % 7


def _limpar_nome_medico(t: str) -> str:
    if not t:
        return ""
    limpo = "".join(c for c in unicodedata.normalize("NFD", str(t).lower()) if unicodedata.category(c) != "Mn")
    limpo = re.sub(r"^(dr\(a\)\.?\s+|dra?\.?\s+)", "", limpo)
    return limpo.strip()


def _filtrar_medicos_por_preferencia(medicos: list[dict], medico_pref: str) -> list[dict]:
    """`medicos` já normalizado por `tisaude.extrair_lista_medicos` (garante idCalendar/medico).
    Sem preferência (vazio ou contém "sem preferencia") -> lista inteira, igual ao JS."""
    pref = _limpar_nome_medico(medico_pref)
    tem_pref = pref != "" and "sem preferencia" not in pref
    if not tem_pref:
        return list(medicos)
    return [m for m in medicos if (lambda n: n in pref or pref in n)(_limpar_nome_medico(m.get("medico") or ""))]


def _normalizar_telefone_busca(telefone: str | None) -> str:
    """FIX_66787 (mesmo do node): só dígitos, prefixo '55' sem duplicar."""
    raw = re.sub(r"\D", "", str(telefone or ""))
    return ("55" + re.sub(r"^55", "", raw)) if raw else ""


def _resolver_dia_semana_num(dia_semana: str | None) -> int | None:
    if not dia_semana:
        return None
    raw = tisaude._normalizar(str(dia_semana))
    return _DIAS_MAP_BUSCA.get(raw)


def _filtrar_horarios_por_periodo(horarios: list[str], periodo: str) -> list[str]:
    """`horarios` já vem normalizado/ordenado por `tisaude.horarios_do_dia` (HH:MM) — só aplica
    o filtro de período (manhã <12h / tarde 12-18h / noite >=18h)."""
    p = tisaude._normalizar(str(periodo or ""))
    resultado = []
    for h in horarios:
        hora = int(h[:2])
        manter = True
        if "manha" in p and hora >= 12:
            manter = False
        elif "tarde" in p and (hora < 12 or hora >= 18):
            manter = False
        elif "noite" in p and hora < 18:
            manter = False
        if manter:
            resultado.append(h)
    return sorted(resultado)


def _resposta_sem_vaga(dia_semana_num: int | None, data_alvo: str, *, hoje: date | None = None) -> dict:
    """Port de 'Fim - Retornar IA1' pro ramo sem primeiro dia (nenhuma vaga achada)."""
    filtro_ativo = dia_semana_num is not None
    d_nome = _DIAS_CURTO[dia_semana_num] if filtro_ativo else ""
    dt_est = (date.fromisoformat(data_alvo) + timedelta(days=21)).isoformat()
    dt_hoje = (hoje or date.today()).isoformat()

    if not filtro_ativo:
        return {
            "status": "SEM_VAGA", "total_dias_com_vaga": 0, "dia_semana_pedido": "",
            "proxima_busca_opcao2": None, "proxima_busca_opcao3": None,
            "aviso": _AVISO_SEM_VAGA_GENERICO,
        }

    aviso = (
        f'Nenhuma vaga de {d_nome} nos próximos 20 dias. ⛔ NÃO rechame buscar_agenda sem dia_semana '
        f'agora. INFORME o paciente: "[MEDICO] não tem vagas de {d_nome} nos próximos 20 dias na '
        '[UNIDADE]." e exiba o menu EXATO: "O que deseja fazer?\n1️⃣ Buscar outro médico\n2️⃣ Ver '
        f'outros dias que [MEDICO] atende\n3️⃣ Procurar mais para frente". ⛔ Depois de exibir o menu, '
        'PARE e AGUARDE a resposta — NÃO chame buscar_agenda de novo neste turno e NÃO execute '
        'nenhuma opção antes do paciente escolher. QUANDO o paciente responder: Opção 2 = chame '
        f'buscar_agenda EXATAMENTE com data="{dt_hoje}" e SEM dia_semana (mesmos unidade/medico/'
        'periodo) — ⛔ NÃO use a data onde a busca parou. Opção 3 = chame buscar_agenda EXATAMENTE '
        f'com data="{dt_est}" e dia_semana="{d_nome}". ⛔ Na opção 3 NUNCA omita dia_semana. ⛔ NUNCA '
        'anuncie ou prometa que a consulta pode ser "hoje" ou "amanhã" — apresente APENAS as datas '
        'que a tool retornar.'
    )
    return {
        "status": "FILTRO_SEM_RESULTADO", "total_dias_com_vaga": 0, "dia_semana_pedido": d_nome,
        "proxima_busca_opcao2": {"data": dt_hoje}, "proxima_busca_opcao3": {"data": dt_est, "dia_semana": d_nome},
        "aviso": aviso,
    }


# ─── IO ─────────────────────────────────────────────────────────────────────────────────────

def buscar_agenda_completo(
    *,
    unidade: str,
    data: str | None,
    medico: str | None,
    periodo: str | None,
    telefone_paciente: str,
    dia_semana: str | None = None,
    horario_preferencia: str | None = None,
    conn: psycopg.Connection,
    tisaude_client: httpx.Client | None = None,
    hoje: date | None = None,
) -> dict:
    """Orquestra a busca completa (login + loop de 21 dias) e grava o resultado em
    `agenda_cache` (upsert, TTL 20min — mesma query de 'Salvar Cache Postgres'). Retorna o shape
    que o agente recebe ('Fim - Retornar IA1'): `{"status": "OK", "dia": {...}, ...}` ou
    `{"status": "SEM_VAGA"|"FILTRO_SEM_RESULTADO", ...}`."""
    token = tisaude.login(client=tisaude_client)
    id_local = tisaude.resolver_id_local(unidade)
    data_alvo = (data or "").strip() or (hoje or date.today()).isoformat()
    telefone_norm = _normalizar_telefone_busca(telefone_paciente)
    dia_semana_num = _resolver_dia_semana_num(dia_semana)

    medicos_raw = tisaude.medicos_por_unidade(unidade, token, client=tisaude_client)
    candidatos = _filtrar_medicos_por_preferencia(medicos_raw, medico or "sem preferência")

    dias_acumulados: dict[str, dict[str, dict]] = {}
    data_atual = data_alvo
    for _ in range(21):  # $runIndex 0..20 inclusive, igual 'Limite 20 Dias?1'
        for med in candidatos:
            if not tisaude.dia_disponivel(med["idCalendar"], id_local, data_atual, token, client=tisaude_client):
                continue
            if dia_semana_num is not None and _get_day_js(data_atual) != dia_semana_num:
                continue
            horarios = _filtrar_horarios_por_periodo(
                tisaude.horarios_do_dia(med["idCalendar"], id_local, data_atual, token, client=tisaude_client),
                periodo or "indiferente",
            )
            if not horarios:
                continue
            chave = f"{med['idCalendar']}_{med['medico']}"
            dias_acumulados.setdefault(data_atual, {})
            dias_acumulados[data_atual].setdefault(chave, {
                "medico": med["medico"], "idLocal": id_local, "idCalendar": med["idCalendar"],
                "horarios": ", ".join(horarios),
            })
        data_atual = (date.fromisoformat(data_atual) + timedelta(days=1)).isoformat()

    dias = [
        {"data": d, "dia_semana_nome": _DIAS_LONGO[_get_day_js(d)], "medicos": list(meds.values())}
        for d, meds in sorted(dias_acumulados.items())
    ]

    resultado = {
        "unidade": unidade, "data_solicitada": data_alvo, "telefone_paciente": telefone_norm,
        "horario_pref": int(horario_preferencia) if str(horario_preferencia or "").strip().isdigit() else 0,
        "periodo_pref": periodo or "indiferente", "total_dias_com_vaga": len(dias), "dias": dias,
        "aviso": "" if dias else "Nenhuma vaga nos próximos 20 dias",
    }
    _salvar_agenda_cache(conn, telefone_norm, unidade, resultado)

    if not dias:
        return _resposta_sem_vaga(dia_semana_num, data_alvo, hoje=hoje)

    return {
        "status": "OK", "indice_atual": 0, "total_dias_com_vaga": len(dias),
        "dias_restantes": len(dias) - 1, "dia": dias[0], "aviso": _AVISO_CACHE_SALVO,
    }


def _salvar_agenda_cache(conn: psycopg.Connection, telefone: str, unidade: str, resultado: dict) -> None:
    """Port fiel do node 'Salvar Cache Postgres' — upsert com TTL de 20 minutos."""
    dias = resultado.get("dias") or []
    ultimo_dia_exibido = Jsonb({"data": dias[0]["data"], "medicos": dias[0]["medicos"]}) if dias else None
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO agenda_cache (telefone, unidade, agenda_json, indice_atual, ultimo_dia_exibido, expira_em)
            VALUES (%(telefone)s, %(unidade)s, %(agenda_json)s::jsonb, 0, %(ultimo_dia_exibido)s::jsonb, NOW() + INTERVAL '20 minutes')
            ON CONFLICT (telefone, unidade)
            DO UPDATE SET
              agenda_json = EXCLUDED.agenda_json,
              indice_atual = 0,
              ultimo_dia_exibido = EXCLUDED.ultimo_dia_exibido,
              expira_em = NOW() + INTERVAL '20 minutes';
            """,
            {
                "telefone": telefone, "unidade": unidade, "agenda_json": Jsonb(resultado),
                "ultimo_dia_exibido": ultimo_dia_exibido,
            },
        )
