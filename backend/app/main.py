from fastapi import FastAPI
from sqlalchemy import text
from app.db import engine

app = FastAPI(title="Daki Replica")
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:3000"], allow_methods=["*"], allow_headers=["*"])

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/produtos")
def listar_produtos():
    sql = text("""
        SELECT p.sku, p.nome, p.categoria, p.preco, p.subcategoria, p.conservacao, p.peso, p.imagem_url, p.preco_original,
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
        num = c.execute(text("SELECT 'MD-' || LPAD((COUNT(*)+1)::text, 6, '0') FROM pedidos")).scalar()
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
            c.execute(text("UPDATE pedidos SET status='pago' WHERE id=:id"), {"id": pg.pedido_id})
        else:
            c.execute(text("UPDATE pagamentos SET status='recusado', atualizado_em=now() WHERE id=:id"), {"id": pg.id})
            c.execute(text("UPDATE pedidos SET status='pagamento_recusado' WHERE id=:id"), {"id": pg.pedido_id})
            c.execute(text("""UPDATE lotes l SET reservado = l.reservado - i.quantidade
                              FROM itens_pedido i WHERE i.lote_id = l.id AND i.pedido_id = :id"""), {"id": pg.pedido_id})
    return {"ok": True}

@app.get("/pedidos/{numero}")
def ver_pedido(numero: str):
    with engine.connect() as c:
        r = c.execute(text("""SELECT p.numero, p.status, p.total, pg.metodo, pg.status AS pagamento
                              FROM pedidos p LEFT JOIN pagamentos pg ON pg.pedido_id = p.id WHERE p.numero = :n"""), {"n": numero}).first()
    if not r: raise HTTPException(404, "Pedido não encontrado")
    return dict(r._mapping)
