"""add reviews table and product rating columns

Revision ID: a1b2c3d4e5f6
Revises: 3580e80a656e
Create Date: 2026-05-23 10:57:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import app.core.database


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '3580e80a656e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 1. Add avg_rating and review_count to products
    op.add_column('products', sa.Column(
        'avg_rating',
        sa.Numeric(precision=3, scale=2),
        nullable=True,
    ))
    op.add_column('products', sa.Column(
        'review_count',
        sa.Integer(),
        nullable=False,
        server_default=sa.text('0'),
    ))

    # 2. Create reviews table
    op.create_table(
        'reviews',
        sa.Column(
            'id',
            app.core.database.GUID(),
            server_default=sa.text('(gen_random_uuid())'),
            nullable=False,
        ),
        sa.Column('product_id', app.core.database.GUID(), nullable=False),
        sa.Column('buyer_id',   app.core.database.GUID(), nullable=False),
        sa.Column('order_id',   app.core.database.GUID(), nullable=False),
        sa.Column('rating',     sa.Integer(), nullable=False),
        sa.Column('body',       sa.Text(), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('(CURRENT_TIMESTAMP)'),
            nullable=False,
        ),
        sa.CheckConstraint('rating IN (1,2,3,4,5)', name='ck_review_rating'),
        sa.ForeignKeyConstraint(['buyer_id'],   ['users.id'],    ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['order_id'],   ['orders.id'],   ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('product_id', 'buyer_id', name='uq_review_product_buyer'),
    )
    op.create_index(op.f('ix_reviews_buyer_id'),   'reviews', ['buyer_id'],   unique=False)
    op.create_index(op.f('ix_reviews_order_id'),   'reviews', ['order_id'],   unique=False)
    op.create_index(op.f('ix_reviews_product_id'), 'reviews', ['product_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_reviews_product_id'), table_name='reviews')
    op.drop_index(op.f('ix_reviews_order_id'),   table_name='reviews')
    op.drop_index(op.f('ix_reviews_buyer_id'),   table_name='reviews')
    op.drop_table('reviews')
    op.drop_column('products', 'review_count')
    op.drop_column('products', 'avg_rating')
