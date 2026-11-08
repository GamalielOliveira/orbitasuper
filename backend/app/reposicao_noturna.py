"""Reposição noturna da loja 2.

Repõe, numa entrada só por produto, as unidades que saíram de verdade no estoque.
Não é tarefa de funcionário e não mexe em escala, pedido ou simulador.

Conta só movimentação com tipo saida, campo quantidade e quantidade negativa.
Reserva, liberação, perda, ajuste e entrada manual ficam de fora e não são abatidos.

O dia da saída é o calendário de America/Sao_Paulo em criado_em. A execução da
madrugada olha apenas dias já encerrados (anteriores à data de São Paulo do
relógio) e somente da data de corte para a frente. Sem corte, a prévia só lê
e --aplicar recusa sem gravar.

Cada saída de origem entra no máximo uma vez em reposicao_noturna_origem.
A prévia não grava marcador. Rodar de novo não duplica. Duas execuções
sobrepostas da mesma loja esperam um cadeado e a segunda não recebe de novo.

Uso, a partir da pasta backend:
  python -m app.reposicao_noturna --loja 2
  python -m app.reposicao_noturna --loja 2 --corte AAAA-MM-DD
  python -m app.reposicao_noturna --loja 2 --corte AAAA-MM-DD --aplicar
"""
import argparse
import json
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import text

from app.db import engine
from app.main import _entrada_lote, _validade_auto

FUSO = ZoneInfo("America/Sao_Paulo")
LOJA_PADRAO = 2
ATOR_AUTOMATICO = "AUTO"
# Cadeado por loja, solto no fim da transação. Não é marcador gravado na tabela.
_CADEADO = 724_000_000

_DIA = "(m.criado_em AT TIME ZONE 'America/Sao_Paulo')::date"
_FISICO = "m.tipo = 'saida' AND m.campo = 'quantidade' AND m.quantidade < 0"
_IGNORADOS = ("entrada", "reserva", "liberacao", "perda", "ajuste", "saida_nao_fisica", "outro")


class ReposicaoRecusada(Exception):
    """A execução parou antes de gravar estoque."""


def analisar_corte(texto):
    if texto is None:
        return None
    try:
        return date.fromisoformat(texto)
    except ValueError:
        raise ReposicaoRecusada("Corte inválido. Use AAAA-MM-DD. Nada foi gravado.") from None


def executar(loja_id: int = LOJA_PADRAO, corte: date | None = None, aplicar: bool = False,
             agora: datetime | None = None, ator: str = ATOR_AUTOMATICO, *, _gancho=None) -> dict:
    """Prévia (padrão) ou aplicação. Sem corte, aplicar recusa e não grava."""
    if not isinstance(ator, str) or ator != ATOR_AUTOMATICO:
        raise ReposicaoRecusada("Ator inválido. A reposição automática só registra AUTO, que não é funcionário e não é o gerente. Nada foi gravado.")
    if isinstance(loja_id, bool) or not isinstance(loja_id, int) or loja_id <= 0:
        raise ReposicaoRecusada("Loja inválida. Nada foi gravado.")
    if corte is not None and type(corte) is not date:
        raise ReposicaoRecusada("Corte inválido. Use uma data AAAA-MM-DD. Nada foi gravado.")
    if aplicar and corte is None:
        raise ReposicaoRecusada("Sem corte de ativação nada é reposto. Escolha a data antes de aplicar. Nada foi gravado.")
    if agora is None:
        agora = datetime.now(FUSO)
    elif agora.tzinfo is None or agora.tzinfo.utcoffset(agora) is None:
        raise ReposicaoRecusada("O relógio da execução precisa de fuso. Nada foi gravado.")
    referencia = agora.astimezone(FUSO).date()
    if aplicar:
        with engine.begin() as c:
            try:
                return _aplicar(c, loja_id, corte, referencia, _gancho)
            except HTTPException as e:
                raise ReposicaoRecusada(f"{e.detail} Nada foi gravado.") from e
    with engine.begin() as c:
        c.execute(text("SET TRANSACTION READ ONLY"))
        _exigir_loja(c, loja_id)
        _exigir_ator_livre(c)
        return _pacote(c, loja_id, corte, referencia, "preview", False, None, [])


def _aplicar(c, loja_id, corte, referencia, gancho):
    _exigir_loja(c, loja_id)
    _exigir_ator_livre(c)
    c.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _CADEADO + loja_id})
    candidatos = _elegiveis(c, loja_id, corte, referencia, travar=True)
    if gancho is not None:
        gancho(candidatos)
    if not candidatos:
        return _pacote(c, loja_id, corte, referencia, "aplicar", False, None, [])
    rid, lotes = _gravar(c, loja_id, corte, referencia, candidatos)
    pacote = _pacote(c, loja_id, corte, referencia, "aplicar", True, rid, lotes)
    pacote["mensagem"] = "Entrada registrada uma vez para cada produto desta execução."
    return pacote


def _exigir_loja(c, loja_id):
    if c.execute(text("SELECT 1 FROM lojas WHERE id = :id"), {"id": loja_id}).first() is None:
        raise ReposicaoRecusada(f"Loja {loja_id} não existe. Nada foi gravado.")


