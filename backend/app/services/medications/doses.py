"""Dose generation, status transitions and the three actions.

(PRD 5, sections 12, 16-25, 33, 48, 49, 54, 63 and 70.)

This is the one place recurrence is worked out. Routes never compute a due
time, and neither does the app: both read the rows this module writes
(PRD 5, section 70).

**A reminder is a wall-clock time, not an instant.** "Eight in the morning"
means eight where the person is, in March and in July alike. So a schedule
carries an IANA zone, and generation resolves *local date + local time in that
zone* to a UTC instant. The alternative -- storing an offset -- is wrong twice
a year, in the direction of either a missed dose or a doubled one.

**Daylight saving is decided, not left to chance** (PRD 5, section 12):

  - A time that does not exist on a spring-forward day (01:30 where the
    clocks jump 01:00 to 02:00) resolves through the pre-transition offset:
    the instant it would have been had the clocks not moved, which reads an
    hour later on the clock. One dose, never zero.
  - A time that happens twice on an autumn day resolves to the *first*
    occurrence. One dose, never two.
  - Changing a schedule's zone regenerates its future doses rather than
    reinterpreting the existing ones, so travelling cannot duplicate a day.

**Generation only ever looks forward.** A schedule created at 10am does not
retroactively produce -- let alone miss -- this morning's 8am, because there
was nothing to remind anybody about at 8am (PRD 5, section 22).

**One row per moment, owned by the user.** Taken, Snooze and Skip update that
row; they never append an event beside it. That is what makes a retried
request harmless and what stops a robot's confirmation from becoming a second
entry in somebody's history (PRD 5, sections 48 and 49).
"""

import logging
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import MedicationDose, MedicationSchedule
from app.services.errors import DomainError, NotFoundError
from app.services.medications import supply as supply_service

logger = logging.getLogger(__name__)

#: How far ahead concrete doses are created (PRD 5, section 22). Long enough
#: that a phone which has been offline for a week still has reminders left to
#: fire, short enough that a schedule edit does not have to rewrite months.
GENERATION_HORIZON_DAYS = 14

#: How long after its due time a dose waits before it counts as missed
#: (PRD 5, section 23). Deliberately generous: someone who takes a tablet with
#: breakfast an hour late has not missed it, and Nura calling it missed would
#: be both wrong and unkind. It is a bookkeeping threshold and nothing more --
#: no advice follows from it (section 57).
GRACE_PERIOD = timedelta(hours=2)

#: How early a dose starts reading as "due" rather than "upcoming"
#: (PRD 5, section 54).
DUE_LEAD = timedelta(minutes=30)

#: The snooze durations offered (PRD 5, section 18).
SNOOZE_OPTIONS_MINUTES: tuple[int, ...] = (10, 30, 60)

#: A dose can be put off this many times. PRD 5 section 18 asks that endless
#: rapid snoozing be avoided; a cap does that without ever taking the Taken
#: and Skip buttons away, which stay available however many times it is
#: snoozed.
MAX_SNOOZES = 3

#: The longest history window a client may ask for (PRD 5, section 26).
HISTORY_MAX_DAYS = 365


class DoseNotFoundError(NotFoundError):
    """No such dose for this profile. Same answer as one owned by somebody else."""

    code = "dose_not_found"


class DoseNotActionableError(DomainError):
    """The dose is in a state where this action has no meaning."""

    status_code = 409
    code = "dose_not_actionable"


class SnoozeLimitError(DomainError):
    """This dose has been put off as many times as Nura allows."""

    status_code = 409
    code = "snooze_limit_reached"


class InvalidSnoozeError(DomainError):
    status_code = 422
    code = "invalid_snooze_duration"


class UnknownTimezoneError(DomainError):
    """A zone name the IANA database does not have."""

    status_code = 422
    code = "unknown_timezone"


# --- time zones -------------------------------------------------------------


def zone_for(name: str) -> ZoneInfo:
    """The named zone, or a refusal a client can act on."""
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as error:
        raise UnknownTimezoneError(f"{name} is not a known time zone.") from error


