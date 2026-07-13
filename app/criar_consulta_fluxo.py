"""
Port fiel do sub-workflow n8n 'Ferramenta - Criar Consulta e Paciente' (id `IF5VwPZB6uVVbok4`),
lido via `get_workflow_details` 13/07/2026.

⚠️ Simplificação documentada: 'Extrair IDs Dinamicos2' resolve idLocal/idCalendar do médico
chamando primeiro 'Chama Busca de Agenda1' (sub-workflow `qRGPjB7wruHgtQUu`, NUNCA aberto/
investigado) e então o match por nome — port fiel já existente em
`app.tool_criar_ids_dinamicos.processar()` (achado 13/07/2026, revisão pós-implementação: essa
função já existia de uma fase anterior da migração e é EXATAMENTE o que faltava aqui — eu tinha
recriado a mesma lógica via `tisaude.resolver_medico`, agora trocado por reusar o módulo certo).
Como o idCalendar de um médico não muda por dia, alimentar `tool_criar_ids_dinamicos.processar()`
com a lista de `tisaude.medicos_por_unidade()` (aceita lista flat direto, ver
`_extrair_lista_medicos`) é EQUIVALENTE ao resultado de chamar o sub-workflow de busca só pra
extrair esses 2 IDs — evita portar um 4º sub-workflow nunca visto.

⚠️ Bug preservado FIELMENTE do JS original ('Cria fila', campo `para_terceiro`): a condição é
`$query.terceiro ? false : true` — como `terceiro` chega como STRING ("terceiro_true"/
"terceiro_false"), QUALQUER string não-vazia é truthy em JS, então `para_terceiro` sai `False`
sempre que o campo `terceiro` vier preenchido (mesmo "terceiro_false"), e só vira `True` quando
o campo vem vazio/ausente. Parece bug do node original, mas não é desta migração corrigir sem
perguntar — portado literal.

⚠️ ESCOPO (13/07/2026, decisão Lucas): só CÓDIGO — MUTA de verdade (cria paciente/agendamento
real na TiSaude + grava em `agendamentos` no Postgres). NÃO ligado a nenhum dispatcher/agente/
tool ainda. Só entra em uso depois do cutover (Fase 2) — mesma trava do cancelar_consulta_fluxo/
confirmar_presenca_fluxo.

⚠️ Achados de revisão de fidelidade (13/07/2026, segunda auditoria via `get_workflow_details`,
sem ligar nada): (1) o node `If` real valida `notEmpty` em 8 campos antes de deixar o fluxo
prosseguir — a branch falsa não tem conexão nenhuma, ou seja, é um no-op silencioso (nenhuma
chamada TiSaude/Postgres, nenhum erro). Portado como guard logo no início de
`criar_consulta_completo`, retornando `{}`. (2) o node `Extrair IDs Dinamicos3` calcula
`telefoneTitular = dados.telefone_titular || dados.telefone_paciente || ''` e é ESSE valor que
`Criar Paciente` usa pro `cellphone` — não `telefone_paciente` direto. Este tool também é
chamado com `terceiro` preenchido (agendar dependente sem passar pelo tool dedicado), então o
parâmetro `telefone_titular` (opcional) foi adicionado com prioridade sobre `telefone_paciente`,
igual ao JS.
"""

from __future__ import annotations

import re

import httpx
import psycopg

from app import tisaude, tool_criar_ids_dinamicos


def _extrair_celular_criar_paciente(telefone_bruto: str) -> str:
    """Port de `$('Extrair IDs Dinamicos3').item.json.telefone_paciente` tratado inline em
    'Criar Paciente': tira sufixo de JID do WhatsApp (@.../:...), tira prefixo 55, string vazia
    se ainda sobrar mais de 13 chars (heurística do node pra descartar lixo)."""
    t = str(telefone_bruto or "").split("@")[0].split(":")[0]
    t = re.sub(r"^55", "", t)
    return "" if len(t) > 13 else t


def _normalizar_nascimento_pg(date_of_birth: str | None) -> str:
    """Port do parsing inline em 'Cria fila' pra `nascimento_paciente` (coluna DATE) — aceita
    DD/MM/YYYY ou ISO com sufixo de hora, normaliza pra YYYY-MM-DD (ou string vazia)."""
    if not date_of_birth:
        return ""
    d = str(date_of_birth).split("T")[0]
    if "/" in d:
        partes = d.split("/")
        if len(partes) == 3:
            d = f"{partes[2]}-{partes[1]}-{partes[0]}"
    return re.sub(r"[^0-9\-]", "", d)


def _telefone_com_55(telefone: str) -> str:
    t = str(telefone or "").strip()
    return t if t.startswith("55") else "55" + t


_CAMPOS_OBRIGATORIOS = (
    "nome_paciente", "hora", "nascimento_paciente", "unidade", "data", "convenio",
    "nome_medico_escolhido", "cpf_paciente",
)


