"""add auth tables and columns

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2025-12-17

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b8c9d0e1f2a3'
down_revision: Union[str, None] = 'a7b8c9d0e1f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create auth_provider enum type for PostgreSQL
    auth_provider_enum = sa.Enum('email', 'google', 'linkedin', 'github', name='authprovider')

    # Add auth columns to users table
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('password_hash', sa.String(255), nullable=True))
        batch_op.add_column(sa.Column('auth_provider', sa.String(50), nullable=True, server_default='email'))
        batch_op.add_column(sa.Column('provider_user_id', sa.String(255), nullable=True))
        batch_op.add_column(sa.Column('email_verified', sa.Boolean(), nullable=True, server_default='false'))
        batch_op.add_column(sa.Column('avatar_url', sa.String(500), nullable=True))

        # Make first_name and last_name nullable for OAuth users
        batch_op.alter_column('first_name', existing_type=sa.String(100), nullable=True)
        batch_op.alter_column('last_name', existing_type=sa.String(100), nullable=True)

    # Create refresh_tokens table
    op.create_table(
        'refresh_tokens',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('token_hash', sa.String(255), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('revoked', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('device_info', sa.String(500), nullable=True),
        sa.Column('ip_address', sa.String(45), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='fk_refresh_tokens_user_id'),
    )

    # Create index on token_hash for fast lookups
    op.create_index('ix_refresh_tokens_token_hash', 'refresh_tokens', ['token_hash'], unique=False)


def downgrade() -> None:
    # Drop refresh_tokens table
    op.drop_index('ix_refresh_tokens_token_hash', table_name='refresh_tokens')
    op.drop_table('refresh_tokens')

    # Remove auth columns from users table
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('avatar_url')
        batch_op.drop_column('email_verified')
        batch_op.drop_column('provider_user_id')
        batch_op.drop_column('auth_provider')
        batch_op.drop_column('password_hash')

        # Revert first_name and last_name to non-nullable
        batch_op.alter_column('first_name', existing_type=sa.String(100), nullable=False)
        batch_op.alter_column('last_name', existing_type=sa.String(100), nullable=False)
