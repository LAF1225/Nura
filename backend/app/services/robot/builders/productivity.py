"""Tasks, reminders, alarms and routines on the robot's screen.

PRD 12, sections 30, 31, 32, 33, 64 and 65.

**Additive, and nothing here is load-bearing.** Section 31 is the rule: the
robot is never the source of truth. A task stays in the app, a reminder stays
scheduled on the phone, a routine stays usable and an alarm stays on the phone
whether or not anything in this file ever runs. Nothing below writes to a task,
a reminder, an alarm, a routine or a run -- every function reads state and
returns a presentation request, exactly as PRD 11's builders do.

**The privacy level is applied here, not later** (section 32). Three levels,
the same three PRD 11 gave a medication reminder, and the redaction happens
while the payload is built -- so the row stored in ``device_presentations`` is
already the redacted one and the app's own history endpoint cannot show more
than the robot was sent. A task title can be as private as a tablet name:
"ring the clinic about the results" on a shelf in a shared room is exactly what
this exists for.

**Privacy Mode wins over the preference**, downwards only, for the reason PRD 11
gives: the mode is something somebody is doing now and the preference is
something they set once.

**The alarm card cannot claim a sound** (section 65). The robot's speaker
reports ``not_connected``, so the card says the alarm will not sound on Nura
rather than implying it will. If a chime capability ever appears, the line
disappears because it is derived from the capability map and not written into
the card.

**No card offers an action the device cannot take** (PRD 11, section 86;
PRD 12, section 33). Until a device reports input, every card says to use the
app, and section 33's "do not show unusable on-robot action buttons" is
honoured by the same mechanism PRD 11 built.
"""

import logging
import uuid
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Alarm,
    Device,
    DevicePresentation,
    GeneralReminderOccurrence,
    RoutineRun,
    Task,
)
from app.services.productivity import alarms as alarm_service
from app.services.productivity import recurrence
from app.services.productivity import reminders as reminder_service
from app.services.productivity import routines as routine_service
from app.services.productivity import wording as productivity_wording
from app.services.robot import capabilities as capability_service
from app.services.robot import layouts, modes, preferences, queue, wording

logger = logging.getLogger(__name__)

SOURCE = "daily_life"

TASK_TYPE = "task_reminder"
REMINDER_TYPE = "general_reminder"
ALARM_TYPE = "alarm"
ROUTINE_TYPE = "routine"

#: Every type this builder produces, for the reconciler and for the preference
#: switch that turns all four off.
TYPES = (TASK_TYPE, REMINDER_TYPE, ALARM_TYPE, ROUTINE_TYPE)

#: How early a task's card appears, and how long it stays. PRD 5's lead, so a
#: task and a dose at the same minute agree about the word "due"; an hour
#: afterwards, because by then it is one of the overdue ones the app lists
#: rather than something to put on a shelf.
TASK_LEAD = recurrence.DUE_LEAD
TASK_TRAIL = timedelta(hours=1)

#: What a card offers once a device reports input. Until then every one of
#: these lists is empty and the card says to use the app (PRD 11, section 86).
TASK_ACTIONS = ("dismiss", "open_app")
REMINDER_ACTIONS = ("acknowledge", "snooze", "dismiss")
ROUTINE_ACTIONS = ("open_app",)


def privacy_level_for(
    resolved: preferences.EffectivePreferences, mode: modes.RobotMode
) -> str:
    """Which level applies right now (section 32).

    Privacy Mode overrides the stored preference, downwards only. One
    function, used by the builders *and* by the reconciler's staleness checks,
    so "which level is in force" has one answer -- which is the lesson PRD 11's
    manual walk-through paid for.
    """
    if mode.mode == "privacy":
        return "private"
    return resolved.daily_life_privacy_level


def enabled(resolved: preferences.EffectivePreferences) -> bool:
    """Whether the robot shows daily-life cards at all (section 31)."""
    return resolved.daily_life_display_enabled


# --- tasks ------------------------------------------------------------------


