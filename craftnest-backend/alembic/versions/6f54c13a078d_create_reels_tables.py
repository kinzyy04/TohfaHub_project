"""create_reels_tables

Revision ID: 6f54c13a078d
Revises: 484828734e4e
Create Date: 2026-05-21 15:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '6f54c13a078d'
down_revision: Union[str, Sequence[str], None] = '484828734e4e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # 1. Create reels table
    op.create_table('reels',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('video_url', sa.String(), nullable=False),
        sa.Column('caption', sa.String(length=500), nullable=False),
        sa.Column('product_id', sa.UUID(), nullable=True),
        sa.Column('likes_count', sa.Integer(), server_default=sa.text('0'), nullable=False),
        sa.Column('saves_count', sa.Integer(), server_default=sa.text('0'), nullable=False),
        sa.Column('views_count', sa.Integer(), server_default=sa.text('0'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='SET NULL')
    )
    op.create_index(op.f('ix_reels_product_id'), 'reels', ['product_id'], unique=False)

    # 2. Create reel_likes table
    op.create_table('reel_likes',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('reel_id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['reel_id'], ['reels.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE')
    )
    op.create_index(op.f('ix_reel_likes_reel_id'), 'reel_likes', ['reel_id'], unique=False)
    op.create_index(op.f('ix_reel_likes_user_id'), 'reel_likes', ['user_id'], unique=False)

    # 3. Create reel_saves table
    op.create_table('reel_saves',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('reel_id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['reel_id'], ['reels.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE')
    )
    op.create_index(op.f('ix_reel_saves_reel_id'), 'reel_saves', ['reel_id'], unique=False)
    op.create_index(op.f('ix_reel_saves_user_id'), 'reel_saves', ['user_id'], unique=False)

    # 4. Create reel_comments table
    op.create_table('reel_comments',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('reel_id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=True),
        sa.Column('comment_text', sa.String(length=1000), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['reel_id'], ['reels.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE')
    )
    op.create_index(op.f('ix_reel_comments_reel_id'), 'reel_comments', ['reel_id'], unique=False)
    op.create_index(op.f('ix_reel_comments_user_id'), 'reel_comments', ['user_id'], unique=False)

def downgrade() -> None:
    op.drop_index(op.f('ix_reel_comments_user_id'), table_name='reel_comments')
    op.drop_index(op.f('ix_reel_comments_reel_id'), table_name='reel_comments')
    op.drop_table('reel_comments')
    
    op.drop_index(op.f('ix_reel_saves_user_id'), table_name='reel_saves')
    op.drop_index(op.f('ix_reel_saves_reel_id'), table_name='reel_saves')
    op.drop_table('reel_saves')

    op.drop_index(op.f('ix_reel_likes_user_id'), table_name='reel_likes')
    op.drop_index(op.f('ix_reel_likes_reel_id'), table_name='reel_likes')
    op.drop_table('reel_likes')

    op.drop_index(op.f('ix_reels_product_id'), table_name='reels')
    op.drop_table('reels')
