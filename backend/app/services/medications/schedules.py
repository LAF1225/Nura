"""Medication schedules: what they are allowed to be, and what changing one does.

(PRD 5, sections 8, 9, 11, 36-39 and 52.)

A schedule is "remind me about this medication, at these times, in this zone,
between these dates, unless it is paused". Everything harder than that is out
of scope on purpose: tapering, sliding scales, dose calculation and PRN
interpretation all belong to a clinician, not to a reminder app
(PRD 5, section 10).

The rule that shapes this whole module: **editing the future never edits the
past.** Every write here ends by rebuilding doses from now forward, and none
of them can reach a dose that has already been recorded (PRD 5, section 36).
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import date, datetime, time

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Medication, MedicationSchedule, MedicationScheduleTime
from app.services.errors import DomainError, NotFoundError
from app.services.medications import doses as dose_service

logger = logging.getLogger(__name__)

#: More reminder times than any real medication needs, and few enough that one
#: schedule cannot be turned into a thousand notifications.
MAX_TIMES_PER_SCHEDULE = 12


class ScheduleNotFoundError(NotFoundError):
    """No such schedule for this profile."""

    code = "schedule_not_found"


class InvalidScheduleError(DomainError):
    """The schedule as described could not produce sensible reminders."""

    status_code = 422
    code = "invalid_schedule"


class MedicationNotFoundError(NotFoundError):
    """The medication does not exist, or belongs to another profile."""

    code = "medication_not_found"


@dataclass(frozen=True)
class TimeInput:
    """One reminder time as a client describes it."""

    time_of_day: time
    #: 0 = Monday. Null on a daily schedule.
    weekday: int | None = None


def get_medication(
    db: Session, profile_id: uuid.UUID, medication_id: uuid.UUID
) -> Medication:
    """A medication of this profile's, or a 404 (PRD 5, section 52).

    A schedule can only ever be attached through here, so "the medication
    belongs to the profile" is checked in one place rather than at four call
    sites.
    """
    medication = db.execute(
        select(Medication).where(
            Medication.id == medication_id, Medication.profile_id == profile_id
        )
    ).scalar_one_or_none()
    if medication is None:
        raise MedicationNotFoundError("Not found.")
    return medication


def validate_times(schedule_type: str, times: list[TimeInput]) -> list[TimeInput]:
    """Checks that the times make sense for the pattern they belong to.

    The two patterns have opposite requirements, and letting them blur would
    produce schedules that silently generate nothing: a daily schedule with a
    weekday on it, or a specific-days schedule with none.
    """
    if not times:
        raise InvalidScheduleError("Add at least one time.")
    if len(times) > MAX_TIMES_PER_SCHEDULE:
        raise InvalidScheduleError(
            f"A schedule can have at most {MAX_TIMES_PER_SCHEDULE} times."
        )

    for entry in times:
        if schedule_type == "daily" and entry.weekday is not None:
            raise InvalidScheduleError("An every-day schedule does not take weekdays.")
        if schedule_type == "specific_days":
            if entry.weekday is None:
                raise InvalidScheduleError("Choose which days this should repeat on.")
            if not 0 <= entry.weekday <= 6:
                raise InvalidScheduleError("That is not a day of the week.")

    seen = {(entry.time_of_day, entry.weekday) for entry in times}
    if len(seen) != len(times):
        # Without this the database would refuse it anyway, but as a 500. The
        # user's mistake deserves a sentence, not a stack trace.
        raise InvalidScheduleError("That time is already on this schedule.")

    return times


def _validate_range(start_date: date, end_date: date | None) -> None:
    if end_date is not None and end_date < start_date:
        raise InvalidScheduleError("The end date is before the start date.")


def _apply_times(schedule: MedicationSchedule, times: list[TimeInput]) -> None:
    """Replaces the schedule's times wholesale.

    A client sends the times it is displaying, exactly as the dashboard sends
    the card order: reconciling individual time rows would buy nothing and
    would add a way for the list on screen and the list stored to disagree.
    """
    schedule.times = [
        MedicationScheduleTime(time_of_day=entry.time_of_day, weekday=entry.weekday)
        for entry in times
    ]


# --- reading ----------------------------------------------------------------


def list_schedules(
    db: Session,
    profile_id: uuid.UUID,
    *,
    medication_id: uuid.UUID | None = None,
    active_only: bool = False,
) -> list[MedicationSchedule]:
    query = select(MedicationSchedule).where(MedicationSchedule.profile_id == profile_id)
    if medication_id is not None:
        query = query.where(MedicationSchedule.medication_id == medication_id)
    if active_only:
        query = query.where(MedicationSchedule.is_active.is_(True))

    return list(
        db.execute(
            query.order_by(MedicationSchedule.created_at.asc()).options(
                selectinload(MedicationSchedule.times),
                selectinload(MedicationSchedule.medication),
            )
        )
        .scalars()
        .all()
    )


def get_schedule(
    db: Session, profile_id: uuid.UUID, schedule_id: uuid.UUID
) -> MedicationSchedule:
    """One schedule of this profile's, or a 404 that reveals nothing."""
    schedule = db.execute(
        select(MedicationSchedule)
        .where(
            MedicationSchedule.id == schedule_id,
            MedicationSchedule.profile_id == profile_id,
        )
        .options(
            selectinload(MedicationSchedule.times),
            selectinload(MedicationSchedule.medication),
        )
    ).scalar_one_or_none()
    if schedule is None:
        raise ScheduleNotFoundError("Not found.")
    return schedule


