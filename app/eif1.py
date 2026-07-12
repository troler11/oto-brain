"""
Port fiel do nó 'Extrair Intencao Final1' (EIF1) — DEPLOY/_proposed_Extrair_Intencao_Final1.js
(646 linhas, snapshot 12/07/2026). Fase 1 do plano de migração (ver
C:\\Users\\lucas\\.claude\\plans\\unified-coalescing-puppy.md).

Traduz o output bruto do agente MINI (raw string, às vezes com bloco $$$ JSON) em estado
estruturado de conversa. Toda a lógica de fallback/canonicalização é preservada — este é um
PORT, não uma reescrita: a ordem dos blocos e as regras exatas espelham o JS de propósito,
pra permitir comparação 1:1 durante a validação (Fase 1 do plano).

Diferenças deliberadas de plataforma (não de lógica):
  - `$('Extrair Rota').first().json` do n8n → parâmetro `extrair_rota: dict`
  - `$('Carregar Sessao').first().json` do n8n → parâmetro `carregar_sessao: dict | None`
  - `Date.now()` / fuso do n8n (America/Sao_Paulo hardcoded via -3h) → mesma técnica aqui
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone


def _strip_accents(s: str) -> str:
    """Equivalente a .normalize('NFD').replace(/[\\u0300-\\u036f]/g, '')."""
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def _norm(s) -> str:
    """Normalização comum: lowercase, sem acento, trim."""
    return _strip_accents(str(s or "")).lower().strip()


# FIX_DT_DS_MISMATCH / FIX_CLEAR_FIELDS usam a convenção JS de getDay(): domingo=0.
_DS_MAP = {"segunda": 1, "terca": 2, "quarta": 3, "quinta": 4, "sexta": 5, "sabado": 6, "domingo": 0}

_PERIODO_UNICO = {
    "Dr. Caio Vinicius Saettini||Vila Olímpia": "manha",
    "Dra. Fernanda Butura Broetto||Vila Olímpia": "tarde",
    "Dra. Fernanda Butura Broetto||Tatuapé": "tarde",
}

_PERIODO_DIA = {
    "Dra. Giseli Rebechi||Vila Olímpia||quarta": "manha",
    "Dra. Giseli Rebechi||Vila Olímpia||sexta": "manha",
    "Dr. Elias Lobo Braga||Vila Olímpia||terça": "tarde",
    "Dr. Jose Emmanuel Burle Neto||Vila Olímpia||quarta": "manha",
    "Dra. Stephanie Rugeri de Souza||Vila Olímpia||terça": "manha",
    "Dra. Stephanie Rugeri de Souza||Vila Olímpia||quarta": "tarde",
    "Dra. Juliana Paulino do Amaral||Vila Olímpia||segunda": "tarde",
    "Dra. Juliana Paulino do Amaral||Vila Olímpia||sexta": "tarde",
    "Dr. Torcuato Sanchez Rojas Neto||Vila Olímpia||quarta": "tarde",
    "Dra. Fernanda Butura Broetto||Vila Olímpia||quinta": "tarde",
    "Dr. Caio Vinicius Saettini||Vila Olímpia||terça": "manha",
    "Dr. Elias Lobo Braga||Tatuapé||sexta": "manha",
    "Dra. Fernanda Butura Broetto||Tatuapé||sexta": "tarde",
}

_MED_CANON = [
    (re.compile(r"giseli|rebechi"), "Dra. Giseli Rebechi"),
    (re.compile(r"elias|lobo braga"), "Dr. Elias Lobo Braga"),
    (re.compile(r"emmanuel|burle"), "Dr. Jose Emmanuel Burle Neto"),
    (re.compile(r"stephanie|rugeri"), "Dra. Stephanie Rugeri de Souza"),
    (re.compile(r"juliana|paulino|amaral"), "Dra. Juliana Paulino do Amaral"),
    (re.compile(r"torcuato|rojas"), "Dr. Torcuato Sanchez Rojas Neto"),
    (re.compile(r"fernanda|butura|broetto"), "Dra. Fernanda Butura Broetto"),
    (re.compile(r"caio|saettini"), "Dr. Caio Vinicius Saettini"),
]

_RE_QUOTES = [('"', '"'), ("“", "”")]


def _cpf_digitos_validos(digs: str) -> bool:
    if not re.fullmatch(r"\d{11}", digs) or re.fullmatch(r"(\d)\1{10}", digs):
        return False
    s1 = sum(int(digs[i]) * (10 - i) for i in range(9))
    d1 = (s1 * 10) % 11
    if d1 == 10:
        d1 = 0
    s2 = sum(int(digs[i]) * (11 - i) for i in range(10))
    d2 = (s2 * 10) % 11
    if d2 == 10:
        d2 = 0
    return d1 == int(digs[9]) and d2 == int(digs[10])


def _hoje_sp() -> datetime:
    """Mesmo truque do JS: Date.now() - 3h ~ America/Sao_Paulo (sem lib de timezone)."""
    return datetime.now(timezone.utc) - timedelta(hours=3)


@dataclass
class ResultadoEIF1:
    intencao: str
    texto_ia: str
    dados: dict = field(default_factory=dict)
    eh_terceiro: bool = False
    nome_dependente: str = ""
    cpf_dependente: str = ""
    nascimento_dependente: str = ""
    convenio: str = ""
    unidade_coleta: str = ""
    data_coleta: str = ""
    periodo_coleta: str = ""
    horario_coleta: str = ""
    medico_coleta: str = ""
    modo_coleta: int = 0
    dia_semana_coleta: str = ""
    id_tisaude_coleta: str = ""
    id_agendamento_coleta: str = ""
    id_cancelamento: str = ""
    motivo_cancelamento: str = ""
    motivo_humano: str = ""
    conv_fail: int = -1
    ir_agenda: bool = False
    ir_coleta: bool = False
    ir_humano: bool = False
    ir_concluido: bool = False
    ir_triagem: bool = False

    def to_dict(self) -> dict:
        return {
            "intencao": self.intencao,
            "texto_ia": self.texto_ia,
            "dados": self.dados,
            "eh_terceiro": self.eh_terceiro,
            "nome_dependente": self.nome_dependente,
            "cpf_dependente": self.cpf_dependente,
            "nascimento_dependente": self.nascimento_dependente,
            "convenio": self.convenio,
            "unidade_coleta": self.unidade_coleta,
            "data_coleta": self.data_coleta,
            "periodo_coleta": self.periodo_coleta,
            "horario_coleta": self.horario_coleta,
            "medico_coleta": self.medico_coleta,
            "modo_coleta": self.modo_coleta,
            "dia_semana_coleta": self.dia_semana_coleta,
            "id_tisaude_coleta": self.id_tisaude_coleta,
            "id_agendamento_coleta": self.id_agendamento_coleta,
            "id_cancelamento": self.id_cancelamento,
            "motivo_cancelamento": self.motivo_cancelamento,
            "motivo_humano": self.motivo_humano,
            "conv_fail": self.conv_fail,
            "ir_agenda": self.ir_agenda,
            "ir_coleta": self.ir_coleta,
            "ir_humano": self.ir_humano,
            "ir_concluido": self.ir_concluido,
            "ir_triagem": self.ir_triagem,
        }


def processar(raw: str, extrair_rota: dict, carregar_sessao: dict | None = None) -> ResultadoEIF1:
    er = extrair_rota or {}
    sessao = carregar_sessao or {}
    raw = raw or ""

    intencao = "conversa"
    extraido: dict = {}
    texto_ia = raw

    # FIX_LEAK_JSON_CLASSIFICADOR
    eh_json_classificador = False
    if "$$$" not in raw and raw.lstrip().startswith("{"):
        try:
            pc = json.loads(raw)
            if (
                isinstance(pc, dict)
                and ("intencao_rapida" in pc or "rota_agente" in pc or "precisa_agente_completo" in pc)
                and "output" not in pc
                and "meta" not in pc
            ):
                eh_json_classificador = True
        except (json.JSONDecodeError, TypeError):
            pass

    if eh_json_classificador:
        extraido = {
            "i": er.get("intencao_rapida") or er.get("sessao_intencao") or "coleta",
            "t": er.get("coleta_terceiro") == "true" or er.get("coleta_terceiro") is True,
            "d": er.get("nome_dependente") or "",
            "c": er.get("cpf_dependente") or "",
            "n": er.get("nascimento_dependente") or "",
            "conv": er.get("coleta_convenio") or "",
            "unid": er.get("coleta_unidade") or "",
            "dt": er.get("coleta_data") or "",
            "per": er.get("coleta_periodo") or "",
            "h": er.get("coleta_horario") or "",
            "med": er.get("coleta_medico") or "",
            "modo": er.get("coleta_modo") or 0,
            "ds": er.get("coleta_dia_semana") or "",
            "id": "",
            "motivo": "",
        }
        texto_ia = "Desculpe, não entendi. Pode repetir, por favor? 😊"

    # Modo A: JSON puro
    if not eh_json_classificador and raw.lstrip().startswith("{"):
        parsed = None
        try:
            parsed = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            pass
        if isinstance(parsed, dict) and isinstance(parsed.get("output"), str) and parsed["output"].lstrip().startswith("{"):
            try:
                parsed = json.loads(parsed["output"])
            except (json.JSONDecodeError, TypeError):
                pass
        if isinstance(parsed, dict) and parsed.get("meta"):
            texto_ia = parsed.get("output") or ""
            extraido = parsed["meta"]
        elif isinstance(parsed, dict) and parsed.get("output"):
            texto_ia = parsed["output"]
            extraido = {}
    # Modo B: legado com $$$
    elif "$$$" in raw:
        partes = raw.split("$$$")
        texto_ia = partes[0].strip()
        json_str = partes[1] if len(partes) > 1 else ""
        inicio = json_str.find("{")
        fim = json_str.rfind("}")
        if inicio != -1 and fim != -1:
            try:
                extraido = json.loads(json_str[inicio : fim + 1])
            except (json.JSONDecodeError, TypeError):
                extraido = {}

    # FIX_FALLBACK_SEM_JSON
    if "$$$" in raw and not extraido:
        extraido = {
            "i": er.get("intencao_rapida") or "coleta",
            "t": False,
            "d": "",
            "c": "",
            "n": "",
            "conv": er.get("coleta_convenio") or "",
            "unid": er.get("coleta_unidade") or "",
            "dt": er.get("coleta_data") or "",
            "per": er.get("coleta_periodo") or "",
            "h": er.get("coleta_horario") or "",
            "med": er.get("coleta_medico") or "",
            "modo": er.get("coleta_modo") or 0,
            "ds": er.get("coleta_dia_semana") or "",
            "id": "",
            "motivo": "",
        }

    # FIX_67351: erro de framework nunca chega ao paciente
    if re.search(r"agent stopped due to", raw, re.IGNORECASE) and "$$$" not in raw:
        extraido = {
            "i": "humano",
            "t": er.get("coleta_terceiro") == "true" or er.get("coleta_terceiro") is True,
            "d": er.get("nome_dependente") or "",
            "c": er.get("cpf_dependente") or "",
            "n": er.get("nascimento_dependente") or "",
            "conv": er.get("coleta_convenio") or "",
            "unid": er.get("coleta_unidade") or "",
            "dt": er.get("coleta_data") or "",
            "per": er.get("coleta_periodo") or "",
            "h": er.get("coleta_horario") or "",
            "med": er.get("coleta_medico") or "",
            "modo": er.get("coleta_modo") or 0,
            "ds": er.get("coleta_dia_semana") or "",
            "id": "",
            "motivo": (
                "ERRO TECNICO (max iterations): o agente nao conseguiu concluir — provavel "
                "falha na tool de criacao. Criar o agendamento manualmente com os dados "
                "salvos e avisar o paciente."
            ),
        }
        texto_ia = "Ops, tive um problema técnico para concluir aqui! 🙏 Já chamei uma atendente para finalizar seu atendimento, um instante."

    # FIX_FALLBACK_SEM_BBB
    if "$$$" not in raw and not raw.lstrip().startswith("{") and raw.strip() and not extraido:
        extraido = {
            "i": er.get("intencao_rapida") or er.get("sessao_intencao") or "coleta",
            "t": er.get("coleta_terceiro") == "true" or er.get("coleta_terceiro") is True,
            "d": er.get("nome_dependente") or "",
            "c": er.get("cpf_dependente") or "",
            "n": er.get("nascimento_dependente") or "",
            "conv": er.get("coleta_convenio") or "",
            "unid": er.get("coleta_unidade") or "",
            "dt": er.get("coleta_data") or "",
            "per": er.get("coleta_periodo") or "",
            "h": er.get("coleta_horario") or "",
            "med": er.get("coleta_medico") or "",
            "modo": er.get("coleta_modo") or 0,
            "ds": er.get("coleta_dia_semana") or "",
            "id": "",
            "motivo": "",
        }
        intencao = extraido["i"]
        texto_ia = raw.strip()

    # FIX_ASPAS_ENVOLVENTES
    tq = (texto_ia or "").strip()
    for qa, qz in _RE_QUOTES:
        if len(tq) > 2 and tq.startswith(qa) and tq.endswith(qz):
            miolo = tq[1:-1]
            if qa not in miolo and qz not in miolo:
                texto_ia = miolo.strip()
                break

    # FIX_DCN_FALLBACK / FIX_DCN_NOME_DIFERENTE
    def _eq_dcn(a, b) -> bool:
        return _norm(a) != "" and _norm(a) == _norm(b)

    if extraido.get("d") and not extraido.get("c") and er.get("cpf_dependente") and _eq_dcn(extraido["d"], er.get("nome_dependente")):
        extraido["c"] = er["cpf_dependente"]
    if extraido.get("d") and not extraido.get("n") and er.get("nascimento_dependente") and _eq_dcn(extraido["d"], er.get("nome_dependente")):
        extraido["n"] = er["nascimento_dependente"]
    if not extraido.get("d") and er.get("nome_dependente"):
        extraido["d"] = er["nome_dependente"]
        if not extraido.get("c"):
            extraido["c"] = er.get("cpf_dependente") or ""
        if not extraido.get("n"):
            extraido["n"] = er.get("nascimento_dependente") or ""

    # FIX_PMSG_FALLBACK
    pm_er = er.get("_pmsg")
    if pm_er:
        if not extraido.get("unid") and pm_er.get("unid"):
            extraido["unid"] = pm_er["unid"]
        if not extraido.get("med") and pm_er.get("med"):
            extraido["med"] = pm_er["med"]
            if not extraido.get("modo") and pm_er.get("modo"):
                extraido["modo"] = pm_er["modo"]
        if not extraido.get("dt") and pm_er.get("dt"):
            extraido["dt"] = pm_er["dt"]
        if not extraido.get("ds") and pm_er.get("ds"):
            extraido["ds"] = pm_er["ds"]
        if not extraido.get("per") and pm_er.get("per"):
            extraido["per"] = pm_er["per"]
        if not extraido.get("conv") and pm_er.get("conv"):
            extraido["conv"] = pm_er["conv"]

    # FIX_T_BOOLEAN
    if isinstance(extraido.get("t"), str):
        extraido["t"] = extraido["t"] == "true"

    intencao = extraido.get("i") or extraido.get("intencao") or "conversa"

    # FIX_OFERTA_HUMANO_CANONICO
    if intencao != "humano" and re.search(r"deseja falar com um atendente", texto_ia, re.IGNORECASE):
        intencao = "oferta_humano"
        extraido["i"] = "oferta_humano"

    # FIX_67529
    if intencao not in ("humano", "oferta_humano") and re.search(r"posso te ajudar a agendar\?", texto_ia, re.IGNORECASE):
        intencao = "oferta_agendar"
        extraido["i"] = "oferta_agendar"

    eh_terceiro = extraido.get("t") is True or extraido.get("terceiro") is True
    nome_dependente = extraido.get("d") or extraido.get("nome_dependente") or ""
    cpf_dependente = extraido.get("c") or extraido.get("cpf_dependente") or ""
    nasc_dependente = extraido.get("n") or extraido.get("nascimento_dependente") or ""
    convenio = extraido.get("conv") or extraido.get("convenio") or ""
    id_cancelamento = extraido.get("id") or extraido.get("id_agendamento_cancelamento") or ""
    id_agendamento_coleta = extraido.get("id") or extraido.get("id_agendamento") or ""
    motivo_cancelamento = extraido.get("motivo") or extraido.get("motivo_cancelamento") or ""
    motivo_humano = extraido.get("motivo") or extraido.get("motivo_humano") or extraido.get("m") or ""

    unidade_coleta = extraido.get("unid") or ""
    data_coleta = extraido.get("dt") or ""
    periodo_coleta = extraido.get("per") or ""
    horario_coleta = extraido.get("h") or ""
    medico_coleta = extraido.get("med") or ""
    modo_coleta = int(extraido["modo"]) if extraido.get("modo") else 0
    dia_semana_coleta = extraido.get("ds") or ""

    # FIX_SEM_PREF_CANON
    if medico_coleta:
        med_canon_sp = _norm(medico_coleta)
        if med_canon_sp == "sem preferencia":
            medico_coleta = "sem preferencia"
            extraido["med"] = "sem preferencia"

    # FIX_PERIODO_DETERMINISTICO
    chave_per = f"{medico_coleta}||{unidade_coleta}"
    if not periodo_coleta and chave_per in _PERIODO_UNICO:
        periodo_coleta = _PERIODO_UNICO[chave_per]
        extraido["per"] = periodo_coleta

    # FIX_PERIODO_DIA_SEMANA
    if not periodo_coleta and medico_coleta and dia_semana_coleta:
        chave_dia = f"{medico_coleta}||{unidade_coleta}||{dia_semana_coleta}"
        if chave_dia in _PERIODO_DIA:
            periodo_coleta = _PERIODO_DIA[chave_dia]
            extraido["per"] = periodo_coleta

    # FIX_CONV_GUARD
    if convenio and convenio not in ("PART?", "RESET_CONV"):
        sess_conv = er.get("coleta_convenio") or ""
        if not sess_conv:
            msg_orig = (er.get("texto_ia") or "").lower()
            convs = ["porto", "itau", "itaú", "omint", "bradesco", "particular", "part", "convenio", "convênio"]
            if not any(c in msg_orig for c in convs):
                convenio = ""
                extraido["conv"] = ""

    # FIX_PERIODO_NORMALIZAR
    if periodo_coleta and periodo_coleta not in ("manha", "tarde"):
        periodo_coleta = ""
        extraido["per"] = ""

    # FIX_MODO1_DS_CLEAR / FIX_MODO1_MED_CLEAR
    if modo_coleta == 1 and not horario_coleta and medico_coleta and medico_coleta not in ("sem preferencia", "sem preferência"):
        medico_coleta = "sem preferencia"
        extraido["med"] = "sem preferencia"
    if modo_coleta == 1 and dia_semana_coleta:
        dia_semana_coleta = ""
        extraido["ds"] = ""

    # FIX_DT_DS_MISMATCH
    if data_coleta and dia_semana_coleta and modo_coleta not in (1, 3):
        ds_norm = _norm(dia_semana_coleta)
        target_dow = _DS_MAP.get(ds_norm)
        if target_dow is not None:
            try:
                y, m, d = (int(p) for p in data_coleta.split("-"))
                dt_date = datetime(y, m, d)
                actual_dow = (dt_date.weekday() + 1) % 7  # Python Mon=0 -> JS Sun=0 convenção
                if actual_dow != target_dow:
                    diff = ((target_dow - actual_dow) + 7) % 7 or 7
                    fixed = dt_date + timedelta(days=diff)
                    data_coleta = fixed.strftime("%Y-%m-%d")
                    extraido["dt"] = data_coleta
            except (ValueError, TypeError):
                pass

    # FIX_DIA_SEMANA_ER_FALLBACK
    if er.get("_dia_semana_precomputed") or (er.get("_modo2_precomputed") and er.get("coleta_dia_semana")):
        if not dia_semana_coleta and er.get("coleta_dia_semana"):
            dia_semana_coleta = er["coleta_dia_semana"]
            extraido["ds"] = dia_semana_coleta
        if not data_coleta and er.get("coleta_data"):
            data_coleta = er["coleta_data"]
            extraido["dt"] = data_coleta

    # FIX_MODO2_ER_FALLBACK
    if er.get("_modo2_precomputed"):
        if modo_coleta != 2:
            modo_coleta = 2
            extraido["modo"] = 2
        if not dia_semana_coleta and er.get("coleta_dia_semana"):
            dia_semana_coleta = er["coleta_dia_semana"]
            extraido["ds"] = dia_semana_coleta
        if not data_coleta and er.get("coleta_data"):
            data_coleta = er["coleta_data"]
            extraido["dt"] = data_coleta

    # FIX_PERIODO_ER_FALLBACK / FIX_PERIODO_STALE
    if er.get("_periodo_precomputed") and er.get("coleta_periodo") and periodo_coleta != er.get("coleta_periodo"):
        periodo_coleta = er["coleta_periodo"]
        extraido["per"] = periodo_coleta

    # FIX_MODO3_AUTO
    if medico_coleta and medico_coleta not in ("sem preferencia", "sem preferência") and modo_coleta not in (1, 3):
        modo_coleta = 3
        extraido["modo"] = 3

    # FIX_MODO1_ER_FALLBACK
    if er.get("_modo1_precomputed"):
        if not modo_coleta:
            modo_coleta = 1
            extraido["modo"] = 1
        if not medico_coleta:
            medico_coleta = "sem preferencia"
            extraido["med"] = "sem preferencia"
        if not data_coleta and er.get("coleta_data"):
            data_coleta = er["coleta_data"]
            extraido["dt"] = data_coleta

    # FIX_MODO1_DT_AMANHA
    if modo_coleta == 1 and not data_coleta:
        amanha = _hoje_sp() + timedelta(days=1)
        data_coleta = amanha.strftime("%Y-%m-%d")
        extraido["dt"] = data_coleta

    # FIX_PART_CONV_FALLBACK
    if not convenio:
        er_conv_part = er.get("coleta_convenio") or ""
        if er_conv_part == "PART?":
            convenio = "PART?"
            extraido["conv"] = "PART?"

    # FIX_OMINT_CONV_FALLBACK
    if not convenio:
        er_conv_om = er.get("coleta_convenio") or ""
        if er_conv_om == "OMINT?" or re.match(r"^Omint\s", er_conv_om, re.IGNORECASE):
            convenio = er_conv_om
            extraido["conv"] = er_conv_om

    # FIX_CPF_CANONICO
    if not eh_terceiro and nome_dependente:
        pacs_cc = er.get("pacientes") or []
        d_cc = _norm(nome_dependente)
        match_cc = [p for p in pacs_cc if _norm(p.get("nome")) == d_cc]
        if not match_cc:
            match_cc = [p for p in pacs_cc if _norm(p.get("nome")).split(" ")[0] == d_cc]
        if len(match_cc) == 1:
            p_cc = match_cc[0]
            if p_cc.get("cpf") and cpf_dependente != p_cc["cpf"]:
                cpf_dependente = p_cc["cpf"]
                extraido["c"] = p_cc["cpf"]
            if p_cc.get("nascimento") and nasc_dependente != p_cc["nascimento"]:
                nasc_dependente = p_cc["nascimento"]
                extraido["n"] = p_cc["nascimento"]

    # FIX_MULTI_CANONICO
    cd_mc = er.get("_cad_det")
    if cd_mc:
        if cd_mc.get("c") and cpf_dependente != cd_mc["c"]:
            cpf_dependente = cd_mc["c"]
            extraido["c"] = cd_mc["c"]
        if cd_mc.get("n") and nasc_dependente != cd_mc["n"]:
            nasc_dependente = cd_mc["n"]
            extraido["n"] = cd_mc["n"]
        if cd_mc.get("d") and not nome_dependente:
            nome_dependente = cd_mc["d"]
            extraido["d"] = cd_mc["d"]
        if cd_mc.get("email") and not extraido.get("email"):
            extraido["email"] = cd_mc["email"]

    # FIX_CPF_DV_BACKSTOP
    dig_dv = re.sub(r"\D", "", str(cpf_dependente or ""))
    if cpf_dependente and not _cpf_digitos_validos(dig_dv):
        cpf_dependente = ""
        extraido["c"] = ""
    elif cpf_dependente and dig_dv != cpf_dependente:
        cpf_dependente = dig_dv
        extraido["c"] = dig_dv

    # FIX_NASC_BACKSTOP
    raw_nb = str(nasc_dependente or "").strip()
    if raw_nb:
        d_nb = m_nb = y_nb = 0
        mt_nb = re.match(r"^(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})$", raw_nb)
        if mt_nb:
            d_nb, m_nb, y_str = int(mt_nb.group(1)), int(mt_nb.group(2)), mt_nb.group(3)
            y_nb = int(y_str)
            if len(y_str) == 2:
                y_nb += 1900 if y_nb > 26 else 2000
        else:
            mt_nb2 = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", raw_nb)
            if mt_nb2:
                y_nb, m_nb, d_nb = int(mt_nb2.group(1)), int(mt_nb2.group(2)), int(mt_nb2.group(3))
        ok_nb = False
        if y_nb:
            try:
                dt_nb = datetime(y_nb, m_nb, d_nb)
                hj_nb = _hoje_sp()
                ok_nb = dt_nb < hj_nb.replace(tzinfo=None) and y_nb >= hj_nb.year - 120
            except ValueError:
                ok_nb = False
        if ok_nb:
            fmt_nb = f"{d_nb:02d}/{m_nb:02d}/{y_nb}"
            if fmt_nb != nasc_dependente:
                nasc_dependente = fmt_nb
                extraido["n"] = fmt_nb
        else:
            nasc_dependente = ""
            extraido["n"] = ""

    # FIX_ID_TISAUDE_LOOKUP
    pacs_it = er.get("pacientes") or []
    id_tisaude_coleta = ""
    if cpf_dependente and not eh_terceiro and len(pacs_it) > 1:
        match_pac = next((p for p in pacs_it if p.get("cpf") == cpf_dependente), None)
        if match_pac:
            id_tisaude_coleta = str(match_pac.get("id_tisaude") or "")

    # FIX_TITULAR_DCN / FIX_TITULAR_DCN_GATE
    if not eh_terceiro and (unidade_coleta or intencao in ("confirmacao", "execucao")):
        id_sel_tit = str(er.get("coleta_id_tisaude") or id_tisaude_coleta or "")
        pac_tit = None
        if cpf_dependente:
            pac_tit = next((p for p in pacs_it if p.get("cpf") == cpf_dependente), None)
        if not pac_tit and id_sel_tit:
            pac_tit = next((p for p in pacs_it if str(p.get("id_tisaude")) == id_sel_tit), None)
        if not pac_tit and nome_dependente:
            pac_tit = next((p for p in pacs_it if _norm(p.get("nome")) == _norm(nome_dependente)), None)
        if not pac_tit and len(pacs_it) == 1:
            pac_tit = pacs_it[0]
        if pac_tit:
            if not nome_dependente or nome_dependente == "Titular":
                nome_dependente = pac_tit.get("nome")
                extraido["d"] = pac_tit.get("nome")
            if not cpf_dependente:
                cpf_dependente = pac_tit.get("cpf")
                extraido["c"] = pac_tit.get("cpf")
            if not nasc_dependente or nasc_dependente == "Titular":
                nasc_dependente = pac_tit.get("nascimento")
                extraido["n"] = pac_tit.get("nascimento")
            if not id_tisaude_coleta and pac_tit.get("id_tisaude"):
                id_tisaude_coleta = str(pac_tit["id_tisaude"])

    # FIX_CANCEL_VAZIO_NAO_HUMANO
    tnorm_cv = _norm(texto_ia)
    if intencao == "humano" and "nao encontrei consultas" in tnorm_cv:
        intencao = "cancelando"
        extraido["i"] = "cancelando"

    # FIX_CLEAR_FIELDS
    clear_pm = er.get("_clear_pm")
    if clear_pm:
        def _dig_cf(v):
            return re.sub(r"\D", "", str(v or ""))

        def _eq_cf(a, b):
            return str(a or "").strip().lower() == str(b or "").strip().lower()

        if clear_pm.get("dt") and (not data_coleta or _eq_cf(data_coleta, sessao.get("coleta_data"))):
            data_coleta = "__CLEAR__"
        if clear_pm.get("per") and not periodo_coleta:
            periodo_coleta = "__CLEAR__"
        if clear_pm.get("ds") and not dia_semana_coleta:
            dia_semana_coleta = "__CLEAR__"
        if clear_pm.get("h") and (not horario_coleta or _eq_cf(horario_coleta, sessao.get("coleta_horario"))):
            horario_coleta = "__CLEAR__"
        if clear_pm.get("d") and (not nome_dependente or _eq_cf(nome_dependente, sessao.get("nome_dependente"))):
            nome_dependente = "__CLEAR__"
        if clear_pm.get("c") and (not cpf_dependente or _dig_cf(cpf_dependente) == _dig_cf(sessao.get("cpf_dependente"))):
            cpf_dependente = "__CLEAR__"
        if clear_pm.get("n") and (not nasc_dependente or _eq_cf(nasc_dependente, sessao.get("nascimento_dependente"))):
            nasc_dependente = "__CLEAR__"
        if clear_pm.get("id") and (not id_tisaude_coleta or str(id_tisaude_coleta) == str(sessao.get("coleta_id_tisaude") or "")):
            id_tisaude_coleta = "__CLEAR__"

    # FIX_CONV_FAIL
    conv_fail = int(extraido["cf"]) if extraido.get("cf") is not None else -1

    # FIX_SAUDACAO_PRIMEIRO_CONTATO
    idade_sd = float("inf")
    if sessao.get("sessao_atualizada_em"):
        try:
            atualizado = sessao["sessao_atualizada_em"]
            if isinstance(atualizado, str):
                atualizado = datetime.fromisoformat(atualizado.replace("Z", "+00:00"))
            idade_sd = (datetime.now(timezone.utc) - atualizado).total_seconds() * 1000
        except (ValueError, TypeError):
            idade_sd = float("inf")
    novo_sd = not sessao.get("sessao_intencao") or idade_sd > 12 * 3600 * 1000
    txt_sd = (texto_ia or "").strip()
    ja_sauda_sd = bool(re.match(r"^(ol[aá]\b|oi\b|bom dia|boa tarde|boa noite)", txt_sd, re.IGNORECASE)) or "Bem-vindo" in txt_sd
    if novo_sd and txt_sd and not ja_sauda_sd:
        h_sd = _hoje_sp().hour
        sd_sd = "Bom dia" if h_sd < 12 else ("Boa tarde" if h_sd < 18 else "Boa noite")
        texto_ia = f"{sd_sd}! 👋 Eu sou a assistente virtual da Oto-SP.\n\n{texto_ia}"

    # FIX_65707
    med_raw_657 = _norm(extraido.get("med") or "")
    if med_raw_657 and med_raw_657 != "sem preferencia":
        for regex, canon in _MED_CANON:
            if regex.search(med_raw_657):
                extraido["med"] = canon
                break

    # FIX_64079 / FIX_65038
    if "[ENCERRAMENTO" in (er.get("texto_ia") or "") and intencao != "humano":
        intencao = "concluido"
        extraido["i"] = "concluido"

    return ResultadoEIF1(
        intencao=intencao,
        texto_ia=texto_ia,
        dados=extraido,
        eh_terceiro=eh_terceiro,
        nome_dependente=nome_dependente,
        cpf_dependente=cpf_dependente,
        nascimento_dependente=nasc_dependente,
        convenio=convenio,
        unidade_coleta=unidade_coleta,
        data_coleta=data_coleta,
        periodo_coleta=periodo_coleta,
        horario_coleta=horario_coleta,
        medico_coleta=medico_coleta,
        modo_coleta=modo_coleta,
        dia_semana_coleta=dia_semana_coleta,
        id_tisaude_coleta=id_tisaude_coleta,
        id_agendamento_coleta=id_agendamento_coleta,
        id_cancelamento=id_cancelamento,
        motivo_cancelamento=motivo_cancelamento,
        motivo_humano=motivo_humano,
        conv_fail=conv_fail,
        ir_agenda=intencao == "agenda",
        ir_coleta=intencao == "coleta",
        ir_humano=intencao == "humano",
        ir_concluido=intencao == "concluido",
        ir_triagem=intencao == "triagem",
    )
