"""
Fase 4 (mecanismo 3) do plano de migração — fonte única das regras da clínica que hoje estão
duplicadas byte-a-byte em vários prompts. Proposto a Lucas em 12/07: NÃO é RAG com embeddings
(overkill pro tamanho do corpus — poucos blocos curtos — e com risco real de retrieval errado
numa clínica médica); é substituição direta e determinística de um token `{{REGRAS:chave}}`
pelo texto canônico, no momento de carregar o prompt (`app.dispatcher.carregar_prompt`).

Extração escopada ao que é BYTE-IDÊNTICO entre arquivos — mesma regra usada no port do ER
(só reusar quando idêntico, nunca "só parecido"). Confirmado via diff, 12/07: os blocos
`LISTA_CONV`/`INFO_PARTICULAR`/regras Omint são idênticos entre agente_coleta_1pac.txt,
agente_coleta_terceiro.txt e agente_coleta_titular.txt. `agente_coleta_0pac.txt` e
`agente_triagem.txt` têm redação PRÓPRIA pros mesmos fatos (não duplicação, versões
independentes) — deliberadamente NÃO tocados aqui; unificá-los seria mudança de conteúdo de
prompt, não extração de duplicata, e fica fora deste escopo.

Trocar aqui = a próxima carga de prompt já reflete a mudança nos 3 agentes de coleta, sem
editar cada arquivo.
"""

from __future__ import annotations

REGRAS: dict[str, str] = {
    "convenios_lista": (
        '"A Oto-SP atende os seguintes convênios:\n'
        "➡️ Itaú\n"
        "➡️ Omint\n"
        "➡️ Porto Seguro\n"
        "➡️ Bradesco — apenas na Unidade Vila Olímpia\n"
        "\n"
        'Não encontrou o seu? Pode me informar o nome — verifico se atendemos, ou podemos agendar como particular! 😊"'
    ),
    "info_particular": (
        '"Informações para agendamento Consulta no Particular:\n'
        "\n"
        "✔️ Incluso 1 retorno em até 30 dias\n"
        "\n"
        "✔️ Durante a consulta, se necessário, realizamos os seguintes procedimentos já inclusos no valor:\n"
        "\n"
        "- Vídeo-endoscopia naso-sinusal com ótica flexível\n"
        "- Vídeo-faringo-laringoscopia com endoscópio flexível\n"
        "- Nasofibrolaringoscopia para diagnóstico\n"
        "- Cerúmen-remoção (bilateral)\n"
        "\n"
        "📌 Formas de pagamento:\n"
        "\n"
        "- R$ 600,00 no débito ou crédito à vista\n"
        '- R$ 570,00 via PIX (5% de desconto)"'
    ),
    "omint_categorias": (
        '⛔ Omint → tem 3 CATEGORIAS com credenciamento distinto: Premium, Skill e Corporation. '
        'NUNCA aceite conv="Omint" puro — o sistema pergunta a categoria (conv="OMINT?"); '
        "quando houver tag [OMINT ...] no input, siga-a EXATAMENTE.\n"
        '  CONV_SALVO="OMINT?" → aguardando a categoria (menu 1-4). NÃO trate a resposta como convênio novo.\n'
        "  Omint Premium → atende nas DUAS unidades, SOMENTE com Dra. Giseli, Dr. Elias ou Dr. Jose Emmanuel. "
        'MED_SALVO for outro → "Pelo Omint Premium atendemos com a Dra. Giseli, o Dr. Elias ou o Dr. José '
        'Emmanuel. Com qual deles prefere? 😊" estado.med="".\n'
        "  Omint Skill / Omint Corporation → SOMENTE Dr. Torcuato Sanchez Rojas Neto, SOMENTE Vila Olímpia "
        '(quarta só à tarde, quinta e sexta). Paciente citar outro médico → "Infelizmente [médico] não atende '
        "pelo [categoria] — atende apenas pelo Omint Premium. Pelo [categoria] o atendimento é com o Dr. "
        'Torcuato. Quer seguir com ele? 😊"\n'
        '  Após escolher médico (Premium): Giseli → med="Dra. Giseli Rebechi", cf=0 (TA=quinta, VO=terça/quarta/'
        'sexta) | Elias → med="Dr. Elias Lobo Braga", cf=0, modo=3, dt=AMANHA, "Manhã ou tarde? 😊" | Jose → '
        'med="Dr. Jose Emmanuel Burle Neto", cf=0, dt=PROX_TER, ds="terca", modo=2, "Manhã ou tarde? 😊"\n'
        '  ⛔ Em `estado`, conv SEMPRE com a categoria completa (ex: "Omint Premium") — NUNCA "Omint" puro.\n'
        "  ⛔ STOP.\n"
    ),
}


def aplicar_regras(texto_prompt: str) -> str:
    """Substitui cada `{{REGRAS:chave}}` no texto do prompt pelo valor canônico de `REGRAS`."""
    for chave, valor in REGRAS.items():
        texto_prompt = texto_prompt.replace(f"{{{{REGRAS:{chave}}}}}", valor)
    return texto_prompt
