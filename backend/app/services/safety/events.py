"""Where a safety event comes from, and the one place one is created.

PRD 10, sections 11, 12, 14, 15, 16, 17, 19, 20, 21, 22, 57 and 77.

**One function creates events.** ``create`` is it, and every path -- the app's
SOS button, the "Nura, emergency" contract, the device-trigger endpoint, the
developer harness, the seed script -- goes through it. That is what makes the
rules in section 22 and section 57 enforceable rather than repeated: a passive
trigger with no active monitoring is refused here, and there is no second door.

**Section 57, which is the one that matters most.** The model may not invent a
sensor event. Nothing in ``services.assistant`` calls this function with a
``possible_*`` type -- the assistant's safety tools can start monitoring, raise
a manual SOS the user asked for, and answer a check, and the tool argument
models have no event-type field at all. A speculative interpretation of
something somebody typed cannot become a ``possible_seizure_like_activity``
row, because there is nowhere to put the idea.

**Manual SOS does not need monitoring** (section 21) and passive triggers do
(section 22). Those two sentences are the branch in ``create``, written once.

**A repeat is the same emergency** (section 77). Two guards, in order: an
explicit idempotency key if the client sent one, and otherwise any event that
is still live for this profile. Somebody pressing SOS twice because nothing
visibly happened must not produce two emergencies, two chains and two sets of
caregiver alerts.
"""

import logging
import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Profile, SafetyEvent, SafetyMonitoringSession
from app.models.enums import (
    SAFETY_EVENT_LIVE_STATUSES,
    SAFETY_EVENT_TYPES,
    SAFETY_EVENT_TYPES_IMMEDIATE,
    SAFETY_EVENT_TYPES_REQUIRING_MONITORING,
    SAFETY_TRIGGER_SOURCES,
)
from app.services.errors import DomainError, NotFoundError
from app.services.safety import audit, checks, monitoring

logger = logging.getLogger(__name__)

#: How many events one history request returns at most.
MAX_EVENTS = 50


class SafetyEventNotFoundError(NotFoundError):
    code = "safety_event_not_found"


class MonitoringNotActiveError(DomainError):
    """A passive trigger arrived while Safety Monitoring was off (section 22).

    409 and a stable code, so a future robot can tell "you are not being
    watched right now" apart from "your token is wrong". Section 22 says to
    reject or ignore safely; rejecting with a reason is the version a device
    can act on, and it is also the version that cannot be mistaken for Nura
    quietly monitoring anyway.
    """

    status_code = 409
    code = "monitoring_not_active"


class EventTypeNotAllowedError(DomainError):
    """A type this caller may not raise (sections 17, 18 and 57)."""

    status_code = 403
    code = "safety_event_type_not_allowed"


def active_event(db: Session, profile_id: uuid.UUID) -> SafetyEvent | None:
    """The event still in flight for this person, if any.

    "In flight" includes ``escalated``: alerts exist, emergency mode is on, and
    the user has not said anything yet. Section 126 is explicit that a late
    answer still belongs to that event rather than starting a new one.
    """
    return db.execute(
        select(SafetyEvent)
        .where(
            SafetyEvent.profile_id == profile_id,
            SafetyEvent.status.in_(SAFETY_EVENT_LIVE_STATUSES),
        )
        .order_by(SafetyEvent.triggered_at.desc())
        .limit(1)
    ).scalar_one_or_none()


def get_event(db: Session, profile_id: uuid.UUID, event_id: uuid.UUID) -> SafetyEvent:
    """One event of this person's, or 404.

    Scoped by profile, so an id belonging to somebody else is not found rather
    than refused -- the answer this codebase gives everywhere, for the reason
    it gives everywhere.
    """
    event = db.execute(
        select(SafetyEvent).where(
            SafetyEvent.id == event_id, SafetyEvent.profile_id == profile_id
        )
    ).scalar_one_or_none()
    if event is None:
        raise SafetyEventNotFoundError("Not found.")
    return event


