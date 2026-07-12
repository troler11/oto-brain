"""
Client Python pra API TiSaude (https://api.tisaude.com) — porta os 9 workflows-ferramenta n8n
mapeados na investigação da Fase 3 (Buscar Agenda, Criar Consulta e Paciente, Criar Consulta
Terceiro, Cancelar Consulta, Confirmar Presença, Verificar Consulta, Consultar Minhas Consultas
+ tabelas idLocal/idHealthInsurance). "Navegar Agenda" ficou de fora: não chama a API, é
paginação pura sobre `agenda_cache` no Postgres.

Segue o padrão IO de app.db: as funções fazem chamada HTTP real, mas recebem um `client`
(httpx.Client) injetável — testável via httpx.MockTransport, sem rede real (ver
tests/test_tisaude.py). Login não usa refresh token — a API não expõe esse fluxo, e os
workflows n8n originais também relogam a cada chamada em vez de cachear; este client replica o
mesmo comportamento (cada função recebe `token` como argumento — quem orquestra decide se
reusa ou realoga).

Este módulo só embrulha os endpoints; ainda NÃO está ligado ao app.pipeline (rota_agente==5,
buscar/criar/cancelar consulta continuam no caminho legado do n8n até essa integração ser
proposta e aprovada — ver docstring de app.pipeline).
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date, timedelta

import httpx

from app.config import TISAUDE_LOGIN, TISAUDE_SENHA

BASE_URL = "https://api.tisaude.com/api"

# idLocal por unidade — só Tatuapé tem código próprio nos workflows mapeados; toda outra
# unidade (Vila Olímpia e variantes) cai no padrão 1.
ID_LOCAL_POR_UNIDADE = {"tatuape": 2}
ID_LOCAL_PADRAO = 1

STATUS_CANCELAR = -2
STATUS_CONFIRMAR = 3


# ─── Pura: normalização e resolução de IDs (sem IO, testável direto) ──────────────────────

def _normalizar(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFD", texto or "")
    sem_acento = "".join(c for c in sem_acento if unicodedata.category(c) != "Mn")
    return sem_acento.lower().strip()


def resolver_id_local(unidade: str) -> int:
    return ID_LOCAL_POR_UNIDADE.get(_normalizar(unidade), ID_LOCAL_PADRAO)


def resolver_id_health_insurance(convenio: str, unidade: str) -> int:
    """Réplica exata da IIFE JS do nó 'Agendar Consulta' — tabela idêntica (verificada byte a
    byte) nos workflows Criar Consulta e Paciente / Criar Consulta Terceiro. Convênio não
    mapeado -> 1 (mesmo fallback do original)."""
    conv = _normalizar(convenio)
    is_olimpia = "olimpia" in _normalizar(unidade)
    if "porto" in conv:
        return 30475 if is_olimpia else 30493
    if "omint" in conv:
        return 30491
    if "bradesco" in conv:
        return 30490
    if "sami" in conv:
        return 32423 if is_olimpia else 30492
    if "mediservice" in conv or "itau" in conv:
        return 47355
    if "particular" in conv:
        return 32285 if is_olimpia else 1
    return 1


def _strip_titulo(s: str) -> str:
    s = _normalizar(s)
    s = re.sub(r"\b(dr|dra|doutor|doutora)\.?\s*", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def resolver_medico(nome_desejado: str, medicos: list[dict]) -> dict | None:
    """Réplica de 'Extrair IDs Dinamicos2' (Criar Consulta Terceiro) — a versão com fix do
    exec 65707: match bidirecional de substring sem título (Dr./Dra.), fallback por tokens.
    Sem preferência (`nome_desejado` vazio/"sem preferência"/"qualquer") -> primeiro médico
    válido da lista. Nome ESPECÍFICO sem nenhum match -> None (NUNCA agenda com médico errado
    — era o bug do 65707: caía no primeiro da lista mesmo com nome pedido)."""
    alvo = _strip_titulo(nome_desejado)
    candidato_tokens = None
    for m in medicos:
        nome_api = _strip_titulo(m.get("medico") or m.get("name") or "")
        if not nome_api or not alvo:
            continue
        if nome_api in alvo or alvo in nome_api:
            return m
        if candidato_tokens is None:
            tokens = [t for t in alvo.split(" ") if len(t) > 2]
            if tokens and all(t in nome_api for t in tokens):
                candidato_tokens = m
    if candidato_tokens is not None:
        return candidato_tokens

    sem_pref = not alvo or "sem preferencia" in alvo or "qualquer" in alvo
    if sem_pref:
        return next((m for m in medicos if m.get("idCalendar") or m.get("id")), None)
    return None


def extrair_lista_medicos(resposta) -> list[dict]:
    """Normaliza a resposta de GET /schedule/doctors — vem como {'data': [...]}, lista direta,
    ou objeto único de 1 médico (formatos observados em 'Separar Medicos2'). Cada item sai com
    'idCalendar'/'medico' garantidos, mantendo os campos originais da API."""
    if isinstance(resposta, dict) and isinstance(resposta.get("data"), list):
        bruto = resposta["data"]
    elif isinstance(resposta, list):
        bruto = resposta
    elif isinstance(resposta, dict) and resposta.get("id") and resposta.get("name"):
        bruto = [resposta]
    else:
        bruto = []
    return [{**d, "idCalendar": d["id"], "medico": d["name"]} for d in bruto if d.get("id") and d.get("name")]


def filtrar_consultas_ativas(timeline_data: list[dict], *, hoje: str | None = None, limite: int = 5) -> list[dict]:
    """Réplica de 'Filtrar Consultas Ativas1' (Cancelar Consulta) / 'Formatar Consultas'
    (Verificar Consulta) — mesma lógica nos dois: só type=='appointment', status sem
    'desmarcado', data >= hoje, no máximo `limite`. `hoje` (YYYY-MM-DD) injetável pra teste;
    produção usa date.today() por padrão."""
    hoje = hoje or date.today().isoformat()
    consultas: list[dict] = []
    for dia in timeline_data:
        for evento in dia.get("data") or []:
            if evento.get("type") != "appointment":
                continue
            status = evento.get("status") or {}
            status_nome = status.get("name") or ""
            if "desmarcad" in status_nome.lower():
                continue
            data_evento = evento.get("date") or dia.get("date") or ""
            if data_evento < hoje:
                continue
            consultas.append({
                "id": evento.get("id"),
                "data": data_evento,
                "data_br": "/".join(reversed(data_evento.split("-"))) if data_evento else "",
                "hora": evento.get("hour") or "?",
                "medico": (evento.get("calendar") or {}).get("name") or "Médico não informado",
                "status": status_nome or "Ativo",
                "status_id": status.get("id") or 0,
            })
            if len(consultas) >= limite:
                return consultas
    return consultas


# ─── IO: chamadas HTTP reais, `client` injetável pra teste ─────────────────────────────────

def _cliente(client: httpx.Client | None) -> httpx.Client:
    return client if client is not None else httpx.Client(timeout=30.0)


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def login(*, client: httpx.Client | None = None) -> str:
    c = _cliente(client)
    r = c.post(f"{BASE_URL}/login", json={"login": TISAUDE_LOGIN, "senha": TISAUDE_SENHA})
    r.raise_for_status()
    body = r.json()
    return body.get("access_token") or (body.get("data") or {}).get("token") or body.get("token")


def buscar_paciente_por_cpf(cpf: str, token: str, *, client: httpx.Client | None = None) -> list[dict]:
    c = _cliente(client)
    r = c.get(f"{BASE_URL}/patients", params={"search": re.sub(r"\D", "", cpf or "")}, headers=_headers(token))
    r.raise_for_status()
    return r.json().get("data") or []


def buscar_paciente_por_id(id_paciente: int, token: str, *, client: httpx.Client | None = None) -> dict:
    c = _cliente(client)
    r = c.get(f"{BASE_URL}/patients/{id_paciente}", headers=_headers(token))
    r.raise_for_status()
    return r.json()


def criar_paciente(
    *, nome: str, cpf: str, celular: str, nascimento_iso: str, email: str, token: str,
    client: httpx.Client | None = None,
) -> dict:
    """`nascimento_iso` em YYYY-MM-DD -> API espera DD/MM/YYYY (conversão de 'Criar Paciente')."""
    c = _cliente(client)
    nasc_br = (
        "/".join(reversed(nascimento_iso.split("-")))
        if re.match(r"^\d{4}-\d{2}-\d{2}$", nascimento_iso or "")
        else nascimento_iso
    )
    body = {
        "name": nome, "cpf": cpf, "cellphone": celular, "dateOfBirth": nasc_br,
        "email": email or "", "country": "BR", "acceptDuplicate": False,
        "acceptDuplicateCpf": False, "acceptMinorPatient": False, "cellphoneCountry": "BR",
    }
    r = c.post(f"{BASE_URL}/patients/create", json=body, headers=_headers(token))
    r.raise_for_status()
    return r.json()


def timeline_paciente(
    id_paciente: int, token: str, *, dias_futuro: int = 365, client: httpx.Client | None = None,
) -> list[dict]:
    c = _cliente(client)
    hoje = date.today()
    fim = hoje + timedelta(days=dias_futuro)
    r = c.get(
        f"{BASE_URL}/patients/{id_paciente}/timeline",
        params={"startDate": hoje.isoformat(), "endDate": fim.isoformat()},
        headers=_headers(token),
    )
    r.raise_for_status()
    return r.json().get("data") or []


def medicos_por_unidade(unidade: str, token: str, *, client: httpx.Client | None = None) -> list[dict]:
    c = _cliente(client)
    r = c.get(f"{BASE_URL}/schedule/doctors", params={"local": resolver_id_local(unidade)}, headers=_headers(token))
    r.raise_for_status()
    return extrair_lista_medicos(r.json())


def dia_disponivel(
    id_calendar: int, id_local: int, data_iso: str, token: str, *, client: httpx.Client | None = None,
) -> bool:
    c = _cliente(client)
    r = c.get(
        f"{BASE_URL}/schedule/{data_iso}",
        params={"idCalendar": id_calendar, "idLocal": id_local},
        headers=_headers(token),
    )
    r.raise_for_status()
    return bool(r.json().get("dayAvailable"))


def horarios_do_dia(
    id_calendar: int, id_local: int, data_iso: str, token: str, *, client: httpx.Client | None = None,
) -> list[str]:
    c = _cliente(client)
    r = c.get(
        f"{BASE_URL}/schedule/filter/calendar/hours",
        params={"idCalendar": id_calendar, "date": data_iso, "local": id_local},
        headers=_headers(token),
    )
    r.raise_for_status()
    body = r.json()
    bruto = body.get("schedules") if isinstance(body, dict) and body.get("schedules") is not None else (
        body.get("data") if isinstance(body, dict) else body
    )
    horarios = []
    for h in bruto or []:
        hora = (h.get("hour") or h.get("time")) if isinstance(h, dict) else h
        if hora and re.match(r"^\d{2}:\d{2}", hora):
            horarios.append(hora[:5])
    return sorted(horarios)


def criar_consulta(
    *, id_paciente: int, nome: str, cpf: str, nascimento: str, celular: str, email: str,
    convenio: str, unidade: str, id_calendar: int, id_local: int, data_iso: str, hora: str,
    token: str, client: httpx.Client | None = None,
) -> dict:
    c = _cliente(client)
    body = {
        "idPatient": id_paciente, "email": email or "", "typeQuery": "CONSULTA",
        "name": nome, "cpf": cpf, "dateOfBirth": nascimento, "cellphone": celular,
        "idHealthInsurance": resolver_id_health_insurance(convenio, unidade),
        "schedule": [{
            "id": "", "idScheduleReturn": None,
            "dateSchudule": "/".join(reversed(data_iso.split("-"))) if "-" in (data_iso or "") else data_iso,
            "local": id_local, "idCalendar": id_calendar, "procedures": [1],
            "hour": hora if hora.count(":") == 2 else f"{hora}:00",
        }],
    }
    r = c.post(f"{BASE_URL}/schedule/new", json=body, headers=_headers(token))
    r.raise_for_status()
    return r.json()


def _post_status(id_agendamento: int, status_code: int, body: dict, token: str, *, client: httpx.Client | None) -> dict:
    c = _cliente(client)
    r = c.post(
        f"{BASE_URL}/schedule/status/update/{id_agendamento}/{status_code}",
        json=body, headers=_headers(token),
    )
    r.raise_for_status()
    return r.json()


def cancelar_consulta(id_agendamento: int, token: str, *, client: httpx.Client | None = None) -> dict:
    body = {"reasonLack": "", "reasonUnchecked": "Paciente desmarcou", "sms": False, "email": False, "usePrePaidGuide": False}
    return _post_status(id_agendamento, STATUS_CANCELAR, body, token, client=client)


def confirmar_presenca(id_agendamento: int, token: str, *, client: httpx.Client | None = None) -> dict:
    body = {"reasonLack": "", "reasonUnchecked": "", "sms": False, "email": False}
    return _post_status(id_agendamento, STATUS_CONFIRMAR, body, token, client=client)
