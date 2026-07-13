"""
Port fiel do nó 'Injetar Contexto Agendamento' — DEPLOY/_proposed_Injetar_Contexto_Agendamento.js
(315 linhas, snapshot 12/07/2026). Fase 1 do plano de migração (ver
C:\\Users\\lucas\\.claude\\plans\\unified-coalescing-puppy.md).

Roda depois da busca de agenda (`base.ultimo_dia_exibido` = dia+médicos+horários retornados
pela tool de busca), resolve qual médico/horário o paciente está confirmando/escolhendo, e
injeta blocos de texto determinísticos (âncora de memória + confirmação pendente / pedido de
email / criação direta) no `texto_ia` que o agente executor lê. Único nó desta leva que só
depende de UM input (`$input.first().json` = `base`) — sem outros `$('...')` no JS fonte.

Branches, em ordem (a primeira que casar decide o retorno — mesmos early-returns do JS):
  0. Sem `ultimo_dia_exibido.data` → `eh_confirmacao=False`, passa `base` adiante sem mexer.
  1. "sim" positivo + `eh_confirmacao=True` já pendente → resolve o slot salvo; se o paciente
     selecionado já tem email (ficha ou sessão), injeta bloco de chamar a tool DIRETO; senão
     pede email.
  2. Resposta ao pedido de email (endereço encontrado ou "não tenho"/"pular") → injeta bloco
     de chamar a tool DIRETO com o email recebido (ou vazio).
  3. Desambiguação por nome de médico (paciente respondeu só o nome, sem hora, havia horas
     ambíguas entre 2+ médicos naquele dia) → nova "CONFIRMAÇÃO PENDENTE" com o médico
     escolhido.
  4. Resolução principal médico×hora: por nome mencionado (+ hora mais próxima se a pedida não
     bate), por hora mencionada (0 médicos → não encontrado; 1 → usa; 2+ → pede desambiguação),
     ou fallback pro primeiro médico do dia.
"""

from __future__ import annotations

import re

from app.text_utils import _norm

_SIMS_POSITIVOS = ("s", "sim", "ok", "correto", "isso", "pode", "confirmo", "isso mesmo")
_EMAIL_PATTERNS = ("n tenho", "nao tenho", "não tenho", "pular", "sem email", "n tenho email", "nao tenho email")
_HORA_RX = re.compile(r"\b(\d{1,2})[h:](\d{2})\b|\b(\d{1,2})h\b|\bpode ser a?s?\s*(\d{1,2})[h:]?(\d{0,2})\b")
_EMAIL_RX = re.compile(r"[\w.+-]+@[\w.-]+\.[a-z]{2,}", re.IGNORECASE)


def _resolver_medico(medicos: list[dict], medico_salvo: str) -> dict | None:
    if not medicos:
        return None
    if not medico_salvo or medico_salvo.lower() in ("sem preferencia", "sem preferência"):
        return medicos[0]
    medico_salvo_norm = _norm(medico_salvo)
    return next(
        (m for m in medicos if (lambda n: n in medico_salvo_norm or medico_salvo_norm in ((n.split(" ") or [""])[-1] or ""))(_norm(m["medico"]))),
        medicos[0],
    )


def _achar_medico_mencionado(medicos: list[dict], msg: str) -> dict | None:
    for m in medicos:
        partes = _norm(m["medico"]).split(" ")
        if any(len(p) > 3 and p in msg for p in partes):
            return m
    return None


def _extrair_hora_mencionada(msg: str) -> str | None:
    m = _HORA_RX.search(msg)
    if not m:
        return None
    h = (m.group(1) or m.group(3) or m.group(4) or "").zfill(2)
    mi = (m.group(2) or m.group(5) or "00").zfill(2)
    return f"{h}:{mi}"


