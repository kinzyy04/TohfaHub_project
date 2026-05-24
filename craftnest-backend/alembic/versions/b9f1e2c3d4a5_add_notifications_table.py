"""add_notifications_table

Revision ID: b9f1e2c3d4a5
Revises: 8677ed52bb8e
Create Date: 2026-05-24 12:00:00.000000

Creates the `notifications` table for the lightweight in-app notification system.
Each notification is scoped to a user (FK→users) and carries a type, title, body,
is_read flag, and an optional related_id (order or product UUID) for deep-linking.

Why this approach:
  - Notifications are created atomically inside the same DB savepoint as the event
    that triggers them (order creation, status changes, review creation). If the
    parent transaction rolls back, the notification is rolled back too.
  - ix_notifications_user_id speeds up the per-user listing query.
  - ix_notifications_user_id_is_read speeds up the unread_count query.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b9f1e2c3d4a5'
down_revision: Union[str, Sequence[str], None] = '8677ed52bb8e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the notifications table."""
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == 'postgresql':
        op.create_table(
            'notifications',
            sa.Column('id', sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True,
                      server_default=sa.text('gen_random_uuid()')),
            sa.Column('user_id', sa.dialects.postgresql.UUID(as_uuid=True),
                      sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
            sa.Column('type', sa.Text(), nullable=False),
            sa.Column('title', sa.String(80), nullable=False),
            sa.Column('body', sa.String(200), nullable=False),
            sa.Column('is_read', sa.Boolean(), nullable=False, server_default=sa.text('false')),
            sa.Column('related_id', sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
        )
    else:
        # SQLite-compatible fallback (UUIDs stored as CHAR(36))
        op.create_table(
            'notifications',
            sa.Column('id', sa.CHAR(36), primary_key=True),
            sa.Column('user_id', sa.CHAR(36), sa.ForeignKey('users.id', ondelete='CASCADE'),
                      nullable=False),
            sa.Column('type', sa.Text(), nullable=False),
            sa.Column('title', sa.String(80), nullable=False),
            sa.Column('body', sa.String(200), nullable=False),
            sa.Column('is_read', sa.Boolean(), nullable=False, server_default=sa.text('0')),
            sa.Column('related_id', sa.CHAR(36), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
        )

    # ix_notifications_user_id: speeds up per-user notification listing
    op.create_index('ix_notifications_user_id', 'notifications', ['user_id'])

    # ix_notifications_user_id_is_read: speeds up unread_count query per user
    op.create_index(
        'ix_notifications_user_id_is_read',
        'notifications',
        ['user_id', 'is_read'],
    )


def downgrade() -> None:
    """Drop the notifications table and its indexes."""
    op.drop_index('ix_notifications_user_id_is_read', table_name='notifications')
    op.drop_index('ix_notifications_user_id', table_name='notifications')
    op.drop_table('notifications')
