"""PRD 11 robot presentation, capabilities and preferences

Three new tables, all hanging off ``devices``, and nothing else changed.

    device_presentations                one thing for one robot to show
    device_presentation_preferences     how that robot should behave
    device_capabilities                 what that robot says it can do

**Nothing in PRD 0-10 is reshaped.** No existing column changes type,
nullability or default; no medical record is touched; no constraint is
replaced. Every foreign key points at ``devices`` or ``profiles``, and the
robot is additive in the schema exactly as it is in the code (PRD 11,
sections 51-54).

Section 119 invites a decision on where capabilities live, and this is it:
one row per capability rather than a JSONB column on ``devices``. Three
reasons, and the second is the one that decided it -- the key and the state get
CHECK constraints (section 120); ``reported_at`` is per capability, so "the
screen was proven last Tuesday and the speaker has never been tested" is
representable, which is section 124's stale-report case; and a device reporting
a subset does not erase the rest.

Two constraints are worth reading before anything else writes to these tables.

``ck_device_presentations_displayed`` is section 14 in SQL::

    displayed_at IS NULL
    OR (ack_state IS NOT NULL
        AND ack_state IN ('render_started', 'render_completed'))

The parenthesised half matters more than it looks: a SQL CHECK is satisfied
when it evaluates to TRUE *or null*, and ``ack_state IN (...)`` is null when
``ack_state`` is -- which is precisely the row this constraint exists to
refuse. Written the short way, it accepted it.

The backend handing a command to a robot is not the robot showing it. With this
constraint there is no code path -- now or in a later release -- that can mark
a presentation displayed without a device having said it rendered it.

``uq_device_presentations_dedupe`` is section 57, partial over the four open
statuses, so a retried build folds into the card that is already waiting while
tomorrow's dose still gets its own.

``device_presentation_preferences.reduced_motion`` is **nullable on purpose**
and null is the default: it means *follow the account's accessibility
preference* (sections 30 and 105). A plain boolean would have had to pick a
value, and would then have stopped following that preference the first time
anybody opened the screen.

Revision ID: 03ce36f69b39
Revises: 724cae2ee9c2
Create Date: 2026-10-11 16:41:26.211916

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "03ce36f69b39"
down_revision: str | Sequence[str] | None = "724cae2ee9c2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "device_capabilities",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("device_id", sa.UUID(), nullable=False),
        sa.Column("capability_key", sa.String(length=24), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column(
            "source", sa.String(length=16), server_default="device_report", nullable=False
        ),
        sa.Column("reported_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("firmware_version", sa.String(length=32), nullable=True),
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
            "capability_key IN ('display', 'display_text', 'display_animation', 'speaker', 'tts', 'audio_playback', 'microphone', 'wake_word', 'camera', 'camera_detection', 'buttons', 'touch')",
            name="ck_device_capabilities_key",
        ),
        sa.CheckConstraint(
            "source IN ('device_report', 'self_test', 'default')",
            name="ck_device_capabilities_source",
        ),
        sa.CheckConstraint(
            "state IN ('available', 'unavailable', 'not_verified', 'not_connected')",
            name="ck_device_capabilities_state",
        ),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "device_id", "capability_key", name="uq_device_capabilities_key"
        ),
    )
    op.create_index(
        op.f("ix_device_capabilities_device_id"),
        "device_capabilities",
        ["device_id"],
        unique=False,
    )
    op.create_table(
        "device_presentation_preferences",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("device_id", sa.UUID(), nullable=False),
        sa.Column("profile_id", sa.UUID(), nullable=True),
        sa.Column("brightness", sa.Integer(), server_default="70", nullable=False),
        sa.Column("volume", sa.Integer(), server_default="40", nullable=False),
        sa.Column("reduced_motion", sa.Boolean(), nullable=True),
        sa.Column(
            "medication_privacy_level",
            sa.String(length=16),
            server_default="private",
            nullable=False,
        ),
        sa.Column(
            "read_medications_aloud", sa.Boolean(), server_default="false", nullable=False
        ),
        sa.Column(
            "read_messages_aloud", sa.Boolean(), server_default="false", nullable=False
        ),
        sa.Column(
            "read_assistant_aloud", sa.Boolean(), server_default="false", nullable=False
        ),
        sa.Column(
            "sleep_screen_mode",
            sa.String(length=16),
            server_default="dim",
            nullable=False,
        ),
        sa.Column(
            "face_animation_enabled", sa.Boolean(), server_default="true", nullable=False
        ),
        sa.Column(
            "family_message_display_enabled",
            sa.Boolean(),
            server_default="true",
            nullable=False,
        ),
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
            "medication_privacy_level IN ('full', 'name_only', 'private')",
            name="ck_device_presentation_preferences_medication_privacy",
        ),
        sa.CheckConstraint(
            "sleep_screen_mode IN ('dim', 'sleeping_face', 'blank')",
            name="ck_device_presentation_preferences_sleep_screen",
        ),
        sa.CheckConstraint(
            "brightness BETWEEN 0 AND 100",
            name="ck_device_presentation_preferences_brightness",
        ),
        sa.CheckConstraint(
            "volume BETWEEN 0 AND 100", name="ck_device_presentation_preferences_volume"
        ),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "device_id", name="uq_device_presentation_preferences_device"
        ),
    )
    op.create_table(
        "device_presentations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("device_id", sa.UUID(), nullable=False),
        sa.Column("profile_id", sa.UUID(), nullable=False),
        sa.Column("presentation_type", sa.String(length=24), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("layout", sa.String(length=16), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("dedupe_key", sa.String(length=160), nullable=False),
        sa.Column(
            "status", sa.String(length=16), server_default="queued", nullable=False
        ),
        sa.Column("protocol_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("displayed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ack_state", sa.String(length=16), nullable=True),
        sa.Column("failure_code", sa.String(length=32), nullable=True),
        sa.Column("cancel_reason", sa.String(length=24), nullable=True),
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
            "ack_state IS NULL OR ack_state IN ('received', 'render_started', 'render_completed', 'failed', 'unsupported')",
            name="ck_device_presentations_ack_state",
        ),
        sa.CheckConstraint(
            "cancel_reason IS NULL OR cancel_reason IN ('preempted', 'source_resolved', 'source_cancelled', 'superseded', 'preference_changed', 'capability_withdrawn', 'device_unlinked')",
            name="ck_device_presentations_cancel_reason",
        ),
        sa.CheckConstraint(
            "displayed_at IS NULL OR (ack_state IS NOT NULL AND ack_state IN "
            "('render_started', 'render_completed'))",
            name="ck_device_presentations_displayed",
        ),
        sa.CheckConstraint(
            "failure_code IS NULL OR failure_code IN ('render_failed', 'unsupported_layout', 'unsupported_capability', 'unsupported_protocol_version', 'no_display', 'device_error')",
            name="ck_device_presentations_failure_code",
        ),
        sa.CheckConstraint(
            "layout IN ('FACE', 'TITLE_BODY', 'TITLE_VALUE', 'REMINDER', 'MESSAGE', 'STATUS', 'EMERGENCY', 'PAIRING_CODE')",
            name="ck_device_presentations_layout",
        ),
        sa.CheckConstraint(
            "presentation_type IN ('face_state', 'info_card', 'medication_reminder', 'appointment_reminder', 'family_message', 'assistant_response', 'safety_check', 'safety_status', 'emergency_status', 'system_status', 'setup_code')",
            name="ck_device_presentations_type",
        ),
        sa.CheckConstraint(
            "source IN ('medication', 'appointment', 'family_message', 'assistant', 'safety', 'system', 'user')",
            name="ck_device_presentations_source",
        ),
        sa.CheckConstraint(
            "status <> 'cancelled' OR cancel_reason IS NOT NULL",
            name="ck_device_presentations_cancelled",
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'sent', 'acknowledged', 'displayed', 'completed', 'expired', 'failed', 'cancelled', 'not_supported')",
            name="ck_device_presentations_status",
        ),
        sa.CheckConstraint(
            "status NOT IN ('failed', 'not_supported') OR failure_code IS NOT NULL",
            name="ck_device_presentations_failed",
        ),
        sa.CheckConstraint(
            "expires_at IS NULL OR expires_at > available_at",
            name="ck_device_presentations_window",
        ),
        sa.CheckConstraint(
            "priority IN (10, 20, 30, 35, 38, 40, 50, 60, 70, 80, 90)",
            name="ck_device_presentations_priority",
        ),
        sa.CheckConstraint(
            "protocol_version >= 1", name="ck_device_presentations_protocol"
        ),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_device_presentations_device_id"),
        "device_presentations",
        ["device_id"],
        unique=False,
    )
    op.create_index(
        "ix_device_presentations_expiry",
        "device_presentations",
        ["expires_at"],
        unique=False,
        postgresql_where="status IN ('queued', 'sent', 'acknowledged', 'displayed')",
    )
    op.create_index(
        "ix_device_presentations_next",
        "device_presentations",
        ["device_id", "status", "priority", "available_at"],
        unique=False,
    )
    op.create_index(
        "ix_device_presentations_profile_created",
        "device_presentations",
        ["profile_id", "created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_device_presentations_profile_id"),
        "device_presentations",
        ["profile_id"],
        unique=False,
    )
    op.create_index(
        "uq_device_presentations_dedupe",
        "device_presentations",
        ["device_id", "dedupe_key"],
        unique=True,
        postgresql_where="status IN ('queued', 'sent', 'acknowledged', 'displayed')",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        "uq_device_presentations_dedupe",
        table_name="device_presentations",
        postgresql_where="status IN ('queued', 'sent', 'acknowledged', 'displayed')",
    )
    op.drop_index(
        op.f("ix_device_presentations_profile_id"), table_name="device_presentations"
    )
    op.drop_index(
        "ix_device_presentations_profile_created", table_name="device_presentations"
    )
    op.drop_index("ix_device_presentations_next", table_name="device_presentations")
    op.drop_index(
        "ix_device_presentations_expiry",
        table_name="device_presentations",
        postgresql_where="status IN ('queued', 'sent', 'acknowledged', 'displayed')",
    )
    op.drop_index(
        op.f("ix_device_presentations_device_id"), table_name="device_presentations"
    )
    op.drop_table("device_presentations")
    op.drop_table("device_presentation_preferences")
    op.drop_index(
        op.f("ix_device_capabilities_device_id"), table_name="device_capabilities"
    )
    op.drop_table("device_capabilities")
