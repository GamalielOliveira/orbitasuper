"""clientes (login da loja + endereço + perfil de simulação)

Revision ID: b2c4d6e8f0a1
Revises: a1b3c5d7e9f0
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'b2c4d6e8f0a1'
down_revision: Union[str, Sequence[str], None] = 'a1b3c5d7e9f0'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Cliente separado de funcionário: outro cadastro, outros dados (endereço), mesmo login (matrícula + senha).
    # A matrícula é a mesma que vai em pedidos.cliente_matricula.
    op.create_table('clientes',
        sa.Column('matricula', sa.String(10), primary_key=True),          # 5xxx
        sa.Column('nome', sa.String(100), nullable=False),
        sa.Column('pin_hash', sa.String(100), nullable=False),
        sa.Column('ativo', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('simulado', sa.Boolean(), server_default='false', nullable=False),
        # endereço padrão (mesmos campos do pedido)
        sa.Column('cep', sa.String(9)),
        sa.Column('rua', sa.String(150), nullable=False),
        sa.Column('numero_end', sa.String(10), nullable=False),
        sa.Column('complemento', sa.String(60)),
        sa.Column('bairro', sa.String(80), nullable=False),
        sa.Column('cidade', sa.String(80), nullable=False, server_default='Belo Horizonte'),
        sa.Column('uf', sa.String(2), nullable=False, server_default='MG'),
        sa.Column('lat', sa.Float(), nullable=False),
        sa.Column('lon', sa.Float(), nullable=False),
        sa.Column('dist_loja_km', sa.Float()),                             # por rua (OSRM)
        # {"pedidos_semana": 0.8, "categorias": [...], "ticket_medio": 95.0, "faixas": ["noite"]}
        sa.Column('perfil', postgresql.JSONB()),
        sa.Column('criado_em', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))


def downgrade() -> None:
    op.drop_table('clientes')
