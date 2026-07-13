"""
Testes de app/fila_humana.py — nós "Preparar Dados para Fila", "Cria fila", "Cria Fila (Falha
Confirmar)" e "Formatar Falha Confirmar" (achados na auditoria de inventário completo do grafo,
157 nós, 13/07/2026). Puro, sem Postgres.
"""

from app.fila_humana import (
    formatar_falha_confirmar,
    montar_params_cria_fila,
    montar_params_cria_fila_falha_confirmar,
    preparar_dados_fila,
)

WA_INFO = {"SenderAlt": "", "from": "5511999999999@s.whatsapp.net"}


# ---------- preparar_dados_fila ----------

def test_preparar_dados_fila_consolida_campos():
    r = preparar_dados_fila({"intencao_rapida": "humano", "unidade_cache": "Vila Olímpia", "nome": "Lucas"})
    assert r["intencao_fila"] == "humano"
    assert r["dados_fila"]["unidade"] == "Vila Olímpia"
    assert r["dados_fila"]["nome_paciente"] == "Lucas"


def test_preparar_dados_fila_default_conversa():
    r = preparar_dados_fila({})
    assert r["intencao_fila"] == "conversa"


def test_preparar_dados_fila_para_terceiro_true_so_com_nome_e_cpf():
    r = preparar_dados_fila({"nome_dependente": "Zeca", "cpf_dependente": "12345678900"})
    assert r["dados_fila"]["para_terceiro"] is True


def test_preparar_dados_fila_preserva_base():
    r = preparar_dados_fila({"coleta_unidade": "Tatuapé"})
    assert r["coleta_unidade"] == "Tatuapé"


# ---------- montar_params_cria_fila ----------

def test_cria_fila_sem_eif1_usa_fallback_preparar_dados():
    base = {"intencao_rapida": "humano", "unidade_cache": "Vila Olímpia", "nome": "Lucas Bueno", "cpf": "12345678900"}
    r = montar_params_cria_fila(base, whatsapp_info=WA_INFO)
    assert r["telefone"] == "5511999999999"
    assert r["intencao"] == "humano"
    assert r["unidade"] == "Vila Olímpia"
    assert r["nome_paciente"] == "Lucas Bueno"
    assert r["especialidade"] == "Não informada"


def test_cria_fila_com_eif1_usa_dados_dele():
    base = {"intencao_rapida": "humano"}
    eif1 = {"intencao": "concluido", "dados": {"especialidade": "Otorrino", "unidade": "Tatuapé"}, "nome_dependente": "Zeca"}
    r = montar_params_cria_fila(base, whatsapp_info=WA_INFO, extrair_intencao_final=eif1)
    assert r["intencao"] == "concluido"
    assert r["especialidade"] == "Otorrino"
    assert r["unidade"] == "Tatuapé"
    assert r["nome_paciente"] == "Zeca"


def test_cria_fila_eif1_campo_vazio_cai_pro_fallback():
    base = {"unidade_cache": "Vila Olímpia"}
    eif1 = {"intencao": "concluido", "dados": {}}
    r = montar_params_cria_fila(base, whatsapp_info=WA_INFO, extrair_intencao_final=eif1)
    assert r["unidade"] == "Vila Olímpia"


def test_cria_fila_nome_com_quebra_de_linha_pega_so_primeira():
    base = {}
    eif1 = {"intencao": "concluido", "nome_dependente": "Zeca\nSilva"}
    r = montar_params_cria_fila(base, whatsapp_info=WA_INFO, extrair_intencao_final=eif1)
    assert r["nome_paciente"] == "Zeca"


def test_cria_fila_nascimento_formata_dd_mm_yyyy():
    base = {"nascimento_dependente": "15/03/1990"}
    r = montar_params_cria_fila(base, whatsapp_info=WA_INFO)
    assert r["nascimento"] == "1990-03-15"


def test_cria_fila_motivo_humano_vem_do_bloco_agente_humano():
    base = {}
    r = montar_params_cria_fila(
        base, whatsapp_info=WA_INFO,
        agente_humano_output='texto $$${"motivo":"paciente irritado","t":true}',
    )
    assert r["motivo_humano"] == "paciente irritado"


def test_cria_fila_motivo_humano_default():
    r = montar_params_cria_fila({}, whatsapp_info=WA_INFO)
    assert r["motivo_humano"] == "Atendimento Humano"


def test_cria_fila_para_terceiro_do_eif1_nao_cai_pro_fallback():
    base = {"nome_dependente": "X", "cpf_dependente": "Y"}  # faria para_terceiro=True no fallback
    eif1 = {"intencao": "concluido", "eh_terceiro": False}
    r = montar_params_cria_fila(base, whatsapp_info=WA_INFO, extrair_intencao_final=eif1)
    assert r["para_terceiro"] is False


# ---------- montar_params_cria_fila_falha_confirmar ----------

def test_cria_fila_falha_confirmar_campos_fixos():
    mc = {"nome_dependente": "Zeca", "cpf_dependente": "12345678900"}
    er = {"coleta_id_agendamento": "999"}
    r = montar_params_cria_fila_falha_confirmar(mc, er, whatsapp_info=WA_INFO)
    assert r["intencao"] == "confirmar_presenca"
    assert r["nome_paciente"] == "Zeca"
    assert "999" in r["observacoes"]
    assert r["motivo_humano"] == "Falha ao confirmar presenca"


# ---------- formatar_falha_confirmar ----------

def test_formatar_falha_confirmar_inclui_bloco_e_id():
    r = formatar_falha_confirmar({"coleta_id_agendamento": "42"})
    assert "Não consegui confirmar" in r["mensagem_final"]
    assert '"id": "42"' in r["mensagem_final"]
    assert r["mensagem_final"].count("$$$") == 1
