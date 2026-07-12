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
  PARTE 3 (linhas 1092-1613): convênio Omint (categorias), particular bloqueado/preço, menu
    principal da triagem (opções 1-6), ver frase livre, fluxo de confirmar presença (escolher/
    lista/recusou/turno2), atraso, oferta_agendar/oferta_humano, promoção pra rota=4 (agenda),
    backstop de identidade incompleta, histórico do paciente, breadcrumb "outro dia".
  PARTE 4 (linhas 1615-1945): máquina de sub-rota da agenda (navegação → confirmação →
    execução) — backtracking/confirmação de horário, "procurar mais pra frente", "mais horário
    mesmo dia", consumo do "quer ver outro dia" por estado, desistência, FIX_COLETA_PROTECTION,
    carência de convênio (FIX_67553), gate de convênio (FIX_66512) e gate de email (FIX_59124)
    na entrada da execução.
  PARTE 5 (linhas 1947-2461): overrides de navegação por data explícita, troca de médico
    (detectada por frase ou por nome citado), guard de confirmação com horário explícito,
    troca de unidade mid-fluxo (com recálculo de grade/dia), confirmação de troca sugerida
    (FIX_PERGUNTA_DIA_CONFIRM), casos especiais Bradesco+Tatuapé, resolução de unidade a partir
    de médico+dia sem unidade escolhida (FIX_DIA_SEM_UNIDADE), lembretes de período/convênio
    obrigatórios. Esta fatia tem MUITAS tabelas de grade médico×unidade×dia praticamente
    duplicadas no JS original (mesma grade codificada ~6x em formatos ligeiramente diferentes
    pra guards diferentes) — mantidas fiéis; só reaproveitei em Python as que eram byte-a-byte
    idênticas entre dois guards (mesmo dado, mesmo uso), não as que só pareciam parecidas.
  PARTE 6 (linhas 2462-2792): "para mim" com paciente único, pré-injeção de identidade no
    cancelamento (+ recusa de cancelamento), atalho de médico com período único, resolução
    automática de médico→dia (único e múltiplos dias), injeção de período por médico/unidade/dia
    e o resolvedor determinístico dia+período→busca completa (FIX_DIA_PERIODO_DETERMINISTICO).
    Introduz o fuzzy-matcher `_match_medico_key` (Levenshtein, tolera erro de digitação de até
    2 no nome do médico) usado por vários guards seguintes.
  PARTE 7 (linhas 2794-3055): detecção de dia NÃO negado (`_dia_nao_negado_ok` — "não posso na
    terça... tem quarta?" tem que achar quarta, não terça), FIX_DIA_CROSS_UNIT (médico não
    atende esse dia na unidade atual mas atende na outra), FIX_ATENDENTE_SUBSTRING ("atendente"
    contém "atende" — guard anti-falso-positivo), FIX_PERGUNTA_DIA ("atende terça?" — responde
    com data literal calculada ou sugere trocar de unidade), FIX_TROCA_PERIODO, FIX_PROXIMO_HORARIO,
    FIX_DIA_SEMANA_INJECT (com FIX_TROCA_PERIODO_GRADE e FIX_DIA_CROSS_UNIT_INJECT aninhados).
  PARTE 8 (linhas 3056-3469): FIX_NAV_MENU_OPTIONS (menu "sem vagas" com 3 opções + detecção de
    dia dentro do catch-all), FIX_NUMERO_PRECOMPUTE (pré-computo determinístico de data/horário
    a partir de números soltos ou "dia N"/"DD/MM" no texto_ia, incluindo HHMM tipo "0820"),
    FIX_P1_TERCEIRO (nome não cadastrado digitado na etapa P1 força fluxo de terceiro),
    FIX_P3_MENU_GUARD e FIX_UNIDADE_TEXTO_OU_INVALIDA (unidade escolhida por "1"/"2" ou por
    texto livre — duas cópias quase idênticas do mesmo menu P3), limpeza de resíduo zumbi
    terceiro==titular (FIX_58755) e FIX_MESMO_MEDICO_SIM (resposta determinística de sim/não pro
    "deseja agendar com o mesmo médico da última vez?").
  PARTE 9 (linhas 3470-3689): FIX_59087 (menu P3 numérico "1/2/3" respondido com texto literal
    por opção, evitando o LLM recompor lista_med e cortar médico), FIX_NOME_INJECT_TITULAR
    (pré-identifica o paciente titular certo quando há 2+ cadastrados no telefone, via match
    exato/substring ou fuzzy Levenshtein ≤2 do nome digitado) e o bloco FAQ_INJECT completo
    (14 categorias de pergunta frequente detectadas por radical de palavra, com retomada
    determinística da coleta/agenda onde a conversa parou). `sessao_era_agenda_com_coleta`,
    `tem_identidade_em_andamento` e `tem_terceiro_completo` — computados uma vez no início do
    node no JS original e reusados por vários blocos depois, inclusive o FAQ_INJECT — entram
    aqui como parâmetros vindos de `ResultadoIntake` (Parte 1), não recomputados, pra preservar
    o valor de INÍCIO de turno mesmo depois de guards posteriores mutarem `base`.
O resto (guards de criação de consulta, cancelamento, empacotamento final) fica pra próximas
fatias — cada uma seguindo o mesmo padrão de port fiel + testes.

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
from datetime import date, datetime, timedelta, timezone

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


# ============================================================================
# PARTE 3 (linhas 1092-1613 do JS): convênio Omint, particular, menu principal,
# confirmar presença, atraso, ofertas pendentes, promoção pra agenda, histórico
# ============================================================================

_MENU_OMINT_MSG = 'Qual é a categoria do seu plano Omint? 😊\nDigite o número:\n\n1️⃣ Premium\n2️⃣ Skill\n3️⃣ Corporation\n4️⃣ Não sei informar'

_MED_OMINT_PREMIUM = ("giseli", "elias", "jose")

_CONV_PENDENTES = ("PART?", "OMINT?", "RESET_CONV")


@dataclass
class ResultadoParte3:
    base: dict
    intencao_rapida: str
    rota_agente: int
    motivo_humano: str | None
    sub_rota_agenda: str
    esta_em_agenda_ativa: bool


def processar_convenio_menu_agenda(
    base: dict,
    texto_usuario: str,
    intencao_rapida: str,
    rota_agente: int,
    ia_output: dict,
    eh_cancel_real: bool,
    eh_sessao_nova: bool,
    menu_opt: str,
    ia_rota_original: int,
    motivo_humano: str | None = None,
) -> ResultadoParte3:
    txt_norm = _norm(texto_usuario)

    # FIX_OMINT_V2 (parte 1): categorias com credenciamento distinto
    conv_om = (base.get("coleta_convenio") or "").strip().lower()
    rota_coleta_om = rota_agente in (2, 3) or _int(base.get("sessao_rota")) in (2, 3)
    if rota_coleta_om and conv_om == "omint?" and _texto_ia_livre(base):
        eh_premium_om = menu_opt == "1" or "premium" in txt_norm
        eh_skill_om = menu_opt == "2" or "skill" in txt_norm
        eh_corp_om = menu_opt == "3" or "corporation" in txt_norm or "corporacao" in txt_norm or bool(re.search(r"\bcorp\b", txt_norm))
        nao_sabe_om = menu_opt == "4" or bool(re.search(r"nao sei|nao lembro|nao tenho certeza|sei la", txt_norm))

        if eh_premium_om:
            base["coleta_convenio"] = "Omint Premium"
            med_om = _norm(base.get("coleta_medico"))
            med_real_om = bool(base.get("coleta_medico")) and base["coleta_medico"] not in ("sem preferencia", "__CLEAR__")
            ok_premium = any(m in med_om for m in _MED_OMINT_PREMIUM)
            if med_real_om and ok_premium:
                base["texto_ia"] = (
                    f'[OMINT PREMIUM OK: categoria Premium confirmada; {base["coleta_medico"]} atende Omint '
                    'Premium. Setar conv="Omint Premium" no $$$. Confirme brevemente ("Perfeito, Omint Premium!") '
                    'e CONTINUE o fluxo do ponto atual sem repetir etapas ja preenchidas: se unidade/dia/periodo '
                    'ja estiverem salvos, siga para a busca de horarios; senao pergunte o proximo campo faltante. '
                    '⛔ NUNCA invente horarios — horarios validos vem EXCLUSIVAMENTE de buscar_agenda.] ' + texto_usuario
                )
            else:
                if med_real_om and not ok_premium:
                    base["coleta_data"] = ""
                    base["coleta_periodo"] = ""
                    base["coleta_dia_semana"] = ""
                    base["_clear_pm"] = {**(base.get("_clear_pm") or {}), "dt": 1, "per": 1, "ds": 1}
                base["coleta_medico"] = ""
                base["coleta_modo"] = 0
                base["texto_ia"] = (
                    '[OMINT PREMIUM: categoria confirmada. Pelo Omint Premium atendem SOMENTE Dra. Giseli Rebechi, '
                    'Dr. Elias Lobo Braga e Dr. Jose Emmanuel Burle Neto (nas duas unidades). Setar conv="Omint '
                    'Premium", med="", modo=0 no $$$. Responder EXATAMENTE: "Perfeito! Pelo Omint Premium atendemos '
                    'com a Dra. Giseli, o Dr. Elias ou o Dr. José Emmanuel — nas duas unidades. Com qual deles '
                    'prefere? 😊" NAO chame buscar_agenda.] ' + texto_usuario
                )
        elif eh_skill_om or eh_corp_om:
            cat_om = "Omint Skill" if eh_skill_om else "Omint Corporation"
            base["coleta_convenio"] = cat_om
            if "Tatu" in (base.get("coleta_unidade") or ""):
                base["coleta_medico"] = ""
                base["coleta_modo"] = 0
                base["coleta_data"] = ""
                base["coleta_periodo"] = ""
                base["coleta_dia_semana"] = ""
                base["_clear_pm"] = {**(base.get("_clear_pm") or {}), "dt": 1, "per": 1, "ds": 1}
                base["texto_ia"] = (
                    f'[OMINT SO VILA OLIMPIA: o {cat_om} e atendido SOMENTE na Vila Olimpia, pelo Dr. Torcuato '
                    f'Sanchez Rojas Neto — e a unidade atual e Tatuape. Setar conv="{cat_om}", med="", modo=0 no '
                    '$$$ (⛔ NAO mude unid ainda). Responder EXATAMENTE: "O ' + cat_om + ' é atendido apenas na '
                    'unidade Vila Olímpia, pelo Dr. Torcuato Sanchez Rojas Neto. Deseja mudar para a Vila Olímpia? '
                    '😊" Aguarde a resposta.] ' + texto_usuario
                )
            else:
                if not base.get("coleta_unidade"):
                    base["coleta_unidade"] = "Vila Olímpia"
                base["coleta_medico"] = "Dr. Torcuato Sanchez Rojas Neto"
                base["coleta_modo"] = 3
                base["coleta_data"] = ""
                base["coleta_periodo"] = ""
                base["coleta_dia_semana"] = ""
                base["_clear_pm"] = {**(base.get("_clear_pm") or {}), "dt": 1, "per": 1, "ds": 1}
                base["texto_ia"] = (
                    f'[OMINT TORCUATO: o {cat_om} e atendido SOMENTE pelo Dr. Torcuato Sanchez Rojas Neto, na Vila '
                    f'Olimpia. Setar conv="{cat_om}", unid="Vila Olímpia", med="Dr. Torcuato Sanchez Rojas Neto", '
                    'modo=3, dt="", per="", ds="" no $$$. Responder EXATAMENTE: "O ' + cat_om + ' é atendido pelo '
                    'Dr. Torcuato Sanchez Rojas Neto, na Vila Olímpia. Ele atende quarta (só tarde), quinta e '
                    'sexta — qual dia prefere? 😊" NAO chame buscar_agenda.] ' + texto_usuario
                )
        elif nao_sabe_om:
            rota_agente = 5
            intencao_rapida = "humano"
            ia_output["bypass_agente_humano"] = True
            motivo_humano = "Paciente Omint nao sabe a categoria do plano (Premium/Skill/Corporation)"
            base["motivo_humano"] = motivo_humano
            base["texto_ia"] = (
                '[TRANSFERIR HUMANO: paciente Omint nao sabe a categoria do plano. Responder EXATAMENTE: "Sem '
                'problemas! Vou te transferir para uma atendente que confirma a categoria do seu plano e já '
                'agenda para você. 😊" e emitir i="humano", motivo="Categoria do plano Omint". NAO siga o fluxo '
                'de agenda/coleta.] ' + texto_usuario
            )
        else:
            eh_duvida_om = bool(re.search(r"\bcomo\b|\bonde\b|vejo|encontro|descubro|\?", txt_norm))
            dica_om = "Você encontra a categoria na sua carteirinha Omint (física ou no app). 😊\n\n" if eh_duvida_om else ""
            base["texto_ia"] = (
                f'[OMINT CATEGORIA INVALIDA: paciente respondeu "{texto_usuario}" mas esperamos a categoria do '
                f'plano Omint. Responder EXATAMENTE: "{dica_om}{_MENU_OMINT_MSG}" NAO mude nada no $$$ (mantenha '
                'conv="OMINT?").] ' + texto_usuario
            )
    elif (rota_coleta_om and conv_om in ("omint skill", "omint corporation")
            and "Tatu" in (base.get("coleta_unidade") or "") and _texto_ia_livre(base)):
        cat_omt = "Omint Skill" if conv_om == "omint skill" else "Omint Corporation"
        sim_omt = bool(re.match(r"^(s|si|sim|pode|pode ser|quero|claro|ok|isso|bora|vamos|aceito|pode mudar|muda|trocar|troca|vila|vila olimpia)$", txt_norm)) \
            or "vila ol" in txt_norm
        nao_omt = bool(re.match(r"^(n|nao|nao quero|prefiro nao|deixa|melhor nao)$", txt_norm)) \
            or bool(re.search(r"nao quero mudar|ficar no tatuape|prefiro( o)? tatuape", txt_norm))
        if sim_omt:
            base["coleta_unidade"] = "Vila Olímpia"
            base["coleta_medico"] = "Dr. Torcuato Sanchez Rojas Neto"
            base["coleta_modo"] = 3
            base["coleta_data"] = ""
            base["coleta_periodo"] = ""
            base["coleta_dia_semana"] = ""
            base["coleta_horario"] = ""
            base["texto_ia"] = (
                f'[TROCA UNIDADE OMINT: paciente aceitou mudar para a Vila Olimpia (unica unidade do {cat_omt}). '
                'Setar unid="Vila Olímpia", med="Dr. Torcuato Sanchez Rojas Neto", modo=3, conv="' + cat_omt
                + '", dt="", per="", ds="" no $$$. Responder EXATAMENTE: "Ótimo! Então será na Vila Olímpia com o '
                'Dr. Torcuato Sanchez Rojas Neto. Ele atende quarta (só tarde), quinta e sexta — qual dia prefere? '
                '😊" NAO chame buscar_agenda.] ' + texto_usuario
            )
        elif nao_omt:
            ia_output["bypass_agente_humano"] = True
            intencao_rapida = "humano"
            motivo_humano = f"{cat_omt} so na Vila Olimpia e paciente nao quer mudar"
            base["motivo_humano"] = motivo_humano
            base["texto_ia"] = (
                f'[OMINT SEM VILA OLIMPIA → ATENDENTE: paciente NAO quer ir para a Vila Olimpia e o {cat_omt} so '
                'e atendido la. REGRA DA CLINICA: NAO ofereca particular nem outro convenio. Responder EXATAMENTE: '
                f'"Entendo! Como o {cat_omt} é atendido apenas na Vila Olímpia, vou te passar para um atendente '
                'para te ajudar, tudo bem? 😊" e emitir i="humano", motivo="' + cat_omt
                + ' só na Vila Olímpia — paciente não quer mudar". NAO mude conv no $$$.] ' + texto_usuario
            )
        else:
            base["texto_ia"] = (
                f'[OMINT TROCA PENDENTE: o {cat_omt} so e atendido na Vila Olimpia e o paciente respondeu '
                f'"{texto_usuario}". Responder EXATAMENTE: "O {cat_omt} é atendido apenas na Vila Olímpia, pelo '
                'Dr. Torcuato. Deseja mudar para a Vila Olímpia? 😊" NAO mude nada no $$$.] ' + texto_usuario
            )

    # FIX_PARTICULAR_BLOQUEADO (REGRA CLINICA 03/07)
    conv_pb = (base.get("coleta_convenio") or "").lower()
    restrito_pb = bool(re.search(r"bradesco|omint|amil|med ?serv", conv_pb))
    if (restrito_pb and re.search(r"\bparticular\b", txt_norm)
            and not ia_output.get("bypass_agente_humano") and _texto_ia_livre(base)):
        ia_output["bypass_agente_humano"] = True
        intencao_rapida = "humano"
        motivo_humano = f'Convenio {base.get("coleta_convenio")} pediu particular (regra clinica)'
        base["motivo_humano"] = motivo_humano
        base["texto_ia"] = (
            f'[PARTICULAR BLOQUEADO → ATENDENTE: paciente com {base.get("coleta_convenio")} pediu particular. '
            'REGRA DA CLINICA: convenio declarado NUNCA vira particular pelo bot. Responder EXATAMENTE: '
            '"Infelizmente não podemos seguir no particular — vou te transferir para um atendente 😊" e emitir '
            f'i="humano", motivo="Plano {base.get("coleta_convenio")} não permite particular". ⛔ NAO mostre '
            'preço. ⛔ NAO ofereça outro convenio.] ' + texto_usuario
        )

    # FIX_PARTICULAR_PRECO
    rota_coleta_pp = rota_agente in (2, 3) or _int(base.get("sessao_rota")) in (2, 3)
    if (rota_coleta_pp and re.search(r"\bparticular\b", txt_norm) and not (base.get("coleta_convenio") or "").strip()
            and not ia_output.get("bypass_agente_humano") and _texto_ia_livre(base)):
        base["texto_ia"] = (
            '[PARTICULAR PRECO: paciente escolheu Particular. Setar conv="PART?" no $$$. Responder EXATAMENTE: '
            '"Informações para agendamento Consulta no Particular:\n✔️ Incluso 1 retorno em até 30 dias\n'
            '✔️ Procedimentos inclusos: vídeo-endoscopia, faringo-laringoscopia, nasofibrolaringoscopia, remoção '
            'de cerúmen\n📌 Pagamento: R$ 600,00 no débito/crédito | R$ 570,00 via PIX (5% de desconto)\n\n'
            'Deseja agendar como Particular? 😊" ⛔ NUNCA pule o preço. ⛔ NAO chame buscar_agenda ainda.] ' + texto_usuario
        )

    # MENU PRINCIPAL: números em sessão nova
    if eh_sessao_nova:
        opt = menu_opt
        ctx_menu_puro = not base.get("sessao_intencao") or base.get("sessao_intencao") in ("triagem", "concluido")
        eh_confirmar_kw = (
            not eh_cancel_real and bool(re.search(r"\bconfirm(a|ar|o|ado)\b", txt_norm))
            and (bool(re.search(r"(consulta|presenc|agendamento|horario)", txt_norm)) or ctx_menu_puro)
        )
        if opt == "1":
            rota_agente = 2
            intencao_rapida = "coleta"
            pacs_895 = base.get("pacientes") or []
            if len(pacs_895) == 1:
                pergunta_p1 = f'A consulta será para {pacs_895[0].get("nome", "")} ou para outra pessoa? 😊'
            elif len(pacs_895) >= 2:
                nomes = ", ".join(p.get("nome", "") for p in pacs_895)
                pergunta_p1 = f'A consulta será para {nomes} ou para outra pessoa? 😊'
            else:
                pergunta_p1 = 'A consulta será para você ou para outra pessoa? 😊'
            base["texto_ia"] = (
                f'[INICIO COLETA: paciente escolheu "1 Agendar". ⛔ NÃO mostre o menu principal de novo. '
                f'⛔ NÃO peça nome/CPF agora. Responder EXATAMENTE: "{pergunta_p1}"]'
            )
        elif opt in ("2", "3"):
            rota_agente = 1
            intencao_rapida = "cancelando"
        elif opt == "4":
            intencao_rapida = "ver"
            pacs_ver = base.get("pacientes") or []
            if len(pacs_ver) >= 2:
                intencao_rapida = "ver_escolher"
                menu_tit = "\n".join(f'{i + 1}. {p.get("nome") or f"Titular {i + 1}"}' for i, p in enumerate(pacs_ver))
                base["texto_ia"] = (
                    f'[VER ESCOLHER TITULAR: ha {len(pacs_ver)} titulares neste numero. ⛔ NAO peca CPF nem nome. '
                    f'Responder EXATAMENTE: "De quem você quer ver as consultas pendentes?\n\n{menu_tit}"] ' + texto_usuario
                )
            else:
                p_ver = pacs_ver[0] if pacs_ver else {}
                nome_ver = p_ver.get("nome") or base.get("nome") or ""
                id_ver = p_ver.get("id_tisaude") or base.get("id_tisaude") or ""
                base["texto_ia"] = (
                    f'[VER CONSULTAS: paciente escolheu "4 Consulta pendente". ⛔ NAO peca CPF nem nome — paciente '
                    f'JA identificado ({nome_ver}, id {id_ver}). Chame consultar_minhas_consultas AGORA e liste as '
                    'consultas pendentes. i="ver".] ' + texto_usuario
                )
        elif opt == "5":
            ia_output["bypass_agente_humano"] = True
        elif opt == "6" or eh_confirmar_kw:
            rota_agente = 5
            intencao_rapida = "confirmar_presenca"
            base["_sub_confirmar"] = "verificar"
            pacs_cp = base.get("pacientes") or []
            if len(pacs_cp) >= 2:
                intencao_rapida = "confirmar_presenca_escolher"
                base["_sub_confirmar"] = "escolher_titular"
                menu_tit_cp = "\n".join(f'{i + 1}. {p.get("nome") or f"Titular {i + 1}"}' for i, p in enumerate(pacs_cp))
                base["texto_ia"] = (
                    f'[CONFIRMAR PRESENÇA - ESCOLHER TITULAR: há {len(pacs_cp)} titulares neste número. ⛔ NAO peca '
                    f'CPF nem nome. Responder EXATAMENTE: "De quem você quer confirmar a consulta?\n\n{menu_tit_cp}"] '
                    + texto_usuario
                )
            else:
                toks_cf = re.sub(r"[^a-z0-9 ]", " ", txt_norm).strip().split()
                confirma_forte = (
                    opt == "6"
                    or bool(re.match(r"^\W*(confirma|confirmar|confirmo|confirmado)\W*$", txt_norm))
                    or bool(re.search(r"confirmar?\s+(minha\s+)?presen", txt_norm))
                    or (len(toks_cf) <= 5
                        and any(re.match(r"^(confirma|confirmar|confirmo|confirmado)$", t) for t in toks_cf)
                        and not re.search(r"\?|\bnao\b|\bcomo\b|\bposso\b|\bsera\b", txt_norm))
                )
                if confirma_forte:
                    base["_confirma_direto"] = True
                p_cp = pacs_cp[0] if pacs_cp else {}
                nome_cp = p_cp.get("nome") or base.get("nome") or ""
                id_cp = p_cp.get("id_tisaude") or base.get("id_tisaude") or ""
                base["texto_ia"] = (
                    f'[CONFIRMAR PRESENÇA INICIO: paciente escolheu opção 6. ⛔ NAO mostre o menu. ⛔ NAO peca CPF '
                    f'nem nome — paciente JA identificado ({nome_cp}, id {id_cp}). Chame consultar_minhas_consultas '
                    'e liste as consultas pendentes. Pergunte: "Deseja confirmar presença na consulta do dia [DATA] '
                    'às [HORA] com Dr(a). [MÉDICO]? 😊" Emitir i="confirmar_presenca" no $$$. NAO confirme ainda — '
                    'só pergunte.] ' + texto_usuario
                )

    # FIX_VER_FRASE_LIVRE
    if eh_sessao_nova and intencao_rapida not in ("ver", "ver_escolher"):
        eh_frase_ver = bool(re.search(
            r"esqueci.*(data|dia|quando|hora|consulta)|quando.*(minha\s*)?(e|esta|sera|tem).*consulta|"
            r"qual.*(data|dia|hora).*consulta|ver.*minhas?\s*consultas?|minhas\s*consultas?|"
            r"tem.*consulta.*marcad[ao]", txt_norm
        ))
        pacs_fl = base.get("pacientes") or []
        tem_pac_fl = bool(pacs_fl) or bool(base.get("cpf") or base.get("id_tisaude"))
        if eh_frase_ver and tem_pac_fl:
            intencao_rapida = "ver"
            if len(pacs_fl) >= 2:
                intencao_rapida = "ver_escolher"
                menu_tit_fl = "\n".join(f'{i + 1}. {p.get("nome") or f"Titular {i + 1}"}' for i, p in enumerate(pacs_fl))
                base["texto_ia"] = (
                    f'[VER ESCOLHER TITULAR: ha {len(pacs_fl)} titulares neste numero. ⛔ NAO peca CPF nem nome. '
                    f'Responder EXATAMENTE: "De quem você quer ver as consultas pendentes?\n\n{menu_tit_fl}"] ' + texto_usuario
                )
            else:
                p_fl = pacs_fl[0] if pacs_fl else {}
                nome_fl = p_fl.get("nome") or base.get("nome") or ""
                id_fl = p_fl.get("id_tisaude") or base.get("id_tisaude") or ""
                base["texto_ia"] = (
                    f'[VER CONSULTAS: paciente perguntou "{texto_usuario}". ⛔ NAO peca CPF nem nome — paciente JA '
                    f'identificado ({nome_fl}, id {id_fl}). Chame consultar_minhas_consultas AGORA e liste as '
                    'consultas pendentes. i="ver".] ' + texto_usuario
                )

    # FIX_CONFIRMAR_PRESENCA_ESCOLHER
    if base.get("sessao_intencao") == "confirmar_presenca_escolher":
        pacs_cp2 = base.get("pacientes") or []
        sel_cp2 = _to_int_or_none(texto_usuario.strip())
        if sel_cp2 is not None and 1 <= sel_cp2 <= len(pacs_cp2):
            p_sel2 = pacs_cp2[sel_cp2 - 1]
            nome_s2 = p_sel2.get("nome") or f"Titular {sel_cp2}"
            id_s2 = p_sel2.get("id_tisaude") or ""
            rota_agente = 5
            intencao_rapida = "confirmar_presenca"
            base["_sub_confirmar"] = "verificar"
            base["_confirma_direto"] = True
            base["cpf_dependente"] = p_sel2.get("cpf") or base.get("cpf_dependente") or ""
            base["nome_dependente"] = nome_s2
            base["id_tisaude"] = id_s2
            base["texto_ia"] = (
                f'[CONFIRMAR PRESENÇA INICIO: paciente escolheu {nome_s2} (id {id_s2}). ⛔ NAO mostre menu. '
                '⛔ NAO peca CPF nem nome — paciente JA identificado. Chame consultar_minhas_consultas e liste as '
                'consultas pendentes. Pergunte: "Deseja confirmar presença na consulta do dia [DATA] às [HORA] com '
                'Dr(a). [MÉDICO]? 😊" Emitir i="confirmar_presenca". NAO confirme ainda.] ' + texto_usuario
            )
        else:
            nao_esc = bool(re.search(r"\b(nao|n|nao quero|cancelar|cancela|desmarcar|desistir|deixa)\b", txt_norm))
            if nao_esc:
                rota_agente = 5
                intencao_rapida = "confirmar_presenca_recusou"
                base["_sub_confirmar"] = "recusou"
            elif _int(base.get("coleta_conv_fail")) >= 2:
                ia_output["bypass_agente_humano"] = True
                intencao_rapida = "humano"
                motivo_humano = "Confirmação de presença — paciente não conseguiu escolher o titular"
                base["motivo_humano"] = motivo_humano
                base["texto_ia"] = (
                    '[TRANSFERIR HUMANO: paciente não conseguiu responder a lista de confirmação. Responder '
                    'EXATAMENTE: "Vou te passar para um atendente para te ajudar com a confirmação! 😊" e emitir '
                    'i="humano", motivo="Confirmação de presença — paciente não conseguiu escolher".] ' + texto_usuario
                )
            else:
                rota_agente = 5
                intencao_rapida = "confirmar_presenca_escolher"
                base["_sub_confirmar"] = "escolher_titular"

    # FIX_CONFIRMAR_PRESENCA_LISTA
    if base.get("sessao_intencao") == "confirmar_presenca_lista":
        sel_lst = _to_int_or_none(txt_norm)
        nao_lst = bool(re.search(r"\b(nao|n|nao quero|cancelar|cancela|desmarcar|desistir|deixa)\b", txt_norm))
        if sel_lst is not None and sel_lst >= 1:
            rota_agente = 5
            intencao_rapida = "confirmar_presenca"
            base["_sub_confirmar"] = "verificar"
            base["_indice_consulta"] = sel_lst
            base["_confirma_direto"] = True
        elif nao_lst:
            rota_agente = 5
            intencao_rapida = "confirmar_presenca_recusou"
            base["_sub_confirmar"] = "recusou"
        elif _int(base.get("coleta_conv_fail")) >= 2:
            ia_output["bypass_agente_humano"] = True
            intencao_rapida = "humano"
            motivo_humano = "Confirmação de presença — paciente não conseguiu escolher a consulta"
            base["motivo_humano"] = motivo_humano
            base["texto_ia"] = (
                '[TRANSFERIR HUMANO: paciente não conseguiu responder a lista de confirmação. Responder EXATAMENTE: '
                '"Vou te passar para um atendente para te ajudar com a confirmação! 😊" e emitir i="humano", '
                'motivo="Confirmação de presença — paciente não conseguiu escolher".] ' + texto_usuario
            )
        else:
            rota_agente = 5
            intencao_rapida = "confirmar_presenca_lista"
            base["_sub_confirmar"] = "verificar"

    # FIX_CONFIRMAR_PRESENCA_RECUSOU
    if base.get("sessao_intencao") == "confirmar_presenca_recusou":
        sim_rc = bool(re.search(r"\b(sim|s|quero|pode|isso|cancelar|cancela|desmarcar|remarcar|remarca|trocar|mudar|outro)\b", txt_norm))
        nao_rc = bool(re.search(r"\b(nao|n|nao quero|deixa|esquece|nada|obrigad|obg|valeu|tudo bem|ta bom|ok)\b", txt_norm))
        if sim_rc and not nao_rc:
            rota_agente = 1
            intencao_rapida = "cancelando"
            base["texto_ia"] = (
                '[CANCELAMENTO via recusa de confirmação: paciente quer cancelar ou remarcar a consulta. Proceder '
                'normalmente com o cancelamento.] ' + texto_usuario
            )
        else:
            rota_agente = 5
            intencao_rapida = "concluido"
            base["_sub_confirmar"] = "despedida"

    # FIX_CONFIRMAR_PRESENCA (turno 2)
    if base.get("sessao_intencao") == "confirmar_presenca":
        sim_cp = bool(re.search(r"\b(sim|s|ok|pode|isso|confirmo|confirma|confirmado|claro|bora|vamos|perfeito)\b", txt_norm))
        nao_cp = bool(re.search(r"\b(nao|n|nao quero|cancelar|cancela|desmarcar)\b", txt_norm))
        if sim_cp and not nao_cp:
            rota_agente = 5
            intencao_rapida = "confirmar_presenca"
            id_ag_cp = str(base.get("coleta_id_agendamento") or "").strip()
            if id_ag_cp:
                base["_sub_confirmar"] = "executar"
            else:
                base["_sub_confirmar"] = "verificar"
                base["_confirma_direto"] = True
        elif nao_cp:
            rota_agente = 5
            intencao_rapida = "confirmar_presenca_recusou"
            base["_sub_confirmar"] = "recusou"
        else:
            rota_agente = 5
            intencao_rapida = "confirmar_presenca"
            base["_sub_confirmar"] = "verificar"

    # FIX_ATRASO_HUMANO — sem gate: sempre que casar, sobrescreve (prioridade máxima)
    eh_atraso = bool(re.search(
        r"atrasar|atrasad|atrasando|vou chegar (mais )?tarde|chegar mais tarde|vou demorar|preso no transito|"
        r"preso no transit|engarrafament", txt_norm
    ))
    if eh_atraso:
        ia_output["bypass_agente_humano"] = True
        motivo_humano = "Paciente avisou que vai se atrasar para a consulta"
        base["motivo_humano"] = motivo_humano
        base["texto_ia"] = (
            '[TRANSFERIR HUMANO: paciente avisou que vai se atrasar para a consulta. Responder EXATAMENTE: "Vou te '
            'transferir para um atendente para ajustar isso! 😊" e emitir i="humano", motivo="Paciente vai se '
            'atrasar para a consulta". NAO siga o fluxo de agenda/coleta.] ' + texto_usuario
        )

    # FIX_67529: resposta à oferta_agendar pendente
    if base.get("sessao_intencao") == "oferta_agendar" and not eh_cancel_real and _texto_ia_livre(base):
        txt_oa_seco = re.sub(r"[^a-z]", "", txt_norm)
        sim_oa = bool(re.search(r"\b(sim|sin|claro|quero|pode|pode ser|isso|ok|beleza|blz|bora|vamos|por favor|agendar|marcar)\b", txt_norm)) \
            or txt_oa_seco in ("s", "ss", "si", "sim", "sin")
        nao_oa = bool(re.search(r"\b(nao|deixa|depois|esquece|nem|so isso|obrigad[oa]|por enquanto)\b", txt_norm)) or txt_oa_seco == "n"
        if sim_oa and not nao_oa:
            rota_agente = 2
            intencao_rapida = "coleta"
            pacs_oa = base.get("pacientes") or []
            if len(pacs_oa) == 1:
                pergunta_oa = f'A consulta será para {pacs_oa[0].get("nome", "")} ou para outra pessoa? 😊'
            elif len(pacs_oa) >= 2:
                pergunta_oa = f'A consulta será para {", ".join(p.get("nome", "") for p in pacs_oa)} ou para outra pessoa? 😊'
            else:
                pergunta_oa = 'A consulta será para você ou para outra pessoa? 😊'
            base["texto_ia"] = (
                f'[INICIO COLETA: paciente aceitou o convite de agendamento. ⛔ NÃO mostre o menu principal. '
                f'⛔ NÃO peça CPF agora. Responder EXATAMENTE: "{pergunta_oa}"]'
            )
        elif nao_oa:
            intencao_rapida = "concluido"
            base["texto_ia"] = (
                '[ENCERRAMENTO OFERTA AGENDAR: paciente nao quer agendar agora. Responder EXATAMENTE: "Sem '
                'problemas! 😊 Precisando de algo é só chamar!" e emitir i="concluido".] ' + texto_usuario
            )
        else:
            intencao_rapida = "triagem"

    # FIX_CONFIRMA_HUMANO: resposta à oferta_humano pendente
    if base.get("sessao_intencao") == "oferta_humano":
        txt_ch_seco = re.sub(r"[^a-z]", "", txt_norm)
        sim_humano = (
            bool(re.search(r"\b(sim|sin|claro|quero|pode|isso|aceito|ok|positivo|atendente|bora|vamos|preciso)\b", txt_norm))
            or bool(re.search(r"confirm", txt_norm)) or bool(re.search(r"por favor|pf\b", txt_norm))
            or txt_ch_seco in ("s", "ss", "si")
        )
        nao_humano = bool(re.search(r"\b(nao|deixa|depois|esquece|nem|cancela|so isso|sem)\b", txt_norm)) or txt_ch_seco == "n"
        if sim_humano and not nao_humano:
            ia_output["bypass_agente_humano"] = True
            intencao_rapida = "humano"
            motivo_humano = "Duvida nao respondida pelo bot — paciente pediu atendente"
            base["motivo_humano"] = motivo_humano
            base["texto_ia"] = (
                '[TRANSFERIR HUMANO: paciente confirmou que quer falar com atendente apos uma duvida nao '
                'respondida. Responder EXATAMENTE: "Certo! Vou te transferir para um atendente. 😊" e emitir '
                'i="humano", motivo="Duvida". NAO siga o fluxo de agenda/coleta.] ' + texto_usuario
            )
        elif nao_humano:
            intencao_rapida = "triagem"

    # ROTA 4: todos os passos de coleta confirmados → Agente Agenda
    conv_valido = (base.get("coleta_convenio") or "") != "" and base.get("coleta_convenio") not in _CONV_PENDENTES
    all_coleta_confirmed = (
        conv_valido
        and (base.get("coleta_data") or "") != ""
        and (base.get("coleta_unidade") or "") != ""
        and (base.get("coleta_periodo") or "") != ""
    )
    ia_requested_downgrade = (
        isinstance(ia_output.get("rota_agente"), int) and ia_rota_original < 4 and _int(base.get("sessao_rota")) >= 4
    )
    if all_coleta_confirmed and rota_agente in (2, 3) and not ia_requested_downgrade:
        rota_agente = 4

    # PROTEÇÃO COLETA AGENDA: rota=4 sem coleta completa → downgrade
    if rota_agente == 4 and not all_coleta_confirmed:
        rota_agente = 2

    # FIX_IDENTIDADE_0PAC (52775): backstop de identidade antes do Agente Agenda
    identidade_incompleta = not base.get("paciente_encontrado") and (
        not (base.get("nome_dependente") or "").strip()
        or not (base.get("cpf_dependente") or "").strip()
        or not (base.get("nascimento_dependente") or "").strip()
    )
    if identidade_incompleta and rota_agente == 4:
        rota_agente = 3 if base.get("coleta_terceiro") == "true" else 2
        if intencao_rapida == "agenda":
            intencao_rapida = "coleta"
        if not (base.get("nome_dependente") or "").strip():
            falta_id = "nome completo"
        elif not (base.get("cpf_dependente") or "").strip():
            falta_id = "CPF"
        else:
            falta_id = "data de nascimento"
        base["texto_ia"] = (
            f'[IDENTIDADE OBRIGATORIA: paciente NAO cadastrado, falta o {falta_id}. ⛔ NAO chame buscar_agenda. '
            f'⛔ NAO confirme horario. Pergunte EXATAMENTE pelo {falta_id} do paciente antes de prosseguir. Mantenha '
            'unid/med/dt/per/conv no $$$.] ' + texto_usuario
        )

    # FIX_HIST_PACIENTE (57455) + FIX_ULTIMO_CONV (57405): stashed em base pra uso downstream
    pacs_hist = base.get("pacientes") or []
    id_hist = str(base.get("coleta_id_tisaude") or "")
    nm_hist = (base.get("nome_dependente") or "").strip().lower()
    hist_pac = None
    if id_hist:
        hist_pac = next((x for x in pacs_hist if str(x.get("id_tisaude")) == id_hist), None)
    if not hist_pac and nm_hist:
        hist_pac = next((x for x in pacs_hist if (x.get("nome") or "").strip().lower() == nm_hist), None)
    if not hist_pac and len(pacs_hist) == 1:
        hist_pac = pacs_hist[0]
    hist_pac = hist_pac or {}
    base["_ultimo_medico_global"] = hist_pac.get("ultimo_medico") or ""

    ult_conv_upper = (hist_pac.get("ultimo_convenio") or "").upper()
    ult_conv_global = ""
    if ult_conv_upper:
        if "PARTICULAR" in ult_conv_upper:
            ult_conv_global = "Particular"
        elif "PORTO" in ult_conv_upper:
            ult_conv_global = "Porto Seguro"
        elif "ITAU" in ult_conv_upper or "ITAÚ" in ult_conv_upper:
            ult_conv_global = "Itaú"
        elif "BRADESCO" in ult_conv_upper:
            ult_conv_global = "Bradesco"
        elif "OMINT" in ult_conv_upper:
            ult_conv_global = "Omint"
    base["_ultimo_convenio_global"] = ult_conv_global
    base["_pergunta_convenio_global"] = (
        f'Sua última consulta foi como {ult_conv_global}. Deseja usar {ult_conv_global} novamente, ou prefere '
        'outra forma? 😊'
    ) if ult_conv_global else 'A consulta será Particular ou Convênio? 😊'

    # FIX_OUTRO_DIA_BREADCRUMB
    if base.get("sessao_intencao") == "oferecer_outro_dia":
        base["sessao_intencao"] = "navegacao"
        neg_od = bool(re.match(r"^(nao|n|nao quero|esse mesmo|esse|fico com esse|pode ser esse|deixa esse)\b", txt_norm))
        afirm_od = not neg_od and (
            bool(re.match(r"^(s|si|sim|quero|pode|isso|outro|proximo|proxima|ver outro|quero ver|pode ser|sim quero|quero outro|outro dia)\b", txt_norm))
            or "outro dia" in txt_norm or "proximo dia" in txt_norm
        )
        if afirm_od:
            base["texto_ia"] = (
                '[VER OUTRO DIA CONFIRMADO: paciente quer ver o proximo dia disponivel. ⛔ OBRIGATORIO chamar '
                'navegar_agenda(avancar) AGORA e EXIBIR o proximo dia. ⛔ NAO repita os horarios do dia atual. '
                '⛔ NAO peca horario do dia atual. i="agenda".] ' + texto_usuario
            )

    # FIX_AGENDA_SUB_ROUTE: divide rota=4 em sub-estados
    agenda_sub_rotas = ("navegacao", "confirmacao", "execucao", "coleta")
    esta_em_sub_rota_agenda = base.get("sessao_intencao") in agenda_sub_rotas
    esta_em_agenda_ativa = esta_em_sub_rota_agenda or (
        base.get("sessao_intencao") == "agenda" and _int(base.get("sessao_rota")) == 4
    )
    sub_rota_agenda = base.get("sessao_intencao") if esta_em_sub_rota_agenda else "navegacao"

    return ResultadoParte3(
        base=base,
        intencao_rapida=intencao_rapida,
        rota_agente=rota_agente,
        motivo_humano=motivo_humano,
        sub_rota_agenda=sub_rota_agenda,
        esta_em_agenda_ativa=esta_em_agenda_ativa,
    )


