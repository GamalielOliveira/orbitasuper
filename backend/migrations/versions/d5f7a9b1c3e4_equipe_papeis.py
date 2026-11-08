"""papéis da equipe interna e turno opcional

Revision ID: d5f7a9b1c3e4
Revises: c3d5e7f9a0b1

Não insere pessoa e não altera matrícula, PIN nem pedido.
turno fica vazio em quem já existe. A restrição de função só aceita
os papéis já usados (gerente, separador, entregador) e os três novos.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "d5f7a9b1c3e4"
down_revision: Union[str, Sequence[str], None] = "c3d5e7f9a0b1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("funcionarios", sa.Column("turno", sa.String(length=10), nullable=True))
    op.create_check_constraint(
        "ck_funcionario_turno", "funcionarios", "turno IS NULL OR turno IN ('T1', 'T2', 'noite')")
    op.create_check_constraint(
        "ck_funcionario_funcao", "funcionarios",
        "funcao IN ('gerente', 'lider', 'separador', 'embalador', 'repositor', 'entregador')")


def downgrade() -> None:
    op.drop_constraint("ck_funcionario_funcao", "funcionarios", type_="check")
    op.drop_constraint("ck_funcionario_turno", "funcionarios", type_="check")
    op.drop_column("funcionarios", "turno")
