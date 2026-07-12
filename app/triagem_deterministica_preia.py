"""
Port fiel do nó 'Triagem Determinística (Pre-IA)' — DEPLOY/_new_Triagem_Deterministica_PreIA.js
(99 linhas, snapshot 12/07/2026). Fase 1 do plano de migração (ver
C:\\Users\\lucas\\.claude\\plans\\unified-coalescing-puppy.md).

Roda ANTES do agente LLM. Replica (não substitui) um subconjunto dos guards do Extrair Rota
que já sobrescrevem a IA de qualquer forma nos casos de maior confiança/volume — o comentário
do JS chama isso de "hoisted de Extrair Rota". FASE SHADOW: só calcula `_preRota` e anexa ao
item, não desvia nada — serve pra comparar com o resultado FINAL do pipeline (`app.er.processar`)
antes de ativar qualquer bypass real. É exatamente o dado que faltava pro `_shadow_check` que
`app.er.processar` deliberadamente NÃO computa (ver docstring de `processar()` em app/er.py).

IMPORTANTE: os guards aqui são DELIBERADAMENTE uma cópia independente das versões equivalentes
em `app.er` (Partes 1/7), não uma chamada às funções de lá — o propósito inteiro deste nó é
comparar duas implementações computadas separadamente. Reusar o código do ER aqui tornaria a
comparação vazia (as duas sempre bateriam por construção). Isso é a EXCEÇÃO à regra de "reusar
quando idêntico" do resto do port: aqui a duplicação é o requisito, não um descuido.

Único cálculo genuinamente compartilhado (não é um guard, é normalização de texto): as 3 linhas
de sanitização de `texto_usuario` (FIX_SANITIZE_TRAILING_DIGIT / FIX_NORMALIZE_SPACES) são
byte-idênticas às de `app.er.processar_intake` — replicadas aqui por serem só 3 linhas, sem
puxar um import cruzado só por causa disso.
"""

from __future__ import annotations

import re

from app.text_utils import _norm

_MENSAGENS_INFORMATIVAS = (
    "quais convenios", "quais convênios", "convenios aceitos", "convênios aceitos",
    "qual o valor", "quanto custa", "qual o preco", "qual o preço",
    "valor da consulta", "valor a consulta", "gostaria de saber o valor", "saber o valor",
    "qual o endereco", "qual o endereço", "onde fica", "horario de funcionamento",
    "horário de funcionamento", "atendem", "aceitam", "vocês aceitam",
    "voces aceitam", "que convenio", "que convênio", "quais planos", "qual plano",
    "agendar consulta", "agendar retorno", "ver agendamentos",
    "falar com especialista",
)

_SESSAO_NOVA_INTENCOES = ("", "triagem", "concluido", "humano", "oferta_humano", "confirmar_presenca")


def _parseint_js(v) -> int | None:
    m = re.match(r"^\s*[-+]?\d+", str(v if v is not None else ""))
    return int(m.group(0)) if m else None