def occurrence_instant(on_date: date, wall_time: time, zone: ZoneInfo) -> datetime:
    """The UTC instant of a wall-clock time on a local date.

    ``fold=0`` is the whole daylight-saving policy in one keyword. On an
    ambiguous autumn hour it picks the earlier of the two occurrences; on a
    spring hour that never happens it uses the offset from before the jump,
    so the reminder lands the same elapsed time later and reads an hour on
    from the chosen time. Either way exactly one instant comes back, which is
    what stops a doubled or a vanished dose.
    """
    local = datetime.combine(on_date, wall_time).replace(tzinfo=zone, fold=0)
    return local.astimezone(UTC)


def local_today(zone: ZoneInfo, now: datetime) -> date:
    """The calendar date it is *there* right now."""
    return now.astimezone(zone).date()


# --- generation -------------------------------------------------------------


@dataclass(frozen=True)
class Occurrence:
    """One moment a schedule says a dose is due."""

    local_date: date
    scheduled_for: datetime


def occurrences(
    schedule: MedicationSchedule, from_date: date, to_date: date
) -> Iterator[Occurrence]:
    """Every moment this schedule produces between two local dates, inclusive.

    Pure: it reads the schedule and returns moments, touching no database and
    no clock. That is what makes the recurrence rules testable on their own,
    including the two daylight-saving days a year that are easy to get wrong
    and impossible to notice.
    """
    zone = zone_for(schedule.timezone)
    start = max(from_date, schedule.start_date)
    end = to_date if schedule.end_date is None else min(to_date, schedule.end_date)

    current = start
    while current <= end:
        for entry in schedule.times:
            # A specific-days schedule is defined entirely by its weekday
            # rows; one with none produces nothing, which is correct -- "on no
            # days" is no reminders. A daily schedule has no weekdays at all,
            # so every time applies to every date.
            if schedule.schedule_type == "specific_days" and (
                entry.weekday is None or entry.weekday != current.weekday()
            ):
                continue
            yield Occurrence(
                local_date=current,
                scheduled_for=occurrence_instant(current, entry.time_of_day, zone),
            )
        current += timedelta(days=1)


def generate_for_schedule(
    db: Session,
    schedule: MedicationSchedule,
    now: datetime,
    horizon_days: int = GENERATION_HORIZON_DAYS,
) -> list[MedicationDose]:
    """Tops the schedule's window up to ``horizon_days`` ahead.

    Idempotent, and safe to call on every read: a moment that already has a
    dose row -- taken, skipped, snoozed or merely waiting -- is left exactly as
    it is. Nothing before ``now`` is created, so a schedule can never invent
    history it was not around for (PRD 5, section 22).
    """
    if not schedule.is_active:
        return []

    zone = zone_for(schedule.timezone)
    today = local_today(zone, now)
    horizon = today + timedelta(days=horizon_days)

    existing = {
        instant
        for (instant,) in db.execute(
            select(MedicationDose.scheduled_for).where(
                MedicationDose.schedule_id == schedule.id,
                MedicationDose.scheduled_for >= now,
            )
        ).all()
    }

    created: list[MedicationDose] = []
    for occurrence in occurrences(schedule, today, horizon):
        if occurrence.scheduled_for <= now or occurrence.scheduled_for in existing:
            continue
        dose = MedicationDose(
            profile_id=schedule.profile_id,
            medication_id=schedule.medication_id,
            schedule_id=schedule.id,
            scheduled_for=occurrence.scheduled_for,
            local_date=occurrence.local_date,
            status="scheduled",
        )
        db.add(dose)
        created.append(dose)
        existing.add(occurrence.scheduled_for)

    return created


def active_schedules(db: Session, profile_id: uuid.UUID) -> list[MedicationSchedule]:
    """Schedules that should still be producing doses.

    A paused schedule is excluded, and so is one whose medication the user has
    marked as no longer taken -- an inactive medication stops generating
    without the schedule being deleted, so turning it back on restores the
    reminders as they were (PRD 5, section 38).
    """
    from app.models import Medication

    return list(
        db.execute(
            select(MedicationSchedule)
            .join(Medication, Medication.id == MedicationSchedule.medication_id)
            .where(
                MedicationSchedule.profile_id == profile_id,
                MedicationSchedule.is_active.is_(True),
                Medication.is_active.is_(True),
            )
            .options(selectinload(MedicationSchedule.times))
        )
        .scalars()
        .all()
    )


