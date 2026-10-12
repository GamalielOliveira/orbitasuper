from fastapi import FastAPI, Depends
from sqlalchemy import text
from app.db import engine

import asyncio, os as _os
from contextlib import asynccontextmanager

EXPIRA_MIN = int(_os.getenv("EXPIRA_MIN", "15"))  # minutos para pagar

def expirar_pedidos(minutos: int = EXPIRA_MIN) -> list[str]:
    """Pedidos aguardando pagamento há mais de N minutos: libera estoque e marca 'expirado'."""
    with engine.begin() as c:
        ids = c.execute(text("""SELECT id, numero FROM pedidos WHERE status='aguardando_pagamento'
                                AND criado_em < now() - make_interval(mins => :m) FOR UPDATE SKIP LOCKED"""), {"m": minutos}).all()
        for p in ids:
            c.execute(text("""UPDATE lotes l SET reservado = l.reservado - i.quantidade
                              FROM itens_pedido i WHERE i.lote_id = l.id AND i.pedido_id = :id"""), {"id": p.id})
            c.execute(text("UPDATE pedidos SET status='expirado' WHERE id=:id"), {"id": p.id})
            c.execute(text("UPDATE pagamentos SET status='expirado', atualizado_em=now() WHERE pedido_id=:id AND status='pendente'"), {"id": p.id})
        return [p.numero for p in ids]

def seed_equipe():
    """Cria S01 (separador) e E01 (entregador), PIN 1234, só se não houver funcionários."""
    from app.auth import hash_pin
    with engine.begin() as c:
        if c.execute(text("SELECT COUNT(*) FROM funcionarios")).scalar(): return
        for m, n, f in (("S01", "Separador Teste", "separador"), ("E01", "Entregador Teste", "entregador")):
            c.execute(text("""INSERT INTO funcionarios (matricula, nome, funcao, pin_hash, ativo, disponivel)
                              VALUES (:m, :n, :f, :h, true, true) ON CONFLICT DO NOTHING"""), {"m": m, "n": n, "f": f, "h": hash_pin("1234")})

async def _loop_expiracao():
    while True:
        try:
            feitos = await asyncio.to_thread(expirar_pedidos)
            if feitos: print("expirados:", feitos, flush=True)
        except Exception as e:
            print("erro expiracao:", e, flush=True)
        await asyncio.sleep(60)

@asynccontextmanager
async def lifespan(app):
    try: seed_equipe()
    except Exception as e: print("seed equipe falhou:", e, flush=True)
    tarefa = asyncio.create_task(_loop_expiracao())
    yield
    tarefa.cancel()

app = FastAPI(title="Daki Replica", lifespan=lifespan)

@app.post("/admin/expirar")
def expirar_agora(minutos: int = EXPIRA_MIN):
    return {"expirados": expirar_pedidos(minutos)}
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:3000"], allow_methods=["*"], allow_headers=["*"])

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/produtos")
def listar_produtos():
    sql = text("""
        SELECT p.sku, p.nome, p.categoria, p.preco, p.subcategoria, p.descricao, p.conservacao, p.peso, p.imagem_url, p.preco_original,
               COALESCE(SUM(l.quantidade - l.reservado), 0) AS estoque,
               MIN(l.validade) AS proxima_validade
        FROM produtos p LEFT JOIN lotes l ON l.sku = p.sku
        GROUP BY p.sku ORDER BY p.categoria, p.nome
    """)
    with engine.connect() as c:
        return [dict(r._mapping) for r in c.execute(sql)]

from pydantic import BaseModel, Field
from fastapi import HTTPException

class ItemIn(BaseModel):
    sku: str
    quantidade: int = Field(gt=0)

class PedidoIn(BaseModel):
    cliente: str
    itens: list[ItemIn]