# --- writing ----------------------------------------------------------------


def create_schedule(
    db: Session,
    profile_id: uuid.UUID,
    medication: Medication,
    *,
    schedule_type: str,
    timezone: str,
    start_date: date,
    end_date: date | None,
    times: list[TimeInput],
    now: datetime,
) -> MedicationSchedule:
    """Adds a schedule and fills its dose window straight away.

    Generating here rather than on the next read means the app can show the
    user their first upcoming dose immediately, and can schedule the local
    notification for it without a round trip in between.
    """
    dose_service.zone_for(timezone)
    validate_times(schedule_type, times)
    _validate_range(start_date, end_date)

    schedule = MedicationSchedule(
        profile_id=profile_id,
        medication_id=medication.id,
        schedule_type=schedule_type,
        timezone=timezone,
        start_date=start_date,
        end_date=end_date,
        is_active=True,
    )
    _apply_times(schedule, times)
    db.add(schedule)
    db.flush()

    dose_service.generate_for_schedule(db, schedule, now)
    db.commit()
    db.refresh(schedule)
    # Never the medication's name, and never the times (PRD 5, section 59).
    logger.info("medication.schedule.create success")
    return schedule


def update_schedule(
    db: Session,
    schedule: MedicationSchedule,
    now: datetime,
    *,
    schedule_type: str | None = None,
    timezone: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    end_date_set: bool = False,
    times: list[TimeInput] | None = None,
) -> MedicationSchedule:
    """Changes a schedule, then rebuilds its future doses (PRD 5, section 36).

    Past doses are untouched, including the ones from earlier today: someone
    who moved their reminder from 8am to 9am this afternoon still took this
    morning's 8am, and rewriting that would be falsifying their history.
    """
    if timezone is not None:
        dose_service.zone_for(timezone)
        schedule.timezone = timezone
    if schedule_type is not None:
        schedule.schedule_type = schedule_type
    if start_date is not None:
        schedule.start_date = start_date
    if end_date_set:
        schedule.end_date = end_date

    _validate_range(schedule.start_date, schedule.end_date)

    if times is not None:
        validate_times(schedule.schedule_type, times)
        _apply_times(schedule, times)
    else:
        # The pattern may have changed under times that were not resent --
        # switching to specific days with only weekday-less rows would
        # silently stop producing anything.
        validate_times(
            schedule.schedule_type,
            [
                TimeInput(time_of_day=entry.time_of_day, weekday=entry.weekday)
                for entry in schedule.times
            ],
        )

    db.flush()
    dose_service.regenerate(db, schedule, now)
    db.commit()
    db.refresh(schedule)
    logger.info("medication.schedule.update success")
    return schedule


def set_paused(
    db: Session, schedule: MedicationSchedule, *, paused: bool, now: datetime
) -> MedicationSchedule:
    """Pauses or resumes reminders (PRD 5, section 37).

    Pausing stops generation and withdraws the doses that have not happened
    yet; it keeps the schedule, the medication and every recorded dose.
    Nothing here infers *why* somebody paused, and nothing asks.
    """
    schedule.is_active = not paused
    schedule.paused_at = now if paused else None

    if paused:
        dose_service.withdraw_future(db, schedule, now)
    else:
        dose_service.generate_for_schedule(db, schedule, now)

    db.commit()
    db.refresh(schedule)
    logger.info("medication.schedule.%s success", "pause" if paused else "resume")
    return schedule


def delete_schedule(db: Session, schedule: MedicationSchedule, now: datetime) -> None:
    """Removes a schedule, keeping everything it already produced.

    Doses it created keep their status, their times and their source; their
    ``schedule_id`` simply becomes null. That is why the column is
    ``ON DELETE SET NULL`` and not a cascade (PRD 5, section 39).
    """
    dose_service.withdraw_future(db, schedule, now)
    db.flush()
    db.delete(schedule)
    db.commit()
    logger.info("medication.schedule.delete success")


def on_medication_inactivated(db: Session, medication: Medication, now: datetime) -> int:
    """Stops future reminders when a medication is marked as no longer taken.

    The schedules are paused rather than deleted (PRD 5, section 38): marking
    a medication active again is a common correction, and someone who does
    that should get their reminders back rather than having to build them
    again. History is untouched either way.
    """
    schedules = list(
        db.execute(
            select(MedicationSchedule).where(
                MedicationSchedule.medication_id == medication.id,
                MedicationSchedule.is_active.is_(True),
            )
        )
        .scalars()
        .all()
    )

    for schedule in schedules:
        schedule.is_active = False
        schedule.paused_at = now
        dose_service.withdraw_future(db, schedule, now)

    if schedules:
        logger.info("medication.schedule.pause success (%d)", len(schedules))
    return len(schedules)


def has_history(db: Session, medication_id: uuid.UUID) -> bool:
    """Whether anything has ever been recorded against this medication.

    Used to refuse a destructive delete: a medication somebody has been taking
    is archived by marking it inactive, not erased along with every dose they
    recorded (PRD 5, section 40).
    """
    from app.models import MedicationDose

    return (
        db.execute(
            select(MedicationDose.id)
            .where(
                MedicationDose.medication_id == medication_id,
                MedicationDose.status.in_(("taken", "skipped", "missed")),
            )
            .limit(1)
        ).scalar_one_or_none()
        is not None
    )
