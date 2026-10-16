"""Tasks, general reminders, alarms and routines (PRD 12, sections 4-14, 49).

PRD 12 section 4 is the shape of this file, and it is a boundary rather than a
suggestion: a task, a reminder, an alarm and a routine are four different
things, and section 113 says not to fold them into one ambiguous table unless
their distinct behaviour stays explicit. They are four tables -- eight with the
children -- because the behaviour genuinely differs::

    tasks                        something to finish; may have no time at all
    general_reminders            a message at a time, possibly repeating
        +-- general_reminder_occurrences    one concrete moment, and what happened
    alarms                       a time of day whose purpose is to be noticed
    routines                     a repeated set of steps
        +-- routine_steps                   the steps, in order
        +-- routine_runs                    one scheduled instance
                +-- routine_step_completions    which steps got done

Five conventions run through all of them, and four are inherited rather than
invented.

**A repeating thing carries its own time zone, and a wall-clock time.**
Straight from PRD 5 (section 35 of PRD 12 says to reuse that discipline and not
to build a second, contradictory one): a 7:30 PM routine means half past seven
where the person is, in January and in July. So a recurring row stores an IANA
zone and a naive ``time_of_day``, and the generator resolves them to an instant
through ``services.medications.doses.occurrence_instant`` -- the same function,
with the same spring-forward and autumn-ambiguity answers.

**An occurrence is a row, not a calculation.** Reminder occurrences and routine
runs are generated ahead of time, so "what is due today", "what did I miss" and
the phone's notification schedule all read the same rows rather than three
separate re-derivations of a recurrence rule (PRD 5, section 22; PRD 12,
section 8).

**A task's due time is an instant and a local date, both stored.** PRD 12
section 36's travel policy is that an absolute task due timestamp stays fixed;
the local date is stored beside it so "due today" is one indexed comparison in
the day the person was in when they set it, and so a task keeps the day it was
meant for.

**Client ids make a retry free.** ``client_task_id`` and its three siblings are
PRD 7's idempotency pattern, which PRD 12 sections 37-39 ask for again: an
offline draft sent twice is one row, because the second send finds the first.

**Two timestamps, not one, on anything a second device can edit.** PRD 12
section 40 asks for deterministic conflict resolution and, specifically, that a
completion must not be undone by an unrelated title edit from another device.
So a task records ``content_updated_at`` and ``status_changed_at``
separately, and an edit is compared against the one it actually touches. The
field-level consequence is written down in
``docs/architecture/daily-life-assistant.md``.

**Nothing here is clinical.** A routine may say "stretch for five minutes"
because somebody typed it or a clinician told them to; nothing in this file or
anywhere near it decides that somebody should have one (PRD 12, sections 15
and 24).
"""

import uuid
from datetime import date, datetime, time

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    Time,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.enums import (
    ALARM_RECURRENCES,
    ALARM_SOUND_KEYS,
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
    sql_in_list,
)
from app.models.medication import MONDAY, SUNDAY, TIMEZONE_MAX_LENGTH
from app.models.symptom import CLIENT_ID_MAX_LENGTH

#: A title is one line somebody reads in a list. Long enough for "Call the
#: physiotherapist about the referral", short enough that no row wraps forever.
TITLE_MAX_LENGTH = 120

#: An alarm's label is shown on a lock screen beside a time, so shorter still.
LABEL_MAX_LENGTH = 80

#: A task's notes: a few sentences beside a checkbox, not a journal.
NOTES_MAX_LENGTH = 2000

#: A reminder's body and a routine's description -- the sentence under the
#: title.
BODY_MAX_LENGTH = 500

#: How many steps one routine may have. More than any morning has, and few
#: enough that the run screen is never a scroll nobody finishes.
MAX_ROUTINE_STEPS = 30

#: A reminder may be put off this many times before Snooze stops being offered.
#: The same shape PRD 5 gave a dose, and the same reason: endless rapid
#: snoozing is worth preventing, but Done and Dismiss stay available however
#: many times it has been put off.
MAX_REMINDER_SNOOZES = 3

#: The SQL fragment that checks a weekday array.
#:
#: Weekdays are stored as a small array rather than three child tables or a
#: bitmask, for two reasons: ``{0,2,4}`` is legible in psql, and ``<@`` makes
#: "every element is a weekday" one readable comparison. 0 is Monday, matching
#: ``date.weekday()``, so nothing is ever translated between the database and
#: the generator.
_WEEKDAYS_IN_RANGE = (
    f"weekdays <@ ARRAY[{','.join(str(day) for day in range(MONDAY, SUNDAY + 1))}]"
    "::smallint[] AND array_length(weekdays, 1) BETWEEN 1 AND 7"
)


