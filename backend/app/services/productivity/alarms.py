"""Alarms (PRD 12, sections 10, 11, 65 and 71).

**No occurrence rows, deliberately.** Everything else in PRD 12 that repeats
generates concrete rows; an alarm does not, because there is nothing worth
keeping about last Tuesday's seven o'clock. Nobody asks what they did about it,
nothing counts it, and a table of them would be a history somebody has to tidy.
So "when does this next go off" is derived from the stored time, the stored
days and the clock -- the same choice PRD 2 made for a robot's connection
status, for the same reason: a value meaning "right now" is wrong the moment it
is written.

**What this module cannot promise, and says so.** Section 11 asks for the
chosen platform mechanism to be verified before anything claims clock-app
reliability, and section 71 asks for the gap to be stated plainly. The honest
position for this build is further back than section 11's fallback: **the app
has never been run on a physical phone**, so no notification has fired, no
alarm has fired, and no vibration has been felt. An alarm here is a row and a
scheduled local notification. ``wording.ALARM_LIMITATION`` is the sentence the
product itself shows, beside the list, so nobody has to read a report to find
it out.

**The robot cannot sound one either** (section 65). Its speaker reports
``not_connected``, so the robot's alarm card is information on a screen. The
builder says so on the card rather than implying a sound happened.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Alarm
from app.models.enums import ALARM_RECURRENCES, ALARM_SOUND_KEYS
from app.services.errors import DomainError, NotFoundError
from app.services.medications.doses import zone_for
from app.services.productivity import recurrence

logger = logging.getLogger(__name__)

#: How many alarms one profile may hold. A generous morning.
MAX_ALARMS = 50

#: How long an alarm reads as "now". Ten minutes: after that it is not an alarm
#: any more, and a robot card still showing 7:00 AM at half past is worse than
#: no card at all.
RING_WINDOW = timedelta(minutes=10)

EDITABLE_FIELDS = frozenset(
    {
        "label",
        "time_of_day",
        "timezone",
        "recurrence",
        "weekdays",
        "on_date",
        "enabled",
        "sound_key",
        "vibration",
    }
)


class AlarmNotFoundError(NotFoundError):
    code = "alarm_not_found"


class TooManyAlarmsError(DomainError):
    status_code = 409
    code = "too_many_alarms"


class InvalidAlarmError(DomainError):
    status_code = 422
    code = "invalid_alarm"


def _log(action: str) -> None:
    """``alarm.create success``. Never the label, which the user typed."""
    logger.info("alarm.%s success", action)


def pattern_for(alarm: Alarm) -> recurrence.Pattern:
    """The alarm's recurrence, flattened for the generator.

    A one-off alarm's ``start_date`` *and* ``end_date`` are its own date, so it
    produces exactly one moment however wide a window it is asked about.
    """
    if alarm.recurrence == "one_time":
        assert alarm.on_date is not None, "a one-off alarm has a date"
        return recurrence.Pattern(
            recurrence="one_time",
            timezone=alarm.timezone,
            start_date=alarm.on_date,
            end_date=alarm.on_date,
            time_of_day=alarm.time_of_day,
        )
    return recurrence.Pattern(
        recurrence=alarm.recurrence,
        timezone=alarm.timezone,
        # An alarm has no start date of its own: "every Tuesday at seven" began
        # whenever it was created, and the generator is always asked about
        # today onwards. ``date.min`` is the honest way to say "no start".
        start_date=date.min,
        time_of_day=alarm.time_of_day,
        weekdays=alarm.weekdays,
    )


# --- reading ----------------------------------------------------------------


def get_alarm(db: Session, profile_id: uuid.UUID, alarm_id: uuid.UUID) -> Alarm:
    """One alarm of this profile's, or a 404 that confirms nothing."""
    alarm = db.execute(
        select(Alarm).where(Alarm.id == alarm_id, Alarm.profile_id == profile_id)
    ).scalar_one_or_none()
    if alarm is None:
        raise AlarmNotFoundError("Not found.")
    return alarm


def find_by_client_id(
    db: Session, profile_id: uuid.UUID, client_alarm_id: str | None
) -> Alarm | None:
    if not client_alarm_id:
        return None
    return db.execute(
        select(Alarm).where(
            Alarm.profile_id == profile_id, Alarm.client_alarm_id == client_alarm_id
        )
    ).scalar_one_or_none()


def list_alarms(
    db: Session, profile_id: uuid.UUID, *, enabled_only: bool = False
) -> list[Alarm]:
    """This profile's alarms, earliest time of day first."""
    query = select(Alarm).where(Alarm.profile_id == profile_id)
    if enabled_only:
        query = query.where(Alarm.enabled.is_(True))
    return list(
        db.execute(query.order_by(Alarm.time_of_day.asc(), Alarm.created_at.asc()))
        .scalars()
        .all()
    )


def next_fire(alarm: Alarm, now: datetime) -> datetime | None:
    """When this alarm next goes off, or None.

    None for a disabled alarm and for a one-off whose day has gone. Derived on
    every read, so a one-off alarm quietly stops being "next" without anything
    having to remember to clear it.
    """
    if not alarm.enabled:
        return None
    return recurrence.next_occurrence(pattern_for(alarm), now)


def is_ringing(alarm: Alarm, now: datetime) -> bool:
    """Whether this alarm's moment is happening about now.

    Used by the robot builder, which has no occurrence row to look at. The
    window is checked backwards from ``now`` rather than forwards, because an
    alarm that is about to go off is not yet an alarm.
    """
    if not alarm.enabled:
        return False
    pattern = pattern_for(alarm)
    zone = zone_for(alarm.timezone)
    today = recurrence.local_today(zone, now)
    for moment in recurrence.occurrences(
        pattern, today - timedelta(days=1), today + timedelta(days=1)
    ):
        if now - RING_WINDOW <= moment.scheduled_for <= now:
            return True
    return False


