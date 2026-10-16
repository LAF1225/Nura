"""One function that answers "what should this robot be showing?".

PRD 11, sections 18, 51, 52, 53, 54, 56, 83, 84, 99, 100, 101 and 102.

**Reconciliation, not notification.** This is the architectural decision PRD 11
turns on, and it is worth stating plainly: nothing in PRD 0-10 was modified to
call into the robot. There is no hook in the dose service, no hook in the
appointment service, no hook in the messaging service and no hook anywhere in
PRD 10's safety engine. Instead, ``refresh`` reads what is currently true and
makes the queue match.

Three things follow, and each one is a requirement the PRD states separately:

  - **The robot is additive** (sections 51-54). A workflow cannot fail because
    of the robot, because no workflow calls the robot.
  - **A card cannot go stale** (section 56). There is no event that could have
    been missed -- only state, read again. A dose that has been taken loses its
    card on the next reconciliation, whether that is a second later or after
    the robot has been unplugged for a week.
  - **Reconnecting is not special** (sections 99 and 20). A robot that comes
    back after a day gets what is true now. There is no replay, no backlog and
    no "while you were away".

**It is also the cheapest thing to be sure about.** The alternative -- a
notification per source, each one responsible for cancelling its own card --
would have meant six places that could forget, and the thing they would forget
is withdrawing a reminder that is no longer true.

**Nothing here writes outside the robot's own tables.** The doses, the
appointments, the messages and PRD 10's events are all read. The only rows this
module creates or changes are in ``device_presentations``.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    Alarm,
    Appointment,
    Device,
    FamilyMessage,
    GeneralReminderOccurrence,
    MedicationDose,
    RoutineRun,
    Task,
)
from app.services.productivity import alarms as alarm_service
from app.services.productivity import routines as routine_service
from app.services.robot import modes, preferences, queue
from app.services.robot.builders import appointments as appointment_builder
from app.services.robot.builders import medication as medication_builder
from app.services.robot.builders import messages as message_builder
from app.services.robot.builders import productivity as productivity_builder
from app.services.robot.builders import safety as safety_builder
from app.services.robot.builders import system as system_builder

logger = logging.getLogger(__name__)

#: How far back to look for doses that might still be due. PRD 5's grace
#: period is two hours, and a dose stops reading as ``due`` after it; an hour
#: of slack beyond that costs one indexed query and means a clock skew cannot
#: hide a reminder.
DOSE_LOOKBACK = timedelta(hours=3)

#: How far ahead. PRD 5 starts calling a dose ``due`` half an hour early.
DOSE_LOOKAHEAD = timedelta(hours=1)


@dataclass(frozen=True)
class RefreshResult:
    """What reconciliation did, for diagnostics (section 65).

    Counts only. Nothing in here names a medication, a message or a person,
    because this is the thing that gets logged (section 67).
    """

    mode: modes.RobotMode
    queued: int
    cancelled: int
    expired: int
    queue_depth: int


def refresh(
    db: Session,
    device: Device,
    now: datetime,
    *,
    assume_online: bool = False,
) -> RefreshResult:
    """Brings this robot's queue in line with what is true (section 18).

    ``assume_online`` is set when the robot itself is asking: a device whose
    request we are answering is reachable, whatever its last heartbeat says.

    The order matters once: safety is reconciled first, so that an emergency
    card exists before anything ordinary is considered and the preemption in
    ``queue`` has something to preempt.
    """
    expired = queue.expire_due(db, now, device.id)
    if device.owner_profile_id is None:
        mode = modes.resolve(db, device, now, assume_online=assume_online)
        return RefreshResult(
            mode=mode, queued=0, cancelled=0, expired=expired, queue_depth=0
        )

    profile_id = device.owner_profile_id
    mode = modes.resolve(db, device, now, assume_online=assume_online)

    queued = len(safety_builder.sync(db, device, now))
    cancelled = 0

    cancelled += _withdraw_stale_doses(db, device, now)
    cancelled += _withdraw_stale_appointments(db, device, now)
    cancelled += _withdraw_stale_messages(db, device, now)
    cancelled += _withdraw_stale_daily_life(db, device, now)

    queued += _queue_due_doses(db, device, profile_id, now, mode)
    queued += _queue_upcoming_appointments(db, device, profile_id, now, mode)
    queued += _queue_unread_messages(db, device, profile_id, now, mode)
    queued += _queue_daily_life(db, device, profile_id, now, mode)

    if system_builder.queue_setup_prompt(db, device, now, mode) is not None:
        queued += 1

    # Section 83: the face is whatever is left when nothing else is showing,
    # and the mode is recomputed first so a queued card turns the robot into
    # ``information`` rather than leaving it claiming to be idle.
    showing = queue.showing_card(db, device.id)
    final_mode = modes.resolve(
        db, device, now, assume_online=assume_online, showing_card=showing
    )
    if system_builder.ensure_face(db, device, now, final_mode) is not None:
        queued += 1

    db.flush()
    result = RefreshResult(
        mode=final_mode,
        queued=queued,
        cancelled=cancelled,
        expired=expired,
        queue_depth=queue.queue_depth(db, device.id),
    )
    logger.info(
        "robot.refresh mode=%s queued=%d cancelled=%d expired=%d depth=%d",
        result.mode.mode,
        result.queued,
        result.cancelled,
        result.expired,
        result.queue_depth,
    )
    return result


# --- medication (sections 56, 102, 125) --------------------------------------


def _due_doses(db: Session, profile_id: uuid.UUID, now: datetime) -> list[MedicationDose]:
    """Doses that PRD 5 would call ``due`` right now.

    The window is a cheap index scan; ``is_due`` then applies PRD 5's own
    rule, so there is no second definition of "due" in this codebase.
    """
    candidates = (
        db.execute(
            select(MedicationDose)
            .where(
                MedicationDose.profile_id == profile_id,
                MedicationDose.status.in_(("scheduled", "snoozed")),
                MedicationDose.scheduled_for >= now - DOSE_LOOKBACK,
                MedicationDose.scheduled_for <= now + DOSE_LOOKAHEAD,
            )
            .options(
                selectinload(MedicationDose.medication),
                selectinload(MedicationDose.schedule),
            )
            .order_by(MedicationDose.scheduled_for.asc())
        )
        .scalars()
        .all()
    )
    return [dose for dose in candidates if medication_builder.is_due(dose, now)]


def _queue_due_doses(
    db: Session,
    device: Device,
    profile_id: uuid.UUID,
    now: datetime,
    mode: modes.RobotMode,
) -> int:
    queued = 0
    for dose in _due_doses(db, profile_id, now):
        row = medication_builder.queue_for_dose(db, device, dose, now, mode=mode)
        if row is not None:
            queued += 1
    return queued


def _withdraw_stale_doses(db: Session, device: Device, now: datetime) -> int:
    """Section 56, and section 125's "taken dose cancels stale card".

    The dose is loaded and asked again. A dose that was taken, skipped,
    cancelled, missed or snoozed past its moment is no longer due, and its
    card goes -- which is why a robot reconnecting an hour later is never
    handed "take this now" for a tablet somebody already took.

    A dose that was *snoozed* is a second case and needs the extra comparison
    below: it is still due, at a new time, and its new card has a new key. The
    old one has to go or the robot would hold two cards for one tablet.
    """
    _, resolved_preferences = preferences.resolved_for(db, device, now)
    mode = modes.resolve(db, device, now)
    level = medication_builder.privacy_level_for(resolved_preferences, mode)

    cancelled = 0
    for row in queue.open_presentations(db, device.id):
        if row.presentation_type != medication_builder.PRESENTATION_TYPE:
            continue
        dose = _dose_for(db, row.dedupe_key)
        if dose is None or not medication_builder.is_due(dose, now):
            # The occasion is over: taken, skipped, missed, or snoozed past its
            # moment. Nothing notified the robot; the dose was asked again.
            queue.cancel(db, row, reason="source_resolved", now=now)
            cancelled += 1
            continue
        # The key carries the snooze count and the privacy level, so a card
        # built before either changed is about an occasion that no longer
        # applies. Asking only "is it due" would leave two cards for one tablet
        # after a snooze, and would leave a card naming the tablet after
        # somebody asked for a private preview.
        if medication_builder.source_id(dose, level) != _source_id(row.dedupe_key):
            # ``preference_changed`` rather than ``source_resolved``: the dose
            # is still due, and this says the card was withdrawn because of how
            # it was being rendered. ``queue`` reads that reason and lets the
            # same key be rebuilt if the person configures back.
            queue.cancel(db, row, reason="preference_changed", now=now)
            cancelled += 1
    return cancelled


def _dose_for(db: Session, dedupe_key: str) -> MedicationDose | None:
    dose_id = _source_id(dedupe_key).split(":", 1)[0]
    try:
        parsed = uuid.UUID(dose_id)
    except ValueError:
        return None
    return db.get(MedicationDose, parsed)


def _source_id(dedupe_key: str) -> str:
    """The middle of ``source:source_id:type``."""
    _, remainder = dedupe_key.split(":", 1)
    return remainder.rsplit(":", 1)[0]


# --- appointments (section 52) ------------------------------------------------


def _queue_upcoming_appointments(
    db: Session,
    device: Device,
    profile_id: uuid.UUID,
    now: datetime,
    mode: modes.RobotMode,
) -> int:
    rows = (
        db.execute(
            select(Appointment)
            .where(
                Appointment.profile_id == profile_id,
                Appointment.status == "scheduled",
                Appointment.reminders_enabled.is_(True),
                Appointment.scheduled_at >= now,
                Appointment.scheduled_at <= now + appointment_builder.LEAD,
            )
            .options(selectinload(Appointment.clinician))
            .order_by(Appointment.scheduled_at.asc())
        )
        .scalars()
        .all()
    )
    queued = 0
    for appointment in rows:
        presentation = appointment_builder.queue_for_appointment(
            db, device, appointment, now, mode=mode
        )
        if presentation is not None:
            queued += 1
    return queued


def _withdraw_stale_appointments(db: Session, device: Device, now: datetime) -> int:
    cancelled = 0
    for row in queue.open_presentations(db, device.id):
        if row.presentation_type != appointment_builder.PRESENTATION_TYPE:
            continue
        appointment = _row_for(db, Appointment, row.dedupe_key)
        if appointment is not None and appointment_builder.is_upcoming(appointment, now):
            continue
        queue.cancel(db, row, reason="source_resolved", now=now)
        cancelled += 1
    return cancelled


# --- family messages (sections 53, 101, 126) ---------------------------------


def _queue_unread_messages(
    db: Session,
    device: Device,
    profile_id: uuid.UUID,
    now: datetime,
    mode: modes.RobotMode,
) -> int:
    queued = 0
    for message in message_builder.recent_for_profile(db, profile_id, now):
        if message_builder.queue_for_message(db, device, message, now, mode=mode):
            queued += 1
    return queued


def _withdraw_stale_messages(db: Session, device: Device, now: datetime) -> int:
    """A message read in the app stops being news on the shelf.

    Also the permission case: a caregiver whose ``communication`` permission
    was withdrawn has their pending card cancelled here, because
    ``is_presentable`` asks the permission again rather than trusting that it
    held when the card was built (PRD 10's section 86, applied to PRD 9's
    permissions).
    """
    cancelled = 0
    for row in queue.open_presentations(db, device.id):
        if row.presentation_type != message_builder.PRESENTATION_TYPE:
            continue
        message = _row_for(db, FamilyMessage, row.dedupe_key)
        if message is not None and message_builder.is_presentable(
            db, device, message, now
        ):
            continue
        reason = "source_resolved" if message is not None else "source_cancelled"
        queue.cancel(db, row, reason=reason, now=now)
        cancelled += 1
    return cancelled


# --- daily life (PRD 12, sections 30, 31 and 32) -----------------------------
#
# Four more kinds of card through the same reconciliation, which is the whole
# of section 30's "do not create a second robot transport". Nothing in PRD 12's
# services calls into the robot; the same ``refresh`` that asks "what doses are
# due" now also asks "what tasks are due", and the queue is made to match.
#
# Section 31 follows for free. A task, a reminder, an alarm and a routine all
# work with no device row in the database, because nothing about them reaches
# this file -- this file reaches them.


def _queue_daily_life(
    db: Session,
    device: Device,
    profile_id: uuid.UUID,
    now: datetime,
    mode: modes.RobotMode,
) -> int:
    """Queues whatever daily-life cards are true right now."""
    queued = 0
    for task in productivity_builder.due_tasks(db, profile_id, now):
        if productivity_builder.queue_for_task(db, device, task, now, mode=mode):
            queued += 1
    for occurrence in productivity_builder.due_occurrences(db, profile_id, now):
        if productivity_builder.queue_for_occurrence(
            db, device, occurrence, now, mode=mode
        ):
            queued += 1
    for alarm, fire_at in productivity_builder.alarms_ringing_now(db, profile_id, now):
        if productivity_builder.queue_for_alarm(
            db, device, alarm, fire_at, now, mode=mode
        ):
            queued += 1
    for run in productivity_builder.open_runs(db, profile_id, now):
        if productivity_builder.queue_for_run(db, device, run, now, mode=mode):
            queued += 1
    return queued


def _withdraw_stale_daily_life(db: Session, device: Device, now: datetime) -> int:
    """Withdraws daily-life cards that are no longer true (sections 31, 32).

    One function for all four types, because the question is the same each
    time: is the thing this card was built from still in the state the card
    describes? A task that was completed, a reminder that was answered, an
    alarm whose minute has gone and a routine whose next step has been ticked
    all lose their card here -- so a robot that has been unplugged for an hour
    never comes back holding somebody's finished morning.
    """
    _, resolved = preferences.resolved_for(db, device, now)
    mode = modes.resolve(db, device, now)

    # Section 31's switch. Off withdraws the lot, and the tasks, reminders,
    # alarms and routines themselves are untouched.
    if not productivity_builder.enabled(resolved):
        return productivity_builder.cancel_all(db, device, now)

    level = productivity_builder.privacy_level_for(resolved, mode)
    cancelled = 0
    for row in queue.open_presentations(db, device.id):
        if row.presentation_type not in productivity_builder.TYPES:
            continue
        reason = _daily_life_reason(
            db, row.presentation_type, _source_id(row.dedupe_key), level, now
        )
        if reason is None:
            continue
        queue.cancel(db, row, reason=reason, now=now)
        cancelled += 1
    return cancelled


def _key_mismatch_reason(key: str, expected: str, level: str) -> str:
    """Why a key that no longer matches should be withdrawn.

    ``preference_changed`` when only the privacy level moved, because PRD 11
    learned that a card withdrawn for a preference has to be rebuildable if
    the person configures back. ``superseded`` when the occasion itself moved
    on -- a snooze, a new minute, another step ticked -- which produces a new
    key anyway, so the distinction costs nothing and keeps the history honest.
    """
    if key.rsplit(":", 1)[-1] != level:
        return "preference_changed"
    return "superseded"


def _daily_life_reason(
    db: Session, presentation_type: str, key: str, level: str, now: datetime
) -> str | None:
    """The cancel reason for this card, or None to leave it alone."""
    row_id = _uuid_prefix(key)
    if row_id is None:
        return "source_cancelled"

    if presentation_type == productivity_builder.TASK_TYPE:
        task = db.get(Task, row_id)
        if task is None:
            return "source_cancelled"
        if not productivity_builder.task_is_due(task, now):
            return "source_resolved"
        expected = productivity_builder.task_source_id(task, level)
        return None if expected == key else _key_mismatch_reason(key, expected, level)

    if presentation_type == productivity_builder.REMINDER_TYPE:
        occurrence = db.get(GeneralReminderOccurrence, row_id)
        if occurrence is None:
            return "source_cancelled"
        if not productivity_builder.reminder_is_due(occurrence, now):
            return "source_resolved"
        expected = productivity_builder.reminder_source_id(occurrence, level)
        return None if expected == key else _key_mismatch_reason(key, expected, level)

    if presentation_type == productivity_builder.ALARM_TYPE:
        alarm = db.get(Alarm, row_id)
        if alarm is None or not alarm.enabled:
            return "source_cancelled"
        fire_at = _alarm_moment(key)
        if fire_at is None or now > fire_at + alarm_service.RING_WINDOW:
            return "source_resolved"
        expected = productivity_builder.alarm_source_id(alarm, fire_at, level)
        return None if expected == key else _key_mismatch_reason(key, expected, level)

    run = db.get(RoutineRun, row_id)
    if run is None:
        return "source_cancelled"
    if not productivity_builder.routine_is_showable(run, now):
        return "source_resolved"
    expected = productivity_builder.routine_source_id(
        run, routine_service.progress(run), level
    )
    return None if expected == key else _key_mismatch_reason(key, expected, level)


def _uuid_prefix(key: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(key.split(":", 1)[0])
    except ValueError:
        return None


def _alarm_moment(key: str) -> datetime | None:
    """The instant out of an alarm card's key.

    An alarm has no occurrence row -- see ``services.productivity.alarms`` --
    so the moment the card is for lives in the key and is read back out here.
    """
    parts = key.split(":")
    if len(parts) < 3:
        return None
    try:
        return datetime.fromtimestamp(int(parts[1]), tz=UTC)
    except (ValueError, OverflowError, OSError):
        return None


def _row_for(db: Session, model: type, dedupe_key: str):  # type: ignore[no-untyped-def]
    try:
        parsed = uuid.UUID(_source_id(dedupe_key).split(":", 1)[0])
    except ValueError:
        return None
    return db.get(model, parsed)
