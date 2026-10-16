"""Robot presentation, preferences and reported capabilities.

PRD 11, sections 10, 11, 13, 14, 19, 48, 57, 113, 119, 120 and 121.

Three tables, and the shape of the first one carries the whole design:

    devices                           already existed (PRD 2)
        |
        +-- device_presentations          one thing for the robot to show
        +-- device_presentation_preferences   how this robot should behave
        +-- device_capabilities           what this robot says it can do

**A presentation is a request, not an event.** The backend queueing a card is
not the robot showing it. Section 14 says so in words; this schema says it in a
CHECK constraint -- ``displayed_at`` cannot be written unless ``ack_state``
holds a render acknowledgement the device sent, so there is no code path, now
or later, that can mark something displayed because a fetch returned it.

**Capabilities come from the device, and ``not_verified`` can only come from
the device.** Section 12's point is that a compiled driver is not a working
one, and the backend has no way to tell the difference -- what it knows is
whether a robot has said anything, and the honest answer to that is
``not_connected``. So a missing row reads ``not_connected`` and the backend
never writes ``not_verified`` on its own initiative (section 91).

**Nothing here is a second source of truth.** A medication reminder row holds a
copy of what the robot should draw, built from the dose; the dose is still the
record. Section 51 makes the robot additive, which means a presentation can be
expired, cancelled or never shown without any effect on the health data it was
built from -- and there is no foreign key from a presentation into a dose, an
appointment or a message, only a ``dedupe_key`` naming the thing it came from.

**Payloads are small and layouts are fixed.** ``payload`` is JSONB holding a
validated envelope (``services.robot.layouts``) -- a layout name from a closed
set and a handful of short strings. Section 111 rules out markup, section 108
rules out media, and section 67 rules out letting a payload reach a log.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.enums import (
    ROBOT_ACK_STATES,
    ROBOT_CAPABILITY_KEYS,
    ROBOT_CAPABILITY_SOURCES,
    ROBOT_CAPABILITY_STATES,
    ROBOT_MEDICATION_PRIVACY_LEVELS,
    ROBOT_PRESENTATION_CANCEL_REASONS,
    ROBOT_PRESENTATION_FAILURE_CODES,
    ROBOT_PRESENTATION_LAYOUTS,
    ROBOT_PRESENTATION_PRIORITY_BANDS,
    ROBOT_PRESENTATION_SOURCES,
    ROBOT_PRESENTATION_STATUSES,
    ROBOT_PRESENTATION_TYPES,
    ROBOT_PRIVACY_LEVELS,
    ROBOT_SLEEP_SCREEN_MODES,
    sql_in_list,
)

if TYPE_CHECKING:
    from app.models.device import Device
    from app.models.profile import Profile

#: ``source_type:source_id:presentation_type`` (section 57). One text column
#: rather than three nullable foreign keys, for the reason PRD 10's
#: ``recipient_key`` is one column: PostgreSQL treats NULLs as distinct, so a
#: unique constraint over nullable columns never collides and the idempotency
#: it was meant to provide quietly does nothing.
DEDUPE_KEY_MAX_LENGTH = 160

#: A stable code, never a device's own error text (section 67).
FAILURE_CODE_MAX_LENGTH = 32


def _priority_in_list() -> str:
    """``ROBOT_PRESENTATION_PRIORITY_BANDS`` as a SQL ``IN`` list of integers."""
    return "(" + ", ".join(str(rank) for rank in ROBOT_PRESENTATION_PRIORITY_BANDS) + ")"


class DevicePresentation(Base, TimestampMixin):
    """One thing for one robot to show, and what became of it (section 13).

    The lifecycle, and which side writes each step:

        queued       backend, when something worth showing happened
        sent         backend, when the device fetched the envelope
        acknowledged device, "received"
        displayed    device, "render_started" or "render_completed"
        completed    device, "render_completed", or the backend when the card
                     has served its purpose
        expired      backend, once ``expires_at`` has passed unshown
        failed       device, "failed"
        not_supported device, "unsupported", or the backend when the capability
                     needed is not available
        cancelled    backend, when something preempted it or its source
                     resolved

    ``available_at`` and ``expires_at`` are both stored instants, the way PRD
    10 stores its deadlines: the selection query is a comparison, so a backend
    that restarted and a robot that was unplugged for a day both behave the
    same way. Sections 20 and 55.

    ``expires_at`` is nullable, and the nullability is section 113: a safety or
    emergency presentation is tied to the live PRD 10 event rather than to a
    timer, so it has no expiry instant and is withdrawn when the event
    resolves. Everything else has one.
    """

    __tablename__ = "device_presentations"
    __table_args__ = (
        CheckConstraint(
            f"presentation_type IN {sql_in_list(ROBOT_PRESENTATION_TYPES)}",
            name="ck_device_presentations_type",
        ),
        CheckConstraint(
            f"status IN {sql_in_list(ROBOT_PRESENTATION_STATUSES)}",
            name="ck_device_presentations_status",
        ),
        CheckConstraint(
            f"layout IN {sql_in_list(ROBOT_PRESENTATION_LAYOUTS)}",
            name="ck_device_presentations_layout",
        ),
        CheckConstraint(
            f"source IN {sql_in_list(ROBOT_PRESENTATION_SOURCES)}",
            name="ck_device_presentations_source",
        ),
        CheckConstraint(
            f"priority IN {_priority_in_list()}",
            name="ck_device_presentations_priority",
        ),
        CheckConstraint("protocol_version >= 1", name="ck_device_presentations_protocol"),
        CheckConstraint(
            f"ack_state IS NULL OR ack_state IN {sql_in_list(ROBOT_ACK_STATES)}",
            name="ck_device_presentations_ack_state",
        ),
        CheckConstraint(
            "failure_code IS NULL OR failure_code IN "
            f"{sql_in_list(ROBOT_PRESENTATION_FAILURE_CODES)}",
            name="ck_device_presentations_failure_code",
        ),
        CheckConstraint(
            "cancel_reason IS NULL OR cancel_reason IN "
            f"{sql_in_list(ROBOT_PRESENTATION_CANCEL_REASONS)}",
            name="ck_device_presentations_cancel_reason",
        ),
        # Section 14, as a constraint rather than a convention: nothing is
        # displayed unless a device said it rendered it. ``received`` is not
        # enough -- a device can receive an envelope and then fail to draw it.
        CheckConstraint(
            "displayed_at IS NULL OR (ack_state IS NOT NULL AND ack_state IN "
            "('render_started', 'render_completed'))",
            name="ck_device_presentations_displayed",
        ),
        # A withdrawn presentation says why, and a failed one says what failed.
        CheckConstraint(
            "status <> 'cancelled' OR cancel_reason IS NOT NULL",
            name="ck_device_presentations_cancelled",
        ),
        CheckConstraint(
            "status NOT IN ('failed', 'not_supported') OR failure_code IS NOT NULL",
            name="ck_device_presentations_failed",
        ),
        CheckConstraint(
            "expires_at IS NULL OR expires_at > available_at",
            name="ck_device_presentations_window",
        ),
        # Section 57: a retry builds the same key and finds the row that is
        # already waiting instead of making a second card. Partial, so the
        # same dose may be reminded again tomorrow once today's card is done.
        Index(
            "uq_device_presentations_dedupe",
            "device_id",
            "dedupe_key",
            unique=True,
            postgresql_where="status IN ('queued', 'sent', 'acknowledged', 'displayed')",
        ),
        # What "give me the next one" reads (section 121).
        Index(
            "ix_device_presentations_next",
            "device_id",
            "status",
            "priority",
            "available_at",
        ),
        # What expiry reads.
        Index(
            "ix_device_presentations_expiry",
            "expires_at",
            postgresql_where="status IN ('queued', 'sent', 'acknowledged', 'displayed')",
        ),
        Index("ix_device_presentations_profile_created", "profile_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    device_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("devices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    #: Carried alongside ``device_id`` the way every child table in this schema
    #: carries its profile: a query that filters by profile should not have to
    #: join through the device to be safe.
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    presentation_type: Mapped[str] = mapped_column(String(24), nullable=False)
    #: From ``ROBOT_PRESENTATION_PRIORITIES``, lowest first. Copied onto the row
    #: so the selection query can order on it, and so an old row still reads
    #: with the ranking it was queued under.
    priority: Mapped[int] = mapped_column(Integer, nullable=False)
    layout: Mapped[str] = mapped_column(String(16), nullable=False)
    #: The validated envelope body. Built by ``services.robot.layouts`` and
    #: never assembled anywhere else.
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    dedupe_key: Mapped[str] = mapped_column(String(DEDUPE_KEY_MAX_LENGTH), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="queued"
    )
    protocol_version: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="1"
    )
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: Written only on a render acknowledgement, and the CHECK above is what
    #: makes that true of the table rather than only of the service.
    displayed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: The last thing the device said about this presentation (section 19).
    ack_state: Mapped[str | None] = mapped_column(String(16))
    failure_code: Mapped[str | None] = mapped_column(String(FAILURE_CODE_MAX_LENGTH))
    cancel_reason: Mapped[str | None] = mapped_column(String(24))

    device: Mapped["Device"] = relationship()
    profile: Mapped["Profile"] = relationship()


class DevicePresentationPreferences(Base, TimestampMixin):
    """How one robot should behave, set before the hardware exists (section 48).

    Section 49 is the reason this table can be fully populated for a robot that
    cannot do any of it: a person may say "when the speaker works, do not read
    my messages out" today, and the setting is kept without implying that the
    speaker works. The capability map is a separate question, asked separately.

    ``reduced_motion`` is nullable, and the three states are the feature:
    ``NULL`` means follow the account's own accessibility preference, which is
    sections 30 and 105; ``true`` and ``false`` are deliberate overrides. A
    plain boolean would have had to pick a default and would then have silently
    stopped following the accessibility setting the first time anybody opened
    the screen.
    """

    __tablename__ = "device_presentation_preferences"
    __table_args__ = (
        UniqueConstraint("device_id", name="uq_device_presentation_preferences_device"),
        CheckConstraint(
            "brightness BETWEEN 0 AND 100",
            name="ck_device_presentation_preferences_brightness",
        ),
        CheckConstraint(
            "volume BETWEEN 0 AND 100",
            name="ck_device_presentation_preferences_volume",
        ),
        CheckConstraint(
            f"medication_privacy_level IN {sql_in_list(ROBOT_MEDICATION_PRIVACY_LEVELS)}",
            name="ck_device_presentation_preferences_medication_privacy",
        ),
        CheckConstraint(
            f"daily_life_privacy_level IN {sql_in_list(ROBOT_PRIVACY_LEVELS)}",
            name="ck_device_presentation_preferences_daily_life_privacy",
        ),
        CheckConstraint(
            f"sleep_screen_mode IN {sql_in_list(ROBOT_SLEEP_SCREEN_MODES)}",
            name="ck_device_presentation_preferences_sleep_screen",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    device_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("devices.id", ondelete="CASCADE"),
        nullable=False,
    )
    #: Nullable because a device can be claimed before it is linked to anybody,
    #: exactly as ``devices.owner_profile_id`` is.
    profile_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="SET NULL")
    )
    brightness: Mapped[int] = mapped_column(Integer, nullable=False, server_default="70")
    volume: Mapped[int] = mapped_column(Integer, nullable=False, server_default="40")
    #: NULL = follow ``user_settings.reduce_motion`` (sections 30 and 105).
    reduced_motion: Mapped[bool | None] = mapped_column()
    #: Section 104's conservative default: a reminder on a screen other people
    #: can see says as little as it can until somebody asks for more.
    medication_privacy_level: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="private"
    )
    #: All three default off (sections 43 and 104). Sensitive content does not
    #: start speaking in somebody's living room because a speaker appeared.
    read_medications_aloud: Mapped[bool] = mapped_column(
        nullable=False, server_default="false"
    )
    read_messages_aloud: Mapped[bool] = mapped_column(
        nullable=False, server_default="false"
    )
    read_assistant_aloud: Mapped[bool] = mapped_column(
        nullable=False, server_default="false"
    )
    sleep_screen_mode: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="dim"
    )
    face_animation_enabled: Mapped[bool] = mapped_column(
        nullable=False, server_default="true"
    )
    #: Section 24's "robot message display is enabled". Defaults on: the
    #: message is already an authorized one in the person's own home, and the
    #: thing that leaks into a room is reading it aloud, which defaults off.
    family_message_display_enabled: Mapped[bool] = mapped_column(
        nullable=False, server_default="true"
    )
    #: How much of a task, reminder or routine the robot may show
    #: (PRD 12, section 32). Defaults to ``full``, which is a different answer
    #: from the medication default and a deliberate one: "Call the
    #: physiotherapist" on a shelf is a note to self, and hiding it by default
    #: would make the robot useless for the thing PRD 12 is for. Somebody with
    #: a task they would rather not have read over their shoulder sets
    #: ``name_only`` or ``private``, and the builders apply it the same way the
    #: medication builder does.
    daily_life_privacy_level: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="full"
    )
    #: Section 31's additive principle, as a switch. Off means no task,
    #: reminder, alarm or routine card is ever queued -- and every one of them
    #: still works on the phone, because nothing about a daily-life item
    #: depends on the robot (PRD 12, section 31).
    daily_life_display_enabled: Mapped[bool] = mapped_column(
        nullable=False, server_default="true"
    )

    device: Mapped["Device"] = relationship()


class DeviceCapability(Base, TimestampMixin):
    """What one robot says it can do, and when it last said it (section 11).

    One row per capability rather than a JSONB blob, which section 119 invites
    a decision on. Three reasons, all of which turned out to matter:

      - the key and the state get CHECK constraints, which is section 120;
      - ``reported_at`` is per capability, so "the display was proven last
        Tuesday and the speaker has never been tested" is representable --
        which is section 124's stale-report case;
      - a device reporting a subset does not erase the rest.

    ``source`` separates a device's own claim from a startup self-test result
    (section 92) and from ``default``, which is the only value the backend
    writes by itself and means "nobody has said".
    """

    __tablename__ = "device_capabilities"
    __table_args__ = (
        UniqueConstraint(
            "device_id", "capability_key", name="uq_device_capabilities_key"
        ),
        CheckConstraint(
            f"capability_key IN {sql_in_list(ROBOT_CAPABILITY_KEYS)}",
            name="ck_device_capabilities_key",
        ),
        CheckConstraint(
            f"state IN {sql_in_list(ROBOT_CAPABILITY_STATES)}",
            name="ck_device_capabilities_state",
        ),
        CheckConstraint(
            f"source IN {sql_in_list(ROBOT_CAPABILITY_SOURCES)}",
            name="ck_device_capabilities_source",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    device_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("devices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    capability_key: Mapped[str] = mapped_column(String(24), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    source: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="device_report"
    )
    #: When the device said it. Distinct from ``updated_at``, which moves when
    #: the row is rewritten with the same answer.
    reported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    #: What was running when it said it, so a capability can be attributed to a
    #: build later. Not identity, and nothing authorizes on it.
    firmware_version: Mapped[str | None] = mapped_column(String(32))

    device: Mapped["Device"] = relationship()
