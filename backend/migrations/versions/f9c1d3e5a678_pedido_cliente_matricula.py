"""dono do pedido (login de quem comprou)

Revision ID: f9c1d3e5a678
Revises: e8b0c2d4f567
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'f9c1d3e5a678'
down_revision: Union[str, Sequence[str], None] = 'e8b0c2d4f567'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # login de quem fez o pedido; cliente só vê/paga os pedidos com o próprio login
    op.add_column('pedidos', sa.Column('cliente_matricula', sa.String(10), nullable=True, index=True))
    # pedidos antigos foram todos feitos pelo Gamaliel (antes não havia login): ficam com o 9001
    op.execute("UPDATE pedidos SET cliente_matricula = '9001' WHERE cliente_matricula IS NULL")


def downgrade() -> None:
    op.drop_column('pedidos', 'cliente_matricula')
