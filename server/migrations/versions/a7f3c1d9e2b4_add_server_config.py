"""add server config

Revision ID: a7f3c1d9e2b4
Revises: 6ac6928bb656
Create Date: 2026-10-11 14:30:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a7f3c1d9e2b4'
down_revision: Union[str, None] = '6ac6928bb656'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'server_config',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('signing_key_pem', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('server_config')
