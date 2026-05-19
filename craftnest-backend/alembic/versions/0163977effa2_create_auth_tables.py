"""create_auth_tables

Revision ID: 0163977effa2
Revises: 
Create Date: 2026-05-19 21:51:43.224477

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0163977effa2'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    connection = op.get_bind()
    
    # Safely query if the citext extension is already installed to avoid transaction aborts
    has_citext = False
    try:
        res = connection.execute(sa.text("SELECT 1 FROM pg_extension WHERE extname = 'citext';")).scalar()
        has_citext = bool(res)
    except Exception:
        has_citext = False

    # 2. Drop existing foreign key and users table (cascade) to ensure a clean slate for UUID transition
    op.execute("DROP TABLE IF EXISTS refresh_tokens CASCADE;")
    op.execute("DROP TABLE IF EXISTS users CASCADE;")

    # 3. Create the users table with UUID primary key and citext (or String fallback) email
    email_type = postgresql.CITEXT() if has_citext else sa.String()
    
    op.create_table('users',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('email', email_type, nullable=False),
        sa.Column('password_hash', sa.String(), nullable=False),
        sa.Column('full_name', sa.String(), nullable=True),
        sa.Column('role', sa.String(), server_default=sa.text("'buyer'"), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)

    # Truncate items to allow clean migration of integer owner_id to UUID
    op.execute("TRUNCATE TABLE items CASCADE;")

    # 4. Alter the items table's owner_id to use UUID and reference users.id
    op.execute("ALTER TABLE items ALTER COLUMN owner_id TYPE UUID USING owner_id::text::uuid;")
    op.create_foreign_key(
        'items_owner_id_fkey',
        'items',
        'users',
        ['owner_id'],
        ['id'],
        ondelete='CASCADE'
    )

    # 5. Create the refresh_tokens table
    op.create_table('refresh_tokens',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('token_hash', sa.String(), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('revoked', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('user_agent', sa.String(), nullable=True),
        sa.Column('ip_address', postgresql.INET(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_refresh_tokens_token_hash'), 'refresh_tokens', ['token_hash'], unique=True)
    op.create_index(op.f('ix_refresh_tokens_user_id'), 'refresh_tokens', ['user_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_refresh_tokens_user_id'), table_name='refresh_tokens')
    op.drop_index(op.f('ix_refresh_tokens_token_hash'), table_name='refresh_tokens')
    op.drop_table('refresh_tokens')

    op.drop_constraint('items_owner_id_fkey', 'items', type_='foreignkey')
    op.execute("ALTER TABLE items ALTER COLUMN owner_id TYPE INTEGER USING owner_id::text::integer;")

    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_table('users')
