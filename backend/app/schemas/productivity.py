"""Task, reminder, alarm and routine request/response models.

PRD 12, sections 5, 7, 8, 10, 12, 14, 51, 52-58 and 74.

Models, never ORM rows: the API's shape is decided here rather than falling out
of whatever columns a table happens to have.

**Every Literal is guarded against the tuple the database CHECK constraints are
built from** (section 51). A value set that drifts between the API and the
database is a request Postgres rejects at three in the morning; these asserts
turn it into a startup failure instead. The same pattern as every other schema
module in this codebase.

**No model carries a profile id.** The profile is in the path and resolved
through ``OwnedProfile`` before the body is read, so there is no field anywhere
below that could name a person (section 74). The same reason the assistant's
tools have no profile argument.

**``source`` is not writable.** A client may create something as ``user`` and
nothing else: ``assistant`` is set by the assistant's own tool path and
``caregiver_suggestion`` by an approval, so provenance is always the server's
record of how a write arrived (section 43).

**Labels travel with the rows.** A recurrence sentence, a due label and a
status label are rendered by ``services.productivity.wording`` and sent, rather
than reassembled by the client -- which is PRD 7's choice, and the reason the
honest alarm sentence cannot be dropped by a client that forgot about it.
"""

import uuid
from datetime import date, datetime, time
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import (
    ALARM_RECURRENCES,
    ALARM_SOUND_KEYS,
    DAILY_LIFE_CAPABILITY_KEYS,
    DAILY_LIFE_CAPABILITY_STATES,
    DAILY_LIFE_SOURCES,
    REMINDER_OCCURRENCE_STATUSES,
    REMINDER_RECURRENCES,
    REMINDER_STATUSES,
    ROUTINE_RUN_STATUSES,
    ROUTINE_SCHEDULE_TYPES,
    ROUTINE_STATUSES,
    ROUTINE_STEP_STATES,
    TASK_PRIORITIES,
    TASK_STATUSES,
)
from app.models.productivity import (
    BODY_MAX_LENGTH,
    LABEL_MAX_LENGTH,
    MAX_ROUTINE_STEPS,
    NOTES_MAX_LENGTH,
    TITLE_MAX_LENGTH,
)
from app.models.symptom import CLIENT_ID_MAX_LENGTH

TaskStatus = Literal["open", "completed", "archived", "cancelled"]
TaskPriority = Literal["normal", "important"]
DailyLifeSource = Literal["user", "assistant", "caregiver_suggestion", "import_future"]
ReminderRecurrence = Literal["one_time", "daily", "selected_days", "weekly", "monthly"]
ReminderStatus = Literal["active", "paused", "completed", "cancelled"]
OccurrenceStatus = Literal[
    "scheduled", "completed", "dismissed", "snoozed", "missed", "cancelled"
]
AlarmRecurrence = Literal["one_time", "daily", "selected_days"]
AlarmSound = Literal["default", "gentle", "chime", "bell"]
RoutineScheduleType = Literal["daily", "selected_days"]
RoutineStatus = Literal["active", "paused", "archived"]
RoutineRunStatus = Literal[
    "scheduled", "in_progress", "completed", "skipped", "missed", "cancelled"
]
RoutineStepState = Literal["completed", "skipped"]
CapabilityKey = Literal[
    "tasks", "reminders", "alarms", "routines", "weather", "news", "external_calendar"
]
CapabilityState = Literal["available", "not_configured", "unavailable"]

#: Where an occurrence or a task sits relative to now. Derived on every read,
#: never stored -- the same four words a dose uses, so a reminder and a dose at
#: the same minute agree.
ItemWindow = Literal["upcoming", "due", "overdue", "completed"]

