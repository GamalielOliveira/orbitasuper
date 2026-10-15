"""perfil de simulação dos funcionários

Revision ID: a1b3c5d7e9f0
Revises: f9c1d3e5a678
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'a1b3c5d7e9f0'
down_revision: Union[str, Sequence[str], None] = 'f9c1d3e5a678'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # simulado = o simulador pode agir por esta pessoa (gente real fica false)
    op.add_column('funcionarios', sa.Column('simulado', sa.Boolean(), server_default='false', nullable=False))
    # perfil: {"velocidade": 1.1, "erro": 0.05, "atraso": 0.1, "turno": "manha"}
    op.add_column('funcionarios', sa.Column('perfil', postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column('funcionarios', 'perfil')
    op.drop_column('funcionarios', 'simulado')
