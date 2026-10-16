"""Which time zone this person is in, when nobody has said.

PRD 12, sections 22, 35 and 36.

**The backend has never stored a user's time zone, and this does not add one.**
Every PRD before this one took the zone from the client, which was right: the
phone knows where it is and the server does not. A medication schedule carries
its own zone, so does an appointment, and so does a monitoring session.

That leaves one gap, and it is the assistant's. "Remind me to ring the bank at
four" arrives as text, through a model that has no clock and no location, into
a tool that has neither. Four o'clock *where*? PRD 10 hit the same wall and
answered it by refusing: ``StartMonitoringArgs`` offers three fixed durations
and no "until bedtime", because a fixed duration is the same length of time
everywhere and a bedtime is not.

A reminder cannot be answered that way -- the whole thing is a wall-clock time
-- so this module answers the question from what the person has already told
us. The zones on their own reminders, routines, alarms, medication schedules
and appointments are facts they entered through a client that knew where it
was. The most recently entered one is the best available answer, and
``None`` -- meaning *nobody has ever told us* -- is a real answer the tools act
on rather than papering over.

**Nothing here guesses.** No IP lookup, no locale, no server zone, no UTC
fallback pretending to be a choice. A tool that cannot find a zone says so and
asks, which is section 22's clarification rule applied to the one piece of
information a model genuinely cannot supply.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Alarm,
    Appointment,
    GeneralReminder,
    MedicationSchedule,
    Routine,
    SafetyMonitoringSession,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class KnownZone:
    """A zone the person themselves entered, and where it came from."""

    name: str
    #: Which kind of record it was read off, for the sentence a tool returns.
    #: Never an id and never a title -- this travels into a model's context.
    source: str


#: The tables that carry a zone the user chose, newest first wins. Ordered by
#: how directly each one is about "where I am right now": a reminder or an
#: alarm was set for a local time today; an appointment may have been made for
#: somewhere the person is travelling to.
#:
#: Typed ``Any`` for the model rather than a protocol: all six are declarative
#: classes with ``timezone``, ``profile_id`` and ``created_at``, and inventing
#: a structural type for a loop that reads three columns would be more code
#: than the loop.
_SOURCES: tuple[tuple[str, Any, str], ...] = (
    ("reminder", GeneralReminder, "timezone"),
    ("alarm", Alarm, "timezone"),
    ("routine", Routine, "timezone"),
    ("medication schedule", MedicationSchedule, "timezone"),
    ("safety session", SafetyMonitoringSession, "timezone"),
    ("appointment", Appointment, "timezone"),
)


def known_zone(db: Session, profile_id: uuid.UUID) -> KnownZone | None:
    """The most recent zone this person entered, or None.

    One query per table, each ordered by ``created_at`` and limited to one row:
    six cheap indexed lookups rather than a union nobody can read. The newest
    across all six wins, and ties break in ``_SOURCES`` order.
    """
    best: tuple[datetime, KnownZone] | None = None
    for label, model, column in _SOURCES:
        row = db.execute(
            select(getattr(model, column), model.created_at)
            .where(model.profile_id == profile_id)
            .order_by(model.created_at.desc())
            .limit(1)
        ).first()
        if row is None:
            continue
        name, created_at = row
        if not name:
            continue
        if best is None or created_at > best[0]:
            best = (created_at, KnownZone(name=name, source=label))
    return None if best is None else best[1]


def zone_name(db: Session, profile_id: uuid.UUID) -> str | None:
    """Just the name, for a caller that does not need to say where it came from."""
    found = known_zone(db, profile_id)
    return None if found is None else found.name
