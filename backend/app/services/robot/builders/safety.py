"""PRD 10's state, on PRD 11's screen, with nothing added.

PRD 11, sections 8, 9, 54, 72, 100, 113, 114, 115 and 127.

**PRD 10 is the source of truth and this file only reads it.** Section 54, and
section 100 is the reason it matters: no safety behaviour may depend on
presentation hardware. So nothing here starts, advances, resolves or escalates
anything. It does not even expire a monitoring session whose time has passed --
``monitoring.peek_session`` exists precisely so that drawing a screen cannot
have a safety side effect.

**Reconciliation rather than notification.** ``sync`` asks what is true now and
makes the robot's cards match. Nothing in PRD 10 had to be modified to call it,
which is what keeps the robot additive -- and it is also why a card can never
be stale: there is no event that could have been missed, only state that is
read again. Section 113's "when the event resolves, cancel or update the
pending safety presentation" is therefore not a hook somebody has to remember,
it is what happens on the next read.

**The copy is PRD 10's answer, not a summary of it.** Section 8 requires the
display to show the actual escalation state, and forbids "Help is on the way."
``wording.emergency_lines`` is given three facts -- who an alert record exists
for, whether any calling provider is configured, whether there are contacts at
all -- and there is no argument it could be passed that would make it claim
somebody is coming.

**A caregiver acknowledgement is an acknowledgement.** Section 115: the card
says somebody pressed a button in their own app, because that is what the
backend knows. It does not say they are nearby, on their way or at the door.
"""

import logging
import uuid
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    CaregiverRelationship,
    Device,
    DevicePresentation,
    SafetyAlert,
    SafetyEvent,
    SafetyMonitoringSession,
)
from app.models.enums import (
    SAFETY_EVENT_AWAITING_RESPONSE_STATUSES,
    SAFETY_EVENT_EMERGENCY_STATUSES,
)
from app.services.robot import layouts, queue, wording
from app.services.safety import capabilities as safety_capabilities
from app.services.safety import events as safety_events
from app.services.safety import monitoring as monitoring_service

logger = logging.getLogger(__name__)

SOURCE = "safety"

CHECK_TYPE = "safety_check"
STATUS_TYPE = "safety_status"
EMERGENCY_TYPE = "emergency_status"

#: All three go when the thing they described stops being true.
SAFETY_TYPES = (EMERGENCY_TYPE, CHECK_TYPE, STATUS_TYPE)

#: How long the "Emergency request cancelled" card stays up (section 114). Long
#: enough that somebody walking back into the room sees it, short enough that
#: it is not still there an hour later implying something happened recently.
CANCELLED_NOTICE = timedelta(minutes=2)

#: How recently an event must have been cancelled for that card to appear.
CANCELLED_WINDOW = timedelta(minutes=2)

#: A safety card is worth sending to a screen and nothing else. No audio: a
#: robot announcing an emergency in a room is a decision PRD 11 does not make,
#: and no deployment has a speaker to make it with.
REQUIRES = ("display", "display_text")


def sync(db: Session, device: Device, now: datetime) -> list[DevicePresentation]:
    """Makes this robot's safety cards match PRD 10 (sections 54 and 113).

    Called on every device poll and on every read of the robot's status, so
    the cards are a view of the live state rather than a record of
    notifications that may or may not have been delivered.
    """
    profile_id = device.owner_profile_id
    if profile_id is None:
        return []

    queued: list[DevicePresentation] = []
    event = safety_events.active_event(db, profile_id)

    if event is not None and event.status in SAFETY_EVENT_EMERGENCY_STATUSES:
        _cancel_except(db, device, keep=EMERGENCY_TYPE, now=now)
        row = _queue_emergency(db, device, event, now)
        if row is not None:
            queued.append(row)
    elif event is not None and event.status in SAFETY_EVENT_AWAITING_RESPONSE_STATUSES:
        _cancel_except(db, device, keep=CHECK_TYPE, now=now)
        row = _queue_check(db, device, event, now)
        if row is not None:
            queued.append(row)
    else:
        # Nothing is live. Section 113: withdraw what was about the event.
        queue.cancel_types(
            db,
            device.id,
            presentation_types=(EMERGENCY_TYPE, CHECK_TYPE),
            reason="source_resolved",
            now=now,
        )
        row = _queue_cancelled_notice(db, device, profile_id, now)
        if row is not None:
            queued.append(row)

    session = monitoring_service.peek_session(db, profile_id, now)
    if session is None:
        queue.cancel_types(
            db,
            device.id,
            presentation_types=(STATUS_TYPE,),
            reason="source_resolved",
            now=now,
        )
    elif event is None:
        # Section 9's subtle indicator, and only when nothing louder is
        # happening: during a check or an escalation the screen has something
        # more important on it.
        row = _queue_monitoring(db, device, session, now)
        if row is not None:
            queued.append(row)
    return queued


