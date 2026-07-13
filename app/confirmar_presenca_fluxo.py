"""
Orquestra o fluxo determinístico de confirmar presença (rota_agente==5, `base['_sub_confirmar']`
setado em app.er) chamando o client TiSaude (app.tisaude) pra buscar as consultas reais do
paciente, e delega a decisão pro port já existente (app.formatar_verificar_confirmar).

Lado LEITURA é port fiel do sub-workflow n8n 'Ferramenta - Verificar Consulta (Confirmar)' (id
`8kB4ORYvbetTlz9j`, achado numa auditoria completa 13/07/2026 — não estava mapeado quando este
módulo foi escrito originalmente; a versão anterior buscava por `id_tisaude` via
`timeline_paciente` direto — o node real busca por **CPF** via `buscar_paciente_por_cpf`, shape
de consulta próprio (`dataISO`/`dataBR`/`hora`/`medico`/`status_id`/`status_nome`, cap 8) que já
bate 1:1 com o que `app.formatar_verificar_confirmar` espera, sem precisar de adapter).

Lado MUTAÇÃO — port fiel completo (13/07/2026, tarde: `get_workflow_details` no sub-workflow
inteiro, 10 nós, draft==ativo sem divergência) do sub-workflow 'Ferramenta - Confirmar Presença'
(id `QKwWFLrBaBC5hew3`): `confirmar_presenca_completo()` abaixo. `POST
/schedule/status/update/{id}/3` (já era `tisaude.confirmar_presenca()`, reusado) + um UPDATE em
`agendamentos` (`status_atendimento = 'CONFIRMADO'`, `observacoes = 'Presença confirmada pelo
paciente via WhatsApp'`). Dois achados de fidelidade no node real: (1) o node `If1` (que decide
sucesso/erro na formatação final) reavalia `id_agendamento` do TRIGGER, não o resultado da
chamada TiSaude — como esse campo não muda entre o `If` inicial e o `If1`, a branch de erro
(`Formatar Erro Confirmação`) é código morto, nunca alcançado na prática (o node HTTP não tem
`onError`/`continueOnFail`, então uma falha real de API simplesmente para a execução inteira —
replicado aqui deixando `tisaude.confirmar_presenca()` propagar a exceção sem try/except). (2) o
UPDATE usa `$json.id_itsaude`, que vem da SELECT anterior (`Buscar agendamento`), não direto do
`id_agendamento` do trigger — se a linha não existir localmente no Postgres (`agendamentos`
dessincronizado da TiSaude), o UPDATE é um no-op silencioso (0 linhas), mas a função ainda
retorna sucesso (a TiSaude já confirmou, é isso que importa pro paciente). Replicado com o mesmo
comportamento (SELECT primeiro, UPDATE com o que achou ou `None`).

⚠️ ESCOPO (13/07/2026): `confirmar_presenca_completo()` MUTA de verdade (TiSaude real +
Postgres) — código pronto, mas NÃO ligado a nenhum dispatcher/agente/tool, mesma trava dos
outros 3 fluxos de mutação (`criar_consulta_fluxo`/`criar_consulta_terceiro_fluxo`/
`cancelar_consulta_fluxo`). Só entra em uso depois do cutover (Fase 2, `/route` ainda roda em
shadow). O caminho de LEITURA (`processar_rota5`/`buscar_consultas_paciente`, resto deste
módulo) continua ligado normalmente — decisão original (13/07/2026, manhã): `/route` roda em
shadow, então o caminho "auto_confirmar" de `processar_rota5` só decide e loga o que FARIA, sem
chamar `confirmar_presenca_completo()`.

IO real (login + busca + timeline) é envolvido em try/except: falha de rede/API na TiSaude
durante um turno de shadow não pode derrubar `/route` — cai pro mesmo fallback de antes da
integração (mensagem vazia, caminho legado n8n decide).
"""

from __future__ import annotations

import logging

import httpx

from app import formatar_verificar_confirmar as fvc
from app import tisaude

logger = logging.getLogger("oto-brain.confirmar_presenca")

_SUB_COM_TISAUDE = ("verificar", "executar")
_LIMITE_CONSULTAS = 8


