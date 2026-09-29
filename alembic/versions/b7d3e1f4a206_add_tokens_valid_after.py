"""add users.tokens_valid_after and stop expiring refresh tokens

Access tokens are now issued without an "exp" claim, so a session can only be
ended explicitly. This adds the cutoff column that makes that possible, and
backfills existing refresh tokens to never expire so that anyone already
signed in is not logged out by this change.

Revision ID: b7d3e1f4a206
Revises: c41f4e2f9a10
Create Date: 2026-09-28 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b7d3e1f4a206'
down_revision: Union[str, Sequence[str], None] = 'c41f4e2f9a10'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# MySQL DATETIME upper bound, used as the "never expires" marker. Must match
# auth_service.NEVER_EXPIRES.
NEVER_EXPIRES = '9999-12-31 23:59:59'


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'users',
        sa.Column('tokens_valid_after', sa.DateTime(), nullable=True),
    )
    # Existing sessions keep working: push every current refresh token's expiry
    # out to the sentinel instead of letting the old 7-day window sign people out.
    op.execute(
        sa.text(
            "UPDATE refresh_tokens SET expires_at = :never WHERE expires_at < :never"
        ).bindparams(never=NEVER_EXPIRES)
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('users', 'tokens_valid_after')