@app.post("/pedidos", status_code=201)
def criar_pedido(p: PedidoIn):
    with engine.begin() as c:  # uma transação: tudo ou nada
        num = c.execute(text("SELECT 'MD-' || LPAD((COALESCE(MAX(id),0)+1)::text, 6, '0') FROM pedidos")).scalar()
        pid = c.execute(text("INSERT INTO pedidos (numero, loja_id, cliente, status, total) VALUES (:n, (SELECT MIN(id) FROM lojas), :c, 'aguardando_pagamento', 0) RETURNING id"), {"n": num, "c": p.cliente}).scalar()
        total = 0
        for item in p.itens:
            falta = item.quantidade
            lotes = c.execute(text("""
                SELECT l.id, l.quantidade - l.reservado AS livre, pr.preco
                FROM lotes l JOIN produtos pr ON pr.sku = l.sku
                WHERE l.sku = :s AND l.quantidade - l.reservado > 0
                ORDER BY l.validade NULLS LAST
                FOR UPDATE OF l
            """), {"s": item.sku}).all()
            for lote in lotes:
                if falta == 0: break
                pega = min(falta, lote.livre)
                c.execute(text("UPDATE lotes SET reservado = reservado + :q WHERE id = :id"), {"q": pega, "id": lote.id})
                c.execute(text("INSERT INTO itens_pedido (pedido_id, sku, quantidade, preco_unitario, lote_id) VALUES (:p, :s, :q, :pr, :l)"),
                          {"p": pid, "s": item.sku, "q": pega, "pr": lote.preco, "l": lote.id})
                total += pega * lote.preco
                falta -= pega
            if falta > 0:
                raise HTTPException(409, f"Estoque insuficiente para {item.sku}")  # desfaz tudo
        c.execute(text("UPDATE pedidos SET total = :t WHERE id = :id"), {"t": total, "id": pid})
    return {"numero": num, "status": "aguardando_pagamento", "total": total}

import uuid, json, time, threading, urllib.request

class PagamentoIn(BaseModel):
    metodo: str  # "pix" ou "cartao"
    cartao_final: str | None = None