class Task(Base, TimestampMixin):
    """Something the user wants to get done (PRD 12, sections 5 and 6).

    A task may have no due date at all, which is the common case for "pick up
    the prescription at some point" -- so ``due_at`` is nullable and nothing
    invents a deadline for a task that never had one.

    Completion preserves history (section 6): ``completed`` keeps the row and
    its ``completed_at``, Undo clears both, and neither archiving nor
    cancelling deletes anything. Deleting is a separate act, for a task entered
    by mistake.
    """

    __tablename__ = "tasks"
    __table_args__ = (
        CheckConstraint(
            f"status IN {sql_in_list(TASK_STATUSES)}", name="ck_tasks_status"
        ),
        CheckConstraint(
            f"priority IN {sql_in_list(TASK_PRIORITIES)}", name="ck_tasks_priority"
        ),
        CheckConstraint(
            f"source IN {sql_in_list(DAILY_LIFE_SOURCES)}", name="ck_tasks_source"
        ),
        # A due instant and the local day it belongs to arrive together or not
        # at all. Half of a due date is a task that sorts into today and
        # renders with no time, or the other way round.
        CheckConstraint(
            "(due_at IS NULL AND due_local_date IS NULL) OR "
            "(due_at IS NOT NULL AND due_local_date IS NOT NULL)",
            name="ck_tasks_due",
        ),
        # One task per client id, so an offline draft sent twice is one task
        # (PRD 12, section 37).
        UniqueConstraint("profile_id", "client_task_id", name="uq_task_client_id"),
        # What every list query asks: this profile's open tasks, soonest first.
        Index("ix_tasks_profile_status_due", "profile_id", "status", "due_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(TITLE_MAX_LENGTH), nullable=False)
    notes: Mapped[str | None] = mapped_column(String(NOTES_MAX_LENGTH))
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="open")
    priority: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="normal"
    )
    #: The instant it is due, in UTC. Null for a task with no due date.
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    #: The day it is due *where the user was when they set it* (section 36).
    due_local_date: Mapped[date | None] = mapped_column(Date, index=True)
    #: The zone that local date was worked out in. Kept even when ``due_at`` is
    #: null, so a task given a due date later keeps the person's own zone.
    timezone: Mapped[str] = mapped_column(
        String(TIMEZONE_MAX_LENGTH), nullable=False, server_default="UTC"
    )
    source: Mapped[str] = mapped_column(String(24), nullable=False, server_default="user")
    client_task_id: Mapped[str | None] = mapped_column(String(CLIENT_ID_MAX_LENGTH))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: When the title, notes, priority or due date last changed (section 40).
    content_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: When the status last changed. Separate on purpose: comparing an edit
    #: against the timestamp for the *other* kind of change is how a stale
    #: title edit comes to undo a completion.
    status_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class GeneralReminder(Base, TimestampMixin):
    """A message at a time, possibly repeating (PRD 12, section 7).

    Not a task with a date on it. A reminder's whole purpose is the moment:
    section 4 keeps the two apart, and the practical difference is that a
    reminder produces occurrence rows and a task does not.

    The recurrence is five named patterns and no grammar (section 7). A
    ``one_time`` reminder is one occurrence and then the series is
    ``completed``; the four repeating ones keep producing until ``end_date``,
    a pause, or a cancellation.
    """

    __tablename__ = "general_reminders"
    __table_args__ = (
        CheckConstraint(
            f"recurrence IN {sql_in_list(REMINDER_RECURRENCES)}",
            name="ck_general_reminders_recurrence",
        ),
        CheckConstraint(
            f"status IN {sql_in_list(REMINDER_STATUSES)}",
            name="ck_general_reminders_status",
        ),
        CheckConstraint(
            f"source IN {sql_in_list(DAILY_LIFE_SOURCES)}",
            name="ck_general_reminders_source",
        ),
        CheckConstraint(
            "end_date IS NULL OR end_date >= start_date",
            name="ck_general_reminders_date_range",
        ),
        # Weekdays belong to exactly the two recurrences that mean anything
        # without them, and are refused on the three that do not.
        CheckConstraint(
            "CASE WHEN recurrence IN ('selected_days', 'weekly') "
            f"THEN weekdays IS NOT NULL AND {_WEEKDAYS_IN_RANGE} "
            "ELSE weekdays IS NULL END",
            name="ck_general_reminders_weekdays",
        ),
        CheckConstraint(
            "recurrence <> 'weekly' OR array_length(weekdays, 1) = 1",
            name="ck_general_reminders_weekly",
        ),
        CheckConstraint(
            "CASE WHEN recurrence = 'monthly' "
            "THEN day_of_month IS NOT NULL AND day_of_month BETWEEN 1 AND 31 "
            "ELSE day_of_month IS NULL END",
            name="ck_general_reminders_day_of_month",
        ),
        UniqueConstraint(
            "profile_id", "client_reminder_id", name="uq_general_reminder_client_id"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(TITLE_MAX_LENGTH), nullable=False)
    body: Mapped[str | None] = mapped_column(String(BODY_MAX_LENGTH))
    recurrence: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="one_time"
    )
    #: IANA name. The whole daylight-saving policy rests on this being stored
    #: rather than an offset (PRD 5's reasoning, PRD 12 section 35).
    timezone: Mapped[str] = mapped_column(
        String(TIMEZONE_MAX_LENGTH), nullable=False, server_default="UTC"
    )
    #: The first local date this can produce an occurrence on.
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    #: Null means "no end", which is the common case for "every morning".
    end_date: Mapped[date | None] = mapped_column(Date)
    #: A naive wall-clock time, meaningless without ``timezone``.
    time_of_day: Mapped[time] = mapped_column(Time(timezone=False), nullable=False)
    #: 0 is Monday. Null on the recurrences that do not use weekdays.
    weekdays: Mapped[list[int] | None] = mapped_column(ARRAY(SmallInteger))
    #: 1-31 on a monthly reminder. A month without that day uses its last day,
    #: decided in the generator rather than refused here (section 35).
    day_of_month: Mapped[int | None] = mapped_column(SmallInteger)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="active"
    )
    #: False keeps the reminder and stops the phone notification (section 9).
    #: The reminder still appears on Today, which is what section 9 asks for
    #: when permission has been refused.
    notification_enabled: Mapped[bool] = mapped_column(
        nullable=False, server_default="true"
    )
    source: Mapped[str] = mapped_column(String(24), nullable=False, server_default="user")
    client_reminder_id: Mapped[str | None] = mapped_column(String(CLIENT_ID_MAX_LENGTH))
    paused_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    occurrences: Mapped[list["GeneralReminderOccurrence"]] = relationship(
        back_populates="reminder",
        cascade="all, delete-orphan",
        order_by="GeneralReminderOccurrence.scheduled_for",
    )


