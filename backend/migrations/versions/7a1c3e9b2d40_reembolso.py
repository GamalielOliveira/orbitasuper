"""reembolso no pedido

Revision ID: 7a1c3e9b2d40
Revises: 6f7afe698df2
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '7a1c3e9b2d40'
down_revision: Union[str, Sequence[str], None] = '6f7afe698df2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('pedidos', sa.Column('reembolso', sa.Numeric(10, 2), nullable=False, server_default='0'))


def downgrade() -> None:
    op.drop_column('pedidos', 'reembolso')
