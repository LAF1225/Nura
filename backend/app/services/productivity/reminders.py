"""General reminders and their occurrences (PRD 12, sections 7, 8, 9, 34, 35).

The shape is PRD 5's, deliberately. A reminder series says what repeats; an
occurrence is one concrete moment with a status on it; and generation tops the
window up on every read, so nothing depends on a background job having run
(section 63 says to document that dependency, and the honest documentation is
that there is none for correctness).

Three things are different from a medication dose, and each is a requirement.

**The words are not medication words** (section 8). Done, Snooze and Dismiss,
not Taken, Snooze and Skip. ``completed`` is as far as any status goes, nothing
counts adherence, and no skip reason is recorded -- a reminder to ring the bank
is not a health record and nothing about it is interpreted.

**Dismiss exists, and it is not Done.** Section 8 lists all three. Dismissing
says "I have seen this and I am not doing it", which is a different fact from
having done it, and keeping them apart is the difference between a list
somebody trusts and one they stop reading.

**A one-off series finishes.** After its single occurrence is answered or
missed, the series becomes ``completed`` rather than sitting ``active`` forever
with nothing left to produce. That is what lets the reminders list show "On"
honestly.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import GeneralReminder, GeneralReminderOccurrence
from app.models.enums import (
    REMINDER_ACTIVE_STATUSES,
    REMINDER_OCCURRENCE_OPEN_STATUSES,
    REMINDER_RECURRENCES,
    REMINDER_RECURRENCES_WITH_WEEKDAYS,
)
from app.models.productivity import MAX_REMINDER_SNOOZES
from app.services.errors import DomainError, NotFoundError
from app.services.medications.doses import SNOOZE_OPTIONS_MINUTES, zone_for
from app.services.productivity import recurrence

logger = logging.getLogger(__name__)

#: How many reminder series one profile may hold at once.
MAX_ACTIVE_REMINDERS = 200

#: Fields a client may change on a series. Changing any of them regenerates the
#: future occurrences, because the pattern they describe has moved.
EDITABLE_FIELDS = frozenset(
    {
        "title",
        "body",
        "recurrence",
        "timezone",
        "start_date",
        "end_date",
        "time_of_day",
        "weekdays",
        "day_of_month",
        "notification_enabled",
    }
)

#: Changing one of these means the occurrences have to be rebuilt.
PATTERN_FIELDS = frozenset(
    {
        "recurrence",
        "timezone",
        "start_date",
        "end_date",
        "time_of_day",
        "weekdays",
        "day_of_month",
    }
)


class ReminderNotFoundError(NotFoundError):
    code = "reminder_not_found"


class OccurrenceNotFoundError(NotFoundError):
    code = "reminder_occurrence_not_found"


class TooManyRemindersError(DomainError):
    status_code = 409
    code = "too_many_reminders"


class InvalidReminderError(DomainError):
    status_code = 422
    code = "invalid_reminder"


class OccurrenceNotActionableError(DomainError):
    """The occurrence is in a state where this action has no meaning."""

    status_code = 409
    code = "occurrence_not_actionable"


class SnoozeLimitError(DomainError):
    status_code = 409
    code = "snooze_limit_reached"


class InvalidSnoozeError(DomainError):
    status_code = 422
    code = "invalid_snooze_duration"


def _log(action: str, count: int | None = None) -> None:
    """``reminder.create success`` and nothing about what it says (section 45)."""
    if count is None:
        logger.info("reminder.%s success", action)
    else:
        logger.info("reminder.%s success (%d)", action, count)


# --- the pattern ------------------------------------------------------------


def pattern_for(reminder: GeneralReminder) -> recurrence.Pattern:
    """The reminder's recurrence, flattened for the generator."""
    return recurrence.Pattern(
        recurrence=reminder.recurrence,
        timezone=reminder.timezone,
        start_date=reminder.start_date,
        time_of_day=reminder.time_of_day,
        end_date=reminder.end_date,
        weekdays=reminder.weekdays,
        day_of_month=reminder.day_of_month,
    )


# --- reading ----------------------------------------------------------------


