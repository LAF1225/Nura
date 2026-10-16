"""Tasks, reminders, alarms and routines over HTTP.

PRD 12, sections 52-56, 58 and 74.

Every route is nested under the profile the records belong to and resolves it
through ``OwnedProfile``, so the authorization chain is the one the health
record, medication, symptom and appointment routes already use: *a task, a
reminder, an alarm or a routine is reachable only through a profile the
signed-in account owns*, and anything else is a 404 rather than a 403
(section 74).

The chain is complete at every depth. A reminder occurrence is fetched by
profile *and* id; a routine step by profile *and* routine *and* id; a step
completion by profile *and* run *and* step. There is no route here that takes
an id and works out who it belongs to afterwards.

**One caregiver route, and it is the only one.** ``/care/routines`` uses
``CaregiverScope`` and requires the ``routines`` permission (section 56). There
is no caregiver route anywhere that reaches a task, an alarm or a general
reminder, which is how section 42 is kept: not by filtering, but by there being
nothing to filter.

**Routine suggestions go through PRD 9's existing endpoint.** Section 16 says
to reuse ``caregiver_suggestions``, and that is exactly what the three new
action types do -- ``POST /profiles/{id}/caregiver-suggestions`` with
``action_type: add_routine`` is a caregiver proposing a routine. A second
create endpoint would be a second mechanism for the thing PRD 9 section 21 built
once, and the one that mattered -- approval through the ordinary routine
service -- would then have two ways in.

The routes are written out rather than generated. They are repetitive, and
that is the point: this is the surface that decides whether somebody's day can
be read, and being able to read each one in full is worth more here than
brevity.
"""

import logging
import uuid
from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import CaregiverScope, DbSession, Now, OwnedProfile, http_error
from app.models import (
    Alarm,
    GeneralReminder,
    GeneralReminderOccurrence,
    Routine,
    RoutineRun,
    Task,
)
from app.models.productivity import MAX_REMINDER_SNOOZES
from app.schemas.productivity import (
    AlarmCreate,
    AlarmListRead,
    AlarmRead,
    AlarmSaved,
    AlarmUpdate,
    CaregiverRoutineListRead,
    CaregiverRoutineRead,
    DailyLifeSummaryRead,
    OccurrenceAction,
    OccurrenceSaved,
    OccurrenceSnooze,
    ReminderCountsRead,
    ReminderCreate,
    ReminderDetailRead,
    ReminderListRead,
    ReminderOccurrenceRead,
    ReminderRead,
    ReminderSaved,
    ReminderUpdate,
    RoutineCountsRead,
    RoutineCreate,
    RoutineListRead,
    RoutineRead,
    RoutineRunListRead,
    RoutineRunRead,
    RoutineSaved,
    RoutineStepRead,
    RoutineUpdate,
    RunActionRead,
    StepCompletionInput,
    StepCompletionRead,
    TaskAction,
    TaskCountsRead,
    TaskCreate,
    TaskListRead,
    TaskRead,
    TaskSaved,
    TaskUpdate,
)
from app.services.caregivers import care_view
from app.services.errors import DomainError
from app.services.productivity import alarms as alarm_service
from app.services.productivity import reminders as reminder_service
from app.services.productivity import routines as routine_service
from app.services.productivity import summary as summary_service
from app.services.productivity import tasks as task_service
from app.services.productivity import wording

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/profiles/{profile_id}", tags=["daily life"])

NO_CONTENT = status.HTTP_204_NO_CONTENT
CREATED = status.HTTP_201_CREATED


# --- shared plumbing --------------------------------------------------------


def _today_for(zone: str, now: datetime) -> date:
    return task_service.today_date(zone, now)


