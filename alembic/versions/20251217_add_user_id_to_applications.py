"""add user_id to applications

Revision ID: a7b8c9d0e1f2
Revises: e35207fe4427
Create Date: 2025-12-17

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7b8c9d0e1f2'
down_revision: Union[str, None] = 'e35207fe4427'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # SQLite doesn't support ALTER CONSTRAINT, so we use batch mode
    with op.batch_alter_table('applications', schema=None) as batch_op:
        # Add user_id column (nullable initially for existing rows)
        batch_op.add_column(sa.Column('user_id', sa.UUID(), nullable=True))

        # Add foreign key constraint
        batch_op.create_foreign_key(
            'fk_applications_user_id',
            'users',
            ['user_id'],
            ['id']
        )

        # Make job_id nullable (for applications not linked to tracked jobs)
        batch_op.alter_column('job_id', existing_type=sa.UUID(), nullable=True)

    # Note: In production, you should populate user_id for existing rows before making it non-null


def downgrade() -> None:
    with op.batch_alter_table('applications', schema=None) as batch_op:
        # Remove foreign key
        batch_op.drop_constraint('fk_applications_user_id', type_='foreignkey')

        # Remove column
        batch_op.drop_column('user_id')

        # Revert job_id to non-nullable
        batch_op.alter_column('job_id', existing_type=sa.UUID(), nullable=False)