def criar_consulta_completo(
    *,
    nome_paciente: str,
    cpf_paciente: str,
    nascimento_paciente: str,
    telefone_paciente: str,
    email_paciente: str | None,
    unidade: str,
    convenio: str,
    nome_medico_escolhido: str,
    data: str,
    hora: str,
    terceiro: str | None = None,
    telefone_titular: str | None = None,
    conn: psycopg.Connection,
    tisaude_client: httpx.Client | None = None,
) -> dict:
    """Orquestra 'Criar Consulta e Paciente' inteiro: resolve médico -> busca/cria paciente na
    TiSaude -> cria a consulta -> grava linha em `agendamentos` (Postgres, tabela de fila/
    histórico — não é `agenda_cache`). Retorna `{"resultado": "..."}` (sucesso),
    `{"erro": "MEDICO_NAO_ENCONTRADO", "resultado": "..."}` (mesmo texto de erro do `throw` do
    node original, sem agendar) ou `{}` (gate `notEmpty` do node `If` real reprovou — no-op
    silencioso, port fiel: nenhuma chamada TiSaude/Postgres acontece)."""
    campos = {
        "nome_paciente": nome_paciente, "hora": hora, "nascimento_paciente": nascimento_paciente,
        "unidade": unidade, "data": data, "convenio": convenio,
        "nome_medico_escolhido": nome_medico_escolhido, "cpf_paciente": cpf_paciente,
    }
    if not all(campos[c] for c in _CAMPOS_OBRIGATORIOS):
        return {}

    token = tisaude.login(client=tisaude_client)

    medicos = tisaude.medicos_por_unidade(unidade, token, client=tisaude_client)
    try:
        ids = tool_criar_ids_dinamicos.processar({"nome_medico_escolhido": nome_medico_escolhido}, medicos)
    except tool_criar_ids_dinamicos.MedicoNaoEncontrado as e:
        return {"erro": "MEDICO_NAO_ENCONTRADO", "resultado": str(e)}
    id_local = ids["idLocal_dinamico"]
    id_calendar = ids["idCalendar_dinamico"]

    pacientes_existentes = tisaude.buscar_paciente_por_cpf(cpf_paciente, token, client=tisaude_client)
    if not pacientes_existentes:
        tisaude.criar_paciente(
            nome=nome_paciente, cpf=cpf_paciente,
            celular=_extrair_celular_criar_paciente(telefone_titular or telefone_paciente),
            nascimento_iso=nascimento_paciente, email=email_paciente or "",
            token=token, client=tisaude_client,
        )
        pacientes_existentes = tisaude.buscar_paciente_por_cpf(cpf_paciente, token, client=tisaude_client)

    paciente = tisaude.buscar_paciente_por_id(pacientes_existentes[0]["id"], token, client=tisaude_client)

    resultado_api = tisaude.criar_consulta(
        id_paciente=paciente["id"], nome=paciente["name"], cpf=paciente["cpf"],
        nascimento=paciente["dateOfBirth"], celular=paciente.get("cellphone") or "",
        email=email_paciente or paciente.get("email") or "",
        convenio=convenio, unidade=unidade, id_calendar=id_calendar, id_local=id_local,
        data_iso=data, hora=hora, token=token, client=tisaude_client,
    )

    _inserir_agendamento_fila(
        conn, telefone_paciente=telefone_paciente, unidade=unidade, convenio=convenio,
        terceiro=terceiro, resultado_api=resultado_api, nome_medico_escolhido=nome_medico_escolhido,
        data=data, hora=hora,
    )

    return {"resultado": "Agendamento criado com sucesso no banco de dados da TiSaúde!"}


def _inserir_agendamento_fila(
    conn: psycopg.Connection, *, telefone_paciente: str, unidade: str, convenio: str,
    terceiro: str | None, resultado_api: dict, nome_medico_escolhido: str, data: str, hora: str,
) -> None:
    """Port fiel do node Postgres 'Cria fila' — INSERT em `agendamentos` (fila/histórico, NÃO é
    `agenda_cache`). Campos `patient.*` vêm da resposta real da API (`resultado_api['appointment']
    ['patient']`), o resto vem dos args originais da tool (não dos dados resolvidos)."""
    appointment = resultado_api.get("appointment") or {}
    patient = appointment.get("patient") or {}
    para_terceiro = not bool(terceiro)  # bug preservado — ver docstring do módulo
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO agendamentos (
              contato_id, intencao, especialidade, unidade, pagamento, para_terceiro,
              nome_paciente, status_atendimento, cpf_paciente, nascimento_paciente, nome_medico,
              periodo_atendimento, tipo_consulta, observacoes, data_consulta, hora_consulta,
              medico_final, atendente_nome, id_itsaude
            ) VALUES (
              (SELECT id FROM contatos_whatsapp WHERE telefone = %(telefone)s),
              'agendamento', 'Não informada', %(unidade)s, %(convenio)s, %(para_terceiro)s,
              %(nome_paciente)s, 'AGENDADO', %(cpf_paciente)s, NULLIF(%(nascimento)s, '')::DATE,
              %(nome_medico)s, %(hora)s, 'a confirmar', NULLIF('', ''), %(data)s, %(hora)s,
              %(nome_medico)s, 'IA', %(id_itsaude)s
            );
            """,
            {
                "telefone": _telefone_com_55(telefone_paciente), "unidade": unidade, "convenio": convenio,
                "para_terceiro": para_terceiro, "nome_paciente": patient.get("name"),
                "cpf_paciente": patient.get("cpf"), "nascimento": _normalizar_nascimento_pg(patient.get("dateOfBirth")),
                "nome_medico": nome_medico_escolhido, "data": data, "hora": hora,
                "id_itsaude": appointment.get("id"),
            },
        )
