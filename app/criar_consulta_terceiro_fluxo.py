"""
Port fiel do sub-workflow n8n 'Ferramenta - Criar Consulta Terceiro' (id `xfpTs6C4BmnXs3jB`),
lido via `get_workflow_details` 13/07/2026 — espelho de `app.criar_consulta_fluxo` pra agendar
em nome de um DEPENDENTE (titular liga pro filho/cônjuge/etc), mesmas simplificações/bugs
documentados lá (resolução de médico via `app.tool_criar_ids_dinamicos.processar()` — port fiel
já existente de fase anterior da migração, alimentado com `medicos_por_unidade()` em vez de
portar o mesmo 4º sub-workflow nunca aberto). `para_terceiro` sai sempre `True` aqui — ver
docstring de `_inserir_agendamento_fila_terceiro` abaixo.

⚠️ Bug ADICIONAL encontrado só neste workflow (não corrigido, só documentado — mesma disciplina
do resto da migração): o node 'Buscar Terceiro no Banco1' consulta `terceiros_agendamento` pra
usar como FALLBACK quando a IA manda placeholder tipo "PREENCHA_COM_CPF_COLETADO_NO_PASSO_1" em
vez do CPF real — mas o resultado desse fallback (`nome_paciente`/`cpf_paciente`/
`nascimento_paciente` calculados em 'Extrair IDs Dinamicos3') NUNCA é lido pelos nós seguintes
('Buscar Paciente'/'Criar Paciente' leem `.nome_dependente`/`.cpf_dependente`/
`.nascimento_dependente` — os campos RAW, sem a correção). O fallback do banco é efetivamente
código morto no fluxo real. Por isso este port usa os campos `_dependente` recebidos direto,
sem tentar reimplementar a consulta a `terceiros_agendamento` (sem efeito observável no
comportamento real).

⚠️ Simplificação adicional: o node 'Buscar Paciente1' (pós-criação) referencia `$json.patient.cpf`
— assume que a resposta de `POST /patients/create` vem aninhada em `.patient`, diferente do
padrão usado em todo o resto da API (paciente direto na raiz, ex. `POST /schedule/new` retorna
`.appointment.patient`, não `POST /patients/create`). Parece inconsistente/possível bug do node
original. Este port reusa o mesmo padrão robusto já testado em `app.criar_consulta_fluxo`
(rebusca por CPF conhecido após criar, em vez de confiar no shape da resposta de criação).

⚠️ ESCOPO (13/07/2026, decisão Lucas): só CÓDIGO — MUTA de verdade. NÃO ligado a nenhum
dispatcher/agente/tool ainda. Trava até cutover (Fase 2), mesmo critério dos outros 3 fluxos de
mutação (confirmar_presenca_fluxo/cancelar_consulta_fluxo/criar_consulta_fluxo).
"""

from __future__ import annotations

import httpx
import psycopg

from app import tisaude, tool_criar_ids_dinamicos
from app.criar_consulta_fluxo import (
    _extrair_celular_criar_paciente,
    _normalizar_nascimento_pg,
    _telefone_com_55,
)


