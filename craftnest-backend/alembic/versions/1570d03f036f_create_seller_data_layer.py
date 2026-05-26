"""create_seller_data_layer

Revision ID: 1570d03f036f
Revises: b9f1e2c3d4a5
Create Date: 2026-05-26 14:54:48.699808

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import app.core.database

# revision identifiers, used by Alembic.
revision: str = '1570d03f036f'
down_revision: Union[str, Sequence[str], None] = 'b9f1e2c3d4a5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Drop existing seller_profiles table
    op.drop_table('seller_profiles')

    # 2. Create new seller_profiles table
    op.create_table(
        'seller_profiles',
        sa.Column('id', app.core.database.GUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('user_id', app.core.database.GUID(), nullable=False),
        sa.Column('store_name', sa.String(), nullable=False),
        sa.Column('store_handle', sa.String(), nullable=False),
        sa.Column('bio', sa.Text(), nullable=True),
        sa.Column('location', sa.String(), nullable=True),
        sa.Column('website_url', sa.String(), nullable=True),
        sa.Column('artisan_story', sa.Text(), nullable=True),
        sa.Column('avatar_url', sa.String(), nullable=True),
        sa.Column('is_accepting_orders', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('is_online', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('shipping_days', sa.Integer(), server_default=sa.text('5'), nullable=False),
        sa.Column('payout_method', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id'),
        sa.UniqueConstraint('store_name'),
        sa.UniqueConstraint('store_handle')
    )

    # 3. Create seller_onboarding_status table
    op.create_table(
        'seller_onboarding_status',
        sa.Column('id', app.core.database.GUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('seller_id', app.core.database.GUID(), nullable=False),
        sa.Column('step_key', sa.String(), nullable=False),
        sa.Column('is_complete', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['seller_id'], ['seller_profiles.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # 4. Create seller_payout_details table
    op.create_table(
        'seller_payout_details',
        sa.Column('id', app.core.database.GUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('seller_id', app.core.database.GUID(), nullable=False),
        sa.Column('masked_account', sa.String(), nullable=True),
        sa.Column('payout_method', sa.String(), nullable=False),
        sa.Column('pending_payout_amount', sa.Numeric(precision=10, scale=2), server_default=sa.text('0.00'), nullable=False),
        sa.Column('payout_schedule', sa.String(), server_default=sa.text("'Every Monday 10 AM'"), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['seller_id'], ['seller_profiles.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('seller_id')
    )


def downgrade() -> None:
    # 1. Drop seller_payout_details
    op.drop_table('seller_payout_details')

    # 2. Drop seller_onboarding_status
    op.drop_table('seller_onboarding_status')

    # 3. Drop new seller_profiles
    op.drop_table('seller_profiles')

    # 4. Recreate old seller_profiles
    op.create_table(
        'seller_profiles',
        sa.Column('user_id', app.core.database.GUID(), nullable=False),
        sa.Column('shop_name', sa.String(length=80), nullable=True),
        sa.Column('bio', sa.String(length=500), nullable=True),
        sa.Column('shipping_days', sa.Integer(), server_default=sa.text('5'), nullable=False),
        sa.Column('instagram_handle', sa.String(length=30), nullable=True),
        sa.Column('payout_method', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('user_id')
    )