def get_reminder(
    db: Session, profile_id: uuid.UUID, reminder_id: uuid.UUID
) -> GeneralReminder:
    """One reminder of this profile's, or a 404 that confirms nothing."""
    reminder = db.execute(
        select(GeneralReminder).where(
            GeneralReminder.id == reminder_id,
            GeneralReminder.profile_id == profile_id,
        )
    ).scalar_one_or_none()
    if reminder is None:
        raise ReminderNotFoundError("Not found.")
    return reminder


def find_by_client_id(
    db: Session, profile_id: uuid.UUID, client_reminder_id: str | None
) -> GeneralReminder | None:
    """A reminder this client already created, if any (section 38)."""
    if not client_reminder_id:
        return None
    return db.execute(
        select(GeneralReminder).where(
            GeneralReminder.profile_id == profile_id,
            GeneralReminder.client_reminder_id == client_reminder_id,
        )
    ).scalar_one_or_none()


def list_reminders(
    db: Session, profile_id: uuid.UUID, *, active_only: bool = False
) -> list[GeneralReminder]:
    """This profile's reminders, soonest time of day first."""
    query = select(GeneralReminder).where(GeneralReminder.profile_id == profile_id)
    if active_only:
        query = query.where(GeneralReminder.status.in_(REMINDER_ACTIVE_STATUSES))
    return list(
        db.execute(
            query.order_by(
                GeneralReminder.time_of_day.asc(), GeneralReminder.created_at.asc()
            )
        )
        .scalars()
        .all()
    )


def active_reminders(db: Session, profile_id: uuid.UUID) -> list[GeneralReminder]:
    """Series that should still be producing occurrences."""
    return list_reminders(db, profile_id, active_only=True)


def get_occurrence(
    db: Session, profile_id: uuid.UUID, occurrence_id: uuid.UUID
) -> GeneralReminderOccurrence:
    """One occurrence of this profile's, scoped at both depths.

    The profile is part of the lookup even though the occurrence's own parent
    carries it, which is the convention every child table in this codebase
    follows: the authorization chain is complete at every depth, and no route
    loads a row and works out whose it is afterwards.
    """
    row = db.execute(
        select(GeneralReminderOccurrence)
        .where(
            GeneralReminderOccurrence.id == occurrence_id,
            GeneralReminderOccurrence.profile_id == profile_id,
        )
        .options(selectinload(GeneralReminderOccurrence.reminder))
    ).scalar_one_or_none()
    if row is None:
        raise OccurrenceNotFoundError("Not found.")
    return row


def list_occurrences(
    db: Session,
    profile_id: uuid.UUID,
    *,
    from_date: date | None = None,
    to_date: date | None = None,
    reminder_id: uuid.UUID | None = None,
    statuses: tuple[str, ...] | None = None,
    limit: int | None = None,
) -> list[GeneralReminderOccurrence]:
    """Occurrences in a range of the user's own local days, earliest first."""
    query = select(GeneralReminderOccurrence).where(
        GeneralReminderOccurrence.profile_id == profile_id
    )
    if from_date is not None:
        query = query.where(GeneralReminderOccurrence.local_date >= from_date)
    if to_date is not None:
        query = query.where(GeneralReminderOccurrence.local_date <= to_date)
    if reminder_id is not None:
        query = query.where(GeneralReminderOccurrence.reminder_id == reminder_id)
    if statuses is not None:
        query = query.where(GeneralReminderOccurrence.status.in_(statuses))
    query = query.order_by(GeneralReminderOccurrence.scheduled_for.asc()).options(
        selectinload(GeneralReminderOccurrence.reminder)
    )
    if limit is not None:
        query = query.limit(limit)
    return list(db.execute(query).scalars().all())


def due_at(occurrence: GeneralReminderOccurrence) -> datetime:
    """When this occurrence is actually waiting for -- its snooze, if it has one."""
    if occurrence.status == "snoozed" and occurrence.snoozed_until is not None:
        return occurrence.snoozed_until
    return occurrence.scheduled_for