def task_source_id(task: Task, privacy_level: str) -> str:
    """The task, at a level (PRD 11, section 57).

    The level is part of the occasion for the reason a medication card's is:
    without it a rebuild folds into the card already on the screen, and
    somebody who has just asked for less on their shelf keeps looking at the
    same words.
    """
    return f"{task.id}:{privacy_level}"


def task_is_due(task: Task, now: datetime) -> bool:
    """Whether this task should be on the screen right now.

    A task with no due date never gets a card. That is not an omission: a card
    is a thing that appears at a moment, and "pick up the prescription at some
    point" has no moment. It is in the app, on the list, where it belongs.
    """
    if task.status not in ("open",) or task.due_at is None:
        return False
    return task.due_at - TASK_LEAD <= now <= task.due_at + TASK_TRAIL


def build_task(
    task: Task,
    *,
    privacy_level: str,
    local_today: date,
    has_input: bool,
    chime: bool,
) -> queue.PresentationRequest:
    """One task card (section 33's first example).

    ``full`` shows what it is and when; ``name_only`` shows what it is;
    ``private`` says a task is due and nothing else.
    """
    when = productivity_wording.due_label(task.due_at, task.timezone, local_today)
    if privacy_level == "private":
        primary, secondary = "Something due", None
    elif privacy_level == "name_only":
        primary, secondary = task.title, None
    else:
        primary, secondary = task.title, when

    payload = layouts.build_payload(
        "REMINDER",
        title=wording.PRESENTATION_TITLES[TASK_TYPE],
        primary=primary,
        secondary=secondary,
        actions=list(TASK_ACTIONS) if has_input else [],
        respond_in_app=not has_input,
        sensitive=privacy_level != "private",
        chime="reminder" if chime else None,
    )
    assert task.due_at is not None  # task_is_due guarantees it
    return queue.PresentationRequest(
        presentation_type=TASK_TYPE,
        layout="REMINDER",
        payload=payload,
        source=SOURCE,
        source_id=task_source_id(task, privacy_level),
        expires_at=task.due_at + TASK_TRAIL,
        meta={"privacy": privacy_level},
    )


# --- general reminders ------------------------------------------------------


def reminder_source_id(occurrence: GeneralReminderOccurrence, privacy_level: str) -> str:
    """The occurrence, which attempt at it, and at what level.

    The snooze count is in the key for PRD 11's reason: a snoozed reminder is a
    second occasion at a new time, and folding the two together would leave one
    card for two moments.
    """
    return f"{occurrence.id}:{occurrence.snooze_count}:{privacy_level}"


def reminder_is_due(occurrence: GeneralReminderOccurrence, now: datetime) -> bool:
    """Whether this occurrence is waiting for an answer right now."""
    return reminder_service.window(occurrence, now) == "due"


def build_reminder(
    occurrence: GeneralReminderOccurrence,
    *,
    privacy_level: str,
    has_input: bool,
    speak: bool,
    chime: bool,
) -> queue.PresentationRequest:
    """One reminder card (section 33)."""
    reminder = occurrence.reminder
    zone = reminder.timezone
    moment = reminder_service.due_at(occurrence)
    when = wording.dose_window_line(due_at=moment, zone=zone)

    if privacy_level == "private":
        primary, secondary = "Reminder", None
    elif privacy_level == "name_only":
        primary, secondary = reminder.title, None
    else:
        primary = reminder.title
        secondary = f"{reminder.body} · {when}" if reminder.body else when

    payload = layouts.build_payload(
        "REMINDER",
        title=wording.PRESENTATION_TITLES[REMINDER_TYPE],
        primary=primary,
        secondary=secondary,
        actions=list(REMINDER_ACTIONS) if has_input else [],
        respond_in_app=not has_input,
        sensitive=privacy_level != "private",
        speak=speak,
        chime="reminder" if chime else None,
    )
    return queue.PresentationRequest(
        presentation_type=REMINDER_TYPE,
        layout="REMINDER",
        payload=payload,
        source=SOURCE,
        source_id=reminder_source_id(occurrence, privacy_level),
        expires_at=moment + recurrence.MISS_AFTER,
        meta={"privacy": privacy_level},
    )


