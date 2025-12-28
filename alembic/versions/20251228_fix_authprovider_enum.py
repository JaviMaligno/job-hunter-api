"""Create authprovider enum and convert column.

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2025-12-28

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "f2a3b4c5d6e7"
down_revision = "e1f2a3b4c5d6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create the authprovider enum type in PostgreSQL
    # Use uppercase values to match how SQLAlchemy generates them
    op.execute("CREATE TYPE authprovider AS ENUM ('EMAIL', 'GOOGLE', 'LINKEDIN', 'GITHUB')")

    # Drop the default first (it's a string and can't be cast)
    op.execute("ALTER TABLE users ALTER COLUMN auth_provider DROP DEFAULT")

    # Convert the auth_provider column from varchar to enum
    # First, update any existing values to uppercase (if any)
    op.execute(
        "UPDATE users SET auth_provider = UPPER(auth_provider) WHERE auth_provider IS NOT NULL"
    )

    # Alter the column to use the enum type
    op.execute(
        "ALTER TABLE users ALTER COLUMN auth_provider TYPE authprovider USING auth_provider::authprovider"
    )

    # Add the default back as an enum value
    op.execute("ALTER TABLE users ALTER COLUMN auth_provider SET DEFAULT 'EMAIL'")


def downgrade() -> None:
    # Convert back to varchar
    op.execute(
        "ALTER TABLE users ALTER COLUMN auth_provider TYPE VARCHAR(50) USING auth_provider::text"
    )

    # Drop the enum type
    op.execute("DROP TYPE authprovider")