def window(occurrence: GeneralReminderOccurrence, now: datetime) -> str:
    """Where it sits relative to now: upcoming, due, overdue or completed.

    The same four words a dose uses, and the same derivation: a value meaning
    "right now" is stale the instant it is written, so nothing stores this.
    """
    if occurrence.status in ("completed", "dismissed", "cancelled"):
        return "completed"
    if occurrence.status == "missed":
        return "overdue"
    moment = due_at(occurrence)
    if now < moment - recurrence.DUE_LEAD:
        return "upcoming"
    if now <= moment + recurrence.MISS_AFTER:
        return "due"
    return "overdue"


def due_occurrences(
    db: Session, profile_id: uuid.UUID, now: datetime
) -> list[GeneralReminderOccurrence]:
    """Occurrences that are ``due`` right now, for Today and for the robot."""
    candidates = list_occurrences(
        db,
        profile_id,
        statuses=REMINDER_OCCURRENCE_OPEN_STATUSES,
    )
    return [row for row in candidates if window(row, now) in ("due", "overdue")]


# --- generation -------------------------------------------------------------


def generate_for_reminder(
    db: Session,
    reminder: GeneralReminder,
    now: datetime,
    horizon_days: int = recurrence.GENERATION_HORIZON_DAYS,
) -> list[GeneralReminderOccurrence]:
    """Tops this reminder's window up to ``horizon_days`` ahead.

    Idempotent, and safe to call on every read: a moment that already has a row
    -- answered, snoozed or merely waiting -- is left exactly as it is. Nothing
    before ``now`` is created, so a reminder created at ten in the morning does
    not retroactively produce, let alone miss, this morning's eight o'clock.
    """
    if reminder.status not in REMINDER_ACTIVE_STATUSES:
        return []

    pattern = pattern_for(reminder)
    zone = zone_for(reminder.timezone)
    today = recurrence.local_today(zone, now)
    horizon = today + timedelta(days=horizon_days)

    existing = {
        instant
        for (instant,) in db.execute(
            select(GeneralReminderOccurrence.scheduled_for).where(
                GeneralReminderOccurrence.reminder_id == reminder.id,
                GeneralReminderOccurrence.scheduled_for >= now,
            )
        ).all()
    }

    created: list[GeneralReminderOccurrence] = []
    for moment in recurrence.occurrences(pattern, today, horizon):
        if moment.scheduled_for <= now or moment.scheduled_for in existing:
            continue
        row = GeneralReminderOccurrence(
            reminder_id=reminder.id,
            profile_id=reminder.profile_id,
            scheduled_for=moment.scheduled_for,
            local_date=moment.local_date,
            status="scheduled",
        )
        db.add(row)
        created.append(row)
        existing.add(moment.scheduled_for)
        if not pattern.repeats:
            # A one-off produces exactly one, however wide the window is.
            break

    return created


def withdraw_future(db: Session, reminder: GeneralReminder, now: datetime) -> int:
    """Removes a reminder's future occurrences without touching its history.

    The same two cases PRD 5 distinguishes, for the same reason: an occurrence
    nobody has touched is deleted, because nothing ever happened at it; one the
    person snoozed is marked ``cancelled`` instead, because quietly deleting it
    would erase something they did.
    """
    future = (
        db.execute(
            select(GeneralReminderOccurrence).where(
                GeneralReminderOccurrence.reminder_id == reminder.id,
                GeneralReminderOccurrence.scheduled_for > now,
                GeneralReminderOccurrence.status.in_(REMINDER_OCCURRENCE_OPEN_STATUSES),
            )
        )
        .scalars()
        .all()
    )
    affected = 0
    for row in future:
        if row.status == "scheduled" and row.snooze_count == 0:
            db.delete(row)
        else:
            row.status = "cancelled"
        affected += 1
    if affected:
        _log("withdraw", affected)
    return affected


def regenerate(db: Session, reminder: GeneralReminder, now: datetime) -> None:
    """Rebuilds future occurrences after the pattern changed.

    Withdraw then generate, in that order and in one transaction, so there is
    no moment at which the old pattern and the new one are both live.
    """
    withdraw_future(db, reminder, now)
    db.flush()
    generate_for_reminder(db, reminder, now)