# ============================================================================
# PARTE 4 (linhas 1615-1945 do JS): máquina de sub-rota da agenda
# (navegação → confirmação → execução), carência, gate de convênio/email
# ============================================================================

_MAPA_CONVENIO = [
    (re.compile(r"\bporto( seguro)?\b"), "Porto Seguro"),
    (re.compile(r"\bitau\b"), "Itaú"),
    (re.compile(r"\bomint\b"), "Omint"),
    (re.compile(r"\bbradesco\b"), "Bradesco"),
    (re.compile(r"\bparticular\b"), "Particular"),
]


def _br_data(iso: str) -> str:
    partes = (iso or "").split("-")
    return "/".join(reversed(partes)) if len(partes) == 3 else (iso or "")


def _add_dias(date_str: str, dias: int) -> str:
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d") + timedelta(days=dias)
        return d.strftime("%Y-%m-%d")
    except ValueError:
        return ""


@dataclass
class ResultadoParte4:
    base: dict
    intencao_rapida: str
    rota_agente: int
    sub_rota_agenda: str


def processar_sub_rota_agenda(
    base: dict,
    texto_usuario: str,
    intencao_rapida: str,
    rota_agente: int,
    ia_output: dict,
    eh_cancel_real: bool,
    eh_pergunta_ver: bool,
    eh_mensagem_informativa: bool,
    all_coleta_confirmed: bool,
    esta_em_agenda_ativa: bool,
    sub_rota_agenda: str,
) -> ResultadoParte4:
    txt_norm = _norm(texto_usuario)
    udi = base.get("ultimo_dia_exibido")
    if not isinstance(udi, dict):
        udi = {}

    # FIX_59204: horario+data escolhidos e ainda nao em execucao = confirmacao por definicao
    if esta_em_agenda_ativa and base.get("coleta_horario") and base.get("coleta_data") and sub_rota_agenda != "execucao":
        sub_rota_agenda = "confirmacao"

    # Backtracking / FIX_CONFIRMA_DIRETO
    if sub_rota_agenda == "confirmacao" and _texto_ia_livre(base):
        quer_voltar = txt_norm.strip() == "n" or bool(re.search(
            r"outr[oa]|diferente|mudar|nao quero|nao|errado|trocar|voltar|proximo dia|dia seguinte|proxima semana|"
            r"semana que vem|tem mais (dias?|datas?|horarios?|opcao|opcoes)|\bn consigo\b|\bn posso\b|\bn quero\b|\bn da\b",
            txt_norm,
        ))
        if quer_voltar:
            sub_rota_agenda = "navegacao"
            tag_vn = (
                '[VOLTA NAVEGACAO: paciente rejeitou horário, mostrar opções novamente. Setar h="" e dt="" no $$$ '
                '— ⛔ NAO ecoe o horario/data rejeitados.] '
            )
            pede_dia_vn = bool(re.search(r"\bdias?\b|proximo dia|proxima semana|semana que vem|dia seguinte", txt_norm))
            if pede_dia_vn and re.match(r"^\d{4}-\d{2}-\d{2}$", base.get("coleta_data") or ""):
                dt_prox_vn = _add_dias(base["coleta_data"], 1)
                if re.search(r"proxima semana|semana que vem", txt_norm) and re.match(r"^\d{4}-\d{2}-\d{2}$", base.get("prox_seg") or ""):
                    dt_prox_vn = base["prox_seg"]
                if dt_prox_vn:
                    dt_rej_br = _br_data(base["coleta_data"])
                    per_txt = f', periodo="{base["coleta_periodo"]}"' if base.get("coleta_periodo") else ""
                    tag_vn = (
                        f'[OUTRO DIA APOS REJEICAO: paciente quer OUTRO DIA (nao os horarios de {dt_rej_br}). '
                        f'⛔ OBRIGATORIO chamar buscar_agenda AGORA com data="{dt_prox_vn}", '
                        f'unidade="{base.get("coleta_unidade") or ""}", medico="{base.get("coleta_medico") or ""}"'
                        f'{per_txt} e EXIBIR os dias que a tool retornar. ⛔ NAO repita os horarios de {dt_rej_br}. '
                        'Setar h="" no $$$.] '
                    )
            base["coleta_data"] = ""
            base["coleta_horario"] = ""
            base["_clear_pm"] = {**(base.get("_clear_pm") or {}), "dt": 1, "h": 1}
            base["texto_ia"] = tag_vn + texto_usuario
        else:
            txt_conf = txt_norm.strip()
            eh_conf_positiva = bool(re.match(
                r"^(s|si|sim|ok|pode|correto|certo|isso|bora|vamos|perfeito|confirmo|confirma|pode ser|ta bom|ta certo|beleza)$",
                txt_conf,
            )) or bool(re.search(
                r"\b(sim|correto|corretos|certo|isso|perfeito|confirmo|confirmado|confirma|confirmar|exato|"
                r"exatamente|positivo|fechado|combinado|pode confirmar|pode agendar|pode marcar|ta correto|ta certo|"
                r"esta correto|tudo certo|tudo correto)\b",
                txt_conf,
            ))
            if eh_conf_positiva:
                sub_rota_agenda = "execucao"

    # FIX_65977c: tag HORARIO NAO VERIFICADO forca navegacao (Agente Confirmacao nao busca)
    base["_sub_rota_agenda"] = "navegacao" if "[HORARIO NAO VERIFICADO" in (base.get("texto_ia") or "") else sub_rota_agenda

    # FIX_PROCURAR_MAIS_FRENTE
    if sub_rota_agenda == "navegacao" and base.get("coleta_medico"):
        txt_pmf = txt_norm
        udi_raw = base.get("ultimo_dia_exibido")
        tem_vaga_exibida = bool(udi_raw) and (not isinstance(udi_raw, dict) or len(udi_raw) > 0)
        eh_proc_mais = (not tem_vaga_exibida and base.get("cache_ativo") and txt_pmf == "3") or bool(
            re.search(r"mais para frente|mais pra frente|procurar mais|mais adiante|mais para a frente", txt_pmf)
        )
        if eh_proc_mais:
            if base.get("coleta_data") and re.match(r"^\d{4}-\d{2}-\d{2}$", base["coleta_data"]):
                base_dt_pmf = base["coleta_data"]
            else:
                base_dt_pmf = _add_dias(datetime.now().strftime("%Y-%m-%d"), 1)
            nova_dt_pmf = _add_dias(base_dt_pmf, 20)
            base["coleta_data"] = nova_dt_pmf
            per_txt = f', periodo="{base["coleta_periodo"]}"' if base.get("coleta_periodo") else ""
            base["texto_ia"] = (
                f'[PROCURAR MAIS PARA FRENTE: paciente quer datas mais adiante. ⛔ OBRIGATORIO chamar buscar_agenda '
                f'AGORA com data="{nova_dt_pmf}", unidade="{base.get("coleta_unidade") or ""}", '
                f'medico="{base.get("coleta_medico") or ""}"{per_txt} (mantenha o periodo escolhido) → '
                'navegar_agenda(ver). Se houver vagas, EXIBA. Se vazio, ofereça outro medico ou atendente. '
                '⛔ NAO repita o menu "proximos 20 dias" com a mesma data anterior.] ' + texto_usuario
            )

    # FIX_MAIS_HORARIO_MESMO_DIA
    if sub_rota_agenda == "navegacao" and udi.get("data"):
        txt_mh = txt_norm
        fala_dia_mh = bool(re.search(r"\bdia\b|\bdata\b|semana|amanha|segunda|terca|quarta|quinta|sexta", txt_mh))
        eh_mais_horario = not fala_dia_mh and (
            bool(re.search(r"mais hor|outro hor|outros hor|mais opcao|mais opcoes", txt_mh))
            or txt_mh in ("tem mais", "mais", "tem outro", "tem mais horario", "tem outro horario")
        )
        if eh_mais_horario:
            dt_mh = _br_data(udi["data"])
            per_mh = f' ({"manhã" if base.get("coleta_periodo") == "manha" else base.get("coleta_periodo")})' if base.get("coleta_periodo") else ""
            base["texto_ia"] = (
                f'[MAIS HORARIO MESMO DIA: a busca ja trouxe TODOS os horarios de {dt_mh}. ⛔ NAO avance de dia. '
                f'⛔ NAO invente horarios. Responder EXATAMENTE: "Esses sao todos os horarios disponiveis para '
                f'{dt_mh}{per_mh}. Quer ver outro dia? 😊" i="agenda".] ' + texto_usuario
            )
            intencao_rapida = "oferecer_outro_dia"

    # FIX_59198: consumo do "Quer ver outro dia?" por ESTADO
    if (esta_em_agenda_ativa and base.get("cache_ativo") and udi.get("data") and not base.get("coleta_horario")
            and not ia_output.get("bypass_agente_humano") and _texto_ia_livre(base)):
        txt_vod = re.sub(r"\s+", " ", re.sub(r"[!.,?]+", " ", txt_norm)).strip()
        rejeita_dia_vod = (
            bool(re.search(r"\bn(ao)?\s+(posso|consigo|da|rola|serve|gostei)\b", txt_vod))
            or bool(re.match(r"^n(ao)?,? ?(nesse|nessa|esse dia|essa data)", txt_vod))
            or bool(re.match(r"^n(ao)? quero (esse|nesse|essa)", txt_vod))
        )
        neg_vod = not rejeita_dia_vod and bool(re.match(
            r"^(nao|n|nao quero|esse mesmo|esse|fico com esse|pode ser esse|deixa esse|quero esse|nao obrigado)$", txt_vod
        ))
        afirm_vod = not neg_vod and (
            rejeita_dia_vod
            or bool(re.match(r"^(s|si|sim|quero|pode|pode ser|ok|claro|isso|blz|beleza|por favor|sim quero|quero sim|pode sim)$", txt_vod))
            or bool(re.search(r"\b(outro dia|proximo dia|ver outro|quero outro|dia seguinte)\b", txt_vod))
            or txt_vod in ("outro", "proximo")
        )
        if afirm_vod:
            base["texto_ia"] = (
                '[VER OUTRO DIA CONFIRMADO: paciente quer ver o proximo dia disponivel. ⛔ OBRIGATORIO chamar '
                'navegar_agenda(avancar) AGORA e EXIBIR o proximo dia que a tool retornar. ⛔ NAO repita os '
                'horarios do dia atual. ⛔ NAO peca horario do dia atual. i="agenda".] ' + texto_usuario
            )
        elif neg_vod:
            dt_vod = _br_data(udi["data"])
            medicos_vod = udi.get("medicos") or []
            hs_vod = (medicos_vod[0].get("horarios") if medicos_vod else "") or ""
            base["texto_ia"] = (
                f'[FICAR NO DIA ATUAL: paciente NAO quer outro dia. Responder EXATAMENTE: "Perfeito! Qual horário '
                f'prefere para {dt_vod}: {hs_vod}? 😊" ⛔ NAO chame navegar_agenda. ⛔ NAO avance de dia. i="agenda".] '
                + texto_usuario
            )

    # FIX_67635: desistencia da agenda
    if esta_em_agenda_ativa and not ia_output.get("bypass_agente_humano") and not eh_cancel_real and _texto_ia_livre(base):
        txt_des = txt_norm
        desiste_forte = bool(re.search(
            r"muito longe|deixa pra la|nao quero mais|desist[oi]|fica pra proxima|outra hora eu vejo|nao vou marcar|"
            r"deixa quieto",
            txt_des,
        ))
        tem_nenhum_des = bool(re.search(r"\bnenhum[a]?\b", txt_des))
        if desiste_forte or (tem_nenhum_des and "obrigad" in txt_des):
            intencao_rapida = "concluido"
            unid_des = _norm(base.get("coleta_unidade"))
            extra_des = (
                ' Só um detalhe: também temos a unidade Tatuapé (Rua Soriano de Sousa, 189 - Tatuapé). Se ficar '
                'melhor pra você, é só me chamar!'
            ) if ("longe" in txt_des and "olimpia" in unid_des) else ""
            base["texto_ia"] = (
                '[DESISTENCIA AGENDA: paciente desistiu do agendamento. Responder EXATAMENTE: "Sem problemas! 😊 '
                f'Quando quiser agendar é só me chamar. Até logo!{extra_des}" e emitir i="concluido" no $$$. '
                '⛔ NAO ofereça horarios. ⛔ NAO re-pergunte.] ' + texto_usuario
            )
        elif tem_nenhum_des and base.get("cache_ativo") and udi.get("data") and not base.get("coleta_horario"):
            intencao_rapida = "oferecer_outro_dia"
            base["texto_ia"] = (
                '[NENHUM HORARIO SERVIU: nenhum horario do dia exibido serve para o paciente. Responder EXATAMENTE: '
                '"Entendi! Quer ver os horários de outro dia? 😊" ⛔ NAO repita os horarios do dia atual. i="agenda".] '
                + texto_usuario
            )

    # Protege rota=4 em sub-fluxo
    if esta_em_agenda_ativa and not eh_cancel_real and not eh_pergunta_ver and not eh_mensagem_informativa:
        rota_agente = 4
        if intencao_rapida == "triagem":
            intencao_rapida = "agenda"

    # FIX_COLETA_PROTECTION
    if (base.get("sessao_intencao") == "coleta" and not eh_cancel_real and not ia_output.get("bypass_agente_humano")
            and intencao_rapida not in ("remarcando", "remarcando_escolher")):
        if all_coleta_confirmed and base.get("coleta_medico"):
            base["_sub_rota_agenda"] = "navegacao"
            intencao_rapida = "agenda"
            if _texto_ia_livre(base):
                txt_cc = txt_norm
                conv_salvo_cc = _norm(base.get("coleta_convenio"))
                conv_msg_cc = next((nome for rx, nome in _MAPA_CONVENIO if rx.search(txt_cc)), "")
                afirma_cc = bool(re.match(
                    r"^(s|si|sim|ok|pode|pode ser|isso|usar|quero usar|vou usar|esse mesmo|o mesmo|mesmo|novamente|"
                    r"manter|pode usar)\b",
                    txt_cc,
                )) or (bool(conv_salvo_cc) and conv_salvo_cc in txt_cc)
                if conv_msg_cc or afirma_cc:
                    if conv_msg_cc:
                        base["coleta_convenio"] = conv_msg_cc
                    conv_final_cc = base["coleta_convenio"]
                    per_txt = f', periodo="{base["coleta_periodo"]}"' if base.get("coleta_periodo") else ""
                    base["texto_ia"] = (
                        f'[CONVENIO CONFIRMADO — COLETA COMPLETA: conv="{conv_final_cc}". Chame buscar_agenda '
                        f'AGORA com unidade="{base.get("coleta_unidade") or ""}", '
                        f'medico="{base.get("coleta_medico") or ""}", data="{base.get("coleta_data") or ""}"'
                        f'{per_txt} e mostre os horarios que a TOOL retornar. Setar conv="{conv_final_cc}", '
                        'i="agenda" no $$$. ⛔ NAO pergunte convenio. ⛔ NAO mude unidade nem medico. ⛔ NUNCA '
                        'invente horarios.] ' + texto_usuario
                    )
        else:
            rota_agente = 3 if (base.get("sessao_rota") == "3" or base.get("coleta_terceiro") == "true") else 2
            intencao_rapida = "coleta"

    # FIX email: força eh_confirmacao=true para respostas de email
    txt_email_norm2 = re.sub(r"[!.?]", "", txt_norm)
    padroes_email_fix = ("n tenho", "nao tenho", "nao tenho email", "pular", "sem email")
    eh_email_addr = bool(re.search(r"[\w.+-]+@[\w.-]+\.[a-z]{2,}", texto_usuario, re.IGNORECASE))
    eh_resposta_email_fix = any(p in txt_email_norm2 for p in padroes_email_fix) or eh_email_addr
    if rota_agente == 4 and base.get("coleta_horario") and base.get("coleta_data") and eh_resposta_email_fix:
        ia_output["eh_confirmacao"] = True

    # FIX_67553: carencia — guard de entrada na execucao
    ult_conv_global = base.get("_ultimo_convenio_global") or ""
    conv_ja_c = (base.get("coleta_convenio") or "").strip()
    dt_min_c = base.get("data_minima_carencia") or ""
    if (base.get("_sub_rota_agenda") == "execucao" and conv_ja_c and ult_conv_global
            and conv_ja_c.lower() == ult_conv_global.lower()
            and re.match(r"^\d{4}-\d{2}-\d{2}$", dt_min_c) and re.match(r"^\d{4}-\d{2}-\d{2}$", base.get("coleta_data") or "")
            and base["coleta_data"] < dt_min_c
            and not ia_output.get("bypass_agente_humano") and _texto_ia_livre(base)):
        min_br_c = base.get("data_minima_carencia_br") or _br_data(dt_min_c)
        esc_br_c = _br_data(base["coleta_data"])
        txt_car = txt_norm
        if re.search(r"\bparticular\b", txt_car):
            base["coleta_convenio"] = "Particular"
            base["texto_ia"] = (
                f'[CONVENIO PARTICULAR CONFIRMADO: paciente optou por particular para manter {esc_br_c}. Salve '
                'conv="Particular" no $$$ e continue: se ainda nao temos o email do paciente, pergunte o email '
                'AGORA; senao chame criar_consulta/criar_consulta_terceiro AGORA com os dados salvos. ⛔ NAO mude '
                'a data. ⛔ NAO pergunte convenio de novo.] ' + texto_usuario
            )
        elif re.search(r"buscar|a partir|nova data|outra data|essa data|aguardo|espero|apos|depois d|pode ser depois", txt_car):
            rota_agente = 4
            base["_sub_rota_agenda"] = "navegacao"
            intencao_rapida = "agenda"
            base["coleta_data"] = ""
            base["coleta_dia_semana"] = ""
            base["coleta_horario"] = ""
            base["_clear_pm"] = {**(base.get("_clear_pm") or {}), "dt": 1, "ds": 1, "h": 1}
            per_txt = f', periodo="{base["coleta_periodo"]}"' if base.get("coleta_periodo") else ""
            base["texto_ia"] = (
                f'[CARENCIA BUSCAR: paciente quer horarios a partir de {min_br_c} pelo {conv_ja_c}. Chame '
                f'buscar_agenda AGORA com unidade="{base.get("coleta_unidade") or ""}", '
                f'medico="{base.get("coleta_medico") or ""}", data="{dt_min_c}"{per_txt} e mostre os horarios que '
                'a TOOL retornar. Setar dt="", h="" no $$$. ⛔ NUNCA invente horarios.] ' + texto_usuario
            )
        else:
            base["texto_ia"] = (
                f'[CARENCIA CONVENIO: pelo {conv_ja_c} a proxima consulta so pode ser a partir de {min_br_c} '
                f'(carencia) e a data escolhida e {esc_br_c}. Responder EXATAMENTE: "Pelo convênio {conv_ja_c} sua '
                f'próxima consulta pode ser a partir de {min_br_c}. Quer que eu busque horários a partir dessa '
                f'data, ou prefere manter {esc_br_c} como particular? 😊" e emita i="execucao" no $$$. ⛔ PROIBIDO '
                'chamar criar_consulta/criar_consulta_terceiro NESTE turno. ⛔ NUNCA mude a data sozinho.] ' + texto_usuario
            )

    # FIX_66512: gate de convenio na entrada da execucao
    if (base.get("_sub_rota_agenda") == "execucao" and not (base.get("coleta_convenio") or "").strip()
            and not ia_output.get("bypass_agente_humano") and not eh_email_addr and _texto_ia_livre(base)):
        txt_gc = txt_norm
        conv_msg_gc = next((nome for rx, nome in _MAPA_CONVENIO if rx.search(txt_gc)), "")
        reuso_gc = base.get("sessao_intencao") != "confirmacao" and ult_conv_global and bool(re.match(
            r"^(s|si|sim|ok|pode|pode ser|isso|usar|quero usar|vou usar|esse mesmo|o mesmo|mesmo|novamente|manter|"
            r"pode usar)\b",
            txt_gc,
        ))
        if conv_msg_gc or reuso_gc:
            base["coleta_convenio"] = conv_msg_gc or ult_conv_global
            dt_min_c512 = base.get("data_minima_carencia") or ""
            viola_c512 = (
                ult_conv_global and base["coleta_convenio"].lower() == ult_conv_global.lower()
                and re.match(r"^\d{4}-\d{2}-\d{2}$", dt_min_c512) and re.match(r"^\d{4}-\d{2}-\d{2}$", base.get("coleta_data") or "")
                and base["coleta_data"] < dt_min_c512
            )
            if viola_c512:
                min_br_512 = base.get("data_minima_carencia_br") or _br_data(dt_min_c512)
                esc_br_512 = _br_data(base["coleta_data"])
                base["texto_ia"] = (
                    f'[CARENCIA CONVENIO: pelo {base["coleta_convenio"]} a proxima consulta so pode ser a partir de '
                    f'{min_br_512} (carencia) e a data escolhida e {esc_br_512}. Responder EXATAMENTE: "Pelo '
                    f'convênio {base["coleta_convenio"]} sua próxima consulta pode ser a partir de {min_br_512}. '
                    f'Quer que eu busque horários a partir dessa data, ou prefere manter {esc_br_512} como '
                    'particular? 😊" e emita i="execucao" no $$$. ⛔ PROIBIDO chamar criar_consulta/'
                    'criar_consulta_terceiro NESTE turno. ⛔ NUNCA mude a data sozinho.] ' + texto_usuario
                )
            else:
                base["texto_ia"] = (
                    f'[CONVENIO RECEBIDO: conv="{base["coleta_convenio"]}". Salve conv="{base["coleta_convenio"]}" '
                    'no $$$ e continue: se ainda nao temos o email do paciente, pergunte o email AGORA; senao '
                    'chame criar_consulta/criar_consulta_terceiro AGORA com os dados salvos. ⛔ NAO pergunte '
                    'convenio de novo.] ' + texto_usuario
                )
        elif base.get("sessao_intencao") == "confirmacao":
            pergunta_conv_global = base.get("_pergunta_convenio_global") or "A consulta será Particular ou Convênio? 😊"
            base["texto_ia"] = (
                f'[GATE CONVENIO: dados confirmados, mas o convenio nao foi coletado. Responder EXATAMENTE: '
                f'"{pergunta_conv_global}" e emita i="execucao" no $$$. ⛔ PROIBIDO chamar criar_consulta/'
                'criar_consulta_terceiro NESTE turno — so no proximo, apos a resposta.] ' + texto_usuario
            )
        else:
            base["texto_ia"] = (
                '[GATE CONVENIO: o convenio ainda nao foi definido. Responder EXATAMENTE: "A consulta será '
                'Particular ou Convênio? Se convênio, qual? 😊" e emita i="execucao" no $$$. ⛔ PROIBIDO chamar '
                'criar_consulta/criar_consulta_terceiro NESTE turno.] ' + texto_usuario
            )

    # FIX_59124: gate de email deterministico na entrada da execucao
    email_ficha_ge = ((base.get("pacientes") or [{}])[0] or {}).get("email") or ""
    email_conhecido_ge = bool(email_ficha_ge) or bool((base.get("coleta_email") or "").strip())
    if (base.get("_sub_rota_agenda") == "execucao" and not email_conhecido_ge
            and not ia_output.get("bypass_agente_humano") and _texto_ia_livre(base)):
        if eh_resposta_email_fix:
            m_email_ge = re.search(r"[\w.+-]+@[\w.-]+\.[a-z]{2,}", texto_usuario, re.IGNORECASE)
            tool_ge = "criar_consulta_terceiro" if base.get("coleta_terceiro") in ("true", True) else "criar_consulta"
            if m_email_ge:
                base["coleta_email"] = m_email_ge.group(0)
                base["texto_ia"] = (
                    f'[EMAIL RECEBIDO: paciente informou o email {m_email_ge.group(0)}. Chame {tool_ge} AGORA com '
                    f'email_paciente="{m_email_ge.group(0)}" e os dados salvos. Salve email="{m_email_ge.group(0)}" '
                    'no $$$. ⛔ NAO pergunte mais nada antes de criar.] ' + texto_usuario
                )
            else:
                base["texto_ia"] = (
                    f'[SEM EMAIL: paciente nao quer informar email (permitido — ausencia de email NAO e recusa de '
                    f'agendamento). Chame {tool_ge} AGORA com email_paciente="" e os dados salvos. ⛔ NAO insista '
                    'no email.] ' + texto_usuario
                )
        elif base.get("sessao_intencao") == "confirmacao":
            txt_end_ge = txt_norm
            pede_end_ge = bool(re.search(
                r"endereco|onde fica|localiza|como cheg|qual a rua|qual rua|aonde fica|fica aonde|fica onde|"
                r"qual bairro|(passa|manda|qual|e)\s+o\s+local|local da (clinica|consulta|unidade)", txt_end_ge
            ))
            unid_ge = _norm(base.get("coleta_unidade"))
            if "tatuape" in unid_ge:
                end_unid_ge = "📍 Tatuapé — Rua Soriano de Sousa, 189 - Tatuapé, 1° Andar, sala 14."
            elif "olimpia" in unid_ge:
                end_unid_ge = (
                    "📍 Vila Olímpia — Rua Alvorada, 1289 - Vila Olímpia, Condomínio Vila Olímpia Prime Office, "
                    "15°Andar - sala 1508"
                )
            else:
                end_unid_ge = ""
            prefix_end_ge = f'Claro! O endereço é:\n{end_unid_ge}\n\n' if (pede_end_ge and end_unid_ge) else ""
            base["texto_ia"] = (
                f'[GATE EMAIL: dados confirmados, mas nao temos o email do paciente. Responder EXATAMENTE: '
                f'"{prefix_end_ge}Para enviar a confirmação, qual seu email? 😊" e emita i="execucao" no $$$. '
                '⛔ PROIBIDO chamar criar_consulta/criar_consulta_terceiro NESTE turno — so no proximo, apos a '
                'resposta (email ou "nao"/"pular").] ' + texto_usuario
            )

    return ResultadoParte4(base=base, intencao_rapida=intencao_rapida, rota_agente=rota_agente, sub_rota_agenda=sub_rota_agenda)