def processar(base: dict, mensagem_agrupada: str) -> dict:
    base = dict(base or {})

    texto_usuario = (mensagem_agrupada or "").lower().strip()
    texto_usuario = re.sub(r"([a-zà-ÿ])\d$", r"\1", texto_usuario, flags=re.IGNORECASE).strip()
    texto_usuario = re.sub(r"\s+", " ", texto_usuario).strip()

    txt_nfd = _norm(texto_usuario)

    eh_mensagem_informativa = any(p in texto_usuario for p in _MENSAGENS_INFORMATIVAS)

    sessao_intencao = base.get("sessao_intencao") or ""
    eh_sessao_nova = sessao_intencao in _SESSAO_NOVA_INTENCOES or eh_mensagem_informativa

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
    sessao_rota_int = _parseint_js(base.get("sessao_rota"))
    sessao_era_agenda_com_coleta = (
        sessao_rota_int in (2, 3)
        and (
            bool(base.get("coleta_unidade")) or bool(base.get("coleta_data")) or bool(base.get("coleta_periodo"))
            or bool(base.get("coleta_convenio")) or tem_identidade_em_andamento or tem_terceiro_completo
        )
        and sessao_intencao in ("coleta", "agenda")
    )

    pre_rota: dict = {"bypass": False, "motivo_regra": None}

    # FIX_REMARCAR_V2 (hoisted, linha ~191 do ER)
    if re.search(r"\bremarca|\breagend", txt_nfd) and not sessao_era_agenda_com_coleta and sessao_intencao != "coleta":
        pre_rota = {"bypass": True, "motivo_regra": "remarcar", "intencao_rapida": "remarcando"}

    # FIX_ENCAIXE (hoisted, linha ~199)
    if not pre_rota["bypass"] and re.search(r"\bencaix", txt_nfd):
        pre_rota = {"bypass": True, "motivo_regra": "encaixe", "rota_agente": 5, "intencao_rapida": "humano", "bypass_agente_humano": True}

    # Lista de espera / desistência (hoisted, linha ~207) — FIX_LISTA_ESPERA_ROBUSTA
    if not pre_rota["bypass"]:
        tem_aviso_intencao = bool(re.search(r"avis\w+", txt_nfd))
        tem_contexto_vaga = bool(re.search(r"vaga|vagar|abrir|surgir|aparecer|liberar|dispon", txt_nfd))
        eh_desistencia = bool(re.search(r"desist[eê]ncia|desistir", txt_nfd))
        eh_lista_espera = bool(re.search(r"lista.{0,15}espera", txt_nfd)) or (tem_aviso_intencao and tem_contexto_vaga)
        if eh_desistencia:
            pre_rota = {"bypass": True, "motivo_regra": "desistencia", "rota_agente": 5, "intencao_rapida": "humano", "bypass_agente_humano": True}
        elif eh_lista_espera:
            pre_rota = {"bypass": True, "motivo_regra": "lista_espera", "rota_agente": 5, "intencao_rapida": "humano", "bypass_agente_humano": True}

    # Menu numérico — SÓ opções 1/2/3 (hoisted, linha ~384-414) + menu inválido (linha ~305)
    if not pre_rota["bypass"] and eh_sessao_nova:
        toks = texto_usuario.split()
        opt = toks[0] if (len(toks) > 1 and all(k == toks[0] for k in toks)) else texto_usuario
        opt_int = _parseint_js(opt)
        if opt == "1":
            pre_rota = {"bypass": True, "motivo_regra": "menu_1_agendar", "rota_agente": 2, "intencao_rapida": "coleta"}
        elif opt in ("2", "3"):
            pre_rota = {"bypass": True, "motivo_regra": "menu_2_3_cancelar", "rota_agente": 1, "intencao_rapida": "cancelando"}
        elif (
            bool(re.match(r"^\d{1,2}$", opt)) and opt_int is not None and (opt_int < 1 or opt_int > 6)
            and not base.get("coleta_unidade") and not base.get("coleta_medico")
        ):
            pre_rota = {"bypass": True, "motivo_regra": "menu_invalido", "rota_agente": 0, "intencao_rapida": sessao_intencao or "triagem"}
        # opções 4, 5, 6 deliberadamente fora da Fase 1

    # FIX_ATRASO_HUMANO (hoisted, linha ~2520) — Fase 2
    if not pre_rota["bypass"]:
        eh_atraso = bool(re.search(
            r"atrasar|atrasad|atrasando|vou chegar (mais )?tarde|chegar mais tarde|vou demorar|"
            r"preso no transito|preso no transit|engarrafament",
            txt_nfd,
        ))
        if eh_atraso:
            pre_rota = {"bypass": True, "motivo_regra": "atraso", "bypass_agente_humano": True}

    return {**base, "_preRota": pre_rota}