def _exigir_ator_livre(c):
    if c.execute(text("SELECT 1 FROM funcionarios WHERE matricula = :m"), {"m": ATOR_AUTOMATICO}).first():
        raise ReposicaoRecusada("A matrícula AUTO já pertence a uma pessoa. A reposição automática não usa funcionário. Nada foi gravado.")


def _classe(tipo, campo, quantidade):
    if tipo == "saida" and campo == "quantidade" and quantidade < 0:
        return None
    if tipo == "saida":
        return "saida_nao_fisica"
    if tipo in ("entrada", "reserva", "liberacao", "perda", "ajuste"):
        return tipo
    return "outro"


def _elegiveis(c, loja_id, corte, referencia, travar):
    if corte is None or corte >= referencia:
        return []
    sql = f"""
        SELECT m.id, m.sku, m.quantidade, {_DIA} AS dia
        FROM movimentacoes_estoque m
        WHERE m.loja_id = :loja AND {_FISICO}
          AND {_DIA} >= :corte AND {_DIA} < :ref
          AND NOT EXISTS (SELECT 1 FROM reposicao_noturna_origem o WHERE o.movimentacao_id = m.id)
        ORDER BY m.id
    """
    if travar:
        sql += " FOR UPDATE OF m"
    return c.execute(text(sql), {"loja": loja_id, "corte": corte, "ref": referencia}).all()


def _agrupar(rows):
    acc = {}
    for r in rows:
        g = acc.setdefault(r.sku, {"sku": r.sku, "unidades": 0, "movimentos": 0, "de": r.dia, "ate": r.dia})
        g["unidades"] += -int(r.quantidade)
        g["movimentos"] += 1
        if r.dia < g["de"]:
            g["de"] = r.dia
        if r.dia > g["ate"]:
            g["ate"] = r.dia
    itens = []
    for sku in sorted(acc):
        g = acc[sku]
        g["de"] = g["de"].isoformat()
        g["ate"] = g["ate"].isoformat()
        itens.append(g)
    return itens


def _pacote(c, loja_id, corte, referencia, modo, gravou, reposicao_id, lotes):
    ontem = referencia - timedelta(days=1)
    saidas_ontem = c.execute(text(f"""
        SELECT m.sku, m.quantidade FROM movimentacoes_estoque m
        WHERE m.loja_id = :loja AND {_FISICO} AND {_DIA} = :dia
    """), {"loja": loja_id, "dia": ontem}).all()
    ignorados = {nome: 0 for nome in _IGNORADOS}
    ini = corte if corte is not None else ontem
    if ini < referencia:
        bruto = c.execute(text(f"""
            SELECT m.tipo, m.campo, m.quantidade FROM movimentacoes_estoque m
            WHERE m.loja_id = :loja AND {_DIA} >= :ini AND {_DIA} < :ref
        """), {"loja": loja_id, "ini": ini, "ref": referencia}).all()
        for r in bruto:
            classe = _classe(r.tipo, r.campo, int(r.quantidade))
            if classe:
                ignorados[classe] += 1
    antes = None
    vinculados = {"movimentos": 0, "unidades": 0}
    if corte is not None:
        row = c.execute(text(f"""
            SELECT COUNT(*) AS n, COALESCE(SUM(-m.quantidade), 0) AS un
            FROM movimentacoes_estoque m
            WHERE m.loja_id = :loja AND {_FISICO} AND {_DIA} < :corte
        """), {"loja": loja_id, "corte": corte}).one()
        antes = {"movimentos": int(row.n), "unidades": int(row.un)}
        if corte < referencia:
            vin = c.execute(text("""
                SELECT COUNT(*) AS n, COALESCE(SUM(unidades), 0) AS un
                FROM reposicao_noturna_origem
                WHERE loja_id = :loja AND dia >= :corte AND dia < :ref
            """), {"loja": loja_id, "corte": corte, "ref": referencia}).one()
            vinculados = {"movimentos": int(vin.n), "unidades": int(vin.un)}
    if gravou:
        itens = [{
            "sku": item["sku"], "unidades": item["unidades"], "movimentos": None,
            "de": item["de"], "ate": item["ate"], "validade": item["validade"], "lote_id": item["lote_id"],
        } for item in lotes]
        # movimentos por sku vêm do que acabou de ser vinculado nesta execução
        contagem = c.execute(text("""
            SELECT sku, COUNT(*) AS n FROM reposicao_noturna_origem
            WHERE reposicao_id = :id GROUP BY sku
        """), {"id": reposicao_id}).all()
        por_sku = {r.sku: int(r.n) for r in contagem}
        for item in itens:
            item["movimentos"] = por_sku.get(item["sku"], 0)
    else:
        # aplicar vazio já leu os elegíveis antes; não há segunda leitura nem FOR UPDATE
        linhas = _elegiveis(c, loja_id, corte, referencia, travar=False) if modo == "preview" else []
        itens = _agrupar(linhas)
        for item in itens:
            item["validade"] = _validade_auto(c, item["sku"], referencia, loja_id=loja_id).isoformat()
    unidades = sum(item["unidades"] for item in itens)
    dias = [item["de"] for item in itens if item.get("de")]
    dias_fim = [item["ate"] for item in itens if item.get("ate")]
    bloqueio = None
    if corte is None:
        bloqueio = "Sem corte de ativação a reposição não grava. O corte ainda não foi escolhido."
    if gravou:
        mensagem = "Entrada registrada uma vez para cada produto desta execução."
    elif bloqueio:
        mensagem = "Prévia somente leitura. Aplicar está fechado até você escolher o corte."
    elif unidades == 0:
        mensagem = "Nenhuma saída elegível. Nada foi gravado."
    else:
        mensagem = "Prévia somente leitura. Nada foi gravado."
    return {
        "modo": modo,
        "gravou": gravou,
        "mensagem": mensagem,
        "bloqueio": bloqueio,
        "loja_id": loja_id,
        "ator": ATOR_AUTOMATICO,
        "fuso": "America/Sao_Paulo",
        "referencia": referencia.isoformat(),
        "entrada_em": referencia.isoformat(),
        "corte": corte.isoformat() if corte else None,
        "ontem": {
            "dia": ontem.isoformat(),
            "produtos": len({r.sku for r in saidas_ontem}),
            "unidades": sum(-int(r.quantidade) for r in saidas_ontem),
            "movimentos": len(saidas_ontem),
        },
        "antes_do_corte": antes,
        "ja_vinculados": vinculados,
        "ignorados": ignorados,
        "demanda": {
            "produtos": len(itens),
            "unidades": unidades,
            "movimentos": sum(item["movimentos"] or 0 for item in itens),
            "de": min(dias) if dias else None,
            "ate": max(dias_fim) if dias_fim else None,
            "itens": itens,
        },
        "reposicao_id": reposicao_id,
        "lotes": lotes,
    }


