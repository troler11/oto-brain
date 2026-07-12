"""
Port fiel do nó 'Extrair Rota' (ER) — DEPLOY/_proposed_Extrair_Rota.js (4.774 linhas,
snapshot 12/07/2026). Fase 1 do plano de migração (ver
C:\\Users\\lucas\\.claude\\plans\\unified-coalescing-puppy.md).

ER é grande demais pra portar de uma vez (250+ guards sequenciais, ~135 blocos FIX_*) — este
arquivo cobre, em fatias sucessivas:
  PARTE 1 (linhas 1-736): setup inicial + guards determinísticos de transferência humana
    (documento/telemedicina/reembolso/remarcação múltipla/convênio recusado/lista de espera/
    encaixe/Stephanie teleconsulta) + proteções de contexto de sessão.
  PARTE 2 (linhas 737-1090): coleta de identidade — extração multi-dados (nome/CPF/nascimento/
    email numa mensagem só), lookup de paciente por nome, identidade residual, execução sem
    nascimento, terceiro pede nascimento, CPF/nascimento trocados.
O resto (convênios específicos, guards de agenda/coleta detalhados, empacotamento final) fica
pra próximas fatias — cada uma seguindo o mesmo padrão de port fiel + testes.

Como em app/eif1.py: PORT, não reescrita — ordem dos blocos e regras exatas espelham o JS de
propósito, pra permitir comparação 1:1 na validação.

Diferenças deliberadas de plataforma (não de lógica):
  - `$('Montar Contexto').first().json` → parâmetro `base: dict` (mutado in-place, como no JS)
  - `$('6. Agrupar Textos1').first().json.mensagem_agrupada` → parâmetro `mensagem_agrupada`
  - `$('AI Agent').first().json` → parâmetro `ai_agent_json: dict`
  - `$('Recebe WhatsApp1').first().json.body.payload._data.Info` → parâmetro `whatsapp_info: dict`
  - `$('Recebe WhatsApp1').first().json.body.payload.hasMedia` → parâmetro `has_media: bool`
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime

from app.text_utils import _cpf_digitos_validos, _norm, _strip_accents

SAUDACOES_PURAS = {
    "oi", "ola", "bom dia", "boa tarde", "boa noite",
    "tudo bem", "tudo bom", "oi tudo bem", "ola tudo bem",
    "oi bom dia", "ola bom dia", "oi boa tarde", "oi boa noite",
    "ola boa tarde", "ola boa noite", "hello", "hey",
}

PADROES_TERCEIRO = [
    "para minha filha", "para meu filho",
    "para minha esposa", "para meu marido",
    "para minha mãe", "para minha mae",
    "para meu pai",
    "para minha irmã", "para minha irma",
    "para meu irmão", "para meu irmao",
    "para minha avó", "para minha avo",
    "para meu avô", "para meu avo",
    "para minha sobrinha", "para meu sobrinho",
    "para outra pessoa", "outra pessoa",
    "não é para mim", "nao e para mim",
    "não é pra mim", "nao e pra mim",
    "minha filha", "meu filho",
    "minh filha", "minh filho",
    "minha esposa", "meu marido",
    "minha mãe", "minha mae",
    "meu pai",
    "minha irmã", "minha irma",
    "meu irmão", "meu irmao",
    "minha avó", "minha avo",
    "meu avô", "meu avo",
    "minha sobrinha", "meu sobrinho",
    "pra ela", "pra ele",
    "não sou eu", "nao sou eu",
]

AFIRMACOES_TITULAR = [
    "isso", "isso mesmo", "isso ai", "e isso", "e isso mesmo", "eh isso",
    "exato", "exatamente", "correto", "ta correto", "certo", "ta certo",
    "positivo", "confirmo", "confirma", "confirmado",
    "sou eu mesmo", "eu mesmo", "eu mesma", "e pra mim mesmo",
    "para o titular", "pro titular", "e o titular", "e meu", "minha consulta",
    "sim", "simm", "claro", "perfeito", "titular",
]

MENSAGENS_INFORMATIVAS = [
    "quais convenios", "quais convênios", "convenios aceitos", "convênios aceitos",
    "qual o valor", "quanto custa", "qual o preco", "qual o preço",
    "valor da consulta", "valor a consulta", "gostaria de saber o valor", "saber o valor",
    "qual o endereco", "qual o endereço", "onde fica", "horario de funcionamento",
    "horário de funcionamento", "atendem", "aceitam", "vocês aceitam",
    "voces aceitam", "que convenio", "que convênio", "quais planos", "qual plano",
    "agendar consulta", "agendar retorno", "ver agendamentos",
    "falar com especialista",
]

# FIX_63267b: typos comuns -> forma canonica ANTES do teste de "e medico da casa"
_TYPO_MED_CURA = re.compile(
    r"\b(sthephanie|sthefanie|stefanie|stephany|sthepanie|estefani|estefania|stefani)\b",
    re.IGNORECASE,
)
_EH_MED_CASA_CURA = re.compile(
    r"giseli|rebechi|elias|lobo|braga|jose|emmanuel|burle|caio|saettini|fernanda|"
    r"butura|broetto|stephanie|rugeri|juliana|amaral|torcuato|sanchez|rojas|sem preferencia"
)

_PLANOS_CR: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bamil\b"), "Amil"), (re.compile(r"\bmed ?serv\b"), "Medserv"),
    (re.compile(r"\bunimed\b"), "Unimed"), (re.compile(r"\bsul ?america\b"), "SulAmérica"),
    (re.compile(r"\bhapvida\b"), "Hapvida"),
    (re.compile(r"\bnotre ?dame\b|\bintermedica\b|\bgndi\b"), "NotreDame Intermédica"),
    (re.compile(r"\bprevent senior\b"), "Prevent Senior"), (re.compile(r"\bgolden cross\b"), "Golden Cross"),
    (re.compile(r"\bcare ?plus\b"), "Care Plus"), (re.compile(r"\bcassi\b"), "Cassi"), (re.compile(r"\bgeap\b"), "GEAP"),
    (re.compile(r"\bmediservice\b"), "Mediservice"), (re.compile(r"\bsao cristovao\b"), "São Cristóvão"),
    (re.compile(r"\bcruz azul\b"), "Cruz Azul"), (re.compile(r"\btrasmontano\b"), "Trasmontano"),
    (re.compile(r"\bbiovida\b"), "Biovida"), (re.compile(r"\bameplan\b"), "Ameplan"), (re.compile(r"\bsamp\b"), "Samp"),
    (re.compile(r"\b(?:plano|convenio|pelo|pela)\s+alice\b|\balice\s+(?:saude|plano)\b"), "Alice"),
    (re.compile(r"\bq ?saude\b"), "QSaúde"), (re.compile(r"\bsompo\b"), "Sompo"), (re.compile(r"\ballianz\b"), "Allianz"),
    (re.compile(r"\bleve saude\b"), "Leve Saúde"), (re.compile(r"\bpostal saude\b"), "Postal Saúde"),
]

_SESSOES_VER_ESCOLHER_EXCLUDE = {
    "agenda", "navegacao", "confirmacao", "execucao", "coleta",
    "confirmar_presenca", "confirmar_presenca_escolher",
    "confirmar_presenca_lista", "confirmar_presenca_recusou",
}


def _dow_js(date_str: str) -> int:
    """getUTCDay() de `new Date(date+'T12:00:00-03:00')` — meio-dia SP não cruza fronteira
    UTC de data, então equivale ao weekday() do calendário, convertido pra convenção domingo=0."""
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_str or ""):
        return 0
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return 0
    return (d.weekday() + 1) % 7  # Python Mon=0..Sun=6 -> JS Sun=0..Sat=6


def _texto_ia_livre(base: dict) -> bool:
    """`!(base.texto_ia || '').includes('[')` — true se ainda NENHUM guard determinístico
    injetou instrução nesse turno (guards são "primeira-tag-vence")."""
    return "[" not in (base.get("texto_ia") or "")


@dataclass
class ResultadoIntake:
    base: dict
    intencao_rapida: str
    rota_agente: int
    telefone: str
    texto_usuario: str
    ia_output: dict
    ia_rota_original: int
    eh_cancelamento: bool
    eh_cancel_real: bool
    tem_dependente_salvo: bool
    eh_texto_terceiro: bool
    eh_mensagem_informativa: bool
    eh_sessao_nova: bool
    eh_pergunta_ver: bool
    eh_saudacao_pura: bool
    sessao_era_agenda: bool
    sessao_era_agenda_com_coleta: bool
    tem_identidade_em_andamento: bool
    tem_terceiro_completo: bool
    menu_opt: str
    motivo_humano: str | None = None


def processar_intake(
    base: dict,
    mensagem_agrupada: str,
    ai_agent_json: dict | None,
    whatsapp_info: dict | None,
    has_media: bool = False,
) -> ResultadoIntake:
    base = dict(base or {})
    whatsapp_info = whatsapp_info or {}
    ai_agent_json = ai_agent_json or {}

    # 1. texto do usuário
    texto_usuario = (mensagem_agrupada or "").lower().strip()
    texto_usuario = re.sub(r"([a-zà-ÿ])\d$", r"\1", texto_usuario, flags=re.IGNORECASE).strip()  # FIX_SANITIZE_TRAILING_DIGIT
    texto_usuario = re.sub(r"\s+", " ", texto_usuario).strip()  # FIX_NORMALIZE_SPACES

    # 2. JSON da Mini IA (com fallback pro estado salvo)
    ia_output: dict = {}
    resposta_ia = ai_agent_json.get("output") or ai_agent_json.get("text") \
        or (ai_agent_json.get("message") or {}).get("content") or "{}"
    match = re.search(r"\{[\s\S]*\}", resposta_ia) if isinstance(resposta_ia, str) else None
    try:
        ia_output = json.loads(match.group(0) if match else resposta_ia)
    except (json.JSONDecodeError, TypeError):
        ia_output = {
            "intencao_rapida": base.get("sessao_intencao") or "triagem",
            "rota_agente": int(base.get("sessao_rota") or 0),
            "eh_confirmacao": False,
            "eh_navegacao": False,
            "eh_confirmacao_cancelamento": False,
            "eh_resposta_generica": False,
            "bypass_agente_humano": False,
            "precisa_agente_completo": True,
        }

    # 3. Telefone
    info = whatsapp_info
    sender_alt = info.get("SenderAlt") or ""
    raw_id = sender_alt if "@s.whatsapp.net" in sender_alt else info.get("Chat")
    telefone = ((raw_id or "").split("@")[0].split(":")[0]) or "indefinido"

    # FIX_NOME_TITULAR: PushName -> primeiro nome, capitalizado. So contatos_whatsapp.nome_titular.
    push_raw = (info.get("PushName") or "").strip()
    nome_titular = "".join(c if (c.isalpha() or c.isspace()) else " " for c in push_raw).strip()
    partes = nome_titular.split()
    nome_titular = partes[0] if partes else ""
    if nome_titular:
        nome_titular = nome_titular[0].upper() + nome_titular[1:].lower()
    base["nome_titular"] = nome_titular

    # 4. Saudação pura
    eh_saudacao_pura = texto_usuario in SAUDACOES_PURAS

    # 5. Sempre agente completo
    ia_output["precisa_agente_completo"] = True

    # 6. Roteamento
    intencao_rapida = ia_output.get("intencao_rapida") or "triagem"
    rota_agente = ia_output.get("rota_agente") if isinstance(ia_output.get("rota_agente"), int) else 0
    ia_rota_original = rota_agente

    eh_cancelamento = intencao_rapida in ("cancelando", "cancelamento")
    txt_cancel_check = _norm(texto_usuario)
    eh_cancel_real = eh_cancelamento and bool(re.search(r"cancelar|desmarcar|desistir|nao quero mais|cancela", txt_cancel_check))
    tem_dependente_salvo = bool((base.get("nome_dependente") or "").strip()) and base.get("coleta_terceiro") == "true"

    # FIX_CLEAR_DIA_COMO_MEDICO
    if base.get("coleta_medico"):
        dia_norm = _norm(base["coleta_medico"])
        if re.match(r"^(segunda|seg|terca|ter|quarta|qua|quinta|qui|sexta|sex)([-\s]feira)?$", dia_norm):
            base["coleta_medico"] = ""

    # FIX_TITULAR_ID_INJECT
    if base.get("coleta_id_tisaude") and base.get("coleta_terceiro") != "true":
        p_ti = next((p for p in (base.get("pacientes") or []) if str(p.get("id_tisaude")) == str(base["coleta_id_tisaude"])), None)
        if p_ti:
            base["nome_dependente"] = p_ti.get("nome") or base.get("nome_dependente")
            base["cpf_dependente"] = p_ti.get("cpf") or base.get("cpf_dependente")
            base["nascimento_dependente"] = p_ti.get("nascimento") or base.get("nascimento_dependente")

    eh_texto_terceiro = any(p in texto_usuario for p in PADROES_TERCEIRO)

    eh_mensagem_informativa = any(p in texto_usuario for p in MENSAGENS_INFORMATIVAS)

    eh_sessao_nova = (
        not base.get("sessao_intencao")
        or base.get("sessao_intencao") in ("triagem", "concluido", "humano", "oferta_humano", "confirmar_presenca")
        or eh_mensagem_informativa
    )

    # FIX_MIDIA_SEM_TEXTO
    if not texto_usuario and has_media:
        rota_agente = 0
        intencao_rapida = "triagem"
        base["texto_ia"] = (
            '[MIDIA SEM TEXTO: paciente enviou áudio/imagem/arquivo sem nenhum texto. Responder EXATAMENTE: '
            '"Recebi sua mensagem! 😊 Mas ainda não consigo ouvir áudios nem abrir arquivos por aqui 😅 '
            'Pode me escrever o que você precisa? Ou, se preferir, é só dizer *atendente* que te passo para uma '
            'pessoa da equipe 😊" e emitir i="triagem". ⛔ NAO mostre o menu principal.]'
        )

    sessao_era_agenda = _int(base.get("sessao_rota")) in (2, 3) and not eh_sessao_nova

    tem_identidade_em_andamento = (
        base.get("coleta_terceiro") == "true"
        and bool((base.get("nome_dependente") or "").strip())
        and (not (base.get("cpf_dependente") or "").strip() or not (base.get("nascimento_dependente") or "").strip())
    )
    tem_terceiro_completo = (
        base.get("coleta_terceiro") == "true"
        and bool((base.get("nome_dependente") or "").strip())
        and bool((base.get("cpf_dependente") or "").strip())
        and bool((base.get("nascimento_dependente") or "").strip())
    )
    sessao_era_agenda_com_coleta = (
        _int(base.get("sessao_rota")) in (2, 3)
        and (bool(base.get("coleta_unidade")) or bool(base.get("coleta_data")) or bool(base.get("coleta_periodo"))
             or bool(base.get("coleta_convenio")) or tem_identidade_em_andamento or tem_terceiro_completo)
        and base.get("sessao_intencao") in ("coleta", "agenda")
    )

    eh_pergunta_ver = (
        ("quando" in texto_usuario and "consulta" in texto_usuario)
        or ("esqueci" in texto_usuario and "consulta" in texto_usuario)
        or ("esqueci" in texto_usuario and "data" in texto_usuario)
        or ("data" in texto_usuario and "consulta" in texto_usuario)
        or ("que dia" in texto_usuario and "atende" not in texto_usuario)
        or "meus agendamentos" in texto_usuario
        or "tenho consulta" in texto_usuario
        or "ver agendamento" in texto_usuario
        or "checar agenda" in texto_usuario
    )

    # FIX_REMARCAR_V2 / FIX_58405
    if (re.search(r"\bremarca|\breagend", txt_cancel_check)
            and not re.search(r"\bcancel|\bdesmarc", txt_cancel_check)
            and not sessao_era_agenda_com_coleta and base.get("sessao_intencao") != "coleta"):
        intencao_rapida = "remarcando"

    # FIX_REMARCAR_ESCOLHER
    if base.get("sessao_intencao") == "remarcando_escolher":
        intencao_rapida = "remarcando_escolher"

    motivo_humano = base.get("motivo_humano")

    # FIX_ENCAIXE
    if re.search(r"\bencaix", txt_cancel_check) and rota_agente != 5:
        rota_agente = 5
        intencao_rapida = "humano"
        ia_output["bypass_agente_humano"] = True
        motivo_humano = "Paciente pediu encaixe"
        base["motivo_humano"] = motivo_humano
        base["texto_ia"] = (
            '[ENCAIXE NAO SUPORTADO: responda EXATAMENTE: "O encaixe não consigo fazer por aqui diretamente 😅 '
            'Mas vou te encaminhar para uma atendente, que verifica a possibilidade de encaixe para você! 😊" '
            'e emitir i="humano", motivo="Paciente pediu encaixe". ⛔ NAO diga que VOCE vai verificar/procurar '
            'o encaixe. ⛔ NAO busque horarios.] ' + texto_usuario
        )

    # FIX_LISTA_ESPERA_ROBUSTA
    txt_le = txt_cancel_check
    tem_aviso_intencao_le = bool(re.search(r"avis\w+", txt_le))
    tem_contexto_vaga_le = bool(re.search(r"vaga|vagar|abrir|surgir|aparecer|liberar|dispon", txt_le))
    if (re.search(r"desist[eê]ncia|desistir|lista.{0,15}espera", txt_le)
            or (tem_aviso_intencao_le and tem_contexto_vaga_le)) and rota_agente != 5:
        rota_agente = 5
        intencao_rapida = "humano"
        ia_output["bypass_agente_humano"] = True
        motivo_humano = "Paciente pediu lista de espera / aviso de vagas"
        base["motivo_humano"] = motivo_humano
        base["texto_ia"] = (
            '[LISTA ESPERA NAO SUPORTADA: responda EXATAMENTE: "Infelizmente não temos essa função de aviso '
            'automático de vagas. Mas posso te transferir para um atendente que pode te ajudar com isso! 😊" '
            'e emitir i="humano", motivo="Lista de espera / aviso de vaga".] ' + texto_usuario
        )

    # PROTEÇÃO INFORMATIVA DURANTE COLETA
    if eh_mensagem_informativa and sessao_era_agenda_com_coleta:
        rota_agente = _int(base.get("sessao_rota")) or 2
        intencao_rapida = "agenda"
        if (base.get("coleta_medico") or "").lower().strip() == texto_usuario:
            base["coleta_medico"] = ""

    # FIX_62678/62640 + FIX_63267b: cura médico contaminado
    def _typo_med_cura(v):
        return _TYPO_MED_CURA.sub("Stephanie", str(v or ""))

    def _eh_med_casa_cura(v):
        return bool(_EH_MED_CASA_CURA.search(_norm(v)))

    if base.get("coleta_medico"):
        base["coleta_medico"] = _typo_med_cura(base["coleta_medico"])
    if base.get("medico_candidato_msg"):
        base["medico_candidato_msg"] = _typo_med_cura(base["medico_candidato_msg"])
    if base.get("coleta_medico") and not _eh_med_casa_cura(base["coleta_medico"]):
        base["coleta_medico"] = ""
        if _int(base.get("coleta_modo")) == 3:
            base["coleta_modo"] = 0
    if base.get("medico_candidato_msg") and not _eh_med_casa_cura(base["medico_candidato_msg"]):
        base["medico_candidato_msg"] = ""

    # FIX_63305b: "qual medico tem horario"
    txt_qm = txt_cancel_check
    eh_qual_med_qm = bool(re.search(r"\b(qual|quais|algum|alguma)\s+(dos\s+|das\s+)?medic|\bque\s+medic", txt_qm))
    tem_tempo_qm = bool(re.search(
        r"amanha|\bhoje\b|semana|\bdia\b|horario|vaga|disponivel|\bcedo\b|\bantes\b|segunda|terca|quarta|quinta|sexta",
        txt_qm,
    ))
    if (eh_qual_med_qm and tem_tempo_qm and base.get("coleta_unidade")
            and (rota_agente in (2, 3, 4) or base.get("sessao_intencao") in ("coleta", "agenda", "navegacao", "execucao"))
            and _texto_ia_livre(base) and not ia_output.get("bypass_agente_humano")):
        dt_qm = ""
        if "amanha" in txt_qm:
            dt_qm = base.get("amanha") or ""
        elif re.search(r"\bhoje\b", txt_qm):
            dt_qm = base.get("hoje") or ""
        else:
            m_qm = re.search(r"\b(segunda|terca|quarta|quinta|sexta)\b", txt_qm)
            if m_qm:
                dt_qm = base.get("prox_" + m_qm.group(1)[:3]) or ""
        dt_busca_qm = dt_qm or base.get("hoje") or ""
        per_qm = base.get("coleta_periodo") if base.get("coleta_periodo") in ("manha", "tarde") else ""
        base["coleta_medico"] = "sem preferencia"
        base["coleta_modo"] = 1
        base["coleta_dia_semana"] = ""
        if dt_qm:
            base["coleta_data"] = dt_qm
        base["texto_ia"] = (
            '[QUALQUER MEDICO NO DIA: paciente quer saber QUAL medico tem horario. Setar med="sem preferencia", '
            f'modo=1, dt="{dt_busca_qm}" no $$$. Chame buscar_agenda AGORA com unid="{base.get("coleta_unidade")}", '
            f'med="sem preferencia", dt="{dt_busca_qm}"' + (f', per="{per_qm}"' if per_qm else '')
            + ' e mostre TODOS os medicos e horarios que a TOOL retornar. ⛔ NAO filtre por medico. '
              '⛔ NUNCA invente horarios. ⛔ NAO cite data exata antes do retorno da tool.] ' + texto_usuario
        )

    # FIX_STEPHANIE_TELE
    med_st = _norm((base.get("coleta_medico") or "") + " " + (base.get("medico_candidato_msg") or ""))
    if (re.search(r"stephanie|rugeri", med_st) and "Tatu" not in (base.get("coleta_unidade") or "")
            and _texto_ia_livre(base) and not ia_output.get("bypass_agente_humano")):
        txt_st = txt_cancel_check
        dow_st = _dow_js(base.get("coleta_data") or "")
        ds_st = (base.get("coleta_dia_semana") or "").lower()
        if not dow_st:
            if re.match(r"^seg", ds_st):
                dow_st = 1
            elif re.match(r"^ter", ds_st):
                dow_st = 2
        if not dow_st:
            if re.search(r"(?:^|\s)(segunda|seg)\b", txt_st):
                dow_st = 1
            elif re.search(r"(?:^|\s)(terca|ter)\b", txt_st):
                dow_st = 2
        per_st = ""
        if re.search(r"\bmanha\b|de manha|\bcedo\b", txt_st):
            per_st = "manha"
        elif re.search(r"\btarde\b", txt_st):
            per_st = "tarde"
        if not per_st:
            h_msg_st = re.search(r"(?:^|\s)(?:as\s+)?(\d{1,2})(?::\d{2})?\s*(?:h|hs|horas?)\b", txt_st) \
                or re.search(r"(?:^|\s)(\d{1,2}):\d{2}(?:\s|$)", txt_st)
            if h_msg_st:
                hv_st = int(h_msg_st.group(1))
                if 6 <= hv_st <= 20:
                    per_st = "manha" if hv_st < 12 else "tarde"
        if not per_st:
            per_st = base.get("coleta_periodo") if base.get("coleta_periodo") in ("manha", "tarde") else ""
        if not per_st and re.match(r"^\d{1,2}:\d{2}$", base.get("coleta_horario") or ""):
            per_st = "manha" if int(base["coleta_horario"].split(":")[0]) < 12 else "tarde"
        eh_tele_st = (dow_st == 2) or (dow_st == 1 and per_st == "manha")
        if eh_tele_st:
            ia_output["bypass_agente_humano"] = True
            intencao_rapida = "humano"
            rota_agente = 0
            motivo_humano = "Teleconsulta Dra. Stephanie"
            base["motivo_humano"] = motivo_humano
            base["texto_ia"] = (
                '[STEPHANIE TELECONSULTA → ATENDENTE: nesse dia/horario a Dra. Stephanie atende por TELECONSULTA — '
                'regra da clinica: teleconsulta agenda com atendente. Responder EXATAMENTE: "Nesse horário a Dra. '
                'Stephanie atende por teleconsulta 😊 Vou te passar para um atendente para agendar, um instante! '
                '(Presencial com ela: segunda à tarde ou quarta à tarde)" e emitir i="humano", motivo="Teleconsulta '
                'Dra. Stephanie". ⛔ NAO busque horarios. ⛔ NAO crie consulta. ⛔ NAO ofereça outros medicos.] ' + texto_usuario
            )

    # FIX_65977b: horário não verificado (nunca exibiu slot)
    sem_slots_hc = not base.get("cache_ativo") and not base.get("ultimo_dia_exibido")
    sess_conf_hc = base.get("sessao_intencao") in ("confirmacao", "execucao") or base.get("_sub_rota_agenda") == "confirmacao"
    txt_hc = txt_cancel_check
    h_msg_hc = re.search(r"(?:^|\s)(?:as\s+)?(\d{1,2})(?::\d{2})?\s*(?:h|hs|horas?)\b", txt_hc) \
        or re.search(r"(?:^|\s)(\d{1,2}):\d{2}(?:\s|$)", txt_hc)
    if (sem_slots_hc and sess_conf_hc and (h_msg_hc or (base.get("coleta_horario") or "").strip())
            and (base.get("coleta_unidade") or "").strip() and (base.get("coleta_medico") or "").strip()
            and _texto_ia_livre(base) and not ia_output.get("bypass_agente_humano") and not eh_cancel_real):
        rota_agente = 4
        base["_sub_rota_agenda"] = "navegacao"
        intencao_rapida = "agenda"
        base["texto_ia"] = (
            '[HORARIO NAO VERIFICADO: nenhum horario real foi exibido nesta conversa (cache inativo). '
            'O horario citado veio do PACIENTE — NAO confirme nem crie consulta com ele. '
            'Chame buscar_agenda AGORA com unid/med/dt/per salvos e mostre APENAS os horarios que a TOOL retornar. '
            'Se o horario desejado nao estiver na lista, diga quais existem. '
            '⛔ PROIBIDO "So para confirmar" sem slot vindo da tool. ⛔ NUNCA invente horarios.] ' + texto_usuario
        )

    # PROTEÇÃO: fluxo de agenda ativo + IA voltou triagem/0 -> preserva contexto
    if not eh_cancel_real and not eh_pergunta_ver and sessao_era_agenda and intencao_rapida == "triagem" and rota_agente == 0:
        intencao_rapida = "agenda"
        rota_agente = 3 if tem_dependente_salvo else _int(base.get("sessao_rota"))
    # PROTEÇÃO: banco como fallback só se IA não classificou nada
    elif not eh_pergunta_ver and not eh_sessao_nova and base.get("sessao_rota") and _int(base.get("sessao_rota")) != 0 and rota_agente == 0:
        rota_agente = _int(base.get("sessao_rota"))
        if base.get("sessao_intencao") and base.get("sessao_intencao") not in ("triagem", "concluido", "humano"):
            intencao_rapida = base["sessao_intencao"]
    # PROTEÇÃO EXTRA: só força rota 2 se não for cancelamento/remarcação
    elif (not eh_cancel_real and intencao_rapida not in ("remarcando", "remarcando_escolher")
          and not re.search(r"\breagend|\bremarca", texto_usuario)
          and (intencao_rapida == "agenda" or "agendar" in texto_usuario or "qualquer" in texto_usuario)):
        rota_agente = 2
        intencao_rapida = "agenda"

    # PROTEÇÃO COLETA INCOMPLETA/INTERROMPIDA
    if (not eh_cancel_real and not eh_mensagem_informativa and not eh_pergunta_ver and rota_agente == 0
            and base.get("coleta_unidade") and base.get("coleta_data") and base.get("coleta_periodo")):
        rota_agente = 2
        intencao_rapida = "agenda"

    # FIX_TRIAGEM_HANDOFF_COLETA
    if (rota_agente == 0 and base.get("sessao_intencao") == "coleta"
            and not eh_cancel_real and not eh_pergunta_ver and not eh_mensagem_informativa and not eh_sessao_nova):
        rota_agente = 2
        intencao_rapida = "coleta"
        if not base.get("coleta_unidade") and not base.get("coleta_medico"):
            base["texto_ia"] = (
                '[INICIO AGENDA: paciente quer agendar. Comece pelo P1 (para quem) e depois a unidade. '
                '⛔ IGNORE qualquer data/horario que o paciente tenha mandado antes de escolher unidade e medico — '
                'os horarios reais vem EXCLUSIVAMENTE de buscar_agenda. ⛔ NUNCA afirme disponibilidade sem chamar '
                'buscar_agenda.] ' + texto_usuario
            )
        elif base.get("coleta_unidade") and base.get("coleta_medico") and base.get("coleta_data"):
            b_per = f', per="{base["coleta_periodo"]}"' if base.get("coleta_periodo") else ""
            base["texto_ia"] = (
                f'[BUSCAR AGENDA: paciente confirmou os dados ("{texto_usuario}"). Chame buscar_agenda com '
                f'unid="{base["coleta_unidade"]}", med="{base["coleta_medico"]}", dt="{base["coleta_data"]}"{b_per}. '
                '⛔ NUNCA invente horarios — os horarios validos vem EXCLUSIVAMENTE de buscar_agenda. Mostre os '
                f'horarios retornados pela tool.] {texto_usuario}'
            )

    # FIX_COLETA_PACIENTE_IDENTIFICADO
    if (rota_agente == 2 and (base.get("cpf") or base.get("id_tisaude")) and not base.get("coleta_unidade")
            and not base.get("nome_dependente") and intencao_rapida != "remarcando"
            and "INICIO AGENDA" not in (base.get("texto_ia") or "") and "BUSCAR AGENDA" not in (base.get("texto_ia") or "")):
        txt_pci = re.sub(r"\s+", " ", re.sub(r"[.,!?;:]+", " ", txt_cancel_check)).strip()
        pacs_pci = base.get("pacientes") or []

        def _match_nome_pci(p):
            pn = _norm(p.get("nome"))
            if not pn:
                return False
            txt_pci_sp = re.sub(r"^(?:a consulta )?(?:e |eh |sera |vai ser )?(?:para|pra|pro)\s+(?:a |o )?", "", txt_pci).strip()
            return txt_pci == pn or txt_pci == pn.split(" ")[0] or txt_pci_sp == pn or txt_pci_sp == pn.split(" ")[0]

        eh_nome_pci = any(_match_nome_pci(p) for p in pacs_pci)
        eh_resposta_quem_pci = bool(re.search(r"\b(para|pra|p)\s+mim\b", txt_pci)) or bool(re.search(
            r"\b(outra pessoa|um terceiro|terceiro|filhos?|filhas?|marido|esposos?|esposas?|mae|pai|irmaos?|irmas?|"
            r"netos?|netas?|sogros?|sogras?|tios?|tias?|primos?|primas?|genro|nora)\b", txt_pci
        ))
        nome_pc_raw = "" if (eh_nome_pci or eh_resposta_quem_pci) else (base.get("nome") or "").split(" ")[0]
        nome_pc_fmt = (nome_pc_raw[0].upper() + nome_pc_raw[1:].lower()) if nome_pc_raw else ""
        if nome_pc_fmt:
            if len(pacs_pci) >= 2:
                nomes_pci = ", ".join(p.get("nome", "").strip() for p in pacs_pci if p.get("nome", "").strip())
                base["texto_ia"] = (
                    f'[PACIENTE JA IDENTIFICADO (MULTI): ha {len(pacs_pci)} cadastros neste telefone. '
                    f'NAO pergunte nome nem CPF. Pergunte EXATAMENTE: "A consulta será para {nomes_pci}? Ou para '
                    'outra pessoa? 😊" ⛔ NAO preencha d/c/n/id no $$$ ate o paciente ESCOLHER (deixe vazios neste '
                    'turno).] ' + (base.get("texto_ia") or "")
                )
            else:
                base["texto_ia"] = (
                    f'[PACIENTE JA IDENTIFICADO: nome="{nome_pc_fmt}", CPF disponivel no sistema. '
                    'NAO pergunte nome nem CPF. Pergunte: "A consulta será para você, ' + nome_pc_fmt
                    + ', ou para outra pessoa?"] ' + (base.get("texto_ia") or "")
                )

    # FIX_BUFFER_DUP_MENU
    toks = texto_usuario.strip().split()
    menu_opt = toks[0] if (len(toks) > 1 and all(t == toks[0] for t in toks)) else texto_usuario.strip()

    # FIX_LEAD_SITE
    txt_ls = txt_cancel_check
    pede_info_ls = bool(re.search(r"\binformac", txt_ls))
    do_site_ls = bool(re.search(r"estou no site|vim pelo site|site da oto", txt_ls))
    tem_acao_ls = bool(re.search(r"agendar|marcar|remarcar|cancelar|confirmar|desmarcar|encaix|valor|convenio|endereco|horario", txt_ls))
    if (rota_agente == 0 and not tem_acao_ls and (do_site_ls or (pede_info_ls and base.get("sessao_intencao") == "triagem"))
            and _texto_ia_livre(base)):
        base["texto_ia"] = (
            '[LEAD SITE: paciente chegou pelo site pedindo informacoes. Responder EXATAMENTE: "Olá! 👋\n'
            'Seja bem-vindo(a) ao atendimento automatizado da Clínica Oto-SP de Otorrinolaringologia.\n\n'
            'Eu sou o assistente virtual da clínica e estou aqui para agilizar o seu atendimento!\n'
            'Como posso ajudar você hoje? Digite o número da opção desejada ou escreva o que precisa:\n\n'
            '1️⃣ Agendar consulta\n2️⃣ Remarcar consulta\n3️⃣ Cancelar consulta\n4️⃣ Consulta pendente\n'
            '5️⃣ Troca de guias e documentos\n6️⃣ Confirmar consulta\n\nOu me pergunte sobre valores, convênios, '
            'endereços e horários de atendimento 😊" e emitir i="triagem" com d/c/n vazios. ⛔ NAO invente valores '
            'nem informacoes — se depois perguntarem, use as secoes de FAQ.] ' + texto_usuario
        )

    # FIX_DOC_HUMANO
    txt_dh = txt_cancel_check
    eh_doc_dh = bool(re.search(
        r"\breceitas?\b|\batestados?\b|\blaudos?\b|declaracao (de )?comparecimento|resultado (do |de |dos )?exame|"
        r"exame.{0,12}resultado", txt_dh
    ))
    if eh_doc_dh and rota_agente == 0 and not ia_output.get("bypass_agente_humano") and _texto_ia_livre(base):
        ia_output["bypass_agente_humano"] = True
        intencao_rapida = "humano"
        motivo_humano = "Documento: receita/atestado/laudo/resultado de exame"
        base["motivo_humano"] = motivo_humano
        base["texto_ia"] = (
            '[TRANSFERIR HUMANO: paciente precisa de documento (receita/atestado/laudo/resultado de exame) — o bot '
            'NAO emite documentos. Responder EXATAMENTE: "Claro! Vou te passar para um atendente que consegue te '
            'ajudar com isso 😊" e emitir i="humano", motivo="Documento: receita/atestado/laudo". ⛔ NAO responda '
            'FAQ. ⛔ NAO ofereça agendamento.] ' + texto_usuario
        )

    # FIX_TELE_HUMANO
    txt_tm = txt_cancel_check
    eh_tele_tm = bool(re.search(
        r"telemedicina|teleconsulta|tele consulta|tele-consulta|teleatendimento|tele atendimento|consulta online|"
        r"consulta on line|consultas online|atendimento online|videochamada|video chamada|consulta por video|"
        r"consulta remota|consulta a distancia", txt_tm
    )) or (
        bool(re.search(r"(^|\s)(online|on line|on-line|remot[ao]|por video|tele)([\s.,!?;]|$)", txt_tm))
        and not re.search(r"pag(ar|amento)|pix|cartao|boleto|reembols|\bsite\b|\blink\b", txt_tm)
    )
    neg_tele_tm = bool(re.search(r"presencial", txt_tm)) or bool(
        re.search(r"\bn(ao)?\b[^.,!?;]{0,25}(online|on line|tele|video|virtual|distancia|remot)", txt_tm)
    )
    if (eh_tele_tm and not neg_tele_tm and not eh_cancel_real and not ia_output.get("bypass_agente_humano")
            and _texto_ia_livre(base)):
        ia_output["bypass_agente_humano"] = True
        intencao_rapida = "humano"
        motivo_humano = "Telemedicina"
        base["motivo_humano"] = motivo_humano
        base["texto_ia"] = (
            '[TRANSFERIR HUMANO: paciente quer telemedicina/teleconsulta — a clinica FAZ telemedicina, mas o '
            'agendamento dela e feito por atendente. Responder EXATAMENTE: "Sim, temos telemedicina! 😊 Para '
            'agendar uma teleconsulta vou te passar para um atendente, um instante!" e emitir i="humano", '
            'motivo="Telemedicina". ⛔ NAO responda FAQ. ⛔ NAO ofereça agendamento pelo bot.] ' + texto_usuario
        )

    # FIX_REEMBOLSO_HUMANO
    txt_rb = txt_cancel_check
    eh_reemb_rb = bool(re.search(r"reembols|nota fiscal|\brecibos?\b", txt_rb))
    if eh_reemb_rb and rota_agente == 0 and not ia_output.get("bypass_agente_humano") and _texto_ia_livre(base):
        ia_output["bypass_agente_humano"] = True
        intencao_rapida = "humano"
        motivo_humano = "Reembolso/nota fiscal"
        base["motivo_humano"] = motivo_humano
        base["texto_ia"] = (
            '[TRANSFERIR HUMANO: paciente quer reembolso/nota fiscal/recibo — assunto de atendente. Responder '
            'EXATAMENTE: "Claro! Sobre reembolso e nota fiscal, vou te passar para um atendente que consegue te '
            'ajudar com isso 😊" e emitir i="humano", motivo="Reembolso/nota fiscal". ⛔ NAO responda FAQ. '
            '⛔ NAO ofereça particular.] ' + texto_usuario
        )

    # FIX_REMARCA_MULTI
    txt_rm = txt_cancel_check
    eh_remarca_rm = bool(re.search(r"\bremarca|\breagend", txt_rm)) and not re.search(r"\bcancel|\bdesmarc", txt_rm)
    eh_outros_rm = bool(re.search(
        r"\bmarido\b|\besposa\b|\besposo\b|\bfilhas?\b|\bfilhos?\b|\bmae\b|\bpai\b|\bavos?\b|\bavo\b|\birmaos?\b|"
        r"\birmas?\b|\bnetos?\b|\bnetas?\b|\bsogras?\b|\bsogros?\b|\btias?\b|\btios?\b|\bprimas?\b|\bprimos?\b|"
        r"outra pessoa|\bnossas?\b|\bconsultas\b", txt_rm
    ))
    if eh_remarca_rm and eh_outros_rm and not ia_output.get("bypass_agente_humano") and _texto_ia_livre(base):
        ia_output["bypass_agente_humano"] = True
        intencao_rapida = "humano"
        motivo_humano = "Remarcacao multipla/terceiro"
        base["motivo_humano"] = motivo_humano
        base["texto_ia"] = (
            '[TRANSFERIR HUMANO: paciente quer remarcar consulta de outra pessoa ou de varias pessoas — o bot so '
            'remarca a consulta do proprio titular do telefone. Responder EXATAMENTE: "Claro! Para remarcar '
            'consulta de outra pessoa ou de mais de uma pessoa, vou te passar para um atendente que resolve tudo '
            'de uma vez, rapidinho! 😊" e emitir i="humano", motivo="Remarcacao multipla/terceiro". ⛔ NAO inicie '
            'remarcacao. ⛔ NAO ofereça agendar consulta nova.] ' + texto_usuario
        )

    # FIX_65739: agendamento múltiplo
    txt_ma = txt_cancel_check
    idx_tb_ma = _search_index(r"(tambem|e tambem)\s+(gostaria|queria|quero|preciso)?\s*(de\s+)?(agendar|marcar)", txt_ma)
    pedido_duplo_ma = (
        (idx_tb_ma > 0 and bool(re.search(r"(agendar|marcar|consulta|retorno)", txt_ma[:idx_tb_ma])))
        or bool(re.search(r"\bduas consultas\b|\bdois horarios\b|\b(para|pra) mim e (para|pra|pro)\b", txt_ma))
        or (bool(re.search(r"(agendar|marcar)", txt_ma))
            and bool(re.search(r"\be (para|pra|pro)\s+(o |a )?(meu|minha)\s+(filho|filha|esposa|esposo|marido|mulher|mae|pai)\b", txt_ma)))
    )
    dois_cpfs_ma = (
        (rota_agente in (2, 3) or _int(base.get("sessao_rota")) in (2, 3))
        and len(re.findall(r"\d{3}\.?\d{3}\.?\d{3}-?\d{2}", texto_usuario)) >= 2
    )
    if (pedido_duplo_ma or dois_cpfs_ma) and not ia_output.get("bypass_agente_humano") and _texto_ia_livre(base) and not eh_cancel_real:
        rota_agente = 5
        intencao_rapida = "humano"
        ia_output["bypass_agente_humano"] = True
        motivo_humano = "Agendamento multiplo (2+ pacientes)"
        base["motivo_humano"] = motivo_humano
        base["texto_ia"] = (
            '[TRANSFERIR HUMANO: paciente quer agendar consultas para MAIS DE UMA pessoa — o fluxo automatico '
            'agenda uma por vez. Responder EXATAMENTE: "Para agendar consultas para mais de uma pessoa, vou te '
            'passar para um atendente que resolve tudo de uma vez, rapidinho! 😊" e emitir i="humano", '
            'motivo="Agendamento multiplo (2+ pacientes)". ⛔ NAO inicie coleta. ⛔ NAO pergunte para quem e a '
            'consulta.] ' + texto_usuario
        )

    # FIX_CANCELAR_LEMBRETE
    txt_cl = txt_cancel_check.strip()
    ctx_puro_cl = not base.get("sessao_intencao") or base.get("sessao_intencao") in ("triagem", "concluido")
    if (re.match(r"^\W*(cancelar|cancela|desmarcar)\W*$", txt_cl) and ctx_puro_cl
            and _texto_ia_livre(base) and not ia_output.get("bypass_agente_humano")):
        rota_agente = 1
        intencao_rapida = "cancelando"
        base["texto_ia"] = (
            '[CANCELAR LEMBRETE: paciente respondeu CANCELAR ao lembrete de consulta. '
            '⛔ NAO pergunte "deseja cancelar?". ⛔ NAO pergunte motivo. Se houver 1 titular, chame cancelar_consulta '
            'AGORA; com 1 consulta na lista, mostre-a e faca UMA confirmacao: "Encontrei sua consulta de <dt> às '
            '<hr> com Dr(a). <md>. Confirma o cancelamento? 😊". Apos o sim, chame cancelar_consulta(cpf, id, '
            'motivo="") DIRETO. Com 2+ consultas, liste e pergunte o numero antes.] ' + texto_usuario
        )

    # FIX_CONV_RECUSADO_TRIAGEM
    txt_cr = txt_cancel_check
    hit_cr = next((nome for (rx, nome) in _PLANOS_CR if rx.search(txt_cr)), None)
    rota_cr = rota_agente in (0, 2, 3, 4) or _int(base.get("sessao_rota")) in (2, 3, 4)
    if hit_cr and rota_cr and not ia_output.get("bypass_agente_humano") and _texto_ia_livre(base):
        if hit_cr in ("Amil", "Medserv"):
            resp_cr = (
                'A Amil está em processo de credenciamento com a gente 😊 Por enquanto ainda não consigo agendar '
                'por ela — vou te passar para um atendente para te orientar!'
            ) if hit_cr == "Amil" else (
                f'Infelizmente não atendemos pelo {hit_cr} 😔 Vou te passar para um atendente para te orientar, '
                'um instante! 😊'
            )
            ia_output["bypass_agente_humano"] = True
            intencao_rapida = "humano"
            motivo_humano = f"Convenio nao atendido: {hit_cr}"
            base["motivo_humano"] = motivo_humano
            base["texto_ia"] = (
                f'[CONVENIO NAO ATENDIDO → ATENDENTE: paciente citou "{hit_cr}". REGRA DA CLINICA: credenciamento '
                f'em andamento — NAO oferecer particular. Responder EXATAMENTE: "{resp_cr}" e emitir i="humano", '
                f'motivo="Convenio nao atendido: {hit_cr}".] ' + texto_usuario
            )
        else:
            base["coleta_convenio"] = "PART?"
            base["texto_ia"] = (
                f'[CONVENIO NAO ATENDIDO → OFERTA PARTICULAR: paciente citou "{hit_cr}" (nao atendido). Setar '
                'conv="PART?" no $$$. Responder EXATAMENTE: "Infelizmente não atendemos pelo ' + hit_cr + ' 😔 Mas '
                'podemos te atender como *Particular*:\n✔️ Incluso 1 retorno em até 30 dias\n💰 R$ 600,00 no débito '
                'ou crédito à vista\n💰 R$ 570,00 via PIX (5% de desconto)\nQuer agendar como particular? 😊 Se '
                'preferir, te passo para um atendente!" ⛔ NAO transfira NESTE turno. ⛔ NUNCA pule os preços. '
                '⛔ NAO chame buscar_agenda. ⛔ NAO use o FALLBACK.] ' + texto_usuario
            )

    # FIX_TRIAGEM_MENU_GUARD
    if rota_agente == 0 and (base.get("sessao_intencao") == "triagem" or not base.get("sessao_intencao")) \
            and not base.get("coleta_unidade") and not base.get("coleta_medico"):
        txt_tmg = menu_opt
        if re.match(r"^\d{1,2}$", txt_tmg) and (int(txt_tmg) < 1 or int(txt_tmg) > 6):
            base["texto_ia"] = (
                f'[OPCAO INVALIDA TRIAGEM: Paciente digitou "{txt_tmg}" mas menu so tem opcoes 1-6. Responder '
                'EXATAMENTE: "Desculpe, não entendi. Por favor, escolha uma opção:\n\n1️⃣ Agendar consulta\n'
                '2️⃣ Remarcar consulta\n3️⃣ Cancelar consulta\n4️⃣ Consulta pendente\n5️⃣ Troca de guias e '
                'documentos\n6️⃣ Confirmar consulta" NAO peca CPF. NAO peca nome. Aguarde resposta.] ' + texto_usuario
            )

    # FIX_VER_ESCOLHER_TITULAR
    if base.get("sessao_intencao") == "ver_escolher":
        pacs_ve = base.get("pacientes") or []
        sel_ve = _to_int_or_none(texto_usuario.strip())
        if sel_ve is not None and 1 <= sel_ve <= len(pacs_ve):
            p_sel = pacs_ve[sel_ve - 1]
            intencao_rapida = "ver"
            base["texto_ia"] = (
                f'[VER CONSULTAS: titular escolhido = {p_sel.get("nome", "")} (id {p_sel.get("id_tisaude", "")}). '
                '⛔ NAO peca CPF nem nome. Chame consultar_minhas_consultas AGORA com esse id e liste as consultas '
                'pendentes. i="ver".] ' + texto_usuario
            )
        else:
            intencao_rapida = "ver_escolher"
            menu_ve = "\n".join(f'{i + 1}. {p.get("nome") or f"Titular {i + 1}"}' for i, p in enumerate(pacs_ve))
            base["texto_ia"] = (
                f'[VER ESCOLHER TITULAR INVALIDO: paciente digitou "{texto_usuario.strip()}". Responder EXATAMENTE: '
                f'"Não entendi. De quem você quer ver as consultas?\n\n{menu_ve}"]'
            )

    # HORARIO AMBIGUO (sem contexto de agendamento ativo)
    if (rota_agente == 0 and base.get("sessao_intencao") not in _SESSOES_VER_ESCOLHER_EXCLUDE
            and re.match(r"^\d{1,2}[h:]\d{0,2}$", texto_usuario.strip())):
        base["texto_ia"] = (
            f'[HORARIO AMBIGUO: paciente enviou apenas um horário ("{texto_usuario.strip()}") sem contexto de '
            'agendamento ativo. ⛔ NAO agende. ⛔ NAO invente data. ⛔ NAO chame nenhuma tool. Responder EXATAMENTE: '
            f'"Recebi \'{texto_usuario.strip()}\', mas não entendi o contexto. 😊 Você quer:\n• Agendar uma consulta?'
            '\n• Ver agendamentos?\n• Outra coisa?"] '
        )

    # PROTEÇÃO TERCEIRO
    if (_int(base.get("sessao_rota")) == 3 and base.get("coleta_terceiro")
            and not eh_mensagem_informativa and not eh_cancel_real and not eh_pergunta_ver):
        rota_agente = 3
        if intencao_rapida == "triagem":
            intencao_rapida = "coleta"

    # CORREÇÃO FINAL: dependente salvo + fluxo de agenda ativo
    if (tem_dependente_salvo or eh_texto_terceiro) and rota_agente == 2 and not eh_sessao_nova:
        rota_agente = 3

    return ResultadoIntake(
        base=base,
        intencao_rapida=intencao_rapida,
        rota_agente=rota_agente,
        telefone=telefone,
        texto_usuario=texto_usuario,
        ia_output=ia_output,
        ia_rota_original=ia_rota_original,
        eh_cancelamento=eh_cancelamento,
        eh_cancel_real=eh_cancel_real,
        tem_dependente_salvo=tem_dependente_salvo,
        eh_texto_terceiro=eh_texto_terceiro,
        eh_mensagem_informativa=eh_mensagem_informativa,
        eh_sessao_nova=eh_sessao_nova,
        eh_pergunta_ver=eh_pergunta_ver,
        eh_saudacao_pura=eh_saudacao_pura,
        sessao_era_agenda=sessao_era_agenda,
        sessao_era_agenda_com_coleta=sessao_era_agenda_com_coleta,
        tem_identidade_em_andamento=tem_identidade_em_andamento,
        tem_terceiro_completo=tem_terceiro_completo,
        menu_opt=menu_opt,
        motivo_humano=motivo_humano,
    )


def _int(v, default=0) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _to_int_or_none(s: str):
    try:
        return int(s)
    except ValueError:
        return None


def _search_index(pattern: str, s: str) -> int:
    m = re.search(pattern, s)
    return m.start() if m else -1


# ============================================================================
# PARTE 2 (linhas 737-1090 do JS): coleta de identidade
# ============================================================================

_KEYWORDS_NOME_MD_RE = re.compile(
    r"\b(meu nome e|meu nome é|me chamo|sou o|sou a|sou|nome completo|nome|cpf|data de nascimento|"
    r"nascimento|nascido em|nasci em|nascida em|email|e-mail|segue|seguem|meus dados|dados)\b",
    re.IGNORECASE,
)
_RUIM_NOME_MD_RE = re.compile(
    r"\b(nao|não|sim|tenho|sem|quero|queria|gostaria|agendar|marcar|remarcar|consulta|cancelar|pular|"
    r"opcional|dia|tarde|noite|manha|manhã|ola|olá|oi|bom|boa|obrigado|obrigada|valeu|ok|por favor|pfv|favor)\b",
    re.IGNORECASE,
)
_TOKEN_NOME_MD_RE = re.compile(r"^[a-zà-ÿ]+$", re.IGNORECASE)
_EMAIL_RE = re.compile(r"[\w.+\-]+@[\w\-]+\.[\w.\-]{2,}")

_TERCEIRO_PURO_RE = re.compile(
    r"^\W*(e |eh |vai ser |sera )?((para|pra|pro)\s+)?(o |a )?(meu |minha )?(outra pessoa|um terceiro|terceiro|"
    r"filho|filha|esposo|esposa|marido|mae|pai|irmao|irma|neto|neta|sogro|sogra|tio|tia|primo|prima|genro|nora)\W*$"
)


def _parse_data_nascimento(txt: str):
    """dd/mm/aaaa (com - . espaco) ou ddmmaaaa colado — data real, nao-futura, <=120 anos.
    Retorna (data_formatada, texto_casado) ou (None, None)."""
    m = re.search(r"\b(\d{1,2})[/\-.\s]+(\d{1,2})[/\-.\s]+(\d{2,4})\b", txt)
    if not m:
        m = re.search(r"\b(\d{2})(\d{2})(\d{4})\b", txt)
    if not m:
        return None, None
    dd, mm, yy = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if len(m.group(3)) == 2:
        yy += 1900 if yy > 26 else 2000
    try:
        dt = datetime(yy, mm, dd)
    except ValueError:
        return None, None
    hoje = datetime.now()
    if dt < hoje and yy >= hoje.year - 120:
        return f"{dd:02d}/{mm:02d}/{yy}", m.group(0)
    return None, None


def _extrair_cpf_md(txt: str, telefone: str):
    """Retorna (cpf_valido, texto_casado, cpf_invalido_encontrado)."""
    tel_digits = re.sub(r"\D", "", telefone or "")
    cands = re.findall(r"[\d.\-]{11,14}", txt) + re.findall(r"\d[\d.\-\s]{9,17}\d", txt)
    cpf_invalido = ""
    for cand in cands:
        dig = re.sub(r"\D", "", cand)
        if len(dig) != 11:
            continue
        if re.fullmatch(r"(\d)\1{10}", dig):
            continue
        if tel_digits and tel_digits.endswith(dig[-8:]):
            continue
        if _cpf_digitos_validos(dig):
            return dig, cand, ""
        cpf_invalido = dig
    return "", "", cpf_invalido


def _extrair_nome_md(txt: str) -> str | None:
    limpo = _KEYWORDS_NOME_MD_RE.sub(" ", txt)
    limpo = re.sub(r"[\d/\-.:,;()*\"']+", " ", limpo)
    limpo = re.sub(r"\s+", " ", limpo).strip()
    if _RUIM_NOME_MD_RE.search(limpo):
        return None
    palavras = [w for w in limpo.split(" ") if _TOKEN_NOME_MD_RE.match(w)]
    if 2 <= len(palavras) <= 8 and sum(1 for w in palavras if len(w) >= 2) >= 2:
        return " ".join(palavras).upper()
    return None


@dataclass
class ResultadoIdentidade:
    base: dict
    intencao_rapida: str
    rota_agente: int
    motivo_humano: str | None = None


def processar_identidade(
    base: dict,
    texto_usuario: str,
    intencao_rapida: str,
    rota_agente: int,
    ia_output: dict,
    eh_cancel_real: bool,
    eh_mensagem_informativa: bool,
    motivo_humano: str | None = None,
) -> ResultadoIdentidade:
    txt_norm = _norm(texto_usuario)

    # FIX_MULTI_DADOS (+ FIX_CPF_INVALIDO_AVISO): nome, CPF, nascimento e email numa mensagem só.
    pacs_md = base.get("pacientes") or []
    eh_0pac_md = len(pacs_md) == 0
    eh_terc_md = base.get("coleta_terceiro") == "true"
    cpf_falta_md = not _cpf_digitos_validos(re.sub(r"\D", "", base.get("cpf_dependente") or ""))
    incompleto_md = (
        not (base.get("nome_dependente") or "").strip()
        or cpf_falta_md
        or not (base.get("nascimento_dependente") or "").strip()
    )
    if (eh_0pac_md or eh_terc_md) and incompleto_md and not eh_cancel_real and not eh_mensagem_informativa:
        det_md: dict = {}
        txt_md = texto_usuario
        cpf_invalido_md = ""
        if cpf_falta_md:
            cpf_ok, cpf_matched, cpf_invalido_md = _extrair_cpf_md(txt_md, base.get("telefone", ""))
            if cpf_ok:
                det_md["c"] = cpf_ok
                txt_md = txt_md.replace(cpf_matched, " ")
        if not (base.get("nascimento_dependente") or "").strip():
            nasc, matched = _parse_data_nascimento(txt_md)
            if nasc:
                det_md["n"] = nasc
                txt_md = txt_md.replace(matched, " ")
        if not (base.get("coleta_email") or "").strip():
            m_email = _EMAIL_RE.search(txt_md)
            if m_email:
                det_md["email"] = m_email.group(0)
                txt_md = txt_md.replace(m_email.group(0), " ")
        if not (base.get("nome_dependente") or "").strip() and (det_md.get("c") or det_md.get("n") or cpf_invalido_md):
            nome_md = _extrair_nome_md(txt_md)
            if nome_md:
                det_md["d"] = nome_md

        sess_coleta_md = base.get("sessao_intencao") == "coleta" or _int(base.get("sessao_rota")) in (2, 3)
        if (det_md.get("c") or det_md.get("n") or det_md.get("d") or det_md.get("email") or cpf_invalido_md) \
                and (sess_coleta_md or det_md.get("c")):
            if det_md.get("d"):
                base["nome_dependente"] = det_md["d"]
            if det_md.get("c"):
                base["cpf_dependente"] = det_md["c"]
            if det_md.get("n"):
                base["nascimento_dependente"] = det_md["n"]
            if det_md.get("email"):
                base["coleta_email"] = det_md["email"]
            base["_cad_det"] = det_md
            rota_agente = 3 if eh_terc_md else 2
            if intencao_rapida == "triagem" or not intencao_rapida:
                intencao_rapida = "coleta"
            if _texto_ia_livre(base):
                falta_md = []
                if not (base.get("nome_dependente") or "").strip():
                    falta_md.append("nome completo")
                if not _cpf_digitos_validos(re.sub(r"\D", "", base.get("cpf_dependente") or "")):
                    falta_md.append("CPF")
                if not (base.get("nascimento_dependente") or "").strip():
                    falta_md.append("data de nascimento")
                rec_md = ", ".join(filter(None, [
                    det_md.get("d") and "nome", det_md.get("c") and "CPF",
                    det_md.get("n") and "nascimento", det_md.get("email") and "email",
                ]))
                ddl_md = (
                    (f' d="{det_md["d"]}"' if det_md.get("d") else "")
                    + (f' c="{det_md["c"]}"' if det_md.get("c") else "")
                    + (f' n="{det_md["n"]}"' if det_md.get("n") else "")
                    + (f' email="{det_md["email"]}"' if det_md.get("email") else "")
                )
                if falta_md and cpf_invalido_md:
                    cf_cpf_md = _int(base.get("coleta_conv_fail"))
                    if cf_cpf_md >= 1:
                        ia_output["bypass_agente_humano"] = True
                        intencao_rapida = "humano"
                        motivo_humano = f"CPF invalido 2x na coleta ({cpf_invalido_md})"
                        base["motivo_humano"] = motivo_humano
                        base["texto_ia"] = (
                            '[CPF INVALIDO 2X → ATENDENTE: segunda tentativa de CPF que nao confere nos digitos '
                            'verificadores. Responder EXATAMENTE: "O CPF não conferiu de novo 😔 Vou te passar para '
                            'um atendente para te ajudar com o cadastro!" e emitir i="humano", motivo="CPF invalido '
                            '2x".] ' + texto_usuario
                        )
                    else:
                        base["texto_ia"] = (
                            f'[CPF INVALIDO: "{cpf_invalido_md}" reprova nos digitos verificadores (typo provavel '
                            '— o TiSaude recusaria).'
                            + (f' Demais dados ({rec_md}) JA SALVOS no sistema — copie EXATAMENTE no $$$:{ddl_md}.' if rec_md else '')
                            + ' ⛔ NAO salve esse CPF — deixe c="" no $$$. Setar cf=1 no $$$. Responder EXATAMENTE: '
                              '"Hmm, o CPF não conferiu 🤔 Pode ver se digitou os 11 números certinho e me enviar de '
                              'novo? 😊"] ' + texto_usuario
                        )
                elif falta_md:
                    base["texto_ia"] = (
                        f'[DADOS CADASTRO DETECTADOS ({rec_md}) — JA SALVOS no sistema. Copie EXATAMENTE no '
                        f'$$$:{ddl_md}. ⛔ NAO repergunte o que ja veio. Responder EXATAMENTE: "Obrigado! Só faltou: '
                        + " e ".join(falta_md) + '. Pode me enviar? 😊"] ' + texto_usuario
                    )
                else:
                    d_full_md = (base.get("nome_dependente") or "").strip()
                    c_full_md = (base.get("cpf_dependente") or "").strip()
                    n_full_md = (base.get("nascimento_dependente") or "").strip()
                    prox_md = (
                        'Responder EXATAMENTE: "Perfeito, dados anotados! 😊\nTemos dois endereços de atendimento, '
                        'qual a melhor unidade para você?\nDigite o número correspondente:\n1️⃣ Vila Olímpia\n'
                        '2️⃣ Tatuapé"'
                    ) if not (base.get("coleta_unidade") or "").strip() else (
                        'Identidade completa — va ao proximo passo da coleta pendente. ⛔ NAO repergunte '
                        'nome/CPF/nascimento.'
                    )
                    base["texto_ia"] = (
                        f'[DADOS CADASTRO COMPLETOS — JA SALVOS no sistema. Copie EXATAMENTE no $$$: '
                        f'd="{d_full_md}" c="{c_full_md}" n="{n_full_md}"'
                        + (f' email="{det_md["email"]}"' if det_md.get("email") else "")
                        + (' t=true' if eh_terc_md else "")
                        + f'. ⛔ NAO pergunte email. {prox_md}] ' + texto_usuario
                    )

    # FIX_PEDIR_IDENTIDADE_COMPLETA (58070)
    txt_pi = txt_norm
    pacs_pi = base.get("pacientes") or []
    sess_coleta_pi = base.get("sessao_intencao") == "coleta" or _int(base.get("sessao_rota")) in (2, 3) or rota_agente in (2, 3)
    ident_vazia_pi = (
        not (base.get("nome_dependente") or "").strip()
        and not (base.get("cpf_dependente") or "").strip()
        and not (base.get("nascimento_dependente") or "").strip()
    )
    eh_para_mim_pi = bool(re.search(r"\b(para|pra|p)\s+mim\b", txt_pi)) and len(pacs_pi) == 0
    eh_terceiro_pi = bool(_TERCEIRO_PURO_RE.match(txt_pi))
    if (((eh_para_mim_pi and ident_vazia_pi) or eh_terceiro_pi) and sess_coleta_pi
            and not eh_cancel_real and not eh_mensagem_informativa
            and not ia_output.get("bypass_agente_humano") and _texto_ia_livre(base)):
        rota_agente = 3 if eh_terceiro_pi else 2
        if intencao_rapida == "triagem" or not intencao_rapida:
            intencao_rapida = "coleta"
        if eh_terceiro_pi:
            base["nome_dependente"] = ""
            base["cpf_dependente"] = ""
            base["nascimento_dependente"] = ""
            base["coleta_terceiro"] = "true"
            base["_clear_pm"] = {**(base.get("_clear_pm") or {}), "d": 1, "c": 1, "n": 1}
            base["texto_ia"] = (
                '[COLETA IDENTIDADE TERCEIRO: consulta e para outra pessoa. Copie EXATAMENTE no $$$: t=true, d="", '
                'c="", n="" (dados anteriores NAO valem para outra pessoa). Responder EXATAMENTE: "Certo! Para o '
                'cadastro de quem vai se consultar, preciso de:\n👤 Nome completo\n🔢 CPF\n🎂 Data de nascimento\n'
                'Pode me enviar? 😊" ⛔ Os 3 itens sao OBRIGATORIOS na resposta — NUNCA omita o nome completo.] ' + texto_usuario
            )
        else:
            base["texto_ia"] = (
                '[COLETA IDENTIDADE: paciente confirmou que a consulta e para ele mesmo. Setar t=false no $$$ '
                '(mantenha unid/med/dt que vierem na msg). Responder EXATAMENTE: "Perfeito! Para eu localizar ou '
                'criar seu cadastro aqui na clínica, preciso de três dadinhos 😊\n👤 Nome completo\n🔢 CPF\n'
                '🎂 Data de nascimento\nPode me enviar?" ⛔ Os 3 itens sao OBRIGATORIOS na resposta — NUNCA omita o '
                'nome completo. ⛔ NAO pergunte unidade agora.] ' + texto_usuario
            )

    # FIX_58842: resposta é nome de paciente cadastrado (lookup determinístico)
    txt_qc = re.sub(r"\s+", " ", re.sub(r"[.,!?;:]+", " ", txt_norm)).strip()
    pacs_qc = base.get("pacientes") or []
    sess_coleta_qc = base.get("sessao_intencao") == "coleta" or _int(base.get("sessao_rota")) in (2, 3) or rota_agente in (2, 3)
    quem_vazio_qc = not (base.get("nome_dependente") or "").strip() and not (base.get("cpf_dependente") or "").strip()
    if (sess_coleta_qc and quem_vazio_qc and txt_qc and pacs_qc
            and not ia_output.get("bypass_agente_humano") and _texto_ia_livre(base)):
        txt_qc_sp = re.sub(r"^(?:a consulta )?(?:e |eh |sera |vai ser )?(?:para|pra|pro)\s+(?:a |o )?", "", txt_qc).strip()

        def _match_qc(p):
            pn = _norm(p.get("nome"))
            if not pn:
                return False
            pn_toks = pn.split(" ")
            if txt_qc == pn or txt_qc == pn_toks[0] or txt_qc_sp == pn or txt_qc_sp == pn_toks[0]:
                return True
            for cand in (txt_qc, txt_qc_sp):
                m_toks = [t for t in cand.split(" ") if len(t) >= 2]
                if len(m_toks) >= 2 and m_toks[0] == pn_toks[0] and all(t in pn_toks for t in m_toks):
                    return True
            return False

        matches_qc = [p for p in pacs_qc if _match_qc(p)]
        if len(matches_qc) == 1:
            p_qc = matches_qc[0]
            base["nome_dependente"] = p_qc.get("nome") or ""
            base["cpf_dependente"] = str(p_qc.get("cpf") or "")
            base["nascimento_dependente"] = p_qc.get("nascimento") or ""
            base["coleta_id_tisaude"] = str(p_qc.get("id_tisaude") or "")
            base["coleta_terceiro"] = ""
            rota_agente = 2
            intencao_rapida = "coleta"
            dd_qc = (
                f't=false, d="{base["nome_dependente"]}", c="{base["cpf_dependente"]}", '
                f'n="{base["nascimento_dependente"]}", id="{base["coleta_id_tisaude"]}"'
            )
            nome_qc = p_qc.get("nome") or ""
            if not base["nascimento_dependente"]:
                base["texto_ia"] = (
                    f'[QUEM CONFIRMADO LOOKUP: consulta para {nome_qc} (cadastrado). Copie EXATAMENTE no $$$: '
                    f'{dd_qc}. Responder EXATAMENTE: "Perfeito! Consulta para {nome_qc} 😊 Só falta a data de '
                    'nascimento — pode me enviar? (dia/mês/ano)" ⛔ NAO peça CPF.] ' + texto_usuario
                )
            elif not base.get("coleta_unidade"):
                base["texto_ia"] = (
                    f'[QUEM CONFIRMADO LOOKUP: consulta para {nome_qc} (cadastrado). Copie EXATAMENTE no $$$: '
                    f'{dd_qc}. Responder EXATAMENTE: "Perfeito! Consulta para {nome_qc} 😊\nTemos dois endereços de '
                    'atendimento, qual a melhor unidade para você?\nDigite o número correspondente:\n\n'
                    '1️⃣ Vila Olímpia\n2️⃣ Tatuapé" ⛔ NAO peça CPF nem nascimento.] ' + texto_usuario
                )
            else:
                base["texto_ia"] = (
                    f'[QUEM CONFIRMADO LOOKUP: consulta para {nome_qc} (cadastrado, unidade ja salva). Copie '
                    f'EXATAMENTE no $$$: {dd_qc}. Responder EXATAMENTE: "Perfeito! Consulta para {nome_qc} 😊\n'
                    'Com qual médico você prefere?\nDigite o número ou escreva:\n\n1️⃣ Primeiro horário disponível\n'
                    '2️⃣ Escolher especialista\n3️⃣ Já tenho médico de preferência" ⛔ NAO peça CPF nem nascimento.] '
                    + texto_usuario
                )

    # FIX_IDENTIDADE_RESIDUAL (58245, loop "para mim")
    txt_ir = txt_norm
    pacs_ir = base.get("pacientes") or []
    d_ir = (base.get("nome_dependente") or "").strip()
    c_ir = re.sub(r"\D", "", base.get("cpf_dependente") or "")
    n_ir = (base.get("nascimento_dependente") or "").strip()
    dv_ok_ir = _cpf_digitos_validos(c_ir)
    sess_ir = base.get("sessao_intencao") == "coleta" or _int(base.get("sessao_rota")) in (2, 3) or rota_agente in (2, 3)
    if (re.search(r"\b(para|pra|p)\s+mim\b", txt_ir) and len(pacs_ir) == 0
            and d_ir and dv_ok_ir and n_ir and base.get("coleta_terceiro") != "true"
            and sess_ir and not eh_cancel_real and not eh_mensagem_informativa
            and not ia_output.get("bypass_agente_humano") and _texto_ia_livre(base)):
        rota_agente = 2
        if intencao_rapida == "triagem" or not intencao_rapida:
            intencao_rapida = "coleta"
        prox_ir = (
            f'Responder EXATAMENTE: "Perfeito! Consulta para {d_ir} 😊\nTemos dois endereços de atendimento, qual a '
            'melhor unidade para você?\nDigite o número correspondente:\n1️⃣ Vila Olímpia\n2️⃣ Tatuapé"'
        ) if not (base.get("coleta_unidade") or "").strip() else (
            f'Confirme brevemente ("Perfeito! Consulta para {d_ir} 😊") e siga o proximo passo da coleta pendente.'
        )
        base["texto_ia"] = (
            f'[QUEM CONFIRMADO RESIDUAL: este WhatsApp ja tem cadastro coletado — d="{d_ir}" c="{c_ir}" n="{n_ir}". '
            f'Paciente disse "para mim" → identidade RESOLVIDA. Copie EXATAMENTE no $$$: t=false, d="{d_ir}", '
            f'c="{c_ir}", n="{n_ir}". {prox_ir} ⛔ NAO peça nome/CPF/nascimento de novo. ⛔ NAO pergunte "para você ou '
            'outra pessoa".] ' + texto_usuario
        )

    # FIX_EXECUCAO_SEM_NASC (58382)
    eh_exec_nb = base.get("sessao_intencao") == "execucao" or intencao_rapida == "execucao"
    pacs_nb = base.get("pacientes") or []
    if (eh_exec_nb and pacs_nb and base.get("coleta_terceiro") != "true"
            and not (base.get("nascimento_dependente") or "").strip()
            and not ia_output.get("bypass_agente_humano") and _texto_ia_livre(base)):
        nasc_nb, _ = _parse_data_nascimento(texto_usuario)
        if nasc_nb:
            base["nascimento_dependente"] = nasc_nb
            base["_cad_det"] = {**(base.get("_cad_det") or {}), "n": nasc_nb}
            base["texto_ia"] = (
                f'[NASC RECEBIDO: data de nascimento {nasc_nb} JA SALVA no sistema. Copie n="{nasc_nb}" no $$$ e '
                'PROSSIGA a criacao: chame criar_consulta AGORA com todos os dados salvos (unid/med/dt/h/conv). '
                '⛔ NAO repergunte nada.] ' + texto_usuario
            )
        else:
            m_mail_nb = _EMAIL_RE.search(texto_usuario)
            base["texto_ia"] = (
                '[FALTA NASCIMENTO P/ CRIAR: o cadastro deste paciente NAO tem data de nascimento e criar_consulta '
                'FALHA sem ela. '
                + (f'A msg trouxe o email {m_mail_nb.group(0)} — salve email="{m_mail_nb.group(0)}" no $$$. ' if m_mail_nb else '')
                + '⛔ NAO chame criar_consulta ainda. Responder EXATAMENTE: "Só falta sua data de nascimento para '
                  'concluir o agendamento 😊 Pode me enviar? (dia/mês/ano)"] ' + texto_usuario
            )

    # FIX_TERCEIRO_PEDIR_NASCIMENTO (52946)
    if (base.get("coleta_terceiro") == "true" and (base.get("nome_dependente") or "").strip()
            and not (base.get("nascimento_dependente") or "").strip() and not eh_mensagem_informativa):
        digitos_cpf = re.sub(r"\D", "", texto_usuario or "")
        cpf_vazio = not (base.get("cpf_dependente") or "").strip()
        if cpf_vazio and len(digitos_cpf) == 11:
            nome_tpn = (base.get("nome_dependente") or "o paciente").strip()
            base["cpf_dependente"] = digitos_cpf
            rota_agente = 3
            if intencao_rapida == "triagem":
                intencao_rapida = "coleta"
            base["texto_ia"] = (
                f'[COLETA TERCEIRO - PEDIR NASCIMENTO: paciente informou o CPF de {nome_tpn}. Salve '
                f'c="{digitos_cpf}", d="{nome_tpn}", t=true no $$$. AGORA pergunte EXATAMENTE: "Qual a data de '
                f'nascimento de {nome_tpn}? (dia/mês/ano) 😊". ⛔ NAO pergunte unidade. ⛔ NAO avance para P2 sem o '
                'nascimento.]'
            )

    # FIX_CPF_NASCIMENTO_TROCADOS
    if rota_agente in (2, 3) and (base.get("nome_dependente") or "").strip() and _texto_ia_livre(base):
        msg_cn = texto_usuario.strip()
        dig_cn = re.sub(r"\D", "", msg_cn)
        parece_cpf_cn = bool(re.fullmatch(r"\d{11}", msg_cn))
        parece_data_cn = len(dig_cn) > 0 and len(dig_cn) != 11 and (
            bool(re.search(r"\d{1,2}\D{1,3}\d{1,2}\D{1,3}\d{2,4}", msg_cn)) or len(dig_cn) == 8
        )
        if not (base.get("cpf_dependente") or "").strip() and not (base.get("nascimento_dependente") or "").strip() and parece_data_cn:
            base["nascimento_dependente"] = msg_cn
            base["texto_ia"] = (
                f'[CPF/NASCIMENTO TROCADOS: isso parece a data de nascimento, nao o CPF. Setar n="{msg_cn}", c="" '
                'no $$$. Responder EXATAMENTE: "Ah, acho que essa é sua data de nascimento! Já anotei aqui. 😊 '
                'Agora me confirma o seu CPF, por favor?" NAO peça nascimento de novo.] ' + texto_usuario
            )
        elif ((base.get("cpf_dependente") or "").strip() and not (base.get("nascimento_dependente") or "").strip()
              and parece_cpf_cn and len(re.sub(r"\D", "", base.get("cpf_dependente") or "")) != 11):
            base["cpf_dependente"] = dig_cn
            base["texto_ia"] = (
                f'[CPF/NASCIMENTO TROCADOS: isso parece o CPF, nao a data de nascimento. Setar c="{dig_cn}" no $$$. '
                'Responder EXATAMENTE: "Ah, acho que esse é o seu CPF! Já anotei aqui. 😊 Agora me informa sua data '
                'de nascimento, por favor?" NAO peça CPF de novo.] ' + texto_usuario
            )

    return ResultadoIdentidade(base=base, intencao_rapida=intencao_rapida, rota_agente=rota_agente, motivo_humano=motivo_humano)