assert set(TASK_STATUSES) == set(TaskStatus.__args__)  # type: ignore[attr-defined]
assert set(TASK_PRIORITIES) == set(TaskPriority.__args__)  # type: ignore[attr-defined]
assert set(DAILY_LIFE_SOURCES) == set(DailyLifeSource.__args__)  # type: ignore[attr-defined]
assert set(REMINDER_RECURRENCES) == set(ReminderRecurrence.__args__)  # type: ignore[attr-defined]
assert set(REMINDER_STATUSES) == set(ReminderStatus.__args__)  # type: ignore[attr-defined]
assert set(REMINDER_OCCURRENCE_STATUSES) == set(OccurrenceStatus.__args__)  # type: ignore[attr-defined]
assert set(ALARM_RECURRENCES) == set(AlarmRecurrence.__args__)  # type: ignore[attr-defined]
assert set(ALARM_SOUND_KEYS) == set(AlarmSound.__args__)  # type: ignore[attr-defined]
assert set(ROUTINE_SCHEDULE_TYPES) == set(RoutineScheduleType.__args__)  # type: ignore[attr-defined]
assert set(ROUTINE_STATUSES) == set(RoutineStatus.__args__)  # type: ignore[attr-defined]
assert set(ROUTINE_RUN_STATUSES) == set(RoutineRunStatus.__args__)  # type: ignore[attr-defined]
assert set(ROUTINE_STEP_STATES) == set(RoutineStepState.__args__)  # type: ignore[attr-defined]
assert set(DAILY_LIFE_CAPABILITY_KEYS) == set(CapabilityKey.__args__)  # type: ignore[attr-defined]
assert set(DAILY_LIFE_CAPABILITY_STATES) == set(CapabilityState.__args__)  # type: ignore[attr-defined]

Title = Annotated[str, Field(min_length=1, max_length=TITLE_MAX_LENGTH)]
Label = Annotated[str, Field(min_length=1, max_length=LABEL_MAX_LENGTH)]
Notes = Annotated[str, Field(max_length=NOTES_MAX_LENGTH)]
Body = Annotated[str, Field(max_length=BODY_MAX_LENGTH)]
ClientId = Annotated[str, Field(min_length=1, max_length=CLIENT_ID_MAX_LENGTH)]
TimezoneName = Annotated[str, Field(min_length=1, max_length=64)]
Weekday = Annotated[int, Field(ge=0, le=6)]
Weekdays = Annotated[list[Weekday], Field(min_length=1, max_length=7)]
DayOfMonth = Annotated[int, Field(ge=1, le=31)]
#: The snooze durations PRD 5 offers, reused so a reminder and a dose behave
#: the same way (section 8).
SnoozeMinutes = Literal[10, 30, 60]


def _tidy(value: str | None) -> str | None:
    """Trims, and treats a blank string as nothing.

    Without this, clearing a notes field would store an empty string that
    renders as a note the user did not write.
    """
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


# --- tasks ------------------------------------------------------------------


class TaskRead(BaseModel):
    """One task, with its labels rendered (sections 5 and 6)."""

    id: uuid.UUID
    profile_id: uuid.UUID
    title: str
    notes: str | None
    status: TaskStatus
    status_label: str
    priority: TaskPriority
    priority_label: str
    due_at: datetime | None
    due_local_date: date | None
    timezone: str
    #: "Today, 4:00 PM". Null for a task with no due date, which is a normal
    #: task and not an incomplete one.
    due_label: str | None
    #: Derived on every read. ``overdue`` is a fact about a time and nothing
    #: follows from it (section 18).
    overdue: bool
    source: DailyLifeSource
    source_label: str
    completed_at: datetime | None
    archived_at: datetime | None
    cancelled_at: datetime | None
    #: Section 40's two timestamps, sent so a client knows what it is editing
    #: against.
    content_updated_at: datetime | None
    status_changed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class TaskCreate(BaseModel):
    """The body of a task creation (sections 5, 6 and 37)."""

    title: Title
    notes: Notes | None = None
    priority: TaskPriority = "normal"
    due_at: datetime | None = None
    #: The zone the due date was chosen in. Defaults to UTC, which is only
    #: right by accident, so the app always sends its own.
    timezone: TimezoneName = "UTC"
    #: Makes a retry free (section 37): the same id twice is one task.
    client_task_id: ClientId | None = None

    @field_validator("notes")
    @classmethod
    def _tidy_notes(cls, value: str | None) -> str | None:
        return _tidy(value)


class TaskUpdate(BaseModel):
    """A content edit. Deliberately cannot touch the status (section 40).

    There is no ``status`` field here, and that is the whole point: a title edit
    arriving from a device that was offline must not be able to undo a
    completion made since. Status changes go through the four action endpoints,
    which compare against ``status_changed_at`` instead.
    """

    title: Title | None = None
    notes: Notes | None = None
    priority: TaskPriority | None = None
    due_at: datetime | None = None
    timezone: TimezoneName | None = None
    #: When the user made this edit -- not when the request arrived. An offline
    #: edit may be hours old by the time it syncs, and this is what lets the
    #: server keep a newer one (section 40).
    client_updated_at: datetime | None = None

    @field_validator("notes")
    @classmethod
    def _tidy_notes(cls, value: str | None) -> str | None:
        return _tidy(value)