def mark_missed(db: Session, profile_id: uuid.UUID, now: datetime) -> int:
    """Turns unanswered past occurrences into ``missed`` after the grace period.

    A snoozed occurrence is measured from what it was snoozed *to*, not from
    when it was originally due -- otherwise snoozing for an hour would mark it
    missed the moment the hour was up.

    This records what happened and nothing else. No advice follows, nothing is
    escalated, and nobody is told.
    """
    waiting = (
        db.execute(
            select(GeneralReminderOccurrence).where(
                GeneralReminderOccurrence.profile_id == profile_id,
                GeneralReminderOccurrence.status.in_(REMINDER_OCCURRENCE_OPEN_STATUSES),
                GeneralReminderOccurrence.scheduled_for <= now,
            )
        )
        .scalars()
        .all()
    )
    changed = 0
    for row in waiting:
        if due_at(row) + recurrence.MISS_AFTER < now:
            row.status = "missed"
            changed += 1
    if changed:
        _log("missed", changed)
    return changed


def _finish_one_offs(db: Session, profile_id: uuid.UUID) -> int:
    """Marks a one-off series ``completed`` once its occurrence is answered.

    Without this, a reminder for last Tuesday sits in the list saying "On"
    forever, which is a small untruth that makes the whole list less worth
    reading.
    """
    rows = (
        db.execute(
            select(GeneralReminder)
            .where(
                GeneralReminder.profile_id == profile_id,
                GeneralReminder.recurrence == "one_time",
                GeneralReminder.status.in_(REMINDER_ACTIVE_STATUSES),
            )
            .options(selectinload(GeneralReminder.occurrences))
        )
        .scalars()
        .all()
    )
    changed = 0
    for reminder in rows:
        occurrences = reminder.occurrences
        if not occurrences:
            continue
        if any(row.status in REMINDER_OCCURRENCE_OPEN_STATUSES for row in occurrences):
            continue
        reminder.status = "completed"
        changed += 1
    return changed


def replenish(db: Session, profile_id: uuid.UUID, now: datetime) -> None:
    """Brings one profile's reminders up to date: new ones ahead, missed behind.

    Called at the top of every read of reminders and of Today, which is what
    lets PRD 12 work with no background worker at all. ``scripts/
    productivity_maintenance.py`` calls the same function for every profile so
    a phone that is never opened still has its occurrences recorded, but
    nothing depends on that job having run (section 63).
    """
    for reminder in active_reminders(db, profile_id):
        generate_for_reminder(db, reminder, now)
    mark_missed(db, profile_id, now)
    _finish_one_offs(db, profile_id)
    db.commit()


# --- writing ----------------------------------------------------------------


@dataclass(frozen=True)
class ReminderInput:
    """What a client may say when creating a reminder."""

    title: str
    time_of_day: time
    start_date: date
    recurrence: str = "one_time"
    timezone: str = "UTC"
    body: str | None = None
    end_date: date | None = None
    weekdays: list[int] | None = None
    day_of_month: int | None = None
    notification_enabled: bool = True
    client_reminder_id: str | None = None
    source: str = "user"


def _check(
    *,
    rule: str,
    weekdays: list[int] | None,
    day_of_month: int | None,
    start_date: date,
    end_date: date | None,
    timezone: str,
) -> None:
    """Refuses a pattern that cannot mean anything.

    Every one of these is also a database CHECK. Both exist on purpose: the
    constraint is what makes a bad row impossible, and this is what makes the
    refusal a sentence a client can act on rather than an integrity error.
    """
    if rule not in REMINDER_RECURRENCES:
        raise InvalidReminderError("That is not a repeat Nura has.")
    zone_for(timezone)
    if end_date is not None and end_date < start_date:
        raise InvalidReminderError("The end date is before the start date.")
    if rule in REMINDER_RECURRENCES_WITH_WEEKDAYS:
        if not weekdays:
            raise InvalidReminderError("Choose at least one day.")
        if any(day < 0 or day > 6 for day in weekdays):
            raise InvalidReminderError("That is not a day of the week.")
        if rule == "weekly" and len(set(weekdays)) != 1:
            raise InvalidReminderError("A weekly reminder is on one day.")
    elif weekdays:
        raise InvalidReminderError("That repeat does not use days of the week.")
    if rule == "monthly":
        if day_of_month is None or not 1 <= day_of_month <= 31:
            raise InvalidReminderError("Choose a day of the month.")
    elif day_of_month is not None:
        raise InvalidReminderError("That repeat does not use a day of the month.")


