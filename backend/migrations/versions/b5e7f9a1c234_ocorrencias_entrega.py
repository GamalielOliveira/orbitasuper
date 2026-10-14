"""ocorrências informadas pelo entregador

Revision ID: b5e7f9a1c234
Revises: a4d6e8f0b123
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'b5e7f9a1c234'
down_revision: Union[str, Sequence[str], None] = 'a4d6e8f0b123'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('ocorrencias_entrega',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('pedido_id', sa.Integer(), sa.ForeignKey('pedidos.id'), nullable=False, index=True),
        sa.Column('funcionario_id', sa.String(10), sa.ForeignKey('funcionarios.matricula'), nullable=False),
        sa.Column('tipo', sa.String(20), nullable=False),   # transito, endereco, cliente, chuva, moto, outro
        sa.Column('texto', sa.String(200)),
        sa.Column('criado_em', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))


def downgrade() -> None:
    op.drop_table('ocorrencias_entrega')