# --- alarms -----------------------------------------------------------------


def alarm_source_id(alarm: Alarm, fire_at: datetime, privacy_level: str) -> str:
    """The alarm, the moment it is for, and at what level.

    The moment is in the key because a daily alarm is a different occasion
    every morning, and there are no occurrence rows to carry that -- see
    ``services.productivity.alarms``.
    """
    return f"{alarm.id}:{int(fire_at.timestamp())}:{privacy_level}"


def build_alarm(
    alarm: Alarm,
    fire_at: datetime,
    *,
    privacy_level: str,
    has_input: bool,
    chime: bool,
) -> queue.PresentationRequest:
    """One alarm card, which is information and not a sound (section 65).

    The robot's speaker reports ``not_connected`` in every deployment, so the
    card says so. The sentence is derived from the capability map rather than
    written into the card, which is what makes it disappear on its own if a
    chime capability ever appears.
    """
    local = fire_at.astimezone(ZoneInfo(alarm.timezone))
    when = productivity_wording.format_clock(time(hour=local.hour, minute=local.minute))
    primary = "Alarm" if privacy_level == "private" else alarm.label
    secondary = when if chime else f"{when} · {productivity_wording.ALARM_ROBOT_NOTE}"

    payload = layouts.build_payload(
        "REMINDER",
        title=wording.PRESENTATION_TITLES[ALARM_TYPE],
        primary=primary,
        secondary=secondary,
        actions=["dismiss"] if has_input else [],
        respond_in_app=not has_input,
        sensitive=privacy_level != "private",
        chime="reminder" if chime else None,
    )
    return queue.PresentationRequest(
        presentation_type=ALARM_TYPE,
        layout="REMINDER",
        payload=payload,
        source=SOURCE,
        source_id=alarm_source_id(alarm, fire_at, privacy_level),
        expires_at=fire_at + alarm_service.RING_WINDOW,
        meta={"privacy": privacy_level},
    )


# --- routines ---------------------------------------------------------------


def routine_source_id(
    run: RoutineRun, progress: routine_service.RunProgress, privacy_level: str
) -> str:
    """The run, how far through it is, and at what level.

    The count is part of the occasion because the card *is* the count: a card
    saying "1 of 3" after the second step was ticked would be worse than no
    card. Ticking a step therefore withdraws the old card and queues a new one,
    which is the same shape a snoozed dose uses.
    """
    done = progress.done + progress.skipped
    return f"{run.id}:{done}:{privacy_level}"


def routine_is_showable(run: RoutineRun, now: datetime) -> bool:
    """Whether today's run is still somebody's business.

    A finished run loses its card: section 31 keeps the robot additive, and a
    "2 of 3" card that stayed up after the routine was completed would be the
    robot disagreeing with the app.
    """
    if run.status not in ("scheduled", "in_progress"):
        return False
    zone = recurrence.zone_for(run.routine.timezone)
    return run.local_date == recurrence.local_today(zone, now)


def build_routine(
    run: RoutineRun,
    progress: routine_service.RunProgress,
    *,
    privacy_level: str,
    has_input: bool,
    chime: bool,
) -> queue.PresentationRequest:
    """One routine card (section 33's second example).

    ``full`` shows the routine's name, the progress and the next step;
    ``name_only`` drops the step, because a step title is the part that says
    what the routine is actually for; ``private`` drops the name too.
    """
    lines = [productivity_wording.progress_sentence(progress.done, progress.total)]
    if privacy_level == "full" and progress.next_step is not None:
        lines.append(productivity_wording.next_step_sentence(progress.next_step.title))
    if not has_input:
        lines.append(wording.USE_THE_APP)

    title = (
        wording.PRESENTATION_TITLES[ROUTINE_TYPE]
        if privacy_level == "private"
        else run.routine.title
    )
    payload = layouts.build_payload(
        "STATUS",
        title=title,
        lines=lines,
        actions=list(ROUTINE_ACTIONS) if has_input else [],
        sensitive=privacy_level != "private",
        chime="reminder" if chime else None,
    )
    # Until the end of the person's own day: a routine card is progress through
    # today, and tomorrow's run is a different card.
    zone = recurrence.zone_for(run.routine.timezone)
    local_end = datetime.combine(
        run.local_date + timedelta(days=1), time(0, 0), tzinfo=zone
    )
    return queue.PresentationRequest(
        presentation_type=ROUTINE_TYPE,
        layout="STATUS",
        payload=payload,
        source=SOURCE,
        source_id=routine_source_id(run, progress, privacy_level),
        expires_at=local_end,
        meta={"privacy": privacy_level},
    )