def _cancel_except(db: Session, device: Device, *, keep: str, now: datetime) -> None:
    others = tuple(kind for kind in SAFETY_TYPES if kind != keep)
    queue.cancel_types(
        db, device.id, presentation_types=others, reason="superseded", now=now
    )


# --- the three cards ---------------------------------------------------------


def alert_labels(db: Session, event_id: uuid.UUID) -> tuple[str, ...]:
    """The names of the caregivers an alert record exists for (section 8).

    Read from ``safety_alerts`` rather than from the escalation plan: the plan
    says who Nura intended to reach, and the alert rows say who a record was
    actually created for. Section 8 asks for the actual state.
    """
    rows = db.execute(
        select(CaregiverRelationship.invited_name)
        .join(SafetyAlert, SafetyAlert.relationship_id == CaregiverRelationship.id)
        .where(SafetyAlert.safety_event_id == event_id)
        .order_by(CaregiverRelationship.invited_name.asc())
    ).all()
    return tuple(name for (name,) in rows)


def _queue_emergency(
    db: Session, device: Device, event: SafetyEvent, now: datetime
) -> DevicePresentation | None:
    """Section 8. The whole card is PRD 10's answer, in PRD 10's words."""
    capability_map = safety_capabilities.capability_map()
    payload = layouts.build_payload(
        "EMERGENCY",
        title=wording.PRESENTATION_TITLES[EMERGENCY_TYPE],
        lines=list(
            wording.emergency_lines(
                alert_labels=alert_labels(db, event.id),
                calling_configured=capability_map.get("audio_calling") == "available",
                has_contacts=_has_contacts(db, event),
            )
        ),
        serious=True,
        sensitive=False,
    )
    request = queue.PresentationRequest(
        presentation_type=EMERGENCY_TYPE,
        layout="EMERGENCY",
        payload=payload,
        source=SOURCE,
        source_id=str(event.id),
        requires=REQUIRES,
    )
    return queue.queue(db, device, request, now)


def _has_contacts(db: Session, event: SafetyEvent) -> bool:
    """Whether there was anybody in the chain when escalation ran.

    Taken from the snapshot PRD 10 froze at the moment escalation started
    (section 88 there), so the card describes the emergency as it happened
    rather than as the contact list looks now.
    """
    snapshot = event.escalation_snapshot or {}
    plan = snapshot.get("plan")
    if isinstance(plan, list):
        return len(plan) > 0
    return False


def _queue_check(
    db: Session, device: Device, event: SafetyEvent, now: datetime
) -> DevicePresentation | None:
    """Sections 7 and 9. Serious, so there is no face and no animation."""
    profile = event.profile
    seconds = _seconds_left(event, now)
    payload = layouts.build_payload(
        "STATUS",
        title=wording.PRESENTATION_TITLES[CHECK_TYPE],
        lines=list(
            wording.safety_check_lines(
                name=profile.preferred_name if profile is not None else None,
                seconds=seconds,
            )
        ),
        serious=True,
        # Section 86: there is no input hardware anywhere, so the card says
        # where the answer goes rather than offering a button that is not
        # there. A robot that reported buttons would get the actions instead.
        respond_in_app=True,
        sensitive=False,
    )
    request = queue.PresentationRequest(
        presentation_type=CHECK_TYPE,
        layout="STATUS",
        payload=payload,
        source=SOURCE,
        # The status is part of the key, so the second prompt replaces the
        # first card rather than folding into it (PRD 10's section 8).
        source_id=f"{event.id}:{event.status}",
        requires=REQUIRES,
    )
    return queue.queue(db, device, request, now)


