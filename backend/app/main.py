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

class EnderecoIn(BaseModel):
    cep: str = Field(pattern=r"^\d{5}-?\d{3}$")
    rua: str = Field(min_length=2, max_length=150)
    numero_end: str = Field(min_length=1, max_length=20)
    complemento: str | None = Field(None, max_length=80)
    bairro: str = Field(min_length=1, max_length=80)
    cidade: str = Field(min_length=2, max_length=80)
    uf: str = Field(pattern=r"^[A-Za-z]{2}$")
    referencia: str | None = Field(None, max_length=150)
    lat: float | None = Field(None, ge=-90, le=90)
    lon: float | None = Field(None, ge=-180, le=180)

class PedidoIn(BaseModel):
    cliente: str
    itens: list[ItemIn] = Field(min_length=1)
    endereco: EnderecoIn

def nominatim(q: str):
    """Geocodifica no OpenStreetMap; devolve (lat, lon) ou None."""
    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode({"q": q, "format": "json", "limit": 1, "countrycodes": "br"})
    req = urllib.request.Request(url, headers={"User-Agent": "OrbitaSuper/1.0", "Accept-Language": "pt-BR"})
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            d = json.loads(r.read())
        return (float(d[0]["lat"]), float(d[0]["lon"])) if d else None
    except Exception:
        return None

def geocodificar(rua: str, numero: str | None, cidade: str, uf: str):
    return (nominatim(f"{rua}, {numero}, {cidade}, {uf}, Brasil") if numero else None) or nominatim(f"{rua}, {cidade}, {uf}, Brasil")

@app.get("/geo/geocode")
def geo_geocode(rua: str, cidade: str, uf: str, numero: str | None = None):
    pos = geocodificar(rua, numero, cidade, uf)
    if not pos: raise HTTPException(404, "Endereço não encontrado no mapa")
    return {"lat": pos[0], "lon": pos[1]}

@app.post("/pedidos", status_code=201)
def criar_pedido(p: PedidoIn):
    e = p.endereco
    if e.lat is None or e.lon is None:  # sem pino do cliente: geocodifica fora da transação
        pos = geocodificar(e.rua, e.numero_end, e.cidade, e.uf)
        if pos: e.lat, e.lon = pos
    with engine.begin() as c:  # uma transação: tudo ou nada
        cep = e.cep.replace("-", ""); cep = f"{cep[:5]}-{cep[5:]}"
        linha = f"{e.rua}, {e.numero_end}" + (f" - {e.complemento}" if e.complemento else "") + f" - {e.bairro}, {e.cidade}/{e.uf.upper()} - CEP {cep}"
        num = c.execute(text("SELECT 'MD-' || LPAD(nextval('pedido_numero_seq')::text, 6, '0')")).scalar()
        pid = c.execute(text("""INSERT INTO pedidos (numero, loja_id, cliente, status, total, endereco, cep, rua, numero_end, complemento, bairro, cidade, uf, referencia, lat, lon)
                                VALUES (:n, (SELECT MIN(id) FROM lojas), :c, 'aguardando_pagamento', 0, :linha, :cep, :rua, :num, :comp, :bairro, :cidade, :uf, :ref, :lat, :lon) RETURNING id"""),
                            {"n": num, "c": p.cliente, "linha": linha[:200], "cep": cep, "rua": e.rua, "num": e.numero_end, "comp": e.complemento or None,
                             "bairro": e.bairro, "cidade": e.cidade, "uf": e.uf.upper(), "ref": e.referencia or None, "lat": e.lat, "lon": e.lon}).scalar()
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
    return {"numero": num, "status": "aguardando_pagamento", "total": total, "lat": e.lat, "lon": e.lon}

import uuid, json, time, threading, urllib.request, urllib.parse

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
    r = c.execute(text("""SELECT numero, status, endereco, total, reembolso, rua, numero_end, complemento, bairro, cidade, uf, cep, referencia,
            lat::float AS lat, lon::float AS lon, (SELECT lat::float FROM lojas l WHERE l.id = pedidos.loja_id) AS loja_lat, (SELECT lon::float FROM lojas l WHERE l.id = pedidos.loja_id) AS loja_lon,
            EXTRACT(EPOCH FROM saiu_em - criado_em)::int AS loja_seg,            -- clique até sair da loja
            EXTRACT(EPOCH FROM chegou_em - saiu_em)::int AS rota_seg,            -- saída até chegada
            EXTRACT(EPOCH FROM entregue_em - chegou_em)::int AS porta_seg,       -- chegada até entregue
            EXTRACT(EPOCH FROM entregue_em - criado_em)::int AS total_seg,
            EXTRACT(EPOCH FROM now() - saiu_em)::int AS desde_saida_seg,         -- para o cronômetro sobreviver a recarga
            EXTRACT(EPOCH FROM now() - chegou_em)::int AS desde_chegada_seg
        FROM pedidos WHERE numero = :n"""), {"n": numero}).first()
    return dict(r._mapping)

