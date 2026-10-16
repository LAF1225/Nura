"""One answer to "where does safety stand for this person, right now".

PRD 10, sections 4, 11, 42, 43, 51, 59, 60, 64, 73 and 74.

The Safety screen, the assistant's ``get_safety_status`` tool and the
emergency-mode check all need the same five facts, and assembling them in
three places is how three screens come to disagree about whether monitoring is
on. They are assembled here, once.

**Reading the status advances the clock.** A deadline that has passed is acted
on before the answer is built, which is section 80's state-correctness half:
whoever looks sees the true state, with or without the worker having run. The
worker still matters -- somebody whose phone is in another room is not looking
-- and section 80 asks for the distinction to be explicit, so it is drawn here
in one place and tested in two files.

**The warnings are computed, not written into a screen.** "There is nobody to
reach" comes from the chain being empty and "Nura cannot reach anybody" from
the capability map, so sections 73 and 74 are properties of the deployment
rather than sentences somebody remembered to add.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import EmergencyContact, SafetyEvent, SafetyMonitoringSession
from app.models.enums import SAFETY_EVENT_EMERGENCY_STATUSES
from app.services.safety import capabilities, checks, events, monitoring

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SafetyStatus:
    """Everything the Safety screen needs in one request."""

    monitoring: SafetyMonitoringSession | None
    active_event: SafetyEvent | None
    capabilities: dict[str, str]
    #: How many active emergency contacts there are. A count, not the chain:
    #: the status endpoint is read often and the names belong to the screen
    #: that manages them.
    emergency_contact_count: int
    #: Section 73's warning condition.
    has_emergency_contacts: bool
    #: Section 74's warning condition -- no push, no SMS, no calling.
    external_delivery_available: bool
    #: Section 43: escalation has begun and has not been answered for.
    emergency_mode: bool


def active_contact_count(db: Session, profile_id: uuid.UUID) -> int:
    return int(
        db.execute(
            select(func.count(EmergencyContact.id)).where(
                EmergencyContact.profile_id == profile_id,
                EmergencyContact.is_active.is_(True),
            )
        ).scalar_one()
    )


def emergency_mode_for(event: SafetyEvent | None) -> bool:
    """Whether the app should be in emergency mode (sections 43 and 44).

    Derived from the event rather than stored, for the reason every derived
    value in this codebase is derived: a flag meaning "right now" is wrong the
    moment it is written. Emergency mode begins when escalation does and ends
    when the event does -- which is section 44's list of exits, all four of
    which are ways an event stops being live.
    """
    return event is not None and event.status in SAFETY_EVENT_EMERGENCY_STATUSES


def current(db: Session, profile_id: uuid.UUID, now: datetime) -> SafetyStatus:
    """The whole picture, with any passed deadline acted on first."""
    session = monitoring.active_session(db, profile_id, now)

    event = events.active_event(db, profile_id)
    if event is not None:
        advanced = checks.advance(db, event, now)
        if advanced is not event or advanced.status != event.status:
            db.commit()
        event = events.active_event(db, profile_id)

    contact_count = active_contact_count(db, profile_id)
    return SafetyStatus(
        monitoring=session,
        active_event=event,
        capabilities=capabilities.capability_map(),
        emergency_contact_count=contact_count,
        has_emergency_contacts=contact_count > 0,
        external_delivery_available=capabilities.external_delivery_available(),
        emergency_mode=emergency_mode_for(event),
    )


def in_emergency_mode(db: Session, profile_id: uuid.UUID) -> bool:
    """A cheap check for the assistant (section 43).

    Deliberately does *not* advance deadlines: this is asked on the path of
    every assistant reply, and a reply is not the right place to discover that
    somebody's escalation was due two minutes ago. The status endpoint and the
    worker both do that; this only reads.
    """
    return emergency_mode_for(events.active_event(db, profile_id))
