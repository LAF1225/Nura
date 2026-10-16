"""PRD 13 data exports

One table, and nothing else at all.

    data_exports    one archive of one profile, with its expiry

**No existing table is touched** -- no column added, no type changed, no CHECK
constraint replaced. That is PRD 13 section 47's "keep schema changes minimal"
taken literally, and it is possible because the stage's two features need
almost nothing of their own:

**An export needs a row** because it has a file in private storage and an
expiry, and something has to say where the file is and when it stops being
downloadable.

**Deletion needs none.** Section 47 makes ``deletion_requests`` conditional on
deletion being asynchronous, and it is synchronous here: one statement plus a
file sweep, finished before the response is written. A table recording that
somebody asked to be deleted, surviving after they were, would be the single
piece of their data that outlived the request.

The cascade is the usual one: ``profile_id`` references ``profiles`` with
``ON DELETE CASCADE``, so deleting a profile removes its export rows. The bytes
those rows point at are removed by ``services.privacy.deletion``, which reads
the storage keys before the rows go -- no foreign key can reach a file, which is
the whole reason that service exists.

Revision ID: 1af52299dead
Revises: e40d2ad16353
Create Date: 2026-10-12 20:10:18.873150

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "1af52299dead"
down_revision: str | Sequence[str] | None = "e40d2ad16353"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "data_exports",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("profile_id", sa.UUID(), nullable=False),
        sa.Column("status", sa.String(length=12), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("file_storage_key", sa.String(length=200), nullable=True),
        sa.Column("byte_size", sa.Integer(), nullable=True),
        sa.Column("file_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("schema_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("categories", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("failure_reason", sa.String(length=200), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status <> 'failed' OR file_storage_key IS NULL",
            name="ck_data_exports_failed_no_file",
        ),
        sa.CheckConstraint(
            "status <> 'ready' OR (file_storage_key IS NOT NULL AND expires_at IS NOT NULL)",
            name="ck_data_exports_ready_file",
        ),
        sa.CheckConstraint(
            "status IN ('requested', 'generating', 'ready', 'failed', 'expired')",
            name="ck_data_exports_status",
        ),
        sa.CheckConstraint(
            "byte_size IS NULL OR byte_size > 0", name="ck_data_exports_byte_size"
        ),
        sa.CheckConstraint("file_count >= 0", name="ck_data_exports_file_count"),
        sa.CheckConstraint("schema_version >= 1", name="ck_data_exports_schema_version"),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("file_storage_key"),
    )
    op.create_index(
        op.f("ix_data_exports_profile_id"), "data_exports", ["profile_id"], unique=False
    )


def downgrade() -> None:
    """Downgrade schema.

    Safe in a way most downgrades are not: the table holds temporary archives
    with a one-day expiry, so dropping it loses nothing a person recorded.
    """
    op.drop_index(op.f("ix_data_exports_profile_id"), table_name="data_exports")
    op.drop_table("data_exports")