@app.get("/entrega/minha")
def minha_entrega(u=Depends(exige("entregador"))):
    with engine.connect() as c:
        n = c.execute(text("SELECT numero FROM pedidos WHERE entregador=:m AND status IN ('atribuido','a_caminho','chegou')"), {"m": u["sub"]}).scalar()
        prontos = c.execute(text("SELECT COUNT(*) FROM pedidos WHERE status='pronto'")).scalar()
        return {"pedido": resumo_entrega(c, n) if n else None, "prontos_na_loja": prontos}

@app.post("/entrega/pegar")
def pegar_entrega(u=Depends(exige("entregador"))):
    with engine.begin() as c:
        if c.execute(text("SELECT 1 FROM pedidos WHERE entregador=:m AND status IN ('atribuido','a_caminho','chegou')"), {"m": u["sub"]}).first():
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

@app.post("/entrega/{numero}/cheguei")
def cheguei(numero: str, u=Depends(exige("entregador"))):
    with engine.begin() as c:
        ok = c.execute(text("UPDATE pedidos SET status='chegou', chegou_em=now() WHERE numero=:n AND entregador=:m AND status='a_caminho' RETURNING id"), {"n": numero, "m": u["sub"]}).first()
        if not ok: raise HTTPException(409, "Pedido não está a caminho com você")
        return resumo_entrega(c, numero)

@app.post("/entrega/{numero}/entreguei")
def entreguei(numero: str, u=Depends(exige("entregador"))):
    with engine.begin() as c:
        ok = c.execute(text("""UPDATE pedidos SET status='entregue', entregue_em=now(), chegou_em=COALESCE(chegou_em, now())
                               WHERE numero=:n AND entregador=:m AND status IN ('a_caminho','chegou') RETURNING id"""), {"n": numero, "m": u["sub"]}).first()
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

# ---- Distância percorrida por viagem, calculada com as posições do Traccar ----
import math
_cache_km: dict[str, float] = {}         # numero do pedido -> km (entrega concluída não muda, então guarda para sempre)
_cache_dev: dict[str, int] = {}          # uniqueId do aparelho -> id interno do Traccar
_traccar_off_ate = 0.0                   # se o Traccar falhar, não tenta de novo por 60 s (evita deixar o painel lento)

def haversine_km(a, b):
    """Distância em km entre dois pontos (lat, lon) na superfície da Terra."""
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))

_cache_pos: dict[str, list] = {}        # numero -> posições da viagem (só para entregas concluídas)

def posicoes_viagem(numero, unique_id, de, ate, final=True):
    """Posições do Traccar entre a saída e a entrega: [(lat, lon, km/h, horário ISO)]. None se indisponível.
    Só guarda no cache quando a entrega terminou (final=True); em rota busca de novo."""
    global _traccar_off_ate
    if numero in _cache_pos: return _cache_pos[numero]
    if not unique_id or not de or not ate or time.time() < _traccar_off_ate or not os.environ.get("TRACCAR_URL"): return None
    try:
        if unique_id not in _cache_dev:
            for d in traccar("/api/devices"): _cache_dev[d["uniqueId"]] = d["id"]
        dev = _cache_dev.get(unique_id)
        if dev is None: return None
        iso = lambda t: datetime.fromisoformat(str(t)).astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%SZ")
        pos = traccar(f"/api/positions?deviceId={dev}&from={iso(de)}&to={iso(ate)}")
        pts = [(p["latitude"], p["longitude"], round(p.get("speed", 0) * 1.852, 1), p.get("fixTime")) for p in pos if p.get("valid", True)]
        if final: _cache_pos[numero] = pts
        return pts
    except Exception:
        _traccar_off_ate = time.time() + 60   # Traccar fora: espera 60 s antes de tentar de novo
        return None

