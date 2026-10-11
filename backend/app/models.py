from datetime import date
from decimal import Decimal
from sqlalchemy import String, Integer, SmallInteger, Numeric, Boolean, Date, ForeignKey, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base

class Loja(Base):
    __tablename__ = "lojas"
    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(100))
    cidade: Mapped[str] = mapped_column(String(100))

class Produto(Base):
    __tablename__ = "produtos"
    sku: Mapped[str] = mapped_column(String(30), primary_key=True)
    nome: Mapped[str] = mapped_column(String(150))
    categoria: Mapped[str] = mapped_column(String(50))
    corredor: Mapped[int] = mapped_column(SmallInteger)
    preco: Mapped[Decimal] = mapped_column(Numeric(10, 2), CheckConstraint("preco >= 0"))
    perecivel: Mapped[bool] = mapped_column(Boolean, default=False)

class Lote(Base):
    __tablename__ = "lotes"
    id: Mapped[int] = mapped_column(primary_key=True)
    loja_id: Mapped[int] = mapped_column(ForeignKey("lojas.id"))
    sku: Mapped[str] = mapped_column(ForeignKey("produtos.sku"))
    validade: Mapped[date | None] = mapped_column(Date)
    quantidade: Mapped[int] = mapped_column(Integer, CheckConstraint("quantidade >= 0"))
    reservado: Mapped[int] = mapped_column(Integer, CheckConstraint("reservado >= 0"), default=0)

from datetime import datetime
from sqlalchemy import DateTime, Sequence, func

class Pedido(Base):
    __tablename__ = "pedidos"
    id: Mapped[int] = mapped_column(primary_key=True)
    numero: Mapped[str] = mapped_column(String(20), unique=True)
    loja_id: Mapped[int] = mapped_column(ForeignKey("lojas.id"))
    cliente: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(30), default="aguardando_pagamento")
    total: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class ItemPedido(Base):
    __tablename__ = "itens_pedido"
    id: Mapped[int] = mapped_column(primary_key=True)
    pedido_id: Mapped[int] = mapped_column(ForeignKey("pedidos.id"))
    sku: Mapped[str] = mapped_column(ForeignKey("produtos.sku"))
    quantidade: Mapped[int] = mapped_column(Integer, CheckConstraint("quantidade > 0"))
    preco_unitario: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    lote_id: Mapped[int] = mapped_column(ForeignKey("lotes.id"))