# ============================================================================
# PARTE 5 (linhas 1947-2461 do JS): troca de unidade/médico, grades, DIA_SEM_UNIDADE
# ============================================================================

_NOMES_DOCS_DETECT = ("giseli", "caio", "elias", "jose", "stephanie", "juliana", "torcuato", "fernanda")

_DOC_FULLNAME = {
    "giseli": "Dra. Giseli Rebechi", "caio": "Dr. Caio Vinicius Saettini", "elias": "Dr. Elias Lobo Braga",
    "jose": "Dr. Jose Emmanuel Burle Neto", "stephanie": "Dra. Stephanie Rugeri de Souza",
    "juliana": "Dra. Juliana Paulino do Amaral", "torcuato": "Dr. Torcuato Sanchez Rojas Neto",
    "fernanda": "Dra. Fernanda Butura Broetto",
}

# Grade só-texto (sem nome do médico) — idêntica no JS entre TROCAR_MEDICO_NOME_DETECT
# (lá chamada _GRADE_TROCA) e FIX_TROCA_UNIDADE_INJECT (lá chamada _GRTXT_TU).
_GRADE_TEXTO = {
    "Vila Olímpia": {
        "giseli": "terça, quarta (só manhã), sexta (só manhã)", "elias": "terça (só tarde), quarta",
        "jose": "segunda, quarta (só manhã), quinta",
        "stephanie": "segunda (manhã: teleconsulta), terça (só manhã — teleconsulta), quarta (só tarde)",
        "juliana": "segunda (só tarde), sexta (só tarde)", "torcuato": "quarta (só tarde), quinta, sexta",
        "fernanda": "quinta (só tarde)", "caio": "terça (só manhã)",
    },
    "Tatuapé": {
        "elias": "segunda, sexta (só manhã)", "jose": "terça", "caio": "quarta", "giseli": "quinta",
        "fernanda": "sexta (só tarde)",
    },
}

_LISTA_MEDICOS_TEXTO = {
    "Vila Olímpia": (
        "Médicos disponíveis em Vila Olímpia:\n👩‍⚕️ Dra. Giseli Rebechi — terça, quarta (só manhã), "
        "sexta (só manhã)\n👨‍⚕️ Dr. Elias Lobo Braga — terça (só tarde), quarta\n👨‍⚕️ Dr. Jose Emmanuel "
        "Burle Neto — segunda, quarta (só manhã), quinta\n👩‍⚕️ Dra. Stephanie Rugeri de Souza — segunda "
        "(manhã: teleconsulta), terça (só manhã — teleconsulta), quarta (só tarde)\n👩‍⚕️ Dra. Juliana "
        "Paulino do Amaral — segunda (só tarde), sexta (só tarde)\n👨‍⚕️ Dr. Torcuato Sanchez Rojas Neto — "
        "quarta (só tarde), quinta, sexta\n👩‍⚕️ Dra. Fernanda Butura Broetto — quinta (só tarde)\n"
        "👨‍⚕️ Dr. Caio Vinicius Saettini — terça (só manhã)\nQual prefere? 😊"
    ),
    "Tatuapé": (
        "Médicos disponíveis em Tatuapé:\n👨‍⚕️ Dr. Elias Lobo Braga — segunda, sexta (só manhã)\n"
        "👨‍⚕️ Dr. Jose Emmanuel Burle Neto — terça\n👨‍⚕️ Dr. Caio Vinicius Saettini — quarta\n"
        "👩‍⚕️ Dra. Giseli Rebechi — quinta\n👩‍⚕️ Dra. Fernanda Butura Broetto — sexta (só tarde)\n"
        "Qual prefere? 😊"
    ),
}

_SO_VO = ("stephanie", "juliana", "torcuato")

# Período (ou 'Ambos') por médico/unidade/dia-abreviado — usado em FIX_TROCA_UNIDADE_DIA.
_DLU_PERIODO = {
    "Vila Olímpia": {
        "giseli": {"ter": "Ambos", "qua": "manha", "sex": "manha"}, "elias": {"ter": "tarde", "qua": "Ambos"},
        "jose": {"seg": "Ambos", "qua": "manha", "qui": "Ambos"}, "stephanie": {"seg": "Ambos", "ter": "manha", "qua": "tarde"},
        "juliana": {"seg": "tarde", "sex": "tarde"}, "torcuato": {"qua": "tarde", "qui": "Ambos", "sex": "Ambos"},
        "fernanda": {"qui": "tarde"}, "caio": {"ter": "manha"},
    },
    "Tatuapé": {
        "elias": {"seg": "Ambos", "sex": "manha"}, "jose": {"ter": "Ambos"}, "caio": {"qua": "Ambos"},
        "giseli": {"qui": "Ambos"}, "fernanda": {"sex": "tarde"},
    },
}

# Existência (1) por médico/unidade/dia-abreviado — usado em FIX_PERGUNTA_DIA_CONFIRM.
_DLU_EXISTE = {
    "Vila Olímpia": {
        "giseli": {"ter": 1, "qua": 1, "sex": 1}, "elias": {"ter": 1, "qua": 1}, "jose": {"seg": 1, "qua": 1, "qui": 1},
        "stephanie": {"seg": 1, "ter": 1, "qua": 1}, "juliana": {"seg": 1, "sex": 1},
        "torcuato": {"qua": 1, "qui": 1, "sex": 1}, "fernanda": {"qui": 1}, "caio": {"ter": 1},
    },
    "Tatuapé": {
        "elias": {"seg": 1, "sex": 1}, "jose": {"ter": 1}, "caio": {"qua": 1}, "giseli": {"qui": 1}, "fernanda": {"sex": 1},
    },
}

_DS_AB = {"segunda": "seg", "terca": "ter", "terça": "ter", "quarta": "qua", "quinta": "qui", "sexta": "sex",
          "seg": "seg", "ter": "ter", "qua": "qua", "qui": "qui", "sex": "sex"}
_DS_DOW = {"segunda": 1, "terca": 2, "terça": 2, "quarta": 3, "quinta": 4, "sexta": 5,
           "seg": 1, "ter": 2, "qua": 3, "qui": 4, "sex": 5}

# Grade médico×unidade×dia com nome completo na frase — usada só no autoswitch Bradesco+Tatuapé.
_GRADE_TEXTO_COM_NOME = {
    "Vila Olímpia": {
        "giseli": "Dra. Giseli Rebechi atende terça, quarta (só manhã), sexta (só manhã)",
        "elias": "Dr. Elias Lobo Braga atende terça (só tarde), quarta",
        "jose": "Dr. Jose Emmanuel Burle Neto atende segunda, quarta (só manhã), quinta",
        "stephanie": "Dra. Stephanie Rugeri de Souza atende segunda (manhã: teleconsulta), terça (só manhã — teleconsulta), quarta (só tarde)",
        "juliana": "Dra. Juliana Paulino do Amaral atende segunda (só tarde), sexta (só tarde)",
        "torcuato": "Dr. Torcuato Sanchez Rojas Neto atende quarta (só tarde), quinta, sexta",
        "fernanda": "Dra. Fernanda Butura Broetto atende quinta (só tarde)",
        "caio": "Dr. Caio Vinicius Saettini atende terça (só manhã)",
    },
    "Tatuapé": {
        "elias": "Dr. Elias Lobo Braga atende segunda, sexta (só manhã)",
        "jose": "Dr. Jose Emmanuel Burle Neto atende terça",
        "caio": "Dr. Caio Vinicius Saettini atende quarta",
        "giseli": "Dra. Giseli Rebechi atende quinta",
        "fernanda": "Dra. Fernanda Butura Broetto atende sexta (só tarde)",
    },
}

_GRADE_DIA_SEM_UNIDADE = {
    "giseli": {"seg": None, "ter": {"u": "Vila Olímpia", "p": "ambos"}, "qua": {"u": "Vila Olímpia", "p": "manha"},
               "qui": {"u": "Tatuapé", "p": "ambos"}, "sex": {"u": "Vila Olímpia", "p": "manha"}},
    "elias": {"seg": {"u": "Tatuapé", "p": "ambos"}, "ter": {"u": "Vila Olímpia", "p": "tarde"},
              "qua": {"u": "Vila Olímpia", "p": "ambos"}, "qui": None, "sex": {"u": "Tatuapé", "p": "manha"}},
    "jose": {"seg": {"u": "Vila Olímpia", "p": "ambos"}, "ter": {"u": "Tatuapé", "p": "ambos"},
             "qua": {"u": "Vila Olímpia", "p": "manha"}, "qui": {"u": "Vila Olímpia", "p": "ambos"}, "sex": None},
    "stephanie": {"seg": {"u": "Vila Olímpia", "p": "ambos"}, "ter": {"u": "Vila Olímpia", "p": "manha"},
                  "qua": {"u": "Vila Olímpia", "p": "tarde"}, "qui": None, "sex": None},
    "juliana": {"seg": {"u": "Vila Olímpia", "p": "tarde"}, "ter": None, "qua": None, "qui": None,
                "sex": {"u": "Vila Olímpia", "p": "tarde"}},
    "torcuato": {"seg": None, "ter": None, "qua": {"u": "Vila Olímpia", "p": "tarde"},
                 "qui": {"u": "Vila Olímpia", "p": "ambos"}, "sex": {"u": "Vila Olímpia", "p": "ambos"}},
    "fernanda": {"seg": None, "ter": None, "qua": None, "qui": {"u": "Vila Olímpia", "p": "tarde"},
                 "sex": {"u": "Tatuapé", "p": "tarde"}},
    "caio": {"seg": None, "ter": {"u": "Vila Olímpia", "p": "manha"}, "qua": {"u": "Tatuapé", "p": "ambos"},
             "qui": None, "sex": None},
}

_NOMES_DSU = {"seg": "segunda", "ter": "terça", "qua": "quarta", "qui": "quinta", "sex": "sexta"}


def _hoje_sp() -> datetime:
    return datetime.now(timezone.utc) - timedelta(hours=3)


def _proxima_data_dow(dow_alvo: int) -> str:
    """Replica `$now.setZone('America/Sao_Paulo')` + diff até o próximo dow_alvo (1=segunda..
    5=sexta, convenção ISO/Luxon .weekday == Python isoweekday()). Nunca retorna hoje (diff
    mínimo 1, igual ao `|| 7` do JS quando diff dá 0)."""
    hj = _hoje_sp()
    diff = (dow_alvo - hj.isoweekday() + 7) % 7
    if diff == 0:
        diff = 7
    return (hj + timedelta(days=diff)).strftime("%Y-%m-%d")


def _medico_key(texto_norm: str) -> str:
    return next((k for k in _NOMES_DOCS_DETECT if k in texto_norm), "")


@dataclass
class ResultadoParte5:
    base: dict
    intencao_rapida: str
    rota_agente: int