def distancia_viagem(numero, unique_id, de, ate):
    """km entre a saída da loja e a entrega; None se não houver Traccar/posições."""
    if numero in _cache_km: return _cache_km[numero]
    pts = posicoes_viagem(numero, unique_id, de, ate)
    if pts is None: return None
    km = sum(haversine_km(pts[i], pts[i + 1]) for i in range(len(pts) - 1))
    _cache_km[numero] = km
    return km

def metricas_gps(pts, destino=None):
    """Indicadores da viagem a partir das posições: distância, velocidades, tempo parado e desvio."""
    if not pts or len(pts) < 2: return None
    t = [datetime.fromisoformat(str(p[3]).replace("Z", "+00:00")) for p in pts]
    dist = sum(haversine_km(pts[i], pts[i + 1]) for i in range(len(pts) - 1))
    horas = max((t[-1] - t[0]).total_seconds() / 3600, 1e-9)
    # parado = trechos entre posições com velocidade < 3 km/h; conta paradas que somam mais de 1 min seguidas
    parado, paradas, trecho = 0.0, 0, 0.0
    for i in range(len(pts) - 1):
        dt = (t[i + 1] - t[i]).total_seconds()
        if pts[i][2] < 3:
            parado += dt; trecho += dt
        else:
            paradas += trecho > 60; trecho = 0.0
    paradas += trecho > 60
    fim = destino if destino and destino[0] is not None else pts[-1]
    reta = haversine_km(pts[0], fim)   # distância em linha reta da saída até o cliente
    return {"dist_km": round(dist, 2), "vel_media": round(dist / horas, 1), "vel_max": max(p[2] for p in pts),
            "parado_min": round(parado / 60, 1), "paradas": int(paradas), "reta_km": round(reta, 2),
            "desvio": round(dist / reta, 2) if reta > 0.05 else None}   # 1,0 = foi reto; 1,5 = rodou 50% a mais

@app.get("/entrega/{numero}/posicao")
def posicao(numero: str):
    with engine.connect() as c:
        f = c.execute(text("""SELECT f.nome, f.device_id, p.status FROM pedidos p JOIN funcionarios f ON f.matricula = p.entregador
                              WHERE p.numero = :n"""), {"n": numero}).first()
    if not f or not f.device_id: raise HTTPException(404, "Pedido sem entregador rastreável")
    try:
        dev = next((d for d in traccar("/api/devices") if d["uniqueId"] == f.device_id), None)
        if not dev or not dev.get("positionId"): raise HTTPException(404, "Sem posição no Traccar")
        pos = traccar(f"/api/positions?id={dev['positionId']}")[0]
    except HTTPException: raise
    except Exception:
        raise HTTPException(503, "Traccar indisponível")
    return {"entregador": f.nome, "status_pedido": f.status, "lat": pos["latitude"], "lon": pos["longitude"],
            "velocidade_kmh": round(pos["speed"] * 1.852, 1), "atualizado": pos["fixTime"]}

import jwt
from app.auth import bearer, SEGREDO

