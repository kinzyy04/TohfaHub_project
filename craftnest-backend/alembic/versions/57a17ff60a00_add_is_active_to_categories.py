"""add_is_active_to_categories

Revision ID: 57a17ff60a00
Revises: a1b2c3d4e5f6
Create Date: 2026-05-24 11:24:05.256642

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '57a17ff60a00'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('categories', sa.Column('is_active', sa.Boolean(), server_default=sa.text('(true)'), nullable=False))


def downgrade() -> None:
    op.drop_column('categories', 'is_active')
