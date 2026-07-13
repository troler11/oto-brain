"""
Testes do port de Montar Contexto (app/montar_contexto.py::processar) —
DEPLOY/_proposed_Montar_Contexto.js, 362 linhas.
"""

from app.er import hoje_fixado
from app.montar_contexto import processar
from datetime import datetime

WA_INFO = {"SenderAlt": "", "Chat": "5511999999999@s.whatsapp.net"}


def _run(**kw):
    defaults = dict(
        busca_paciente_id1=None,
        busca_paciente_telefone=None,
        extrair_medico_timeline=None,
        sessao=None,
        whatsapp_info=WA_INFO,
        mensagem_agrupada="",
    )
    defaults.update(kw)
    return processar(**defaults)


# ---------- pacientes: fonte ID1 vs fallback ----------

def test_pacientes_da_fonte_id1():
    r = _run(busca_paciente_id1=[{"id": "1", "name": "Lucas Bueno", "cpf": "11111111111"}])
    assert r.paciente_encontrado is True
    assert r.pacientes[0]["nome"] == "Lucas Bueno"


def test_pacientes_fallback_telefone_lista():
    r = _run(busca_paciente_telefone={"data": [{"id": "2", "nome": "Ana Souza"}]})
    assert r.paciente_encontrado is True
    assert r.pacientes[0]["nome"] == "Ana Souza"


def test_pacientes_fallback_telefone_item_unico():
    r = _run(busca_paciente_telefone={"id": "3", "nome": "Bruno Lima"})
    assert r.pacientes[0]["nome"] == "Bruno Lima"


def test_id1_com_id_falsy_ignorado_cai_no_fallback():
    r = _run(busca_paciente_id1=[{"id": None, "name": "X"}], busca_paciente_telefone={"id": "4", "nome": "Carla"})
    assert r.pacientes[0]["nome"] == "Carla"


def test_email_nao_entra_se_blacklist():
    r = _run(busca_paciente_id1=[{"id": "1", "name": "Lucas", "email": "x@x.com", "blacklistEmail": True}])
    assert r.pacientes[0]["email"] is None


def test_sem_paciente_nenhum():
    r = _run()
    assert r.paciente_encontrado is False
    assert r.pacientes == []


# ---------- merge com Extrair Medico Timeline1 ----------

def test_timeline_merge_por_id():
    r = _run(
        busca_paciente_id1=[{"id": "1", "name": "Lucas Bueno"}],
        extrair_medico_timeline=[{"pacientes": [{"id_tisaude": "1", "ultimo_medico": "Dra. Giseli Rebechi", "data_ultima_consulta": "10/01/2026", "ultimo_convenio": "Itaú"}]}],
    )
    p = r.pacientes[0]
    assert p["ultimo_medico"] == "Dra. Giseli Rebechi"
    assert r.ultimo_medico == "Dra. Giseli Rebechi"
    assert "SUCESSO" in r.status_leitura_timelines


def test_timeline_merge_por_nome_case_insensitive():
    r = _run(
        busca_paciente_id1=[{"id": "1", "name": "lucas bueno"}],
        extrair_medico_timeline=[{"pacientes": [{"nome": "LUCAS BUENO", "ultimo_medico": "Dr. Elias Lobo Braga"}]}],
    )
    assert r.pacientes[0]["ultimo_medico"] == "Dr. Elias Lobo Braga"


def test_timeline_valor_nenhum_vira_vazio():
    r = _run(
        busca_paciente_id1=[{"id": "1", "name": "Lucas"}],
        extrair_medico_timeline=[{"pacientes": [{"id_tisaude": "1", "ultimo_medico": "NENHUM"}]}],
    )
    assert r.pacientes[0]["ultimo_medico"] == ""


def test_timeline_ausente_status_falha():
    r = _run(busca_paciente_id1=[{"id": "1", "name": "Lucas"}])
    assert "FALHA" in r.status_leitura_timelines


# ---------- sessão / cache ----------

def test_sessao_intencao_default_triagem_lowercase():
    r = _run(sessao={"sessao_intencao": "COLETA"})
    assert r.sessao_intencao == "coleta"