@dataclass(frozen=True)
class AlarmFire:
    """One moment an alarm goes off, for the phone's notification schedule."""

    alarm: Alarm
    fire_at: datetime


def upcoming_fires(
    db: Session, profile_id: uuid.UUID, now: datetime, *, days: int = 14
) -> list[AlarmFire]:
    """Every moment every enabled alarm goes off in the next ``days``.

    What the phone's scheduler mirrors into the operating system. A fortnight,
    matching the reminder horizon, so an app that has been closed for a week
    still has alarms left to fire.
    """
    fires: list[AlarmFire] = []
    for alarm in list_alarms(db, profile_id, enabled_only=True):
        zone = zone_for(alarm.timezone)
        today = recurrence.local_today(zone, now)
        for moment in recurrence.occurrences(
            pattern_for(alarm), today, today + timedelta(days=days)
        ):
            if moment.scheduled_for > now:
                fires.append(AlarmFire(alarm=alarm, fire_at=moment.scheduled_for))
    fires.sort(key=lambda entry: entry.fire_at)
    return fires


# --- writing ----------------------------------------------------------------


@dataclass(frozen=True)
class AlarmInput:
    label: str
    time_of_day: time
    recurrence: str = "one_time"
    timezone: str = "UTC"
    weekdays: list[int] | None = None
    on_date: date | None = None
    enabled: bool = True
    sound_key: str = "default"
    vibration: bool = True
    client_alarm_id: str | None = None
    source: str = "user"


def _check(
    *,
    rule: str,
    weekdays: list[int] | None,
    on_date: date | None,
    sound_key: str,
    timezone: str,
) -> None:
    if rule not in ALARM_RECURRENCES:
        raise InvalidAlarmError("That is not a repeat an alarm has.")
    if sound_key not in ALARM_SOUND_KEYS:
        raise InvalidAlarmError("That is not a sound Nura has.")
    zone_for(timezone)
    if rule == "selected_days":
        if not weekdays:
            raise InvalidAlarmError("Choose at least one day.")
        if any(day < 0 or day > 6 for day in weekdays):
            raise InvalidAlarmError("That is not a day of the week.")
    elif weekdays:
        raise InvalidAlarmError("That repeat does not use days of the week.")
    if rule == "one_time":
        if on_date is None:
            raise InvalidAlarmError("A one-off alarm needs a date.")
    elif on_date is not None:
        raise InvalidAlarmError("A repeating alarm does not take a date.")


def create_alarm(
    db: Session, profile_id: uuid.UUID, data: AlarmInput, now: datetime
) -> Alarm:
    """Adds an alarm (section 10).

    Stores a choice. It does not verify that the operating system will honour
    it, because nothing in this project can: see the module docstring and
    ``wording.ALARM_LIMITATION``.
    """
    if not data.label.strip():
        raise InvalidAlarmError("An alarm needs a label.")
    _check(
        rule=data.recurrence,
        weekdays=data.weekdays,
        on_date=data.on_date,
        sound_key=data.sound_key,
        timezone=data.timezone,
    )
    if len(list_alarms(db, profile_id)) >= MAX_ALARMS:
        raise TooManyAlarmsError("There are too many alarms set already.")

    alarm = Alarm(
        profile_id=profile_id,
        label=data.label.strip(),
        time_of_day=data.time_of_day,
        timezone=data.timezone,
        recurrence=data.recurrence,
        weekdays=sorted(set(data.weekdays)) if data.weekdays else None,
        on_date=data.on_date,
        enabled=data.enabled,
        sound_key=data.sound_key,
        vibration=data.vibration,
        source=data.source,
        client_alarm_id=data.client_alarm_id,
    )
    db.add(alarm)
    db.commit()
    db.refresh(alarm)
    _log("create")
    return alarm


def update_alarm(db: Session, alarm: Alarm, fields: dict[str, Any]) -> Alarm:
    """Edits an alarm. Nothing is regenerated, because nothing was generated."""
    unknown = set(fields) - EDITABLE_FIELDS
    if unknown:
        raise InvalidAlarmError(f"An alarm has no {sorted(unknown)[0]}.")

    merged = {
        "recurrence": alarm.recurrence,
        "weekdays": alarm.weekdays,
        "on_date": alarm.on_date,
        "sound_key": alarm.sound_key,
        "timezone": alarm.timezone,
        **fields,
    }
    _check(
        rule=str(merged["recurrence"]),
        weekdays=merged["weekdays"],
        on_date=merged["on_date"],
        sound_key=str(merged["sound_key"]),
        timezone=str(merged["timezone"]),
    )

    if "label" in fields:
        label = str(fields["label"] or "").strip()
        if not label:
            raise InvalidAlarmError("An alarm needs a label.")
        alarm.label = label
    for key in (
        "time_of_day",
        "timezone",
        "recurrence",
        "on_date",
        "enabled",
        "sound_key",
        "vibration",
    ):
        if key in fields:
            setattr(alarm, key, fields[key])
    if "weekdays" in fields:
        value = fields["weekdays"]
        alarm.weekdays = sorted(set(value)) if value else None

    db.commit()
    db.refresh(alarm)
    _log("update")
    return alarm


def set_enabled(db: Session, alarm: Alarm, *, enabled: bool) -> Alarm:
    """The switch on the list row (section 10). Idempotent."""
    if alarm.enabled == enabled:
        return alarm
    alarm.enabled = enabled
    db.commit()
    db.refresh(alarm)
    _log("enabled" if enabled else "disabled")
    return alarm


def delete_alarm(db: Session, alarm: Alarm) -> None:
    db.delete(alarm)
    db.commit()
    _log("delete")
