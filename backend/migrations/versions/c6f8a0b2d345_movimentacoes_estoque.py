"""histórico de estoque + limpeza de reservas presas

Revision ID: c6f8a0b2d345
Revises: b5e7f9a1c234
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'c6f8a0b2d345'
down_revision: Union[str, Sequence[str], None] = 'b5e7f9a1c234'
branch_labels = None
depends_on = None

# Pedidos que ainda "seguram" estoque (todos menos os encerrados)
FECHADOS = "('entregue', 'expirado', 'pagamento_recusado', 'cancelado')"


def upgrade() -> None:
    op.create_table('movimentacoes_estoque',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('lote_id', sa.Integer(), sa.ForeignKey('lotes.id'), nullable=False, index=True),
        sa.Column('sku', sa.String(40), nullable=False, index=True),
        sa.Column('loja_id', sa.Integer(), nullable=False),
        sa.Column('tipo', sa.String(12), nullable=False),        # entrada, reserva, liberacao, saida, perda, ajuste
        sa.Column('quantidade', sa.Integer(), nullable=False),   # com sinal: + entra, - sai
        sa.Column('campo', sa.String(12), nullable=False),       # 'quantidade' (físico) ou 'reservado'
        sa.Column('saldo_quantidade', sa.Integer(), nullable=False),  # saldos DEPOIS da mexida
        sa.Column('saldo_reservado', sa.Integer(), nullable=False),
        sa.Column('pedido_id', sa.Integer(), sa.ForeignKey('pedidos.id'), nullable=True, index=True),
        sa.Column('funcionario', sa.String(10), nullable=True),
        sa.Column('motivo', sa.Text(), nullable=True),
        sa.Column('criado_em', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False, index=True),
        sa.CheckConstraint("tipo IN ('entrada','reserva','liberacao','saida','perda','ajuste')", name='ck_mov_tipo'),
        sa.CheckConstraint("campo IN ('quantidade','reservado')", name='ck_mov_campo'))

    # 1) Foto inicial: uma 'entrada' por lote com o saldo físico atual
    op.execute("""INSERT INTO movimentacoes_estoque (lote_id, sku, loja_id, tipo, quantidade, campo, saldo_quantidade, saldo_reservado, motivo)
                  SELECT id, sku, loja_id, 'entrada', quantidade, 'quantidade', quantidade, reservado, 'saldo inicial' FROM lotes""")

    # 2) Reservas presas: reservado correto = soma dos itens (não faltando) de pedidos em aberto.
    #    Registra a diferença como 'ajuste' e só depois corrige o lote.
    certo = f"""SELECT l.id, l.reservado AS atual, COALESCE(SUM(i.quantidade), 0) AS correto
                FROM lotes l LEFT JOIN itens_pedido i ON i.lote_id = l.id AND i.status <> 'faltando'
                     AND i.pedido_id IN (SELECT id FROM pedidos WHERE status NOT IN {FECHADOS})
                GROUP BY l.id"""
    op.execute(f"""INSERT INTO movimentacoes_estoque (lote_id, sku, loja_id, tipo, quantidade, campo, saldo_quantidade, saldo_reservado, motivo)
                   SELECT l.id, l.sku, l.loja_id, 'ajuste', c.correto - c.atual, 'reservado', l.quantidade, c.correto, 'limpeza de reservas presas'
                   FROM ({certo}) c JOIN lotes l ON l.id = c.id WHERE c.correto <> c.atual""")
    op.execute(f"UPDATE lotes l SET reservado = c.correto FROM ({certo}) c WHERE c.id = l.id AND c.correto <> c.atual")


def downgrade() -> None:
    # Não desfaz a limpeza das reservas (eram valores errados); só remove o histórico.
    op.drop_table('movimentacoes_estoque')