# --- queueing ---------------------------------------------------------------


def _context(
    db: Session, device: Device, now: datetime, mode: modes.RobotMode | None
) -> tuple[modes.RobotMode, preferences.EffectivePreferences, dict[str, str], str]:
    resolved_mode = mode or modes.resolve(db, device, now)
    _, resolved = preferences.resolved_for(db, device, now)
    states = capability_service.capability_map(db, device, now)
    return resolved_mode, resolved, states, privacy_level_for(resolved, resolved_mode)


def queue_for_task(
    db: Session,
    device: Device,
    task: Task,
    now: datetime,
    *,
    mode: modes.RobotMode | None = None,
) -> DevicePresentation | None:
    """Queues a card for one task, if it is due and cards are switched on."""
    if not task_is_due(task, now):
        return None
    resolved_mode, resolved, states, level = _context(db, device, now, mode)
    if not enabled(resolved):
        return None
    request = build_task(
        task,
        privacy_level=level,
        local_today=recurrence.local_today(recurrence.zone_for(task.timezone), now),
        has_input=capability_service.has_input(states),
        chime=capability_service.can_play_chime(states),
    )
    return queue.queue(db, device, request, now, mode=resolved_mode)


def queue_for_occurrence(
    db: Session,
    device: Device,
    occurrence: GeneralReminderOccurrence,
    now: datetime,
    *,
    mode: modes.RobotMode | None = None,
) -> DevicePresentation | None:
    """Queues a card for one reminder occurrence, if it is waiting."""
    if not reminder_is_due(occurrence, now):
        return None
    resolved_mode, resolved, states, level = _context(db, device, now, mode)
    if not enabled(resolved):
        return None
    speak = (
        # Reuses the message read-aloud switch rather than inventing a fourth:
        # section 43's conservative default is what matters, and a reminder is
        # the same kind of thing as a message in a room with people in it.
        resolved.read_messages_aloud
        and capability_service.can_speak(states)
        and not modes.suppresses_audio(resolved_mode.mode)
        and level == "full"
    )
    request = build_reminder(
        occurrence,
        privacy_level=level,
        has_input=capability_service.has_input(states),
        speak=speak,
        chime=capability_service.can_play_chime(states),
    )
    return queue.queue(db, device, request, now, mode=resolved_mode)


def queue_for_alarm(
    db: Session,
    device: Device,
    alarm: Alarm,
    fire_at: datetime,
    now: datetime,
    *,
    mode: modes.RobotMode | None = None,
) -> DevicePresentation | None:
    """Queues a card for an alarm whose moment is now."""
    resolved_mode, resolved, states, level = _context(db, device, now, mode)
    if not enabled(resolved):
        return None
    request = build_alarm(
        alarm,
        fire_at,
        privacy_level=level,
        has_input=capability_service.has_input(states),
        chime=capability_service.can_play_chime(states),
    )
    return queue.queue(db, device, request, now, mode=resolved_mode)


def queue_for_run(
    db: Session,
    device: Device,
    run: RoutineRun,
    now: datetime,
    *,
    mode: modes.RobotMode | None = None,
) -> DevicePresentation | None:
    """Queues a progress card for today's run, if it is still open."""
    if not routine_is_showable(run, now):
        return None
    resolved_mode, resolved, states, level = _context(db, device, now, mode)
    if not enabled(resolved):
        return None
    progress = routine_service.progress(run)
    if progress.total == 0:
        return None
    request = build_routine(
        run,
        progress,
        privacy_level=level,
        has_input=capability_service.has_input(states),
        chime=capability_service.can_play_chime(states),
    )
    return queue.queue(db, device, request, now, mode=resolved_mode)