def _gravar(c, loja_id, corte, referencia, candidatos):
    por = {}
    for r in candidatos:
        por.setdefault(r.sku, []).append(r)
    unidades = sum(-int(r.quantidade) for r in candidatos)
    rid = c.execute(text("""
        INSERT INTO reposicoes_noturnas (loja_id, corte, referencia, ator, produtos, unidades)
        VALUES (:loja, :corte, :ref, :ator, :produtos, :unidades)
        RETURNING id
    """), {
        "loja": loja_id, "corte": corte, "ref": referencia, "ator": ATOR_AUTOMATICO,
        "produtos": len(por), "unidades": unidades,
    }).scalar()
    recibo = {"sub": ATOR_AUTOMATICO}
    lotes = []
    for sku in sorted(por):
        linhas = por[sku]
        un = sum(-int(r.quantidade) for r in linhas)
        dias = [r.dia for r in linhas]
        dia_min, dia_max = min(dias), max(dias)
        faixa = dia_min.isoformat() if dia_min == dia_max else f"{dia_min.isoformat()} a {dia_max.isoformat()}"
        motivo = f"reposição noturna #{rid} · loja {loja_id} · saídas {faixa} · {un} un"
        validade = _validade_auto(c, sku, referencia, loja_id=loja_id)
        lid = _entrada_lote(c, sku, un, validade, referencia, recibo, motivo, loja_id=loja_id)
        entrada_id = c.execute(text("""
            SELECT id FROM movimentacoes_estoque
            WHERE lote_id = :l AND tipo = 'entrada' AND funcionario = :f
            ORDER BY id DESC LIMIT 1
        """), {"l": lid, "f": ATOR_AUTOMATICO}).scalar()
        for r in linhas:
            c.execute(text("""
                INSERT INTO reposicao_noturna_origem (
                    movimentacao_id, reposicao_id, lote_id, movimentacao_entrada_id,
                    sku, loja_id, dia, unidades)
                VALUES (:m, :rid, :lid, :eid, :sku, :loja, :dia, :un)
            """), {
                "m": r.id, "rid": rid, "lid": lid, "eid": entrada_id, "sku": sku,
                "loja": loja_id, "dia": r.dia, "un": -int(r.quantidade),
            })
        lotes.append({
            "sku": sku, "lote_id": lid, "unidades": un, "de": dia_min.isoformat(), "ate": dia_max.isoformat(),
            "validade": validade.isoformat(), "entrada_em": referencia.isoformat(),
        })
    return rid, lotes


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Reposição noturna (padrão: só leitura, não grava)")
    ap.add_argument("--loja", type=int, default=LOJA_PADRAO, help="loja explícita; padrão 2")
    ap.add_argument("--corte", default=None, help="AAAA-MM-DD; obrigatório com --aplicar")
    ap.add_argument("--aplicar", action="store_true", help="grava a entrada; sem isto, só mostra a prévia")
    args = ap.parse_args(argv)
    try:
        resultado = executar(loja_id=args.loja, corte=analisar_corte(args.corte), aplicar=args.aplicar)
    except ReposicaoRecusada as e:
        print(str(e))
        return 2
    print(json.dumps(resultado, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
