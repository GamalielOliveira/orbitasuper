"""endereco do pedido e sequencia do numero

Revision ID: 8b2d4f6a1c50
Revises: 7a1c3e9b2d40
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '8b2d4f6a1c50'
down_revision: Union[str, Sequence[str], None] = '7a1c3e9b2d40'
branch_labels = None
depends_on = None

COLS = [("cep", sa.String(9)), ("rua", sa.String(150)), ("numero_end", sa.String(20)), ("complemento", sa.String(80)),
        ("bairro", sa.String(80)), ("cidade", sa.String(80)), ("uf", sa.String(2)), ("referencia", sa.String(150)),
        ("lat", sa.Numeric(9, 6)), ("lon", sa.Numeric(9, 6))]


def upgrade() -> None:
    for nome, tipo in COLS:
        op.add_column('pedidos', sa.Column(nome, tipo, nullable=True))
    op.execute("CREATE SEQUENCE IF NOT EXISTS pedido_numero_seq")
    op.execute("""SELECT setval('pedido_numero_seq',
                  GREATEST(COALESCE((SELECT MAX(NULLIF(regexp_replace(numero, '\\D', '', 'g'), '')::int) FROM pedidos), 0), 1),
                  (SELECT COUNT(*) > 0 FROM pedidos))""")


def downgrade() -> None:
    op.execute("DROP SEQUENCE IF EXISTS pedido_numero_seq")
    for nome, _ in reversed(COLS):
        op.drop_column('pedidos', nome)
