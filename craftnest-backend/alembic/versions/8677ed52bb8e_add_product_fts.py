"""add_product_fts

Revision ID: 8677ed52bb8e
Revises: a8bc3c7fdbd2
Create Date: 2026-05-24 11:58:03.885136

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8677ed52bb8e'
down_revision: Union[str, Sequence[str], None] = 'a8bc3c7fdbd2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