def replenish(db: Session, profile_id: uuid.UUID, now: datetime) -> None:
    """Brings one profile's doses up to date: new ones ahead, missed ones behind.

    Called at the top of every read of doses, Today and adherence, which is
    what lets PRD 5 work with no background worker at all. A cron job can call
    the same function for every profile (``scripts/medication_maintenance.py``)
    so a phone that is never opened still has its missed doses recorded, but
    nothing depends on that job having run (PRD 5, section 71).
    """
    for schedule in active_schedules(db, profile_id):
        generate_for_schedule(db, schedule, now)
    mark_missed(db, profile_id, now)
    db.commit()


def mark_missed(db: Session, profile_id: uuid.UUID, now: datetime) -> int:
    """Turns unrecorded past doses into ``missed`` once the grace period is up.

    A snoozed dose is measured from when it was snoozed *to*, not from when it
    was originally due -- otherwise snoozing a dose for an hour would mark it
    missed the moment the hour was up.

    This only ever records what happened. It produces no advice about what to
    do next, which is PRD 5 section 57's line and not one Nura goes near.
    """
    waiting = (
        db.execute(
            select(MedicationDose).where(
                MedicationDose.profile_id == profile_id,
                MedicationDose.status.in_(("scheduled", "snoozed")),
                MedicationDose.scheduled_for <= now,
            )
        )
        .scalars()
        .all()
    )

    changed = 0
    for dose in waiting:
        if due_at(dose) + GRACE_PERIOD < now:
            dose.status = "missed"
            changed += 1

    if changed:
        logger.info("medication.dose.missed success (%d)", changed)
    return changed


def withdraw_future(db: Session, schedule: MedicationSchedule, now: datetime) -> int:
    """Removes a schedule's future doses without touching its history.

    The two cases are treated differently on purpose (PRD 5, sections 36
    and 39):

      - A future dose nobody has touched is deleted. No history is lost,
        because nothing ever happened at it.
      - A future dose the user has snoozed is marked ``cancelled`` instead.
        They interacted with it, and quietly deleting that would be erasing
        something they did. ``cancelled`` is excluded from adherence, so it
        counts against nobody.

    Anything already taken, skipped or missed is never touched by this.
    """
    future = (
        db.execute(
            select(MedicationDose).where(
                MedicationDose.schedule_id == schedule.id,
                MedicationDose.scheduled_for > now,
                MedicationDose.status.in_(("scheduled", "snoozed")),
            )
        )
        .scalars()
        .all()
    )

    affected = 0
    for dose in future:
        if dose.status == "scheduled" and dose.snooze_count == 0:
            db.delete(dose)
        else:
            dose.status = "cancelled"
        affected += 1

    if affected:
        logger.info("medication.dose.withdraw success (%d)", affected)
    return affected


def regenerate(db: Session, schedule: MedicationSchedule, now: datetime) -> None:
    """Rebuilds future doses after a schedule changed (PRD 5, section 36).

    Withdraw then generate, in that order and in one transaction, so there is
    no moment at which the old pattern and the new one are both live.
    """
    withdraw_future(db, schedule, now)
    db.flush()
    generate_for_schedule(db, schedule, now)


# --- reading ----------------------------------------------------------------


def due_at(dose: MedicationDose) -> datetime:
    """When this dose is actually waiting for -- its snooze, if it has one."""
    if dose.status == "snoozed" and dose.snoozed_until is not None:
        return dose.snoozed_until
    return dose.scheduled_for


def window(dose: MedicationDose, now: datetime) -> str:
    """Where the dose sits relative to now (PRD 5, section 54).

    Derived on every read rather than stored, for the same reason a robot's
    connection status is: a value meaning "right now" is stale the instant it
    is written.
    """
    if dose.status in ("taken", "skipped", "cancelled"):
        return "completed"
    if dose.status == "missed":
        return "overdue"

    moment = due_at(dose)
    if now < moment - DUE_LEAD:
        return "upcoming"
    if now <= moment + GRACE_PERIOD:
        return "due"
    return "overdue"