def test_cache_ativo_via_agenda_json():
    r = _run(sessao={"agenda_json": '{"unidade": "Tatuapé"}'})
    assert r.cache_ativo is True
    assert r.unidade_cache == "Tatuapé"


def test_ultimo_dia_exibido_texto():
    r = _run(sessao={"ultimo_dia_exibido": {"data": "2026-07-15", "medicos": [{"medico": "Giseli", "horarios": "09:00,10:00"}]}})
    assert r.ultimo_dia_texto == "Data: 15/07/2026 | Dr(a). Giseli: 09:00,10:00"


# ---------- telefone (SEM prefixo 55, diferente do app.er) ----------

def test_telefone_remove_prefixo_55():
    r = _run(whatsapp_info={"SenderAlt": "", "Chat": "5511988887777@s.whatsapp.net"})
    assert r.telefone == "11988887777"


def test_telefone_sender_alt_vence_chat():
    r = _run(whatsapp_info={"SenderAlt": "5511977776666@s.whatsapp.net", "Chat": "5511900000000@s.whatsapp.net"})
    assert r.telefone == "11977776666"


# ---------- medico_candidato_msg ----------

def test_medico_candidato_detectado():
    r = _run(sessao={"sessao_intencao": "coleta", "coleta_medico": ""}, mensagem_agrupada="quero com a giseli")
    assert r.medico_candidato_msg == "quero com a giseli"
    assert r.coleta_medico == "quero com a giseli"


def test_medico_candidato_nao_dispara_fora_de_coleta():
    r = _run(sessao={"sessao_intencao": "triagem"}, mensagem_agrupada="giseli")
    assert r.medico_candidato_msg == ""


def test_medico_candidato_nao_dispara_se_ja_tem_medico_salvo():
    r = _run(sessao={"sessao_intencao": "coleta", "coleta_medico": "Dra. Giseli Rebechi"}, mensagem_agrupada="giseli de novo")
    assert r.medico_candidato_msg == ""


def test_medico_candidato_ignora_keyword():
    r = _run(sessao={"sessao_intencao": "coleta"}, mensagem_agrupada="sim")
    assert r.medico_candidato_msg == ""


def test_medico_candidato_ignora_dia_da_semana():
    r = _run(sessao={"sessao_intencao": "coleta"}, mensagem_agrupada="segunda")
    assert r.medico_candidato_msg == ""


def test_medico_candidato_dr_prefixo():
    r = _run(sessao={"sessao_intencao": "coleta"}, mensagem_agrupada="dr joao silva")
    assert r.medico_candidato_msg == "dr joao silva"


# ---------- FIX_CARENCIA_DETERMINISTICA ----------

def test_carencia_porto_seguro_futura():
    with hoje_fixado(datetime(2026, 7, 12, 12, 0, 0)):
        r = _run(
            busca_paciente_id1=[{"id": "1", "name": "Lucas"}],
            extrair_medico_timeline=[{"pacientes": [{"id_tisaude": "1", "ultimo_convenio": "Porto Seguro", "data_ultima_consulta": "01/07/2026"}]}],
        )
    assert r.data_minima_carencia == "2026-07-21"
    assert r.data_minima_carencia_br == "21/07/2026"


def test_carencia_ja_vencida_fica_vazia():
    r = _run(
        busca_paciente_id1=[{"id": "1", "name": "Lucas"}],
        extrair_medico_timeline=[{"pacientes": [{"id_tisaude": "1", "ultimo_convenio": "Porto Seguro", "data_ultima_consulta": "01/01/2020"}]}],
    )
    assert r.data_minima_carencia == ""


def test_carencia_convenio_sem_regra_fica_vazia():
    r = _run(
        busca_paciente_id1=[{"id": "1", "name": "Lucas"}],
        extrair_medico_timeline=[{"pacientes": [{"id_tisaude": "1", "ultimo_convenio": "Itaú", "data_ultima_consulta": "01/07/2026"}]}],
    )
    assert r.data_minima_carencia == ""


