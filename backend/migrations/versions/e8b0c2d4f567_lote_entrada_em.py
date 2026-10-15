"""data de entrada do lote

Revision ID: e8b0c2d4f567
Revises: d7a9b1c3e456
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'e8b0c2d4f567'
down_revision: Union[str, Sequence[str], None] = 'd7a9b1c3e456'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # dia em que a mercadoria chegou; lotes antigos ficam vazios (não sabemos a data real)
    op.add_column('lotes', sa.Column('entrada_em', sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column('lotes', 'entrada_em')