def _seconds_left(event: SafetyEvent, now: datetime) -> int:
    deadline = event.second_prompt_deadline_at or event.response_deadline_at
    if deadline is None:
        return 0
    return max(0, int((deadline - now).total_seconds()))


def _queue_monitoring(
    db: Session,
    device: Device,
    session: SafetyMonitoringSession,
    now: datetime,
) -> DevicePresentation | None:
    """Section 9's indicator. It says monitoring is on, and nothing more."""
    payload = layouts.build_payload(
        "STATUS",
        title=wording.PRESENTATION_TITLES[STATUS_TYPE],
        lines=list(
            wording.monitoring_lines(ends_at=session.ends_at, zone=session.timezone)
        ),
        serious=True,
        sensitive=False,
    )
    request = queue.PresentationRequest(
        presentation_type=STATUS_TYPE,
        layout="STATUS",
        payload=payload,
        source=SOURCE,
        source_id=str(session.id),
        requires=REQUIRES,
    )
    return queue.queue(db, device, request, now)


def _queue_cancelled_notice(
    db: Session, device: Device, profile_id: uuid.UUID, now: datetime
) -> DevicePresentation | None:
    """Section 114. Only for an escalation that was actually cancelled.

    A check somebody simply answered needs no notice -- they were there, they
    answered, and a card telling them so would be noise. What section 114 is
    about is an emergency that got as far as escalating and was then called
    off, where leaving the emergency card up would be the dangerous kind of
    stale.
    """
    event = db.execute(
        select(SafetyEvent)
        .where(
            SafetyEvent.profile_id == profile_id,
            SafetyEvent.resolution == "cancelled_by_user",
            SafetyEvent.escalation_started_at.is_not(None),
            SafetyEvent.resolved_at.is_not(None),
            SafetyEvent.resolved_at >= now - CANCELLED_WINDOW,
        )
        .order_by(SafetyEvent.resolved_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    if event is None:
        return None

    payload = layouts.build_payload(
        "EMERGENCY",
        title=wording.PRESENTATION_TITLES[EMERGENCY_TYPE],
        lines=list(wording.emergency_cancelled_lines()),
        serious=True,
        sensitive=False,
    )
    request = queue.PresentationRequest(
        presentation_type=EMERGENCY_TYPE,
        layout="EMERGENCY",
        payload=payload,
        source=SOURCE,
        source_id=f"{event.id}:cancelled",
        requires=REQUIRES,
        expires_at=now + CANCELLED_NOTICE,
    )
    return queue.queue(db, device, request, now)


def queue_acknowledgement(
    db: Session,
    device: Device,
    alert: SafetyAlert,
    now: datetime,
    *,
    label: str,
) -> DevicePresentation | None:
    """Section 115, called only when the backend has the acknowledgement.

    Not part of ``sync``: an acknowledgement is a moment rather than a state,
    and reconciling it would put it back on the screen every poll for as long
    as the row existed.
    """
    if alert.acknowledged_at is None:
        return None
    payload = layouts.build_payload(
        "STATUS",
        title=wording.PRESENTATION_TITLES[STATUS_TYPE],
        lines=[wording.acknowledgement_line(label)],
        serious=True,
        sensitive=False,
    )
    request = queue.PresentationRequest(
        presentation_type=STATUS_TYPE,
        layout="STATUS",
        payload=payload,
        source=SOURCE,
        source_id=f"{alert.id}:acknowledged",
        requires=REQUIRES,
        expires_at=now + CANCELLED_NOTICE,
    )
    return queue.queue(db, device, request, now)
