"""add_skills_to_persona

Revision ID: 60c76b4cd923
Revises: 8ce57dd3341d
Create Date: 2026-02-28 11:51:58.107556
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '60c76b4cd923'
down_revision: Union[str, None] = '8ce57dd3341d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade database schema."""
    with op.batch_alter_table('personas', schema=None) as batch_op:
        batch_op.add_column(sa.Column('skills', sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade database schema."""
    with op.batch_alter_table('personas', schema=None) as batch_op:
        batch_op.drop_column('skills')
