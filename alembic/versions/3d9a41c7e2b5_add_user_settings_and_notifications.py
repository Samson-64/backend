"""add user_settings and notifications

Gives both clients a working preferences store and a persisted notification
centre. user_settings is a 1:1 row per user created lazily on first read;
notifications records booking events per recipient with read tracking, and a
dedupe key so the reminder scheduler can re-run safely after a restart.

Revision ID: 3d9a41c7e2b5
Revises: b7d3e1f4a206
Create Date: 2026-09-29 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '3d9a41c7e2b5'
down_revision: Union[str, Sequence[str], None] = 'b7d3e1f4a206'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'user_settings',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('language', sa.String(length=10), nullable=False),
        sa.Column('timezone', sa.String(length=64), nullable=False),
        sa.Column('default_duration_minutes', sa.Integer(), nullable=False),
        sa.Column('preferred_parking_floor', sa.String(length=20), nullable=True),
        sa.Column('notify_booking_updates', sa.Boolean(), nullable=False),
        sa.Column('notify_new_bookings', sa.Boolean(), nullable=False),
        sa.Column('notify_reminders', sa.Boolean(), nullable=False),
        sa.Column('reminder_minutes_before', sa.Integer(), nullable=False),
        sa.Column('quiet_hours_enabled', sa.Boolean(), nullable=False),
        sa.Column('quiet_hours_start', sa.String(length=5), nullable=False),
        sa.Column('quiet_hours_end', sa.String(length=5), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_user_settings_user_id', 'user_settings', ['user_id'], unique=True
    )

    op.create_table(
        'notifications',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('category', sa.Enum(
            'BOOKING_STATUS', 'NEW_BOOKING', 'REMINDER', 'SYSTEM',
            name='notification_category',
        ), nullable=False),
        sa.Column('title', sa.String(length=120), nullable=False),
        sa.Column('body', sa.String(length=500), nullable=False),
        sa.Column('booking_id', sa.String(length=36), nullable=True),
        sa.Column('dedupe_key', sa.String(length=120), nullable=True),
        sa.Column('read_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['booking_id'], ['bookings.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_notifications_user_id', 'notifications', ['user_id'], unique=False
    )
    op.create_index(
        'ix_notifications_booking_id', 'notifications', ['booking_id'], unique=False
    )
    # MySQL allows multiple NULLs in a unique index, so only reminders (the sole
    # writer of dedupe_key) are constrained.
    op.create_index(
        'uq_notifications_dedupe',
        'notifications',
        ['user_id', 'dedupe_key'],
        unique=True,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('uq_notifications_dedupe', table_name='notifications')
    op.drop_index('ix_notifications_booking_id', table_name='notifications')
    op.drop_index('ix_notifications_user_id', table_name='notifications')
    op.drop_table('notifications')

    op.drop_index('ix_user_settings_user_id', table_name='user_settings')
    op.drop_table('user_settings')
