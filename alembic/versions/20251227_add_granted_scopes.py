"""Add granted_scopes to email_connections.

Revision ID: 20251227_granted_scopes
Revises: 20251217_add_auth_tables
Create Date: 2025-12-27

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "c9d0e1f2a3b4"
down_revision = "b8c9d0e1f2a3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add granted_scopes column to email_connections table
    op.add_column(
        "email_connections",
        sa.Column("granted_scopes", sa.Text(), nullable=True, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("email_connections", "granted_scopes")