def create_reminder(
    db: Session, profile_id: uuid.UUID, data: ReminderInput, now: datetime
) -> GeneralReminder:
    """Adds a reminder and generates its first occurrences (sections 7 and 8)."""
    if not data.title.strip():
        raise InvalidReminderError("A reminder needs a title.")
    _check(
        rule=data.recurrence,
        weekdays=data.weekdays,
        day_of_month=data.day_of_month,
        start_date=data.start_date,
        end_date=data.end_date,
        timezone=data.timezone,
    )
    open_count = len(active_reminders(db, profile_id))
    if open_count >= MAX_ACTIVE_REMINDERS:
        raise TooManyRemindersError("There are too many reminders set up already.")

    reminder = GeneralReminder(
        profile_id=profile_id,
        title=data.title.strip(),
        body=(data.body or None),
        recurrence=data.recurrence,
        timezone=data.timezone,
        start_date=data.start_date,
        end_date=data.end_date,
        time_of_day=data.time_of_day,
        weekdays=sorted(set(data.weekdays)) if data.weekdays else None,
        day_of_month=data.day_of_month,
        status="active",
        notification_enabled=data.notification_enabled,
        source=data.source,
        client_reminder_id=data.client_reminder_id,
    )
    db.add(reminder)
    db.flush()
    generate_for_reminder(db, reminder, now)
    db.commit()
    db.refresh(reminder)
    _log("create")
    return reminder


def update_reminder(
    db: Session, reminder: GeneralReminder, fields: dict[str, Any], now: datetime
) -> GeneralReminder:
    """Edits a reminder, rebuilding its future occurrences if the pattern moved.

    Only the *future* is rebuilt. An occurrence somebody already answered keeps
    its status and its time forever, which is PRD 5's rule about history and
    applies just as much to "ring the bank" as to a tablet.
    """
    unknown = set(fields) - EDITABLE_FIELDS
    if unknown:
        raise InvalidReminderError(f"A reminder has no {sorted(unknown)[0]}.")

    merged = {
        "recurrence": reminder.recurrence,
        "weekdays": reminder.weekdays,
        "day_of_month": reminder.day_of_month,
        "start_date": reminder.start_date,
        "end_date": reminder.end_date,
        "timezone": reminder.timezone,
        **fields,
    }
    _check(
        rule=str(merged["recurrence"]),
        weekdays=merged["weekdays"],
        day_of_month=merged["day_of_month"],
        start_date=merged["start_date"],
        end_date=merged["end_date"],
        timezone=str(merged["timezone"]),
    )

    if "title" in fields:
        title = str(fields["title"] or "").strip()
        if not title:
            raise InvalidReminderError("A reminder needs a title.")
        reminder.title = title
    if "body" in fields:
        reminder.body = fields["body"] or None
    if "notification_enabled" in fields:
        reminder.notification_enabled = bool(fields["notification_enabled"])
    for key in (
        "recurrence",
        "timezone",
        "start_date",
        "end_date",
        "time_of_day",
        "day_of_month",
    ):
        if key in fields:
            setattr(reminder, key, fields[key])
    if "weekdays" in fields:
        value = fields["weekdays"]
        reminder.weekdays = sorted(set(value)) if value else None

    if PATTERN_FIELDS & set(fields):
        regenerate(db, reminder, now)
    db.commit()
    db.refresh(reminder)
    _log("update")
    return reminder


def set_paused(
    db: Session, reminder: GeneralReminder, *, paused: bool, now: datetime
) -> GeneralReminder:
    """Pausing stops the occurrences and keeps the series (section 7).

    Nothing infers why it was paused, and resuming generates forward from now
    rather than filling in the gap: a reminder nobody wanted last week is not
    a backlog to work through.
    """
    reminder.status = "paused" if paused else "active"
    reminder.paused_at = now if paused else None
    if paused:
        withdraw_future(db, reminder, now)
    else:
        generate_for_reminder(db, reminder, now)
    db.commit()
    db.refresh(reminder)
    _log("paused" if paused else "resumed")
    return reminder


