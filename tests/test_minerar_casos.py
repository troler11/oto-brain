"""Testes de app/minerar_casos.py — 100% puro, sem Postgres."""

from datetime import datetime, timedelta, timezone

from app.minerar_casos import minerar_telefone, minerar_tudo

T0 = datetime(2026, 7, 7, 10, 0, tzinfo=timezone.utc)


def _msg(offset_min, texto, origem, enviado_por=None):
    return {"telefone": "5511999999999", "texto": texto, "origem": origem,
            "enviado_por": enviado_por, "data": T0 + timedelta(minutes=offset_min)}


def test_conversa_sem_padroes_nao_gera_caso():
    msgs = [
        _msg(0, "oi", "paciente"),
        _msg(1, "Qual dia você prefere?", "ia_ou_recepcao"),
        _msg(2, "amanhã de manhã", "paciente"),
        _msg(3, "Consulta agendada! 😊", "ia_ou_recepcao"),
    ]
    assert minerar_telefone("tel", msgs, tem_agendamento=True) == []


def test_transferencia_humano_detectada_uma_vez_por_sessao():
    msgs = [
        _msg(0, "quero falar com atendente", "paciente"),
        _msg(1, "Pode me dizer o motivo?", "ia_ou_recepcao"),
        _msg(2, "duvida", "paciente"),
        _msg(3, "Vou te conectar", "ia_ou_recepcao", enviado_por="Lucas Bueno"),
        _msg(4, "obrigado", "paciente", enviado_por="Lucas Bueno"),
    ]
    casos = minerar_telefone("tel", msgs, tem_agendamento=True)
    transferencias = [c for c in casos if c["categoria"] == "transferencia_humano"]
    assert len(transferencias) == 1
    assert transferencias[0]["turno_texto"] == "Vou te conectar"


def test_desistencia_so_na_ultima_sessao_sem_agendamento():
    msgs = [
        _msg(0, "oi", "paciente"),
        _msg(1, "Qual unidade?", "ia_ou_recepcao"),
        # gap > 2h abre nova sessão
        _msg(200, "oi de novo", "paciente"),
        _msg(201, "Qual médico?", "ia_ou_recepcao"),
    ]
    casos = minerar_telefone("tel", msgs, tem_agendamento=False)
    desistencias = [c for c in casos if c["categoria"] == "desistencia"]
    assert len(desistencias) == 1
    assert desistencias[0]["turno_texto"] == "Qual médico?"


def test_desistencia_nao_dispara_se_tem_agendamento():
    msgs = [_msg(0, "oi", "paciente"), _msg(1, "Qual unidade?", "ia_ou_recepcao")]
    casos = minerar_telefone("tel", msgs, tem_agendamento=True)
    assert not any(c["categoria"] == "desistencia" for c in casos)


def test_desistencia_nao_dispara_se_ultima_msg_e_do_paciente():
    msgs = [_msg(0, "Qual unidade?", "ia_ou_recepcao"), _msg(1, "vila olimpia", "paciente")]
    casos = minerar_telefone("tel", msgs, tem_agendamento=False)
    assert not any(c["categoria"] == "desistencia" for c in casos)


def test_loop_repergunta_na_segunda_repeticao():
    msgs = [
        _msg(0, "oi", "paciente"),
        _msg(1, "Qual seu CPF?", "ia_ou_recepcao"),
        _msg(2, "não quero informar", "paciente"),
        _msg(3, "Qual seu CPF?", "ia_ou_recepcao"),
        _msg(4, "123", "paciente"),
        _msg(5, "Qual seu CPF?", "ia_ou_recepcao"),
    ]
    casos = minerar_telefone("tel", msgs, tem_agendamento=True)
    loops = [c for c in casos if c["categoria"] == "loop_repergunta"]
    # só dispara na 2ª repetição, não na 3ª
    assert len(loops) == 1
    assert loops[0]["turno_texto"] == "Qual seu CPF?"


def test_correcao_detectada_apos_mensagem_do_bot():
    msgs = [
        _msg(0, "quero com a dra juliana", "paciente"),
        _msg(1, "Certo, agendando com Dr. Elias", "ia_ou_recepcao"),
        _msg(2, "não, eu disse Juliana", "paciente"),
    ]
    casos = minerar_telefone("tel", msgs, tem_agendamento=True)
    correcoes = [c for c in casos if c["categoria"] == "correcao"]
    assert len(correcoes) == 1
    assert correcoes[0]["turno_texto"] == "não, eu disse Juliana"


def test_correcao_nao_falso_positivo_em_nao_generico():
    msgs = [
        _msg(0, "Confirma o agendamento?", "ia_ou_recepcao"),
        _msg(1, "não, prefiro outro dia", "paciente"),
    ]
    casos = minerar_telefone("tel", msgs, tem_agendamento=True)
    assert not any(c["categoria"] == "correcao" for c in casos)


def test_contexto_inclui_janela_ao_redor():
    msgs = [
        _msg(0, "a", "paciente"),
        _msg(1, "b", "ia_ou_recepcao"),
        _msg(2, "c", "paciente"),
        _msg(3, "d", "ia_ou_recepcao"),
        _msg(4, "não é isso", "paciente"),
    ]
    casos = minerar_telefone("tel", msgs, tem_agendamento=True)
    correcao = next(c for c in casos if c["categoria"] == "correcao")
    textos = [m["texto"] for m in correcao["contexto"]]
    assert textos == ["c", "d", "não é isso"]


def test_minerar_tudo_agrega_varios_telefones():
    por_telefone = {
        "5511111111111": [_msg(0, "Qual unidade?", "ia_ou_recepcao")],
        "5511222222222": [_msg(0, "oi", "paciente"), _msg(1, "Consulta ok!", "ia_ou_recepcao")],
    }
    casos = minerar_tudo(por_telefone, telefones_com_agendamento=set())
    assert any(c["telefone"] == "5511111111111" and c["categoria"] == "desistencia" for c in casos)