def qualquer_funcionario(cred=Depends(bearer)):
    try:
        return jwt.decode(cred.credentials, SEGREDO, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(401, "Crachá inválido ou expirado")

@app.get("/operacao/quadro")
def quadro(u=Depends(qualquer_funcionario)):
    """Quadro da loja (somente leitura): pedidos por etapa, com responsável e tempo."""
    with engine.connect() as c:
        r = c.execute(text("""
            SELECT p.numero, p.status, p.total, COUNT(i.id) AS itens,
                   fs.nome AS separador, fe.nome AS entregador,
                   EXTRACT(EPOCH FROM now() - p.criado_em)::int AS desde_criado_seg,
                   EXTRACT(EPOCH FROM now() - COALESCE(CASE p.status
                        WHEN 'em_separacao' THEN p.separacao_inicio
                        WHEN 'pronto' THEN p.separacao_fim
                        WHEN 'a_caminho' THEN p.saiu_em
                        WHEN 'chegou' THEN p.chegou_em
                        WHEN 'atribuido' THEN p.separacao_fim END, p.criado_em))::int AS etapa_seg
            FROM pedidos p
            LEFT JOIN itens_pedido i ON i.pedido_id = p.id
            LEFT JOIN funcionarios fs ON fs.matricula = p.separador
            LEFT JOIN funcionarios fe ON fe.matricula = p.entregador
            WHERE p.status IN ('pago','em_separacao','pronto','atribuido','a_caminho','chegou')
            GROUP BY p.id, fs.nome, fe.nome ORDER BY p.criado_em"""))
        col = {"pagos": [], "em_separacao": [], "prontos": [], "em_rota": []}
        mapa = {"pago": "pagos", "em_separacao": "em_separacao", "pronto": "prontos", "atribuido": "em_rota", "a_caminho": "em_rota", "chegou": "em_rota"}
        for x in r:
            col[mapa[x.status]].append(dict(x._mapping))
        return col

# ---------------- Área do gerente · passo 1: resumo do dia ----------------
from datetime import date, datetime
from zoneinfo import ZoneInfo
# Metas de tempo (em segundos) usadas nos indicadores de SLA
META_LOJA = 5 * 60    # clique do cliente até o pedido sair da loja
META_ROTA = 15 * 60   # saída da loja até chegar na porta
META_PORTA = 3 * 60   # chegada até entregar na mão do cliente
META_TOTAL = 20 * 60  # clique até entregue

@app.get("/gerente/resumo")
def gerente_resumo(de: date | None = None, ate: date | None = None, u=Depends(exige("gerente"))):  # só gerente (outros: 403)
    # Período em dias de São Paulo, inclusivo (?de=AAAA-MM-DD&ate=AAAA-MM-DD). Sem parâmetros = hoje.
    hoje_sp = datetime.now(ZoneInfo("America/Sao_Paulo")).date()
    ate = ate or (de or hoje_sp)
    de = de or ate
    if de > ate: raise HTTPException(422, "'de' não pode ser depois de 'ate'")
    if (ate - de).days > 30: raise HTTPException(422, "Período máximo de 31 dias")
    # Filtro usado em todas as consultas abaixo (:de e :ate entram como parâmetros, sem risco de injeção)
    hoje = "(p.criado_em AT TIME ZONE 'America/Sao_Paulo')::date BETWEEN :de AND :ate"
    per = {"de": de, "ate": ate}
    with engine.connect() as c:
        # 1) Quantos pedidos de hoje estão em cada status
        contagem = {s: 0 for s in ("aguardando_pagamento", "pago", "em_separacao", "pronto", "em_rota", "entregue", "expirado")}
        for r in c.execute(text(f"SELECT p.status, COUNT(*) AS n FROM pedidos p WHERE {hoje} GROUP BY p.status"), per):
            chave = "em_rota" if r.status in ("atribuido", "a_caminho", "chegou") else r.status  # junta as etapas da rua
            contagem[chave] = contagem.get(chave, 0) + r.n
        # 2) Faturamento: soma do total dos pedidos entregues hoje
        faturamento = c.execute(text(f"SELECT COALESCE(SUM(p.total), 0) FROM pedidos p WHERE {hoje} AND p.status = 'entregue'"), per).scalar()
        # 3) Lista dos pedidos de hoje, mais novos primeiro, com nomes de quem separou e entregou
        #    e os tempos de cada etapa em segundos (NULL quando a etapa ainda não terminou)
        andamento = "p.status IN ('pago','em_separacao','pronto','atribuido','a_caminho','chegou')"
        pedidos = c.execute(text(f"""
            SELECT p.numero, p.status, p.cliente, p.bairro, p.total, p.criado_em,
                   fs.nome AS separador, fe.nome AS entregador,
                   (SELECT COUNT(*) FROM itens_pedido i WHERE i.pedido_id = p.id) AS itens,
                   EXTRACT(EPOCH FROM p.saiu_em - p.criado_em)::int     AS loja,
                   EXTRACT(EPOCH FROM p.chegou_em - p.saiu_em)::int     AS rota,
                   EXTRACT(EPOCH FROM p.entregue_em - p.chegou_em)::int AS porta,
                   EXTRACT(EPOCH FROM p.entregue_em - p.criado_em)::int AS total_seg,
                   -- no prazo: só faz sentido para entregues (senão NULL)
                   CASE WHEN p.status = 'entregue' THEN EXTRACT(EPOCH FROM p.entregue_em - p.criado_em) <= :meta END AS no_prazo,
                   -- em andamento: há quanto tempo está na etapa atual e desde o clique
                   CASE WHEN {andamento} THEN EXTRACT(EPOCH FROM now() - COALESCE(CASE p.status
                        WHEN 'em_separacao' THEN p.separacao_inicio WHEN 'pronto' THEN p.separacao_fim
                        WHEN 'atribuido' THEN p.separacao_fim WHEN 'a_caminho' THEN p.saiu_em
                        WHEN 'chegou' THEN p.chegou_em END, p.criado_em))::int END AS decorrido,
                   CASE WHEN {andamento} THEN EXTRACT(EPOCH FROM now() - p.criado_em)::int END AS idade,
                   -- atrasado: entregue fora da meta OU ainda em andamento além da meta total
                   (p.status = 'entregue' AND EXTRACT(EPOCH FROM p.entregue_em - p.criado_em) > :meta)
                     OR ({andamento} AND EXTRACT(EPOCH FROM now() - p.criado_em) > :meta) AS atrasado
            FROM pedidos p
            LEFT JOIN funcionarios fs ON fs.matricula = p.separador
            LEFT JOIN funcionarios fe ON fe.matricula = p.entregador
            WHERE {hoje} ORDER BY p.criado_em DESC"""), {"meta": META_TOTAL, **per})
        pedidos = [dict(x._mapping) for x in pedidos]
        # 4) Tempos médios dos pedidos entregues hoje (mesmas contas do placar do entregador)
        t = c.execute(text(f"""
            SELECT AVG(EXTRACT(EPOCH FROM p.saiu_em - p.criado_em))::int     AS loja,
                   AVG(EXTRACT(EPOCH FROM p.chegou_em - p.saiu_em))::int     AS rota,
                   AVG(EXTRACT(EPOCH FROM p.entregue_em - p.chegou_em))::int AS porta,
                   AVG(EXTRACT(EPOCH FROM p.entregue_em - p.criado_em))::int AS total,
                   COUNT(*) AS entregues,
                   COUNT(*) FILTER (WHERE EXTRACT(EPOCH FROM p.entregue_em - p.criado_em) <= :meta) AS no_prazo
            FROM pedidos p WHERE {hoje} AND p.status = 'entregue'"""), {"meta": META_TOTAL, **per}).first()
        tempos = {
            "loja": t.loja, "rota": t.rota, "porta": t.porta, "total": t.total,  # médias em segundos (None se nada entregue)
            "metas": {"loja": META_LOJA, "rota": META_ROTA, "porta": META_PORTA, "total": META_TOTAL},
            "entregues": t.entregues,
            "no_prazo_pct": round(100 * t.no_prazo / t.entregues) if t.entregues else None,  # % entregue dentro da meta total
            "atrasados": t.entregues - t.no_prazo,
        }
        # 5) Indicadores por entregador no período (todo entregador cadastrado + quem entregou no período)
        linhas = c.execute(text(f"""
            WITH ent AS (   -- entregas concluídas no período
                SELECT p.entregador AS mat, p.numero, p.saiu_em, p.entregue_em,
                       EXTRACT(EPOCH FROM p.chegou_em - p.saiu_em)    AS rota,
                       EXTRACT(EPOCH FROM p.entregue_em - p.chegou_em) AS porta,
                       EXTRACT(EPOCH FROM p.entregue_em - p.criado_em) AS total
                FROM pedidos p WHERE {hoje} AND p.status = 'entregue' AND p.entregador IS NOT NULL)
            SELECT f.matricula, f.nome, f.device_id,
                   COUNT(e.numero) AS entregas,
                   AVG(e.rota)::int AS rota, AVG(e.porta)::int AS porta, AVG(e.total)::int AS total,
                   COUNT(*) FILTER (WHERE e.total > :meta) AS atrasos,
                   COUNT(*) FILTER (WHERE e.total <= :meta) AS no_prazo,
                   -- agora: pedido em andamento com ele (se houver)
                   (SELECT p2.numero FROM pedidos p2 WHERE p2.entregador = f.matricula
                      AND p2.status IN ('atribuido','a_caminho','chegou') LIMIT 1) AS pedido_atual,
                   COALESCE(json_agg(json_build_object('numero', e.numero, 'de', e.saiu_em, 'ate', e.entregue_em))
                            FILTER (WHERE e.numero IS NOT NULL), '[]') AS viagens
            FROM funcionarios f LEFT JOIN ent e ON e.mat = f.matricula
            WHERE (f.funcao = 'entregador' AND f.ativo) OR e.numero IS NOT NULL
            GROUP BY f.matricula ORDER BY f.nome"""), {"meta": META_TOTAL, **per}).all()
        entregadores = []
        for r in linhas:
            # distância: soma das viagens com GPS (None se nenhuma viagem tiver dados do Traccar)
            kms = [distancia_viagem(v["numero"], r.device_id, v["de"], v["ate"]) for v in r.viagens] if r.device_id else []
            kms = [k for k in kms if k is not None]
            entregadores.append({
                "matricula": r.matricula, "nome": r.nome, "entregas": r.entregas,
                "rota": r.rota, "porta": r.porta, "total": r.total, "atrasos": r.atrasos,
                "no_prazo_pct": round(100 * r.no_prazo / r.entregas) if r.entregas else None,
                "pedido_atual": r.pedido_atual,  # None = disponível
                "distancia_km": round(sum(kms), 1) if kms else None,
            })
        return {"de": de, "ate": ate, "hoje": hoje_sp, "entregadores": entregadores, "contagem": contagem, "faturamento": faturamento, "pedidos": pedidos, "tempos": tempos}


# ---------------- Gerente · análise de entregas ----------------
DIAS = ["dom", "seg", "ter", "qua", "qui", "sex", "sáb"]

def faixa_horario(h: int) -> str:
    """Faixa do dia pelo horário do pedido (São Paulo)."""
    return "manhã" if 6 <= h < 11 else "almoço" if h < 14 and h >= 11 else "tarde" if 14 <= h < 18 else "noite"

def periodo_sp(de, ate):
    """Mesmas regras do resumo: dias de São Paulo, inclusivo, padrão hoje, máximo 31 dias."""
    hoje_sp = datetime.now(ZoneInfo("America/Sao_Paulo")).date()
    ate = ate or (de or hoje_sp); de = de or ate
    if de > ate: raise HTTPException(422, "'de' não pode ser depois de 'ate'")
    if (ate - de).days > 30: raise HTTPException(422, "Período máximo de 31 dias")
    return de, ate

# ---- Clima (Open-Meteo) e rota esperada (OSRM): buscados em segundo plano e guardados no banco ----
# A tabela nunca espera por essas APIs: se ainda não há dado, mostra "—" e um trabalhador busca e grava.
WMO = {0: ("Céu limpo", "☀️"), 1: ("Quase limpo", "🌤️"), 2: ("Parcialmente nublado", "⛅"), 3: ("Nublado", "☁️"),
       45: ("Neblina", "🌫️"), 48: ("Neblina", "🌫️"), 51: ("Garoa fraca", "🌦️"), 53: ("Garoa", "🌦️"), 55: ("Garoa forte", "🌧️"),
       61: ("Chuva fraca", "🌦️"), 63: ("Chuva", "🌧️"), 65: ("Chuva forte", "🌧️"), 80: ("Pancadas fracas", "🌦️"),
       81: ("Pancadas de chuva", "🌧️"), 82: ("Pancadas fortes", "⛈️"), 95: ("Trovoada", "⛈️"), 96: ("Trovoada c/ granizo", "⛈️"), 99: ("Trovoada c/ granizo", "⛈️")}

def estacao(d: date) -> str:
    """Estação do ano no hemisfério sul (datas aproximadas dos equinócios/solstícios)."""
    md = (d.month, d.day)
    if md >= (12, 21) or md < (3, 20): return "verão"
    if md < (6, 21): return "outono"
    if md < (9, 23): return "inverno"
    return "primavera"

def chave_clima(dia: date, hora: int, lat: float, lon: float) -> str:
    # arredonda o local em ~10 km (1 casa decimal): bairros vizinhos dividem o mesmo dado
    return f"{dia}|{hora:02d}|{lat:.1f}|{lon:.1f}"

_fila_ext: set = set()        # tarefas pendentes, sem repetição: ("clima", dia, lat, lon) ou ("osrm", numero, ...)
_fila_lock = threading.Lock()

def _get_json(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "OrbitaSuper/1.0"})
    with urllib.request.urlopen(req, timeout=3) as r:   # 3 s no máximo; falhou, tenta numa próxima atualização
        return json.loads(r.read())