class TaskAction(BaseModel):
    """The body of Complete, Reopen, Archive or Cancel.

    Everything optional: the common case is an empty body. ``client_updated_at``
    is what an offline queue sends so a stale action cannot overwrite a newer
    one.
    """

    client_updated_at: datetime | None = None


class TaskSaved(BaseModel):
    """The stored task, and whether this request is what created or changed it.

    ``applied`` is False when the server already had something newer, in which
    case the body still carries the stored task so a client can adopt it
    (sections 37 and 40).
    """

    task: TaskRead
    applied: bool = True
    #: False on a replayed create, so a client knows it did not make a second.
    created: bool = True


class TaskListRead(BaseModel):
    tasks: list[TaskRead]
    open_count: int
    overdue_count: int


# --- reminders --------------------------------------------------------------


class ReminderOccurrenceRead(BaseModel):
    """One moment, and what happened at it (section 8)."""

    id: uuid.UUID
    reminder_id: uuid.UUID
    profile_id: uuid.UUID
    #: Carried so a notification list or a Today row can render without a
    #: second request. The reminder's own title, never anything else.
    title: str
    body: str | None
    scheduled_for: datetime
    local_date: date
    status: OccurrenceStatus
    status_label: str
    window: ItemWindow
    action_at: datetime | None
    snoozed_until: datetime | None
    snooze_count: int
    can_snooze: bool
    created_at: datetime
    updated_at: datetime


class ReminderRead(BaseModel):
    """One reminder series, with its recurrence written out."""

    id: uuid.UUID
    profile_id: uuid.UUID
    title: str
    body: str | None
    recurrence: ReminderRecurrence
    recurrence_label: str
    #: "Every day at 7:30 AM" -- the whole pattern as one sentence.
    schedule_label: str
    timezone: str
    start_date: date
    end_date: date | None
    time_of_day: time
    weekdays: list[int] | None
    day_of_month: int | None
    status: ReminderStatus
    status_label: str
    notification_enabled: bool
    #: Section 9: said when notifications are stored but will be silent.
    notification_note: str | None
    source: DailyLifeSource
    source_label: str
    paused_at: datetime | None
    #: The next moment still waiting, if there is one.
    next_occurrence_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ReminderDetailRead(ReminderRead):
    """A reminder and its recent occurrences."""

    occurrences: list[ReminderOccurrenceRead]


class ReminderCreate(BaseModel):
    title: Title
    time_of_day: time
    start_date: date
    recurrence: ReminderRecurrence = "one_time"
    timezone: TimezoneName = "UTC"
    body: Body | None = None
    end_date: date | None = None
    weekdays: Weekdays | None = None
    day_of_month: DayOfMonth | None = None
    notification_enabled: bool = True
    client_reminder_id: ClientId | None = None

    @field_validator("body")
    @classmethod
    def _tidy_body(cls, value: str | None) -> str | None:
        return _tidy(value)


class ReminderUpdate(BaseModel):
    title: Title | None = None
    body: Body | None = None
    recurrence: ReminderRecurrence | None = None
    timezone: TimezoneName | None = None
    start_date: date | None = None
    end_date: date | None = None
    time_of_day: time | None = None
    weekdays: Weekdays | None = None
    day_of_month: DayOfMonth | None = None
    notification_enabled: bool | None = None

    @field_validator("body")
    @classmethod
    def _tidy_body(cls, value: str | None) -> str | None:
        return _tidy(value)


class ReminderSaved(BaseModel):
    reminder: ReminderDetailRead
    created: bool = True


class ReminderListRead(BaseModel):
    reminders: list[ReminderRead]
    #: Occurrences waiting for an answer right now.
    due_count: int


class OccurrenceAction(BaseModel):
    """The body of Done or Dismiss. ``action_at`` is when the person pressed it."""

    action_at: datetime | None = None


class OccurrenceSnooze(BaseModel):
    minutes: SnoozeMinutes = 10