def criar_consulta_terceiro_completo(
    *,
    nome_dependente: str,
    cpf_dependente: str,
    nascimento_dependente: str,
    nome_titular: str,
    cpf_titular: str,
    nascimento_titular: str,
    telefone_titular: str,
    email_paciente: str | None,
    unidade: str,
    convenio: str,
    nome_medico_escolhido: str,
    data: str,
    hora: str,
    conn: psycopg.Connection,
    tisaude_client: httpx.Client | None = None,
) -> dict:
    """Orquestra 'Criar Consulta Terceiro' inteiro: resolve médico, busca/cria o PACIENTE
    DEPENDENTE na TiSaude (usando telefone do TITULAR pro celular, igual ao node original), cria
    a consulta, grava em `agendamentos` com `contato_id` resolvido pelo telefone do titular
    (`Cria fila` usa `query.telefone_titular`, não o telefone do dependente)."""
    token = tisaude.login(client=tisaude_client)

    medicos = tisaude.medicos_por_unidade(unidade, token, client=tisaude_client)
    try:
        ids = tool_criar_ids_dinamicos.processar({"nome_medico_escolhido": nome_medico_escolhido}, medicos)
    except tool_criar_ids_dinamicos.MedicoNaoEncontrado as e:
        return {"erro": "MEDICO_NAO_ENCONTRADO", "resultado": str(e)}
    id_local = ids["idLocal_dinamico"]
    id_calendar = ids["idCalendar_dinamico"]

    pacientes_existentes = tisaude.buscar_paciente_por_cpf(cpf_dependente, token, client=tisaude_client)
    if not pacientes_existentes:
        tisaude.criar_paciente(
            nome=nome_dependente, cpf=cpf_dependente,
            celular=_extrair_celular_criar_paciente(telefone_titular),
            nascimento_iso=nascimento_dependente, email=email_paciente or "",
            token=token, client=tisaude_client,
        )
        pacientes_existentes = tisaude.buscar_paciente_por_cpf(cpf_dependente, token, client=tisaude_client)

    paciente = tisaude.buscar_paciente_por_id(pacientes_existentes[0]["id"], token, client=tisaude_client)

    resultado_api = tisaude.criar_consulta(
        id_paciente=paciente["id"], nome=paciente["name"], cpf=paciente["cpf"],
        nascimento=paciente["dateOfBirth"], celular=paciente.get("cellphone") or "",
        email=email_paciente or paciente.get("email") or "",
        convenio=convenio, unidade=unidade, id_calendar=id_calendar, id_local=id_local,
        data_iso=data, hora=hora, token=token, client=tisaude_client,
    )

    _inserir_agendamento_fila_terceiro(
        conn, telefone_titular=telefone_titular, unidade=unidade, convenio=convenio,
        resultado_api=resultado_api, nome_medico_escolhido=nome_medico_escolhido, data=data, hora=hora,
    )

    return {"resultado": "Agendamento criado com sucesso no banco de dados da TiSaúde!"}


def _inserir_agendamento_fila_terceiro(
    conn: psycopg.Connection, *, telefone_titular: str, unidade: str, convenio: str,
    resultado_api: dict, nome_medico_escolhido: str, data: str, hora: str,
) -> None:
    """Port fiel do node Postgres 'Cria fila' desta ferramenta — `contato_id` resolvido pelo
    telefone do TITULAR (não do dependente), `para_terceiro` sempre `True` (esta ferramenta só
    roda pra terceiro; o node original tem o mesmo campo `query.terceiro ? false : true` das
    outras, mas o tool schema de criar_consulta_terceiro não expõe `terceiro` — nunca vem
    preenchido, então `para_terceiro` sai sempre `True` aqui, sem o bug de truthy-string)."""
    appointment = resultado_api.get("appointment") or {}
    patient = appointment.get("patient") or {}
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
              'agendamento', 'Não informada', %(unidade)s, %(convenio)s, TRUE,
              %(nome_paciente)s, 'AGENDADO', %(cpf_paciente)s, NULLIF(%(nascimento)s, '')::DATE,
              %(nome_medico)s, %(hora)s, 'a confirmar', NULLIF('', ''), %(data)s, %(hora)s,
              %(nome_medico)s, 'IA', %(id_itsaude)s
            );
            """,
            {
                "telefone": _telefone_com_55(telefone_titular), "unidade": unidade, "convenio": convenio,
                "nome_paciente": patient.get("name"), "cpf_paciente": patient.get("cpf"),
                "nascimento": _normalizar_nascimento_pg(patient.get("dateOfBirth")),
                "nome_medico": nome_medico_escolhido, "data": data, "hora": hora,
                "id_itsaude": appointment.get("id"),
            },
        )
