"""clima (cache), coordenadas da loja e rota esperada por pedido

Revision ID: a4d6e8f0b123
Revises: 9c3e5a7b2f61
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'a4d6e8f0b123'
down_revision: Union[str, Sequence[str], None] = '9c3e5a7b2f61'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Coordenadas da loja (ponto de partida das entregas)
    op.add_column('lojas', sa.Column('lat', sa.Numeric(9, 6), nullable=True))
    op.add_column('lojas', sa.Column('lon', sa.Numeric(9, 6), nullable=True))
    # Padrão: centro dos endereços já entregues; sem pedidos, centro de Belo Horizonte. Edite depois com o endereço real.
    op.execute("""UPDATE lojas SET
        lat = COALESCE((SELECT ROUND(AVG(lat), 6) FROM pedidos WHERE lat IS NOT NULL), -19.919100),
        lon = COALESCE((SELECT ROUND(AVG(lon), 6) FROM pedidos WHERE lon IS NOT NULL), -43.938600)
        WHERE lat IS NULL""")
    # Tempo de rota esperado (OSRM) guardado no pedido para não consultar de novo
    op.add_column('pedidos', sa.Column('rota_esperada_seg', sa.Integer(), nullable=True))
    # Cache do clima por hora e local arredondado (chave: AAAA-MM-DD|HH|lat|lon)
    op.create_table('clima_cache',
        sa.Column('chave', sa.String(40), primary_key=True),
        sa.Column('temp', sa.Numeric(4, 1)),
        sa.Column('chuva_mm', sa.Numeric(5, 1)),
        sa.Column('codigo', sa.SmallInteger()),
        sa.Column('criado_em', sa.DateTime(timezone=True), server_default=sa.func.now()))


def downgrade() -> None:
    op.drop_table('clima_cache')
    op.drop_column('pedidos', 'rota_esperada_seg')
    op.drop_column('lojas', 'lon')
    op.drop_column('lojas', 'lat')