def processar_troca_unidade_medico(
    base: dict,
    texto_usuario: str,
    intencao_rapida: str,
    rota_agente: int,
    ia_output: dict,
    eh_cancel_real: bool,
    eh_mensagem_informativa: bool,
) -> ResultadoParte5:
    txt_nav_norm = _norm(texto_usuario)

    # Override: data explícita + cache ativo → força navegação
    eh_data_explicita = bool(re.search(r"\bdia\s*\d{1,2}|\bdo\s*dia\s+\d{1,2}|\b\d{1,2}\/\d{1,2}\b", txt_nav_norm)) \
        or "amanha" in txt_nav_norm
    if base.get("cache_ativo") and eh_data_explicita and not eh_cancel_real and rota_agente != 4:
        ia_output["eh_navegacao"] = True

    # CONF_OVERRIDE_DATA_DIFF: dia pedido != dia do cache em rota=4 → nao tratar como confirmacao
    if base.get("cache_ativo") and eh_data_explicita and rota_agente == 4 and ia_output.get("eh_confirmacao"):
        udi0 = base.get("ultimo_dia_exibido")
        if isinstance(udi0, dict) and udi0.get("data"):
            dia_cache = int(udi0["data"].split("-")[2])
            dia_match = re.search(r"\bdia\s*(\d{1,2})\b", txt_nav_norm) or re.search(r"\bdo\s*dia\s+(\d{1,2})\b", txt_nav_norm)
            if dia_match and int(dia_match.group(1)) != dia_cache:
                ia_output["eh_confirmacao"] = False

    # PROTECAO_NAVEGACAO_SEM_CACHE
    if not base.get("cache_ativo"):
        ia_output["eh_navegacao"] = False

    # PROTECAO_OUTRO_DIA (+ PROTECAO_OUTRO_DIA_CANCEL)
    eh_pede_outro_dia = any(p in txt_nav_norm for p in (
        "outro dia", "outra data", "outra semana", "proxima semana", "semana que vem", "tem outro", "quero outro"
    ))
    if eh_pede_outro_dia and rota_agente == 4:
        ia_output["eh_navegacao"] = False
    if eh_pede_outro_dia and rota_agente == 1 and _int(base.get("sessao_rota")) in (4, 2):
        rota_agente = _int(base.get("sessao_rota"))
        ia_output["rota_agente"] = rota_agente
        ia_output["intencao_rapida"] = base.get("sessao_intencao") or "agenda"

    # Cancelamento sem identidade: exige CPF antes de qualquer acao
    if rota_agente == 1 and not base.get("paciente_encontrado") and not base.get("coleta_id_tisaude"):
        cpf_na_msg = len(re.sub(r"\D", "", str(texto_usuario))) == 11
        tem_cpf_sessao = bool(base.get("cpf_dependente")) and len(re.sub(r"\D", "", str(base["cpf_dependente"]))) == 11
        if not cpf_na_msg and not tem_cpf_sessao:
            base["texto_ia"] = (
                '[CANCELAMENTO SEM IDENTIDADE: contato NAO cadastrado e sem CPF na sessao. ⛔ NAO chame a tool '
                'Cancelar. ⛔ NAO liste nenhuma consulta. ⛔ NAO invente consultas. Responder EXATAMENTE: "Para '
                'localizar sua consulta com seguranca, me informe o seu CPF, por favor. 😊" Aguarde o CPF antes de '
                'qualquer acao.] ' + texto_usuario
            )
            base["_cancel_bloqueado_sem_cpf"] = True

    # TROCAR_MEDICO_DETECT
    eh_troca_medico = any(p in txt_nav_norm for p in (
        "outro medico", "trocar medico", "mudar medico", "mudar o medico", "nao quero esse medico",
        "outro dr", "outra dra", "outro doutor",
    ))
    if eh_troca_medico and (rota_agente == 4 or _int(base.get("sessao_rota")) == 4):
        rota_agente = 3 if base.get("coleta_terceiro") == "true" else 2
        ia_output["rota_agente"] = rota_agente
        ia_output["eh_confirmacao"] = False

    # TROCAR_MEDICO_NOME_DETECT: paciente menciona nome de médico diferente do salvo
    medico_salvo_lower = _norm(base.get("coleta_medico"))
    medico_eh_sem_pref = "sem prefer" in medico_salvo_lower
    tem_hora_msg_tm = bool(re.search(r"\b\d{1,2}\s*h(\s*\d{2})?\b|\b\d{1,2}:\d{2}\b", texto_usuario.lower()))
    if (medico_salvo_lower and not medico_eh_sem_pref and not tem_hora_msg_tm and not eh_troca_medico
            and (rota_agente == 4 or _int(base.get("sessao_rota")) == 4)):
        for m in _NOMES_DOCS_DETECT:
            if m in txt_nav_norm and m not in medico_salvo_lower:
                rota_agente = 3 if base.get("coleta_terceiro") == "true" else 2
                ia_output["rota_agente"] = rota_agente
                ia_output["eh_confirmacao"] = False
                novo_nome = _DOC_FULLNAME.get(m, m)
                base["coleta_medico"] = novo_nome
                base["coleta_modo"] = 3
                base["coleta_dia_semana"] = ""
                base["coleta_data"] = ""
                base["coleta_periodo"] = ""
                base["coleta_horario"] = ""
                base["_clear_pm"] = {**(base.get("_clear_pm") or {}), "dt": 1, "per": 1, "ds": 1, "h": 1}
                unid_troca = base.get("coleta_unidade") or ""
                grade_novo = _GRADE_TEXTO.get(unid_troca, {}).get(m, "")
                if grade_novo:
                    base["texto_ia"] = (
                        f'[TROCA MEDICO: paciente quer {novo_nome} em vez do anterior. Setar med="{novo_nome}", '
                        f'modo=3, limpar dt/per/ds/h no $$$. Responder EXATAMENTE: "{novo_nome} atende {grade_novo}. '
                        'Qual dia prefere? 😊" NAO confirme agendamento. NAO mostre menu inicial.] ' + texto_usuario
                    )
                else:
                    base["texto_ia"] = (
                        f'[TROCA MEDICO: paciente quer {novo_nome}, mas ele NAO atende na {unid_troca}. Setar '
                        f'med="{novo_nome}" no $$$. Informe que ele nao atende nessa unidade e mostre a lista de '
                        'medicos da unidade.] ' + texto_usuario
                    )
                break

    # GUARD_CONFIRMACAO_V2: confirmação só válida com horário explícito ou cache do dia atual
    if ia_output.get("eh_confirmacao"):
        tem_hora_explicita = bool(re.search(r"\b\d{1,2}:\d{2}\b", texto_usuario or ""))
        if not tem_hora_explicita:
            horario_salvo = base.get("coleta_horario") or ""
            if not horario_salvo:
                ia_output["eh_confirmacao"] = False
            else:
                udi1 = base.get("ultimo_dia_exibido")
                if isinstance(udi1, dict) and udi1.get("data") and isinstance(udi1.get("medicos"), list) and udi1["medicos"]:
                    horarios_hoje = (udi1["medicos"][0].get("horarios") or "").split(", ")
                    if horario_salvo not in horarios_hoje:
                        ia_output["eh_confirmacao"] = False

    # FIX_TROCA_UNIDADE_INJECT + FIX_TROCA_UNIDADE_DIA
    if rota_agente in (2, 3, 4) and base.get("coleta_unidade"):
        txt_unid = _strip_accents(texto_usuario)
        unid_atual = base["coleta_unidade"]
        nova_unid = ""
        if ("olimpia" in txt_unid or "olimia" in txt_unid or "vila ol" in txt_unid) and "Ol" not in unid_atual:
            nova_unid = "Vila Olímpia"
        elif "tatua" in txt_unid and "Tatu" not in unid_atual:
            nova_unid = "Tatuapé"

        if nova_unid:
            med_atual = _norm(base.get("coleta_medico"))
            med_invalido = "Tatu" in nova_unid and any(d in med_atual for d in _SO_VO)

            base["coleta_unidade"] = nova_unid
            base["coleta_data"] = ""
            base["coleta_periodo"] = ""
            base["coleta_dia_semana"] = ""
            base["coleta_horario"] = ""
            base["_clear_pm"] = {**(base.get("_clear_pm") or {}), "dt": 1, "per": 1, "ds": 1, "h": 1}
            rota_agente = 3 if base.get("coleta_terceiro") == "true" else 2
            if base.get("coleta_convenio") in ("PART?", "RESET_CONV"):
                base["coleta_convenio"] = ""

            if med_invalido:
                med_ant_tu = base["coleta_medico"]
                base["coleta_medico"] = ""
                base["lista_med"] = _LISTA_MEDICOS_TEXTO[nova_unid]
                base["texto_ia"] = (
                    f'[TROCA UNIDADE: paciente quer {nova_unid} e {med_ant_tu} NAO atende la. Setar '
                    f'unid="{nova_unid}", med="" no $$$. Responder EXATAMENTE:\n"{med_ant_tu} não atende na '
                    f'{nova_unid}. {_LISTA_MEDICOS_TEXTO[nova_unid]}"\n⛔ Copie TODAS as linhas da lista. '
                    '⛔ NAO mostre o menu de unidades.] ' + (base.get("texto_ia") or "")
                )
            else:
                dia_rx_tu = re.search(r"(?:^|\s)(segunda|seg|terca|ter|quarta|qua|quinta|qui|sexta|sex)(?:\s|$|[.,!?])", txt_unid)
                dia_menc = None
                if dia_rx_tu and dia_rx_tu.group(1) in _DS_DOW:
                    ab = _DS_AB[dia_rx_tu.group(1)]
                    dia_menc = {"dow": _DS_DOW[dia_rx_tu.group(1)], "ds": {"seg": "segunda", "ter": "terca", "qua": "quarta", "qui": "quinta", "sex": "sexta"}[ab], "ab": ab}

                if dia_menc and base.get("coleta_medico"):
                    mk = _medico_key(med_atual)
                    lu = _DLU_PERIODO.get(nova_unid, {}).get(mk, {})
                    per = lu.get(dia_menc["ab"])

                    if per:
                        prox = _proxima_data_dow(dia_menc["dow"])
                        if per == "Ambos":
                            base["texto_ia"] = (
                                f'[TROCA UNIDADE + DIA: paciente quer {nova_unid} na {dia_menc["ds"]}. Setar '
                                f'unid="{nova_unid}", dt="{prox}", ds="{dia_menc["ds"]}", modo=2 no $$$. Perguntar: '
                                '"Manha ou tarde? 😊"] ' + (base.get("texto_ia") or "")
                            )
                        else:
                            base["texto_ia"] = (
                                f'[TROCA UNIDADE + DIA + PERIODO: paciente quer {nova_unid} na {dia_menc["ds"]}. '
                                f'Setar unid="{nova_unid}", dt="{prox}", ds="{dia_menc["ds"]}", per="{per}", modo=2 '
                                'no $$$. Perguntar: "A consulta sera Particular ou Convenio? 😊"] ' + (base.get("texto_ia") or "")
                            )
                    else:
                        gr_dia_tu = _GRADE_TEXTO.get(nova_unid, {}).get(mk, "")
                        if gr_dia_tu:
                            base["texto_ia"] = (
                                f'[TROCA UNIDADE: paciente quer {nova_unid} na {dia_menc["ds"]}, mas '
                                f'{base["coleta_medico"]} NAO atende {dia_menc["ds"]} la. Setar unid="{nova_unid}" '
                                f'no $$$. Responder EXATAMENTE: "Na {nova_unid}, {base["coleta_medico"]} atende '
                                f'{gr_dia_tu} — {dia_menc["ds"]} não. Qual dia prefere? 😊" ⛔ NAO mostre menu de '
                                'unidades nem lista de medicos.] ' + (base.get("texto_ia") or "")
                            )
                        else:
                            med_ant_tu2 = base["coleta_medico"]
                            base["coleta_medico"] = ""
                            base["lista_med"] = _LISTA_MEDICOS_TEXTO[nova_unid]
                            base["texto_ia"] = (
                                f'[TROCA UNIDADE: paciente quer {nova_unid} e {med_ant_tu2} NAO atende la. Setar '
                                f'unid="{nova_unid}", med="" no $$$. Responder EXATAMENTE:\n"{med_ant_tu2} não '
                                f'atende na {nova_unid}. {_LISTA_MEDICOS_TEXTO[nova_unid]}"\n⛔ Copie TODAS as '
                                'linhas da lista.] ' + (base.get("texto_ia") or "")
                            )
                else:
                    mk_ger = _medico_key(med_atual)
                    gr_ger_tu = _GRADE_TEXTO.get(nova_unid, {}).get(mk_ger, "") if mk_ger else ""
                    base["lista_med"] = _LISTA_MEDICOS_TEXTO[nova_unid]
                    if gr_ger_tu:
                        base["texto_ia"] = (
                            f'[TROCA UNIDADE: paciente quer {nova_unid} (medico {base["coleta_medico"]} mantido). '
                            f'Setar unid="{nova_unid}", dt="", per="", ds="" no $$$. Responder EXATAMENTE: "Na '
                            f'{nova_unid}, {base["coleta_medico"]} atende {gr_ger_tu}. Qual dia prefere? 😊" ⛔ NAO '
                            'mostre menu de unidades nem lista de medicos.] ' + (base.get("texto_ia") or "")
                        )
                    elif mk_ger:
                        med_ant_tu3 = base["coleta_medico"]
                        base["coleta_medico"] = ""
                        base["texto_ia"] = (
                            f'[TROCA UNIDADE: paciente quer {nova_unid} e {med_ant_tu3} NAO atende la. Setar '
                            f'unid="{nova_unid}", med="" no $$$. Responder EXATAMENTE:\n"{med_ant_tu3} não atende '
                            f'na {nova_unid}. {_LISTA_MEDICOS_TEXTO[nova_unid]}"\n⛔ Copie TODAS as linhas da lista. '
                            '⛔ NAO mostre o menu de unidades.] ' + (base.get("texto_ia") or "")
                        )
                    else:
                        base["texto_ia"] = (
                            f'[TROCA UNIDADE: paciente quer {nova_unid} (sem medico definido). Setar '
                            f'unid="{nova_unid}", dt="", per="", ds="" no $$$. Responder EXATAMENTE:\n'
                            f'"{_LISTA_MEDICOS_TEXTO[nova_unid]}"\n⛔ Copie TODAS as linhas da lista. ⛔ NAO mostre '
                            'o menu de unidades.] ' + (base.get("texto_ia") or "")
                        )

    # FIX_PERGUNTA_DIA_CONFIRM: paciente confirma troca de unidade sugerida anteriormente
    if base.get("coleta_medico") and base.get("coleta_unidade") and (
        ((rota_agente in (2, 3, 4)) and base.get("coleta_dia_semana")) or base.get("sessao_intencao") == "pergunta_troca"
    ):
        txt_pdc = _strip_accents(texto_usuario)
        eh_conf_pdc = any(p in txt_pdc for p in (
            "pode ser", "pode", "sim", "aceito", "ok", "ta bom", "quero", "claro", "bora", "vamos", "muda",
            "trocar", "troca",
        )) or txt_pdc == "s"
        if eh_conf_pdc:
            med_norm_pdc = _norm(base.get("coleta_medico"))
            mk_pdc = _medico_key(med_norm_pdc)
            ds_norm = _norm(base.get("coleta_dia_semana"))
            ab_pdc = _DS_AB.get(ds_norm, "")
            unid_atual_pdc = base["coleta_unidade"]
            outra_unid_pdc = "Tatuapé" if "Vila" in unid_atual_pdc else "Vila Olímpia"
            pdc_switched = False

            if ab_pdc and mk_pdc:
                works_here = bool(_DLU_EXISTE.get(unid_atual_pdc, {}).get(mk_pdc, {}).get(ab_pdc))
                works_other = bool(_DLU_EXISTE.get(outra_unid_pdc, {}).get(mk_pdc, {}).get(ab_pdc))
                if not works_here and works_other:
                    dow = _DS_DOW.get(ds_norm, 4)
                    prox_dt = _proxima_data_dow(dow)
                    base["coleta_unidade"] = outra_unid_pdc
                    base["coleta_data"] = prox_dt
                    base["coleta_horario"] = ""
                    base["intencao_rapida"] = "agenda"
                    rota_agente = 3 if base.get("coleta_terceiro") == "true" else 2
                    base["_autoswitch_fired"] = True
                    pdc_switched = True
                    conv_pdc = _norm(base.get("coleta_convenio"))
                    conv_invalida_nova_unid = "Tatu" in outra_unid_pdc and "bradesco" in conv_pdc
                    if conv_invalida_nova_unid:
                        base["texto_ia"] = (
                            f'[TROCA UNIDADE CONFIRMADA + CONV INVALIDO: Mudou para {outra_unid_pdc} na '
                            f'{base["coleta_dia_semana"]}. Porem {base.get("coleta_convenio")} NAO e aceito no '
                            f'{outra_unid_pdc}. Responder EXATAMENTE: "Mudamos para o {outra_unid_pdc} na '
                            f'{base["coleta_dia_semana"]}! Porem, {base.get("coleta_convenio")} nao e aceito no '
                            f'{outra_unid_pdc}. Deseja mudar o convenio ou agendar como Particular? 😊" Setar '
                            f'unid="{outra_unid_pdc}", dt="{prox_dt}", ds="{base["coleta_dia_semana"]}" no $$$. '
                            f'Manter conv="{base.get("coleta_convenio")}". Aguarde resposta.] ' + (base.get("texto_ia") or "")
                        )
                    else:
                        base["texto_ia"] = (
                            f'[TROCA UNIDADE CONFIRMADA: Paciente aceitou mudar para {outra_unid_pdc} na '
                            f'{base["coleta_dia_semana"]}. Setar unid="{outra_unid_pdc}", dt="{prox_dt}", '
                            f'ds="{base["coleta_dia_semana"]}" no $$$. Se periodo vazio, Responder EXATAMENTE: '
                            '"Manha ou tarde? 😊" (⛔ NAO cite data exata/dia do mes — so depois do buscar_agenda). '
                            'Se periodo preenchido, perguntar convenio.] ' + (base.get("texto_ia") or "")
                        )

            if not pdc_switched and base.get("sessao_intencao") == "pergunta_troca":
                base["coleta_unidade"] = outra_unid_pdc
                base["coleta_dia_semana"] = ""
                base["coleta_data"] = ""
                base["coleta_horario"] = ""
                base["intencao_rapida"] = "agenda"
                rota_agente = 3 if base.get("coleta_terceiro") == "true" else 2
                base["_autoswitch_fired"] = True
                conv_ptk = _norm(base.get("coleta_convenio"))
                conv_invalida_ptk = "Tatu" in outra_unid_pdc and "bradesco" in conv_ptk
                if conv_invalida_ptk:
                    base["texto_ia"] = (
                        f'[TROCA UNIDADE CONFIRMADA + CONV INVALIDO: Mudou para {outra_unid_pdc}. Porem '
                        f'{base.get("coleta_convenio")} NAO e aceito no {outra_unid_pdc}. Responder EXATAMENTE: '
                        f'"Mudamos para o {outra_unid_pdc}! Porem, {base.get("coleta_convenio")} nao e aceito no '
                        f'{outra_unid_pdc}. Deseja mudar o convenio ou agendar como Particular? 😊" Setar '
                        f'unid="{outra_unid_pdc}" no $$$. Aguarde resposta.] ' + (base.get("texto_ia") or "")
                    )
                else:
                    base["texto_ia"] = (
                        f'[TROCA UNIDADE CONFIRMADA: Paciente aceitou mudar para {outra_unid_pdc}. Setar '
                        f'unid="{outra_unid_pdc}" no $$$. Perguntar qual dia prefere. Se periodo vazio, perguntar '
                        'tambem "Manha ou tarde? 😊".] ' + (base.get("texto_ia") or "")
                    )

    # FIX_BRADESCO_TA_AUTOSWITCH + FIX_AUTOSWITCH_3CAMINHOS
    if (rota_agente in (2, 3, 4) and not base.get("_autoswitch_fired")
            and not ia_output.get("bypass_agente_humano") and _texto_ia_livre(base)
            and base.get("coleta_unidade") and "Tatu" in base["coleta_unidade"]
            and base.get("coleta_convenio") and "bradesco" in base["coleta_convenio"].lower()):
        txt_as = _strip_accents(texto_usuario)
        conv_original = base["coleta_convenio"]
        eh_mudar_unidade = any(p in txt_as for p in (
            "olimpia", "olimia", "vila ol", "mudar unidade", "trocar unidade", "mudar a unidade", "trocar a unidade"
        )) or txt_as == "1"
        eh_mudar_conv = any(p in txt_as for p in (
            "porto", "itau", "particular", "mudar convenio", "trocar convenio", "mudar o convenio",
            "trocar o convenio", "outro convenio", "atendente", "humano",
        )) or txt_as == "2"
        eh_conf_generico = not eh_mudar_unidade and not eh_mudar_conv and (
            any(p in txt_as for p in ("pode ser", "pode", "sim", "aceito", "ok", "ta bom", "quero", "claro", "bora", "vamos"))
            or txt_as == "s"
        )

        if eh_mudar_unidade:
            base["coleta_unidade"] = "Vila Olímpia"
            base["coleta_data"] = ""
            base["coleta_periodo"] = ""
            base["coleta_dia_semana"] = ""
            base["coleta_horario"] = ""
            rota_agente = 3 if base.get("coleta_terceiro") == "true" else 2
            base["_autoswitch_fired"] = True
            mn = _norm(base.get("coleta_medico"))
            mk_bt = _medico_key(mn)
            resp_bt = f'{_GRADE_TEXTO_COM_NOME["Vila Olímpia"][mk_bt]}, qual dia prefere? 😊' if mk_bt else ""
            if resp_bt:
                base["texto_ia"] = (
                    f'[TROCA UNIDADE ACEITA] Resposta EXATA: "{resp_bt}". Setar unid="Vila Olimpia", '
                    f'conv="{conv_original}", dt="", per="", ds="" no $$$. ' + (base.get("texto_ia") or "")
                )
            else:
                base["texto_ia"] = (
                    '[TROCA UNIDADE ACEITA] Medico nao atende na Vila Olimpia. Mostre LISTA_MED de [DADOS_MED]. '
                    f'Setar unid="Vila Olimpia", conv="{conv_original}", med="" no $$$. ' + (base.get("texto_ia") or "")
                )
        elif eh_mudar_conv:
            base["_autoswitch_fired"] = True
            ia_output["bypass_agente_humano"] = True
            intencao_rapida = "humano"
            base["motivo_humano"] = "Bradesco no Tatuape: pediu particular/outro convenio ou atendente"
            base["texto_ia"] = (
                '[TRANSFERIR HUMANO (Bradesco Tatuape): paciente pediu particular/outro convenio ou atendente. '
                'REGRA DA CLINICA: quem tem Bradesco NAO pode ser atendido como particular nem trocar de convenio '
                'pelo bot. Responder EXATAMENTE: "Claro! Vou te passar para um atendente para te ajudar 😊" e '
                'emitir i="humano", motivo="Bradesco só na Vila Olímpia — pediu particular/outro convênio/'
                'atendente". NAO mude conv/unid no $$$.] ' + (base.get("texto_ia") or "")
            )
        elif eh_conf_generico:
            rota_agente = 3 if base.get("coleta_terceiro") == "true" else 2
            base["_autoswitch_fired"] = True
            base["texto_ia"] = (
                '[BRADESCO TATUAPE REASK: Paciente disse "sim" mas nao especificou. Responder EXATAMENTE: "O que '
                'prefere?\n1️⃣ Agendar na Vila Olímpia\n2️⃣ Falar com um atendente" NAO mude nada no $$$. NAO '
                'aceite Bradesco no Tatuape. NAO ofereça outro convenio nem particular. Aguarde resposta.] ' + (base.get("texto_ia") or "")
            )

    # FIX_BRADESCO_TA_DETERMINISTIC
    if (rota_agente in (2, 3, 4) and base.get("coleta_unidade") and "Tatu" in base["coleta_unidade"]
            and (not base.get("coleta_convenio") or base.get("coleta_convenio") in ("RESET_CONV", "PART?"))):
        txt_conv_d = _strip_accents(texto_usuario)
        conv_detectado = "Bradesco" if ("bradesco" in txt_conv_d or "brad" in txt_conv_d) else ""
        if conv_detectado:
            base["texto_ia"] = (
                f'[CONVENIO {conv_detectado} RESTRITO — SO VILA OLIMPIA. Responder EXATAMENTE: "O {conv_detectado} '
                'é atendido só na unidade Vila Olímpia 😊 O que prefere?\n1️⃣ Agendar na Vila Olímpia\n2️⃣ Falar '
                f'com um atendente" Setar conv="{conv_detectado}" no $$$. REGRA DA CLINICA: NAO mostrar info de '
                'Particular. NAO ofereça outro convenio. NAO dizer "nao atendemos pelo ' + conv_detectado + '".] '
                + (base.get("texto_ia") or "")
            )

    # FIX_DIA_SEM_UNIDADE (58335, remarcação)
    txt_dsu = txt_nav_norm
    rota_dsu = rota_agente in (2, 3) or _int(base.get("sessao_rota")) in (2, 3)
    med_key_dsu = _medico_key(_norm(base.get("coleta_medico")))
    dia_dsu = ""
    if re.search(r"segunda|\bseg\b", txt_dsu):
        dia_dsu = "seg"
    elif re.search(r"terca|\bter\b", txt_dsu):
        dia_dsu = "ter"
    elif re.search(r"quarta|\bqua\b", txt_dsu):
        dia_dsu = "qua"
    elif re.search(r"quinta|\bqui\b", txt_dsu):
        dia_dsu = "qui"
    elif re.search(r"sexta|\bsex\b", txt_dsu):
        dia_dsu = "sex"
    eh_fds_dsu = bool(re.search(r"sabado|domingo|fim de semana", txt_dsu))
    if (rota_dsu and med_key_dsu and not (base.get("coleta_unidade") or "").strip()
            and (dia_dsu or eh_fds_dsu) and not re.search(r"vila|tatu", txt_dsu)
            and not eh_cancel_real and not eh_mensagem_informativa
            and not ia_output.get("bypass_agente_humano") and _texto_ia_livre(base)):
        med_nome_dsu = base["coleta_medico"]
        if eh_fds_dsu:
            base["texto_ia"] = (
                '[DIA FIM DE SEMANA: nao atendemos sabado/domingo. Responder EXATAMENTE: "Atendemos de segunda a '
                'sexta 😊 Qual dia prefere?" NAO mude nada no $$$.] ' + texto_usuario
            )
        else:
            slot_dsu = _GRADE_DIA_SEM_UNIDADE.get(med_key_dsu, {}).get(dia_dsu)
            if not slot_dsu:
                dias_ok_dsu = ", ".join(
                    _NOMES_DSU[d] for d in ("seg", "ter", "qua", "qui", "sex")
                    if _GRADE_DIA_SEM_UNIDADE.get(med_key_dsu, {}).get(d)
                )
                base["texto_ia"] = (
                    f'[DIA INVALIDO P/ MEDICO: {med_nome_dsu} NAO atende {_NOMES_DSU[dia_dsu]}. Responder '
                    f'EXATAMENTE: "{med_nome_dsu} atende {dias_ok_dsu}. Qual dia prefere? 😊" NAO mude dt/ds no '
                    '$$$.] ' + texto_usuario
                )
            else:
                unid_dsu = slot_dsu["u"]
                dt_dsu = base.get("prox_" + dia_dsu) or ""
                per_salvo_dsu = (base.get("coleta_periodo") or "").lower()
                base["coleta_unidade"] = unid_dsu
                base["coleta_data"] = dt_dsu
                base["coleta_dia_semana"] = "terca" if dia_dsu == "ter" else _NOMES_DSU[dia_dsu]
                if per_salvo_dsu and slot_dsu["p"] != "ambos" and per_salvo_dsu != slot_dsu["p"]:
                    per_fmt_dsu = "de manhã" if slot_dsu["p"] == "manha" else "à tarde"
                    base["texto_ia"] = (
                        f'[DIA COM PERIODO RESTRITO: na {_NOMES_DSU[dia_dsu]}, {med_nome_dsu} atende SO '
                        f'{per_fmt_dsu} (na {unid_dsu}), e o paciente tinha pedido {per_salvo_dsu}. Setar '
                        f'unid="{unid_dsu}", dt="{dt_dsu}", ds="{base["coleta_dia_semana"]}" no $$$ (NAO mude per '
                        f'ainda). Responder EXATAMENTE: "Na {_NOMES_DSU[dia_dsu]} {med_nome_dsu} atende só '
                        f'{per_fmt_dsu}. Pode ser, ou prefere outro dia? 😊"] ' + texto_usuario
                    )
                else:
                    per_final_dsu = per_salvo_dsu or (slot_dsu["p"] if slot_dsu["p"] != "ambos" else "")
                    if per_final_dsu:
                        if not per_salvo_dsu:
                            base["coleta_periodo"] = per_final_dsu
                        conv_ok_dsu = bool((base.get("coleta_convenio") or "").strip()) and base.get("coleta_convenio") not in ("PART?", "OMINT?", "RESET_CONV")
                        if conv_ok_dsu:
                            rota_agente = 4
                            base["_sub_rota_agenda"] = "navegacao"
                            intencao_rapida = "agenda"
                            base["texto_ia"] = (
                                f'[DIA SEM UNIDADE RESOLVIDO → BUSCA: {med_nome_dsu} atende {_NOMES_DSU[dia_dsu]} '
                                f'na {unid_dsu}. unid="{unid_dsu}", dt="{dt_dsu}", ds="{base["coleta_dia_semana"]}", '
                                f'per="{per_final_dsu}", modo=3. Busque os horarios e mostre APENAS os retornados. '
                                '⛔ NUNCA invente horarios.] ' + texto_usuario
                            )
                        else:
                            per_fmt2 = " de manhã" if per_final_dsu == "manha" else " à tarde"
                            base["texto_ia"] = (
                                f'[DIA SEM UNIDADE RESOLVIDO: {med_nome_dsu} atende {_NOMES_DSU[dia_dsu]} na '
                                f'{unid_dsu}. Setar unid="{unid_dsu}", dt="{dt_dsu}", ds="{base["coleta_dia_semana"]}", '
                                f'per="{per_final_dsu}" no $$$. Responder EXATAMENTE: "Perfeito, {_NOMES_DSU[dia_dsu]} '
                                f'na {unid_dsu}{per_fmt2}! A consulta será Particular ou Convênio? 😊" ⛔ NAO chame '
                                'buscar_agenda ainda (falta convenio). ⛔ NAO cite dia do mes.] ' + texto_usuario
                            )
                    else:
                        base["texto_ia"] = (
                            f'[DIA SEM UNIDADE RESOLVIDO: {med_nome_dsu} atende {_NOMES_DSU[dia_dsu]} na {unid_dsu} '
                            f'(manha e tarde). Setar unid="{unid_dsu}", dt="{dt_dsu}", ds="{base["coleta_dia_semana"]}" '
                            f'no $$$. Responder EXATAMENTE: "Perfeito, {_NOMES_DSU[dia_dsu]} na {unid_dsu}! Manhã ou '
                            'tarde? 😊" NAO chame buscar_agenda ainda.] ' + texto_usuario
                        )

    # FIX_PERIODO_OBRIGATORIO
    if (rota_agente in (2, 3) and base.get("coleta_medico") and not base.get("coleta_periodo")
            and not base.get("coleta_data") and not base.get("_autoswitch_fired")):
        txt_po = _strip_accents(texto_usuario)
        eh_conf_po = any(p in txt_po for p in (
            "pode ser", "pode", "sim", "aceito", "ok", "ta bom", "quero", "claro", "bora"
        )) or txt_po == "s"
        if eh_conf_po:
            ds_salvo = _norm(base.get("coleta_dia_semana"))
            dow_po = {"segunda": 1, "terca": 2, "quarta": 3, "quinta": 4, "sexta": 5}.get(ds_salvo)
            dt_inject = ""
            if dow_po:
                prox_po = _proxima_data_dow(dow_po)
                base["coleta_data"] = prox_po
                dt_inject = f' Setar dt="{prox_po}" e ds="{base["coleta_dia_semana"]}" no $$$.'
            base["texto_ia"] = (
                f'[PERIODO OBRIGATORIO: coleta_periodo esta vazio. Dia ja confirmado.{dt_inject} Responder '
                'EXATAMENTE: "Manha ou tarde? 😊" NAO pergunte dia. NAO pergunte convenio.] ' + (base.get("texto_ia") or "")
            )

    # FIX_CONV_OBRIGATORIO
    if (rota_agente in (2, 3) and base.get("coleta_medico") and base.get("coleta_data")
            and (not base.get("coleta_convenio") or base.get("coleta_convenio") == "RESET_CONV")
            and not base.get("_autoswitch_fired")):
        txt_convo = _strip_accents(texto_usuario)
        eh_periodo_resp = any(p in txt_convo for p in ("manha", "tarde", "manhã"))
        if eh_periodo_resp:
            base["texto_ia"] = (
                '[CONVENIO OBRIGATORIO: Paciente escolheu periodo. coleta_convenio esta vazio. Responder '
                'EXATAMENTE: "A consulta sera Particular ou Convenio? 😊" NAO assuma Particular. NAO chame '
                'buscar_agenda. Aguarde resposta.] ' + (base.get("texto_ia") or "")
            )

    return ResultadoParte5(base=base, intencao_rapida=intencao_rapida, rota_agente=rota_agente)


