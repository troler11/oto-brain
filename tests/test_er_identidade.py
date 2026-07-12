"""
Testes da Parte 2 do port do ER (app/er.py::processar_identidade) — coleta de identidade
(linhas 737-1090 do JS fonte): extracao multi-dados, lookup por nome, identidade residual,
execucao sem nascimento, terceiro pede nascimento, CPF/nascimento trocados.
"""

from app.er import processar_identidade

CPF_VALIDO = "11144477735"


def _base(**overrides):
    b = {
        "pacientes": [],
        "coleta_terceiro": "",
        "nome_dependente": "",
        "cpf_dependente": "",
        "nascimento_dependente": "",
        "coleta_email": "",
        "sessao_intencao": "",
        "sessao_rota": 0,
        "coleta_unidade": "",
        "coleta_conv_fail": 0,
        "telefone": "5511999999999",
        "texto_ia": "",
    }
    b.update(overrides)
    return b


def _proc(texto, base=None, intencao_rapida="triagem", rota_agente=0, ia_output=None,
          eh_cancel_real=False, eh_mensagem_informativa=False):
    return processar_identidade(
        base or _base(), texto, intencao_rapida, rota_agente, ia_output or {},
        eh_cancel_real, eh_mensagem_informativa,
    )


# ---------- FIX_MULTI_DADOS ----------

def test_multi_dados_completo_0pac():
    b = _base(sessao_intencao="coleta")
    r = _proc("lucas silva santos, cpf 111.444.777-35, nascimento 01/05/1990", base=b)
    assert r.base["nome_dependente"] == "LUCAS SILVA SANTOS"
    assert r.base["cpf_dependente"] == CPF_VALIDO
    assert r.base["nascimento_dependente"] == "01/05/1990"
    assert r.rota_agente == 2
    assert r.intencao_rapida == "coleta"
    assert "DADOS CADASTRO COMPLETOS" in r.base["texto_ia"]


def test_multi_dados_cpf_invalido_primeira_vez_pede_conferencia():
    b = _base(sessao_intencao="coleta", nome_dependente="JOAO SILVA", nascimento_dependente="01/01/1990",
               coleta_conv_fail=0)
    r = _proc("meu cpf e 111.444.777-36", base=b)
    assert "CPF INVALIDO" in r.base["texto_ia"]
    assert r.intencao_rapida != "humano"


def test_multi_dados_cpf_invalido_segunda_vez_vai_pra_humano():
    b = _base(sessao_intencao="coleta", nome_dependente="JOAO SILVA", nascimento_dependente="01/01/1990",
               coleta_conv_fail=1)
    r = _proc("meu cpf e 111.444.777-36", base=b)
    assert r.intencao_rapida == "humano"
    assert "CPF invalido 2x" in r.motivo_humano


# ---------- FIX_PEDIR_IDENTIDADE_COMPLETA ----------

def test_para_mim_0pac_identidade_vazia_pede_3_dados():
    b = _base(sessao_intencao="coleta")
    r = _proc("para mim", base=b)
    assert "COLETA IDENTIDADE" in r.base["texto_ia"]
    assert "TERCEIRO" not in r.base["texto_ia"]
    assert r.rota_agente == 2
    assert r.intencao_rapida == "coleta"


def test_para_minha_filha_dispara_coleta_terceiro():
    b = _base(sessao_intencao="coleta")
    r = _proc("para minha filha", base=b)
    assert "COLETA IDENTIDADE TERCEIRO" in r.base["texto_ia"]
    assert r.rota_agente == 3
    assert r.base["coleta_terceiro"] == "true"


# ---------- FIX_58842: lookup por nome ----------

def test_lookup_por_primeiro_nome_paciente_cadastrado():
    b = _base(sessao_intencao="coleta",
              pacientes=[{"nome": "MARIA SILVA", "cpf": "11122233344", "nascimento": "01/01/1985", "id_tisaude": "55"}])
    r = _proc("maria", base=b)
    assert r.base["nome_dependente"] == "MARIA SILVA"
    assert r.base["cpf_dependente"] == "11122233344"
    assert r.rota_agente == 2
    assert "QUEM CONFIRMADO LOOKUP" in r.base["texto_ia"]


# ---------- FIX_IDENTIDADE_RESIDUAL ----------

def test_para_mim_com_identidade_residual_confirma_sem_repetir():
    b = _base(sessao_intencao="coleta", nome_dependente="JOAO PEREIRA", cpf_dependente=CPF_VALIDO,
              nascimento_dependente="01/01/1980", coleta_unidade="Vila Olímpia")
    r = _proc("para mim", base=b)
    assert "QUEM CONFIRMADO RESIDUAL" in r.base["texto_ia"]
    assert r.rota_agente == 2


# ---------- FIX_EXECUCAO_SEM_NASC ----------

def test_execucao_sem_nasc_com_data_na_mensagem_salva_e_prossegue():
    b = _base(sessao_intencao="execucao",
              pacientes=[{"nome": "ANA", "cpf": "1", "nascimento": "", "id_tisaude": "9"}])
    r = _proc("minha data de nascimento e 15/03/1985", base=b)
    assert r.base["nascimento_dependente"] == "15/03/1985"
    assert "NASC RECEBIDO" in r.base["texto_ia"]


def test_execucao_sem_nasc_sem_data_pede_nascimento():
    b = _base(sessao_intencao="execucao",
              pacientes=[{"nome": "ANA", "cpf": "1", "nascimento": "", "id_tisaude": "9"}])
    r = _proc("nao sei de cor, posso ver depois?", base=b)
    assert "FALTA NASCIMENTO" in r.base["texto_ia"]


# ---------- FIX_TERCEIRO_PEDIR_NASCIMENTO ----------

def test_terceiro_pedir_nascimento_apos_cpf():
    # telefone = "55"+CPF: colide com o guard anti-falso-positivo do MULTI_DADOS (que ignoraria
    # o CPF por parecer eco do proprio telefone) — isola o guard TERCEIRO_PEDIR_NASCIMENTO.
    b = _base(sessao_intencao="coleta", coleta_terceiro="true", nome_dependente="CARLA SOUZA",
              telefone="55" + CPF_VALIDO)
    r = _proc(CPF_VALIDO, base=b)
    assert r.base["cpf_dependente"] == CPF_VALIDO
    assert r.rota_agente == 3
    assert "PEDIR NASCIMENTO" in r.base["texto_ia"]


# ---------- FIX_CPF_NASCIMENTO_TROCADOS ----------

def test_data_no_lugar_do_cpf_e_corrigida():
    b = _base(sessao_intencao="coleta", nome_dependente="PEDRO ALVES",
              pacientes=[{"nome": "X"}])  # nao-0pac, nao-terceiro: evita MULTI_DADOS engolir antes
    r = _proc("15/08/1990", base=b, rota_agente=2)
    assert r.base["nascimento_dependente"] == "15/08/1990"
    assert "parece a data de nascimento" in r.base["texto_ia"]


def test_cpf_no_lugar_da_data_e_corrigido():
    b = _base(sessao_intencao="coleta", nome_dependente="PEDRO ALVES", cpf_dependente="123",
              pacientes=[{"nome": "X"}])
    r = _proc(CPF_VALIDO, base=b, rota_agente=2)
    assert r.base["cpf_dependente"] == CPF_VALIDO
    assert "parece o CPF" in r.base["texto_ia"]
