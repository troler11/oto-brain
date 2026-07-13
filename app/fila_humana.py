"""
Port fiel dos nós de fila humana (achados na auditoria de inventário completo do grafo — 157
nós reais, não só os 39 `code` — 13/07/2026, ver `project_oto_migracao_python_fase1.md`):

  - `preparar_dados_fila()` — node "Preparar Dados para Fila" (roda SEMPRE, logo depois de
    "É Remarcação?"=false, antes do IF "Precisa Agente Completo?1"). Consolida fallback de
    campos de intenção pro node "Cria fila" usar quando o bypass humano evita
    "Extrair Intencao Final1" rodar neste turno.
  - `montar_params_cria_fila()` — port do `queryReplacement` do node "Cria fila" (dispara
    depois de "Resetar Sessao (Humano)", ou seja quando `intencao_rapida=='humano'` fecha o
    turno). INSERT em `agendamentos` com `status_atendimento='PENDENTE'`.
  - `montar_params_cria_fila_falha_confirmar()` — port do `queryReplacement` do node "Cria
    Fila (Falha Confirmar)" (dispara quando o IF real "Confirmou TiSaude?" avalia falso sobre o
    retorno de `app.confirmar_presenca_fluxo.confirmar_presenca_completo()` — mesmo shape:
    `status=='CONFIRMADO'` ou regex `/confirmad/i` em `resultado`).
  - `formatar_falha_confirmar()` — port do node "Formatar Falha Confirmar" (mensagem +
    bloco `$$$` mostrados ao paciente nesse mesmo caminho de falha).

Fidelidade do `queryReplacement` original: cada campo do "Cria fila" é
`try { $('Extrair Intencao Final1')... } catch(e) { fallback }` — o try/catch em n8n dispara
quando o node referenciado NÃO RODOU neste turno (bypass humano), não quando o valor é
falsy/vazio. Réplica: `extrair_intencao_final=None` == "node não rodou" (catch); um dict
(mesmo com campos vazios) == "node rodou" (try, usa o dict como está, só cai no fallback se o
CAMPO estiver vazio — replicado campo a campo, não uniformizado).

⚠️ **Sem wiring.** Mesma categoria de `app.confirmar_presenca_fluxo.confirmar_presenca_completo()`
e dos fluxos de criar/cancelar consulta: escreve em Postgres real (fila de atendimento humano
visível pra equipe), e `/route` documentadamente NÃO persiste nada enquanto for shadow (ver
docstring de `app/main.py`). `app.db.criar_fila()` (INSERT em si) fica pronto/testado, sem
ponto de chamada em `app/pipeline.py` — os triggers reais (`intencao_rapida=='humano'` fechando
turno, falha de confirmação TiSaude) dependem de trechos do fluxo que também não estão
100% wireados ainda (Agente Humano após rota=humano, mutação de confirmar_presenca).
"""

from __future__ import annotations

import re


def preparar_dados_fila(base: dict) -> dict:
    base = base or {}
    intencao_fila = base.get("intencao_rapida") or "conversa"
    dados_fila = {
        "especialidade": base.get("especialidade") or None,
        "unidade": base.get("unidade_cache") or None,
        "pagamento": base.get("pagamento") or None,
        "para_terceiro": bool(base.get("nome_dependente") and base.get("cpf_dependente")),
        "nome_paciente": base.get("nome") or base.get("nome_dependente") or None,
        "cpf_paciente": base.get("cpf") or base.get("cpf_dependente") or None,
        "nascimento": base.get("nascimento") or base.get("nascimento_dependente") or None,
        "medico": base.get("ultimo_medico") or None,
        "periodo": base.get("periodo") or None,
        "motivo_humano": base.get("motivo_humano") or None,
        "motivo": None,
    }
    return {**base, "intencao_fila": intencao_fila, "dados_fila": dados_fila}


def _telefone_digits(whatsapp_info: dict) -> str:
    """`SenderAlt?.split(':')[0] || from || ""` — fallback é `payload.from` (NÃO `Info.Chat`),
    diferente de `app.db.computar_params_salvar_sessao()` (que usa `Info.Chat`). Divergência
    real entre nós do n8n original, preservada — `whatsapp_info` aqui espera `SenderAlt`
    (de `Info`) e `from` (de `payload`, um nível acima), não o objeto `Info` puro."""
    info = whatsapp_info or {}
    sender_alt = info.get("SenderAlt") or ""
    raw = sender_alt.split(":")[0] if sender_alt else (info.get("from") or "")
    return re.sub(r"\D", "", raw.split("@")[0]) or "erro"


def _formatar_data_iso(raw: str | None) -> str:
    d = (raw or "").split("T")[0]
    if "/" in d:
        partes = d.split("/")
        if len(partes) == 3:
            d = f"{partes[2]}-{partes[1]}-{partes[0]}"
    return re.sub(r"[^0-9\-]", "", d)