def processar(base: dict) -> dict:
    base = dict(base or {})
    udi = base.get("ultimo_dia_exibido")

    msg_original = (base.get("texto_ia") or "").split("\n")[0].strip()
    msg = _norm(msg_original)
    msg_sem_pontuacao = re.sub(r"[!.?]", "", msg).strip()

    if not udi or not udi.get("data"):
        return {**base, "eh_confirmacao": False}

    medico_salvo = (base.get("coleta_medico") or "").strip()

    def resolver_medico(medicos):
        return _resolver_medico(medicos, medico_salvo)

    # ── "sim" confirmando agendamento já pendente ──────────────────────
    eh_sim_positivo = any(msg_sem_pontuacao == s for s in _SIMS_POSITIVOS)

    # FIX_LOOP_CONFIRMACAO (13/07): `eh_confirmacao` vem do classificador LLM (Mini IA) e falha
    # com frequência em detectar "sim"/"correto" como resposta ao "[CONFIRMAÇÃO PENDENTE]" —
    # achado na revisão manual de casos_aprendizado (~9 telefones, loop volta a mostrar horários
    # em vez de agendar). Backstop determinístico: esta função só roda dentro de rota_agente==4
    # (agenda) já — combinado com a palavra exata de confirmação e um dia de agenda recém-
    # exibido (`udi`), é sinal suficiente sem depender do classificador acertar toda vez.
    eh_confirmacao_valida = bool(base.get("eh_confirmacao")) or bool(udi.get("data"))

    if eh_sim_positivo and eh_confirmacao_valida and udi.get("medicos"):
        primeiro_dr = resolver_medico(udi["medicos"])
        data_conf = udi["data"]
        hora_conf = base.get("coleta_horario") or primeiro_dr["horarios"].split(", ")[0]
        medico_conf = primeiro_dr["medico"]
        id_local_conf = primeiro_dr.get("idLocal", 1) if primeiro_dr.get("idLocal") is not None else 1
        id_cal_conf = primeiro_dr.get("idCalendar", 1) if primeiro_dr.get("idCalendar") is not None else 1
        data_exib_conf = "/".join(reversed(data_conf.split("-")))

        ancora_sim = (
            "[HISTÓRICO RECENTE — IGNORE TODAS AS DATAS ANTERIORES A ESTA]\n"
            f"A última data exibida ao paciente foi:\n📅 {data_exib_conf}\n"
            f"Dr(a). {medico_conf}: {hora_conf}\nO paciente CONFIRMOU o agendamento\n"
            "━━━ TODA DATA ANTERIOR A ESTA É OBSOLETA ━━━\n"
            f"USE SOMENTE: {data_conf} / {hora_conf} / {medico_conf}\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )

        # FIX_EMAIL_CADASTRO
        pacs_ic = base.get("pacientes") if isinstance(base.get("pacientes"), list) else []
        id_sel_ic = str(base.get("coleta_id_tisaude") or "")
        nome_sel_ic = _norm(base.get("nome_dependente") or "")
        pac_sel_ic = next((p for p in pacs_ic if str(p.get("id_tisaude")) == id_sel_ic), None) if id_sel_ic else None
        if not pac_sel_ic and nome_sel_ic:
            cands_ic = [p for p in pacs_ic if _norm(p.get("nome")) == nome_sel_ic or _norm(p.get("nome")).split(" ")[0] == nome_sel_ic]
            if len(cands_ic) == 1:
                pac_sel_ic = cands_ic[0]
        eh_terc_ic = base.get("coleta_terceiro") == "true" or base.get("coleta_terceiro") is True
        email_salvo_ic = base.get("coleta_email") if (base.get("coleta_email") and base.get("coleta_email") != "SKIP") else ""
        email_cad_ic = email_salvo_ic or (pac_sel_ic.get("email") if (not eh_terc_ic and pac_sel_ic and pac_sel_ic.get("email")) else "")

        if email_cad_ic:
            email_ctx_cad = "\n".join([
                "[EMAIL JA CADASTRADO]",
                f'email: "{email_cad_ic}" (da ficha do paciente — NAO pergunte email)',
                "Chame DIRETAMENTE criar_consulta (t=false) ou criar_consulta_terceiro (t=true) com:",
                f"  data: {data_conf}",
                f"  hora: {hora_conf}",
                f"  medico: {medico_conf}",
                f"  idLocal: {id_local_conf}",
                f"  idCalendar: {id_cal_conf}",
                f'  email: "{email_cad_ic}"',
                "⛔ NAO peca confirmacao novamente. NAO pergunte email. Chame a ferramenta agora.",
            ])
            return {
                **base,
                "texto_ia": f"{ancora_sim}\n\n{msg_original}\n\n{email_ctx_cad}",
                "ultimo_dia_texto": f"Data: {data_conf} | Dr(a). {medico_conf}: {hora_conf}",
                "data_agendamento": data_conf,
                "hora_agendamento": hora_conf,
                "medico_agendamento": medico_conf,
            }

        confirmacao_email = (
            "[CONFIRMAÇÃO PENDENTE]\nSUA ÚNICA RESPOSTA AGORA DEVE SER EXATAMENTE ESTA FRASE, SEM ALTERAÇÕES:\n"
            '"Qual seu email para confirmação? 😊"\nNÃO CHAME NENHUMA FERRAMENTA NESTA MENSAGEM.\n'
            "Após receber o email, chame a ferramenta apropriada (criar_consulta se t=false, "
            "criar_consulta_terceiro se t=true) com:\n"
            f"  data: {data_conf}\n  hora: {hora_conf}\n  medico: {medico_conf}\n"
            f"  idLocal: {id_local_conf}\n  idCalendar: {id_cal_conf}"
        )
        return {
            **base,
            "texto_ia": f"{ancora_sim}\n\n{msg_original}\n\n{confirmacao_email}",
            "ultimo_dia_texto": f"Data: {data_conf} | Dr(a). {medico_conf}: {hora_conf}",
            "data_agendamento": data_conf,
            "hora_agendamento": hora_conf,
            "medico_agendamento": medico_conf,
        }

    # ── resposta ao pedido de email ──────────────────────────────────────
    email_addr_ic = _EMAIL_RX.search(msg)
    eh_resposta_email = (
        not eh_sim_positivo
        and base.get("coleta_horario") and base.get("coleta_data") and udi and udi.get("data")
        and (any(p in msg_sem_pontuacao for p in _EMAIL_PATTERNS) or bool(email_addr_ic))
    )

    if eh_resposta_email:
        email_val = email_addr_ic.group(0) if email_addr_ic else ""
        hora_email = base.get("coleta_horario")
        data_email = udi["data"]
        dr_email = resolver_medico(udi.get("medicos") or [])
        medico_email = dr_email["medico"] if dr_email else "?"
        id_local_email = (dr_email.get("idLocal", 1) if dr_email.get("idLocal") is not None else 1) if dr_email else 1
        id_cal_email = (dr_email.get("idCalendar", 1) if dr_email.get("idCalendar") is not None else 1) if dr_email else 1

        email_ctx = "\n".join([
            "[EMAIL RECEBIDO]",
            f'email: "{email_val}" (string vazia = sem email)',
            "Chame DIRETAMENTE criar_consulta (t=false) ou criar_consulta_terceiro (t=true) com:",
            f"  data: {data_email}",
            f"  hora: {hora_email}",
            f"  medico: {medico_email}",
            f"  idLocal: {id_local_email}",
            f"  idCalendar: {id_cal_email}",
            f'  email: "{email_val}"',
            "⛔ NAO peca confirmacao novamente. NAO pergunte nome. Chame a ferramenta agora.",
        ])
        return {
            **base,
            "texto_ia": f"{email_ctx}\n\n{msg_original}",
            "ultimo_dia_texto": f"Data: {data_email} | Dr(a). {medico_email}: {hora_email}",
            "data_agendamento": data_email,
            "hora_agendamento": hora_email,
            "medico_agendamento": medico_email,
        }

    # ── hora mencionada / horas ambíguas / médico mencionado ────────────
    hora_mencao = _extrair_hora_mencionada(msg)

    candidatos_ambiguos: dict[str, list[dict]] = {}
    for m in udi.get("medicos") or []:
        for h in [h.strip() for h in (m.get("horarios") or "").split(",") if h.strip()]:
            candidatos_ambiguos.setdefault(h, []).append(m)
    horas_ambiguas_entries = [(h, drs) for h, drs in candidatos_ambiguos.items() if len(drs) > 1]

    medico_mencionado = _achar_medico_mencionado(udi.get("medicos") or [], msg)

    era_desambiguacao = not hora_mencao and medico_mencionado is not None and len(horas_ambiguas_entries) > 0

    if era_desambiguacao:
        medico_respondido = _achar_medico_mencionado(udi.get("medicos") or [], msg)
        if medico_respondido:
            hora_anterior_match = re.search(r"(\d{2}:\d{2})", base.get("ultimo_dia_texto") or "")
            hora_recuperada = hora_anterior_match.group(1) if hora_anterior_match else medico_respondido["horarios"].split(", ")[0]

            data_final = udi["data"]
            data_exibicao = "/".join(reversed(data_final.split("-")))
            medico_final = medico_respondido["medico"]
            hora_final = hora_recuperada
            id_local = medico_respondido.get("idLocal", 1) if medico_respondido.get("idLocal") is not None else 1
            id_calendar = medico_respondido.get("idCalendar", 1) if medico_respondido.get("idCalendar") is not None else 1
            dependente_msg = base.get("nome_dependente") or "você"

            confirmacao_texto = (
                "[CONFIRMAÇÃO PENDENTE]\nSUA ÚNICA RESPOSTA AGORA DEVE SER EXATAMENTE ESTA FRASE, SEM ALTERAÇÕES:\n"
                f'"Só para confirmar: {data_exibicao} às {hora_final} com Dr(a). {medico_final} para {dependente_msg}. Está correto?"\n'
                "NÃO CHAME NENHUMA FERRAMENTA NESTA MENSAGEM.\nNÃO INVENTE DATAS. NÃO CALCULE DATAS.\n"
                'Somente após o paciente responder "sim" / "confirmo" / "correto" / "pode", chame a ferramenta '
                "apropriada com:\n"
                f"  data: {data_final}\n  hora: {hora_final}\n  medico: {medico_final}\n"
                f"  idLocal: {id_local}\n  idCalendar: {id_calendar}"
            )
            ancora_mensagem = (
                "[HISTÓRICO RECENTE — IGNORE TODAS AS DATAS ANTERIORES A ESTA]\n"
                f"A última data exibida ao paciente foi:\n📅 {data_exibicao}\nDr(a). {medico_final}: {hora_final}\n"
                f'O paciente respondeu: "{msg_original}"\n'
                "━━━ TODA DATA ANTERIOR A ESTA É OBSOLETA ━━━\n"
                f"USE SOMENTE: {data_final} / {hora_final} / {medico_final}\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            )
            return {
                **base,
                "texto_ia": f"{ancora_mensagem}\n\n{msg_original}\n\n{confirmacao_texto}",
                "ultimo_dia_texto": f"Data: {data_final} | Dr(a). {medico_final}: {hora_final}",
                "data_agendamento": data_final,
                "hora_agendamento": hora_final,
                "medico_agendamento": medico_final,
            }

    # ── resolução principal médico × hora ────────────────────────────────
    medico_escolhido = None
    hora_escolhida = hora_mencao

    medicos = udi.get("medicos") or []
    if medicos:
        # 1. tenta achar médico pelo nome mencionado
        medico_escolhido = _achar_medico_mencionado(medicos, msg)

        if medico_escolhido and hora_mencao:
            horarios_disponiveis = [h.strip() for h in (medico_escolhido.get("horarios") or "").split(",")]
            if hora_mencao in horarios_disponiveis:
                hora_escolhida = hora_mencao
            else:
                def _diff(h):
                    try:
                        return abs(int(h.split(":")[0]) - int(hora_mencao.split(":")[0]))
                    except ValueError:
                        return 10**9
                ordenado = sorted(horarios_disponiveis, key=_diff)
                hora_escolhida = ordenado[0] if ordenado else hora_mencao

        # 2. se não achou pelo nome, verifica candidatos pelo horário
        if not medico_escolhido and hora_mencao:
            candidatos = [m for m in medicos if hora_mencao in [h.strip() for h in (m.get("horarios") or "").split(",")]]

            if not candidatos:
                lista_horarios = "\n".join(f"🩺 Dr(a). {m['medico']}: {m['horarios']}" for m in medicos)
                return {
                    **base,
                    "eh_confirmacao": False,
                    "texto_ia": f"Não encontrei o horário {hora_mencao} disponível. Os horários disponíveis são:\n{lista_horarios}\nQual prefere?",
                    "data_agendamento": None,
                    "hora_agendamento": None,
                    "medico_agendamento": None,
                }

            if len(candidatos) > 1:
                opcoes = "\n".join(f"🩺 Dr(a). {m['medico']}" for m in candidatos)
                data_exibicao_desambig = "/".join(reversed(udi["data"].split("-")))
                return {
                    **base,
                    "eh_confirmacao": False,
                    "texto_ia": f"O horário {hora_mencao} do dia {data_exibicao_desambig} está disponível com mais de um médico:\n{opcoes}\nCom qual prefere?",
                    "data_agendamento": None,
                    "hora_agendamento": None,
                    "medico_agendamento": None,
                }

            medico_escolhido = candidatos[0]
            hora_escolhida = hora_mencao

        # 3. último fallback: primeiro médico da lista
        if not medico_escolhido:
            medico_escolhido = medicos[0]
            hora_escolhida = hora_mencao or (medico_escolhido.get("horarios") or "").split(", ")[0]

    data_final = udi["data"]
    medico_final = (medico_escolhido or {}).get("medico") or "?"
    hora_final = hora_escolhida or (medico_escolhido or {}).get("horarios", "").split(", ")[0] or "?"
    id_local = ((medico_escolhido or {}).get("idLocal", 1) if (medico_escolhido or {}).get("idLocal") is not None else 1)
    id_calendar = ((medico_escolhido or {}).get("idCalendar", 1) if (medico_escolhido or {}).get("idCalendar") is not None else 1)

    data_exibicao = "/".join(reversed(data_final.split("-")))
    ultimo_dia_texto_corrigido = f"Data: {data_final} | Dr(a). {medico_final}: {hora_final}"
    dependente_msg = base.get("nome_dependente") or "você"

    confirmacao_texto = (
        "[CONFIRMAÇÃO PENDENTE]\nSUA ÚNICA RESPOSTA AGORA DEVE SER EXATAMENTE ESTA FRASE, SEM ALTERAÇÕES:\n"
        f'"Só para confirmar: {data_exibicao} às {hora_final} com Dr(a). {medico_final} para {dependente_msg}. Está correto?"\n'
        "NÃO CHAME NENHUMA FERRAMENTA NESTA MENSAGEM.\nNÃO INVENTE DATAS. NÃO CALCULE DATAS.\n"
        'Somente após o paciente responder "sim" / "confirmo" / "correto" / "pode", chame a ferramenta '
        "apropriada (criar_consulta se for para o titular OU criar_consulta_terceiro se for para dependente) com:\n"
        f"  data: {data_final}\n  hora: {hora_final}\n  medico: {medico_final}\n"
        f"  idLocal: {id_local}\n  idCalendar: {id_calendar}"
    )
    ancora_mensagem = (
        "[HISTÓRICO RECENTE — IGNORE TODAS AS DATAS ANTERIORES A ESTA]\n"
        f"A última data exibida ao paciente foi:\n📅 {data_exibicao}\nDr(a). {medico_final}: {hora_final}\n"
        f'O paciente respondeu: "{msg_original}"\n'
        "━━━ TODA DATA ANTERIOR A ESTA É OBSOLETA ━━━\n"
        f"USE SOMENTE: {data_final} / {hora_final} / {medico_final}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )

    return {
        **base,
        "texto_ia": f"{ancora_mensagem}\n\n{msg_original}\n\n{confirmacao_texto}",
        "ultimo_dia_texto": ultimo_dia_texto_corrigido,
        "data_agendamento": data_final,
        "hora_agendamento": hora_final,
        "medico_agendamento": medico_final,
    }
