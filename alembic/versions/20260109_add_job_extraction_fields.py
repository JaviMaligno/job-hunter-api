"""Add remote_type, employment_type, easy_apply to Job model.

Revision ID: g3h4i5j6k7l8
Revises: f2a3b4c5d6e7
Create Date: 2026-01-09

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "g3h4i5j6k7l8"
down_revision = "f2a3b4c5d6e7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add new columns to jobs table
    # These columns support enhanced job extraction with Gemini AI

    # remote_type: "remote", "hybrid", "onsite"
    op.add_column("jobs", sa.Column("remote_type", sa.String(50), nullable=True))

    # employment_type: "full-time", "part-time", "contract", "internship"
    op.add_column("jobs", sa.Column("employment_type", sa.String(50), nullable=True))

    # easy_apply: True if LinkedIn Easy Apply or similar
    op.add_column("jobs", sa.Column("easy_apply", sa.Boolean(), nullable=True, default=False))


def downgrade() -> None:
    # Remove the new columns
    op.drop_column("jobs", "easy_apply")
    op.drop_column("jobs", "employment_type")
    op.drop_column("jobs", "remote_type")
