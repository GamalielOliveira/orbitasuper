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
        SELECT p.sku, p.nome, p.categoria, p.preco,
               COALESCE(SUM(l.quantidade - l.reservado), 0) AS estoque,
               MIN(l.validade) AS proxima_validade
        FROM produtos p LEFT JOIN lotes l ON l.sku = p.sku
        GROUP BY p.sku ORDER BY p.categoria, p.nome
    """)
    with engine.connect() as c:
        return [dict(r._mapping) for r in c.execute(sql)]
