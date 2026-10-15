"""estoque mínimo por produto

Revision ID: d7a9b1c3e456
Revises: c6f8a0b2d345
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'd7a9b1c3e456'
down_revision: Union[str, Sequence[str], None] = 'c6f8a0b2d345'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # abaixo disso o produto aparece como "baixo" na aba Estoque (padrão 5 unidades)
    op.add_column('produtos', sa.Column('estoque_minimo', sa.Integer(), nullable=True, server_default='5'))


def downgrade() -> None:
    op.drop_column('produtos', 'estoque_minimo')
