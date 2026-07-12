"""
Port fiel de dois nós de aviso pequenos e independentes (Fase 1 do plano de migração, ver
C:\\Users\\lucas\\.claude\\plans\\unified-coalescing-puppy.md):
  - `aviso_sucesso()` — DEPLOY/Aviso_Sucesso1.js (5 linhas): passthrough puro do texto que o
    EIF1 já gerou (o comentário do JS existe só pra registrar que ISSO NÃO é hardcoded).
  - `aviso_transferencia()` — DEPLOY/Aviso_Transferencia1.js (31 linhas): menu principal (6
    opções) exibido ao transferir/reabrir a triagem, saudando pelo primeiro nome se conhecido.
"""

from __future__ import annotations


def aviso_sucesso(extrair_intencao_final: dict) -> dict:
    return {"mensagem_final": (extrair_intencao_final or {}).get("texto_ia")}


def aviso_transferencia(extrair_rota: dict, pacientes: list[dict] | None) -> dict:
    base = extrair_rota or {}
    pacientes = pacientes or []
    nome = pacientes[0]["nome"].split(" ")[0] if pacientes else ""
    saudacao = f"Olá, {nome}! 👋" if nome else "Olá! 👋"

    mensagem = (
        f"{saudacao}\n\n"
        "Seja bem-vindo(a) à Clínica Oto-SP de Otorrinolaringologia.\n\n"
        "Como podemos ajudá-lo(a) hoje?\n"
        "Digite o número ou escreva o que deseja:\n\n"
        "1️⃣ Agendar consulta\n"
        "2️⃣ Remarcar consulta\n"
        "3️⃣ Cancelar consulta\n"
        "4️⃣ Consulta pendente\n"
        "5️⃣ Troca de guias e documentos\n"
        "6️⃣ Confirmar consulta"
    )
    return {**base, "mensagem_final": mensagem}
