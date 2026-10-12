"""chegada do entregador na porta

Revision ID: 9c3e5a7b2f61
Revises: 8b2d4f6a1c50
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '9c3e5a7b2f61'
down_revision: Union[str, Sequence[str], None] = '8b2d4f6a1c50'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('pedidos', sa.Column('chegou_em', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('pedidos', 'chegou_em')