# ============================================================================
# PARTE 6 (linhas 2462-2792 do JS): para mim, cancelamento auto, médico/dia/período
# ============================================================================

_ATALHO_MED = (
    {"p": "caio", "unid": "Vila Olímpia", "per": "manha", "ds": "terca"},
    {"p": "fernanda", "unid": "Vila Olímpia", "per": "tarde", "ds": "quinta"},
    {"p": "fernanda", "unid": "Tatuapé", "per": "tarde", "ds": "sexta"},
)


def _levenshtein(a: str, b: str) -> int:
    m, n = len(a), len(b)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(m + 1):
        dp[i][0] = i
    for j in range(n + 1):
        dp[0][j] = j
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            dp[i][j] = min(dp[i - 1][j] + 1, dp[i][j - 1] + 1, dp[i - 1][j - 1] + (0 if a[i - 1] == b[j - 1] else 1))
    return dp[m][n]


def _match_medico_key(texto: str, keys) -> str:
    """Match exato por substring; senão, fuzzy por Levenshtein (tolera até 2 erros) — o paciente
    digita 'Stephany'/'Estefania' etc e ainda casa com a chave 'stephanie'."""
    t = _norm(texto)
    keys = list(keys)
    exato = next((k for k in keys if k in t), None)
    if exato:
        return exato
    best, bd = None, 99
    for w in t.split():
        if len(w) < 4:
            continue
        for k in keys:
            if abs(len(w) - len(k)) > 2:
                continue
            d = _levenshtein(w, k)
            if d < bd:
                bd, best = d, k
    return best if (best and bd <= 2) else ""


_MED_DIAS = {
    "Tatuapé": {
        "giseli": [{"ds": "quinta", "per": "Ambos", "nome": "Dra. Giseli Rebechi"}],
        "jose": [{"ds": "terca", "per": "Ambos", "nome": "Dr. Jose Emmanuel Burle Neto"}],
        "caio": [{"ds": "quarta", "per": "Ambos", "nome": "Dr. Caio Vinicius Saettini"}],
        "fernanda": [{"ds": "sexta", "per": "tarde", "nome": "Dra. Fernanda Butura Broetto"}],
        "elias": [{"ds": "segunda", "per": "Ambos", "nome": "Dr. Elias Lobo Braga"},
                  {"ds": "sexta", "per": "manha", "nome": "Dr. Elias Lobo Braga"}],
    },
    "Vila Olímpia": {
        "caio": [{"ds": "terca", "per": "manha", "nome": "Dr. Caio Vinicius Saettini"}],
        "fernanda": [{"ds": "quinta", "per": "tarde", "nome": "Dra. Fernanda Butura Broetto"}],
    },
}
_DS_DISPLAY = {"segunda": "segunda", "terca": "terça", "quarta": "quarta", "quinta": "quinta", "sexta": "sexta"}
_DS_DOW_UD = {"segunda": 1, "terca": 2, "quarta": 3, "quinta": 4, "sexta": 5}

_GRADE_MD = {
    "Vila Olímpia": {
        "giseli": "terça (manhã e tarde), quarta (só manhã), sexta (só manhã)",
        "elias": "terça (só tarde), quarta (manhã e tarde)",
        "jose": "segunda (manhã e tarde), quarta (só manhã), quinta (manhã e tarde)",
        "stephanie": "segunda (manhã: teleconsulta / tarde: presencial), terça (só manhã — teleconsulta), quarta (só tarde)",
        "juliana": "segunda (só tarde), sexta (só tarde)",
        "torcuato": "quarta (só tarde), quinta (manhã e tarde), sexta (manhã e tarde)",
        "fernanda": "quinta (só tarde)", "caio": "terça (só manhã)",
    },
    "Tatuapé": {
        "elias": "segunda (manhã e tarde), sexta (só manhã)", "jose": "terça", "caio": "quarta",
        "giseli": "quinta", "fernanda": "sexta (só tarde)",
    },
}
_NDIAS_MD = {
    "Vila Olímpia": {"giseli": 3, "elias": 2, "jose": 3, "stephanie": 3, "juliana": 2, "torcuato": 3, "fernanda": 1, "caio": 1},
    "Tatuapé": {"elias": 2, "jose": 1, "caio": 1, "giseli": 1, "fernanda": 1},
}
_FULL_MD = {
    "giseli": "Dra. Giseli Rebechi", "caio": "Dr. Caio Vinicius Saettini", "elias": "Dr. Elias Lobo Braga",
    "jose": "Dr. Jose Emmanuel Burle Neto", "stephanie": "Dra. Stephanie Rugeri de Souza",
    "juliana": "Dra. Juliana Paulino do Amaral", "torcuato": "Dr. Torcuato Sanchez Rojas Neto",
    "fernanda": "Dra. Fernanda Butura Broetto",
}

