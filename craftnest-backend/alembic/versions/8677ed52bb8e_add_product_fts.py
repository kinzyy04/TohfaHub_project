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
    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        # Create generated column search_vector combining title and description
        # Why: Enables high-performance full-text search indexing on PostgreSQL.
        op.execute(
            "ALTER TABLE products ADD COLUMN search_vector tsvector GENERATED ALWAYS AS ("
            "to_tsvector('english', coalesce(title, '') || ' ' || coalesce(description, ''))"
            ") STORED;"
        )
        # Create GIN index on the generated search_vector column
        # Why: Fast retrieval of products matching multiple search terms.
        op.create_index(
            'ix_products_search_vector',
            'products',
            ['search_vector'],
            postgresql_using='gin'
        )
    else:
        # SQLite fallback for test suite compatibility
        op.add_column('products', sa.Column('search_vector', sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        op.drop_index('ix_products_search_vector', table_name='products')
        op.drop_column('products', 'search_vector')
    else:
        op.drop_column('products', 'search_vector')