def _buscar_clima_dia(dia: date, lat: float, lon: float):
    """Busca as 24 horas do dia de uma vez e grava todas no cache."""
    hoje = datetime.now(ZoneInfo("America/Sao_Paulo")).date()
    base = "https://api.open-meteo.com/v1/forecast" if (hoje - dia).days <= 80 else "https://archive-api.open-meteo.com/v1/archive"
    d = _get_json(f"{base}?latitude={lat:.1f}&longitude={lon:.1f}&hourly=temperature_2m,precipitation,weather_code"
                  f"&start_date={dia}&end_date={dia}&timezone=America%2FSao_Paulo")
    h = d["hourly"]
    with engine.begin() as c:
        for i, t in enumerate(h["time"]):
            c.execute(text("""INSERT INTO clima_cache (chave, temp, chuva_mm, codigo) VALUES (:k, :t, :p, :c)
                              ON CONFLICT (chave) DO UPDATE SET temp = :t, chuva_mm = :p, codigo = :c"""),
                      {"k": chave_clima(dia, int(t[11:13]), lat, lon), "t": h["temperature_2m"][i], "p": h["precipitation"][i], "c": h["weather_code"][i]})

def _buscar_osrm(numero: str, la1, lo1, la2, lo2):
    d = _get_json(f"https://router.project-osrm.org/route/v1/driving/{lo1},{la1};{lo2},{la2}?overview=false")
    if d.get("code") == "Ok":
        with engine.begin() as c:
            c.execute(text("UPDATE pedidos SET rota_esperada_seg = :s WHERE numero = :n"), {"s": int(d["routes"][0]["duration"]), "n": numero})

