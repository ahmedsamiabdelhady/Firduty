"""Add email and status to teachers table

Revision ID: 0002
Revises: 0001
Create Date: 2024-01-02 00:00:00.000000

This migration is kept for compatibility with older databases.
For fresh databases, revision 0001 already includes these columns,
so this migration becomes a no-op.
"""

from typing import Sequence, Union

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # No-op:
    # Fresh databases already get email/status in 0001.
    pass


def downgrade() -> None:
    # No-op:
    # Nothing to undo here because 0001 already owns these columns.
    pass