def _formatar_consultas_confirmar(timeline_data: list[dict]) -> list[dict]:
    """Port fiel do node 'Formatar Consultas' (sub-workflow 'Ferramenta - Verificar Consulta
    (Confirmar)') — shape já bate 1:1 com o que `app.formatar_verificar_confirmar` espera
    (dataBR/hora/medico/status_id/status_nome/id), cap de 8 (não 5 — diferente de
    `app.cancelar_consulta_fluxo`/`app.tisaude.filtrar_consultas_ativas`, cada node com seu
    próprio limite no original, preservado aqui)."""
    consultas = []
    for dia in timeline_data:
        for evento in dia.get("data") or []:
            if evento.get("type") != "appointment":
                continue
            status = evento.get("status") or {}
            status_nome = status.get("name") or ""
            if "desmarcad" in status_nome.lower():
                continue
            data_iso = evento.get("date") or dia.get("date") or ""
            consultas.append({
                "id": evento.get("id"),
                "dataISO": data_iso,
                "dataBR": "/".join(reversed(data_iso.split("-"))) if data_iso else "",
                "hora": evento.get("hour") or "",
                "medico": (evento.get("calendar") or {}).get("name") or "Médico",
                "status_id": status.get("id") or 0,
                "status_nome": status_nome,
            })
            if len(consultas) >= _LIMITE_CONSULTAS:
                return consultas
    return consultas


def buscar_consultas_paciente(cpf: str, *, client: httpx.Client | None = None) -> list[dict]:
    """IO: loga na TiSaude, busca paciente por CPF, busca timeline, formata pro shape que
    app.formatar_verificar_confirmar espera. Sem paciente encontrado pro CPF -> lista vazia
    (o node original não trata esse caso à parte — `data[0].id` falharia; aqui é determinístico)."""
    token = tisaude.login(client=client)
    pacientes = tisaude.buscar_paciente_por_cpf(cpf, token, client=client)
    if not pacientes:
        return []
    timeline = tisaude.timeline_paciente(pacientes[0]["id"], token, client=client)
    return _formatar_consultas_confirmar(timeline)


def processar_rota5(base: dict, *, client: httpx.Client | None = None) -> dict | None:
    """Orquestra o turno rota_agente==5 conforme `base['_sub_confirmar']`:
      - "escolher_titular" -> lista titulares, sem chamada TiSaude
      - "verificar"/"executar" -> busca consultas reais e decide (pergunta/lista/auto) via
        app.formatar_verificar_confirmar.processar()
      - qualquer outro valor (recusou/despedida/None — inclui os rota=5 que na verdade são
        bypass pra humano, ex. encaixe/lista de espera) -> None, deixa pro caminho de sempre.

    Retorna dict no formato de app.formatar_verificar_confirmar.processar() (`output`/
    `auto_confirmar`/...), ou None se não há TiSaude envolvida ou a chamada falhou."""
    sub = base.get("_sub_confirmar")

    if sub == "escolher_titular":
        return fvc.formatar_escolher_titular(base, base.get("pacientes"))

    if sub in _SUB_COM_TISAUDE:
        cpf = base.get("cpf") or (base.get("pacientes") or [{}])[0].get("cpf")
        if not cpf:
            return None
        try:
            consultas = buscar_consultas_paciente(cpf, client=client)
        except Exception:
            logger.exception("rota5: falha ao buscar consultas na TiSaude (cpf=%s)", cpf)
            return None

        resultado = fvc.processar({"consultas": consultas}, base, base.get("_indice_consulta"))
        if resultado.get("auto_confirmar"):
            logger.info(
                "rota5: auto_confirmar decidido (id_agendamento=%s) — mutação real NÃO disparada "
                "(shadow, aguardando cutover Fase 2)", resultado.get("id_agendamento"),
            )
        return resultado

    return None


def confirmar_presenca_completo(
    id_agendamento: str | int | None, *, conn, tisaude_client: httpx.Client | None = None,
) -> dict:
    """Port fiel do sub-workflow 'Ferramenta - Confirmar Presença' (`QKwWFLrBaBC5hew3`) —
    MUTA de verdade: confirma presença na TiSaude (`STATUS_CONFIRMAR=3`) + UPDATE em
    `agendamentos`. NÃO ligado a nenhum dispatcher/agente/tool (ver docstring do módulo)."""
    id_str = str(id_agendamento or "").strip()
    if not id_str or id_str == "null":
        return {"status": "ERRO_INPUT", "resultado": "ID do agendamento não informado. Não é possível confirmar a presença."}

    token = tisaude.login(client=tisaude_client)
    tisaude.confirmar_presenca(int(id_str), token, client=tisaude_client)

    with conn.cursor() as cur:
        cur.execute("SELECT id_itsaude FROM agendamentos WHERE id_itsaude = %s", (id_str,))
        row = cur.fetchone()
        id_itsaude_local = row[0] if row else None
        cur.execute(
            "UPDATE agendamentos SET status_atendimento = 'CONFIRMADO', "
            "observacoes = 'Presença confirmada pelo paciente via WhatsApp' WHERE id_itsaude = %s",
            (id_itsaude_local,),
        )

    return {"status": "CONFIRMADO", "id_agendamento": id_str, "resultado": "Presença confirmada com sucesso!"}
