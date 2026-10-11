from datetime import date, timedelta
from sqlalchemy.orm import Session
from app.db import engine
from app.models import Loja, Produto, Lote

hoje = date.today()
produtos = [
    ("LEITE-1L", "Leite Integral 1L", "Laticínios", 1, 5.49, True),
    ("IOGURTE-NAT", "Iogurte Natural 170g", "Laticínios", 1, 3.29, True),
    ("PAO-FORMA", "Pão de Forma 500g", "Padaria", 2, 8.90, True),
    ("BANANA-KG", "Banana Prata kg", "Hortifruti", 3, 6.99, True),
    ("TOMATE-KG", "Tomate kg", "Hortifruti", 3, 7.49, True),
    ("ARROZ-5KG", "Arroz Branco 5kg", "Mercearia", 4, 27.90, False),
    ("FEIJAO-1KG", "Feijão Carioca 1kg", "Mercearia", 4, 8.49, False),
    ("CAFE-500G", "Café Torrado 500g", "Mercearia", 4, 18.90, False),
    ("AGUA-1-5L", "Água Mineral 1,5L", "Bebidas", 5, 2.99, False),
    ("REFRI-2L", "Refrigerante 2L", "Bebidas", 5, 9.49, False),
]

with Session(engine) as s:
    if s.query(Loja).count():
        print("Já tem dados, nada feito."); raise SystemExit
    loja = Loja(nome="Dark Store Centro", cidade="Belo Horizonte")
    s.add(loja); s.flush()
    for sku, nome, cat, corr, preco, perec in produtos:
        s.add(Produto(sku=sku, nome=nome, categoria=cat, corredor=corr, preco=preco, perecivel=perec))
        s.flush()
        if perec:
            s.add(Lote(loja_id=loja.id, sku=sku, validade=hoje + timedelta(days=2), quantidade=5))
            s.add(Lote(loja_id=loja.id, sku=sku, validade=hoje + timedelta(days=10), quantidade=15))
        else:
            s.add(Lote(loja_id=loja.id, sku=sku, validade=None, quantidade=30))
    s.commit()
    print("Seed ok: 1 loja, 10 produtos, lotes criados.")