def _trabalhador_externo():
    """Processa a fila em segundo plano, uma tarefa por vez (educado com as APIs públicas)."""
    while True:
        with _fila_lock:
            tarefa = next(iter(_fila_ext), None)
        if tarefa is None:
            time.sleep(1); continue
        try:
            if tarefa[0] == "clima": _buscar_clima_dia(*tarefa[1:])
            else: _buscar_osrm(*tarefa[1:])
        except Exception as e:
            print("API externa falhou:", tarefa[0], e, flush=True)
        with _fila_lock:
            _fila_ext.discard(tarefa)
        time.sleep(0.5)

threading.Thread(target=_trabalhador_externo, daemon=True).start()

def pedir(tarefa):
    with _fila_lock:
        if len(_fila_ext) < 200: _fila_ext.add(tarefa)

@app.get("/gerente/entregas")
def gerente_entregas(de: date | None = None, ate: date | None = None, u=Depends(exige("gerente"))):
    """Uma linha por entrega (entregue ou em rota) no período, com tempos e indicadores de GPS."""
    de, ate = periodo_sp(de, ate)
    with engine.connect() as c:
        rows = c.execute(text("""
            SELECT p.numero, p.status, p.cliente, p.bairro, p.criado_em, p.saiu_em, p.chegou_em, p.entregue_em,
                   p.lat::float AS lat, p.lon::float AS lon, f.nome AS entregador, f.device_id,
                   EXTRACT(HOUR FROM p.criado_em AT TIME ZONE 'America/Sao_Paulo')::int AS hora,
                   EXTRACT(DOW FROM p.criado_em AT TIME ZONE 'America/Sao_Paulo')::int AS dow,
                   EXTRACT(EPOCH FROM p.saiu_em - p.criado_em)::int     AS loja,
                   EXTRACT(EPOCH FROM p.chegou_em - p.saiu_em)::int     AS rota,
                   EXTRACT(EPOCH FROM p.entregue_em - p.chegou_em)::int AS porta,
                   EXTRACT(EPOCH FROM COALESCE(p.entregue_em, now()) - p.criado_em)::int AS total,
                   (p.criado_em AT TIME ZONE 'America/Sao_Paulo')::date AS dia,
                   EXTRACT(HOUR FROM COALESCE(p.saiu_em, p.criado_em) AT TIME ZONE 'America/Sao_Paulo')::int AS hora_saida,
                   p.rota_esperada_seg, lj.lat::float AS loja_lat, lj.lon::float AS loja_lon
            FROM pedidos p LEFT JOIN funcionarios f ON f.matricula = p.entregador
            LEFT JOIN lojas lj ON lj.id = p.loja_id
            WHERE (p.criado_em AT TIME ZONE 'America/Sao_Paulo')::date BETWEEN :de AND :ate
              AND p.status IN ('entregue', 'a_caminho', 'chegou')
            ORDER BY p.criado_em DESC"""), {"de": de, "ate": ate}).all()
    saida = []
    climas: dict = {}                      # cache local desta requisição (vários pedidos na mesma hora/lugar)
    c2 = engine.connect()
    for r in rows:
        final = r.status == "entregue"
        pts = posicoes_viagem(r.numero, r.device_id, r.saiu_em, r.entregue_em or datetime.now(ZoneInfo("UTC")), final=final)
        g = metricas_gps(pts, (r.lat, r.lon)) or {}
        # clima na hora da saída, no local do cliente (ou da loja se o pedido não tem coordenadas)
        la, lo = (r.lat, r.lon) if r.lat is not None else (r.loja_lat, r.loja_lon)
        clima = None
        if la is not None:
            k = chave_clima(r.dia, r.hora_saida, la, lo)
            cc = climas.get(k)
            if cc is None and k not in climas:
                cc = climas.setdefault(k, c2.execute(text("SELECT temp, chuva_mm, codigo FROM clima_cache WHERE chave = :k"), {"k": k}).first())
            if cc: clima = {"temp": float(cc.temp) if cc.temp is not None else None, "chuva_mm": float(cc.chuva_mm or 0),
                            "rotulo": WMO.get(cc.codigo, ("—", "❔"))[0], "icone": WMO.get(cc.codigo, ("—", "❔"))[1]}
            else: pedir(("clima", r.dia, round(la, 1), round(lo, 1)))
        # rota esperada (OSRM) da loja até o cliente
        if r.rota_esperada_seg is None and r.lat is not None and r.loja_lat is not None:
            pedir(("osrm", r.numero, r.loja_lat, r.loja_lon, r.lat, r.lon))
        esp = r.rota_esperada_seg
        delta = (r.rota - esp) if esp is not None and r.rota is not None else None
        saida.append({
            "clima": clima, "chuva": (clima["chuva_mm"] > 0.1) if clima else None, "estacao": estacao(r.dia),
            "rota_esperada": esp, "delta_rota": delta, "delta_pct": round(100 * delta / esp) if delta is not None and esp else None,
            "numero": r.numero, "status": r.status, "cliente": r.cliente, "bairro": r.bairro, "entregador": r.entregador,
            "criado_em": r.criado_em, "dia_semana": DIAS[r.dow], "faixa": faixa_horario(r.hora),
            "loja": r.loja, "rota": r.rota, "porta": r.porta, "total": r.total, "em_rota": not final,
            "no_prazo": (r.total <= META_TOTAL) if final else None, "atrasado": r.total > META_TOTAL,
            # indicadores de GPS (None quando não há posições)
            "dist_km": g.get("dist_km"), "vel_media": g.get("vel_media"), "vel_max": g.get("vel_max"),
            "parado_min": g.get("parado_min"), "paradas": g.get("paradas"), "reta_km": g.get("reta_km"), "desvio": g.get("desvio"),
        })
    c2.close()
    return {"de": de, "ate": ate, "metas": {"loja": META_LOJA, "rota": META_ROTA, "porta": META_PORTA, "total": META_TOTAL}, "entregas": saida}

