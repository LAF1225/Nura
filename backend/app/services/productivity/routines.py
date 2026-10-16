"""Routines, their steps, their runs and their step completions.

PRD 12, sections 12, 13, 14, 15, 24, 39, 43 and 55.

**A run covers a day, not a moment.** This is the one place PRD 12 departs from
PRD 5's generation rule, and the departure is deliberate. A dose created at ten
in the morning does not retroactively produce this morning's eight o'clock,
because there was nothing to remind anybody about at eight. A routine is
different: a morning routine is a checklist for the morning, and somebody who
opens Nura at nine should be able to tick off the water they drank at half past
seven. So runs are generated from the start of the local *day*, and a run stays
open until its day is over.

That also gives "missed" an honest definition: a run is missed when its day has
gone, not two hours after its time. Nothing else follows from it -- no advice,
no score, nobody told.

**A step can be optional, so a run can be complete without every step.**
Section 14 tracks individual step completion, and a routine ending in "walk
round the garden if you feel up to it" must not be permanently unfinished.

**Nothing here prescribes a routine.** Sections 15 and 24: a person may create
a health-related routine or enter one a clinician gave them, and Nura may
remind them of it. There is no function in this module that takes a symptom, a
diagnosis or a model's opinion, and no caller anywhere passes one. The only
non-user source is ``caregiver_suggestion``, which means a person approved it
(section 43).
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Routine, RoutineRun, RoutineStep, RoutineStepCompletion
from app.models.enums import (
    ROUTINE_ACTIVE_STATUSES,
    ROUTINE_RUN_OPEN_STATUSES,
    ROUTINE_SCHEDULE_TYPES,
    ROUTINE_STEP_STATES,
)
from app.models.productivity import MAX_ROUTINE_STEPS
from app.services.errors import DomainError, NotFoundError
from app.services.medications.doses import zone_for
from app.services.productivity import recurrence

logger = logging.getLogger(__name__)

#: How many routines one profile may hold. Several mornings' worth.
MAX_ROUTINES = 50

EDITABLE_FIELDS = frozenset(
    {
        "title",
        "description",
        "schedule_type",
        "timezone",
        "time_of_day",
        "weekdays",
        "start_date",
        "end_date",
    }
)

#: Changing one of these means the future runs have to be rebuilt.
PATTERN_FIELDS = frozenset(
    {"schedule_type", "timezone", "time_of_day", "weekdays", "start_date", "end_date"}
)


class RoutineNotFoundError(NotFoundError):
    code = "routine_not_found"


class RoutineRunNotFoundError(NotFoundError):
    code = "routine_run_not_found"


class RoutineStepNotFoundError(NotFoundError):
    code = "routine_step_not_found"


class TooManyRoutinesError(DomainError):
    status_code = 409
    code = "too_many_routines"


class InvalidRoutineError(DomainError):
    status_code = 422
    code = "invalid_routine"


class RunNotActionableError(DomainError):
    status_code = 409
    code = "routine_run_not_actionable"


def _log(action: str, count: int | None = None) -> None:
    """``routine.run.complete success`` -- section 45's own second example.

    Never a routine title or a step title. A routine can say something about
    somebody's health -- a physiotherapy exercise, a medication-adjacent habit
    -- and section 45 rules out user-entered text in a general log.
    """
    if count is None:
        logger.info("routine.%s success", action)
    else:
        logger.info("routine.%s success (%d)", action, count)


def pattern_for(routine: Routine) -> recurrence.Pattern:
    """The routine's recurrence, flattened for the generator."""
    return recurrence.Pattern(
        recurrence=routine.schedule_type,
        timezone=routine.timezone,
        start_date=routine.start_date,
        time_of_day=routine.time_of_day,
        end_date=routine.end_date,
        weekdays=routine.weekdays,
    )


# --- reading ----------------------------------------------------------------


def _with_steps() -> tuple[Any, ...]:
    return (selectinload(Routine.steps),)