_PD_UNICO = {
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
_DIAS_PI = (
    (("segunda", "seg"), "segunda"), (("terca", "ter"), "terça"), (("quarta", "qua"), "quarta"),
    (("quinta", "qui"), "quinta"), (("sexta", "sex"), "sexta"),
)

_GRADE_DP = {
    "Vila Olímpia": {
        "giseli": {"ter": ["manha", "tarde"], "qua": ["manha"], "sex": ["manha"]},
        "elias": {"ter": ["tarde"], "qua": ["manha", "tarde"]},
        "jose": {"seg": ["manha", "tarde"], "qua": ["manha"], "qui": ["manha", "tarde"]},
        "stephanie": {"seg": ["manha", "tarde"], "ter": ["manha"], "qua": ["tarde"]},
        "juliana": {"seg": ["tarde"], "sex": ["tarde"]},
        "torcuato": {"qua": ["tarde"], "qui": ["manha", "tarde"], "sex": ["manha", "tarde"]},
        "fernanda": {"qui": ["tarde"]}, "caio": {"ter": ["manha"]},
    },
    "Tatuapé": {
        "elias": {"seg": ["manha", "tarde"], "sex": ["manha"]}, "jose": {"ter": ["manha", "tarde"]},
        "caio": {"qua": ["manha", "tarde"]}, "giseli": {"qui": ["manha", "tarde"]}, "fernanda": {"sex": ["tarde"]},
    },
}
_DS_FULL_DP = {"seg": "segunda", "ter": "terça", "qua": "quarta", "qui": "quinta", "sex": "sexta"}
_DS_DOW_DP = {"seg": 1, "ter": 2, "qua": 3, "qui": 4, "sex": 5}
_DIAS_DP = (
    ("seg", ("segunda", "seg")), ("ter", ("terca", "terça", "ter")), ("qua", ("quarta", "qua")),
    ("qui", ("quinta", "qui")), ("sex", ("sexta", "sex")),
)


@dataclass
class ResultadoParte6:
    base: dict
    intencao_rapida: str
    rota_agente: int


def processar_medico_dia_periodo(
    base: dict,
    texto_usuario: str,
    intencao_rapida: str,
    rota_agente: int,
    ia_output: dict,
    identidade_incompleta: bool,
) -> ResultadoParte6:
    # FIX_PARA_MIM (51195/51272)
    if (rota_agente in (2, 3) and base.get("pacientes") and base.get("coleta_terceiro") != "true"
            and not base.get("coleta_unidade")):
        txt_pm = _norm(texto_usuario)
        eh_para_mim_expl = bool(re.match(
            r"^(para mim|pra mim|e para mim|e pra mim|sou eu|eu mesmo|eu mesma|comigo|para min|pra min|eu)$", txt_pm
        )) or any(f in txt_pm for f in ("para mim", "pra mim", "sou eu", "e comigo"))
        eh_para_mim = eh_para_mim_expl or txt_pm in AFIRMACOES_TITULAR
        pacientes = base["pacientes"]
        pac_pm = None
        if len(pacientes) == 1:
            pac_pm = pacientes[0]
        elif eh_para_mim_expl:
            if base.get("id_tisaude"):
                pac_pm = next((p for p in pacientes if str(p.get("id_tisaude")) == str(base["id_tisaude"])), None)
            if not pac_pm and base.get("cpf"):
                pac_pm = next((p for p in pacientes if p.get("cpf") == base["cpf"]), None)
        if eh_para_mim and pac_pm:
            base["nome_dependente"] = pac_pm.get("nome") or ""
            base["cpf_dependente"] = pac_pm.get("cpf") or ""
            base["nascimento_dependente"] = pac_pm.get("nascimento") or ""
            base["coleta_terceiro"] = "false"
            base["coleta_id_tisaude"] = str(pac_pm.get("id_tisaude") or base.get("coleta_id_tisaude") or "")
            base["_quem_resolvido_turno"] = True
            base["texto_ia"] = (
                f'[QUEM CONFIRMADO TITULAR: a consulta e para o proprio titular {pac_pm.get("nome", "")}. d/c/n JA '
                'preenchidos. ⛔ NAO peca nome, CPF nem nascimento. Va DIRETO ao P2 (unidade). Responder EXATAMENTE: '
                '"Temos dois endereços de atendimento, qual a melhor unidade para você?\nDigite o número '
                'correspondente:\n\n1️⃣ Vila Olímpia\n2️⃣ Tatuapé"] ' + texto_usuario
            )

    # FIX_CANCELAMENTO_PACIENTE_AUTO
    if rota_agente == 1 and base.get("pacientes") and len(base["pacientes"]) == 1 and not base.get("nome_dependente"):
        pac_c = base["pacientes"][0]
        base["nome_dependente"] = pac_c.get("nome") or ""
        base["cpf_dependente"] = pac_c.get("cpf") or ""
        base["nascimento_dependente"] = pac_c.get("nascimento") or ""
        base["coleta_id_tisaude"] = str(pac_c.get("id_tisaude") or "")

    # FIX_CANCELAMENTO_QUEM_SKIP
    if rota_agente == 1 and base.get("nome_dependente") and "[QUEM CONFIRMADO" not in (base.get("texto_ia") or ""):
        tag_base_c = (
            f'[QUEM CONFIRMADO: cancelamento para {base["nome_dependente"]} '
            f'(cpf: {base.get("cpf_dependente") or ""}). t=false, d="{base["nome_dependente"]}". '
            '⛔ NAO pergunte "para quem e".'
        )
        if base.get("sessao_intencao") != "cancelando":
            base["texto_ia"] = tag_base_c + ' Continue o fluxo de cancelamento.] ' + (base.get("texto_ia") or texto_usuario)
        else:
            base["texto_ia"] = tag_base_c + ' ⛔ NAO reliste as consultas. Continue o fluxo de onde parou.] ' + (base.get("texto_ia") or texto_usuario)

    # FIX_RECUSA_CANCELAMENTO (54141) / FIX_65588
    if rota_agente == 1 and base.get("sessao_intencao") == "cancelando":
        txt_cancel_norm = _strip_accents(texto_usuario)
        recusa_cancel = bool(re.match(
            r"^(nao|n|nope|desisto|esquece|deixa pra la|nao quero|nao precisa|pode deixar|ta bom|tudo bem|ok|"
            r"cancela nao|nao cancela)$",
            txt_cancel_norm.strip(),
        )) or bool(re.search(
            r"\b(nao quero cancelar|desisti de cancelar|nao cancela|nao preciso cancelar|pode deixar|"
            r"esquece o cancelamento)\b",
            txt_cancel_norm,
        ))
        ja_resolveu_cancel = not recusa_cancel and bool(re.search(
            r"\b(ja consegui|ja resolvi|ja cancelei|consegui cancelar|consegui resolver|ja foi|ja esta tudo certo|"
            r"ja esta certo|ja esta resolvido|ja resolvido|nao precisa mais|ja nao preciso)\b",
            txt_cancel_norm.lower(),
        ))
        if recusa_cancel:
            intencao_rapida = "concluido"
            base["texto_ia"] = (
                '[RECUSA CANCELAMENTO: paciente decidiu NAO cancelar. Diga APENAS: "Tudo bem, sua consulta não foi '
                'cancelada! Se precisar é só chamar 😊" Encerre sem perguntar mais nada e sem listar consultas.] '
                + (base.get("texto_ia") or "")
            )
        elif ja_resolveu_cancel:
            intencao_rapida = "concluido"
            base["texto_ia"] = (
                '[ENCERRAMENTO CANCELAMENTO RESOLVIDO: paciente ja resolveu por conta propria e esta se despedindo. '
                'Responda APENAS: "Que bom! 😊 Precisando de algo é só chamar!" ⛔ NAO liste consultas. ⛔ NAO '
                'pergunte nada. ⛔ NAO chame ferramentas.] ' + (base.get("texto_ia") or "")
            )

    # FIX_MEDICO_ATALHO_INJECT
    if (rota_agente in (2, 3) and not base.get("coleta_medico") and base.get("coleta_unidade")
            and not base.get("coleta_periodo") and _texto_ia_livre(base)):
        msg_med = _norm(texto_usuario)
        unid = base["coleta_unidade"]
        match_med = next((a for a in _ATALHO_MED if a["p"] in msg_med and unid == a["unid"]), None)
        if match_med:
            base["texto_ia"] = (
                f'[ATALHO MEDICO: {match_med["p"]} em {unid}. Periodo UNICO: {match_med["per"]}. Setar '
                f'per={match_med["per"]} e ds={match_med["ds"]} no $$$. NAO pergunte periodo. Va direto ao '
                'convenio: Particular ou Convenio?] ' + (base.get("texto_ia") or "")
            )

    # FIX_MEDICO_UNICO_DIA
    if (rota_agente in (2, 3) and base.get("coleta_unidade")
            and (base.get("coleta_medico") or base.get("coleta_modo") in (3, 2) or not base.get("coleta_modo"))
            and not base.get("coleta_dia_semana") and (not base.get("coleta_data") or not base.get("coleta_medico"))):
        med_norm_ud = _norm(base.get("coleta_medico") or texto_usuario)
        unid_ud = base["coleta_unidade"]
        uni_dias = _MED_DIAS.get(unid_ud, {})
        mk_ud = _match_medico_key(med_norm_ud, uni_dias.keys())
        if mk_ud and len(uni_dias[mk_ud]) == 1:
            d = uni_dias[mk_ud][0]
            prox_dt_ud = _proxima_data_dow(_DS_DOW_UD[d["ds"]])
            base["coleta_dia_semana"] = d["ds"]
            base["coleta_data"] = prox_dt_ud
            base["coleta_medico"] = d["nome"]
            if d["per"] != "Ambos":
                base["coleta_periodo"] = d["per"]
                base["_dia_periodo_resolvido"] = True
                pergunta_conv = base.get("_pergunta_convenio_global") or "A consulta será Particular ou Convênio? 😊"
                base["texto_ia"] = (
                    f'[MEDICO DIA+PERIODO UNICO: {d["nome"]} atende {_DS_DISPLAY[d["ds"]]} (so {d["per"]}) no '
                    f'{unid_ud}. Setar ds="{d["ds"]}", dt="{prox_dt_ud}", per="{d["per"]}", med="{d["nome"]}", '
                    f'modo=3 no $$$. Responder EXATAMENTE: "{pergunta_conv}" NAO pergunte periodo.] '
                    + (base.get("texto_ia") or texto_usuario)
                )
            else:
                base["coleta_periodo"] = ""
                base["texto_ia"] = (
                    f'[MEDICO DIA UNICO: {d["nome"]} atende {_DS_DISPLAY[d["ds"]]} no {unid_ud}. Setar '
                    f'ds="{d["ds"]}", dt="{prox_dt_ud}", med="{d["nome"]}", modo=3 no $$$. Responder EXATAMENTE: '
                    f'"A {d["nome"]} atende somente {_DS_DISPLAY[d["ds"]]} no {unid_ud}. Deseja manha ou tarde? 😊" '
                    'NAO pergunte dia.] ' + (base.get("texto_ia") or texto_usuario)
                )

    # FIX_MEDICO_MULTI_DIA
    if (rota_agente in (2, 3) and base.get("coleta_unidade")
            and (base.get("coleta_modo") in (3, 2) or not base.get("coleta_modo"))
            and not base.get("coleta_medico") and not base.get("coleta_dia_semana")):
        med_txt_md = _norm(texto_usuario)
        unid_md = base["coleta_unidade"]
        grade_unit_md = _GRADE_MD.get(unid_md, {})
        ndias_unit_md = _NDIAS_MD.get(unid_md, {})
        mk_md = _match_medico_key(med_txt_md, grade_unit_md.keys())
        if mk_md and ndias_unit_md.get(mk_md, 0) > 1:
            base["coleta_medico"] = _FULL_MD[mk_md]
            base["coleta_data"] = ""
            base["coleta_periodo"] = ""
            base["texto_ia"] = (
                f'[MEDICO MULTI DIA: {_FULL_MD[mk_md]} atende {grade_unit_md[mk_md]} no {unid_md}. Setar '
                f'med="{_FULL_MD[mk_md]}", modo=3, limpar dt/per no $$$. Responder EXATAMENTE: '
                f'"{_FULL_MD[mk_md]} atende {grade_unit_md[mk_md]}. Qual dia prefere? 😊" NAO assuma dia. NAO va '
                'pro horario.] ' + texto_usuario
            )

    # FIX_PERIODO_INJECT
    if rota_agente in (2, 3):
        med_salvo = base.get("coleta_medico") or ""
        unid_salva = base.get("coleta_unidade") or ""
        per_salvo = base.get("coleta_periodo") or ""
        if med_salvo and unid_salva and not per_salvo:
            txt_norm_pi = _strip_accents(texto_usuario)
            dia_mencionado = ""
            for prefixos, nome in _DIAS_PI:
                if any(p in txt_norm_pi for p in prefixos):
                    dia_mencionado = nome
                    break
            if dia_mencionado:
                chave = f"{med_salvo}||{unid_salva}||{dia_mencionado}"
                per_auto = _PD_UNICO.get(chave)
                if per_auto:
                    base["_dia_periodo_resolvido"] = True
                    base["texto_ia"] = (
                        f"[PERIODO UNICO: {per_auto}. NAO pergunte periodo, use direto no $$$. Va ao convenio.] "
                        + (base.get("texto_ia") or "")
                    )

    # FIX_DIA_PERIODO_DETERMINISTICO (51006)
    if (rota_agente in (2, 3) and base.get("coleta_unidade") and base.get("coleta_medico")
            and base.get("coleta_medico") not in ("sem preferencia", "__CLEAR__")
            and (not base.get("coleta_data") or not base.get("coleta_periodo"))):
        txt_dp = _norm(texto_usuario)
        uk_dp = "Tatuapé" if "Tatu" in base["coleta_unidade"] else "Vila Olímpia"
        med_ndp = _norm(base["coleta_medico"])
        grade_udp = _GRADE_DP.get(uk_dp, {})
        mk_dp = next((k for k in grade_udp if k in med_ndp), None)

        dia_dp = ""
        for ab, prefixos in _DIAS_DP:
            if any(p in txt_dp for p in prefixos):
                dia_dp = ab
                break
        per_dp = ""
        txt_per_dp = txt_dp.replace("boa tarde", " ").replace("boa noite", " ").replace("bom dia", " ")
        if re.search(r"\bmanha\b|de manha|pela manha|cedo", txt_per_dp):
            per_dp = "manha"
        elif re.search(r"\btarde\b|de tarde|pela tarde|a tarde", txt_per_dp):
            per_dp = "tarde"

        if mk_dp:
            dias_med = grade_udp.get(mk_dp, {})
            if dia_dp:
                pers_do_dia = dias_med.get(dia_dp)
                if not pers_do_dia:
                    base["coleta_data"] = ""
                    base["coleta_dia_semana"] = ""
                    dias_validos = ", ".join(_DS_FULL_DP[k] for k in dias_med)
                    base["texto_ia"] = (
                        f'[DIA INVALIDO MEDICO: {base["coleta_medico"]} nao atende {_DS_FULL_DP.get(dia_dp, dia_dp)} '
                        f'no {uk_dp}. Atende: {dias_validos}. Responder EXATAMENTE: "{base["coleta_medico"]} atende '
                        f'{dias_validos}. Qual dia prefere? 😊" NAO grave data.] ' + (base.get("texto_ia") or texto_usuario)
                    )
                else:
                    base["coleta_data"] = _proxima_data_dow(_DS_DOW_DP[dia_dp])
                    base["coleta_dia_semana"] = _DS_FULL_DP[dia_dp]
                    per_ef_dp = per_dp or (base.get("coleta_periodo") if base.get("coleta_periodo") in ("manha", "tarde") else "")
                    per_final_dp = pers_do_dia[0] if len(pers_do_dia) == 1 else (per_ef_dp if per_ef_dp in pers_do_dia else "")
                    conv_ok_dp = bool(base.get("coleta_convenio")) and base.get("coleta_convenio") not in ("PART?", "OMINT?", "RESET_CONV")
                    if per_final_dp:
                        aviso_dp = (
                            f'Nesse dia {base["coleta_medico"]} atende só pela '
                            f'{"manhã" if per_final_dp == "manha" else "tarde"} — deixei anotado. '
                        ) if (len(pers_do_dia) == 1 and per_ef_dp and per_ef_dp != pers_do_dia[0]) else ""
                        so_txt_dp = f' (so {per_final_dp})' if len(pers_do_dia) == 1 else f' pela {per_final_dp}'
                        base["coleta_periodo"] = per_final_dp
                        base["_dia_periodo_resolvido"] = True
                        if conv_ok_dp and not identidade_incompleta:
                            rota_agente = 4
                            base["_sub_rota_agenda"] = "navegacao"
                            intencao_rapida = "agenda"
                            base["texto_ia"] = (
                                f'[DIA+PERIODO RESOLVIDO: {base["coleta_medico"]} em {_DS_FULL_DP[dia_dp]}{so_txt_dp} '
                                f'no {uk_dp} — coleta COMPLETA. dt="{base["coleta_data"]}", ds="{_DS_FULL_DP[dia_dp]}", '
                                f'per="{per_final_dp}", modo=3, i="agenda" no $$$. Chame buscar_agenda AGORA com '
                                f'unid="{base["coleta_unidade"]}", med="{base["coleta_medico"]}", '
                                f'dt="{base["coleta_data"]}", per="{per_final_dp}" e mostre os horarios que a TOOL '
                                'retornar. ' + (f'Antes dos horarios, diga: "{aviso_dp.strip()}". ' if aviso_dp else "")
                                + f'⛔ NUNCA invente horarios. ⛔ NAO pergunte convenio (ja salvo: '
                                f'{base.get("coleta_convenio")}).] ' + (base.get("texto_ia") or texto_usuario)
                            )
                        else:
                            pergunta_conv2 = base.get("_pergunta_convenio_global") or "A consulta será Particular ou Convênio? 😊"
                            base["texto_ia"] = (
                                f'[DIA+PERIODO RESOLVIDO: {base["coleta_medico"]} em {_DS_FULL_DP[dia_dp]}{so_txt_dp} '
                                f'no {uk_dp}. dt="{base["coleta_data"]}", ds="{_DS_FULL_DP[dia_dp]}", '
                                f'per="{per_final_dp}", modo=3 no $$$. Responder EXATAMENTE: "{aviso_dp}'
                                f'{pergunta_conv2}" NAO pergunte periodo nem dia.] ' + (base.get("texto_ia") or texto_usuario)
                            )
                    else:
                        base["coleta_periodo"] = ""
                        base["texto_ia"] = (
                            f'[DIA RESOLVIDO, FALTA PERIODO: {base["coleta_medico"]} em {_DS_FULL_DP[dia_dp]} no '
                            f'{uk_dp}. dt="{base["coleta_data"]}", ds="{_DS_FULL_DP[dia_dp]}", modo=3 no $$$. '
                            'Responder EXATAMENTE: "Manha ou tarde? 😊" NAO pergunte dia. NAO pergunte convenio. '
                            '⛔ NAO cite data exata/dia do mes (so depois do buscar_agenda).] '
                            + (base.get("texto_ia") or texto_usuario)
                        )
            elif per_dp and base.get("coleta_data") and base.get("coleta_dia_semana") and not base.get("coleta_periodo"):
                ds_salvo_dp = (base.get("coleta_dia_semana") or "")[:3]
                pers_do_dia_s = dias_med.get(ds_salvo_dp)
                if pers_do_dia_s and per_dp in pers_do_dia_s:
                    base["coleta_periodo"] = per_dp
                    base["_dia_periodo_resolvido"] = True
                    pergunta_conv3 = base.get("_pergunta_convenio_global") or "A consulta será Particular ou Convênio? 😊"
                    base["texto_ia"] = (
                        f'[PERIODO RESOLVIDO: {per_dp} valido para {base["coleta_medico"]}. per="{per_dp}" no $$$. '
                        f'Responder EXATAMENTE: "{pergunta_conv3}" NAO pergunte periodo.] '
                        + (base.get("texto_ia") or texto_usuario)
                    )

    return ResultadoParte6(base=base, intencao_rapida=intencao_rapida, rota_agente=rota_agente)


# ============================================================================
# PARTE 7 (linhas 2794-3055 do JS): dia negado, cross-unit, pergunta dia, troca período
# ============================================================================

_AB_DISPLAY = {"seg": "segunda", "ter": "terça", "qua": "quarta", "qui": "quinta", "sex": "sexta"}

_DIAS_DCU = (
    (("segunda", "seg"), "seg", "segunda"),
    (("terca", "ter", "terça"), "ter", "terça"),
    (("quarta", "qua"), "qua", "quarta"),
    (("quinta", "qui"), "qui", "quinta"),
    (("sexta", "sex"), "sex", "sexta"),
)


def _dia_nao_negado_ok(txt: str, pat: str):
    """FIX_64577: 1º dia da mensagem que NÃO está negado. 'Não posso na terça... tem quarta?'
    tem que achar 'quarta', não 'terça' (o primeiro match ingênuo pegaria terça)."""
    g = re.compile(r"(?:^|\s)(" + pat + r")(?=\s|$|[.,!?;])")
    for m in g.finditer(txt):
        a = txt[max(0, m.start() - 25):m.start()]
        d = txt[m.end():m.end() + 12]
        if re.search(r"\bn(ao)?\b[^.,!?;]{0,20}$", a) or re.match(r"^\s*n(ao)?\b", d):
            continue
        return m
    return None


@dataclass
class ResultadoParte7:
    base: dict
    intencao_rapida: str
    rota_agente: int


def processar_dia_periodo_avancado(
    base: dict,
    texto_usuario: str,
    intencao_rapida: str,
    rota_agente: int,
    ia_output: dict,
) -> ResultadoParte7:
    # FIX_DIA_CROSS_UNIT (63549/64577)
    if (rota_agente in (2, 3) and base.get("coleta_medico") and base.get("coleta_medico") != "sem preferencia"
            and base.get("coleta_unidade") and not base.get("coleta_dia_semana") and _texto_ia_livre(base)):
        txt_dcu = _norm(texto_usuario)
        dia_dcu = None
        for prefixos, ab, disp in _DIAS_DCU:
            if any(_dia_nao_negado_ok(txt_dcu, p) for p in prefixos):
                dia_dcu = (ab, disp)
                break
        if dia_dcu:
            ab_dcu, disp_dcu = dia_dcu
            mk_dcu = _medico_key(_norm(base.get("coleta_medico")))
            unid_dcu = base["coleta_unidade"]
            outra_dcu = "Tatuapé" if "Vila" in unid_dcu else "Vila Olímpia"
            atende_atual_dcu = bool(_DLU_PERIODO.get(unid_dcu, {}).get(mk_dcu, {}).get(ab_dcu))
            atende_outra_dcu = bool(_DLU_PERIODO.get(outra_dcu, {}).get(mk_dcu, {}).get(ab_dcu))
            if not atende_atual_dcu and atende_outra_dcu:
                per_outra = _DLU_PERIODO[outra_dcu][mk_dcu][ab_dcu]
                per_txt = "manhã e tarde" if per_outra == "Ambos" else per_outra
                base["coleta_dia_semana"] = ab_dcu
                intencao_rapida = "pergunta_troca"
                base["intencao_rapida"] = "pergunta_troca"
                base["texto_ia"] = (
                    f'[MEDICO DIA OUTRA UNIDADE: {base["coleta_medico"]} nao atende {disp_dcu} na {unid_dcu}, mas '
                    f'atende {disp_dcu} ({per_txt}) no {outra_dcu}. Responder EXATAMENTE: "{base["coleta_medico"]} '
                    f'nao atende {disp_dcu}-feira na {unid_dcu}, mas atende no {outra_dcu}. Deseja mudar de '
                    'unidade ou escolher outro dia? 😊" NAO mude unid/med/conv no $$$. Aguarde resposta.] '
                    + (base.get("texto_ia") or "")
                )
            elif mk_dcu and not atende_atual_dcu and not atende_outra_dcu:
                grade_dcu = ", ".join(_AB_DISPLAY[d] for d in _DLU_PERIODO.get(unid_dcu, {}).get(mk_dcu, {}))
                base["texto_ia"] = (
                    f'[MEDICO DIA NENHUMA UNIDADE: {base["coleta_medico"]} nao atende {disp_dcu} em nenhuma '
                    f'unidade. Responder EXATAMENTE: "{base["coleta_medico"]} nao atende {disp_dcu}-feira. Na '
                    f'{unid_dcu} atende {grade_dcu}. Qual dia prefere? 😊" NAO mude nada no $$$.] '
                    + (base.get("texto_ia") or "")
                )

    # FIX_ATENDENTE_SUBSTRING: "atendente" contem "atende" — evitar falso-positivo
    eh_pergunta_dia = (
        not re.search(r"atendente", texto_usuario, re.IGNORECASE)
        and base.get("coleta_medico") != "sem preferencia"
        and any(p in texto_usuario for p in (
            "atende", "tem vaga", "tem horario", "trabalha", "tem na ", "tem segunda", "tem terca", "tem terça",
            "tem quarta", "tem quinta", "tem sexta",
        ))
    )
    if eh_pergunta_dia:
        ia_output["eh_navegacao"] = False
        if rota_agente == 4:
            rota_agente = 3 if base.get("coleta_terceiro") == "true" else 2

    # FIX_PERGUNTA_DIA: "atende [dia]?" — checa as duas unidades
    if eh_pergunta_dia and base.get("coleta_medico") and base.get("coleta_medico") != "sem preferencia" and base.get("coleta_unidade"):
        txt_pd = _strip_accents(texto_usuario)
        dia_rx_pd = _dia_nao_negado_ok(txt_pd, "segunda|seg|terca|ter|quarta|qua|quinta|qui|sexta|sex")
        dm_pd = {"segunda": 1, "seg": 1, "terca": 2, "ter": 2, "quarta": 3, "qua": 3, "quinta": 4, "qui": 4, "sexta": 5, "sex": 5}
        dns_pd = {"segunda": "segunda", "seg": "segunda", "terca": "terça", "ter": "terça", "quarta": "quarta",
                   "qua": "quarta", "quinta": "quinta", "qui": "quinta", "sexta": "sexta", "sex": "sexta"}
        dab_pd = {"segunda": "seg", "seg": "seg", "terca": "ter", "ter": "ter", "quarta": "qua", "qua": "qua",
                   "quinta": "qui", "qui": "qui", "sexta": "sex", "sex": "sex"}

        med_norm = _norm(base.get("coleta_medico"))
        med_key = _medico_key(med_norm)
        unid_atual = base["coleta_unidade"]
        outra_unid = "Tatuapé" if "Vila" in unid_atual else "Vila Olímpia"
        med_nome_display = base["coleta_medico"]

        if dia_rx_pd and dia_rx_pd.group(1) in dm_pd:
            dia_pd = {"ds": dns_pd[dia_rx_pd.group(1)], "ab": dab_pd[dia_rx_pd.group(1)]}
            atende_atual = bool(_DLU_PERIODO.get(unid_atual, {}).get(med_key, {}).get(dia_pd["ab"]))
            atende_outra = bool(_DLU_PERIODO.get(outra_unid, {}).get(med_key, {}).get(dia_pd["ab"]))

            if atende_atual:
                prox_pd = _proxima_data_dow(dm_pd[dia_rx_pd.group(1)])
                per_pd = _DLU_PERIODO[unid_atual][med_key][dia_pd["ab"]]
                rota_agente = 4
                base["_sub_rota_agenda"] = "navegacao"
                intencao_rapida = "agenda"
                base["coleta_dia_semana"] = dia_pd["ab"]
                base["coleta_data"] = prox_pd
                base["coleta_horario"] = ""
                if per_pd == "Ambos":
                    base["texto_ia"] = (
                        f'[TROCA DIA: paciente quer {dia_pd["ds"]} ({prox_pd}). No $$$ use EXATAMENTE dt="{prox_pd}", '
                        f'ds="{dia_pd["ds"]}", modo=2. ⛔ NAO calcule outra data, NAO use a data anterior. Pergunte: '
                        '"Manha ou tarde? 😊"] ' + (base.get("texto_ia") or "")
                    )
                else:
                    base["texto_ia"] = (
                        f'[TROCA DIA: paciente quer {dia_pd["ds"]} (a partir de {prox_pd}), periodo {per_pd}. '
                        f'Chame buscar_agenda com dt="{prox_pd}", per="{per_pd}". ⚠️ A tool PODE retornar uma data '
                        f'POSTERIOR se {prox_pd} nao tiver vaga — mostre a DATA e os horarios que a TOOL retornar. '
                        '⛔ NUNCA diga que nao ha vaga se a tool retornou horarios. ⛔ NAO invente horarios. No $$$ '
                        f'use o dt que a TOOL retornou (pode nao ser {prox_pd}), per="{per_pd}", modo=2.] '
                        + (base.get("texto_ia") or "")
                    )
            elif atende_outra:
                base["coleta_dia_semana"] = dia_pd["ds"]
                intencao_rapida = "pergunta_troca"
                base["intencao_rapida"] = "pergunta_troca"
                base["texto_ia"] = (
                    f'[PERGUNTA DIA: {med_nome_display} NAO atende {dia_pd["ds"]} na {unid_atual}, mas atende no '
                    f'{outra_unid}. Responder EXATAMENTE: "{med_nome_display} nao atende {dia_pd["ds"]} na '
                    f'{unid_atual}, mas atende no {outra_unid}. Deseja mudar a consulta para la? 😊" Setar '
                    f'ds="{dia_pd["ds"]}" no $$$. NAO mude os demais campos (unid/dt/per/conv). Aguarde '
                    'confirmacao.] ' + (base.get("texto_ia") or "")
                )
            elif med_key:
                grade_current = ", ".join(_AB_DISPLAY[d] for d in _DLU_PERIODO.get(unid_atual, {}).get(med_key, {}))
                base["texto_ia"] = (
                    f'[PERGUNTA DIA: {med_nome_display} NAO atende {dia_pd["ds"]} em nenhuma unidade. Responder '
                    f'EXATAMENTE: "{med_nome_display} nao atende {dia_pd["ds"]}. Na {unid_atual} ela atende '
                    f'{grade_current}. Qual dia prefere? 😊" NAO mude nada no $$$.] ' + (base.get("texto_ia") or "")
                )
        else:
            grade_map = _GRADE_TEXTO["Vila Olímpia"] if "Vila" in unid_atual else _GRADE_TEXTO["Tatuapé"]
            dias_med_gen = grade_map.get(med_key, "")
            if dias_med_gen:
                base["texto_ia"] = (
                    '[PERGUNTA DIA GENERICA: Paciente perguntou dias de atendimento. Responder EXATAMENTE: '
                    f'"{med_nome_display} atende {dias_med_gen}. Qual dia prefere? 😊" NAO mude nada no $$$.]  '
                    + (base.get("texto_ia") or "")
                )

    # FIX_TROCA_PERIODO: pediu periodo diferente do salvo → invalida cache
    if rota_agente == 4 and base.get("cache_ativo"):
        txt_tp = _norm(texto_usuario)
        per_atual = (base.get("coleta_periodo") or "").lower()
        novo_per = ""
        if any(p in txt_tp for p in ("tarde", "a tarde", "de tarde", "pela tarde")) and per_atual == "manha":
            novo_per = "tarde"
        elif any(p in txt_tp for p in ("manha", "de manha", "pela manha")) and per_atual == "tarde":
            novo_per = "manha"
        if novo_per:
            base["coleta_periodo"] = novo_per
            ia_output["eh_navegacao"] = False
            udi_tp = base.get("ultimo_dia_exibido")
            data_base_tp = udi_tp.get("data") if isinstance(udi_tp, dict) and udi_tp.get("data") else (base.get("coleta_data") or "")
            base["eh_troca_data"] = True
            base["data_alvo_troca"] = data_base_tp
            base["medico_troca"] = "sem preferencia" if (_int(base.get("coleta_modo")) == 1 or not base.get("coleta_medico")) else base["coleta_medico"]

    # FIX_PROXIMO_HORARIO (C3)
    if rota_agente in (2, 3, 4) and base.get("coleta_medico") and base.get("coleta_unidade") and _texto_ia_livre(base):
        txt_ph = _norm(texto_usuario)
        eh_prox_horario = any(p in txt_ph for p in (
            "proximo horario", "proxima horario", "primeiro horario", "primeira horario", "qualquer horario",
            "proximo disponivel", "primeiro disponivel", "proxima vaga", "primeira vaga", "qualquer vaga",
        ))
        if eh_prox_horario:
            base["coleta_periodo"] = ""
            base["texto_ia"] = (
                f'[PROXIMO HORARIO DISPONIVEL: paciente quer o primeiro horario disponivel com '
                f'{base["coleta_medico"]}. Chame buscar_agenda SEM periodo (per="") para ver manha e tarde. Se '
                'FILTRO_SEM_RESULTADO, chame buscar_agenda de novo SEM dia_semana e SEM periodo antes de dizer '
                'que nao ha vagas. NAO restrinja por periodo. Setar per="" no $$$.] ' + (base.get("texto_ia") or "")
            )

    # FIX_DIA_SEMANA_INJECT (+ FIX_TROCA_PERIODO_GRADE + FIX_DIA_CROSS_UNIT_INJECT aninhados)
    if rota_agente == 4 and not eh_pergunta_dia and _texto_ia_livre(base):
        txt_ds = _norm(base.get("texto_ia") or "")
        dia_map = {"segunda": 1, "seg": 1, "terca": 2, "ter": 2, "quarta": 3, "qua": 3, "quinta": 4, "qui": 4, "sexta": 5, "sex": 5}
        dia_nome_map = {"segunda": "segunda", "seg": "segunda", "terca": "terca", "ter": "terca", "quarta": "quarta",
                         "qua": "quarta", "quinta": "quinta", "qui": "quinta", "sexta": "sexta", "sex": "sexta"}
        dia_rx = _dia_nao_negado_ok(txt_ds, "segunda|seg|terca|ter|quarta|qua|quinta|qui|sexta|sex")
        dia_sem_det = None
        if dia_rx and dia_rx.group(1) in dia_map:
            dia_sem_det = {"dow": dia_map[dia_rx.group(1)], "nome": dia_nome_map[dia_rx.group(1)]}

        if dia_sem_det:
            prox_data = _proxima_data_dow(dia_sem_det["dow"])
            med_busca = "sem preferencia" if (_int(base.get("coleta_modo")) == 1 or not base.get("coleta_medico")) else base["coleta_medico"]
            base["eh_troca_data"] = True
            base["data_alvo_troca"] = prox_data
            base["dia_semana_troca"] = dia_sem_det["nome"]
            base["medico_troca"] = med_busca

            ds_ab_per = {"segunda": "seg", "terca": "ter", "quarta": "qua", "quinta": "qui", "sexta": "sex"}
            ab_per = ds_ab_per.get(dia_sem_det["nome"])
            mk_per = _medico_key(_norm(base.get("coleta_medico")))
            menc_per_ds = re.search(r"\b(manha|tarde)\b", txt_ds)
            grade_per = _DLU_PERIODO.get(base.get("coleta_unidade"), {}).get(mk_per, {}).get(ab_per) if (mk_per and ab_per) else None
            if menc_per_ds:
                base["coleta_periodo"] = menc_per_ds.group(1)
            elif grade_per in ("manha", "tarde"):
                base["coleta_periodo"] = grade_per
            elif grade_per == "Ambos" and not base.get("coleta_periodo"):
                base["coleta_periodo"] = "manha"

            # FIX_DIA_CROSS_UNIT_INJECT
            if base.get("coleta_medico") and base.get("coleta_unidade") and _int(base.get("coleta_modo")) != 1 and _texto_ia_livre(base):
                ab_dsi = ds_ab_per.get(dia_sem_det["nome"])
                mk_dsi = _medico_key(_norm(base.get("coleta_medico")))
                unid_atual_dsi = base["coleta_unidade"]
                outra_unid_dsi = "Tatuapé" if "Vila" in unid_atual_dsi else "Vila Olímpia"
                if ab_dsi and mk_dsi:
                    works_here_dsi = bool(_DLU_EXISTE.get(unid_atual_dsi, {}).get(mk_dsi, {}).get(ab_dsi))
                    works_other_dsi = bool(_DLU_EXISTE.get(outra_unid_dsi, {}).get(mk_dsi, {}).get(ab_dsi))
                    if not works_here_dsi and works_other_dsi:
                        rota_agente = 3 if base.get("coleta_terceiro") == "true" else 2
                        base["eh_troca_data"] = False
                        base["data_alvo_troca"] = ""
                        base["coleta_dia_semana"] = ab_dsi
                        intencao_rapida = "pergunta_troca"
                        base["intencao_rapida"] = "pergunta_troca"
                        base["texto_ia"] = (
                            f'[PERGUNTA DIA: {base["coleta_medico"]} nao atende {dia_sem_det["nome"]} na '
                            f'{unid_atual_dsi}, mas atende {dia_sem_det["nome"]} no {outra_unid_dsi}. Responder '
                            f'EXATAMENTE: "{base["coleta_medico"]} nao atende {dia_sem_det["nome"]} na '
                            f'{unid_atual_dsi}, mas atende {dia_sem_det["nome"]} no {outra_unid_dsi}. Deseja mudar '
                            f'a consulta para la? 😊" Setar ds="{ab_dsi}" no $$$. NAO mude os demais campos '
                            '(unid/dt/per/conv). Aguarde confirmacao.] ' + texto_usuario
                        )
                    elif not works_here_dsi and not works_other_dsi:
                        gr_med_dsi = base.get("grade_med") or ""
                        mk_grade_dsi = next((l for l in gr_med_dsi.split("\n") if mk_dsi in l.lower()), "")
                        rota_agente = 3 if base.get("coleta_terceiro") == "true" else 2
                        base["eh_troca_data"] = False
                        base["data_alvo_troca"] = ""
                        base["texto_ia"] = (
                            f'[DIA INVALIDO: {base["coleta_medico"]} nao atende {dia_sem_det["nome"]} em nenhuma '
                            'unidade. Informar dias disponiveis. '
                            + (f'Grade: {mk_grade_dsi.strip()}' if mk_grade_dsi else "") + '] ' + texto_usuario
                        )

    return ResultadoParte7(base=base, intencao_rapida=intencao_rapida, rota_agente=rota_agente)


# ---------------------------------------------------------------------------------------------
# PARTE 8 (linhas 3056-3469)
# ---------------------------------------------------------------------------------------------

_NOMES_DOCS_NMO = ("giseli", "elias", "jose", "stephanie", "juliana", "torcuato", "fernanda", "caio")

_BLOCK_P1 = [
    "agendar", "agendamento", "consulta", "retorno", "marcar", "agenda", "particular", "convenio",
    "conhecer", "quero", "queria", "gostaria", "preciso", "hoje", "amanha", "segunda", "terca", "quarta",
    "quinta", "sexta", "sabado", "domingo", "manha", "tarde", "noite", "olimpia", "tatuape", "primeiro",
    "especialista", "obrigado", "obrigada", "outra", "outro", "pessoa", "mesmo", "mesma", "cancelar", "remarcar",
]

_EH_OUTRA_FASE_UI_RX = (
    r"\bmanha\b|\btarde\b|\bnoite\b|segunda|terca|quarta|quinta|sexta|sabado|domingo|amanha|giseli|elias|"
    r"emmanuel|stephanie|juliana|torcuato|fernanda|\bcaio\b|\bjose\b|medic[oa]|doutor|\bdra?\b|\bfilhos?\b|"
    r"\bfilhas?\b|\bmarido\b|\besposas?\b|\besposos?\b|\bmae\b|\bpai\b|\bnetos?\b|\bnetas?\b|\birmaos?\b|"
    r"\birmas?\b|\bsogras?\b|\bsogros?\b|\btias?\b|\btios?\b|\bprimas?\b|\bprimos?\b|outra pessoa|terceiro"
)


def _ymd_overflow(ano: int, mes: int, dia: int) -> date:
    """Replica o overflow de `new Date(ano, mes-1, dia)`: mes/dia fora do range rolam pro
    mes/ano seguinte via aritmetica de calendario (mes aqui e 1-indexado, ao contrario do JS)."""
    ano += (mes - 1) // 12
    mes = (mes - 1) % 12 + 1
    return date(ano, mes, 1) + timedelta(days=dia - 1)


def _computar_data_precompute(hoje: date, dia: int) -> str:
    dt = _ymd_overflow(hoje.year, hoje.month, dia)
    if dt < hoje:
        dt = _ymd_overflow(hoje.year, hoje.month + 1, dia)
    return dt.strftime("%Y-%m-%d")


def _eh_resposta_email_fix(texto_usuario: str) -> bool:
    txt_email_norm2 = re.sub(r"[!.?]", "", _norm(texto_usuario))
    padroes_email_fix = ("n tenho", "nao tenho", "nao tenho email", "pular", "sem email")
    eh_email_addr = bool(re.search(r"[\w.+-]+@[\w.-]+\.[a-z]{2,}", texto_usuario, re.IGNORECASE))
    return any(p in txt_email_norm2 for p in padroes_email_fix) or eh_email_addr


@dataclass
class ResultadoParte8:
    base: dict
    intencao_rapida: str
    rota_agente: int


def processar_menu_unidade_medico(
    base: dict,
    texto_usuario: str,
    intencao_rapida: str,
    rota_agente: int,
    ia_output: dict,
    eh_cancel_real: bool,
    esta_em_agenda_ativa: bool,
) -> ResultadoParte8:
    """Linhas 3056-3469 do JS fonte: menu "sem vagas" (3 opções, com detecção de dia no
    catch-all), pré-computo determinístico de data/horário a partir de números soltos no
    texto_ia, detecção de nome não cadastrado na etapa P1 (força fluxo terceiro), menu de
    unidade (via "1"/"2" ou texto livre — duas variantes quase idênticas), limpeza de resíduo
    zumbi terceiro==titular, e resposta determinística "mesmo médico da última vez?"."""

    # FIX_NAV_MENU_OPTIONS: menu "sem vagas" (3 opções) — trata cada opção + catch-all
    sem_dia_exibido_nmo = not base.get("ultimo_dia_exibido") or (
        isinstance(base.get("ultimo_dia_exibido"), dict) and not base["ultimo_dia_exibido"]
    )
    bare_menu_nmo = texto_usuario.strip() in ("1", "2", "3") and not (base.get("coleta_horario") or "").strip()
    if (
        rota_agente == 4
        and base.get("_sub_rota_agenda") == "navegacao"
        and base.get("cache_ativo")
        and (sem_dia_exibido_nmo or bare_menu_nmo)
        and _texto_ia_livre(base)
    ):
        txt_nmo = texto_usuario.strip()
        if txt_nmo == "1":
            base["coleta_medico"] = "__CLEAR__"
            base["coleta_dia_semana"] = ""
            base["coleta_data"] = ""
            rota_agente = 3 if base.get("coleta_terceiro") == "true" else 2
            base["texto_ia"] = (
                '[TROCAR MEDICO MENU: paciente escolheu buscar outro medico. Setar med="__CLEAR__", ds="", '
                'dt="" no $$$. Responder EXATAMENTE: "Com qual médico você prefere?\\nDigite o número ou '
                'escreva:\\n\\n1️⃣ Primeiro horário disponível\\n2️⃣ Escolher especialista\\n3️⃣ Já tenho médico '
                'de preferência" NAO mostre lista de medicos ainda.] ' + texto_usuario
            )
        elif txt_nmo == "2":
            med_norm_nmo = _norm(base.get("coleta_medico") or "")
            mk_nmo = next((k for k in _NOMES_DOCS_NMO if k in med_norm_nmo), "")
            grade_msg_nmo = ""
            if mk_nmo and base.get("grade_med"):
                for gl in base["grade_med"].split("\n"):
                    if mk_nmo in _norm(gl):
                        qm = re.search(r'"([^"]+)"', gl)
                        if qm:
                            grade_msg_nmo = qm.group(1)
                        break
            base["coleta_dia_semana"] = ""
            base["coleta_data"] = ""
            if grade_msg_nmo:
                base["texto_ia"] = (
                    f'[VER OUTROS DIAS: paciente quer ver outros dias para {base.get("coleta_medico") or "o medico"}. '
                    f'Responder EXATAMENTE: "{grade_msg_nmo}" Setar ds="" e dt="" no $$$. NAO chame buscar_agenda. '
                    'Aguarde escolha do dia.] ' + texto_usuario
                )
            else:
                base["texto_ia"] = (
                    '[VER OUTROS DIAS: paciente quer ver outros dias. Responder: "Qual dia da semana prefere? 😊" '
                    'Setar ds="" e dt="" no $$$. NAO chame buscar_agenda. Aguarde escolha.] ' + texto_usuario
                )
        elif txt_nmo == "3":
            base["texto_ia"] = (
                '[PROCURAR ADIANTE: paciente quer buscar horarios em datas mais distantes. Usar buscar_agenda '
                'com data mais adiante. Manter medico e unidade atuais.] ' + texto_usuario
            )
        else:
            txt_nmo_norm = _norm(txt_nmo)
            dias_map_nmo = (
                ("segunda", "seg", 1), ("terca", "ter", 2), ("quarta", "qua", 3), ("quinta", "qui", 4),
                ("sexta", "sex", 5), ("seg", "seg", 1), ("ter", "ter", 2), ("qua", "qua", 3), ("qui", "qui", 4),
                ("sex", "sex", 5),
            )
            dia_detectado = None
            for dn, ab, dow in dias_map_nmo:
                if _dia_nao_negado_ok(txt_nmo_norm, dn):
                    dia_detectado = {"nome": dn, "ab": ab, "dow": dow}
                    break
            if dia_detectado and base.get("coleta_medico"):
                med_norm_dia = _norm(base.get("coleta_medico") or "")
                mk_dia = next((k for k in _NOMES_DOCS_NMO if k in med_norm_dia), "")
                unid_atual_dia = base.get("coleta_unidade") or "Vila Olímpia"
                outra_unid_dia = "Tatuapé" if "Vila" in unid_atual_dia else "Vila Olímpia"
                works_here_dia = bool(_DLU_EXISTE.get(unid_atual_dia, {}).get(mk_dia, {}).get(dia_detectado["ab"]))
                works_other_dia = bool(_DLU_EXISTE.get(outra_unid_dia, {}).get(mk_dia, {}).get(dia_detectado["ab"]))
                med_nome_display = base["coleta_medico"]
                ds_nome_full = _AB_DISPLAY.get(dia_detectado["ab"], dia_detectado["nome"])

                if works_here_dia:
                    prox_dt_dia = _proxima_data_dow(dia_detectado["dow"])
                    base["coleta_dia_semana"] = ds_nome_full
                    base["coleta_data"] = prox_dt_dia
                    base["texto_ia"] = (
                        f'[DIA SELECIONADO: paciente escolheu {ds_nome_full}. Setar ds="{ds_nome_full}", '
                        f'dt="{prox_dt_dia}" no $$$. Usar buscar_agenda para encontrar horarios.] ' + texto_usuario
                    )
                elif works_other_dia:
                    base["coleta_dia_semana"] = ds_nome_full
                    rota_agente = 3 if base.get("coleta_terceiro") == "true" else 2
                    base["texto_ia"] = (
                        f'[PERGUNTA DIA: {med_nome_display} NAO atende {ds_nome_full} na {unid_atual_dia}, mas '
                        f'atende no {outra_unid_dia}. Responder EXATAMENTE: "{med_nome_display} nao atende '
                        f'{ds_nome_full} na {unid_atual_dia}, mas atende no {outra_unid_dia}. Deseja mudar a '
                        f'consulta para la? 😊" Setar ds="{ds_nome_full}" no $$$. NAO mude os demais campos '
                        '(unid/dt/per/conv). Aguarde confirmacao.] ' + texto_usuario
                    )
                else:
                    grade_fallback = ""
                    if mk_dia and base.get("grade_med"):
                        for gl in base["grade_med"].split("\n"):
                            if mk_dia in _norm(gl):
                                qm = re.search(r'"([^"]+)"', gl)
                                if qm:
                                    grade_fallback = qm.group(1)
                                break
                    if grade_fallback:
                        base["texto_ia"] = (
                            f'[DIA INVALIDO: {med_nome_display} NAO atende {ds_nome_full} em nenhuma unidade. '
                            f'Responder EXATAMENTE: "{med_nome_display} nao atende {ds_nome_full}. '
                            f'{grade_fallback}" NAO mude nada no $$$. Aguarde escolha.] ' + texto_usuario
                        )
                    else:
                        base["texto_ia"] = (
                            f'[DIA INVALIDO: {med_nome_display} NAO atende {ds_nome_full}. Responder: "Esse '
                            f'medico nao atende {ds_nome_full}. Qual outro dia prefere? 😊" NAO mude nada no $$$. '
                            'Aguarde escolha.] ' + texto_usuario
                        )
            else:
                base["texto_ia"] = (
                    f'[OPCAO INVALIDA: paciente digitou "{txt_nmo}" mas o menu tem 3 opcoes. Responder '
                    'EXATAMENTE: "Desculpe, não entendi. Por favor escolha uma opção:\\n\\n1️⃣ Buscar outro '
                    'médico\\n2️⃣ Ver outros dias\\n3️⃣ Procurar mais para frente" NAO interprete como data ou '
                    'horario.] ' + texto_usuario
                )

    # FIX_NUMERO_PRECOMPUTE: detecta numeros soltos em rota=4, pre-computa data pra injecao
    if rota_agente == 4 and _texto_ia_livre(base):
        txt = (base.get("texto_ia") or "").lower()
        tem_hora_fmt = bool(
            re.search(r"\d{1,2}:\d{2}", txt)
            or re.search(r"\d{1,2}\s*h\s*\d{0,2}", txt)
            or re.search(r"\bdas\s+\d{1,2}\b", txt)
        )
        if not tem_hora_fmt:
            hoje_date = _hoje_sp().date()
            dia_match = re.search(r"dia\s+(\d{1,2})(?![/\-\d])", txt)
            data_br_match = re.search(r"(\d{1,2})[/\-](\d{1,2})", txt)
            if dia_match:
                d_num = int(dia_match.group(1))
                base["eh_troca_data"] = True
                base["data_alvo_troca"] = _computar_data_precompute(hoje_date, d_num)
                base["medico_troca"] = (
                    "sem preferencia" if (_int(base.get("coleta_modo")) == 1 or not base.get("coleta_medico"))
                    else base["coleta_medico"]
                )
            elif data_br_match:
                d_num = int(data_br_match.group(1))
                m_num = int(data_br_match.group(2))
                dt_br = _ymd_overflow(hoje_date.year, m_num, d_num)
                if dt_br < hoje_date:
                    dt_br = _ymd_overflow(dt_br.year + 1, dt_br.month, dt_br.day)
                base["eh_troca_data"] = True
                base["data_alvo_troca"] = dt_br.strftime("%Y-%m-%d")
                base["medico_troca"] = (
                    "sem preferencia" if (_int(base.get("coleta_modo")) == 1 or not base.get("coleta_medico"))
                    else base["coleta_medico"]
                )
            else:
                # FIX_HORARIO_HHMM: formato HHMM ("0820"->08:20, "1430"->14:30)
                hhmm_raw = re.sub(r"[:\s]", "", txt)
                hhmm_full = re.match(r"^(0\d|1\d|2[0-3])([0-5]\d)$", hhmm_raw)
                if hhmm_full and esta_em_agenda_ativa and not eh_cancel_real:
                    hh_formatted = f"{hhmm_full.group(1)}:{hhmm_full.group(2)}"
                    sem_pref_med_hh = not base.get("coleta_medico") or base.get("coleta_medico") == "sem preferencia"
                    aviso_hh = (
                        ' ⚠️ Se MAIS DE UM medico tiver esse horario disponivel, liste-os e pergunte qual o '
                        'paciente prefere ANTES de confirmar (NUNCA escolha automaticamente).'
                    ) if sem_pref_med_hh else ""
                    base["texto_ia"] = (
                        f'[HORARIO PROVAVEL: paciente disse "{hhmm_raw}" = horario {hh_formatted}. Trate como '
                        f'escolha de horario. Se disponivel nos SLOTS de navegar_agenda, va direto a confirmacao '
                        f'(i="confirmacao", h="{hh_formatted}").{aviso_hh} NAO pergunte "dia ou hora". Se nao '
                        'estiver nos slots, chame navegar_agenda(ver) e ofereca os horarios proximos.] '
                        + (base.get("texto_ia") or "")
                    )
                # Numero solto
                num_match = re.search(r"\b(\d{1,2})\b", txt)
                if num_match:
                    num = int(num_match.group(1))
                    # FIX_BARE_MENU_GUARD: 1-4 solto = selecao de menu (buscar outro medico, ver dias...), nao data
                    if 1 <= num <= 4:
                        if not base.get("cache_ativo") and _texto_ia_livre(base):
                            dt_num_menu = _computar_data_precompute(hoje_date, num)
                            # FIX_59027: entrega as chamadas LITERAIS das 3 opcoes do menu do FILTRO
                            menu_filtro_nm = ""
                            ds_map_nm = {"dom": "domingo", "seg": "segunda", "ter": "terça", "qua": "quarta",
                                         "qui": "quinta", "sex": "sexta", "sab": "sábado"}
                            ds_nome_nm = ds_map_nm.get((base.get("coleta_dia_semana") or "").lower(), "")
                            if num <= 3 and base.get("coleta_data") and ds_nome_nm:
                                dt_est_nm = ""
                                try:
                                    dt_e = datetime.strptime(base["coleta_data"], "%Y-%m-%d").date() + timedelta(days=21)
                                    dt_est_nm = dt_e.strftime("%Y-%m-%d")
                                except ValueError:
                                    dt_est_nm = ""
                                menu_filtro_nm = (
                                    ' Se sua ultima mensagem tinha o MENU "O que deseja fazer?" (1=outro medico / '
                                    '2=outros dias / 3=mais pra frente): opcao 1 = liste os medicos da GRADE_MED e '
                                    'pergunte qual prefere (med="__CLEAR__" no $$$); opcao 2 = chame buscar_agenda '
                                    f'EXATAMENTE com data="{base.get("hoje") or ""}" e SEM dia_semana (mesmos '
                                    'unidade/medico/periodo — ⛔ NAO use a data onde a busca parou, ⛔ NAO invente '
                                    f'dia_semana); opcao 3 = chame buscar_agenda EXATAMENTE com data="{dt_est_nm}" '
                                    f'e dia_semana="{ds_nome_nm}".'
                                )
                            base["texto_ia"] = (
                                f'[NUMERO EM AGENDA: paciente disse "{num}". Se sua ULTIMA mensagem listou DATAS '
                                f'(ex: "03/07, 06/07 ou 07/07"), ele quer o DIA {num} → chame buscar_agenda com '
                                f'data="{dt_num_menu}" EXATAMENTE e mostre o que a tool retornar.{menu_filtro_nm} '
                                f'Se sua ultima mensagem tinha OUTRO menu numerado (1️⃣/2️⃣/3️⃣), trate como a opcao '
                                f'{num}. ⛔ NAO use nenhuma outra data. ⛔ NAO avance 20 dias.] '
                                + (base.get("texto_ia") or "")
                            )
                    else:
                        per = (base.get("coleta_periodo") or "").lower()
                        eh_manha = per == "manha"
                        eh_tarde = per == "tarde"
                        fora_clinica = num >= 18 or num <= 7
                        fora_range = False
                        if eh_manha and (num < 7 or num > 12):
                            fora_range = True
                        if eh_tarde and num < 12:
                            fora_range = True

                        if num >= 24 or fora_clinica:
                            base["eh_troca_data"] = True
                            base["data_alvo_troca"] = _computar_data_precompute(hoje_date, 1 if num > 31 else num)
                            base["medico_troca"] = (
                                "sem preferencia" if (_int(base.get("coleta_modo")) == 1 or not base.get("coleta_medico"))
                                else base["coleta_medico"]
                            )
                        elif fora_range:
                            base["eh_troca_data"] = True
                            base["data_alvo_troca"] = _computar_data_precompute(hoje_date, num)
                            base["medico_troca"] = (
                                "sem preferencia" if (_int(base.get("coleta_modo")) == 1 or not base.get("coleta_medico"))
                                else base["coleta_medico"]
                            )
                        elif eh_manha or eh_tarde:
                            # FIX_AMBIGUO_AGENDA / FIX_NUMERO_EH_HORARIO (C1)
                            ja_tem_data = (
                                base.get("sessao_intencao") == "agenda" and base.get("coleta_data")
                                and not base.get("coleta_horario")
                            )
                            if not ja_tem_data:
                                base["texto_ia"] = (
                                    f'[NUMERO AMBIGUO: paciente disse {num}. Pode ser dia {num} ou horario {num}h. '
                                    f'Pergunte: Voce quis dizer dia {num} ou horario das {num}h?] '
                                    + (base.get("texto_ia") or "")
                                )
                            else:
                                hh_c1 = f"{num:02d}:00"
                                sem_pref_med = not base.get("coleta_medico") or base.get("coleta_medico") == "sem preferencia"
                                aviso_multi_med = (
                                    ' ⚠️ Se MAIS DE UM medico tiver esse horario disponivel, liste-os e pergunte '
                                    'qual o paciente prefere ANTES de confirmar (NUNCA escolha automaticamente o '
                                    'primeiro).'
                                ) if sem_pref_med else ""
                                base["texto_ia"] = (
                                    f'[HORARIO PROVAVEL: paciente disse "{num}" = horario {hh_c1}. Trate como '
                                    f'escolha de horario. Se {hh_c1} (ou {num}h) estiver nos SLOTS de '
                                    f'navegar_agenda, va direto a confirmacao do horario (i="confirmacao", '
                                    f'h="{hh_c1}").{aviso_multi_med} NAO pergunte "dia ou hora". Se nao estiver '
                                    'nos slots, chame navegar_agenda(ver) e ofereca os horarios proximos.] '
                                    + (base.get("texto_ia") or "")
                                )

    # FIX_P1_TERCEIRO: nome nao cadastrado digitado na etapa P1 -> forca fluxo de TERCEIRO (rota 3)
    if (
        rota_agente == 2 and not base.get("coleta_unidade") and not base.get("nome_dependente")
        and base.get("sessao_intencao") == "coleta"
    ):
        pacs_ter = base.get("pacientes") or []
        txt_ter = _strip_accents(texto_usuario)
        looks_like_name = bool(re.fullmatch(r"[a-zà-ÿ]+", txt_ter)) and 4 <= len(txt_ter) <= 20
        eh_bloqueado = txt_ter in _BLOCK_P1 or txt_ter in AFIRMACOES_TITULAR
        if looks_like_name and not eh_bloqueado:
            is_reg = False
            for p in pacs_ter:
                pn = _strip_accents(p.get("nome") or "").lower()
                fn = pn.split(" ")[0]
                if txt_ter == pn or txt_ter == fn or txt_ter in pn or fn in txt_ter:
                    is_reg = True
                    break
            if not is_reg:
                rota_agente = 3
                ia_output["rota_agente"] = 3
                intencao_rapida = "coleta"
                base["coleta_terceiro"] = "true"
                base["nome_dependente"] = texto_usuario
                nomes_reg = ", ".join(p.get("nome", "") for p in pacs_ter)
                base["texto_ia"] = (
                    f'[TERCEIRO CONFIRMADO: "{texto_usuario}" NAO e cadastrado ({nomes_reg}), e um terceiro. '
                    f'Setar t=true, d="{texto_usuario}" no $$$. P1: nome diferente → Responder EXATAMENTE: '
                    f'"Qual o CPF de {texto_usuario}? 😊" NAO peca nome de novo. NAO confunda com cadastrado.] '
                    + texto_usuario
                )

    # FIX_P3_MENU_GUARD: unidade selecionada via bare 1/2 -> forcar exibicao do menu P3 antes da lista
    if (
        rota_agente == 2 and not base.get("coleta_unidade") and base.get("nome_dependente")
        and base.get("sessao_intencao") != "triagem" and texto_usuario.strip() in ("1", "2")
    ):
        unid_sel = "Vila Olímpia" if texto_usuario.strip() == "1" else "Tatuapé"
        base["coleta_unidade"] = unid_sel
        mk_p3a = _medico_key(_norm(base.get("coleta_medico") or ""))
        gr_p3a = _GRADE_TEXTO.get(unid_sel, {}).get(mk_p3a, "") if mk_p3a else ""
        ult_med_global = base.get("_ultimo_medico_global") or ""
        if gr_p3a:
            base["texto_ia"] = (
                f'[MEDICO JA ESCOLHIDO: unidade {unid_sel} definida e {base["coleta_medico"]} ja selecionado. '
                f'Setar unid="{unid_sel}", med="{base["coleta_medico"]}", modo=3 no $$$. Responder EXATAMENTE: '
                f'"{base["coleta_medico"]} atende {gr_p3a} na {unid_sel}. Qual dia prefere? 😊" NAO mostre menu '
                'de medico.] ' + texto_usuario
            )
        elif mk_p3a:
            med_ant_p3a = base["coleta_medico"]
            base["coleta_medico"] = ""
            base["coleta_modo"] = 0
            base["texto_ia"] = (
                f'[P3 MENU OBRIGATORIO: paciente escolheu {unid_sel}, mas {med_ant_p3a} NAO atende nessa '
                f'unidade. Setar unid="{unid_sel}", med="", modo=0 no $$$. Responder EXATAMENTE: "{med_ant_p3a} '
                f'não atende na {unid_sel}. Com qual médico você prefere?\nDigite o número ou escreva:\n\n1️⃣ '
                'Primeiro horário disponível\n2️⃣ Escolher especialista\n3️⃣ Já tenho médico de preferência"] '
                + texto_usuario
            )
        elif ult_med_global:
            ela_p3a = "ela" if re.search(r"giseli|stephanie|juliana|fernanda", ult_med_global, re.IGNORECASE) else "ele"
            base["texto_ia"] = (
                f'[P3 ULTIMO MEDICO: paciente escolheu {unid_sel} e ja consultou com {ult_med_global}. Setar '
                f'unid="{unid_sel}" no $$$. Responder EXATAMENTE: "Você já consultou com {ult_med_global}. '
                f'Deseja agendar com {ela_p3a} novamente ou prefere outro médico? 😊" (Proximo turno: "sim"/"esse '
                f'mesmo" → med="{ult_med_global}", modo=2, mostre os dias via GRADE; "não"/"outro" → menu de '
                'medico 1/2/3.) NAO mostre lista de médicos.] ' + texto_usuario
            )
        else:
            cleaned_p3a = re.sub(r"\[PACIENTE JA IDENTIFICADO[^\]]*\]\s*", "", base.get("texto_ia") or texto_usuario)
            base["texto_ia"] = (
                f'[P3 MENU OBRIGATORIO: paciente escolheu {unid_sel}. Setar unid="{unid_sel}" no $$$. Responder '
                'EXATAMENTE: "Com qual médico você prefere?\nDigite o número ou escreva:\n\n1️⃣ Primeiro horário '
                'disponível\n2️⃣ Escolher especialista\n3️⃣ Já tenho médico de preferência" NAO mostre lista de '
                'médicos ainda. ⛔ O número que o paciente digitou foi a escolha da UNIDADE — NAO é resposta ao '
                'menu de médico. NAO sete modo nem dt no $$$.] ' + cleaned_p3a
            )

    # FIX_58755: residual ZUMBI — coleta_terceiro=true com CPF/id do "dependente" IGUAL ao do titular
    cpf_zu = re.sub(r"\D", "", str(base.get("cpf_dependente") or ""))
    pacientes_zu = base.get("pacientes")
    cpf_tit_zu = ""
    id_tit_zu = ""
    if isinstance(pacientes_zu, list) and pacientes_zu:
        cpf_tit_zu = re.sub(r"\D", "", str(pacientes_zu[0].get("cpf") or ""))
        id_tit_zu = str(pacientes_zu[0].get("id_tisaude") or "")
    id_zu = str(base.get("coleta_id_tisaude") or "")
    zumbi_cpf_zu = bool(cpf_zu) and bool(cpf_tit_zu) and cpf_zu == cpf_tit_zu
    zumbi_id_zu = bool(id_zu) and bool(id_tit_zu) and id_zu == id_tit_zu
    if base.get("coleta_terceiro") == "true" and (zumbi_cpf_zu or zumbi_id_zu):
        base["nome_dependente"] = ""
        base["cpf_dependente"] = ""
        base["nascimento_dependente"] = ""
        clear_pm = base.get("_clear_pm") or {}
        clear_pm.update({"d": 1, "c": 1, "n": 1})
        base["_clear_pm"] = clear_pm
        if zumbi_id_zu:
            base["coleta_id_tisaude"] = ""
            base["_clear_pm"]["id"] = 1

    # FIX_UNIDADE_TEXTO_OU_INVALIDA: selecao de unidade por texto ou invalida no menu
    txt_nome_chk = _strip_accents(texto_usuario).lower()
    txt_nome_chk = re.sub(r"[.,!?;:]+", " ", txt_nome_chk)
    txt_nome_chk = re.sub(r"\s+", " ", txt_nome_chk).strip()
    pacientes_ui = base.get("pacientes")
    eh_nome_paciente = False
    if isinstance(pacientes_ui, list):
        for p in pacientes_ui:
            pn = _strip_accents(p.get("nome") or "").lower()
            fn = pn.split(" ")[0] if pn else ""
            if pn and (txt_nome_chk == pn or txt_nome_chk == fn):
                eh_nome_paciente = True
                break
    identidade_completa_ui = bool(base.get("coleta_id_tisaude")) or bool(
        base.get("cpf_dependente") and base.get("nascimento_dependente")
    )
    sess_coleta_ui = (
        base.get("sessao_intencao") == "coleta" or _int(base.get("sessao_rota")) == 2 or _int(base.get("sessao_rota")) == 3
    )
    txt_ofui = _strip_accents(texto_usuario).lower()
    eh_outra_fase_ui = bool(re.search(_EH_OUTRA_FASE_UI_RX, txt_ofui))
    eh_resposta_email_fix = _eh_resposta_email_fix(texto_usuario)
    if (
        rota_agente in (2, 3) and sess_coleta_ui and not base.get("coleta_unidade") and not eh_outra_fase_ui
        and not base.get("_periodo_precomputed") and (base.get("nome_dependente") or base.get("coleta_id_tisaude"))
        and not eh_nome_paciente and identidade_completa_ui and not eh_resposta_email_fix and _texto_ia_livre(base)
    ):
        txt_ut = _norm(texto_usuario)
        unid_texto = ""
        if txt_ut == "1":
            unid_texto = "Vila Olímpia"
        elif txt_ut == "2":
            unid_texto = "Tatuapé"
        elif re.search(r"vila\s*oli|ol[iy]m+[iy]?p+[iy]*a", txt_ut):
            unid_texto = "Vila Olímpia"
        elif re.search(r"tatua?p", txt_ut):
            unid_texto = "Tatuapé"

        if unid_texto:
            base["coleta_unidade"] = unid_texto
            mk_p3b = _medico_key(_norm(base.get("coleta_medico") or ""))
            gr_p3b = _GRADE_TEXTO.get(unid_texto, {}).get(mk_p3b, "") if mk_p3b else ""
            ult_med_global_ui = base.get("_ultimo_medico_global") or ""
            if gr_p3b:
                base["texto_ia"] = (
                    f'[MEDICO JA ESCOLHIDO: unidade {unid_texto} definida e {base["coleta_medico"]} ja '
                    f'selecionado. Setar unid="{unid_texto}", med="{base["coleta_medico"]}", modo=3 no $$$. '
                    f'Responder EXATAMENTE: "{base["coleta_medico"]} atende {gr_p3b} na {unid_texto}. Qual dia '
                    'prefere? 😊" NAO mostre menu de medico.] ' + texto_usuario
                )
            elif mk_p3b:
                med_ant_p3b = base["coleta_medico"]
                base["coleta_medico"] = ""
                base["coleta_modo"] = 0
                base["texto_ia"] = (
                    f'[P3 MENU OBRIGATORIO: paciente escolheu {unid_texto}, mas {med_ant_p3b} NAO atende nessa '
                    f'unidade. Setar unid="{unid_texto}", med="", modo=0 no $$$. Responder EXATAMENTE: '
                    f'"{med_ant_p3b} não atende na {unid_texto}. Com qual médico você prefere?\nDigite o número '
                    'ou escreva:\n\n1️⃣ Primeiro horário disponível\n2️⃣ Escolher especialista\n3️⃣ Já tenho médico '
                    'de preferência"] ' + texto_usuario
                )
            elif ult_med_global_ui:
                ela_p3b = "ela" if re.search(r"giseli|stephanie|juliana|fernanda", ult_med_global_ui, re.IGNORECASE) else "ele"
                base["texto_ia"] = (
                    f'[P3 ULTIMO MEDICO: paciente escolheu {unid_texto} e ja consultou com {ult_med_global_ui}. '
                    f'Setar unid="{unid_texto}" no $$$. Responder EXATAMENTE: "Você já consultou com '
                    f'{ult_med_global_ui}. Deseja agendar com {ela_p3b} novamente ou prefere outro médico? 😊" '
                    f'(Proximo turno: "sim"/"esse mesmo" → med="{ult_med_global_ui}", modo=2, mostre os dias via '
                    'GRADE; "não"/"outro" → menu de medico 1/2/3.) NAO mostre lista de médicos.] ' + texto_usuario
                )
            else:
                cleaned_p3b = re.sub(r"\[PACIENTE JA IDENTIFICADO[^\]]*\]\s*", "", base.get("texto_ia") or texto_usuario)
                base["texto_ia"] = (
                    f'[P3 MENU OBRIGATORIO: paciente escolheu {unid_texto}. Setar unid="{unid_texto}" no $$$. '
                    'Responder EXATAMENTE: "Com qual médico você prefere?\nDigite o número ou escreva:\n\n1️⃣ '
                    'Primeiro horário disponível\n2️⃣ Escolher especialista\n3️⃣ Já tenho médico de preferência" '
                    'NAO mostre lista de médicos ainda. ⛔ O número que o paciente digitou foi a escolha da '
                    'UNIDADE — NAO é resposta ao menu de médico. NAO sete modo nem dt no $$$.] ' + cleaned_p3b
                )
        else:
            base["texto_ia"] = (
                f'[UNIDADE INVALIDA: paciente digitou "{texto_usuario}" que nao e opcao valida. Responder '
                'EXATAMENTE: "Desculpe, não entendi. Por favor, digite o número correspondente:\\n\\n1️⃣ Vila '
                'Olímpia\\n2️⃣ Tatuapé" NAO assuma unidade. NAO avance para medico.] ' + texto_usuario
            )

    # FIX_MESMO_MEDICO_SIM: resposta deterministica ao "Deseja agendar com ele novamente?"
    if (
        rota_agente in (2, 3) and base.get("_ultimo_medico_global") and base.get("coleta_unidade")
        and (not base.get("coleta_medico") or base.get("coleta_medico") == "sem preferencia")
        and _texto_ia_livre(base)
    ):
        ult_med_global_mm2 = base["_ultimo_medico_global"]
        txt_mm2 = _norm(texto_usuario)
        sim_mm2 = bool(re.match(
            r"^(s|si|sim|pode|pode ser|quero|claro|isso|esse mesmo|essa mesma|ele mesmo|ela mesma|com ele|com "
            r"ela|com ele mesmo|ok|bora|vamos|novamente|de novo)[!.,\s]*$", txt_mm2,
        ))
        nao_mm2 = bool(re.match(
            r"^(n|nao|outro|outra|quero outro|quero outra|prefiro outro|prefiro outra|nao quero|outro medico|"
            r"outra medica|nao, outro)[!.,\s]*$", txt_mm2,
        ))
        if sim_mm2 or nao_mm2:
            mk_mm2 = _medico_key(_norm(ult_med_global_mm2))
            uk_mm2 = "Tatuapé" if "Tatu" in base["coleta_unidade"] else "Vila Olímpia"
            gd_mm2 = _GRADE_TEXTO.get(uk_mm2, {}).get(mk_mm2, "") if mk_mm2 else ""
            if sim_mm2 and mk_mm2 and gd_mm2:
                base["coleta_medico"] = _FULL_MD[mk_mm2]
                base["coleta_modo"] = 2
                base["texto_ia"] = (
                    f'[MESMO MEDICO CONFIRMADO: paciente quer {_FULL_MD[mk_mm2]} (medico da ultima consulta). '
                    f'Setar med="{_FULL_MD[mk_mm2]}", modo=2 no $$$. Responder EXATAMENTE: "{_FULL_MD[mk_mm2]} '
                    f'atende {gd_mm2} na {uk_mm2}. Qual dia prefere? 😊" NAO mostre menu de medico. NAO chame '
                    'buscar_agenda ainda.] ' + texto_usuario
                )
            elif sim_mm2 and mk_mm2 and not gd_mm2:
                ela_ou_ele_mm2 = "ela" if re.search(r"giseli|stephanie|juliana|fernanda", mk_mm2) else "ele"
                base["texto_ia"] = (
                    f'[MESMO MEDICO OUTRA UNIDADE: {_FULL_MD[mk_mm2]} NAO atende na {uk_mm2}. Responder '
                    f'EXATAMENTE: "{_FULL_MD[mk_mm2]} não atende na {uk_mm2}. Deseja mudar de unidade para '
                    f'agendar com {ela_ou_ele_mm2}, ou prefere outro médico? 😊" NAO mude med/unid no $$$. '
                    'Aguarde a resposta.] ' + texto_usuario
                )
            else:
                base["texto_ia"] = (
                    '[P3 MENU OBRIGATORIO: paciente NAO quer o medico anterior. Responder EXATAMENTE: "Sem '
                    'problemas! Com qual médico você prefere?\nDigite o número ou escreva:\n\n1️⃣ Primeiro '
                    'horário disponível\n2️⃣ Escolher especialista\n3️⃣ Já tenho médico de preferência" NAO '
                    'mostre lista de medicos ainda.] ' + texto_usuario
                )

    return ResultadoParte8(base=base, intencao_rapida=intencao_rapida, rota_agente=rota_agente)


# ---------------------------------------------------------------------------------------------
# PARTE 9 (linhas 3470-3689)
# ---------------------------------------------------------------------------------------------

def _norm_nome_livre(s: str) -> str:
    """Normalização de texto livre pra match de nome: sem acento, minúsculo, pontuação de
    borda virada espaço, espaços colapsados. Usada por 3 guards distintos no JS original
    (mesma cadeia de replace, copiada 3x) — FIX_59087, FIX_UNIDADE_TEXTO_OU_INVALIDA (Parte 8)
    e FIX_NOME_INJECT_TITULAR."""
    t = _strip_accents(s).lower()
    t = re.sub(r"[.,!?;:]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


_FAQ_PATTERNS = (
    ("EST", ("estacion", "valet", "deixar o carro", "parar o carro", "onde deixo o carro")),
    ("RETORNO", (
        "como funciona o retorno", "tem retorno", "retorno incluso", "retorno esta incluso", "retorno gratis",
        "retorno gratuito", "valor do retorno", "preco do retorno", "custa o retorno", "custa retorno",
        "cobra retorno", "retorno e cobrado", "retorno pago", "direito a retorno",
    )),
    ("CONV", (
        "convenio", "convênio", "plano de saude", "planos de saude", "aceita plano", "qual plano",
        "quais plano", "cobertura", "carteirinha", "trabalham com", "pelo plano", "atende plano",
        "aceita o plano", "atende o plano", "atendem o plano",
    )),
    ("PART", (
        "valor", "preco", "preço", "custa", "quanto fica", "quanto e", "quanto sai", "particular",
        "forma de pagamento", "formas de pagamento", "aceita pix", "aceita cartao", "parcela",
    )),
    ("END", (
        "endereco", "endereço", "onde fica", "onde e a clinica", "onde e o consultorio", "localiza",
        "como chego", "como chegar", "qual a rua", "qual rua", "aonde fica", "fica aonde", "fica onde",
        "qual bairro", "passa o local", "manda o local", "qual o local", "qual e o local", "local da clinica",
        "local da consulta", "local da unidade", "local de atendimento",
    )),
    ("HOR", (
        "horario de funcionamento", "horario de atendimento", "horario da clinica", "horarios de funcionamento",
        "que horas abre", "que horas fecha", "que horas funciona", "que horas atende", "ate que horas",
        "abre que horas", "fecha que horas", "funciona ate", "dias de funcionamento", "expediente",
        "atende sabado", "atendem sabado", "atende no sabado", "atendem no sabado", "atende aos sabados",
        "atendem aos sabados", "abre sabado", "abre no sabado", "abrem sabado", "abrem no sabado",
        "funciona sabado", "funciona no sabado", "funcionam sabado", "trabalha sabado", "trabalham sabado",
        "trabalha no sabado", "trabalham no sabado", "sabado atende", "sabado abre", "sabado funciona",
        "atende domingo", "atendem domingo", "atende no domingo", "atendem no domingo", "abre domingo",
        "abre no domingo", "fim de semana", "final de semana", "feriado", "atendem hoje", "atende hoje",
        "estao atendendo",
    )),
    ("OUVIDO", (
        "limpeza de ouvido", "limpeza no ouvido", "limpar o ouvido", "limpar ouvido", "lavagem de ouvido",
        "lavagem no ouvido", "lavar o ouvido", "cera do ouvido", "cera no ouvido", "tirar cera",
        "remover cera", "cerume",
    )),
    ("CRIANCA", (
        "atende crianca", "atendem crianca", "atende bebe", "atendem bebe", "consulta infantil",
        "atendimento infantil", "pediatrico", "idade minima", "a partir de que idade", "a partir de qual idade",
        "qual idade atende", "atende idoso", "atendem idoso", "atende adulto", "atendem adulto",
        "todas as idades", "qualquer idade", "ate que idade",
    )),
    ("CIRURGIA", ("cirurgi", "operacao", "desvio de septo", "rinoplastia")),
    ("EXAME", (
        "raio x", "raio-x", "raiox", "exame", "audiometria", "tomografia", "ressonancia", "ultrassom",
        "teste da orelhinha", "orelhinha", " bera", " peate", "otoacustic",
    )),
    ("ESPEC", (
        "o que vcs atendem", "o que voces atendem", "o que atendem", "atendem o que", "especialidade",
        "o que vcs fazem", "o que voces fazem", "quais servicos", "que servicos", "tipo de consulta",
        "area de atuacao",
    )),
    ("TRATA", (
        "tratam", "zumbido", "labirintite", "otite", "sinusite", "rinite", "amigdalite", "amigdala",
        "adenoide", "vertigem", "tontura", "apneia", "ronco", "perda auditiva", "perda de audicao",
        "dor de ouvido", "dor de garganta", "ouvido entupido", "nariz entupido", "rouquidao", "surdez",
        "sangra", "epistaxe", "sangue no nariz", "sangue no ouvido",
    )),
)


@dataclass
class ResultadoParte9:
    base: dict
    intencao_rapida: str
    rota_agente: int


def processar_menu_p3_e_faq(
    base: dict,
    texto_usuario: str,
    intencao_rapida: str,
    rota_agente: int,
    ia_output: dict,
    sessao_era_agenda_com_coleta: bool,
    tem_identidade_em_andamento: bool,
    tem_terceiro_completo: bool,
) -> ResultadoParte9:
    """Linhas 3470-3689 do JS fonte: FIX_59087 (menu P3 numérico com resposta literal por
    opção), FIX_NOME_INJECT_TITULAR (pré-identificação de paciente titular entre 2+ cadastrados
    via fuzzy match) e o bloco FAQ_INJECT (14 categorias, com retomada determinística da
    coleta/agenda)."""

    # FIX_59087: menu P3 ("1 Primeiro horario / 2 Escolher especialista / 3 Ja tenho medico")
    sess_coleta_ui_p9 = (
        base.get("sessao_intencao") == "coleta" or _int(base.get("sessao_rota")) == 2
        or _int(base.get("sessao_rota")) == 3
    )
    identidade_completa_p9 = bool(base.get("coleta_id_tisaude")) or bool(
        base.get("cpf_dependente") and base.get("nascimento_dependente")
    )
    if (
        rota_agente in (2, 3) and sess_coleta_ui_p9 and base.get("coleta_unidade")
        and not base.get("coleta_medico") and not base.get("coleta_data") and not base.get("cache_ativo")
        and identidade_completa_p9 and not ia_output.get("bypass_agente_humano") and _texto_ia_livre(base)
    ):
        txt_p3m = _norm_nome_livre(texto_usuario)
        op_p3m = 0
        if txt_p3m == "1" or re.search(r"primeiro horario|qualquer um|tanto faz", txt_p3m):
            op_p3m = 1
        elif txt_p3m == "2" or re.search(r"escolher especialista|ver os medicos|quais medicos|lista de medicos", txt_p3m):
            op_p3m = 2
        elif txt_p3m == "3" or re.search(r"ja tenho medico|tenho preferencia|medico de preferencia", txt_p3m):
            op_p3m = 3
        if op_p3m == 1:
            base["texto_ia"] = (
                f'[MENU P3 OPCAO 1 (primeiro horario): Setar med="sem preferencia", dt="'
                f'{base.get("hoje") or base.get("amanha") or ""}", modo=1 no $$$ — os 3 valores OBRIGATORIOS '
                'neste turno. Responder EXATAMENTE: "Manhã ou tarde? 😊"] ' + texto_usuario
            )
        elif op_p3m == 2:
            base["texto_ia"] = (
                '[MENU P3 OPCAO 2 (escolher especialista): Setar modo=2, id="" no $$$. Responder EXATAMENTE:\n"'
                + (base.get("lista_med") or "") + '"\n⛔ Copie TODAS as linhas — NAO corte nem reformule nenhum '
                'medico.] ' + texto_usuario
            )
        elif op_p3m == 3:
            base["texto_ia"] = (
                f'[MENU P3 OPCAO 3 (ja tem medico): Setar modo=3, dt="'
                f'{base.get("hoje") or base.get("amanha") or ""}" no $$$. Responder EXATAMENTE: "Qual o nome do '
                'médico? 😊" ⛔ PROIBIDO mostrar lista de medicos — apenas pergunte e PARE.] ' + texto_usuario
            )

    # FIX_NOME_INJECT_TITULAR: pré-computar identificação de paciente titular (2+ pacientes)
    pacs_nit = base.get("pacientes") or []
    txt_nome_chk_p9 = _norm_nome_livre(texto_usuario)
    eh_nome_paciente_p9 = False
    if isinstance(pacs_nit, list):
        for p in pacs_nit:
            pn = _strip_accents(p.get("nome") or "").lower()
            fn = pn.split(" ")[0] if pn else ""
            if pn and (txt_nome_chk_p9 == pn or txt_nome_chk_p9 == fn):
                eh_nome_paciente_p9 = True
                break

    if (
        len(pacs_nit) >= 2 and rota_agente == 2 and not base.get("coleta_unidade")
        and (not base.get("nome_dependente") or eh_nome_paciente_p9)
    ):
        txt_nit = txt_nome_chk_p9
        matched = None
        for p in pacs_nit:
            nome_nit = _strip_accents(p.get("nome") or "").lower()
            if not nome_nit:
                continue
            if txt_nit == nome_nit or nome_nit in txt_nit or txt_nit in nome_nit:
                matched = p
                break
            if abs(len(txt_nit) - len(nome_nit)) <= 2 and len(txt_nit) >= 3 and _levenshtein(txt_nit, nome_nit) <= 2:
                matched = p
                break
        if matched:
            d = matched.get("nome") or ""
            c = matched.get("cpf") or ""
            n = matched.get("nascimento") or ""
            base["nome_dependente"] = d
            base["cpf_dependente"] = c
            base["nascimento_dependente"] = n
            base["texto_ia"] = (
                f'[PACIENTE IDENTIFICADO: {d} | CPF: {c} | NASC: {n}] Use d="{d}", c="{c}", n="{n}" no $$$. NAO '
                'peca CPF. Pergunte a unidade: "Temos dois enderecos de atendimento, qual a melhor unidade para '
                'voce? 1 Vila Olimpia 2 Tatupe" ' + (base.get("texto_ia") or "")
            )

    # FAQ_INJECT: detecta perguntas FAQ mid-flow e injeta resposta determinística
    msg_faq = _norm(texto_usuario)
    faq_tag = ""
    for tag, keys in _FAQ_PATTERNS:
        if any(k in msg_faq for k in keys):
            faq_tag = tag
            break

    # LOTE FAQ 2b: sintoma/crianca/cirurgia/espec com verbo de acao na msg = PEDIDO, nao pergunta
    if faq_tag in ("TRATA", "CRIANCA", "CIRURGIA", "ESPEC") and re.search(
        r"agendar|marcar|remarcar|reagendar|cancelar|desmarcar|confirmar|encaix", msg_faq
    ):
        faq_tag = ""

    # FIX_63267: convenio aceito citado junto com verbo de agendar = PEDIDO, injeta conv direto
    if (
        faq_tag == "CONV"
        and re.search(r"agendar|marcar|remarcar|reagendar|encaix|consulta", msg_faq)
        and re.search(r"porto|itau|omint|bradesco", msg_faq)
        and not re.search(r"quais|aceita|atendem|cobre|trabalham com", msg_faq)
    ):
        faq_tag = ""
        conv_faq = "Porto Seguro" if re.search(r"porto", msg_faq) else ("Itaú" if re.search(r"itau", msg_faq) else "")
        if (
            conv_faq and _texto_ia_livre(base) and not ia_output.get("bypass_agente_humano")
            and not (base.get("coleta_convenio") or "").strip()
        ):
            base["texto_ia"] = (
                f'[AGENDAMENTO COM CONVENIO INFORMADO: paciente pediu para MARCAR e ja informou o convenio '
                f'{conv_faq} (aceito). Setar conv="{conv_faq}" no $$$. ⛔ NAO envie a lista de convenios. ⛔ NAO '
                'pergunte convenio depois. Se a msg citar medico da casa, registre em med no $$$. Conduza o '
                'fluxo normal do passo atual — se identidade vazia, pergunte: "A consulta será para você ou '
                'para outra pessoa? 😊"] ' + (base.get("texto_ia") or "")
            )

    # Durante agenda ativa, CONV já é tratado pelo bloco [CONVENIO GENERICO] — suprimir FAQ
    if faq_tag == "CONV" and sessao_era_agenda_com_coleta:
        faq_tag = ""

    # FIX_FAQ_NAO_ATROPELA: convencao primeira-tag-vence
    if faq_tag and (ia_output.get("bypass_agente_humano") or not _texto_ia_livre(base)):
        faq_tag = ""

    if faq_tag:
        faq_resp = ""
        if faq_tag == "CONV":
            faq_resp = (
                "[FAQ] A Oto-SP atende os seguintes convênios:\n➡️ Itaú\n➡️ Omint\n➡️ Porto Seguro\n➡️ Bradesco "
                "— apenas na Unidade Vila Olímpia\n\nNão encontrou o seu? Atendemos também como particular:\n💰 "
                "R$ 600,00 no débito ou crédito à vista\n💰 R$ 570,00 via PIX (5% de desconto)\n✔️ Incluso 1 "
                "retorno em até 30 dias 😊"
            )
        elif faq_tag == "PART":
            faq_resp = (
                "[FAQ] Informações para agendamento Consulta no Particular:\n\n✔️ Incluso 1 retorno em até 30 "
                "dias\n✔️ Procedimentos inclusos no valor:\n- Vídeo-endoscopia naso-sinusal\n- Vídeo-faringo-"
                "laringoscopia\n- Nasofibrolaringoscopia\n- Cerúmen-remoção (bilateral)\n📌 Formas de pagamento:\n"
                "- R$ 600,00 no débito ou crédito à vista\n- R$ 570,00 via PIX (5% de desconto)\nSe tiver "
                "qualquer dúvida, estamos à disposição! 😊"
            )
        elif faq_tag == "END":
            unid_end_faq = _norm(base.get("coleta_unidade") or "")
            if "tatuape" in unid_end_faq:
                faq_resp = (
                    "[FAQ] O endereço da unidade Tatuapé é:\n📍 Rua Soriano de Sousa, 189 - Tatuapé, 1° Andar, "
                    "sala 14. 😊"
                )
            elif "olimpia" in unid_end_faq:
                faq_resp = (
                    "[FAQ] O endereço da unidade Vila Olímpia é:\n📍 Rua Alvorada, 1289 - Vila Olímpia, "
                    "Condomínio Vila Olímpia Prime Office, 15°Andar - sala 1508. 😊"
                )
            else:
                faq_resp = (
                    "[FAQ] Nossos endereços:\n\n📍 Vila Olímpia — Rua Alvorada, 1289 - Vila Olímpia, Condomínio "
                    "Vila Olímpia Prime Office, 15°Andar - sala 1508\n📍 Tatuapé — Rua Soriano de Sousa, 189 - "
                    "Tatuapé, 1° Andar, sala 14.\n\nQual unidade é melhor para você? 😊"
                )
        elif faq_tag == "HOR":
            faq_resp = "[FAQ] Nosso horário de atendimento é de segunda a sexta, das 8h às 18h. 😊"
        elif faq_tag == "EST":
            faq_resp = (
                "[FAQ] Sim! As duas unidades têm estacionamento no próprio prédio 🚗\nO estacionamento é "
                "particular — pago à parte, direto com o prédio. 😊"
            )
        elif faq_tag == "OUVIDO":
            faq_resp = (
                "[FAQ] Sim! 😊 A limpeza de ouvido (remoção de cerúmen) é feita pelo próprio médico durante a "
                "consulta, nas duas unidades.\nNo particular, ela já está inclusa no valor da consulta.\nPosso "
                "te ajudar a agendar? 😊"
            )
        elif faq_tag == "CRIANCA":
            faq_resp = (
                "[FAQ] Sim! Atendemos pacientes de todas as idades — crianças, adultos e idosos 😊 Posso te "
                "ajudar a agendar uma consulta?"
            )
        elif faq_tag == "CIRURGIA":
            faq_resp = (
                "[FAQ] Sim! Nossos médicos realizam cirurgias quando há indicação 😊\nO primeiro passo é uma "
                "consulta de avaliação — o médico examina e, se necessário, indica o procedimento.\nPosso te "
                "ajudar a agendar essa avaliação? 😊"
            )
        elif faq_tag == "RETORNO":
            faq_resp = (
                "[FAQ] No particular, a consulta já inclui 1 retorno em até 30 dias 😊\nPelo convênio as regras "
                "variam — se quiser, te passo para um atendente confirmar as condições do seu plano!"
            )
        elif faq_tag == "ESPEC":
            faq_resp = (
                "[FAQ] Somos especializados em otorrinolaringologia — cuidamos de tudo de ouvido, nariz e "
                "garganta: zumbido, labirintite, tontura, otites, sinusite, rinite, ronco, apneia e mais 😊\n"
                "Posso te ajudar a agendar uma avaliação?"
            )
        elif faq_tag == "TRATA":
            faq_resp = (
                "[FAQ] Sim! 😊 Somos especializados em otorrinolaringologia — cuidamos de tudo de ouvido, nariz "
                "e garganta: zumbido, labirintite, tontura, otites, sinusite, rinite, ronco, apneia e mais.\n"
                "Posso te ajudar a agendar uma avaliação? 😊"
            )
        elif faq_tag == "EXAME":
            faq_resp = (
                "[FAQ] Na Oto-SP fazemos consultas de otorrinolaringologia, e durante a consulta o médico pode "
                "realizar estes procedimentos (inclusos no valor, no particular):\n- Vídeo-endoscopia "
                "naso-sinusal\n- Vídeo-faringo-laringoscopia\n- Nasofibrolaringoscopia\n- Remoção de cerúmen "
                "(bilateral)\nPara outros exames, como raio-x, posso te passar para uma atendente confirmar! 😊"
            )

        if faq_resp:
            faq_retomada = ""
            if sessao_era_agenda_com_coleta and tem_identidade_em_andamento:
                nome_ref = (base.get("nome_dependente") or "o paciente").strip()
                campo_pend = (
                    f'CPF de {nome_ref}' if not (base.get("cpf_dependente") or "").strip()
                    else f'data de nascimento de {nome_ref}'
                )
                faq_retomada = (
                    '\n\n[RESPOSTA OBRIGATORIA: envie LITERALMENTE todo o texto do bloco [FAQ] acima (sem '
                    'resumir, sem cortar) e, na MESMA mensagem, ao FINAL, acrescente em nova linha: "Deseja '
                    f'continuar com o agendamento? Se sim, me informe o {campo_pend}." ⛔ NAO envie so a '
                    'pergunta — o texto do FAQ DEVE vir antes. ⛔ NAO avance para proximo campo sem confirmar.]'
                )
            elif tem_terceiro_completo and sessao_era_agenda_com_coleta and not base.get("coleta_unidade"):
                nome_ref = (base.get("nome_dependente") or "o paciente").strip()
                faq_retomada = (
                    '\n\n[RESPOSTA OBRIGATORIA: envie LITERALMENTE todo o texto do bloco [FAQ] acima (sem '
                    'resumir, sem cortar) e, na MESMA mensagem, ao FINAL, acrescente em nova linha: "Deseja '
                    f'continuar com o agendamento para {nome_ref}?" ⛔ NAO envie so a pergunta — o texto do FAQ '
                    'DEVE vir antes. Proximo passo apos confirmar: perguntar unidade/data/periodo (P2).]'
                )
            elif sessao_era_agenda_com_coleta:
                faq_retomada = (
                    '\n\n[RESPOSTA OBRIGATORIA: envie LITERALMENTE todo o texto do bloco [FAQ] acima (sem '
                    'resumir, sem cortar) e, na MESMA mensagem, ao FINAL, acrescente em nova linha UMA UNICA '
                    'pergunta que ja retoma a coleta do ponto onde parou (consulte o ESTADO SALVO — unidade/'
                    'data/periodo/convenio/medico), no formato: "Deseja continuar com o agendamento? Se sim, '
                    '[proxima pergunta da coleta]". Ex: "Deseja continuar com o agendamento? Se sim, a consulta '
                    'será Particular ou Convênio? 😊". ⛔ NAO faca duas perguntas separadas ("Deseja '
                    'continuar...?" numa linha e outra pergunta depois). ⛔ NAO envie so a pergunta — o texto do '
                    'FAQ DEVE vir antes. ⛔ NAO reinicie o agendamento nem repita etapas ja preenchidas.]'
                )
            elif _int(base.get("sessao_rota")) >= 4 or base.get("sessao_intencao") in (
                "navegacao", "confirmacao", "agenda", "execucao",
            ):
                faq_retomada = (
                    '\n\n[RESPOSTA OBRIGATORIA: envie LITERALMENTE todo o texto do bloco [FAQ] acima (sem '
                    'resumir, sem cortar) e, na MESMA mensagem, ao FINAL, acrescente em nova linha UMA UNICA '
                    'pergunta retomando a agenda do ponto onde parou, no formato: "Deseja continuar com o '
                    'agendamento? Se sim, qual horário prefere? 😊" (use a pergunta pendente real — escolha de '
                    'horario ja exibido, confirmacao etc). ⛔ NAO faca duas perguntas separadas. ⛔ NAO envie so '
                    'a pergunta — o FAQ DEVE vir antes. ⛔ NAO chame tools neste turno.]'
                )
            else:
                faq_retomada = (
                    '\n\n[RESPOSTA OBRIGATORIA: envie LITERALMENTE todo o texto do bloco [FAQ] acima (sem '
                    'resumir, sem cortar, sem reformular e SEM acrescentar perguntas proprias). Pode encerrar '
                    'com: "Posso te ajudar a agendar? 😊"]'
                )
            base["texto_ia"] = faq_resp + faq_retomada + f'\n\n[Mensagem original: {texto_usuario}]'

    return ResultadoParte9(base=base, intencao_rapida=intencao_rapida, rota_agente=rota_agente)