def cancel_reminder(
    db: Session, reminder: GeneralReminder, now: datetime
) -> GeneralReminder:
    """Stops a reminder for good, keeping what it already produced."""
    withdraw_future(db, reminder, now)
    reminder.status = "cancelled"
    db.commit()
    db.refresh(reminder)
    _log("cancel")
    return reminder


def delete_reminder(db: Session, reminder: GeneralReminder) -> None:
    """Removes a reminder and its occurrences. For one entered by mistake."""
    db.delete(reminder)
    db.commit()
    _log("delete")


# --- the three actions ------------------------------------------------------


@dataclass(frozen=True)
class OccurrenceResult:
    """What an action did.

    ``applied`` is False when the occurrence was already in the state being
    asked for, or when an older queued action arrived after a newer one. Either
    way the caller gets the stored row back and converges on it rather than
    retrying (sections 37 and 40).
    """

    occurrence: GeneralReminderOccurrence
    applied: bool


#: States an answered occurrence is in. A queued action never overwrites one
#: of these with an older decision.
ANSWERED = ("completed", "dismissed")


def _stale(occurrence: GeneralReminderOccurrence, action_at: datetime | None) -> bool:
    """Whether a submission is older than what is already recorded."""
    if action_at is None or occurrence.action_at is None:
        return False
    return action_at < occurrence.action_at


def _record(
    db: Session,
    occurrence: GeneralReminderOccurrence,
    status: str,
    now: datetime,
    *,
    action_at: datetime | None,
) -> OccurrenceResult:
    if occurrence.status == "cancelled":
        raise OccurrenceNotActionableError("This reminder is no longer scheduled.")
    if _stale(occurrence, action_at):
        return OccurrenceResult(occurrence=occurrence, applied=False)
    if occurrence.status == status:
        return OccurrenceResult(occurrence=occurrence, applied=False)

    occurrence.status = status
    occurrence.action_at = action_at or now
    occurrence.snoozed_until = None
    db.commit()
    db.refresh(occurrence)
    _log(status)
    return OccurrenceResult(occurrence=occurrence, applied=True)


def record_completed(
    db: Session,
    occurrence: GeneralReminderOccurrence,
    now: datetime,
    *,
    action_at: datetime | None = None,
) -> OccurrenceResult:
    """Done (section 8). Sends twice, happens once."""
    return _record(db, occurrence, "completed", now, action_at=action_at)


def record_dismissed(
    db: Session,
    occurrence: GeneralReminderOccurrence,
    now: datetime,
    *,
    action_at: datetime | None = None,
) -> OccurrenceResult:
    """Dismiss (section 8). Not Done: seen, and not being acted on."""
    return _record(db, occurrence, "dismissed", now, action_at=action_at)


def record_snoozed(
    db: Session,
    occurrence: GeneralReminderOccurrence,
    now: datetime,
    *,
    minutes: int,
) -> OccurrenceResult:
    """Puts a reminder off for a while, leaving it unanswered (section 8).

    Done and Dismiss stay available throughout, including after the snooze
    limit is reached -- the cap stops endless rapid snoozing without ever
    taking away the two buttons that finish the thing.
    """
    if minutes not in SNOOZE_OPTIONS_MINUTES:
        raise InvalidSnoozeError("That is not a snooze Nura offers.")
    if occurrence.status in ("completed", "dismissed", "cancelled"):
        raise OccurrenceNotActionableError("This reminder has already been answered.")
    if occurrence.snooze_count >= MAX_REMINDER_SNOOZES:
        raise SnoozeLimitError("This reminder has already been put off a few times.")

    occurrence.status = "snoozed"
    occurrence.snoozed_until = now + timedelta(minutes=minutes)
    occurrence.snooze_count += 1
    db.commit()
    db.refresh(occurrence)
    _log("snoozed")
    return OccurrenceResult(occurrence=occurrence, applied=True)