class GeneralReminderOccurrence(Base, TimestampMixin):
    """One moment a reminder was for, and what happened at it (section 8).

    Owned by the user: Done, Snooze and Dismiss all update *this* row rather
    than appending an event beside it, which is what makes a retried request
    harmless -- there is one row per moment, and re-sending Done finds it
    already done.

    ``profile_id`` is carried here as well as on the reminder, so every query
    and every authorization check is "this profile's rows" without a join.
    """

    __tablename__ = "general_reminder_occurrences"
    __table_args__ = (
        CheckConstraint(
            f"status IN {sql_in_list(REMINDER_OCCURRENCE_STATUSES)}",
            name="ck_reminder_occurrences_status",
        ),
        CheckConstraint("snooze_count >= 0", name="ck_reminder_occurrences_snooze_count"),
        # One row per moment per reminder, so a regeneration that races with
        # itself cannot produce the same 8am twice.
        UniqueConstraint(
            "reminder_id", "scheduled_for", name="uq_reminder_occurrence_moment"
        ),
        Index(
            "ix_reminder_occurrences_profile_due",
            "profile_id",
            "status",
            "scheduled_for",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    reminder_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("general_reminders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    scheduled_for: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    #: The calendar day it belongs to where the user is, stored rather than
    #: recomputed, for the reason a dose's is.
    local_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="scheduled"
    )
    #: When the person actually did something -- not when the request arrived.
    action_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    snoozed_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    snooze_count: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default="0"
    )

    reminder: Mapped[GeneralReminder] = relationship(back_populates="occurrences")


class Alarm(Base, TimestampMixin):
    """A time of day whose purpose is to be noticed (PRD 12, sections 10, 11).

    No occurrence rows, deliberately. An alarm has no history worth keeping --
    nobody asks what they did about Tuesday's 7am -- so "is this alarm for now"
    is derived from the stored time, the stored days and the clock, the same way
    a robot's connection status is derived rather than stored.

    **What this table cannot promise.** Section 11 is explicit, and so is this
    docstring: a row here is a *scheduled notification*, and nothing in this
    project has ever verified operating-system alarm behaviour. The app has
    never run on a physical phone. ``sound_key`` and ``vibration`` are stored
    choices, not sounds anybody heard.
    """

    __tablename__ = "alarms"
    __table_args__ = (
        CheckConstraint(
            f"recurrence IN {sql_in_list(ALARM_RECURRENCES)}", name="ck_alarms_recurrence"
        ),
        CheckConstraint(
            f"sound_key IN {sql_in_list(ALARM_SOUND_KEYS)}", name="ck_alarms_sound"
        ),
        CheckConstraint(
            f"source IN {sql_in_list(DAILY_LIFE_SOURCES)}", name="ck_alarms_source"
        ),
        CheckConstraint(
            "CASE WHEN recurrence = 'selected_days' "
            f"THEN weekdays IS NOT NULL AND {_WEEKDAYS_IN_RANGE} "
            "ELSE weekdays IS NULL END",
            name="ck_alarms_weekdays",
        ),
        # A one-off alarm is for a named day; a repeating one is not.
        CheckConstraint(
            "(recurrence = 'one_time') = (on_date IS NOT NULL)",
            name="ck_alarms_one_time",
        ),
        UniqueConstraint("profile_id", "client_alarm_id", name="uq_alarm_client_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    label: Mapped[str] = mapped_column(String(LABEL_MAX_LENGTH), nullable=False)
    time_of_day: Mapped[time] = mapped_column(Time(timezone=False), nullable=False)
    timezone: Mapped[str] = mapped_column(
        String(TIMEZONE_MAX_LENGTH), nullable=False, server_default="UTC"
    )
    recurrence: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="one_time"
    )
    #: 0 is Monday. Set only on ``selected_days``.
    weekdays: Mapped[list[int] | None] = mapped_column(ARRAY(SmallInteger))
    #: The local date a one-off alarm is for.
    on_date: Mapped[date | None] = mapped_column(Date)
    enabled: Mapped[bool] = mapped_column(nullable=False, server_default="true")
    sound_key: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="default"
    )
    vibration: Mapped[bool] = mapped_column(nullable=False, server_default="true")
    source: Mapped[str] = mapped_column(String(24), nullable=False, server_default="user")
    client_alarm_id: Mapped[str | None] = mapped_column(String(CLIENT_ID_MAX_LENGTH))


class Routine(Base, TimestampMixin):
    """A repeated set of steps (PRD 12, sections 12, 13 and 15).

    ``paused`` is the pause switch section 13 asks for: a paused routine
    generates no runs and keeps every run it has already produced. Nothing
    infers why it was paused, exactly as nothing infers why a medication
    schedule was.

    **Nothing in Nura prescribes one of these.** Section 15 draws the line and
    section 24 repeats it: a person may create a health-related routine, or
    enter one a clinician gave them, and Nura may remind them of it. Nura never
    decides from a symptom, a diagnosis or a model's inference that somebody
    should have a routine -- there is no code path anywhere that creates a
    ``Routine`` from health data.
    """

    __tablename__ = "routines"
    __table_args__ = (
        CheckConstraint(
            f"schedule_type IN {sql_in_list(ROUTINE_SCHEDULE_TYPES)}",
            name="ck_routines_schedule_type",
        ),
        CheckConstraint(
            f"status IN {sql_in_list(ROUTINE_STATUSES)}", name="ck_routines_status"
        ),
        CheckConstraint(
            f"source IN {sql_in_list(DAILY_LIFE_SOURCES)}", name="ck_routines_source"
        ),
        CheckConstraint(
            "end_date IS NULL OR end_date >= start_date", name="ck_routines_date_range"
        ),
        CheckConstraint(
            "CASE WHEN schedule_type = 'selected_days' "
            f"THEN weekdays IS NOT NULL AND {_WEEKDAYS_IN_RANGE} "
            "ELSE weekdays IS NULL END",
            name="ck_routines_weekdays",
        ),
        UniqueConstraint("profile_id", "client_routine_id", name="uq_routine_client_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(TITLE_MAX_LENGTH), nullable=False)
    description: Mapped[str | None] = mapped_column(String(BODY_MAX_LENGTH))
    schedule_type: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="daily"
    )
    timezone: Mapped[str] = mapped_column(
        String(TIMEZONE_MAX_LENGTH), nullable=False, server_default="UTC"
    )
    #: When the routine is for. A routine without a time is a checklist, and
    #: section 17's own example reads "Every day - 7:30 PM".
    time_of_day: Mapped[time] = mapped_column(Time(timezone=False), nullable=False)
    #: 0 is Monday. Set only on ``selected_days``.
    weekdays: Mapped[list[int] | None] = mapped_column(ARRAY(SmallInteger))
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="active"
    )
    paused_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: Who put it there (section 43). ``caregiver_suggestion`` is what an
    #: approved suggestion carries, so provenance survives the approval.
    source: Mapped[str] = mapped_column(String(24), nullable=False, server_default="user")
    client_routine_id: Mapped[str | None] = mapped_column(String(CLIENT_ID_MAX_LENGTH))

    steps: Mapped[list["RoutineStep"]] = relationship(
        back_populates="routine",
        cascade="all, delete-orphan",
        order_by="RoutineStep.position",
    )


class RoutineStep(Base, TimestampMixin):
    """One step of a routine, in order (PRD 12, section 13).

    ``position`` has an index and deliberately **no unique constraint**.
    Reordering replaces the whole list in one flush -- the same shape the Today
    card layout uses -- and a unique constraint would fail half way through a
    swap for no benefit, since the service assigns positions from the order it
    was given.

    ``optional`` is what lets a run be complete without every step: section 14
    tracks individual step completion, and a routine whose last step is "if you
    feel up to it, walk round the garden" should not be permanently unfinished.
    """

    __tablename__ = "routine_steps"
    __table_args__ = (
        CheckConstraint("position >= 0", name="ck_routine_steps_position"),
        Index("ix_routine_steps_routine_position", "routine_id", "position"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    routine_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("routines.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(TITLE_MAX_LENGTH), nullable=False)
    position: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default="0"
    )
    optional: Mapped[bool] = mapped_column(nullable=False, server_default="false")

    routine: Mapped[Routine] = relationship(back_populates="steps")


class RoutineRun(Base, TimestampMixin):
    """One scheduled instance of a routine (PRD 12, section 14).

    Generated ahead of time like a dose, and for the same reason: "what is due
    today" and "what did I miss" read rows rather than re-deriving a
    recurrence.

    ``routine_id`` cascades rather than clearing, which is the opposite of what
    a dose does, and the difference is deliberate. A dose is a medical record
    somebody acted on and must survive its schedule being deleted; a routine
    run is a checklist for a morning, and keeping orphaned ones would be a
    history nobody asked for. Somebody who wants to stop a routine and keep its
    history archives it -- which is why ``archived`` is a status.
    """

    __tablename__ = "routine_runs"
    __table_args__ = (
        CheckConstraint(
            f"status IN {sql_in_list(ROUTINE_RUN_STATUSES)}",
            name="ck_routine_runs_status",
        ),
        UniqueConstraint("routine_id", "scheduled_for", name="uq_routine_run_moment"),
        Index("ix_routine_runs_profile_due", "profile_id", "status", "scheduled_for"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    routine_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("routines.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    scheduled_for: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    local_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="scheduled"
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    routine: Mapped[Routine] = relationship()
    completions: Mapped[list["RoutineStepCompletion"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class RoutineStepCompletion(Base, TimestampMixin):
    """That a step of a run was done, or passed over (PRD 12, sections 14, 39).

    One row per step per run, enforced by the database, which is what makes
    marking a step complete idempotent -- and what lets an offline queue send
    the same completion twice without inventing partial progress
    (section 39).

    ``state`` rather than a boolean: section 14 tracks individual step
    completion, and "I skipped the stretch" is a different thing from "I have
    not got to the stretch yet". Nothing interprets either.
    """

    __tablename__ = "routine_step_completions"
    __table_args__ = (
        CheckConstraint(
            f"state IN {sql_in_list(ROUTINE_STEP_STATES)}",
            name="ck_routine_step_completions_state",
        ),
        UniqueConstraint("run_id", "step_id", name="uq_routine_step_completion"),
        UniqueConstraint(
            "profile_id",
            "client_completion_id",
            name="uq_routine_step_completion_client_id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("routine_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    step_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("routine_steps.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    state: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="completed"
    )
    #: When the person actually marked it, not when the request arrived.
    completed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    client_completion_id: Mapped[str | None] = mapped_column(String(CLIENT_ID_MAX_LENGTH))

    run: Mapped[RoutineRun] = relationship(back_populates="completions")
    step: Mapped[RoutineStep] = relationship()