class OccurrenceSaved(BaseModel):
    occurrence: ReminderOccurrenceRead
    applied: bool


# --- alarms -----------------------------------------------------------------


class AlarmRead(BaseModel):
    """One alarm, and the honest sentence about what an alarm is here."""

    id: uuid.UUID
    profile_id: uuid.UUID
    label: str
    time_of_day: time
    timezone: str
    recurrence: AlarmRecurrence
    recurrence_label: str
    #: "Weekdays at 7:00 AM".
    schedule_label: str
    weekdays: list[int] | None
    on_date: date | None
    enabled: bool
    sound_key: AlarmSound
    sound_label: str
    vibration: bool
    #: When it next goes off, derived on every read. Null for a disabled alarm
    #: and for a one-off whose day has gone.
    next_fire_at: datetime | None
    source: DailyLifeSource
    created_at: datetime
    updated_at: datetime


class AlarmCreate(BaseModel):
    label: Label
    time_of_day: time
    recurrence: AlarmRecurrence = "one_time"
    timezone: TimezoneName = "UTC"
    weekdays: Weekdays | None = None
    on_date: date | None = None
    enabled: bool = True
    sound_key: AlarmSound = "default"
    vibration: bool = True
    client_alarm_id: ClientId | None = None


class AlarmUpdate(BaseModel):
    label: Label | None = None
    time_of_day: time | None = None
    timezone: TimezoneName | None = None
    recurrence: AlarmRecurrence | None = None
    weekdays: Weekdays | None = None
    on_date: date | None = None
    enabled: bool | None = None
    sound_key: AlarmSound | None = None
    vibration: bool | None = None


class AlarmSaved(BaseModel):
    alarm: AlarmRead
    created: bool = True


class AlarmListRead(BaseModel):
    """The list, and the sentence section 11 requires beside it.

    ``limitation`` is sent with every response rather than written into the
    app, so a client cannot ship a screen that quietly leaves it out. **No
    alarm has ever fired on a physical phone.**
    """

    alarms: list[AlarmRead]
    enabled_count: int
    limitation: str


# --- routines ---------------------------------------------------------------


class RoutineStepRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    routine_id: uuid.UUID
    title: str
    position: int
    optional: bool


class RoutineStepInput(BaseModel):
    title: Title
    optional: bool = False


class StepCompletionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    step_id: uuid.UUID
    state: RoutineStepState
    state_label: str
    completed_at: datetime


class RoutineRunRead(BaseModel):
    """One scheduled instance, and how far through it somebody is."""

    id: uuid.UUID
    routine_id: uuid.UUID
    profile_id: uuid.UUID
    routine_title: str
    scheduled_for: datetime
    local_date: date
    status: RoutineRunStatus
    status_label: str
    started_at: datetime | None
    completed_at: datetime | None
    #: Derived from the completion rows on every read.
    total_steps: int
    completed_steps: int
    skipped_steps: int
    #: "2 of 3 complete. Next: Stretch" -- section 33's own line.
    progress_label: str
    next_step_id: uuid.UUID | None
    next_step_title: str | None
    completions: list[StepCompletionRead]


class RoutineRead(BaseModel):
    id: uuid.UUID
    profile_id: uuid.UUID
    title: str
    description: str | None
    schedule_type: RoutineScheduleType
    #: "Every day at 7:30 AM".
    schedule_label: str
    timezone: str
    time_of_day: time
    weekdays: list[int] | None
    start_date: date
    end_date: date | None
    status: RoutineStatus
    status_label: str
    paused_at: datetime | None
    source: DailyLifeSource
    source_label: str
    steps: list[RoutineStepRead]
    #: Today's run, if the routine runs today. Null is "not today", which is
    #: different from a run nobody has started.
    today_run: RoutineRunRead | None
    created_at: datetime
    updated_at: datetime


class RoutineCreate(BaseModel):
    title: Title
    time_of_day: time
    start_date: date
    schedule_type: RoutineScheduleType = "daily"
    timezone: TimezoneName = "UTC"
    description: Body | None = None
    weekdays: Weekdays | None = None
    end_date: date | None = None
    steps: Annotated[
        list[RoutineStepInput], Field(min_length=1, max_length=MAX_ROUTINE_STEPS)
    ]
    client_routine_id: ClientId | None = None

    @field_validator("description")
    @classmethod
    def _tidy_description(cls, value: str | None) -> str | None:
        return _tidy(value)


