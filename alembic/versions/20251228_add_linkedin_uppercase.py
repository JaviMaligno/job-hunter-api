"""Add LINKEDIN (uppercase) to emailprovider enum.

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
Create Date: 2025-12-28

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "e1f2a3b4c5d6"
down_revision = "d0e1f2a3b4c5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add 'LINKEDIN' to the emailprovider enum (uppercase to match GMAIL, OUTLOOK)
    op.execute("ALTER TYPE emailprovider ADD VALUE IF NOT EXISTS 'LINKEDIN'")


def downgrade() -> None:
    pass
