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