def gateway_falso(gateway_id: str, aprovar: bool):
    """Simula o Mercado Pago/Stripe: depois de 5 s avisa nosso webhook."""
    time.sleep(5)
    aviso = {"id": gateway_id, "type": "payment.approved" if aprovar else "payment.refused"}
    req = urllib.request.Request("http://localhost:8000/webhooks/pagamento", data=json.dumps(aviso).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    urllib.request.urlopen(req)

@app.post("/pedidos/{numero}/pagamento", status_code=201)
def criar_pagamento(numero: str, pg: PagamentoIn):
    with engine.begin() as c:
        ped = c.execute(text("SELECT id, total, status FROM pedidos WHERE numero = :n"), {"n": numero}).first()
        if not ped: raise HTTPException(404, "Pedido não encontrado")
        if ped.status != "aguardando_pagamento": raise HTTPException(409, f"Pedido está {ped.status}")
        gid = f"gw_{uuid.uuid4().hex[:16]}"
        pix = f"00020126BR.GOV.BCB.PIX{gid}5204000053039865406{ped.total}5802BR" if pg.metodo == "pix" else None
        c.execute(text("""INSERT INTO pagamentos (pedido_id, metodo, valor, status, gateway_id, pix_copia_cola)
                          VALUES (:p, :m, :v, 'pendente', :g, :x)
                          ON CONFLICT (pedido_id) DO UPDATE SET metodo = :m, gateway_id = :g, pix_copia_cola = :x, status = 'pendente'"""),
                  {"p": ped.id, "m": pg.metodo, "v": ped.total, "g": gid, "x": pix})
    aprovar = not (pg.metodo == "cartao" and pg.cartao_final == "0000")
    threading.Thread(target=gateway_falso, args=(gid, aprovar), daemon=True).start()
    return {"gateway_id": gid, "status": "pendente", "valor": ped.total, "pix_copia_cola": pix}

@app.post("/webhooks/pagamento")
def webhook_pagamento(aviso: dict):
    with engine.begin() as c:
        pg = c.execute(text("SELECT id, pedido_id, status FROM pagamentos WHERE gateway_id = :g FOR UPDATE"), {"g": aviso["id"]}).first()
        if not pg: raise HTTPException(404, "Pagamento desconhecido")
        c.execute(text("INSERT INTO eventos_pagamento (pagamento_id, tipo, payload) VALUES (:p, :t, CAST(:j AS jsonb))"),
                  {"p": pg.id, "t": aviso["type"], "j": json.dumps(aviso)})
        if pg.status != "pendente":
            return {"ok": True, "ignorado": "já processado"}  # idempotência: aviso repetido não faz nada
        if aviso["type"] == "payment.approved":
            c.execute(text("UPDATE pagamentos SET status='aprovado', atualizado_em=now() WHERE id=:id"), {"id": pg.id})
            ok = c.execute(text("UPDATE pedidos SET status='pago' WHERE id=:id AND status='aguardando_pagamento' RETURNING id"), {"id": pg.pedido_id}).first()
            if not ok:  # pedido expirou antes do pagamento: marcar para estorno
                c.execute(text("UPDATE pagamentos SET status='estornar' WHERE id=:id"), {"id": pg.id})
        else:
            c.execute(text("UPDATE pagamentos SET status='recusado', atualizado_em=now() WHERE id=:id"), {"id": pg.id})
            ok = c.execute(text("UPDATE pedidos SET status='pagamento_recusado' WHERE id=:id AND status='aguardando_pagamento' RETURNING id"), {"id": pg.pedido_id}).first()
            if ok: c.execute(text("""UPDATE lotes l SET reservado = l.reservado - i.quantidade
                              FROM itens_pedido i WHERE i.lote_id = l.id AND i.pedido_id = :id"""), {"id": pg.pedido_id})
    return {"ok": True}

@app.get("/pedidos/{numero}")
def ver_pedido(numero: str):
    with engine.connect() as c:
        r = c.execute(text("""SELECT p.numero, p.status, p.total, pg.metodo, pg.status AS pagamento
                              FROM pedidos p LEFT JOIN pagamentos pg ON pg.pedido_id = p.id WHERE p.numero = :n"""), {"n": numero}).first()
    if not r: raise HTTPException(404, "Pedido não encontrado")
    return dict(r._mapping)

from app.auth import confere_pin, gera_token

class LoginIn(BaseModel):
    matricula: str
    pin: str

@app.post("/auth/login")
def login(d: LoginIn):
    with engine.connect() as c:
        f = c.execute(text("SELECT matricula, nome, funcao, pin_hash FROM funcionarios WHERE matricula = :m AND ativo"), {"m": d.matricula}).first()
    if not f or not confere_pin(d.pin, f.pin_hash):
        raise HTTPException(401, "Matrícula ou PIN inválidos")
    return {"token": gera_token(f.matricula, f.nome, f.funcao), "nome": f.nome, "funcao": f.funcao}

from app.auth import exige

@app.get("/separacao/fila")
def fila(u=Depends(exige("separador"))):
    with engine.connect() as c:
        r = c.execute(text("""SELECT p.numero, p.total, COUNT(i.id) AS itens,
                                     EXTRACT(EPOCH FROM now() - p.criado_em)::int AS espera_seg
                              FROM pedidos p JOIN itens_pedido i ON i.pedido_id = p.id
                              WHERE p.status = 'pago' GROUP BY p.id ORDER BY p.criado_em"""))
        return [dict(x._mapping) for x in r]

@app.post("/separacao/pegar")
def pegar(u=Depends(exige("separador"))):
    with engine.begin() as c:
        atual = c.execute(text("SELECT numero FROM pedidos WHERE status='em_separacao' AND separador=:m"), {"m": u["sub"]}).scalar()
        if atual: return detalhe(c, atual)  # já tem pedido em mãos
        p = c.execute(text("""SELECT id, numero FROM pedidos WHERE status='pago'
                              ORDER BY criado_em FOR UPDATE SKIP LOCKED LIMIT 1""")).first()
        if not p: raise HTTPException(404, "Fila vazia")
        c.execute(text("UPDATE pedidos SET status='em_separacao', separador=:m, separacao_inicio=now() WHERE id=:id"), {"m": u["sub"], "id": p.id})
        return detalhe(c, p.numero)

def detalhe(c, numero):
    itens = c.execute(text("""SELECT i.id, i.sku, pr.nome, pr.categoria, pr.corredor, pr.imagem_url, i.quantidade, l.id AS lote, l.validade
                              FROM itens_pedido i JOIN pedidos p ON p.id=i.pedido_id JOIN produtos pr ON pr.sku=i.sku JOIN lotes l ON l.id=i.lote_id
                              WHERE p.numero=:n ORDER BY pr.corredor, pr.nome"""), {"n": numero})
    return {"numero": numero, "itens": [dict(x._mapping) for x in itens]}

SQL_SUBS = """
    SELECT p.sku, p.nome, p.imagem_url, p.preco, SUM(l.quantidade-l.reservado) AS estoque
    FROM produtos p JOIN lotes l ON l.sku=p.sku, produtos o
    WHERE o.sku=:s AND p.sku<>o.sku AND position('_exp-' in p.sku) = 0 {filtro}
      AND (o.conservacao IS NULL OR p.conservacao IS NOT DISTINCT FROM o.conservacao)
    GROUP BY p.sku, o.preco HAVING SUM(l.quantidade-l.reservado)>0
    ORDER BY ABS(p.preco - o.preco), p.nome LIMIT 5"""

@app.get("/separacao/substitutos/{sku}")
def substitutos(sku: str, u=Depends(exige("separador"))):
    """Mesma subcategoria e conservação, preço mais próximo, top 5; se vazio, mesma categoria."""
    with engine.connect() as c:
        r = c.execute(text(SQL_SUBS.format(filtro="AND o.subcategoria IS NOT NULL AND p.subcategoria=o.subcategoria")), {"s": sku}).all()
        if not r:
            r = c.execute(text(SQL_SUBS.format(filtro="AND p.categoria=o.categoria")), {"s": sku}).all()
        return [dict(x._mapping) for x in r]

class ItemSep(BaseModel):
    id: int
    status: str  # separado, faltando, substituido
    substituto_sku: str | None = None

@app.post("/separacao/{numero}/concluir")
def concluir(numero: str, itens: list[ItemSep], u=Depends(exige("separador"))):
    with engine.begin() as c:
        p = c.execute(text("SELECT id, total FROM pedidos WHERE numero=:n AND status='em_separacao' AND separador=:m FOR UPDATE"), {"n": numero, "m": u["sub"]}).first()
        if not p: raise HTTPException(409, "Pedido não está com você")
        faltas = 0
        for it in itens:
            orig = c.execute(text("SELECT lote_id, quantidade, preco_unitario FROM itens_pedido WHERE id=:id AND pedido_id=:p AND status='pendente'"), {"id": it.id, "p": p.id}).first()
            if not orig: continue
            st, novo_lote, preco = it.status, orig.lote_id, orig.preco_unitario
            if st not in ("separado", "faltando", "substituido"): st = "faltando"
            if st == "substituido":
                lote = c.execute(text("""SELECT l.id, pr.preco FROM lotes l JOIN produtos pr ON pr.sku=l.sku
                                         WHERE l.sku=:s AND l.quantidade-l.reservado>=:q
                                         ORDER BY l.validade NULLS LAST FOR UPDATE OF l LIMIT 1"""), {"s": it.substituto_sku, "q": orig.quantidade}).first()
                if lote:
                    c.execute(text("UPDATE lotes SET reservado=reservado+:q WHERE id=:id"), {"q": orig.quantidade, "id": lote.id})
                    novo_lote = lote.id
                    preco = min(orig.preco_unitario, lote.preco)  # cliente nunca paga mais pelo substituto
                else:
                    st = "faltando"  # substituto sem saldo vira falta
            if st in ("faltando", "substituido"):
                c.execute(text("UPDATE lotes SET reservado=reservado-:q WHERE id=:id"), {"q": orig.quantidade, "id": orig.lote_id})
            if st == "faltando": faltas += 1
            c.execute(text("UPDATE itens_pedido SET status=:st, substituto_sku=:sub, lote_id=:l, preco_unitario=:pr WHERE id=:id"),
                      {"st": st, "sub": it.substituto_sku if st == "substituido" else None, "l": novo_lote, "pr": preco, "id": it.id})
        novo = c.execute(text("SELECT COALESCE(SUM(quantidade*preco_unitario),0) FROM itens_pedido WHERE pedido_id=:p AND status IN ('separado','substituido')"), {"p": p.id}).scalar()
        reembolso = p.total - novo
        c.execute(text("UPDATE pedidos SET status='pronto', separacao_fim=now(), total=:t, reembolso=:r WHERE id=:id"), {"t": novo, "r": reembolso, "id": p.id})
    return {"numero": numero, "status": "pronto", "faltas": faltas, "total": novo, "reembolso": reembolso}

def resumo_entrega(c, numero):
    r = c.execute(text("""SELECT numero, status, endereco, total, reembolso,
            EXTRACT(EPOCH FROM saiu_em - criado_em)::int AS loja_seg,
            EXTRACT(EPOCH FROM entregue_em - saiu_em)::int AS rota_seg,
            EXTRACT(EPOCH FROM entregue_em - criado_em)::int AS total_seg
        FROM pedidos WHERE numero = :n"""), {"n": numero}).first()
    return dict(r._mapping)

@app.get("/entrega/minha")
def minha_entrega(u=Depends(exige("entregador"))):
    with engine.connect() as c:
        n = c.execute(text("SELECT numero FROM pedidos WHERE entregador=:m AND status IN ('atribuido','a_caminho')"), {"m": u["sub"]}).scalar()
        prontos = c.execute(text("SELECT COUNT(*) FROM pedidos WHERE status='pronto'")).scalar()
        return {"pedido": resumo_entrega(c, n) if n else None, "prontos_na_loja": prontos}

@app.post("/entrega/pegar")
def pegar_entrega(u=Depends(exige("entregador"))):
    with engine.begin() as c:
        if c.execute(text("SELECT 1 FROM pedidos WHERE entregador=:m AND status IN ('atribuido','a_caminho')"), {"m": u["sub"]}).first():
            raise HTTPException(409, "Você já tem uma entrega em andamento")
        p = c.execute(text("SELECT id, numero FROM pedidos WHERE status='pronto' ORDER BY separacao_fim FOR UPDATE SKIP LOCKED LIMIT 1")).first()
        if not p: raise HTTPException(404, "Nenhum pedido pronto na loja")
        c.execute(text("UPDATE pedidos SET status='atribuido', entregador=:m WHERE id=:id"), {"m": u["sub"], "id": p.id})
        c.execute(text("UPDATE funcionarios SET disponivel=false WHERE matricula=:m"), {"m": u["sub"]})
        return resumo_entrega(c, p.numero)

@app.post("/entrega/{numero}/retirei")
def retirei(numero: str, u=Depends(exige("entregador"))):
    with engine.begin() as c:
        ok = c.execute(text("UPDATE pedidos SET status='a_caminho', saiu_em=now() WHERE numero=:n AND entregador=:m AND status='atribuido' RETURNING id"), {"n": numero, "m": u["sub"]}).first()
        if not ok: raise HTTPException(409, "Pedido não está atribuído a você")
        return resumo_entrega(c, numero)

@app.post("/entrega/{numero}/entreguei")
def entreguei(numero: str, u=Depends(exige("entregador"))):
    with engine.begin() as c:
        ok = c.execute(text("UPDATE pedidos SET status='entregue', entregue_em=now() WHERE numero=:n AND entregador=:m AND status='a_caminho' RETURNING id"), {"n": numero, "m": u["sub"]}).first()
        if not ok: raise HTTPException(409, "Pedido não está a caminho com você")
        c.execute(text("""UPDATE lotes l SET quantidade = l.quantidade - i.quantidade, reservado = l.reservado - i.quantidade
                          FROM itens_pedido i WHERE i.lote_id = l.id AND i.pedido_id = :id AND i.status IN ('separado','substituido')"""), {"id": ok.id})
        c.execute(text("UPDATE funcionarios SET disponivel=true WHERE matricula=:m"), {"m": u["sub"]})
        return resumo_entrega(c, numero)

import os, base64

def traccar(path: str):
    url = os.environ["TRACCAR_URL"] + path
    cred = base64.b64encode(f'{os.environ["TRACCAR_USER"]}:{os.environ["TRACCAR_PASS"]}'.encode()).decode()
    req = urllib.request.Request(url, headers={"Authorization": f"Basic {cred}", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())

@app.get("/entrega/{numero}/posicao")
def posicao(numero: str):
    with engine.connect() as c:
        f = c.execute(text("""SELECT f.nome, f.device_id, p.status FROM pedidos p JOIN funcionarios f ON f.matricula = p.entregador
                              WHERE p.numero = :n"""), {"n": numero}).first()
    if not f or not f.device_id: raise HTTPException(404, "Pedido sem entregador rastreável")
    dev = next((d for d in traccar("/api/devices") if d["uniqueId"] == f.device_id), None)
    if not dev or not dev.get("positionId"): raise HTTPException(404, "Sem posição no Traccar")
    pos = traccar(f"/api/positions?id={dev['positionId']}")[0]
    return {"entregador": f.nome, "status_pedido": f.status, "lat": pos["latitude"], "lon": pos["longitude"],
            "velocidade_kmh": round(pos["speed"] * 1.852, 1), "atualizado": pos["fixTime"]}
