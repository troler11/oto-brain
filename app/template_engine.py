"""
Fase 3 (peça de fiação, 12/07): resolve as expressões `{{ ... }}` estilo n8n que ainda existem
cruas nos 9 prompts (`{{ $json.coleta_data }}`, `{{ $('Montar Contexto').first().json.telefone }}`
etc) — sem isso o dispatcher carregava o prompt com os placeholders LITERAIS, nunca substituídos
por dado real (só `{{REGRAS:chave}}`, ver app.regras_clinica, era resolvido). Achado ao montar o
endpoint /route: um smoke test trivial ("oi") não exercitava nenhuma dessas expressões, então
passou despercebido.

Duas fontes de dado, espelhando as DUAS formas de referência do n8n:
  - `$('Montar Contexto').first().json.X`  → sempre o output ORIGINAL do nó Montar Contexto,
    não mutado pelo Extrair Rota (n8n pina o nó pelo nome — `$(...)` sempre lê aquele nó
    específico, não o item corrente do fluxo).
  - `$json.X` (sem pin) → o item CORRENTE chegando no nó do agente, ou seja, o `base` já mutado
    pelo Extrair Rota (e, na rota=4/agenda, também por injetar_contexto_agendamento +
    preparar_input_agenda) — é o que `$json` sempre significa em n8n: o item da execução atual.

Cobertura: catalogadas as expressões distintas usadas nos 9 prompts (busca por `{{ ... }}` em
prompts/*.txt, com DOTALL pra não truncar em expressões que têm `{}` literal embutido, como
EMAIL_PAC — armadilha real: uma extração inicial com regex não-DOTALL cortou essa expressão no
meio e a deixou de fora do catálogo). A maioria é acesso simples de campo (com ou sem
`|| default`, espelhando o operador JS `||` — falsy = None/""/0/False, igual JS pra esses
tipos). ~13 são expressões JS mais ricas (ternário, `.split/.reverse/.join`, `.replace` com
regex, `.map/.join` sobre `pacientes`, `JSON.stringify`) — cada uma tem um resolvedor
dedicado, tradução fiel da semântica JS exata (mesma disciplina do port do ER: não é reescrita,
é tradução 1:1).

`renderizar()` falha ALTO (`ValueError`) se encontrar uma expressão sem resolvedor — melhor
quebrar um teste agora do que deixar `{{ ... }}` cru vazar pro paciente em produção.
"""

from __future__ import annotations

import json
import re

_EXPR_RE = re.compile(r"\{\{(.*?)\}\}", re.DOTALL)

_RE_MC_FIELD = re.compile(r"^\$\('Montar Contexto'\)\.first\(\)\.json\.(\w+)\s*(?:\|\|\s*(.+))?$")
_RE_JSON_FIELD = re.compile(r"^\$json\.(\w+)\s*(?:\|\|\s*(.+))?$")
_RE_JSON_PROXIMAS = re.compile(r"^\$json\.proximas\??\.(\w+)\s*(?:\|\|\s*(.+))?$")
_RE_SELF_TERNARY = re.compile(r"^\$json\.(\w+) \? \$json\.\1 : (.+)$")
_RE_CACHE_TERNARY = re.compile(
    r"^\$json\.cache_ativo \? '(?P<pre>.*)' \+ \$json\.unidade_cache \+ '(?P<post>.*)' : '(?P<neg>.*)'$",
    re.DOTALL,
)
_RE_DATA_BR = re.compile(
    r"^\$json\.coleta_data \? \$json\.coleta_data\.split\('-'\)\.reverse\(\)\.join\('/'\) : ''$"
)
_RE_MODO_DS = re.compile(
    r"^\$json\.coleta_modo == 2 && \$json\.coleta_dia_semana \? \$json\.coleta_dia_semana : ''$"
)
_RE_NOME_FALLBACK = re.compile(
    r"^\$json\.nome_dependente \|\| \(\$json\.nome \? \$json\.nome\.split\('\\n'\)\[0\]\.split\(' '\)\[0\] : ''\)$"
)
_RE_CONV_OMINT = re.compile(r"^\(\$json\.coleta_convenio \|\| ''\)\.replace\(/\^Omint\\s\.\+\$/i, 'Omint'\)$")
_RE_EMAIL_SKIP = re.compile(
    r"^\(\$json\.coleta_email && \$json\.coleta_email !== 'SKIP'\) \? \$json\.coleta_email : ''$"
)
_RE_JSON_STRINGIFY_PACIENTES = re.compile(r"^JSON\.stringify\(\$json\.pacientes \|\| \[\]\)$")
_RE_PRIMEIRO_PACIENTE = re.compile(
    r"^\(\(\$\('Montar Contexto'\)\.first\(\)\.json\.pacientes \|\| \[\]\)\[0\] \|\| \{\}\)\.(\w+)"
    r"\s*(?:\|\|\s*(.+))?$"
)