def montar_params_cria_fila(
    base: dict,
    *,
    whatsapp_info: dict,
    extrair_intencao_final: dict | None = None,
    agente_humano_output: str | None = None,
) -> dict:
    preparado = preparar_dados_fila(base)
    df = preparado["dados_fila"]
    eif = extrair_intencao_final
    eif_dados = (eif or {}).get("dados") or {}

    # $2 intencao — try devolve o campo cru (sem || no ramo try); catch cai no fallback.
    intencao = eif.get("intencao") if eif is not None else (preparado["intencao_fila"] or "conversa")

    # $3/$4/$5/$10/$11 — mesmo padrão: try (campo ou None) || fallback do Preparar Dados || default.
    especialidade = (eif_dados.get("especialidade") if eif is not None else None) or df["especialidade"] or "Não informada"
    unidade = (eif_dados.get("unidade") if eif is not None else None) or df["unidade"] or "A confirmar"
    pagamento = (eif_dados.get("pagamento") if eif is not None else None) or df["pagamento"] or "A confirmar"
    medico = (eif_dados.get("medico") if eif is not None else None) or df["medico"] or "A confirmar"
    periodo = (eif_dados.get("periodo") if eif is not None else None) or df["periodo"] or "A confirmar"

    # $6 para_terceiro — try devolve bool direto (sem fallback do Preparar Dados no ramo try).
    para_terceiro = bool(eif.get("eh_terceiro")) if eif is not None else bool(df["para_terceiro"])

    # $7 nome_paciente — fallback só se o valor do EIF1 vier vazio/ausente, com split de \n.
    nome_paciente = (eif.get("nome_dependente") if eif is not None else None) or df["nome_paciente"] or "A confirmar"
    if nome_paciente and "\n" in nome_paciente:
        nome_paciente = nome_paciente.split("\n")[0].strip()

    # $8 cpf_paciente
    cpf_paciente = (eif.get("cpf_dependente") if eif is not None else None) or df["cpf_paciente"] or "A confirmar"

    # $9 nascimento — formata só depois de escolher a fonte (EIF1 ou Preparar Dados).
    nascimento_raw = (eif.get("nascimento_dependente") if eif is not None else None) or df["nascimento"]
    nascimento = _formatar_data_iso(nascimento_raw)

    # $12 motivo_humano/tipo_consulta — prioridade: bloco $$$ do Agente Humano > EIF1 > Preparar Dados > default.
    motivo_humano = None
    if agente_humano_output and "$$$" in agente_humano_output:
        m = re.search(r'"motivo"\s*:\s*"([^"]+)"', agente_humano_output)
        if m:
            motivo_humano = m.group(1)
    if not motivo_humano:
        motivo_humano = (eif.get("motivo_humano") if eif is not None else None) or df["motivo_humano"] or "Atendimento Humano"

    # $13 observacoes
    observacoes = ""
    if eif is not None:
        observacoes = eif.get("motivo_cancelamento") or eif_dados.get("motivo") or ""

    return {
        "telefone": _telefone_digits(whatsapp_info),
        "intencao": intencao,
        "especialidade": especialidade,
        "unidade": unidade,
        "pagamento": pagamento,
        "para_terceiro": para_terceiro,
        "nome_paciente": nome_paciente,
        "cpf_paciente": cpf_paciente,
        "nascimento": nascimento,
        "medico": medico,
        "periodo": periodo,
        "motivo_humano": motivo_humano,
        "observacoes": observacoes,
    }


def montar_params_cria_fila_falha_confirmar(
    montar_contexto_out: dict, extrair_rota: dict, *, whatsapp_info: dict
) -> dict:
    mc = montar_contexto_out or {}
    er = extrair_rota or {}
    return {
        "telefone": _telefone_digits(whatsapp_info),
        "intencao": "confirmar_presenca",
        "especialidade": "Otorrinolaringologia",
        "unidade": "A confirmar",
        "pagamento": "A confirmar",
        "para_terceiro": False,
        "nome_paciente": mc.get("nome_dependente") or mc.get("nome") or "A confirmar",
        "cpf_paciente": mc.get("cpf_dependente") or mc.get("cpf") or "",
        "nascimento": "",
        "medico": "A confirmar",
        "periodo": "A confirmar",
        "motivo_humano": "Falha ao confirmar presenca",
        "observacoes": (
            "Falha ao confirmar presenca via WhatsApp. Consulta id_itsaude: "
            f"{er.get('coleta_id_agendamento') or ''}. Atendente deve confirmar manualmente."
        ),
    }


def formatar_falha_confirmar(extrair_rota: dict) -> dict:
    id_agendamento = str((extrair_rota or {}).get("coleta_id_agendamento") or "").strip()
    texto = (
        "Não consegui confirmar sua presença automaticamente. 😕 Já avisei nossa equipe e um "
        "atendente vai entrar em contato com você em breve para confirmar. 🙏"
    )
    bloco = "$$$" + (
        '{"t": false, "i": "concluido", "d": "", "c": "", "n": "", "conv": "", '
        f'"id": "{id_agendamento}", "motivo": ""}}'
    )
    return {"mensagem_final": f"{texto}\n\n{bloco}"}