def get_routine(db: Session, profile_id: uuid.UUID, routine_id: uuid.UUID) -> Routine:
    """One routine of this profile's, or a 404 that confirms nothing."""
    routine = db.execute(
        select(Routine)
        .where(Routine.id == routine_id, Routine.profile_id == profile_id)
        .options(*_with_steps())
    ).scalar_one_or_none()
    if routine is None:
        raise RoutineNotFoundError("Not found.")
    return routine


def find_by_client_id(
    db: Session, profile_id: uuid.UUID, client_routine_id: str | None
) -> Routine | None:
    if not client_routine_id:
        return None
    return db.execute(
        select(Routine)
        .where(
            Routine.profile_id == profile_id,
            Routine.client_routine_id == client_routine_id,
        )
        .options(*_with_steps())
    ).scalar_one_or_none()


def list_routines(
    db: Session, profile_id: uuid.UUID, *, active_only: bool = False
) -> list[Routine]:
    """This profile's routines, earliest time of day first."""
    query = select(Routine).where(Routine.profile_id == profile_id)
    if active_only:
        query = query.where(Routine.status.in_(ROUTINE_ACTIVE_STATUSES))
    return list(
        db.execute(
            query.order_by(Routine.time_of_day.asc(), Routine.created_at.asc()).options(
                *_with_steps()
            )
        )
        .scalars()
        .all()
    )


def get_step(db: Session, routine: Routine, step_id: uuid.UUID) -> RoutineStep:
    """One step of this routine, or a 404. Scoped at both depths."""
    step = db.execute(
        select(RoutineStep).where(
            RoutineStep.id == step_id,
            RoutineStep.routine_id == routine.id,
            RoutineStep.profile_id == routine.profile_id,
        )
    ).scalar_one_or_none()
    if step is None:
        raise RoutineStepNotFoundError("Not found.")
    return step