def _parse_js_literal(raw: str | None):
    """`None` (sem `|| default` na expressão), `'texto'` → str, `0`/`1` → int, senão a string crua."""
    if raw is None:
        return None
    raw = raw.strip()
    if len(raw) >= 2 and raw[0] == raw[-1] == "'":
        return raw[1:-1]
    if re.fullmatch(r"-?\d+", raw):
        return int(raw)
    return raw


def _falsy(v) -> bool:
    """Conjunto falsy do JS relevante aqui: undefined/null, '', 0, false."""
    return v is None or v == "" or v is False or v == 0


def _js_or(value, default_raw: str | None):
    default = _parse_js_literal(default_raw)
    if default is None:
        default = ""
    return default if _falsy(value) else value


def _fmt(v) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v)


def _resolver_pacientes_para_qual(base_mc: dict) -> str:
    nomes = [p.get("nome", "") for p in (base_mc.get("pacientes") or [])]
    return "Para qual? " + " ou ".join(nomes) + "? 😊"


def _resolver_pacientes_detalhe(base_mc: dict) -> str:
    linhas = [
        f"{p.get('nome', '')} → CPF: {p.get('cpf') or ''} | NASC: {p.get('nascimento') or ''} | "
        f"ID: {p.get('id_tisaude') or ''} | ULTIMO_MED: {p.get('ultimo_medico') or ''}"
        for p in (base_mc.get("pacientes") or [])
    ]
    return "\n".join(linhas)


def _resolver_pacientes_nomes(base_mc: dict) -> str:
    return ", ".join(p.get("nome", "") for p in (base_mc.get("pacientes") or []))


def _resolver(expr: str, base_mc: dict, base: dict) -> str:
    expr = expr.strip()

    if "Para qual? " in expr and ".join(' ou ')" in expr:
        return _resolver_pacientes_para_qual(base_mc)
    if "ULTIMO_MED:" in expr:
        return _resolver_pacientes_detalhe(base_mc)
    if ".map(p => p.nome).join(', ')" in expr:
        return _resolver_pacientes_nomes(base_mc)

    if m := _RE_JSON_STRINGIFY_PACIENTES.match(expr):
        return json.dumps(base.get("pacientes") or [], ensure_ascii=False, separators=(",", ":"))

    if m := _RE_PRIMEIRO_PACIENTE.match(expr):
        campo, default_raw = m.groups()
        pacientes = base_mc.get("pacientes") or []
        primeiro = pacientes[0] if pacientes else {}
        return _fmt(_js_or(primeiro.get(campo), default_raw))

    if m := _RE_CACHE_TERNARY.match(expr):
        if base.get("cache_ativo"):
            return m.group("pre") + _fmt(base.get("unidade_cache")) + m.group("post")
        return m.group("neg")

    if _RE_DATA_BR.match(expr):
        data = base.get("coleta_data") or ""
        if not data:
            return ""
        partes = data.split("-")
        return "/".join(reversed(partes))

    if _RE_MODO_DS.match(expr):
        if base.get("coleta_modo") == 2 and base.get("coleta_dia_semana"):
            return _fmt(base.get("coleta_dia_semana"))
        return ""

    if _RE_NOME_FALLBACK.match(expr):
        nome_dep = base.get("nome_dependente")
        if not _falsy(nome_dep):
            return _fmt(nome_dep)
        nome = base.get("nome") or ""
        if not nome:
            return ""
        primeira_linha = nome.split("\n")[0]
        return primeira_linha.split(" ")[0]

    if _RE_CONV_OMINT.match(expr):
        conv = base.get("coleta_convenio") or ""
        return "Omint" if re.match(r"^Omint\s.+$", conv, re.IGNORECASE) else conv

    if _RE_EMAIL_SKIP.match(expr):
        email = base.get("coleta_email")
        return _fmt(email) if email and email != "SKIP" else ""

    if m := _RE_JSON_PROXIMAS.match(expr):
        sub, default_raw = m.groups()
        valor = (base.get("proximas") or {}).get(sub)
        return _fmt(_js_or(valor, default_raw))

    if m := _RE_MC_FIELD.match(expr):
        campo, default_raw = m.groups()
        return _fmt(_js_or(base_mc.get(campo), default_raw))

    if m := _RE_SELF_TERNARY.match(expr):
        campo, default_raw = m.groups()
        return _fmt(_js_or(base.get(campo), default_raw))

    if m := _RE_JSON_FIELD.match(expr):
        campo, default_raw = m.groups()
        return _fmt(_js_or(base.get(campo), default_raw))

    raise ValueError(f"template_engine: expressão sem resolvedor: {expr!r}")


def renderizar(texto: str, base_mc: dict, base: dict) -> str:
    """Substitui toda `{{ ... }}` de `texto` pelo valor real, lido de `base_mc` (output do
    Montar Contexto, pros refs `$('Montar Contexto')...`) e `base` (item corrente — já mutado
    pelo Extrair Rota e, na rota agenda, também por injetar_contexto_agendamento/
    preparar_input_agenda — pros refs `$json...`)."""
    return _EXPR_RE.sub(lambda m: _resolver(m.group(1), base_mc, base), texto)