def was_late(dose: MedicationDose) -> bool:
    """Whether a taken dose was recorded after its grace period (PRD 5, s25).

    Derived, never stored, and used only for history. It is a fact about a
    time, not a judgement: nothing in the app scores it, and no copy anywhere
    scolds about it (PRD 5, section 24).
    """
    if dose.status != "taken" or dose.action_at is None:
        return False
    return dose.action_at > dose.scheduled_for + GRACE_PERIOD


def get_dose(db: Session, profile_id: uuid.UUID, dose_id: uuid.UUID) -> MedicationDose:
    """One dose of this profile's, or a 404 that confirms nothing.

    The profile is part of the lookup rather than checked afterwards, so there
    is no path that loads a dose first and authorizes it second
    (PRD 5, section 52).
    """
    dose = db.execute(
        select(MedicationDose)
        .where(MedicationDose.id == dose_id, MedicationDose.profile_id == profile_id)
        .options(selectinload(MedicationDose.medication))
    ).scalar_one_or_none()
    if dose is None:
        raise DoseNotFoundError("Not found.")
    return dose


def list_doses(
    db: Session,
    profile_id: uuid.UUID,
    *,
    from_date: date,
    to_date: date,
    medication_id: uuid.UUID | None = None,
    statuses: tuple[str, ...] | None = None,
) -> list[MedicationDose]:
    """Doses in a range of the user's own local days, earliest first.

    Filtered on ``local_date`` rather than on the UTC instant, so "the last 7
    days" means seven of the user's days and a late-evening dose does not fall
    into tomorrow.
    """
    query = select(MedicationDose).where(
        MedicationDose.profile_id == profile_id,
        MedicationDose.local_date >= from_date,
        MedicationDose.local_date <= to_date,
    )
    if medication_id is not None:
        query = query.where(MedicationDose.medication_id == medication_id)
    if statuses is not None:
        query = query.where(MedicationDose.status.in_(statuses))

    return list(
        db.execute(
            query.order_by(MedicationDose.scheduled_for.asc()).options(
                selectinload(MedicationDose.medication)
            )
        )
        .scalars()
        .all()
    )


# --- actions ----------------------------------------------------------------


@dataclass(frozen=True)
class DoseActionResult:
    """What an action did.

    ``applied`` is False when the dose was already in the state being asked
    for, or when a robot's confirmation arrived after the person had already
    recorded something themselves. Either way the caller gets the stored dose
    back and a client converges on it rather than retrying (PRD 5, s48, s49).
    """

    dose: MedicationDose
    applied: bool
    #: What is left after a supply decrement, when tracking is on.
    supply_remaining: int | None = None
    #: True when the remaining count has reached the user's own threshold.
    low_supply: bool = False


#: States a completed dose is in. A source other than the app never overwrites
#: one of these: the person's own record wins over a robot that thinks it
#: heard something (PRD 5, sections 46 and 49).
COMPLETED = ("taken", "skipped")


def _log(action: str) -> None:
    """``medication.dose.taken success`` -- and never a medication name.

    PRD 5 sections 58 and 59: no medication name, dose, skip reason text or
    adherence figure appears in a log line, ever.
    """
    logger.info("medication.dose.%s success", action)


def _stale(dose: MedicationDose, action_at: datetime | None) -> bool:
    """Whether a submission is older than what is already recorded.

    An offline action may be hours old by the time it syncs. The rule is the
    same one the daily check-in uses: the most recent explicit user action
    wins, so a queued Taken cannot overwrite a Skip the user made afterwards
    on another device (PRD 5, section 63).
    """
    if action_at is None or dose.action_at is None:
        return False
    return action_at < dose.action_at


def _clear_action_fields(dose: MedicationDose) -> None:
    dose.skip_reason_code = None
    dose.skip_reason_text = None
    dose.snoozed_until = None


