"""
Testes de app/tools_triagem.py — executor que liga consultar_consultas_fluxo no formato
`Callable[[dict], dict]` que app.agentes.chamar_agente espera.
"""

from unittest.mock import patch

from app.tools_triagem import TOOLS_TRIAGEM, construir_executores


def test_schema_tem_o_nome_certo():
    nomes = {t["function"]["name"] for t in TOOLS_TRIAGEM}
    assert nomes == {"consultar_minhas_consultas"}


def test_executor_repassa_cpf():
    executores = construir_executores(tisaude_client=None)
    with patch("app.tools_triagem.consultar_consultas_fluxo.consultar_minhas_consultas") as fn:
        fn.return_value = {"resultado": "ok"}
        r = executores["consultar_minhas_consultas"]({"cpf": "11144477735"})
        fn.assert_called_once_with("11144477735", tisaude_client=None)
        assert r == {"resultado": "ok"}


def test_executor_cpf_ausente_usa_vazio():
    executores = construir_executores()
    with patch("app.tools_triagem.consultar_consultas_fluxo.consultar_minhas_consultas") as fn:
        fn.return_value = {"resultado": "ok"}
        executores["consultar_minhas_consultas"]({})
        fn.assert_called_once_with("", tisaude_client=None)
