"""add cron_jobs table

Revision ID: 8ce57dd3341d
Revises: 05f41c2650fe
Create Date: 2026-02-28 11:02:34.157396
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '8ce57dd3341d'
down_revision: Union[str, None] = '05f41c2650fe'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade database schema."""
    op.create_table('cron_jobs',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('cron_expression', sa.String(length=100), nullable=False),
    sa.Column('prompt', sa.Text(), nullable=False),
    sa.Column('session_name', sa.String(length=255), nullable=False),
    sa.Column('isolated', sa.Boolean(), nullable=False),
    sa.Column('enabled', sa.Boolean(), nullable=False),
    sa.Column('timezone', sa.String(length=50), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('last_run_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name')
    )


def downgrade() -> None:
    """Downgrade database schema."""
    op.drop_table('cron_jobs')