# ---------- lista_med / grade_med / dia_lookup por unidade ----------

def test_lista_med_tatuape():
    r = _run(sessao={"coleta_unidade": "Tatuapé"})
    assert r.lista_med.startswith("Médicos disponíveis em Tatuapé:")


def test_lista_med_vila_olimpia_default():
    r = _run(sessao={})
    assert r.lista_med.startswith("Médicos disponíveis em Vila Olímpia:")


# ---------- p1_section por num_pacs ----------

def test_p1_section_zero_pacientes():
    r = _run()
    assert "Sem confirmação" in r.p1_section
    assert "A consulta será para você ou para outra pessoa?" in r.p1_section


def test_p1_section_um_paciente():
    r = _run(busca_paciente_id1=[{"id": "1", "name": "Lucas Bueno", "cpf": "11111111111"}])
    assert 'd="Lucas Bueno"' in r.p1_section


def test_p1_section_multi_pacientes():
    r = _run(busca_paciente_id1=[{"id": "1", "name": "Lucas"}, {"id": "2", "name": "Miguel"}])
    assert "NOMES: Lucas, Miguel" in r.p1_section


# ---------- saudacao_section ----------

def test_saudacao_section_zero_pacientes_tem_bloco_dolar():
    r = _run()
    assert "$$$" in r.saudacao_section


def test_saudacao_section_com_paciente_delega_ao_agente():
    r = _run(busca_paciente_id1=[{"id": "1", "name": "Lucas"}])
    assert r.saudacao_section == "# Saudação tratada pelo Agente Triagem/Ver"


def test_saudacao_section_sem_memoria_texto_padrao():
    r = _run()
    assert '"Olá! 👋 Bem-vindo à Oto-SP!' in r.saudacao_section
    assert "de volta" not in r.saudacao_section


def test_saudacao_section_com_memoria_reconhece_sem_citar_medico():
    memoria = {"ultimo_medico": "Dra. Giseli Rebechi", "ultima_unidade": "Vila Olímpia"}
    r = _run(memoria_paciente=memoria)
    assert '"Olá de novo! 👋 Bem-vindo de volta à Oto-SP!' in r.saudacao_section
    # nunca cita médico/unidade — telefone pode ser compartilhado entre dependentes
    assert "Giseli" not in r.saudacao_section
    assert "Vila Olímpia" not in r.saudacao_section
    assert "$$$" in r.saudacao_section


# ---------- p3_menu ----------

def test_p3_menu_com_ultimo_medico_unico_paciente():
    r = _run(
        busca_paciente_id1=[{"id": "1", "name": "Lucas"}],
        extrair_medico_timeline=[{"pacientes": [{"id_tisaude": "1", "ultimo_medico": "Dra. Giseli Rebechi"}]}],
    )
    assert "Você já consultou com Dra. Giseli Rebechi" in r.p3_menu


def test_p3_menu_sem_historico():
    r = _run(busca_paciente_id1=[{"id": "1", "name": "Lucas"}])
    assert "Com qual médico você prefere?" in r.p3_menu


# ---------- resp_sim_med ----------

def test_resp_sim_med_com_schedule_conhecido():
    r = _run(
        sessao={"coleta_unidade": "Vila Olímpia"},
        busca_paciente_id1=[{"id": "1", "name": "Lucas"}],
        extrair_medico_timeline=[{"pacientes": [{"id_tisaude": "1", "ultimo_medico": "Dra. Giseli Rebechi"}]}],
    )
    assert "Lucas=Dra. Giseli Rebechi atende" in r.resp_sim_med
    assert r.resp_sim_med.endswith("qual prefere? 😊")


def test_resp_sim_med_sem_historico_vira_padrao():
    r = _run(
        sessao={"coleta_unidade": "Vila Olímpia"},
        busca_paciente_id1=[{"id": "1", "name": "Lucas"}],
    )
    assert r.resp_sim_med == "Lucas=PADRAO"


def test_resp_sim_med_vazio_sem_unidade():
    r = _run(busca_paciente_id1=[{"id": "1", "name": "Lucas"}])
    assert r.resp_sim_med == ""
