"""add_performance_indexes

Revision ID: a8bc3c7fdbd2
Revises: 57a17ff60a00
Create Date: 2026-05-24 11:36:30.175519

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a8bc3c7fdbd2'
down_revision: Union[str, Sequence[str], None] = '57a17ff60a00'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Composite index for reels feed query: filters by is_active, sorts by created_at DESC, id DESC.
    # Why: Eliminates sequential scan on reels table for the reels feed keyset pagination.
    op.create_index(
        'ix_reels_active_created_at',
        'reels',
        ['is_active', sa.text('created_at DESC'), sa.text('id DESC')]
    )

    # 2. Composite index for products home browse query: filters by is_active, is_sponsored, sorts by created_at DESC, id DESC.
    # Why: Eliminates sequential scan on products table for the home browse page queries.
    op.create_index(
        'ix_products_active_sponsored_created_at',
        'products',
        ['is_active', 'is_sponsored', sa.text('created_at DESC'), sa.text('id DESC')]
    )

    # 3. Composite index for admin orders: filters by status, sorts by created_at DESC.
    # Why: Eliminates sequential scan on orders table when filtering by status on order listings.
    op.create_index(
        'ix_orders_status_created_at',
        'orders',
        ['status', sa.text('created_at DESC')]
    )

    # 4. Index on orders.created_at DESC.
    # Why: Eliminates sort step and speeds up listing seller orders when ordering by created_at DESC.
    op.create_index(
        'ix_orders_created_at',
        'orders',
        [sa.text('created_at DESC')]
    )


def downgrade() -> None:
    op.drop_index('ix_orders_created_at', table_name='orders')
    op.drop_index('ix_orders_status_created_at', table_name='orders')
    op.drop_index('ix_products_active_sponsored_created_at', table_name='products')
    op.drop_index('ix_reels_active_created_at', table_name='reels')