def record_taken(
    db: Session,
    dose: MedicationDose,
    now: datetime,
    *,
    source: str = "app",
    action_at: datetime | None = None,
) -> DoseActionResult:
    """Marks a dose as taken, once.

    Sending it twice leaves one taken dose and decrements supply once, because
    this sets a state rather than appending an event (PRD 5, section 48).
    Taking a dose after its grace period keeps the same row and records when it
    actually happened -- there is no second, "late" dose (section 25).
    """
    if dose.status == "cancelled":
        raise DoseNotActionableError("This dose is no longer scheduled.")
    if dose.status == "taken":
        return DoseActionResult(dose=dose, applied=False)
    if source != "app" and dose.status in COMPLETED:
        # A robot confirming a dose the person already recorded is agreement,
        # not a correction. Nothing changes and nothing errors.
        return DoseActionResult(dose=dose, applied=False)
    if _stale(dose, action_at):
        return DoseActionResult(dose=dose, applied=False)

    dose.status = "taken"
    dose.action_at = action_at or now
    dose.source = source
    _clear_action_fields(dose)

    outcome = supply_service.consume_one(db, dose.medication_id)
    db.commit()
    db.refresh(dose)
    _log("taken")
    return DoseActionResult(
        dose=dose,
        applied=True,
        supply_remaining=outcome.remaining,
        low_supply=outcome.low,
    )


def record_skipped(
    db: Session,
    dose: MedicationDose,
    now: datetime,
    *,
    source: str = "app",
    reason_code: str | None = None,
    reason_text: str | None = None,
    action_at: datetime | None = None,
) -> DoseActionResult:
    """Records that a dose was not taken, with an optional reason.

    The reason is stored exactly as chosen and never interpreted: no reason
    changes what Nura says, escalates anything, or produces advice
    (PRD 5, sections 19 and 57). Supply is not decremented -- a skipped dose
    is still in the packet (section 33).

    Correcting a taken dose to skipped puts one back on the count, which is
    best-effort: it can only do that when tracking is on now, and the count
    stays correctable by hand either way.
    """
    if dose.status == "cancelled":
        raise DoseNotActionableError("This dose is no longer scheduled.")
    if source != "app" and dose.status in COMPLETED:
        return DoseActionResult(dose=dose, applied=False)
    if _stale(dose, action_at):
        return DoseActionResult(dose=dose, applied=False)

    was_taken = dose.status == "taken"
    unchanged = (
        dose.status == "skipped"
        and dose.skip_reason_code == (reason_code or "none")
        and dose.skip_reason_text == reason_text
    )
    if unchanged:
        return DoseActionResult(dose=dose, applied=False)

    dose.status = "skipped"
    dose.action_at = action_at or now
    dose.source = source
    dose.snoozed_until = None
    dose.skip_reason_code = reason_code or "none"
    dose.skip_reason_text = reason_text

    remaining = None
    if was_taken:
        remaining = supply_service.return_one(db, dose.medication_id)

    db.commit()
    db.refresh(dose)
    _log("skipped")
    return DoseActionResult(dose=dose, applied=True, supply_remaining=remaining)


def record_snoozed(
    db: Session,
    dose: MedicationDose,
    now: datetime,
    *,
    minutes: int,
    source: str = "app",
) -> DoseActionResult:
    """Puts a dose off for a while, leaving it incomplete (PRD 5, section 18).

    The snooze is recorded on the dose -- when it is waiting for now, and how
    many times it has been put off -- so the reminder can be rescheduled and
    the dose still counts as unrecorded. Taken and Skip stay available
    throughout, including after the snooze limit is reached.
    """
    if minutes not in SNOOZE_OPTIONS_MINUTES:
        raise InvalidSnoozeError("That is not a snooze Nura offers.")
    if dose.status in ("taken", "skipped", "cancelled"):
        raise DoseNotActionableError("This dose has already been recorded.")
    if dose.snooze_count >= MAX_SNOOZES:
        raise SnoozeLimitError("This dose has already been snoozed a few times.")

    dose.status = "snoozed"
    dose.snoozed_until = now + timedelta(minutes=minutes)
    dose.snooze_count += 1
    dose.source = source
    db.commit()
    db.refresh(dose)
    _log("snoozed")
    return DoseActionResult(dose=dose, applied=True)
