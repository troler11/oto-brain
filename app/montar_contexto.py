"""
Port fiel do nó 'Montar Contexto' — DEPLOY/_proposed_Montar_Contexto.js (362 linhas, snapshot
12/07/2026). Fase 1 do plano de migração (ver
C:\\Users\\lucas\\.claude\\plans\\unified-coalescing-puppy.md).

Monta o `base` que alimenta o Extrair Rota a partir de 5 fontes upstream do n8n:
  - `BUSCAR PACIENTE ID1` / `Buscar Paciente por Telefone` — ficha(s) do(s) paciente(s)
    (fonte preferencial = ID1, traz email; fallback = busca por telefone)
  - `Extrair Medico Timeline1` — último médico/data/convênio por paciente
  - `Carregar Sessao` — linha de sessão persistida no Postgres (`contatos_whatsapp`)
  - `Recebe WhatsApp1` — payload cru do WhatsApp (telefone)
  - `6. Agrupar Textos1` — texto da mensagem já agrupada/deduplicada

Cada um vira um parâmetro explícito de `processar()` — não há leitura de rede/DB aqui, só
transformação pura, igual ao node original.

Exceção declarada (não port fiel): `memoria_paciente` (Fase 4, `app.db.carregar_memoria_paciente`)
é injetado só pra personalizar a saudação de paciente não encontrado no TiSaude ainda —
ver comentário FASE4_MEMORIA_SAUDACAO no bloco `num_pacs == 0`. Aprovado com Lucas em 12/07/2026
(versão conservadora: reconhece "de volta" sem citar médico/unidade — telefone pode ser
compartilhado entre dependentes).

Diferença deliberada (NÃO unificada) com `app.er`: o `telefone` calculado aqui tira o prefixo
"55" (`.replace(/^55/, '')`), enquanto o `telefone` recomputado dentro do próprio Extrair Rota
(`app.er.processar_intake`), a partir do MESMO `whatsapp_info`, mantém o "55". São usos
diferentes (chave de exibição/DB vs. valor pronto pra API do WhatsApp) — fiel ao JS, não bug.

Reaproveita de `app.er` (byte-idênticos, confirmados por comparação com o JS fonte):
  - `_hoje_sp()` / `_proxima_data_dow()` — mesma fórmula de "hoje"/"próximo dia da semana" que
    `_spNow = DateTime.now().setZone('America/Sao_Paulo')` + `(alvo - weekday + 7) % 7 || 7`.
  - `_GRADE_TEXTO_COM_NOME` — mesmo texto "Dr(a). X atende ..." usado no `resp_sim_med`
    (aqui só ganha o sufixo ", qual prefere? 😊" que o JS local `_schedVO`/`_schedTA` acrescenta).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.er import _GRADE_TEXTO_COM_NOME, _hoje_sp, _proxima_data_dow
from app.text_utils import _norm

CARENCIA_DIAS = {"porto seguro": 20, "bradesco": 30, "omint": 30}

_KEYWORDS_MED = (
    "sim", "ok", "pode", "correto", "isso", "confirmo", "nao", "não",
    "outro", "qualquer", "qualquer um", "tanto faz", "esse", "esse mesmo", "isso mesmo", "nao sei", "não sei",
    "para mim", "pra mim", "eu", "para ele", "pra ele", "para ela", "pra ela",
    "outra pessoa", "para outra pessoa", "pra outra pessoa", "terceiro", "dependente",
    "segunda", "segunda-feira", "seg",
    "terca", "terca-feira", "ter",
    "quarta", "quarta-feira", "qua",
    "quinta", "quinta-feira", "qui",
    "sexta", "sexta-feira", "sex",
)

_PARECE_MEDICO_RX = re.compile(
    r"giseli|rebechi|elias|lobo|braga|\bjose\b|emmanuel|burle|\bcaio\b|saettini|fernanda|butura|"
    r"broetto|stephanie|sthep|stefan|sthef|rugeri|juliana|amaral|torcuato|sanchez|rojas|"
    r"^dr\.?a?\s+\S|^doutora?\s+\S"
)

_LISTA_MED = {
    "Tatuapé": (
        "Médicos disponíveis em Tatuapé:\n"
        "👨‍⚕️ Dr. Elias Lobo Braga — segunda, sexta (só manhã)\n"
        "👨‍⚕️ Dr. Jose Emmanuel Burle Neto — terça\n"
        "👨‍⚕️ Dr. Caio Vinicius Saettini — quarta\n"
        "👩‍⚕️ Dra. Giseli Rebechi — quinta\n"
        "👩‍⚕️ Dra. Fernanda Butura Broetto — sexta (só tarde)\n"
        "Qual prefere? 😊"
    ),
    "Vila Olímpia": (
        "Médicos disponíveis em Vila Olímpia:\n"
        "👩‍⚕️ Dra. Giseli Rebechi — terça, quarta (só manhã), sexta (só manhã)\n"
        "👨‍⚕️ Dr. Elias Lobo Braga — terça (só tarde), quarta\n"
        "👨‍⚕️ Dr. Jose Emmanuel Burle Neto — segunda, quarta (só manhã), quinta\n"
        "👩‍⚕️ Dra. Stephanie Rugeri de Souza — segunda (manhã: teleconsulta), terça (só manhã — teleconsulta), quarta (só tarde)\n"
        "👩‍⚕️ Dra. Juliana Paulino do Amaral — segunda (só tarde), sexta (só tarde)\n"
        "👨‍⚕️ Dr. Torcuato Sanchez Rojas Neto — quarta (só tarde), quinta, sexta\n"
        "👩‍⚕️ Dra. Fernanda Butura Broetto — quinta (só tarde)\n"
        "👨‍⚕️ Dr. Caio Vinicius Saettini — terça (só manhã)\n"
        "Qual prefere? 😊"
    ),
}

_GRADE_MED = {
    "Tatuapé": (
        '- Elias → "Dr. Elias Lobo Braga atende segunda, sexta (só manhã), qual prefere? 😊"\n'
        '- Jose → "Dr. Jose Emmanuel Burle Neto atende terça, qual prefere? 😊"\n'
        '- Caio → "Dr. Caio Vinicius Saettini atende quarta, qual prefere? 😊"\n'
        '- Giseli → "Dra. Giseli Rebechi atende quinta, qual prefere? 😊"\n'
        '- Fernanda → "Dra. Fernanda Butura Broetto atende sexta (só tarde), qual prefere? 😊"'
    ),
    "Vila Olímpia": (
        '- Giseli → "Dra. Giseli Rebechi atende terça, quarta (só manhã), sexta (só manhã), qual prefere? 😊"\n'
        '- Elias → "Dr. Elias Lobo Braga atende terça (só tarde), quarta, qual prefere? 😊"\n'
        '- Jose → "Dr. Jose Emmanuel Burle Neto atende segunda, quarta (só manhã), quinta, qual prefere? 😊"\n'
        '- Stephanie → "Dra. Stephanie Rugeri de Souza atende segunda (manhã: teleconsulta), terça (só manhã — teleconsulta), quarta (só tarde), qual prefere? 😊"\n'
        '- Juliana → "Dra. Juliana Paulino do Amaral atende segunda (só tarde), sexta (só tarde), qual prefere? 😊"\n'
        '- Torcuato → "Dr. Torcuato Sanchez Rojas Neto atende quarta (só tarde), quinta, sexta, qual prefere? 😊"\n'
        '- Fernanda → "Dra. Fernanda Butura Broetto atende quinta (só tarde), qual prefere? 😊"\n'
        '- Caio → "Dr. Caio Vinicius Saettini atende terça (só manhã), qual prefere? 😊"'
    ),
}

_DIA_LOOKUP = {
    "Tatuapé": "Elias: seg→Ambos | sex→manha\\nJose: ter→Ambos\\nCaio: qua→Ambos\\nGiseli: qui→Ambos\\nFernanda: sex→tarde",
    "Vila Olímpia": (
        "Giseli: ter→Ambos | qua→manha | sex→manha\\nElias: ter→tarde | qua→Ambos\\n"
        "Jose: seg→Ambos | qua→manha | qui→Ambos\\nStephanie: seg→Ambos | ter→manha | qua→tarde\\n"
        "Juliana: seg→tarde | sex→tarde\\nTorcuato: qua→tarde | qui→Ambos | sex→Ambos\\n"
        "Fernanda: qui→tarde\\nCaio: ter→manha"
    ),
}


def _formatar_paciente(p: dict, pacientes_com_medico: list[dict]) -> dict:
    nome = p.get("name") or p.get("nome")
    id_ = p.get("id") or p.get("id_tisaude")

    def _match(pm: dict) -> bool:
        match_id = pm.get("id_tisaude") is not None and id_ is not None and str(pm["id_tisaude"]) == str(id_)
        match_nome = bool(pm.get("nome")) and bool(nome) and str(pm["nome"]).strip().upper() == str(nome).strip().upper()
        return match_id or match_nome

    com_medico = next((pm for pm in pacientes_com_medico if _match(pm)), None)
    medico_raw = (com_medico or {}).get("ultimo_medico") or ""
    data_raw = (com_medico or {}).get("data_ultima_consulta") or ""
    convenio_raw = (com_medico or {}).get("ultimo_convenio") or ""

    return {
        "nome": nome,
        "cpf": p.get("cpf") or None,
        "nascimento": p.get("dateOfBirth") or p.get("nascimento") or None,
        "email": p.get("email") if (p.get("email") and not p.get("blacklistEmail")) else None,
        "id_tisaude": id_,
        "ultimo_medico": medico_raw if (medico_raw and medico_raw != "NENHUM") else "",
        "data_ultima_consulta": data_raw if (data_raw and data_raw != "NENHUM") else "",
        "ultimo_convenio": convenio_raw if (convenio_raw and convenio_raw != "NENHUM") else "",
    }


def _calcular_carencia(ultimo_convenio_geral: str, data_ultima_consulta_geral: str):
    """FIX_CARENCIA_DETERMINISTICA. Nota de fidelidade: o JS compara contra `new Date()` cru
    (relógio do servidor, SEM o ajuste -3h de `_spNow`/`_hoje_sp` usado no resto do arquivo) —
    quirk preservado aqui com `datetime.now(timezone.utc)`, não `_hoje_sp()`."""
    conv_car = _norm(ultimo_convenio_geral)
    key_car = next((k for k in CARENCIA_DIAS if k in conv_car), None)
    if not key_car or not data_ultima_consulta_geral:
        return "", ""
    from datetime import date, datetime, timedelta, timezone
    d_uc = None
    m_br = re.match(r"^(\d{2})/(\d{2})/(\d{4})", str(data_ultima_consulta_geral))
    m_iso = re.match(r"^(\d{4})-(\d{2})-(\d{2})", str(data_ultima_consulta_geral))
    if m_br:
        d_uc = date(int(m_br.group(3)), int(m_br.group(2)), int(m_br.group(1)))
    elif m_iso:
        d_uc = date(int(m_iso.group(1)), int(m_iso.group(2)), int(m_iso.group(3)))
    if not d_uc:
        return "", ""
    d_uc = d_uc + timedelta(days=CARENCIA_DIAS[key_car])
    agora_cru = datetime.now(timezone.utc).date()
    if d_uc <= agora_cru:
        return "", ""
    return d_uc.strftime("%Y-%m-%d"), d_uc.strftime("%d/%m/%Y")


@dataclass
class ResultadoMontarContexto:
    paciente_encontrado: bool
    pacientes: list = field(default_factory=list)
    nome: str | None = None
    cpf: str | None = None
    nascimento: str | None = None
    id_tisaude: str | None = None
    ultimo_medico: str = ""
    data_ultima_consulta: str = ""
    ultimo_convenio: str = ""
    data_minima_carencia: str = ""
    data_minima_carencia_br: str = ""
    sessao_intencao: str = "triagem"
    sessao_rota: int = 0
    cache_ativo: bool = False
    unidade_cache: str = ""
    ultimo_dia_exibido: dict | None = None
    ultimo_dia_texto: str = "NENHUM"
    nome_dependente: str = ""
    cpf_dependente: str = ""
    nascimento_dependente: str = ""
    texto_ia: str = ""
    telefone: str = ""
    coleta_unidade: str = ""
    coleta_data: str = ""
    coleta_periodo: str = ""
    coleta_convenio: str = ""
    coleta_horario: str = ""
    coleta_terceiro: str = ""
    coleta_medico: str = ""
    coleta_modo: int = 0
    coleta_dia_semana: str = ""
    coleta_id_tisaude: str = ""
    coleta_id_agendamento: str = ""
    medico_candidato_msg: str = ""
    coleta_email: str = ""
    lista_med: str = ""
    p1_section: str = ""
    saudacao_section: str = ""
    p3_menu: str = ""
    grade_med: str = ""
    dia_lookup: str = ""
    hoje: str = ""
    amanha: str = ""
    prox_seg: str = ""
    prox_ter: str = ""
    prox_qua: str = ""
    prox_qui: str = ""
    prox_sex: str = ""
    status_leitura_timelines: str = ""
    resp_sim_med: str = ""

    def to_dict(self) -> dict:
        return dict(self.__dict__)


def processar(
    busca_paciente_id1: list[dict] | None,
    busca_paciente_telefone: dict | None,
    extrair_medico_timeline: list[dict] | None,
    sessao: dict | None,
    whatsapp_info: dict | None,
    mensagem_agrupada: str,
    memoria_paciente: dict | None = None,
) -> ResultadoMontarContexto:
    # ── Dados do paciente (FIX_FICHA_COMPLETA) ──────────────────────────
    pacientes = [p for p in (busca_paciente_id1 or []) if p and p.get("id")]
    if not pacientes:
        resposta_paciente = busca_paciente_telefone or {}
        if isinstance(resposta_paciente.get("data"), list):
            pacientes = resposta_paciente["data"]
        elif resposta_paciente.get("id"):
            pacientes = [resposta_paciente]

    # ── Pacientes com ultimo_medico (Extrair Medico Timeline1) ─────────
    pacientes_com_medico: list[dict] = []
    if not extrair_medico_timeline:
        status_leitura_timelines = "FALHA: Não encontrou dados na entrada do nó."
    else:
        for item in extrair_medico_timeline:
            if isinstance((item or {}).get("pacientes"), list):
                pacientes_com_medico.extend(item["pacientes"])
        if not pacientes_com_medico:
            status_leitura_timelines = "AVISO: Leu a entrada, mas a lista de 'pacientes' estava vazia."
        else:
            status_leitura_timelines = f"SUCESSO: {len(pacientes_com_medico)} pacientes carregados."

    # ── Sessão salva ──────────────────────────────────────────────────
    sessao = sessao or {}
    sessao_intencao = (sessao.get("sessao_intencao") or "triagem").lower()
    sessao_rota = int(sessao.get("sessao_rota") or 0)

    # ── Cache de agenda ──────────────────────────────────────────────
    cache_ativo = False
    unidade_cache = sessao.get("unidade_cache") or ""
    ultimo_dia_exibido = None
    if sessao.get("agenda_json"):
        cache_ativo = True
        import json as _json
        try:
            aj = _json.loads(sessao["agenda_json"]) if isinstance(sessao["agenda_json"], str) else sessao["agenda_json"]
            unidade_cache = aj.get("unidade") or unidade_cache
        except (ValueError, TypeError, AttributeError):
            pass

    if sessao.get("ultimo_dia_exibido") is not None:
        raw_udi = sessao["ultimo_dia_exibido"]
        import json as _json
        try:
            if isinstance(raw_udi, str) and raw_udi.strip().startswith("{"):
                ultimo_dia_exibido = _json.loads(raw_udi)
            elif isinstance(raw_udi, dict):
                ultimo_dia_exibido = raw_udi
        except (ValueError, TypeError):
            pass

    ultimo_dia_texto = "NENHUM"
    if ultimo_dia_exibido and ultimo_dia_exibido.get("data"):
        medicos = " | ".join(
            f"Dr(a). {m.get('medico')}: {m.get('horarios')}" for m in (ultimo_dia_exibido.get("medicos") or [])
        )
        ano, mes, dia = ultimo_dia_exibido["data"].split("-")
        ultimo_dia_texto = f"Data: {dia}/{mes}/{ano} | {medicos}"

    # ── Telefone (SEM prefixo 55 — ver docstring do módulo) ────────────
    info = whatsapp_info or {}
    sender_alt = info.get("SenderAlt") or ""
    raw_id = sender_alt if "@s.whatsapp.net" in sender_alt else info.get("Chat")
    telefone = re.sub(r"^55", "", ((raw_id or "").split("@")[0].split(":")[0]))

    # ── Mensagem do usuário ────────────────────────────────────────────
    texto_ia = mensagem_agrupada or ""

    # ── Monta lista de pacientes mesclando com ultimo_medico ──────────
    pacientes_formatados = [
        _formatar_paciente(p, pacientes_com_medico) for p in pacientes if p.get("name") or p.get("nome")
    ]

    nome_junto = "\n".join(p["nome"] for p in pacientes_formatados)
    paciente_base = pacientes_formatados[0] if pacientes_formatados else {}

    ultimo_medico_geral = next((p["ultimo_medico"] for p in pacientes_formatados if (p["ultimo_medico"] or "").strip()), "")
    data_ultima_consulta_geral = next(
        (p["data_ultima_consulta"] for p in pacientes_formatados if (p["data_ultima_consulta"] or "").strip()), ""
    )
    ultimo_convenio_geral = next((p["ultimo_convenio"] for p in pacientes_formatados if (p["ultimo_convenio"] or "").strip()), "")

    hoje_sp = _hoje_sp()
    data_minima_carencia, data_minima_carencia_br = _calcular_carencia(ultimo_convenio_geral, data_ultima_consulta_geral)

    # ── Pré-computa candidato de médico da mensagem atual ──────────────
    msg_norm_med = _norm((texto_ia or "").strip().split("\n")[0].strip())
    is_keyword_med = any(msg_norm_med == k or msg_norm_med == f"{k}." for k in _KEYWORDS_MED)
    has_digits_med = bool(re.search(r"\d{5,}", msg_norm_med))
    is_date_med = bool(re.search(r"\d{1,2}/\d{1,2}", msg_norm_med))
    is_patient_name = any(
        any(len(w) > 3 and w in msg_norm_med for w in _norm(p.get("nome") or "").split(" "))
        for p in pacientes_formatados
    )
    parece_medico = bool(_PARECE_MEDICO_RX.search(msg_norm_med))
    medico_candidato_msg = (
        (texto_ia.strip().split("\n")[0].strip())
        if (
            sessao_intencao == "coleta"
            and not (sessao.get("coleta_medico") or "")
            and not (len(pacientes_formatados) >= 2 and not (sessao.get("coleta_unidade") or ""))
            and not is_keyword_med and not has_digits_med and not is_date_med and not is_patient_name
            and parece_medico
            and len(msg_norm_med) >= 3
        )
        else ""
    )

    # ── RESP_SIM_MED_COMPUTE ────────────────────────────────────────────
    resp_sim_med = ""
    unid_sim = sessao.get("coleta_unidade") or ""
    if unid_sim and pacientes_formatados:
        uk = "Vila Olímpia" if unid_sim == "Vila Olímpia" else "Tatuapé"
        scheds = _GRADE_TEXTO_COM_NOME.get(uk, {})
        linhas = []
        for p in pacientes_formatados:
            m = _norm(p.get("ultimo_medico") or "")
            if not m:
                linhas.append(f"{p['nome']}=PADRAO")
                continue
            k = next((k for k in scheds if k in m), None)
            linhas.append(f"{p['nome']}=" + (f"{scheds[k]}, qual prefere? 😊" if k else "PADRAO"))
        resp_sim_med = "\n".join(linhas)

    # ── FASE2_PRECOMPUTE_DATES ──────────────────────────────────────────
    hoje = hoje_sp.strftime("%Y-%m-%d")
    from datetime import timedelta
    amanha = (hoje_sp + timedelta(days=1)).strftime("%Y-%m-%d")
    prox_seg = _proxima_data_dow(1)
    prox_ter = _proxima_data_dow(2)
    prox_qua = _proxima_data_dow(3)
    prox_qui = _proxima_data_dow(4)
    prox_sex = _proxima_data_dow(5)

    # ── FASE3_LISTA_MED / GRADE_DIA / DIA_LOOKUP ───────────────────────
    unid_lc = (sessao.get("coleta_unidade") or "").lower()
    is_ta_lc = "tatu" in unid_lc
    uk_fase3 = "Tatuapé" if is_ta_lc else "Vila Olímpia"
    lista_med = _LISTA_MED[uk_fase3]
    grade_med = _GRADE_MED[uk_fase3]
    dia_lookup = _DIA_LOOKUP[uk_fase3]

    # ── FASE4_P1_PRECOMPUTE ─────────────────────────────────────────────
    num_pacs = len(pacientes_formatados)
    pac0 = pacientes_formatados[0] if pacientes_formatados else {}
    if num_pacs == 0:
        pergunta_p1 = "A consulta será para você ou para outra pessoa? 😊"
    elif num_pacs == 1:
        pergunta_p1 = f"A consulta será para {pac0.get('nome') or 'você'} ou para outra pessoa? 😊"
    else:
        pergunta_p1 = "A consulta será para " + ", ".join(p["nome"] for p in pacientes_formatados) + "? Ou para outra pessoa? 😊"
    disamb_p1 = ("Para qual? " + " ou ".join(p["nome"] for p in pacientes_formatados) + "? 😊") if num_pacs >= 2 else ""
    lookup_p1 = "\n".join(
        f"{p['nome']} → CPF: {p.get('cpf') or ''} | NASC: {p.get('nascimento') or ''} | ID: {p.get('id_tisaude') or ''}"
        for p in pacientes_formatados
    )

    nasc_p1 = (pac0.get("nascimento") or "").strip() if num_pacs >= 1 else ""
    regra_nasc_p1 = (
        "(⛔ NUNCA repita PERGUNTA. ⛔ PROIBIDO pedir CPF/nasc)."
        if nasc_p1
        else '⚠️ NASC VAZIO no cadastro: pergunte "Qual sua data de nascimento? (dia/mês/ano) 😊" ANTES de ir a P2 — sem ela o agendamento falha. (⛔ NUNCA peça CPF).'
    )

    if num_pacs == 0:
        p1_section = (
            "P1. QUEM? (Máx 1x/sessão)\nAvalie a msg:\n"
            '1. Confirmação ("para mim/eu/sim/pra mim") → t=false. Peça nome, CPF e nascimento de UMA vez '
            "(+ email opcional); extraia os presentes na msg; repergunte SÓ o que faltar. Vá P2 com os 3.\n"
            '2. "outra pessoa/terceiro/filho(a)/mãe..." → t=true. Mesma coleta: peça os 3 de UMA vez; '
            "repergunte só o que faltar. Vá P2 com os 3.\n"
            f'3. Sem confirmação → Resposta EXATA: "{pergunta_p1}". d/c/n="".'
        )
    elif num_pacs == 1:
        p1_section = (
            "P1. QUEM? (Máx 1x/sessão)\nAvalie a msg nesta ordem:\n"
            f'1. "para mim/eu/sim/pra mim" ou "{pac0.get("nome")}" → t=false. d="{pac0.get("nome")}", '
            f'c="{pac0.get("cpf") or ""}", n="{nasc_p1}". Vá P2. {regra_nasc_p1}\n'
            '2. "outra pessoa/terceiro/filho(a)/mãe..." → t=true. Pergunte EXATAMENTE: "Qual o nome completo, '
            'CPF e data de nascimento de quem vai se consultar? 😊 Pode mandar tudo junto!". Extraia os '
            "presentes; repergunte só o que faltar. Vá P2 com os 3.\n"
            f'3. "1" ou sem confirmação → Resposta EXATA: "{pergunta_p1}". d/c/n="". ⛔ "1" NÃO é "sim" — é seleção de menu.'
        )
    else:
        nomes_join = ", ".join(p["nome"] for p in pacientes_formatados)
        p1_section = (
            "P1. QUEM? (Máx 1x/sessão)\n⛔ REGRA ABSOLUTA: Se d/c/n estão VAZIOS → DEVE perguntar para quem é. "
            "NUNCA pule para unidade ou médico.\n\n"
            f"NOMES: {nomes_join}\nPACIENTES_LOOKUP:\n{lookup_p1}\nPERGUNTA: {pergunta_p1}\nDISAMBIGUACAO: {disamb_p1}\n\n"
            "Avalie a msg nesta ordem:\n"
            "1. Nome em NOMES (case-insensitive, 1-2 erros ok):\n"
            "   → d=nome, c=CPF, n=NASC do PACIENTES_LOOKUP. ⛔ NUNCA peça CPF. Se o NASC do escolhido estiver "
            'VAZIO no lookup → pergunte "Qual a data de nascimento? (dia/mês/ano) 😊" antes de P2 (sem ela o '
            "agendamento falha).\n"
            '   → UNIDADE_SALVA vazio? "Temos dois endereços de atendimento, qual a melhor unidade para '
            'você?\\nDigite o número correspondente:\\n\\n1️⃣ Vila Olímpia\\n2️⃣ Tatuapé"\n'
            "   → UNIDADE_SALVA preenchido? Vá P3.\n"
            '2. "para mim"/"eu" → ambíguo → copie DISAMBIGUACAO.\n'
            "3. Após DISAMBIGUACAO: nome confirmado → mesmo que item 1.\n"
            '4. Nome NÃO em NOMES → t=true, d=[nome]. "Qual o CPF e a data de nascimento de [nome]? 😊 Pode '
            'mandar os dois juntos!"\n'
            '   "outra pessoa" SEM nome → t=true. "Qual o nome completo, CPF e data de nascimento de quem vai '
            'se consultar? 😊 Pode mandar tudo junto!"\n'
            '5. Qualquer outra coisa ("1", "agendar", "sim") → copie PERGUNTA. d/c/n VAZIOS.\n'
            '   ⛔ "1" NÃO é "para mim". "1" = quer agendar → PERGUNTA.'
        )

    if num_pacs == 0:
        # FASE4_MEMORIA_SAUDACAO: telefone reconhecido em paciente_memoria mesmo sem match de
        # CPF/ID no TiSaude ainda — reconhece SEM citar médico/unidade/convênio (telefone pode
        # ser compartilhado entre dependentes; afirmar dado específico do titular arriscaria
        # personalizar errado pra quem não é ele). Único trecho deste bloco que NÃO é port fiel
        # do node original — resto do arquivo continua 1:1 com o JS.
        saudacao_intro = (
            "Olá de novo! 👋 Bem-vindo de volta à Oto-SP!" if memoria_paciente else "Olá! 👋 Bem-vindo à Oto-SP!"
        )
        saudacao_section = (
            "━━━ SAUDAÇÃO ━━━\n"
            'Ative APENAS para: "oi", "olá", "bom dia", "boa tarde", "boa noite", "tudo bem" — sem intenção de agendamento.\n'
            '⛔ NÃO ative para: "agendar", "marcar", nome de NOMES, "para mim", "outra pessoa" → vá direto ao passo 1.\n'
            "Resposta:\n"
            f'"{saudacao_intro} O que deseja?\n'
            "1️⃣ Agendar consulta\n"
            "2️⃣ Remarcar consulta\n"
            "3️⃣ Cancelar consulta\n"
            "4️⃣ Consulta pendente\n"
            '5️⃣ Troca de guias e documentos"\n'
            '$$${"t":false,"i":"triagem","d":"","c":"","n":"","conv":"","unid":"","dt":"","per":"","h":"","med":"","id":"","motivo":"","modo":0,"ds":""}'
        )
    else:
        saudacao_section = "# Saudação tratada pelo Agente Triagem/Ver"

    ultimo_med_p3 = (pac0.get("ultimo_medico") or "").strip()
    if ultimo_med_p3 and num_pacs == 1:
        p3_menu = (
            f'Vazio → Resposta EXATA: "Você já consultou com {ultimo_med_p3}. Deseja agendar com ele(a) '
            'novamente ou prefere outro médico? 😊"\n'
            f'  - "sim"/"pode"/"quero"/"esse mesmo" → med="{ultimo_med_p3}", modo=2. Mostre dias via GRADE_MED abaixo.\n'
            '  - "não"/"outro"/"quero outro" → mostre menu básico abaixo.'
        )
    else:
        p3_menu = (
            'Vazio → Resposta EXATA: "Com qual médico você prefere?\n'
            "Digite o número ou escreva:\n\n"
            "1️⃣ Primeiro horário disponível\n"
            "2️⃣ Escolher especialista\n"
            '3️⃣ Já tenho médico de preferência"'
        )

    return ResultadoMontarContexto(
        paciente_encontrado=len(pacientes_formatados) > 0,
        pacientes=pacientes_formatados,
        nome=nome_junto or paciente_base.get("nome") or None,
        cpf=paciente_base.get("cpf") or None,
        nascimento=paciente_base.get("nascimento") or None,
        id_tisaude=paciente_base.get("id_tisaude") or None,
        ultimo_medico=ultimo_medico_geral,
        data_ultima_consulta=data_ultima_consulta_geral,
        ultimo_convenio=ultimo_convenio_geral,
        data_minima_carencia=data_minima_carencia,
        data_minima_carencia_br=data_minima_carencia_br,
        sessao_intencao=sessao_intencao,
        sessao_rota=sessao_rota,
        cache_ativo=cache_ativo,
        unidade_cache=unidade_cache,
        ultimo_dia_exibido=ultimo_dia_exibido,
        ultimo_dia_texto=ultimo_dia_texto,
        nome_dependente=sessao.get("nome_dependente") or "",
        cpf_dependente=sessao.get("cpf_dependente") or "",
        nascimento_dependente=sessao.get("nascimento_dependente") or "",
        texto_ia=texto_ia,
        telefone=telefone,
        coleta_unidade=sessao.get("coleta_unidade") or "",
        coleta_data=sessao.get("coleta_data") or "",
        coleta_periodo=sessao.get("coleta_periodo") or "",
        coleta_convenio=sessao.get("coleta_convenio") or "",
        coleta_horario=sessao.get("coleta_horario") or "",
        coleta_terceiro=sessao.get("coleta_terceiro") or "",
        coleta_medico=medico_candidato_msg or sessao.get("coleta_medico") or "",
        coleta_modo=sessao["coleta_modo"] if sessao.get("coleta_modo") is not None else 0,
        coleta_dia_semana=sessao.get("coleta_dia_semana") or "",
        coleta_id_tisaude=sessao.get("coleta_id_tisaude") or "",
        coleta_id_agendamento=sessao.get("coleta_id_agendamento") or "",
        medico_candidato_msg=medico_candidato_msg,
        coleta_email=sessao.get("coleta_email") or "",
        lista_med=lista_med,
        p1_section=p1_section,
        saudacao_section=saudacao_section,
        p3_menu=p3_menu,
        grade_med=grade_med,
        dia_lookup=dia_lookup,
        hoje=hoje,
        amanha=amanha,
        prox_seg=prox_seg,
        prox_ter=prox_ter,
        prox_qua=prox_qua,
        prox_qui=prox_qui,
        prox_sex=prox_sex,
        status_leitura_timelines=status_leitura_timelines,
        resp_sim_med=resp_sim_med,
    )