@app.get("/gerente/entregas/{numero}/rota")
def gerente_rota(numero: str, u=Depends(exige("gerente"))):
    """Pontos do GPS da viagem para desenhar no mapa, mais o pino do cliente."""
    with engine.connect() as c:
        r = c.execute(text("""SELECT p.numero, p.status, p.saiu_em, p.entregue_em, p.lat::float AS lat, p.lon::float AS lon, f.device_id,
                                     lj.lat::float AS loja_lat, lj.lon::float AS loja_lon
                              FROM pedidos p LEFT JOIN funcionarios f ON f.matricula = p.entregador LEFT JOIN lojas lj ON lj.id = p.loja_id
                              WHERE p.numero = :n"""), {"n": numero}).first()
    if not r: raise HTTPException(404, "Pedido não encontrado")
    pts = posicoes_viagem(r.numero, r.device_id, r.saiu_em, r.entregue_em or datetime.now(ZoneInfo("UTC")), final=r.status == "entregue") or []
    return {"cliente": {"lat": r.lat, "lon": r.lon} if r.lat is not None else None,
            "loja": {"lat": r.loja_lat, "lon": r.loja_lon} if r.loja_lat is not None else None,
            "pontos": [{"lat": p[0], "lon": p[1], "vel": p[2], "t": p[3]} for p in pts]}
