"""Safety monitoring, SOS and escalation.

PRD 10, sections 9, 15, 33, 83, 88, 89 and 102.

Five tables, and the shape of the second one is the whole design:

    safety_monitoring_sessions    a period the user asked to be watched over
        |
        +-- safety_events             something that happened, and what came of it
                |
                +-- safety_escalation_attempts   one try at reaching one person
                +-- safety_alerts                an in-app record for a caregiver

    safety_audit_events           what the system did, kept so it can be answered for

**Nothing here is a diagnosis.** Section 3 draws the line and sections 16 and
52 police it: an event type says what was *observed*, never what it means.
Every sensor-observed type begins with ``possible_``, enforced by a test that
reads ``SAFETY_EVENT_TYPES_REQUIRING_MONITORING`` and asserts the prefix on all
of them. There is no confidence column on ``safety_events``, no severity, and
no classification -- section 54 keeps confidence as engineering metadata on the
detector interface, where it cannot be mistaken for a probability that somebody
is ill.

**Every deadline is a stored timestamp.** Section 28 asks for state that a
restarted backend can reconstruct, so there is no in-memory timer anywhere:
``response_deadline_at`` and ``second_prompt_deadline_at`` are columns, the
worker reads them with a plain ``WHERE deadline < now``, and an app that was
force-quit mid-countdown changes nothing about when escalation happens.

**An attempt is not a delivery.** ``safety_escalation_attempts.status`` has both
``attempted`` and ``delivered`` and nothing in this codebase writes the second
one, because no provider exists to confirm anything (sections 35, 38 and 39).
``not_configured`` is a first-class outcome rather than a failure: a build that
cannot send an SMS has not failed to send one, and saying so is the difference
between an honest system and one that quietly loses emergencies.

**An alert record is not a notification.** ``safety_alerts`` rows prove that an
alert was created for a caregiver, which is all section 37 claims. Nothing in
this schema can say the caregiver saw it until they open it and ``read_at`` is
written by their own request.

**Nothing medical is in here.** No symptom, no medication, no condition, no
message. Section 90 keeps the safety trail minimal and section 92 rules out
storing video, audio or images -- there is no media column on any of these
tables, and no foreign key into the health record from any of them.
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
    SAFETY_AUDIT_ACTOR_KINDS,
    SAFETY_AUDIT_EVENT_TYPES,
    SAFETY_ESCALATION_ATTEMPT_STATUSES,
    SAFETY_ESCALATION_CHANNELS,
    SAFETY_ESCALATION_OUTCOMES,
    SAFETY_EVENT_RESOLUTIONS,
    SAFETY_EVENT_STATUSES,
    SAFETY_EVENT_TYPES,
    SAFETY_FALSE_POSITIVE_REASONS,
    SAFETY_MONITORING_DURATION_MODES,
    SAFETY_MONITORING_END_REASONS,
    SAFETY_MONITORING_SOURCES,
    SAFETY_MONITORING_STATUSES,
    SAFETY_RESPONSE_TIMEOUT_SECONDS,
    SAFETY_TRIGGER_SOURCES,
    SAFETY_USER_RESPONSES,
    sql_in_list,
)

if TYPE_CHECKING:
    from app.models.caregiver import CaregiverRelationship
    from app.models.profile import Profile

#: IANA zone names are well under this; the longest in the database is 32
#: characters. The same width medication schedules use.
TIMEZONE_MAX_LENGTH = 64

#: A client-supplied idempotency key (sections 20, 75 and 77).
IDEMPOTENCY_KEY_MAX_LENGTH = 64

#: The snapshot of a recipient's name taken when escalation starts (section 87).
#: Long enough for an emergency contact's name, which is the longest thing that
#: goes in it.
RECIPIENT_LABEL_MAX_LENGTH = 120

#: A stable failure code from a provider, such as ``not_configured``. Never a
#: provider's own error text, which could name a phone number.
FAILURE_CODE_MAX_LENGTH = 40


def _timeout_in_list() -> str:
    """``SAFETY_RESPONSE_TIMEOUT_SECONDS`` as a SQL ``IN`` list of integers."""
    return "(" + ", ".join(str(value) for value in SAFETY_RESPONSE_TIMEOUT_SECONDS) + ")"


class SafetyMonitoringSession(Base, TimestampMixin):
    """A period the user explicitly asked to be watched over (section 9).

    **Monitoring is never silently enabled** (section 4). A row here exists
    because somebody pressed Start, and ``started_by_account_id`` records who.
    Section 10 reserves ``caregiver_future`` as a source and the service refuses
    it: a caregiver turning monitoring on for somebody without their knowledge
    is the surveillance product this whole system is written against.

    ``ends_at`` is computed by the server from ``duration_mode`` and never taken
    from the client, which is what makes section 61's "do not silently extend"
    checkable: the only way a session runs longer than it was asked to is a bug
    in one function.

    ``timezone`` is carried because "until bedtime" is a wall-clock time, and a
    wall-clock time without a zone is a different instant every few months --
    the same reason a medication schedule carries one.
    """

    __tablename__ = "safety_monitoring_sessions"
    __table_args__ = (
        CheckConstraint(
            f"status IN {sql_in_list(SAFETY_MONITORING_STATUSES)}",
            name="ck_safety_monitoring_sessions_status",
        ),
        CheckConstraint(
            f"duration_mode IN {sql_in_list(SAFETY_MONITORING_DURATION_MODES)}",
            name="ck_safety_monitoring_sessions_duration_mode",
        ),
        CheckConstraint(
            f"source IN {sql_in_list(SAFETY_MONITORING_SOURCES)}",
            name="ck_safety_monitoring_sessions_source",
        ),
        CheckConstraint(
            "end_reason IS NULL OR end_reason IN "
            f"{sql_in_list(SAFETY_MONITORING_END_REASONS)}",
            name="ck_safety_monitoring_sessions_end_reason",
        ),
        CheckConstraint(
            f"response_timeout_seconds IN {_timeout_in_list()}",
            name="ck_safety_monitoring_sessions_timeout",
        ),
        # An active session has not ended, and an ended one has. Stated as a
        # constraint because "ended at some point but still active" is the state
        # a monitoring system must never be able to reach.
        CheckConstraint(
            "(status = 'active') = (ended_at IS NULL)",
            name="ck_safety_monitoring_sessions_ended",
        ),
        # Only the open-ended mode may have no end. Section 5 forbids a hidden
        # monitoring period, and a null ``ends_at`` on any other mode would be
        # exactly that.
        CheckConstraint(
            "ends_at IS NOT NULL OR duration_mode = 'until_turned_off'",
            name="ck_safety_monitoring_sessions_ends_at",
        ),
        # One active session per profile. Partial, so a person can be monitored
        # again tomorrow while every past session keeps its history.
        Index(
            "uq_safety_monitoring_sessions_active",
            "profile_id",
            unique=True,
            postgresql_where="status = 'active'",
        ),
        # What the worker scans: active sessions whose time is up (section 81).
        Index("ix_safety_monitoring_sessions_ends_at", "status", "ends_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    #: ``SET NULL``: a session's history outlives the account that started it.
    started_by_account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="active"
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    #: Null only for ``until_turned_off``.
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_mode: Mapped[str] = mapped_column(String(24), nullable=False)
    #: IANA zone the duration was worked out in.
    timezone: Mapped[str] = mapped_column(
        String(TIMEZONE_MAX_LENGTH), nullable=False, server_default="UTC"
    )
    #: Stored on the session, as section 7 requires, so an event inherits the
    #: timeout that was chosen when monitoring started -- not the one in force
    #: when the event happened to be processed.
    response_timeout_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="45"
    )
    second_prompt_enabled: Mapped[bool] = mapped_column(
        nullable=False, server_default="false"
    )
    second_prompt_timeout_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="20"
    )
    source: Mapped[str] = mapped_column(
        String(24), nullable=False, server_default="mobile_app"
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    end_reason: Mapped[str | None] = mapped_column(String(24))

    profile: Mapped["Profile"] = relationship()


class SafetyEvent(Base, TimestampMixin):
    """Something observed or asked for, and what came of it (section 15).

    **The timestamps are the state machine.** ``response_deadline_at`` is when
    the first wait runs out; ``second_prompt_deadline_at`` is when the second
    does. Both are written when the clock starts, so section 28's "state should
    be reconstructable" needs no special code -- the worker's query is a
    comparison against columns, and a backend that restarts mid-countdown picks
    up exactly where it was.

    ``escalation_snapshot`` is section 88: the contact order, the response
    timeout and the capability map, frozen at the moment escalation began.
    Section 87 explains why -- a chain reordered halfway through an emergency
    must not change who is being reached -- and it makes an event readable years
    later without reconstructing what the configuration used to be.

    ``false_positive`` is nullable on purpose. Null means nobody was asked or
    nobody answered; false means they said it was real. Collapsing those two
    into one boolean would turn silence into a claim.
    """

    __tablename__ = "safety_events"
    __table_args__ = (
        CheckConstraint(
            f"event_type IN {sql_in_list(SAFETY_EVENT_TYPES)}",
            name="ck_safety_events_type",
        ),
        CheckConstraint(
            f"trigger_source IN {sql_in_list(SAFETY_TRIGGER_SOURCES)}",
            name="ck_safety_events_trigger_source",
        ),
        CheckConstraint(
            f"status IN {sql_in_list(SAFETY_EVENT_STATUSES)}",
            name="ck_safety_events_status",
        ),
        CheckConstraint(
            "user_response IS NULL OR user_response IN "
            f"{sql_in_list(SAFETY_USER_RESPONSES)}",
            name="ck_safety_events_user_response",
        ),
        CheckConstraint(
            "resolution IS NULL OR resolution IN "
            f"{sql_in_list(SAFETY_EVENT_RESOLUTIONS)}",
            name="ck_safety_events_resolution",
        ),
        CheckConstraint(
            "escalation_outcome IS NULL OR escalation_outcome IN "
            f"{sql_in_list(SAFETY_ESCALATION_OUTCOMES)}",
            name="ck_safety_events_escalation_outcome",
        ),
        CheckConstraint(
            "false_positive_reason IS NULL OR false_positive_reason IN "
            f"{sql_in_list(SAFETY_FALSE_POSITIVE_REASONS)}",
            name="ck_safety_events_false_positive_reason",
        ),
        # A finished event says how it finished. Section 127's "do not leave an
        # event stuck" starts here: there is no way to store a resolved row
        # without a resolution.
        CheckConstraint(
            "status NOT IN ('resolved', 'cancelled') "
            "OR (resolution IS NOT NULL AND resolved_at IS NOT NULL)",
            name="ck_safety_events_resolved",
        ),
        # A reason for a false alarm requires a false alarm.
        CheckConstraint(
            "false_positive_reason IS NULL OR false_positive IS TRUE",
            name="ck_safety_events_false_positive",
        ),
        # Section 77: a retried SOS finds its own event rather than making a
        # second one. Partial, because most events have no client id.
        Index(
            "uq_safety_events_client_id",
            "profile_id",
            "client_event_id",
            unique=True,
            postgresql_where="client_event_id IS NOT NULL",
        ),
        # Section 20: a device retrying a trigger does not duplicate it.
        Index(
            "uq_safety_events_idempotency_key",
            "profile_id",
            "idempotency_key",
            unique=True,
            postgresql_where="idempotency_key IS NOT NULL",
        ),
        Index("ix_safety_events_profile_triggered", "profile_id", "triggered_at"),
        # What the maintenance worker scans (section 81). Both deadlines in one
        # index, because the query is "anything overdue", not "overdue first
        # prompts".
        Index("ix_safety_events_response_deadline", "status", "response_deadline_at"),
        Index("ix_safety_events_second_deadline", "status", "second_prompt_deadline_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    #: Null for a manual SOS raised while monitoring was off, which section 21
    #: requires to work. ``SET NULL`` so deleting old sessions never deletes the
    #: record of an emergency.
    monitoring_session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("safety_monitoring_sessions.id", ondelete="SET NULL"),
        index=True,
    )
    #: Which robot raised it, when one ever does. Null for everything today.
    device_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("devices.id", ondelete="SET NULL")
    )
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    trigger_source: Mapped[str] = mapped_column(String(32), nullable=False)
    triggered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    status: Mapped[str] = mapped_column(String(24), nullable=False)

    # --- the check-in (sections 23 to 28) ---
    #: What the user said, whenever they said it -- including after escalation
    #: already began (section 126).
    user_response: Mapped[str | None] = mapped_column(String(16))
    response_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    check_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    response_deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    second_prompt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    second_prompt_deadline_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )

    # --- escalation (sections 29 to 42) ---
    escalation_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    escalation_finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    escalation_outcome: Mapped[str | None] = mapped_column(String(32))
    #: Section 88. The contact order, the timeout and the capabilities as they
    #: were when escalation began. Names and priorities only -- no phone number
    #: and nothing medical.
    escalation_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    # --- the end (sections 44, 46, 47 and 48) ---
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution: Mapped[str | None] = mapped_column(String(32))
    #: Null means nobody was asked, or nobody answered. Not the same as "no".
    false_positive: Mapped[bool | None] = mapped_column()
    false_positive_reason: Mapped[str | None] = mapped_column(String(24))

    #: Set by the app so a retried SOS is the same emergency (section 77).
    client_event_id: Mapped[str | None] = mapped_column(
        String(IDEMPOTENCY_KEY_MAX_LENGTH)
    )
    #: Set by a device so a retried trigger is the same event (section 20).
    idempotency_key: Mapped[str | None] = mapped_column(
        String(IDEMPOTENCY_KEY_MAX_LENGTH)
    )

    profile: Mapped["Profile"] = relationship()
    session: Mapped["SafetyMonitoringSession | None"] = relationship()
    attempts: Mapped[list["SafetyEscalationAttempt"]] = relationship(
        back_populates="event",
        cascade="all, delete-orphan",
        order_by="SafetyEscalationAttempt.priority",
    )
    alerts: Mapped[list["SafetyAlert"]] = relationship(
        back_populates="event", cascade="all, delete-orphan"
    )


class SafetyEscalationAttempt(Base, TimestampMixin):
    """One try at reaching one person through one channel (section 33).

    A row exists for every recipient the policy considered, including the ones
    it could not reach: ``not_configured`` is written for a channel with no
    provider behind it, which is what makes section 42's display honest. The
    user sees "in-app alert created for Ayesha; phone calling is not
    configured", because both facts are rows.

    ``recipient_key`` is what makes section 75's idempotency work. A unique
    constraint over three nullable foreign keys would not: PostgreSQL treats
    NULLs as distinct, so two rows with a null ``contact_id`` never collide.
    A single text key -- ``contact:<uuid>`` or ``caregiver:<uuid>`` -- collides
    exactly when it should, and a worker that runs twice writes one row.

    ``recipient_label`` is a snapshot of the name, taken when escalation starts
    (section 87). A contact deleted afterwards leaves an attempt that still says
    who was tried, which is the whole point of keeping the record.
    """

    __tablename__ = "safety_escalation_attempts"
    __table_args__ = (
        CheckConstraint(
            f"channel IN {sql_in_list(SAFETY_ESCALATION_CHANNELS)}",
            name="ck_safety_escalation_attempts_channel",
        ),
        CheckConstraint(
            f"status IN {sql_in_list(SAFETY_ESCALATION_ATTEMPT_STATUSES)}",
            name="ck_safety_escalation_attempts_status",
        ),
        CheckConstraint("priority >= 0", name="ck_safety_escalation_attempts_priority"),
        CheckConstraint(
            "retry_count >= 0", name="ck_safety_escalation_attempts_retry_count"
        ),
        # Section 75. One attempt per (event, recipient, channel), whatever a
        # retried worker run thinks.
        UniqueConstraint(
            "safety_event_id",
            "recipient_key",
            "channel",
            name="uq_safety_escalation_attempt_recipient",
        ),
        Index("ix_safety_escalation_attempts_event", "safety_event_id", "priority"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    safety_event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("safety_events.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    #: Carried as well as reachable through the event, the way a symptom entry
    #: carries its profile: "what was attempted for this person" should not need
    #: a join.
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    #: One of these two is set. ``SET NULL`` on both: the attempt outlives the
    #: contact, and ``recipient_label`` is why it still makes sense afterwards.
    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("emergency_contacts.id", ondelete="SET NULL")
    )
    caregiver_relationship_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("caregiver_relationships.id", ondelete="SET NULL"),
    )
    #: ``contact:<uuid>`` or ``caregiver:<uuid>``. Stable, and never null.
    recipient_key: Mapped[str] = mapped_column(String(64), nullable=False)
    #: The name as it was when escalation began (section 87).
    recipient_label: Mapped[str] = mapped_column(
        String(RECIPIENT_LABEL_MAX_LENGTH), nullable=False
    )
    #: Position in the chain. Caregiver alerts are 0 -- they go out first,
    #: alongside the chain rather than inside it (sections 32 and 40).
    priority: Mapped[int] = mapped_column(Integer, nullable=False)
    channel: Mapped[str] = mapped_column(String(24), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="pending"
    )
    #: Which provider handled it, when one ever does. Null today.
    provider: Mapped[str | None] = mapped_column(String(40))
    attempted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: Written only when a provider confirms. Nothing in this build writes it.
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: A stable code such as ``not_configured``. Never a provider's own message,
    #: which could name a phone number.
    failure_code: Mapped[str | None] = mapped_column(String(FAILURE_CODE_MAX_LENGTH))
    #: Bounded by ``escalation.MAX_RETRIES`` (section 124).
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    event: Mapped[SafetyEvent] = relationship(back_populates="attempts")


class SafetyAlert(Base):
    """An in-app safety alert for one caregiver (section 83).

    No ``TimestampMixin``: an alert is not edited. ``read_at`` and
    ``acknowledged_at`` are the only things that change, and each is written
    once by the caregiver's own request.

    **A row here means an alert exists, not that anybody saw it** (sections 37
    and 38). That distinction is the reason this table is separate from
    ``safety_escalation_attempts``: the attempt records what the system tried,
    and the alert is the artefact a caregiver can open. An unopened alert has a
    null ``read_at`` forever, and nothing anywhere fills it in.

    Acknowledgement records that a caregiver pressed "I'm checking on them". It
    is not proof of physical contact (section 84) and it does not resolve the
    event (section 125) -- those are different rows written by different people.
    """

    __tablename__ = "safety_alerts"
    __table_args__ = (
        # Section 75: one alert per caregiver per event, whatever a retried
        # worker run thinks.
        UniqueConstraint(
            "safety_event_id",
            "recipient_account_id",
            name="uq_safety_alert_recipient",
        ),
        Index("ix_safety_alerts_recipient", "recipient_account_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    safety_event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("safety_events.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    #: The caregiver's account. ``CASCADE``: an alert addressed to nobody is
    #: not a record of anything.
    recipient_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    #: Which relationship it was created under. Read again before the alert is
    #: shown, so a caregiver whose ``safety_alerts`` permission was withdrawn
    #: stops seeing it (section 86).
    relationship_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("caregiver_relationships.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    event: Mapped[SafetyEvent] = relationship(back_populates="alerts")
    relationship_row: Mapped["CaregiverRelationship"] = relationship()


class SafetyAuditEvent(Base):
    """What the system did, kept so it can be answered for (section 89).

    No ``updated_at`` and no delete path, for the reason the caregiver audit
    table gives: a row that can be edited is not an audit row.

    Unlike the caregiver trail, this one *does* record reads of a sort --
    ``alert_acknowledged`` -- because a caregiver saying "I'm checking on them"
    is an action somebody may later need to account for. It still records no
    views: there is no event for a caregiver opening the safety history, for the
    same reason PRD 9 has none for opening a medication list.

    **Nothing medical and nothing identifying reaches ``meta``** (section 90).
    Every payload is built by ``services.safety.audit`` from a fixed set of
    keys -- a status, a channel, a count, an outcome -- and no helper there
    accepts free text or a phone number.
    """

    __tablename__ = "safety_audit_events"
    __table_args__ = (
        CheckConstraint(
            f"event_type IN {sql_in_list(SAFETY_AUDIT_EVENT_TYPES)}",
            name="ck_safety_audit_events_type",
        ),
        CheckConstraint(
            f"actor_kind IN {sql_in_list(SAFETY_AUDIT_ACTOR_KINDS)}",
            name="ck_safety_audit_events_actor_kind",
        ),
        Index("ix_safety_audit_events_profile_created", "profile_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    safety_event_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("safety_events.id", ondelete="CASCADE"), index=True
    )
    monitoring_session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("safety_monitoring_sessions.id", ondelete="CASCADE"),
    )
    #: ``SET NULL`` so the event survives the account that caused it. Null is
    #: also normal: a timeout has no person behind it.
    actor_account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    actor_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    meta: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