class RoutineUpdate(BaseModel):
    """An edit. ``steps`` replaces the whole list, in the order given.

    The whole list rather than a diff, which is what makes Move Up, Move Down
    and drag-and-drop one operation and removes the duplicate-position bugs
    entirely (section 48).
    """

    title: Title | None = None
    description: Body | None = None
    schedule_type: RoutineScheduleType | None = None
    timezone: TimezoneName | None = None
    time_of_day: time | None = None
    weekdays: Weekdays | None = None
    start_date: date | None = None
    end_date: date | None = None
    steps: (
        Annotated[
            list[RoutineStepInput], Field(min_length=1, max_length=MAX_ROUTINE_STEPS)
        ]
        | None
    ) = None

    @field_validator("description")
    @classmethod
    def _tidy_description(cls, value: str | None) -> str | None:
        return _tidy(value)


class RoutineSaved(BaseModel):
    routine: RoutineRead
    created: bool = True


class RoutineListRead(BaseModel):
    routines: list[RoutineRead]
    active_count: int


class RoutineRunListRead(BaseModel):
    runs: list[RoutineRunRead]


class StepCompletionInput(BaseModel):
    """Marking a step done, or passing over an optional one (section 39)."""

    state: RoutineStepState = "completed"
    #: When the person actually ticked it, for an offline queue.
    completed_at: datetime | None = None
    #: Makes a retried completion one row rather than two (section 39).
    client_completion_id: ClientId | None = None


class RunActionRead(BaseModel):
    run: RoutineRunRead
    applied: bool


# --- the daily-life summary (section 58) -------------------------------------


class TaskCountsRead(BaseModel):
    due_today: int
    overdue: int
    open_total: int


class ReminderCountsRead(BaseModel):
    due_today: int
    due_now: int


class RoutineCountsRead(BaseModel):
    due_today: int
    in_progress: int
    completed_today: int


class DailyLifeSummaryRead(BaseModel):
    """Bounded on purpose (section 58): counts, and one sentence.

    No lists of rows. Today's own response carries the rows it needs through
    ``important``; this is what the Care card and the overview screen read.
    """

    profile_id: uuid.UUID
    local_date: date
    tasks: TaskCountsRead
    reminders: ReminderCountsRead
    routines: RoutineCountsRead
    next_alarm_at: datetime | None
    alarm_count: int
    #: "3 tasks, 1 routine and 2 reminders today."
    summary_label: str
    #: False for somebody who has never made a task, which is what lets the
    #: Today card stay invisible until it is relevant.
    has_anything: bool


# --- external capabilities (sections 25-29 and 57) ---------------------------


class CapabilityRead(BaseModel):
    key: CapabilityKey
    state: CapabilityState
    label: str
    #: The sentence for this state. For the three external keys this is
    #: sections 26, 27 and 28's own wording.
    sentence: str


class ExternalCapabilitiesRead(BaseModel):
    """What Nura can actually reach (section 57).

    Exhaustive over every capability key, because section 29 says the model
    must not improvise one that is absent from the map -- and a map that only
    listed what happens to work would be a map with nothing to be absent from.
    """

    profile_id: uuid.UUID
    capabilities: list[CapabilityRead]
    #: Just the three external keys, as a plain mapping, which is the shape
    #: section 29 shows and the shape the assistant prompt is built from.
    external: dict[str, CapabilityState]
    #: False in every deployment today.
    any_external_configured: bool


# --- the caregiver's view of routines (sections 16 and 56) -------------------


class CaregiverRoutineRead(BaseModel):
    """One routine, as somebody helping sees it.

    Narrower than ``RoutineRead``: no step list, no provenance, and no
    completion rows. A caregiver is told what the routine is, when it runs and
    how today is going, which is what section 16's "view permitted routines"
    means for somebody trying to help.
    """

    routine_id: uuid.UUID
    title: str
    schedule_label: str
    step_count: int
    paused: bool
    today_status: RoutineRunStatus | None
    today_done: int | None
    today_total: int | None
    #: "2 of 3 complete", or null when the routine does not run today.
    today_progress_label: str | None


class CaregiverRoutineListRead(BaseModel):
    routines: list[CaregiverRoutineRead]
    #: Section 42, said on the caregiver's own screen.
    scope_note: str