def get_run(db: Session, profile_id: uuid.UUID, run_id: uuid.UUID) -> RoutineRun:
    """One run of this profile's, with its routine, steps and completions.

    ``populate_existing`` matters here and is easy to leave out. A run that is
    already in the session has its ``completions`` collection loaded, and
    SQLAlchemy will not replace a loaded collection on a later query -- so a
    read taken straight after ticking a step would hand back the progress from
    before the tick. Every caller of this function does exactly that.
    """
    run = db.execute(
        select(RoutineRun)
        .where(RoutineRun.id == run_id, RoutineRun.profile_id == profile_id)
        .options(
            selectinload(RoutineRun.routine).selectinload(Routine.steps),
            selectinload(RoutineRun.completions),
        )
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()
    if run is None:
        raise RoutineRunNotFoundError("Not found.")
    return run


def list_runs(
    db: Session,
    profile_id: uuid.UUID,
    *,
    from_date: date | None = None,
    to_date: date | None = None,
    routine_id: uuid.UUID | None = None,
    statuses: tuple[str, ...] | None = None,
) -> list[RoutineRun]:
    """Runs in a range of the user's own local days, earliest first."""
    query = select(RoutineRun).where(RoutineRun.profile_id == profile_id)
    if from_date is not None:
        query = query.where(RoutineRun.local_date >= from_date)
    if to_date is not None:
        query = query.where(RoutineRun.local_date <= to_date)
    if routine_id is not None:
        query = query.where(RoutineRun.routine_id == routine_id)
    if statuses is not None:
        query = query.where(RoutineRun.status.in_(statuses))
    return list(
        db.execute(
            query.order_by(RoutineRun.scheduled_for.asc())
            .options(
                selectinload(RoutineRun.routine).selectinload(Routine.steps),
                selectinload(RoutineRun.completions),
            )
            # For the reason ``get_run`` gives: a list read after a step was
            # ticked must count the tick.
            .execution_options(populate_existing=True)
        )
        .scalars()
        .all()
    )


def runs_for_today(db: Session, profile_id: uuid.UUID, now: datetime) -> list[RoutineRun]:
    """Today's runs, in each routine's own local day.

    Each routine's zone decides which day its run belongs to, so a routine set
    up in London and one set up while travelling both read correctly. The
    filter is on ``local_date``, which is why it is stored.
    """
    rows = list_runs(db, profile_id)
    today_by_zone: dict[str, date] = {}
    out = []
    for run in rows:
        zone_name = run.routine.timezone
        if zone_name not in today_by_zone:
            today_by_zone[zone_name] = recurrence.local_today(zone_for(zone_name), now)
        if run.local_date == today_by_zone[zone_name]:
            out.append(run)
    return out


@dataclass(frozen=True)
class RunProgress:
    """How far through a run somebody is (sections 14 and 33).

    Derived from the completion rows on every read, never stored: a count that
    could disagree with the rows it counts is a count nobody can trust.
    """

    total: int
    done: int
    skipped: int
    next_step: RoutineStep | None
    #: True when every required step has a completion row.
    all_required_done: bool


def progress(run: RoutineRun) -> RunProgress:
    """Where this run has got to."""
    steps = sorted(run.routine.steps, key=lambda step: step.position)
    by_step = {row.step_id: row for row in run.completions}
    done = sum(1 for row in run.completions if row.state == "completed")
    skipped = sum(1 for row in run.completions if row.state == "skipped")
    next_step = next((step for step in steps if step.id not in by_step), None)
    required_remaining = [
        step for step in steps if not step.optional and step.id not in by_step
    ]
    return RunProgress(
        total=len(steps),
        done=done,
        skipped=skipped,
        next_step=next_step,
        all_required_done=not required_remaining,
    )


# --- generation -------------------------------------------------------------


def generate_for_routine(
    db: Session,
    routine: Routine,
    now: datetime,
    horizon_days: int = recurrence.GENERATION_HORIZON_DAYS,
) -> list[RoutineRun]:
    """Tops this routine's runs up to ``horizon_days`` ahead, including today.

    Including today even when the time has gone is the whole difference from
    PRD 5's generator, and the module docstring says why: a run is a checklist
    for a day. A routine with no steps generates nothing -- an empty checklist
    is not a thing to tick off.
    """
    if routine.status not in ROUTINE_ACTIVE_STATUSES or not routine.steps:
        return []

    zone = zone_for(routine.timezone)
    today = recurrence.local_today(zone, now)
    horizon = today + timedelta(days=horizon_days)

    existing = {
        instant
        for (instant,) in db.execute(
            select(RoutineRun.scheduled_for).where(
                RoutineRun.routine_id == routine.id,
                RoutineRun.local_date >= today,
            )
        ).all()
    }

    created: list[RoutineRun] = []
    for moment in recurrence.occurrences(pattern_for(routine), today, horizon):
        if moment.scheduled_for in existing:
            continue
        run = RoutineRun(
            routine_id=routine.id,
            profile_id=routine.profile_id,
            scheduled_for=moment.scheduled_for,
            local_date=moment.local_date,
            status="scheduled",
        )
        db.add(run)
        created.append(run)
        existing.add(moment.scheduled_for)
    return created


def withdraw_future(db: Session, routine: Routine, now: datetime) -> int:
    """Removes runs from today onwards that nobody has started.

    A run somebody has begun -- one step ticked, or marked in progress -- is
    ``cancelled`` rather than deleted, because deleting it would erase
    something they did. Yesterday's runs are never touched.
    """
    zone = zone_for(routine.timezone)
    today = recurrence.local_today(zone, now)
    rows = (
        db.execute(
            select(RoutineRun)
            .where(
                RoutineRun.routine_id == routine.id,
                RoutineRun.local_date >= today,
                RoutineRun.status.in_(ROUTINE_RUN_OPEN_STATUSES),
            )
            .options(selectinload(RoutineRun.completions))
        )
        .scalars()
        .all()
    )
    affected = 0
    for run in rows:
        if run.status == "scheduled" and not run.completions:
            db.delete(run)
        else:
            run.status = "cancelled"
        affected += 1
    if affected:
        _log("withdraw", affected)
    return affected


def regenerate(db: Session, routine: Routine, now: datetime) -> None:
    """Rebuilds future runs after the schedule changed."""
    withdraw_future(db, routine, now)
    db.flush()
    generate_for_routine(db, routine, now)


def mark_missed(db: Session, profile_id: uuid.UUID, now: datetime) -> int:
    """Turns an unfinished run whose day has gone into ``missed``.

    By day rather than by the clock, which is the honest reading of a
    checklist: a morning routine is not missed at half past nine, it is missed
    when the day is over. A run that was started and then left keeps whatever
    steps were ticked.
    """
    open_runs = (
        db.execute(
            select(RoutineRun)
            .where(
                RoutineRun.profile_id == profile_id,
                RoutineRun.status.in_(ROUTINE_RUN_OPEN_STATUSES),
            )
            .options(selectinload(RoutineRun.routine))
        )
        .scalars()
        .all()
    )
    changed = 0
    for run in open_runs:
        zone = zone_for(run.routine.timezone)
        if run.local_date < recurrence.local_today(zone, now):
            run.status = "missed"
            changed += 1
    if changed:
        _log("missed", changed)
    return changed


def replenish(db: Session, profile_id: uuid.UUID, now: datetime) -> None:
    """Brings one profile's runs up to date. Called at the top of every read."""
    for routine in list_routines(db, profile_id, active_only=True):
        generate_for_routine(db, routine, now)
    mark_missed(db, profile_id, now)
    db.commit()


# --- writing ----------------------------------------------------------------


@dataclass(frozen=True)
class StepInput:
    """One step, as a client describes it."""

    title: str
    optional: bool = False


@dataclass(frozen=True)
class RoutineInput:
    title: str
    time_of_day: time
    start_date: date
    schedule_type: str = "daily"
    timezone: str = "UTC"
    description: str | None = None
    weekdays: list[int] | None = None
    end_date: date | None = None
    client_routine_id: str | None = None
    source: str = "user"


def _check(
    *,
    schedule_type: str,
    weekdays: list[int] | None,
    start_date: date,
    end_date: date | None,
    timezone: str,
) -> None:
    if schedule_type not in ROUTINE_SCHEDULE_TYPES:
        raise InvalidRoutineError("That is not a repeat a routine has.")
    zone_for(timezone)
    if end_date is not None and end_date < start_date:
        raise InvalidRoutineError("The end date is before the start date.")
    if schedule_type == "selected_days":
        if not weekdays:
            raise InvalidRoutineError("Choose at least one day.")
        if any(day < 0 or day > 6 for day in weekdays):
            raise InvalidRoutineError("That is not a day of the week.")
    elif weekdays:
        raise InvalidRoutineError("That repeat does not use days of the week.")


def _steps_for(
    routine_id: uuid.UUID, profile_id: uuid.UUID, steps: list[StepInput]
) -> list[RoutineStep]:
    """Step rows, numbered from the order they were given.

    Position comes from the list rather than from a number the client has to
    keep consistent, which removes the whole class of duplicate-position bugs
    -- the same choice the Today card layout makes.
    """
    rows = []
    for position, step in enumerate(steps):
        title = step.title.strip()
        if not title:
            raise InvalidRoutineError("A step needs a few words saying what it is.")
        rows.append(
            RoutineStep(
                routine_id=routine_id,
                profile_id=profile_id,
                title=title,
                position=position,
                optional=step.optional,
            )
        )
    return rows


def create_routine(
    db: Session,
    profile_id: uuid.UUID,
    data: RoutineInput,
    steps: list[StepInput],
    now: datetime,
) -> Routine:
    """Adds a routine with its steps, and generates its runs (sections 12-14)."""
    if not data.title.strip():
        raise InvalidRoutineError("A routine needs a title.")
    if not steps:
        raise InvalidRoutineError("A routine needs at least one step.")
    if len(steps) > MAX_ROUTINE_STEPS:
        raise InvalidRoutineError(f"A routine can have {MAX_ROUTINE_STEPS} steps.")
    _check(
        schedule_type=data.schedule_type,
        weekdays=data.weekdays,
        start_date=data.start_date,
        end_date=data.end_date,
        timezone=data.timezone,
    )
    if len(list_routines(db, profile_id)) >= MAX_ROUTINES:
        raise TooManyRoutinesError("There are too many routines already.")

    routine = Routine(
        profile_id=profile_id,
        title=data.title.strip(),
        description=(data.description or None),
        schedule_type=data.schedule_type,
        timezone=data.timezone,
        time_of_day=data.time_of_day,
        weekdays=sorted(set(data.weekdays)) if data.weekdays else None,
        start_date=data.start_date,
        end_date=data.end_date,
        status="active",
        source=data.source,
        client_routine_id=data.client_routine_id,
    )
    db.add(routine)
    db.flush()
    routine.steps = _steps_for(routine.id, profile_id, steps)
    db.flush()
    generate_for_routine(db, routine, now)
    db.commit()
    db.refresh(routine)
    _log("create")
    return routine


def update_routine(
    db: Session, routine: Routine, fields: dict[str, Any], now: datetime
) -> Routine:
    """Edits a routine, rebuilding its future runs if the schedule moved."""
    unknown = set(fields) - EDITABLE_FIELDS
    if unknown:
        raise InvalidRoutineError(f"A routine has no {sorted(unknown)[0]}.")

    merged = {
        "schedule_type": routine.schedule_type,
        "weekdays": routine.weekdays,
        "start_date": routine.start_date,
        "end_date": routine.end_date,
        "timezone": routine.timezone,
        **fields,
    }
    _check(
        schedule_type=str(merged["schedule_type"]),
        weekdays=merged["weekdays"],
        start_date=merged["start_date"],
        end_date=merged["end_date"],
        timezone=str(merged["timezone"]),
    )

    if "title" in fields:
        title = str(fields["title"] or "").strip()
        if not title:
            raise InvalidRoutineError("A routine needs a title.")
        routine.title = title
    if "description" in fields:
        routine.description = fields["description"] or None
    for key in ("schedule_type", "timezone", "time_of_day", "start_date", "end_date"):
        if key in fields:
            setattr(routine, key, fields[key])
    if "weekdays" in fields:
        value = fields["weekdays"]
        routine.weekdays = sorted(set(value)) if value else None

    if PATTERN_FIELDS & set(fields):
        regenerate(db, routine, now)
    db.commit()
    db.refresh(routine)
    _log("update")
    return routine


def replace_steps(
    db: Session, routine: Routine, steps: list[StepInput], now: datetime
) -> Routine:
    """Replaces the whole step list, in the order given (section 48).

    The whole list rather than a diff, which is what makes Move Up, Move Down
    and drag-and-drop one operation on the server instead of three. Runs that
    have not been started are rebuilt, because a run's progress is counted
    against the steps that exist; runs with completions on them are left alone
    so nothing somebody did is lost.
    """
    if not steps:
        raise InvalidRoutineError("A routine needs at least one step.")
    if len(steps) > MAX_ROUTINE_STEPS:
        raise InvalidRoutineError(f"A routine can have {MAX_ROUTINE_STEPS} steps.")

    routine.steps = _steps_for(routine.id, routine.profile_id, steps)
    db.flush()
    regenerate(db, routine, now)
    db.commit()
    db.refresh(routine)
    _log("steps")
    return routine


def set_paused(db: Session, routine: Routine, *, paused: bool, now: datetime) -> Routine:
    """Pausing stops the runs and keeps the routine (section 13).

    Resuming generates forward from today rather than filling in the gap: a
    routine nobody wanted last week is not a backlog to work through.
    """
    routine.status = "paused" if paused else "active"
    routine.paused_at = now if paused else None
    if paused:
        withdraw_future(db, routine, now)
    else:
        generate_for_routine(db, routine, now)
    db.commit()
    db.refresh(routine)
    _log("paused" if paused else "resumed")
    return routine


def archive_routine(db: Session, routine: Routine, now: datetime) -> Routine:
    """Stops a routine for good and keeps its history.

    What somebody wants instead of deleting: the runs stay, so "I did this
    every morning for a month" is still true afterwards.
    """
    withdraw_future(db, routine, now)
    routine.status = "archived"
    db.commit()
    db.refresh(routine)
    _log("archive")
    return routine


def delete_routine(db: Session, routine: Routine) -> None:
    """Removes a routine, its steps and its runs. For one entered by mistake."""
    db.delete(routine)
    db.commit()
    _log("delete")


# --- running --------------------------------------------------------------


def find_completion_by_client_id(
    db: Session, profile_id: uuid.UUID, client_completion_id: str | None
) -> RoutineStepCompletion | None:
    """A completion this client already sent, if any (section 39)."""
    if not client_completion_id:
        return None
    return db.execute(
        select(RoutineStepCompletion).where(
            RoutineStepCompletion.profile_id == profile_id,
            RoutineStepCompletion.client_completion_id == client_completion_id,
        )
    ).scalar_one_or_none()


def complete_step(
    db: Session,
    run: RoutineRun,
    step: RoutineStep,
    now: datetime,
    *,
    state: str = "completed",
    completed_at: datetime | None = None,
    client_completion_id: str | None = None,
) -> tuple[RoutineStepCompletion, bool]:
    """Records that a step was done, or passed over (sections 14 and 39).

    Idempotent through the ``(run_id, step_id)`` unique constraint: sending the
    same completion twice leaves one row, so an offline queue that retries
    cannot invent progress. The returned flag says whether this call is the one
    that created it.

    Marking a step also starts the run, because it has started.
    """
    if state not in ROUTINE_STEP_STATES:
        raise InvalidRoutineError("That is not something a step can be.")
    if run.status not in ROUTINE_RUN_OPEN_STATUSES:
        raise RunNotActionableError("This routine run has already been recorded.")
    if step.routine_id != run.routine_id:
        raise RoutineStepNotFoundError("Not found.")

    existing = next((row for row in run.completions if row.step_id == step.id), None)
    if existing is not None:
        if existing.state != state:
            existing.state = state
            existing.completed_at = completed_at or now
            db.commit()
            db.refresh(existing)
            _log("step")
            return existing, True
        return existing, False

    completion = RoutineStepCompletion(
        run_id=run.id,
        step_id=step.id,
        profile_id=run.profile_id,
        state=state,
        completed_at=completed_at or now,
        client_completion_id=client_completion_id,
    )
    db.add(completion)
    if run.status == "scheduled":
        run.status = "in_progress"
        run.started_at = completed_at or now
    db.commit()
    db.refresh(completion)
    _log("step")
    return completion, True


def clear_step(db: Session, run: RoutineRun, step: RoutineStep) -> bool:
    """Un-ticks a step. Returns whether there was anything to un-tick.

    Undo, which a checklist needs as much as a task does: somebody who ticked
    the wrong line should be able to put it back rather than live with it.
    """
    existing = next((row for row in run.completions if row.step_id == step.id), None)
    if existing is None:
        return False
    db.delete(existing)
    db.commit()
    db.refresh(run)
    _log("step.clear")
    return True


def complete_run(
    db: Session, run: RoutineRun, now: datetime, *, completed_at: datetime | None = None
) -> tuple[RoutineRun, bool]:
    """Marks a whole run done (section 14).

    Allowed with steps still unticked. Somebody who did their morning routine
    without opening the app should be able to say so in one tap, and a product
    that insisted on three taps first would be teaching people to lie to it.
    """
    if run.status == "completed":
        return run, False
    if run.status not in ROUTINE_RUN_OPEN_STATUSES:
        raise RunNotActionableError("This routine run has already been recorded.")
    moment = completed_at or now
    run.status = "completed"
    run.completed_at = moment
    if run.started_at is None:
        run.started_at = moment
    db.commit()
    db.refresh(run)
    _log("run.complete")
    return run, True


def skip_run(db: Session, run: RoutineRun, now: datetime) -> tuple[RoutineRun, bool]:
    """Records that a run is not happening today.

    Deliberately *not* ``missed``: skipping is something a person decided, and
    missing is what the end of a day concluded. Keeping them apart is the
    difference between a record and a judgement.
    """
    if run.status == "skipped":
        return run, False
    if run.status not in ROUTINE_RUN_OPEN_STATUSES:
        raise RunNotActionableError("This routine run has already been recorded.")
    run.status = "skipped"
    run.completed_at = now
    db.commit()
    db.refresh(run)
    _log("run.skip")
    return run, True