def list_events(
    db: Session, profile_id: uuid.UUID, *, limit: int = MAX_EVENTS
) -> list[SafetyEvent]:
    """Safety history, newest first (section 49)."""
    return list(
        db.execute(
            select(SafetyEvent)
            .where(SafetyEvent.profile_id == profile_id)
            .order_by(SafetyEvent.triggered_at.desc())
            .limit(min(limit, MAX_EVENTS))
        )
        .scalars()
        .all()
    )


def _existing_for_key(
    db: Session,
    profile_id: uuid.UUID,
    *,
    client_event_id: str | None,
    idempotency_key: str | None,
) -> SafetyEvent | None:
    """The event a retried request already created, if there is one."""
    if client_event_id:
        found = db.execute(
            select(SafetyEvent).where(
                SafetyEvent.profile_id == profile_id,
                SafetyEvent.client_event_id == client_event_id,
            )
        ).scalar_one_or_none()
        if found is not None:
            return found
    if idempotency_key:
        return db.execute(
            select(SafetyEvent).where(
                SafetyEvent.profile_id == profile_id,
                SafetyEvent.idempotency_key == idempotency_key,
            )
        ).scalar_one_or_none()
    return None


def create(
    db: Session,
    profile: Profile,
    *,
    event_type: str,
    trigger_source: str,
    now: datetime,
    actor_account_id: uuid.UUID | None = None,
    actor_kind: str = "primary_user",
    device_id: uuid.UUID | None = None,
    client_event_id: str | None = None,
    idempotency_key: str | None = None,
) -> SafetyEvent:
    """Records that something happened, and starts whatever should follow.

    The branch section 21 and section 22 ask for:

    - ``manual_sos`` and ``call_for_help`` skip the countdown entirely and go
      straight to escalation, whether or not monitoring is on.
    - everything else needs an active monitoring session and begins a check.

    The caller commits. Everything this function does -- the event, the
    deadlines, the escalation and every audit row -- is one transaction, so an
    event can never exist without the thing that was supposed to follow it.
    """
    assert event_type in SAFETY_EVENT_TYPES, event_type
    assert trigger_source in SAFETY_TRIGGER_SOURCES, trigger_source

    existing = _existing_for_key(
        db,
        profile.id,
        client_event_id=client_event_id,
        idempotency_key=idempotency_key,
    )
    if existing is not None:
        logger.info("safety.event.duplicate ignored")
        return existing

    session: SafetyMonitoringSession | None = monitoring.active_session(
        db, profile.id, now
    )
    if event_type in SAFETY_EVENT_TYPES_REQUIRING_MONITORING and session is None:
        logger.info("safety.event.refused: monitoring is not active")
        raise MonitoringNotActiveError("Safety Monitoring is not on.")

    live = active_event(db, profile.id)
    if live is not None:
        # Section 77. The same emergency, however many times it was reported.
        logger.info("safety.event.folded into the event already in flight")
        return live

    event = SafetyEvent(
        profile_id=profile.id,
        monitoring_session_id=session.id if session is not None else None,
        device_id=device_id,
        event_type=event_type,
        trigger_source=trigger_source,
        triggered_at=now,
        status="checking_user",
        client_event_id=client_event_id,
        idempotency_key=idempotency_key,
    )
    db.add(event)
    db.flush()

    audit.record(
        db,
        profile_id=profile.id,
        actor_account_id=actor_account_id,
        actor_kind=actor_kind,
        event_type="trigger_received",
        safety_event_id=event.id,
        monitoring_session_id=session.id if session is not None else None,
        now=now,
        meta=audit.trigger_meta(event_type, trigger_source),
    )

    if event_type in SAFETY_EVENT_TYPES_IMMEDIATE:
        # Sections 12, 14 and 26: no countdown. Somebody asking for help is
        # not a signal that needs confirming.
        checks.escalate_now(db, event, now=now, reason=event_type)
    else:
        checks.begin_check(db, event, session, now=now)

    logger.info("safety.event.created type=%s", event_type)
    return event