def _task_read(task: Task, now: datetime) -> TaskRead:
    """One task with its labels rendered.

    The reference "today" is today in the *task's own* zone, so a task set in
    London reads "Tomorrow" on London's calendar. For most tasks that is the
    user's calendar too; while travelling it is the more useful of the two
    answers, and it is the same choice PRD 7 made for an appointment.
    """
    local_today = _today_for(task.timezone, now)
    return TaskRead(
        id=task.id,
        profile_id=task.profile_id,
        title=task.title,
        notes=task.notes,
        status=task.status,  # type: ignore[arg-type]
        status_label=wording.TASK_STATUS_LABELS[task.status],
        priority=task.priority,  # type: ignore[arg-type]
        priority_label=wording.TASK_PRIORITY_LABELS[task.priority],
        due_at=task.due_at,
        due_local_date=task.due_local_date,
        timezone=task.timezone,
        due_label=wording.due_label(task.due_at, task.timezone, local_today),
        overdue=task_service.is_overdue(task, now),
        source=task.source,  # type: ignore[arg-type]
        source_label=wording.SOURCE_LABELS[task.source],
        completed_at=task.completed_at,
        archived_at=task.archived_at,
        cancelled_at=task.cancelled_at,
        content_updated_at=task.content_updated_at,
        status_changed_at=task.status_changed_at,
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


def _occurrence_read(
    occurrence: GeneralReminderOccurrence, now: datetime
) -> ReminderOccurrenceRead:
    reminder = occurrence.reminder
    return ReminderOccurrenceRead(
        id=occurrence.id,
        reminder_id=occurrence.reminder_id,
        profile_id=occurrence.profile_id,
        title=reminder.title,
        body=reminder.body,
        scheduled_for=occurrence.scheduled_for,
        local_date=occurrence.local_date,
        status=occurrence.status,  # type: ignore[arg-type]
        status_label=wording.OCCURRENCE_STATUS_LABELS[occurrence.status],
        window=reminder_service.window(occurrence, now),  # type: ignore[arg-type]
        action_at=occurrence.action_at,
        snoozed_until=occurrence.snoozed_until,
        snooze_count=occurrence.snooze_count,
        can_snooze=occurrence.snooze_count < MAX_REMINDER_SNOOZES,
        created_at=occurrence.created_at,
        updated_at=occurrence.updated_at,
    )


def _schedule_label(reminder: GeneralReminder) -> str:
    return wording.recurrence_sentence(
        recurrence=reminder.recurrence,
        time_of_day=reminder.time_of_day,
        weekdays=reminder.weekdays,
        day_of_month=reminder.day_of_month,
        start_date=reminder.start_date,
    )


def _next_occurrence_at(
    db: DbSession, reminder: GeneralReminder, now: datetime
) -> datetime | None:
    rows = reminder_service.list_occurrences(
        db,
        reminder.profile_id,
        reminder_id=reminder.id,
        statuses=("scheduled", "snoozed"),
        limit=1,
    )
    return reminder_service.due_at(rows[0]) if rows else None


def _reminder_read(
    db: DbSession, reminder: GeneralReminder, now: datetime
) -> ReminderRead:
    return ReminderRead(
        id=reminder.id,
        profile_id=reminder.profile_id,
        title=reminder.title,
        body=reminder.body,
        recurrence=reminder.recurrence,  # type: ignore[arg-type]
        recurrence_label=wording.REMINDER_RECURRENCE_LABELS[reminder.recurrence],
        schedule_label=_schedule_label(reminder),
        timezone=reminder.timezone,
        start_date=reminder.start_date,
        end_date=reminder.end_date,
        time_of_day=reminder.time_of_day,
        weekdays=reminder.weekdays,
        day_of_month=reminder.day_of_month,
        status=reminder.status,  # type: ignore[arg-type]
        status_label=wording.REMINDER_STATUS_LABELS[reminder.status],
        notification_enabled=reminder.notification_enabled,
        # Section 9: the sentence is sent when the reminder will be silent, so
        # a client cannot ship a screen that quietly leaves it out.
        notification_note=(
            None if reminder.notification_enabled else wording.NOTIFICATIONS_DISABLED
        ),
        source=reminder.source,  # type: ignore[arg-type]
        source_label=wording.SOURCE_LABELS[reminder.source],
        paused_at=reminder.paused_at,
        next_occurrence_at=_next_occurrence_at(db, reminder, now),
        created_at=reminder.created_at,
        updated_at=reminder.updated_at,
    )


def _reminder_detail(
    db: DbSession, reminder: GeneralReminder, now: datetime
) -> ReminderDetailRead:
    occurrences = reminder_service.list_occurrences(
        db, reminder.profile_id, reminder_id=reminder.id, limit=30
    )
    return ReminderDetailRead(
        **_reminder_read(db, reminder, now).model_dump(),
        occurrences=[_occurrence_read(row, now) for row in occurrences],
    )


def _alarm_read(alarm: Alarm, now: datetime) -> AlarmRead:
    return AlarmRead(
        id=alarm.id,
        profile_id=alarm.profile_id,
        label=alarm.label,
        time_of_day=alarm.time_of_day,
        timezone=alarm.timezone,
        recurrence=alarm.recurrence,  # type: ignore[arg-type]
        recurrence_label=wording.ALARM_RECURRENCE_LABELS[alarm.recurrence],
        schedule_label=wording.recurrence_sentence(
            recurrence=alarm.recurrence,
            time_of_day=alarm.time_of_day,
            weekdays=alarm.weekdays,
            start_date=alarm.on_date,
        ),
        weekdays=alarm.weekdays,
        on_date=alarm.on_date,
        enabled=alarm.enabled,
        sound_key=alarm.sound_key,  # type: ignore[arg-type]
        sound_label=wording.ALARM_SOUND_LABELS[alarm.sound_key],
        vibration=alarm.vibration,
        next_fire_at=alarm_service.next_fire(alarm, now),
        source=alarm.source,  # type: ignore[arg-type]
        created_at=alarm.created_at,
        updated_at=alarm.updated_at,
    )


def _run_read(run: RoutineRun) -> RoutineRunRead:
    progress = routine_service.progress(run)
    return RoutineRunRead(
        id=run.id,
        routine_id=run.routine_id,
        profile_id=run.profile_id,
        routine_title=run.routine.title,
        scheduled_for=run.scheduled_for,
        local_date=run.local_date,
        status=run.status,  # type: ignore[arg-type]
        status_label=wording.ROUTINE_RUN_STATUS_LABELS[run.status],
        started_at=run.started_at,
        completed_at=run.completed_at,
        total_steps=progress.total,
        completed_steps=progress.done,
        skipped_steps=progress.skipped,
        progress_label=wording.routine_run_sentence(
            done=progress.done,
            total=progress.total,
            next_title=None if progress.next_step is None else progress.next_step.title,
        ),
        next_step_id=None if progress.next_step is None else progress.next_step.id,
        next_step_title=(
            None if progress.next_step is None else progress.next_step.title
        ),
        completions=[
            StepCompletionRead(
                id=row.id,
                step_id=row.step_id,
                state=row.state,  # type: ignore[arg-type]
                state_label=wording.ROUTINE_STEP_STATE_LABELS[row.state],
                completed_at=row.completed_at,
            )
            for row in sorted(run.completions, key=lambda row: row.completed_at)
        ],
    )


def _routine_read(db: DbSession, routine: Routine, now: datetime) -> RoutineRead:
    runs = routine_service.list_runs(db, routine.profile_id, routine_id=routine.id)
    local_today = _today_for(routine.timezone, now)
    today_run = next((run for run in runs if run.local_date == local_today), None)
    return RoutineRead(
        id=routine.id,
        profile_id=routine.profile_id,
        title=routine.title,
        description=routine.description,
        schedule_type=routine.schedule_type,  # type: ignore[arg-type]
        schedule_label=wording.recurrence_sentence(
            recurrence=routine.schedule_type,
            time_of_day=routine.time_of_day,
            weekdays=routine.weekdays,
            start_date=routine.start_date,
        ),
        timezone=routine.timezone,
        time_of_day=routine.time_of_day,
        weekdays=routine.weekdays,
        start_date=routine.start_date,
        end_date=routine.end_date,
        status=routine.status,  # type: ignore[arg-type]
        status_label=wording.ROUTINE_STATUS_LABELS[routine.status],
        paused_at=routine.paused_at,
        source=routine.source,  # type: ignore[arg-type]
        source_label=wording.SOURCE_LABELS[routine.source],
        steps=[
            RoutineStepRead.model_validate(step)
            for step in sorted(routine.steps, key=lambda step: step.position)
        ],
        today_run=None if today_run is None else _run_read(today_run),
        created_at=routine.created_at,
        updated_at=routine.updated_at,
    )


def _fetch_task(db: DbSession, profile: OwnedProfile, task_id: uuid.UUID) -> Task:
    try:
        return task_service.get_task(db, profile.id, task_id)
    except DomainError as error:
        raise http_error(error) from error


def _fetch_reminder(
    db: DbSession, profile: OwnedProfile, reminder_id: uuid.UUID
) -> GeneralReminder:
    try:
        return reminder_service.get_reminder(db, profile.id, reminder_id)
    except DomainError as error:
        raise http_error(error) from error


def _fetch_occurrence(
    db: DbSession, profile: OwnedProfile, occurrence_id: uuid.UUID
) -> GeneralReminderOccurrence:
    try:
        return reminder_service.get_occurrence(db, profile.id, occurrence_id)
    except DomainError as error:
        raise http_error(error) from error


def _fetch_alarm(db: DbSession, profile: OwnedProfile, alarm_id: uuid.UUID) -> Alarm:
    try:
        return alarm_service.get_alarm(db, profile.id, alarm_id)
    except DomainError as error:
        raise http_error(error) from error


def _fetch_routine(
    db: DbSession, profile: OwnedProfile, routine_id: uuid.UUID
) -> Routine:
    try:
        return routine_service.get_routine(db, profile.id, routine_id)
    except DomainError as error:
        raise http_error(error) from error


def _fetch_run(db: DbSession, profile: OwnedProfile, run_id: uuid.UUID) -> RoutineRun:
    try:
        return routine_service.get_run(db, profile.id, run_id)
    except DomainError as error:
        raise http_error(error) from error


# --- the daily-life summary (section 58) ------------------------------------
#
# Declared before the resource routes so "daily-life" is matched as a literal
# rather than failing to parse as part of a path with an id in it.


LocalDateQuery = Annotated[
    date | None,
    Query(description="The client's own local date. Defaults to the server's."),
]


@router.get("/daily-life/summary", response_model=DailyLifeSummaryRead)
def read_daily_life_summary(
    profile: OwnedProfile, db: DbSession, now: Now, local_date: LocalDateQuery = None
) -> DailyLifeSummaryRead:
    """Counts for the Care card and the overview screen (section 58).

    Bounded: counts and one sentence, no rows. Today's own response carries the
    rows it needs.
    """
    on_date = local_date or now.date()
    summary = summary_service.build_summary(db, profile.id, on_date, now)
    return DailyLifeSummaryRead(
        profile_id=profile.id,
        local_date=summary.local_date,
        tasks=TaskCountsRead(
            due_today=summary.tasks.due_today,
            overdue=summary.tasks.overdue,
            open_total=summary.tasks.open_total,
        ),
        reminders=ReminderCountsRead(
            due_today=summary.reminders.due_today, due_now=summary.reminders.due_now
        ),
        routines=RoutineCountsRead(
            due_today=summary.routines.due_today,
            in_progress=summary.routines.in_progress,
            completed_today=summary.routines.completed_today,
        ),
        next_alarm_at=summary.next_alarm_at,
        alarm_count=summary.alarm_count,
        summary_label=wording.today_summary_sentence(
            summary.tasks.due_today,
            summary.routines.due_today,
            summary.reminders.due_today,
        ),
        has_anything=summary.has_anything,
    )


# --- tasks (section 52) -----------------------------------------------------

TaskScope = Annotated[
    str | None,
    Query(
        pattern="^(open|completed|archived)$",
        description="Which list to return. Omitted returns everything.",
    ),
]


@router.get("/tasks", response_model=TaskListRead)
def list_tasks(
    profile: OwnedProfile, db: DbSession, now: Now, scope: TaskScope = None
) -> TaskListRead:
    """This profile's tasks (section 52)."""
    rows = task_service.list_tasks(db, profile.id, scope=scope)
    open_rows = task_service.list_tasks(db, profile.id, scope="open")
    return TaskListRead(
        tasks=[_task_read(task, now) for task in rows],
        open_count=len(open_rows),
        overdue_count=sum(1 for task in open_rows if task_service.is_overdue(task, now)),
    )


@router.post("/tasks", response_model=TaskSaved, status_code=CREATED)
def create_task(
    payload: TaskCreate, profile: OwnedProfile, db: DbSession, now: Now
) -> TaskSaved:
    """Adds a task (sections 5 and 37).

    **Idempotent through ``client_task_id``.** A retry after a failed request
    returns the stored task with ``created: false``, so an offline draft cannot
    become two tasks.
    """
    existing = task_service.find_by_client_id(db, profile.id, payload.client_task_id)
    if existing is not None:
        return TaskSaved(task=_task_read(existing, now), created=False)

    try:
        task = task_service.create_task(
            db,
            profile.id,
            task_service.TaskInput(
                title=payload.title,
                notes=payload.notes,
                priority=payload.priority,
                due_at=payload.due_at,
                timezone=payload.timezone,
                client_task_id=payload.client_task_id,
            ),
            now,
        )
    except DomainError as error:
        raise http_error(error) from error
    return TaskSaved(task=_task_read(task, now), created=True)


@router.get("/tasks/{task_id}", response_model=TaskRead)
def read_task(
    task_id: uuid.UUID, profile: OwnedProfile, db: DbSession, now: Now
) -> TaskRead:
    return _task_read(_fetch_task(db, profile, task_id), now)


@router.patch("/tasks/{task_id}", response_model=TaskSaved)
def update_task(
    task_id: uuid.UUID,
    payload: TaskUpdate,
    profile: OwnedProfile,
    db: DbSession,
    now: Now,
) -> TaskSaved:
    """Edits a task's content. Cannot touch its status (section 40)."""
    task = _fetch_task(db, profile, task_id)
    fields = payload.model_dump(exclude_unset=True, exclude={"client_updated_at"})
    try:
        updated, applied = task_service.update_task(
            db, task, fields, now, client_updated_at=payload.client_updated_at
        )
    except DomainError as error:
        raise http_error(error) from error
    return TaskSaved(task=_task_read(updated, now), applied=applied, created=False)


@router.delete("/tasks/{task_id}", status_code=NO_CONTENT)
def delete_task(task_id: uuid.UUID, profile: OwnedProfile, db: DbSession) -> None:
    """Removes a task. For one entered by mistake; archiving keeps it."""
    task_service.delete_task(db, _fetch_task(db, profile, task_id))


def _task_action(
    db: DbSession,
    profile: OwnedProfile,
    task_id: uuid.UUID,
    payload: TaskAction,
    now: datetime,
    action: str,
) -> TaskSaved:
    task = _fetch_task(db, profile, task_id)
    runner = {
        "complete": task_service.complete_task,
        "reopen": task_service.reopen_task,
        "archive": task_service.archive_task,
        "cancel": task_service.cancel_task,
    }[action]
    updated, applied = runner(db, task, now, client_updated_at=payload.client_updated_at)
    return TaskSaved(task=_task_read(updated, now), applied=applied, created=False)


@router.post("/tasks/{task_id}/complete", response_model=TaskSaved)
def complete_task(
    task_id: uuid.UUID,
    profile: OwnedProfile,
    db: DbSession,
    now: Now,
    payload: TaskAction | None = None,
) -> TaskSaved:
    """Done (section 6). Sends twice, happens once."""
    return _task_action(db, profile, task_id, payload or TaskAction(), now, "complete")


@router.post("/tasks/{task_id}/reopen", response_model=TaskSaved)
def reopen_task(
    task_id: uuid.UUID,
    profile: OwnedProfile,
    db: DbSession,
    now: Now,
    payload: TaskAction | None = None,
) -> TaskSaved:
    """Undo (section 6)."""
    return _task_action(db, profile, task_id, payload or TaskAction(), now, "reopen")


@router.post("/tasks/{task_id}/archive", response_model=TaskSaved)
def archive_task(
    task_id: uuid.UUID,
    profile: OwnedProfile,
    db: DbSession,
    now: Now,
    payload: TaskAction | None = None,
) -> TaskSaved:
    """Puts a task out of the way and keeps it (section 6)."""
    return _task_action(db, profile, task_id, payload or TaskAction(), now, "archive")


@router.post("/tasks/{task_id}/cancel", response_model=TaskSaved)
def cancel_task(
    task_id: uuid.UUID,
    profile: OwnedProfile,
    db: DbSession,
    now: Now,
    payload: TaskAction | None = None,
) -> TaskSaved:
    """Records that a task is not happening, and keeps it."""
    return _task_action(db, profile, task_id, payload or TaskAction(), now, "cancel")


# --- reminders (section 53) -------------------------------------------------


@router.get("/reminders", response_model=ReminderListRead)
def list_reminders(profile: OwnedProfile, db: DbSession, now: Now) -> ReminderListRead:
    """This profile's reminders, with its occurrences brought up to date."""
    reminder_service.replenish(db, profile.id, now)
    rows = reminder_service.list_reminders(db, profile.id)
    due = reminder_service.due_occurrences(db, profile.id, now)
    return ReminderListRead(
        reminders=[_reminder_read(db, row, now) for row in rows],
        due_count=len(due),
    )


@router.post("/reminders", response_model=ReminderSaved, status_code=CREATED)
def create_reminder(
    payload: ReminderCreate, profile: OwnedProfile, db: DbSession, now: Now
) -> ReminderSaved:
    """Adds a reminder (sections 7 and 38). Idempotent through its client id."""
    existing = reminder_service.find_by_client_id(
        db, profile.id, payload.client_reminder_id
    )
    if existing is not None:
        return ReminderSaved(reminder=_reminder_detail(db, existing, now), created=False)

    try:
        reminder = reminder_service.create_reminder(
            db,
            profile.id,
            reminder_service.ReminderInput(
                title=payload.title,
                time_of_day=payload.time_of_day,
                start_date=payload.start_date,
                recurrence=payload.recurrence,
                timezone=payload.timezone,
                body=payload.body,
                end_date=payload.end_date,
                weekdays=payload.weekdays,
                day_of_month=payload.day_of_month,
                notification_enabled=payload.notification_enabled,
                client_reminder_id=payload.client_reminder_id,
            ),
            now,
        )
    except DomainError as error:
        raise http_error(error) from error
    return ReminderSaved(reminder=_reminder_detail(db, reminder, now), created=True)


@router.get("/reminders/{reminder_id}", response_model=ReminderDetailRead)
def read_reminder(
    reminder_id: uuid.UUID, profile: OwnedProfile, db: DbSession, now: Now
) -> ReminderDetailRead:
    return _reminder_detail(db, _fetch_reminder(db, profile, reminder_id), now)


@router.patch("/reminders/{reminder_id}", response_model=ReminderDetailRead)
def update_reminder(
    reminder_id: uuid.UUID,
    payload: ReminderUpdate,
    profile: OwnedProfile,
    db: DbSession,
    now: Now,
) -> ReminderDetailRead:
    """Edits a reminder, rebuilding its future occurrences if the pattern moved."""
    reminder = _fetch_reminder(db, profile, reminder_id)
    try:
        updated = reminder_service.update_reminder(
            db, reminder, payload.model_dump(exclude_unset=True), now
        )
    except DomainError as error:
        raise http_error(error) from error
    return _reminder_detail(db, updated, now)


@router.delete("/reminders/{reminder_id}", status_code=NO_CONTENT)
def delete_reminder(reminder_id: uuid.UUID, profile: OwnedProfile, db: DbSession) -> None:
    """Removes a reminder and its occurrences. Cancelling keeps them."""
    reminder_service.delete_reminder(db, _fetch_reminder(db, profile, reminder_id))


@router.post("/reminders/{reminder_id}/pause", response_model=ReminderDetailRead)
def pause_reminder(
    reminder_id: uuid.UUID, profile: OwnedProfile, db: DbSession, now: Now
) -> ReminderDetailRead:
    """Stops the occurrences and keeps the series (section 7)."""
    reminder = _fetch_reminder(db, profile, reminder_id)
    updated = reminder_service.set_paused(db, reminder, paused=True, now=now)
    return _reminder_detail(db, updated, now)


@router.post("/reminders/{reminder_id}/resume", response_model=ReminderDetailRead)
def resume_reminder(
    reminder_id: uuid.UUID, profile: OwnedProfile, db: DbSession, now: Now
) -> ReminderDetailRead:
    """Starts generating again, from now rather than filling in the gap."""
    reminder = _fetch_reminder(db, profile, reminder_id)
    updated = reminder_service.set_paused(db, reminder, paused=False, now=now)
    return _reminder_detail(db, updated, now)


@router.post("/reminders/{reminder_id}/cancel", response_model=ReminderDetailRead)
def cancel_reminder(
    reminder_id: uuid.UUID, profile: OwnedProfile, db: DbSession, now: Now
) -> ReminderDetailRead:
    """Stops a reminder for good, keeping what it already produced."""
    reminder = _fetch_reminder(db, profile, reminder_id)
    updated = reminder_service.cancel_reminder(db, reminder, now)
    return _reminder_detail(db, updated, now)


@router.get("/reminder-occurrences", response_model=list[ReminderOccurrenceRead])
def list_occurrences(
    profile: OwnedProfile,
    db: DbSession,
    now: Now,
    from_date: Annotated[date | None, Query()] = None,
    to_date: Annotated[date | None, Query()] = None,
) -> list[ReminderOccurrenceRead]:
    """Occurrences in a range of the user's own local days.

    What the phone's notification scheduler reads: it mirrors these into the
    operating system rather than re-deriving a recurrence rule (section 34).
    """
    reminder_service.replenish(db, profile.id, now)
    rows = reminder_service.list_occurrences(
        db, profile.id, from_date=from_date, to_date=to_date, limit=200
    )
    return [_occurrence_read(row, now) for row in rows]


def _occurrence_action(
    db: DbSession,
    profile: OwnedProfile,
    occurrence_id: uuid.UUID,
    payload: OccurrenceAction,
    now: datetime,
    action: str,
) -> OccurrenceSaved:
    occurrence = _fetch_occurrence(db, profile, occurrence_id)
    runner = {
        "complete": reminder_service.record_completed,
        "dismiss": reminder_service.record_dismissed,
    }[action]
    try:
        result = runner(db, occurrence, now, action_at=payload.action_at)
    except DomainError as error:
        raise http_error(error) from error
    return OccurrenceSaved(
        occurrence=_occurrence_read(result.occurrence, now), applied=result.applied
    )


@router.post(
    "/reminder-occurrences/{occurrence_id}/complete", response_model=OccurrenceSaved
)
def complete_occurrence(
    occurrence_id: uuid.UUID,
    profile: OwnedProfile,
    db: DbSession,
    now: Now,
    payload: OccurrenceAction | None = None,
) -> OccurrenceSaved:
    """Done (section 8). Not "taken" -- see the service's docstring."""
    return _occurrence_action(
        db, profile, occurrence_id, payload or OccurrenceAction(), now, "complete"
    )


@router.post(
    "/reminder-occurrences/{occurrence_id}/dismiss", response_model=OccurrenceSaved
)
def dismiss_occurrence(
    occurrence_id: uuid.UUID,
    profile: OwnedProfile,
    db: DbSession,
    now: Now,
    payload: OccurrenceAction | None = None,
) -> OccurrenceSaved:
    """Dismiss (section 8). Seen, and not being acted on."""
    return _occurrence_action(
        db, profile, occurrence_id, payload or OccurrenceAction(), now, "dismiss"
    )


@router.post(
    "/reminder-occurrences/{occurrence_id}/snooze", response_model=OccurrenceSaved
)
def snooze_occurrence(
    occurrence_id: uuid.UUID,
    profile: OwnedProfile,
    db: DbSession,
    now: Now,
    payload: OccurrenceSnooze | None = None,
) -> OccurrenceSaved:
    """Puts a reminder off, leaving it unanswered (section 8)."""
    occurrence = _fetch_occurrence(db, profile, occurrence_id)
    try:
        result = reminder_service.record_snoozed(
            db, occurrence, now, minutes=(payload or OccurrenceSnooze()).minutes
        )
    except DomainError as error:
        raise http_error(error) from error
    return OccurrenceSaved(
        occurrence=_occurrence_read(result.occurrence, now), applied=result.applied
    )


# --- alarms (section 54) ----------------------------------------------------


@router.get("/alarms", response_model=AlarmListRead)
def list_alarms(profile: OwnedProfile, db: DbSession, now: Now) -> AlarmListRead:
    """This profile's alarms, and the sentence section 11 requires beside them.

    ``limitation`` is part of the response rather than a string in the app, so
    no client can ship an alarm screen without it. **No alarm has ever fired on
    a physical phone.**
    """
    rows = alarm_service.list_alarms(db, profile.id)
    return AlarmListRead(
        alarms=[_alarm_read(alarm, now) for alarm in rows],
        enabled_count=sum(1 for alarm in rows if alarm.enabled),
        limitation=wording.ALARM_LIMITATION,
    )


@router.post("/alarms", response_model=AlarmSaved, status_code=CREATED)
def create_alarm(
    payload: AlarmCreate, profile: OwnedProfile, db: DbSession, now: Now
) -> AlarmSaved:
    """Adds an alarm (section 10). Idempotent through its client id."""
    existing = alarm_service.find_by_client_id(db, profile.id, payload.client_alarm_id)
    if existing is not None:
        return AlarmSaved(alarm=_alarm_read(existing, now), created=False)

    try:
        alarm = alarm_service.create_alarm(
            db,
            profile.id,
            alarm_service.AlarmInput(
                label=payload.label,
                time_of_day=payload.time_of_day,
                recurrence=payload.recurrence,
                timezone=payload.timezone,
                weekdays=payload.weekdays,
                on_date=payload.on_date,
                enabled=payload.enabled,
                sound_key=payload.sound_key,
                vibration=payload.vibration,
                client_alarm_id=payload.client_alarm_id,
            ),
            now,
        )
    except DomainError as error:
        raise http_error(error) from error
    return AlarmSaved(alarm=_alarm_read(alarm, now), created=True)


@router.get("/alarms/{alarm_id}", response_model=AlarmRead)
def read_alarm(
    alarm_id: uuid.UUID, profile: OwnedProfile, db: DbSession, now: Now
) -> AlarmRead:
    return _alarm_read(_fetch_alarm(db, profile, alarm_id), now)


@router.patch("/alarms/{alarm_id}", response_model=AlarmRead)
def update_alarm(
    alarm_id: uuid.UUID,
    payload: AlarmUpdate,
    profile: OwnedProfile,
    db: DbSession,
    now: Now,
) -> AlarmRead:
    """Edits an alarm, including turning it on and off (section 10)."""
    alarm = _fetch_alarm(db, profile, alarm_id)
    try:
        updated = alarm_service.update_alarm(
            db, alarm, payload.model_dump(exclude_unset=True)
        )
    except DomainError as error:
        raise http_error(error) from error
    return _alarm_read(updated, now)


@router.delete("/alarms/{alarm_id}", status_code=NO_CONTENT)
def delete_alarm(alarm_id: uuid.UUID, profile: OwnedProfile, db: DbSession) -> None:
    alarm_service.delete_alarm(db, _fetch_alarm(db, profile, alarm_id))


# --- routines (section 55) --------------------------------------------------


@router.get("/routines", response_model=RoutineListRead)
def list_routines(profile: OwnedProfile, db: DbSession, now: Now) -> RoutineListRead:
    """This profile's routines, with today's runs brought up to date."""
    routine_service.replenish(db, profile.id, now)
    rows = routine_service.list_routines(db, profile.id)
    return RoutineListRead(
        routines=[_routine_read(db, routine, now) for routine in rows],
        active_count=sum(1 for routine in rows if routine.status == "active"),
    )


@router.post("/routines", response_model=RoutineSaved, status_code=CREATED)
def create_routine(
    payload: RoutineCreate, profile: OwnedProfile, db: DbSession, now: Now
) -> RoutineSaved:
    """Adds a routine with its steps (sections 12 and 13).

    Nothing here decides that somebody should have a routine. Sections 15 and
    24: this is a person writing down what they or their clinician decided.
    """
    existing = routine_service.find_by_client_id(
        db, profile.id, payload.client_routine_id
    )
    if existing is not None:
        return RoutineSaved(routine=_routine_read(db, existing, now), created=False)

    try:
        routine = routine_service.create_routine(
            db,
            profile.id,
            routine_service.RoutineInput(
                title=payload.title,
                time_of_day=payload.time_of_day,
                start_date=payload.start_date,
                schedule_type=payload.schedule_type,
                timezone=payload.timezone,
                description=payload.description,
                weekdays=payload.weekdays,
                end_date=payload.end_date,
                client_routine_id=payload.client_routine_id,
            ),
            [
                routine_service.StepInput(title=step.title, optional=step.optional)
                for step in payload.steps
            ],
            now,
        )
    except DomainError as error:
        raise http_error(error) from error
    return RoutineSaved(routine=_routine_read(db, routine, now), created=True)


@router.get("/routines/{routine_id}", response_model=RoutineRead)
def read_routine(
    routine_id: uuid.UUID, profile: OwnedProfile, db: DbSession, now: Now
) -> RoutineRead:
    routine_service.replenish(db, profile.id, now)
    return _routine_read(db, _fetch_routine(db, profile, routine_id), now)


@router.patch("/routines/{routine_id}", response_model=RoutineRead)
def update_routine(
    routine_id: uuid.UUID,
    payload: RoutineUpdate,
    profile: OwnedProfile,
    db: DbSession,
    now: Now,
) -> RoutineRead:
    """Edits a routine, and replaces its steps if ``steps`` is sent (section 48)."""
    routine = _fetch_routine(db, profile, routine_id)
    fields = payload.model_dump(exclude_unset=True, exclude={"steps"})
    try:
        if fields:
            routine = routine_service.update_routine(db, routine, fields, now)
        if payload.steps is not None:
            routine = routine_service.replace_steps(
                db,
                routine,
                [
                    routine_service.StepInput(title=step.title, optional=step.optional)
                    for step in payload.steps
                ],
                now,
            )
    except DomainError as error:
        raise http_error(error) from error
    return _routine_read(db, routine, now)


@router.delete("/routines/{routine_id}", status_code=NO_CONTENT)
def delete_routine(routine_id: uuid.UUID, profile: OwnedProfile, db: DbSession) -> None:
    """Removes a routine, its steps and its runs. Archiving keeps the history."""
    routine_service.delete_routine(db, _fetch_routine(db, profile, routine_id))


@router.post("/routines/{routine_id}/pause", response_model=RoutineRead)
def pause_routine(
    routine_id: uuid.UUID, profile: OwnedProfile, db: DbSession, now: Now
) -> RoutineRead:
    """Stops the runs and keeps the routine (section 13)."""
    routine = _fetch_routine(db, profile, routine_id)
    updated = routine_service.set_paused(db, routine, paused=True, now=now)
    return _routine_read(db, updated, now)


@router.post("/routines/{routine_id}/resume", response_model=RoutineRead)
def resume_routine(
    routine_id: uuid.UUID, profile: OwnedProfile, db: DbSession, now: Now
) -> RoutineRead:
    """Starts generating runs again, from today."""
    routine = _fetch_routine(db, profile, routine_id)
    updated = routine_service.set_paused(db, routine, paused=False, now=now)
    return _routine_read(db, updated, now)


@router.post("/routines/{routine_id}/archive", response_model=RoutineRead)
def archive_routine(
    routine_id: uuid.UUID, profile: OwnedProfile, db: DbSession, now: Now
) -> RoutineRead:
    """Stops a routine for good and keeps its history."""
    routine = _fetch_routine(db, profile, routine_id)
    updated = routine_service.archive_routine(db, routine, now)
    return _routine_read(db, updated, now)


@router.get("/routine-runs/today", response_model=RoutineRunListRead)
def read_today_runs(profile: OwnedProfile, db: DbSession, now: Now) -> RoutineRunListRead:
    """Today's runs, in each routine's own local day (section 55)."""
    routine_service.replenish(db, profile.id, now)
    runs = routine_service.runs_for_today(db, profile.id, now)
    return RoutineRunListRead(runs=[_run_read(run) for run in runs])


@router.get("/routine-runs/{run_id}", response_model=RoutineRunRead)
def read_run(run_id: uuid.UUID, profile: OwnedProfile, db: DbSession) -> RoutineRunRead:
    return _run_read(_fetch_run(db, profile, run_id))


@router.post(
    "/routine-runs/{run_id}/steps/{step_id}/complete", response_model=RoutineRunRead
)
def complete_step(
    run_id: uuid.UUID,
    step_id: uuid.UUID,
    profile: OwnedProfile,
    db: DbSession,
    now: Now,
    payload: StepCompletionInput | None = None,
) -> RoutineRunRead:
    """Ticks a step (sections 14 and 39).

    Idempotent: sending the same completion twice leaves one row, so an offline
    queue that retries cannot invent progress. The whole run comes back, so a
    client gets its new progress line without a second request.
    """
    body = payload or StepCompletionInput()
    run = _fetch_run(db, profile, run_id)
    try:
        step = routine_service.get_step(db, run.routine, step_id)
        routine_service.complete_step(
            db,
            run,
            step,
            now,
            state=body.state,
            completed_at=body.completed_at,
            client_completion_id=body.client_completion_id,
        )
    except DomainError as error:
        raise http_error(error) from error
    return _run_read(_fetch_run(db, profile, run_id))


@router.delete(
    "/routine-runs/{run_id}/steps/{step_id}/complete", response_model=RoutineRunRead
)
def clear_step(
    run_id: uuid.UUID, step_id: uuid.UUID, profile: OwnedProfile, db: DbSession
) -> RoutineRunRead:
    """Un-ticks a step. A checklist needs Undo as much as a task does."""
    run = _fetch_run(db, profile, run_id)
    try:
        step = routine_service.get_step(db, run.routine, step_id)
        routine_service.clear_step(db, run, step)
    except DomainError as error:
        raise http_error(error) from error
    return _run_read(_fetch_run(db, profile, run_id))


@router.post("/routine-runs/{run_id}/complete", response_model=RunActionRead)
def complete_run(
    run_id: uuid.UUID, profile: OwnedProfile, db: DbSession, now: Now
) -> RunActionRead:
    """Marks a whole run done, with or without every step ticked (section 14)."""
    run = _fetch_run(db, profile, run_id)
    try:
        updated, applied = routine_service.complete_run(db, run, now)
    except DomainError as error:
        raise http_error(error) from error
    return RunActionRead(run=_run_read(updated), applied=applied)


@router.post("/routine-runs/{run_id}/skip", response_model=RunActionRead)
def skip_run(
    run_id: uuid.UUID, profile: OwnedProfile, db: DbSession, now: Now
) -> RunActionRead:
    """Records that a run is not happening today.

    Deliberately not ``missed``: skipping is a decision, missing is what the
    end of a day concluded.
    """
    run = _fetch_run(db, profile, run_id)
    try:
        updated, applied = routine_service.skip_run(db, run, now)
    except DomainError as error:
        raise http_error(error) from error
    return RunActionRead(run=_run_read(updated), applied=applied)


# --- the caregiver's routines (section 56) ----------------------------------


@router.get("/care/routines", response_model=CaregiverRoutineListRead)
def read_care_routines(
    scope: CaregiverScope, db: DbSession, now: Now
) -> CaregiverRoutineListRead:
    """What a caregiver with ``routines`` may see (sections 16, 42 and 56).

    ``CaregiverScope`` rather than ``OwnedProfile``, which section 56 asks for
    explicitly: the owner has their own, richer routes for all of this. The
    permission is required here and re-checked at approval if the caregiver
    goes on to suggest something.

    **This is the only caregiver route in PRD 12.** There is none for tasks,
    alarms or general reminders, which is how section 42 is kept -- not by
    filtering a response, but by there being no response to filter.
    """
    try:
        scope.require("routines")
    except DomainError as error:
        raise http_error(error) from error

    views = care_view.routines_for(db, scope.profile.id, now)
    return CaregiverRoutineListRead(
        routines=[
            CaregiverRoutineRead(
                routine_id=view.routine_id,
                title=view.title,
                schedule_label=view.schedule_label,
                step_count=view.step_count,
                paused=view.paused,
                today_status=view.today_status,  # type: ignore[arg-type]
                today_done=view.today_done,
                today_total=view.today_total,
                today_progress_label=(
                    None
                    if view.today_done is None or view.today_total is None
                    else wording.progress_sentence(view.today_done, view.today_total)
                ),
            )
            for view in views
        ],
        scope_note=wording.CAREGIVER_ROUTINES_ONLY,
    )
