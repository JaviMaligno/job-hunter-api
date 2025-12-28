"""Add linkedin to emailprovider enum.

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
Create Date: 2025-12-28

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = "d0e1f2a3b4c5"
down_revision = "c9d0e1f2a3b4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add 'linkedin' to the emailprovider enum
    # PostgreSQL allows adding values to enums
    op.execute("ALTER TYPE emailprovider ADD VALUE IF NOT EXISTS 'linkedin'")


def downgrade() -> None:
    # PostgreSQL doesn't support removing enum values easily
    # This would require recreating the enum type
    pass