def cancel_all(
    db: Session, device: Device, now: datetime, *, reason: str = "preference_changed"
) -> int:
    """Withdraws every daily-life card (section 31).

    What switching the preference off does, and what a device losing its screen
    does. The underlying task, reminder, alarm and routine are untouched -- that
    is the whole of section 31 in one function.
    """
    return queue.cancel_types(
        db, device.id, presentation_types=TYPES, reason=reason, now=now
    )


def task_window_bounds(now: datetime) -> tuple[datetime, datetime]:
    """The instants a task's ``due_at`` must lie between to have a card.

    Exposed so the reconciler's query and ``task_is_due`` cannot disagree about
    the window -- the query narrows, this function decides.
    """
    return now - TASK_TRAIL, now + TASK_LEAD


def alarms_ringing_now(
    db: Session, profile_id: uuid.UUID, now: datetime
) -> list[tuple[Alarm, datetime]]:
    """Enabled alarms whose moment is within the ring window, with the moment.

    The moment is returned as well as the alarm because the dedupe key needs
    it: without it a daily alarm would fold every morning into one card.
    """
    out: list[tuple[Alarm, datetime]] = []
    for alarm in alarm_service.list_alarms(db, profile_id, enabled_only=True):
        if not alarm_service.is_ringing(alarm, now):
            continue
        pattern = alarm_service.pattern_for(alarm)
        zone = recurrence.zone_for(alarm.timezone)
        today = recurrence.local_today(zone, now)
        for moment in recurrence.occurrences(
            pattern, today - timedelta(days=1), today + timedelta(days=1)
        ):
            if now - alarm_service.RING_WINDOW <= moment.scheduled_for <= now:
                out.append((alarm, moment.scheduled_for))
                break
    return out


def due_tasks(db: Session, profile_id: uuid.UUID, now: datetime) -> list[Task]:
    """Open tasks whose card window includes now."""
    low, high = task_window_bounds(now)
    rows = (
        db.execute(
            select(Task).where(
                Task.profile_id == profile_id,
                Task.status == "open",
                Task.due_at.is_not(None),
                Task.due_at >= low,
                Task.due_at <= high,
            )
        )
        .scalars()
        .all()
    )
    return [task for task in rows if task_is_due(task, now)]


def due_occurrences(
    db: Session, profile_id: uuid.UUID, now: datetime
) -> list[GeneralReminderOccurrence]:
    """Reminder occurrences that are waiting for an answer right now."""
    rows = reminder_service.list_occurrences(
        db, profile_id, statuses=("scheduled", "snoozed")
    )
    return [row for row in rows if reminder_is_due(row, now)]


def open_runs(db: Session, profile_id: uuid.UUID, now: datetime) -> list[RoutineRun]:
    """Today's runs that are still open."""
    runs = routine_service.runs_for_today(db, profile_id, now)
    return [run for run in runs if routine_is_showable(run, now)]


__all__ = [
    "ALARM_TYPE",
    "REMINDER_TYPE",
    "ROUTINE_TYPE",
    "SOURCE",
    "TASK_TYPE",
    "TYPES",
    "alarm_source_id",
    "alarms_ringing_now",
    "build_alarm",
    "build_reminder",
    "build_routine",
    "build_task",
    "cancel_all",
    "due_occurrences",
    "due_tasks",
    "enabled",
    "open_runs",
    "privacy_level_for",
    "queue_for_alarm",
    "queue_for_occurrence",
    "queue_for_run",
    "queue_for_task",
    "reminder_is_due",
    "reminder_source_id",
    "routine_is_showable",
    "routine_source_id",
    "task_is_due",
    "task_source_id",
    "task_window_bounds",
]
