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
    subcategoria: Mapped[str | None] = mapped_column(String(80))
    conservacao: Mapped[str | None] = mapped_column(String(20))  # Congelado, Resfriado ou Ambiente
    peso: Mapped[str | None] = mapped_column(String(20))
    imagem_url: Mapped[str | None] = mapped_column(String(300))
    preco_original: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))  # preço antes do desconto

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
    separador: Mapped[str | None] = mapped_column(ForeignKey("funcionarios.matricula", use_alter=True))
    separacao_inicio: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    separacao_fim: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    entregador: Mapped[str | None] = mapped_column(ForeignKey("funcionarios.matricula", use_alter=True))
    saiu_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    entregue_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    endereco: Mapped[str | None] = mapped_column(String(200))

class ItemPedido(Base):
    __tablename__ = "itens_pedido"
    id: Mapped[int] = mapped_column(primary_key=True)
    pedido_id: Mapped[int] = mapped_column(ForeignKey("pedidos.id"))
    sku: Mapped[str] = mapped_column(ForeignKey("produtos.sku"))
    quantidade: Mapped[int] = mapped_column(Integer, CheckConstraint("quantidade > 0"))
    preco_unitario: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    lote_id: Mapped[int] = mapped_column(ForeignKey("lotes.id"))
    status: Mapped[str] = mapped_column(String(20), default="pendente", server_default="pendente")  # pendente, separado, faltando, substituido
    substituto_sku: Mapped[str | None] = mapped_column(ForeignKey("produtos.sku"))

from sqlalchemy.dialects.postgresql import JSONB

class Pagamento(Base):
    __tablename__ = "pagamentos"
    id: Mapped[int] = mapped_column(primary_key=True)
    pedido_id: Mapped[int] = mapped_column(ForeignKey("pedidos.id"), unique=True)
    metodo: Mapped[str] = mapped_column(String(20))            # pix ou cartao
    valor: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    status: Mapped[str] = mapped_column(String(20), default="pendente")  # pendente, aprovado, recusado, estornado
    gateway_id: Mapped[str] = mapped_column(String(60), unique=True)     # id da transação no gateway
    pix_copia_cola: Mapped[str | None] = mapped_column(String(300))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    atualizado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

class EventoPagamento(Base):
    __tablename__ = "eventos_pagamento"
    id: Mapped[int] = mapped_column(primary_key=True)
    pagamento_id: Mapped[int] = mapped_column(ForeignKey("pagamentos.id"))
    tipo: Mapped[str] = mapped_column(String(40))              # ex.: payment.approved
    payload: Mapped[dict] = mapped_column(JSONB)               # o aviso completo, como chegou
    recebido_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class Funcionario(Base):
    __tablename__ = "funcionarios"
    matricula: Mapped[str] = mapped_column(String(10), primary_key=True)
    nome: Mapped[str] = mapped_column(String(100))
    funcao: Mapped[str] = mapped_column(String(20))       # separador, entregador ou gerente
    pin_hash: Mapped[str] = mapped_column(String(100))    # PIN criptografado com bcrypt
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    disponivel: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    device_id: Mapped[str | None] = mapped_column(String(40))  # identificador no Traccar
