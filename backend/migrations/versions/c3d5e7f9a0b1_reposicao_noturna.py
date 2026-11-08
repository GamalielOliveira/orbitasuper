"""vínculo da reposição noturna com cada saída de origem

Revision ID: c3d5e7f9a0b1
Revises: b2c4d6e8f0a1

Só cria tabelas novas. Não altera lotes, movimentacoes_estoque, saldos nem histórico.
O downgrade apaga só estas tabelas; não desfaz entrada de mercadoria já gravada.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "c3d5e7f9a0b1"
down_revision: Union[str, Sequence[str], None] = "b2c4d6e8f0a1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "reposicoes_noturnas",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("loja_id", sa.Integer(), sa.ForeignKey("lojas.id"), nullable=False),
        sa.Column("corte", sa.Date(), nullable=False),
        sa.Column("referencia", sa.Date(), nullable=False),
        sa.Column("ator", sa.String(10), nullable=False),
        sa.Column("produtos", sa.Integer(), nullable=False),
        sa.Column("unidades", sa.Integer(), nullable=False),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("ator = 'AUTO'", name="ck_reposicao_ator"),
        sa.CheckConstraint("produtos > 0 AND unidades > 0", name="ck_reposicao_positiva"),
        sa.CheckConstraint("referencia > corte", name="ck_reposicao_janela"),
    )
    op.create_table(
        "reposicao_noturna_origem",
        sa.Column("movimentacao_id", sa.Integer(), sa.ForeignKey("movimentacoes_estoque.id"), primary_key=True),
        sa.Column("reposicao_id", sa.Integer(), sa.ForeignKey("reposicoes_noturnas.id"), nullable=False),
        sa.Column("lote_id", sa.Integer(), sa.ForeignKey("lotes.id"), nullable=False),
        sa.Column("movimentacao_entrada_id", sa.Integer(), sa.ForeignKey("movimentacoes_estoque.id"), nullable=False),
        sa.Column("sku", sa.String(40), nullable=False),
        sa.Column("loja_id", sa.Integer(), nullable=False),
        sa.Column("dia", sa.Date(), nullable=False),
        sa.Column("unidades", sa.Integer(), nullable=False),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("unidades > 0", name="ck_reposicao_origem_unidades"),
    )
    op.create_index("ix_reposicao_origem_reposicao", "reposicao_noturna_origem", ["reposicao_id"])
    op.create_index("ix_reposicao_origem_loja_dia", "reposicao_noturna_origem", ["loja_id", "dia"])


def downgrade() -> None:
    op.drop_index("ix_reposicao_origem_loja_dia", table_name="reposicao_noturna_origem")
    op.drop_index("ix_reposicao_origem_reposicao", table_name="reposicao_noturna_origem")
    op.drop_table("reposicao_noturna_origem")
    op.drop_table("reposicoes_noturnas")
