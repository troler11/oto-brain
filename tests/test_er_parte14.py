"""
Testes da Parte 14 (ÚLTIMA) do port do ER (app/er.py::processar_encerramento_e_pedido_humano) —
linhas 4663-4740 do JS fonte: FIX_ENCERRAMENTO_TRIAGEM, FIX_64104/DESISTENCIA,
FIX_PEDIDO_HUMANO, backstop FIX_65731 e FIX_65817.
"""

from app.er import processar_encerramento_e_pedido_humano


def _base(**overrides):
    b = {
        "sessao_intencao": "",
        "sessao_rota": 0,
        "texto_ia": "",
        "telefone": "5511999999999",
        "motivo_humano": None,
    }
    b.update(overrides)
    return b


def _proc(texto, base=None, intencao_rapida="agenda", rota_agente=2, ia_output=None):
    io = ia_output if ia_output is not None else {}
    r = processar_encerramento_e_pedido_humano(base or _base(), texto, intencao_rapida, rota_agente, io)
    return r, io


# ---------- FIX_ENCERRAMENTO_TRIAGEM ----------

def test_encerramento_triagem_marca_concluido():
    b = _base(sessao_intencao="triagem")
    r, io = _proc("nao preciso de mais nada", base=b, rota_agente=0, intencao_rapida="triagem")
    assert r.rota_agente == 0
    assert r.intencao_rapida == "concluido"
    assert r.deve_encerrar_triagem is True
    assert "ENCERRAMENTO" in r.base["texto_ia"]


# ---------- FIX_64104: DESISTENCIA ----------

def test_desistencia_vai_pra_humano():
    b = _base(sessao_intencao="agenda")
    r, io = _proc("vou tentar em outro lugar", base=b, rota_agente=4, intencao_rapida="agenda")
    assert r.rota_agente == 0
    assert r.intencao_rapida == "humano"
    assert io["bypass_agente_humano"] is True
    assert r.base["motivo_humano"] == "Paciente desistindo - vai procurar outro lugar"
    assert "TRANSFERIR HUMANO" in r.base["texto_ia"]
    assert "DESISTINDO" in r.base["texto_ia"]


# ---------- FIX_PEDIDO_HUMANO ----------

def test_pedido_humano_explicito():
    b = _base(sessao_intencao="agenda")
    r, io = _proc("quero falar com um atendente", base=b, rota_agente=4, intencao_rapida="agenda")
    assert r.rota_agente == 0
    assert r.intencao_rapida == "humano"
    assert io["bypass_agente_humano"] is True
    assert "TRANSFERIR HUMANO" in r.base["texto_ia"]
    assert "Pediu atendente" in r.base["texto_ia"]


# ---------- FIX_65731: backstop ----------

def test_backstop_bypass_forca_rota5_humano():
    b = _base()
    r, io = _proc("oi", base=b, rota_agente=2, intencao_rapida="agenda", ia_output={"bypass_agente_humano": True})
    assert r.rota_agente == 5
    assert r.intencao_rapida == "humano"


# ---------- FIX_65817: telefone LID ----------

def test_telefone_lid_adiciona_aviso_no_motivo():
    b = _base(telefone="123456789012345", motivo_humano=None)
    r, io = _proc("oi", base=b, rota_agente=0, intencao_rapida="humano", ia_output={"bypass_agente_humano": True})
    assert "ATENCAO: telefone nao identificado (WhatsApp LID)" in r.base["motivo_humano"]
