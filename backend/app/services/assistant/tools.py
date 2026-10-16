"""What Nura is allowed to look up, and the one thing it can change.

PRD 8, sections 13, 14, 51, 52, 90, 91 and 100.

**No tool takes a profile id.** Every one of them reads ``context.profile``,
which was resolved from the signed-in account before the model was called.
Section 90 says the model must never choose a profile; the way to guarantee
that is not to validate the id it chose, but to give it nowhere to put one.
There is no argument on any tool below that names a person, and the section
100 tests check that by asking a second account's assistant for the first
account's records and getting the second account's.

**Arguments are validated before anything runs** (section 91). Each tool
declares a pydantic model; the JSON Schema the provider sees is generated
from it, and the arguments that come back are parsed through it. A call that
does not fit is returned to the model as an error result rather than raising:
a malformed tool call is a thing to recover from, not a crash.

**One tool writes, and it does not write.** ``add_appointment_question`` takes
the question, checks it could be added, and returns a *pending action* for the
user to confirm (section 14). Nothing in this file changes a health record,
and sections 15 and 61 rule out ever adding one that does -- no dose edits, no
stopping a medication, no deleting anything.

**Output is bounded** (section 77). Each result is capped, and the caps are
small: a tool that can return a thousand lines is a tool that can empty a
budget in one conversation.

**Every tool names the permission it needs** (PRD 9, sections 63 and 64). A
``ToolContext`` carries the set of categories its caller was granted, and both
``specs`` and ``run`` filter on it -- so a caregiver whose symptom access was
never granted has no symptom tool in the list the model is shown, and would be
refused if it asked for one anyway. ``permission=None`` means *owner only*:
``get_today_summary`` and ``get_daily_checkin_summary`` span categories a
caregiver is granted separately, and ``add_appointment_question`` writes, which
PRD 9 section 64 reserves for a suggestion the person approves.

``allowed`` has no default, deliberately. A future caregiver-facing assistant
has to say what scope it is running in, rather than silently getting the
owner's. ``account`` has no default either, for the same reason and a sharper
one: PRD 10's safety tools write rows that say who acted, and a context that
could not say would have to guess.

**The safety tools, and why three of them ask before they act** (PRD 10,
sections 56 and 57).

Section 57 is the rule the shape of these tools comes from: the model must not
create a ``possible_*`` event from a speculative interpretation. It cannot --
no tool below takes an event type, so there is nowhere for the idea to go. What
the model *can* do is raise a manual SOS, start or stop monitoring, and answer
a safety check, and those four split along one line:

- **Erring towards help is a safe error, erring towards "they are fine" is
  not.** ``respond_to_safety_check`` with ``need_help`` acts immediately --
  somebody asking for help should not wait for a second tap. The same tool
  with ``im_okay`` returns a pending action the person confirms, because a
  model deciding somebody is all right would end an escalation that was
  already reaching people.
- **The emergency fast path does not go through the model at all.** "Nura,
  emergency" is matched deterministically in ``policy`` and escalates before
  any provider is called (PRD 10, section 14). So ``manual_sos`` as a tool is
  for ambiguous phrasing, where asking first is right rather than slow.

``start_safety_monitoring`` and ``stop_safety_monitoring`` ask too: switching
monitoring on is a decision about being watched, and section 4 says it must
never happen quietly.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from datetime import time as dt_time
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Appointment,
    DailyCheckIn,
    Medication,
    MedicationSchedule,
    Profile,
    SymptomEntry,
    User,
)
from app.models.enums import CAREGIVER_PERMISSION_KEYS
from app.services import checkins as checkin_service
from app.services import health as health_service
from app.services.appointments import appointments as appointment_service
from app.services.appointments import preparation as preparation_service
from app.services.appointments import questions as question_service
from app.services.appointments import summary as appointment_summary
from app.services.appointments import wording
from app.services.assistant.provider import ToolSpec
from app.services.caregivers import permissions as caregiver_permissions
from app.services.errors import DomainError, NotFoundError
from app.services.medications import adherence as adherence_service
from app.services.medications import summary as medication_summary
from app.services.productivity import alarms as alarm_service
from app.services.productivity import boundaries, recurrence, zones
from app.services.productivity import reminders as reminder_service
from app.services.productivity import routines as routine_service
from app.services.productivity import tasks as task_service
from app.services.productivity import wording as productivity_wording
from app.services.safety import alerts as safety_alerts
from app.services.safety import checks as safety_checks
from app.services.safety import escalation as safety_escalation
from app.services.safety import events as safety_events
from app.services.safety import monitoring as safety_monitoring
from app.services.safety import status as safety_status
from app.services.safety import wording as safety_wording
from app.services.symptoms import summary as symptom_summary

logger = logging.getLogger(__name__)

#: Longest result any single tool may hand back (PRD 8, section 77).
MAX_TOOL_OUTPUT_CHARS = 2000

#: How many rows a list tool returns at most. Somebody with forty active
#: symptoms does not need all forty in a chat reply, and the model does not
#: need them to answer the question that was asked.
MAX_ROWS = 10

#: The window "recently" means where a tool does not take one.
RECENT_DAYS = 14

#: What a tool says when there is nothing. Consistent wording so the model
#: learns the shape and reports an empty record as empty rather than
#: filling it in (section 81).
NOTHING_RECORDED = "Nothing recorded."


#: Every category, which is what the person themselves has. An owner's own
#: routes already return everything, so there is nothing for a permission to
#: protect them from.
OWNER_SCOPE: frozenset[str] = frozenset(CAREGIVER_PERMISSION_KEYS)


@dataclass(frozen=True)
class ToolContext:
    """Everything a tool may see. Notably: exactly one profile.

    ``allowed`` is the PRD 9 addition and has no default: a caller must say
    whether it is the person themselves (``OWNER_SCOPE``) or a caregiver with a
    granted subset. ``is_owner`` is separate because an owner is not merely
    somebody with every permission -- the write tool is theirs alone.
    """

    db: Session
    profile: Profile
    now: datetime
    local_date: date
    #: The caregiver permission categories this caller holds.
    allowed: frozenset[str]
    #: True when the caller is the person themselves or their setup helper.
    is_owner: bool
    #: Who is acting. Required, because PRD 10's safety tools write rows that
    #: record an actor, and a context that could not say who would have to
    #: guess. Reads ignore it.
    account: User

    def may_use(self, tool: Tool) -> bool:
        """Whether this caller may run that tool at all.

        ``permission=None`` is owner-only rather than unrestricted, which is the
        safe reading: a tool that spans categories, or writes, should not become
        available to a caregiver because somebody forgot to label it.
        """
        if tool.permission is None:
            return self.is_owner
        if tool.caregiver_only and self.is_owner:
            return False
        if tool.writes and not self.is_owner and not tool.caregiver_writable:
            return False
        return tool.permission in self.allowed


@dataclass(frozen=True)
class PendingAction:
    """A write the user has to agree to before it happens (section 14)."""

    tool: str
    arguments: dict[str, Any]
    #: The sentence the app shows above Confirm and Cancel.
    summary: str


@dataclass(frozen=True)
class ToolOutcome:
    """What running a tool produced."""

    content: str
    is_error: bool = False
    pending: PendingAction | None = None


# --- argument models --------------------------------------------------------


class _Args(BaseModel):
    """Base for tool arguments: unknown fields are refused, not ignored."""

    model_config = ConfigDict(extra="forbid")


class NoArgs(_Args):
    pass


class RecentSymptomArgs(_Args):
    days: int = Field(
        default=RECENT_DAYS,
        ge=1,
        le=90,
        description="How many days back to look.",
    )


class MedicationHistoryArgs(_Args):
    days: int = Field(
        default=7,
        ge=1,
        le=90,
        description="How many days of dose history to count.",
    )


class AppointmentQuestionsArgs(_Args):
    appointment_id: str | None = Field(
        default=None,
        description=(
            "The appointment to read questions for. Omit for the next "
            "upcoming appointment."
        ),
    )


class StartMonitoringArgs(_Args):
    """How long to watch over somebody (PRD 10, section 5).

    Three of the locked presets and **no custom duration**. A model choosing a
    number of minutes is a model inventing a monitoring period, which section
    5 forbids; somebody who wants ninety minutes can say so on the screen.

    ``until_bedtime`` is absent for a different reason: bedtime is a
    wall-clock time and resolving one needs the time zone the person is in.
    The Safety screen knows it, because the phone does. This tool does not,
    and guessing UTC would end monitoring at the wrong hour -- so the
    assistant offers the three durations it can work out honestly.
    """

    duration_mode: Literal["30_minutes", "1_hour", "until_turned_off"] = "1_hour"


class SafetyResponseArgs(_Args):
    """The user's answer to a safety check (PRD 10, sections 24 and 25).

    Two values. ``false_alarm`` is absent on purpose: labelling an event is a
    judgement about what a sensor saw, and section 48 keeps that with the
    person rather than with the model.
    """

    response: Literal["im_okay", "need_help"]


class AcknowledgeAlertArgs(_Args):
    """Which alert a caregiver is acknowledging (PRD 10, sections 84 and 97)."""

    alert_id: str = Field(description="The id of the safety alert to acknowledge.")


# --- daily-life argument models (PRD 12, sections 21 and 22) ----------------
#
# Dates and times arrive as strings with a pattern on them rather than as
# ``date`` and ``time`` objects. Two reasons. A JSON Schema a model reads is
# clearer with ``YYYY-MM-DD`` in the description than with a format keyword it
# may not have been trained to respect; and a value that does not parse comes
# back as a tool error the model can correct, rather than as a validation
# failure that looks like a bug.
#
# **No argument anywhere below names a time zone.** The model has no clock and
# no location, so it cannot know one. ``services.productivity.zones`` answers
# the question from zones the person entered themselves through a client that
# did know, and a tool with no answer says so and asks rather than guessing
# (section 22).

_DATE_PATTERN = r"^\d{4}-\d{2}-\d{2}$"
_TIME_PATTERN = r"^([01][0-9]|2[0-3]):[0-5][0-9]$"


class TaskScopeArgs(_Args):
    scope: Literal["open", "completed"] = Field(
        default="open", description="Which tasks to list."
    )


class CreateTaskArgs(_Args):
    title: str = Field(
        min_length=1, max_length=120, description="What the task is, in a few words."
    )
    notes: str | None = Field(
        default=None, max_length=2000, description="Anything else worth writing down."
    )
    priority: Literal["normal", "important"] = "normal"
    due_date: str | None = Field(
        default=None,
        pattern=_DATE_PATTERN,
        description="The day it is due, as YYYY-MM-DD. Omit for a task with no due date.",
    )
    due_time: str | None = Field(
        default=None,
        pattern=_TIME_PATTERN,
        description="The time it is due, as HH:MM on a 24-hour clock. Needs due_date.",
    )


class TaskIdArgs(_Args):
    task_id: str = Field(description="The id of the task, from get_tasks.")


class UpdateTaskArgs(_Args):
    task_id: str = Field(description="The id of the task, from get_tasks.")
    title: str | None = Field(default=None, min_length=1, max_length=120)
    notes: str | None = Field(default=None, max_length=2000)
    priority: Literal["normal", "important"] | None = None
    due_date: str | None = Field(default=None, pattern=_DATE_PATTERN)
    due_time: str | None = Field(default=None, pattern=_TIME_PATTERN)


class CreateReminderArgs(_Args):
    title: str = Field(
        min_length=1, max_length=120, description="What to remind them about."
    )
    time: str = Field(
        pattern=_TIME_PATTERN,
        description="The time of day, as HH:MM on a 24-hour clock.",
    )
    repeat: Literal["one_time", "daily", "selected_days", "weekly", "monthly"] = Field(
        default="one_time", description="How often it repeats."
    )
    start_date: str | None = Field(
        default=None,
        pattern=_DATE_PATTERN,
        description="The first day, as YYYY-MM-DD. Defaults to today.",
    )
    weekdays: list[int] | None = Field(
        default=None,
        description=(
            "Days of the week, 0 for Monday to 6 for Sunday. Needed for "
            "selected_days and weekly."
        ),
    )
    day_of_month: int | None = Field(
        default=None, ge=1, le=31, description="Needed for monthly."
    )


class CreateAlarmArgs(_Args):
    label: str = Field(min_length=1, max_length=80, description="What the alarm is for.")
    time: str = Field(
        pattern=_TIME_PATTERN,
        description="The time of day, as HH:MM on a 24-hour clock.",
    )
    repeat: Literal["one_time", "daily", "selected_days"] = "one_time"
    on_date: str | None = Field(
        default=None,
        pattern=_DATE_PATTERN,
        description="The day, as YYYY-MM-DD. Needed for a one-off alarm.",
    )
    weekdays: list[int] | None = Field(
        default=None,
        description="Days of the week, 0 for Monday. Needed for selected_days.",
    )


class CreateRoutineArgs(_Args):
    """A routine the *user* has decided on (sections 15 and 24).

    There is no argument here for a symptom, a diagnosis or a reason, and that
    is deliberate: a routine Nura worked out from somebody's pain would be a
    clinical prescription, and section 24 rules it out. The steps are the
    user's own words.
    """

    title: str = Field(min_length=1, max_length=120)
    time: str = Field(pattern=_TIME_PATTERN, description="When it happens, as HH:MM.")
    steps: list[str] = Field(
        min_length=1,
        max_length=30,
        description="The steps, in order, in the user's own words.",
    )
    repeat: Literal["daily", "selected_days"] = "daily"
    weekdays: list[int] | None = Field(
        default=None,
        description="Days of the week, 0 for Monday. Needed for selected_days.",
    )


class RoutineIdArgs(_Args):
    routine_id: str = Field(description="The id of the routine, from get_routines.")


class AddQuestionArgs(_Args):
    text: str = Field(
        min_length=1,
        max_length=500,
        description="The question, in the user's own words.",
    )
    appointment_id: str | None = Field(
        default=None,
        description=(
            "The appointment to add it to. Omit for the next upcoming appointment."
        ),
    )


# --- helpers ----------------------------------------------------------------


def _clip(text: str) -> str:
    if len(text) <= MAX_TOOL_OUTPUT_CHARS:
        return text
    return text[: MAX_TOOL_OUTPUT_CHARS - 1].rstrip() + "…"


def _lines(header: str, rows: list[str]) -> str:
    if not rows:
        return f"{header}: {NOTHING_RECORDED}"
    return "\n".join([f"{header}:", *(f"- {row}" for row in rows[:MAX_ROWS])])


def _appointment_for(
    context: ToolContext, appointment_id: str | None
) -> Appointment | None:
    """The appointment named, or the next one. Never anybody else's.

    An id that does not belong to this profile resolves to nothing, exactly as
    it would over HTTP -- the lookup is scoped by ``profile.id``, so a model
    that invents a UUID gets "no such appointment" rather than a stranger's.
    """
    if appointment_id:
        try:
            parsed = uuid.UUID(appointment_id)
        except ValueError:
            return None
        try:
            return appointment_service.get_appointment(
                context.db, context.profile.id, parsed
            )
        except NotFoundError:
            return None
    return appointment_service.next_upcoming(
        context.db, context.profile.id, now=context.now
    )


# --- the read tools ---------------------------------------------------------


def get_today_summary(context: ToolContext, args: NoArgs) -> ToolOutcome:
    """What the Today screen is showing right now.

    Composed from the same profile-scoped summary services the Today route
    uses, rather than from ``services.today`` itself: that one is built around
    the signed-in *account* and its primary profile, and an assistant scoped
    to a named profile must not quietly answer about a different one.
    """
    rows: list[str] = []

    medications = medication_summary.build_summary(
        context.db, context.profile.id, context.local_date, context.now
    )
    if medications.has_schedules:
        rows.append(
            wording.plural(medications.remaining_today_count, "medication dose")
            + f" still to record today, {medications.overdue_count} overdue"
        )

    appointments = appointment_summary.build_summary(
        context.db, context.profile.id, context.local_date, context.now
    )
    nxt = appointments.next_appointment
    if nxt is not None:
        zone = appointment_service.local_zone(nxt.appointment)
        label = wording.when_label(nxt.appointment.scheduled_at, zone, context.local_date)
        rows.append(f"Next appointment: {nxt.appointment.title}, {label}")

    symptoms = symptom_summary.build_summary(context.db, context.profile.id, context.now)
    if symptoms.has_episodes:
        rows.append(wording.plural(symptoms.active_count, "active symptom"))

    checkin = checkin_service.get_checkin(
        context.db, context.profile.id, context.local_date
    )
    rows.append(
        "Today's check-in is done, recorded as "
        f"{checkin.wellbeing_level.replace('_', ' ')}"
        if checkin is not None
        else "Today's check-in has not been done"
    )
    header = f"Today, {wording.format_day(context.local_date)}"
    return ToolOutcome(_clip(_lines(header, rows)))


def get_health_summary(context: ToolContext, args: NoArgs) -> ToolOutcome:
    """Counts from the health record -- never the records themselves."""
    summary = health_service.build_summary(context.db, context.profile, context.now)
    rows = [
        f"{section.title}: {section.count} recorded"
        for section in summary.sections
        if section.count
    ]
    rows.append(f"Active conditions: {summary.active_conditions}")
    rows.append(f"Active medications: {summary.active_medications}")
    rows.append(f"Active symptoms: {summary.active_symptoms}")
    if summary.blood_type and summary.blood_type not in ("unknown", "prefer_not_to_say"):
        rows.append(f"Blood type: {summary.blood_type}")
    return ToolOutcome(_clip(_lines("Health record", rows)))


def get_active_medications(context: ToolContext, args: NoArgs) -> ToolOutcome:
    """What the user is taking, and when they take it."""
    medications = (
        context.db.execute(
            select(Medication)
            .where(
                Medication.profile_id == context.profile.id,
                Medication.is_active.is_(True),
            )
            .order_by(Medication.name.asc())
        )
        .scalars()
        .all()
    )
    schedules: dict[uuid.UUID, list[MedicationSchedule]] = {}
    for schedule in (
        context.db.execute(
            select(MedicationSchedule).where(
                MedicationSchedule.profile_id == context.profile.id,
                MedicationSchedule.is_active.is_(True),
                MedicationSchedule.paused_at.is_(None),
            )
        )
        .scalars()
        .all()
    ):
        schedules.setdefault(schedule.medication_id, []).append(schedule)

    rows = []
    for medication in medications:
        parts = [medication.name]
        dose = " ".join(
            piece for piece in (medication.dose, medication.dose_unit) if piece
        )
        if dose:
            parts.append(dose)
        # The schedule is what the reminders actually follow, so it is
        # preferred over the free-text frequency -- the same choice a doctor
        # report makes, so the two describe a medication identically.
        medication_schedules = schedules.get(medication.id, [])
        frequency = preparation_service.schedule_frequency(medication_schedules)
        if frequency:
            times = ", ".join(
                entry.time_of_day.strftime("%H:%M")
                for schedule in medication_schedules
                for entry in schedule.times
            )
            parts.append(f"{frequency} at {times}" if times else frequency)
        elif medication.frequency_text:
            parts.append(medication.frequency_text)
        rows.append(" - ".join(parts))
    return ToolOutcome(_clip(_lines("Active medications", rows)))


def get_recent_medication_history(
    context: ToolContext, args: MedicationHistoryArgs
) -> ToolOutcome:
    """Dose counts for a window. Counts only -- never a verdict on them.

    PRD 8 section 19 allows Nura to state recent adherence counts, and
    PRD 5's own rule that the figure is never graded applies here too: this
    returns four numbers and no adjective.
    """
    from_date = context.local_date - timedelta(days=args.days - 1)
    result = adherence_service.calculate(
        context.db,
        context.profile.id,
        from_date=from_date,
        to_date=context.local_date,
    )
    if result.total == 0:
        return ToolOutcome(f"Doses in the last {args.days} days: none were scheduled.")
    return ToolOutcome(
        _clip(
            f"Doses in the last {args.days} days "
            f"({wording.format_range(from_date, context.local_date)}): "
            f"{result.taken} taken, {result.skipped} skipped, "
            f"{result.missed} missed, {result.total} in total."
        )
    )


def get_active_symptoms(context: ToolContext, args: NoArgs) -> ToolOutcome:
    """Open symptom episodes, most recently written about first."""
    snapshots = symptom_summary.active_snapshots(context.db, context.profile.id)
    rows = []
    for snapshot in snapshots:
        parts = [snapshot.episode.name]
        if snapshot.severity is not None:
            parts.append(f"severity {snapshot.severity} of 10")
        if snapshot.change_state:
            parts.append(f"recorded as {snapshot.change_state}")
        parts.append(f"last updated {wording.format_day(snapshot.updated_at.date())}")
        rows.append(", ".join(parts))
    return ToolOutcome(_clip(_lines("Active symptoms", rows)))


def get_recent_symptom_entries(
    context: ToolContext, args: RecentSymptomArgs
) -> ToolOutcome:
    """Individual entries in a window, so trends can be *reported*.

    Section 82 draws the line this tool sits on: three entries with their
    severities is a fact and may be repeated; what the trend means is not.
    """
    since = context.now - timedelta(days=args.days)
    entries = (
        context.db.execute(
            select(SymptomEntry)
            .where(
                SymptomEntry.profile_id == context.profile.id,
                SymptomEntry.recorded_at >= since,
            )
            .order_by(SymptomEntry.recorded_at.desc())
            .limit(MAX_ROWS)
        )
        .scalars()
        .all()
    )
    rows = []
    for entry in entries:
        name = entry.episode.name if entry.episode is not None else "Symptom"
        parts = [f"{wording.format_day(entry.recorded_at.date())}: {name}"]
        if entry.severity is not None:
            parts.append(f"severity {entry.severity}")
        if entry.change_state:
            parts.append(entry.change_state)
        rows.append(", ".join(parts))
    return ToolOutcome(_clip(_lines(f"Symptom entries, last {args.days} days", rows)))


def get_upcoming_appointments(context: ToolContext, args: NoArgs) -> ToolOutcome:
    """Visits still ahead, soonest first."""
    appointments = appointment_service.list_appointments(
        context.db, context.profile.id, scope="upcoming", now=context.now
    )
    rows = []
    for appointment in appointments[:MAX_ROWS]:
        zone = appointment_service.local_zone(appointment)
        label = wording.when_label(appointment.scheduled_at, zone, context.local_date)
        parts = [f"{appointment.title} - {label}"]
        if appointment.location_name:
            parts.append(f"at {appointment.location_name}")
        parts.append(f"preparation {appointment.preparation_status.replace('_', ' ')}")
        rows.append(", ".join(parts))
    return ToolOutcome(_clip(_lines("Upcoming appointments", rows)))


def get_appointment_questions(
    context: ToolContext, args: AppointmentQuestionsArgs
) -> ToolOutcome:
    """The questions already written down for a visit."""
    appointment = _appointment_for(context, args.appointment_id)
    if appointment is None:
        return ToolOutcome("There is no upcoming appointment to read questions for.")
    questions = question_service.list_questions(context.db, appointment.id)
    rows = [question.text for question in questions]
    return ToolOutcome(_clip(_lines(f"Questions for {appointment.title}", rows)))


def get_daily_checkin_summary(context: ToolContext, args: NoArgs) -> ToolOutcome:
    """How the last fortnight of check-ins went, as counts and the latest."""
    from_date = checkin_service.window_start(context.local_date, RECENT_DAYS)
    rows = (
        context.db.execute(
            select(DailyCheckIn)
            .where(
                DailyCheckIn.profile_id == context.profile.id,
                DailyCheckIn.checkin_date >= from_date,
                DailyCheckIn.checkin_date <= context.local_date,
            )
            .order_by(DailyCheckIn.checkin_date.desc())
        )
        .scalars()
        .all()
    )
    if not rows:
        return ToolOutcome(
            f"Check-ins in the last {RECENT_DAYS} days: {NOTHING_RECORDED}"
        )
    counts: dict[str, int] = {}
    for row in rows:
        counts[row.wellbeing_level] = counts.get(row.wellbeing_level, 0) + 1
    breakdown = ", ".join(
        f"{count} {level.replace('_', ' ')}" for level, count in sorted(counts.items())
    )
    latest = rows[0]
    return ToolOutcome(
        _clip(
            f"Check-ins in the last {RECENT_DAYS} days: {len(rows)} completed "
            f"({breakdown}). Most recent was "
            f"{wording.format_day(latest.checkin_date)}, "
            f"recorded as {latest.wellbeing_level.replace('_', ' ')}."
        )
    )


# --- safety (PRD 10, sections 56, 57, 95, 96 and 97) -------------------------


def get_safety_status(context: ToolContext, args: NoArgs) -> ToolOutcome:
    """Where safety stands (PRD 10, sections 56 and 95).

    Reading this advances a deadline that has passed, the same as the status
    endpoint does, so the assistant can never report a countdown that expired
    two minutes ago as though it were still running.

    It also reports what this build *cannot* do. Section 96 says never to
    hallucinate delivery, and the surest way for a model not to claim a push
    was sent is for the tool that tells it about safety to say plainly that
    there is no push.
    """
    status = safety_status.current(context.db, context.profile.id, context.now)
    zone = status.monitoring.timezone if status.monitoring else "UTC"
    rows = [
        safety_wording.monitoring_sentence(
            active=status.monitoring is not None,
            ends_at=status.monitoring.ends_at if status.monitoring else None,
            zone=zone,
        )
    ]
    if status.monitoring is not None:
        rows.append(
            f"Response timeout: {status.monitoring.response_timeout_seconds} seconds."
        )
        rows.append(safety_wording.MONITORING_WITHOUT_DETECTION)
    rows.append(
        f"Emergency contacts: {status.emergency_contact_count}."
        if status.emergency_contact_count
        else safety_wording.NO_EMERGENCY_CONTACTS
    )
    if not status.external_delivery_available:
        rows.append(safety_wording.NO_DELIVERY_PROVIDERS)
    if status.active_event is not None:
        rows.append(
            "There is a safety event in progress: "
            f"{safety_wording.EVENT_TYPE_LABELS[status.active_event.event_type]}."
        )
    return ToolOutcome(_lines("Safety status", rows))


def get_active_safety_event(context: ToolContext, args: NoArgs) -> ToolOutcome:
    """The event in flight, if there is one (section 56)."""
    event = safety_events.active_event(context.db, context.profile.id)
    if event is None:
        return ToolOutcome("No safety event is in progress.")
    zone = event.session.timezone if event.session is not None else "UTC"
    rows = [
        safety_wording.EVENT_TYPE_LABELS[event.event_type],
        f"Started {safety_wording.format_moment(event.triggered_at, zone)}.",
        f"Status: {event.status.replace('_', ' ')}.",
    ]
    if event.response_deadline_at is not None and event.user_response is None:
        rows.append(
            "Waiting for an answer until "
            f"{safety_wording.format_time(event.response_deadline_at, zone)}."
        )
    return ToolOutcome(_lines("Safety event", rows))


def get_escalation_status(context: ToolContext, args: NoArgs) -> ToolOutcome:
    """What escalation actually did (sections 42 and 96).

    Returns the attempt lines verbatim from ``services.safety.wording``, so
    the model is given facts it can repeat rather than an outcome it has to
    describe. Section 96's example -- "An in-app alert was created for Ayesha.
    Calling is not configured." -- is literally two of these lines.
    """
    event = safety_events.active_event(context.db, context.profile.id)
    if event is None:
        recent = safety_events.list_events(context.db, context.profile.id, limit=1)
        event = recent[0] if recent else None
    if event is None:
        return ToolOutcome("No safety event has happened.")
    if event.escalation_started_at is None:
        return ToolOutcome("No escalation has started for that safety event.")
    attempts = safety_escalation.attempts_for(context.db, event.id)
    rows = [
        safety_wording.escalation_line(
            label=attempt.recipient_label,
            channel=attempt.channel,
            status=attempt.status,
        )
        for attempt in attempts[:MAX_ROWS]
    ]
    if event.escalation_outcome:
        rows.append(safety_wording.OUTCOME_LABELS[event.escalation_outcome] + ".")
    return ToolOutcome(_lines("Escalation", rows or [NOTHING_RECORDED]))


def start_safety_monitoring(
    context: ToolContext, args: StartMonitoringArgs
) -> ToolOutcome:
    """Proposes starting monitoring. Does not start it (sections 4 and 56)."""
    label = safety_wording.DURATION_LABELS[args.duration_mode].lower()
    return ToolOutcome(
        "Not started yet. The user has been asked to confirm. Tell them what "
        "you are about to turn on and that you have asked them to confirm.",
        pending=PendingAction(
            tool="start_safety_monitoring",
            arguments={"duration_mode": args.duration_mode},
            summary=f"Turn Safety Monitoring on for {label}?",
        ),
    )


def stop_safety_monitoring(context: ToolContext, args: NoArgs) -> ToolOutcome:
    """Proposes stopping monitoring. Does not stop it (sections 62 and 95)."""
    if not safety_monitoring.monitoring_is_active(
        context.db, context.profile.id, context.now
    ):
        return ToolOutcome("Safety Monitoring is already off.")
    return ToolOutcome(
        "Not stopped yet. The user has been asked to confirm.",
        pending=PendingAction(
            tool="stop_safety_monitoring",
            arguments={},
            summary="Turn Safety Monitoring off?",
        ),
    )


def manual_sos(context: ToolContext, args: NoArgs) -> ToolOutcome:
    """Proposes an emergency request. Does not raise one (sections 13 and 57).

    The fast path for a real emergency is not this tool: "Nura, emergency" is
    matched before any model is called and escalates immediately (section 14).
    This exists for ambiguous phrasing, where asking first is right.
    """
    live = safety_events.active_event(context.db, context.profile.id)
    if live is not None:
        return ToolOutcome(
            "An emergency request is already in progress. Tell the user that, "
            "and what the escalation has done so far."
        )
    return ToolOutcome(
        "Not sent yet. The user has been asked to confirm. Keep the reply "
        "short and do not say anybody has been contacted.",
        pending=PendingAction(
            tool="manual_sos",
            arguments={},
            summary="Start an emergency request?",
        ),
    )


def respond_to_safety_check(
    context: ToolContext, args: SafetyResponseArgs
) -> ToolOutcome:
    """Answers a safety check (sections 24, 25 and 26).

    ``need_help`` acts at once; ``im_okay`` asks first. Erring towards help is
    a safe error and erring towards "they are fine" is not: a model that ends
    an escalation because it misread a sentence has done the one unrecoverable
    thing in this feature.
    """
    event = safety_events.active_event(context.db, context.profile.id)
    if event is None:
        return ToolOutcome("There is no safety check to answer.", is_error=True)

    if args.response == "need_help":
        safety_checks.respond(
            context.db,
            event,
            response="need_help",
            actor=context.account,
            now=context.now,
        )
        return ToolOutcome(
            "Escalation has started. Report only what the escalation actually "
            "did -- use get_escalation_status -- and never say anybody has "
            "been reached."
        )

    return ToolOutcome(
        "Not recorded yet. The user has been asked to confirm.",
        pending=PendingAction(
            tool="respond_to_safety_check",
            arguments={"response": "im_okay"},
            summary="Let Nura know you are okay and stop the emergency request?",
        ),
    )


def get_active_safety_alerts(context: ToolContext, args: NoArgs) -> ToolOutcome:
    """A caregiver's safety alerts about this person (section 97).

    Caregiver-only in practice: an owner reading their own profile has no
    alerts of their own, and is told where their safety history is instead of
    being shown an empty list that reads as "nothing happened".
    """
    scope = caregiver_permissions.resolve_scope(
        context.db, context.account, context.profile.id
    )
    if scope.relationship is None:
        return ToolOutcome(
            "Safety alerts are for caregivers. Use get_safety_status for this "
            "person's own safety history."
        )
    views = safety_alerts.list_for_caregiver(context.db, scope)
    if not views:
        return ToolOutcome(NOTHING_RECORDED)
    rows = [
        safety_wording.caregiver_alert_sentence(
            event_type=view.event_type,
            when=view.triggered_at,
            zone=view.zone,
            no_response_seconds=view.no_response_seconds,
        )
        + (" Acknowledged." if view.acknowledged_at else " Not acknowledged.")
        + f" (id {view.id})"
        for view in views[:MAX_ROWS]
    ]
    return ToolOutcome(_lines("Safety alerts", rows))


def acknowledge_safety_alert(
    context: ToolContext, args: AcknowledgeAlertArgs
) -> ToolOutcome:
    """Records "I'm checking on them" (sections 84, 97 and 125).

    The one caregiver write in the tool layer, and it is allowed because of
    what it is: one timestamp saying a caregiver said they would look in. It
    does not resolve the event (section 125), it does not reach the primary
    user, and it changes nothing about the escalation. Every other caregiver
    change still goes through a suggestion the person approves (PRD 9,
    section 64).
    """
    scope = caregiver_permissions.resolve_scope(
        context.db, context.account, context.profile.id
    )
    if scope.relationship is None:
        return ToolOutcome(
            "Only a caregiver can acknowledge a safety alert.", is_error=True
        )
    try:
        alert_id = uuid.UUID(args.alert_id)
    except ValueError:
        return ToolOutcome("That is not a safety alert id.", is_error=True)
    try:
        alert = safety_alerts.get_for_caregiver(context.db, scope, alert_id)
    except NotFoundError:
        return ToolOutcome("There is no safety alert with that id.", is_error=True)
    safety_alerts.acknowledge(context.db, alert, scope, now=context.now)
    return ToolOutcome(
        "Recorded that the caregiver is checking on them. This does not "
        "resolve the safety event and does not mean anybody has been reached."
    )


# --- daily life (PRD 12, sections 21-24) ------------------------------------
#
# Six reads and seven writes, and the writes split on one line that section 22
# draws: creating a task, a reminder or an alarm, and marking a task done, are
# small, visible in the app and easy to undo, so they happen. Changing
# something that already exists, creating a routine, and pausing a routine are
# proposed, because each one changes something the person already arranged.
#
# ``permission=None`` on all of them except the two routine reads, which is
# owner-only -- section 42's rule, made structural: a caregiver's assistant has
# no tool that can see a task, an alarm or a general reminder, so there is
# nothing to filter. The two routine reads carry ``permission="routines"``,
# which section 16 grants. Neither routine *write* is caregiver-writable: a
# caregiver's change goes through a suggestion the person approves (PRD 9,
# section 64).


def _own_medication_names(context: ToolContext) -> list[str]:
    """The medications on this person's record, for section 23's check.

    Names only, and only this profile's -- read through the same
    profile-scoped query every other tool uses. They never leave this
    function: ``boundaries`` reduces them to words and returns a boolean, so a
    medication name cannot reach a log line, a task payload or the model
    through this path.
    """
    return [
        name
        for (name,) in context.db.execute(
            select(Medication.name).where(
                Medication.profile_id == context.profile.id,
                Medication.is_active.is_(True),
            )
        ).all()
    ]


def _parse_date(value: str | None) -> date | None:
    """A ``YYYY-MM-DD`` string, or None. Raises nothing: a bad one is None."""
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _parse_time(value: str | None) -> dt_time | None:
    if not value:
        return None
    try:
        hour, minute = value.split(":")
        return dt_time(hour=int(hour), minute=int(minute))
    except (ValueError, TypeError):
        return None


def _zone_for_writes(context: ToolContext) -> zones.KnownZone | None:
    """The zone this person's own records are in, or None (section 22).

    None is a real answer and the tools act on it: a model cannot know where
    somebody is, and guessing would put a seven o'clock reminder at an hour
    nobody chose. See ``services.productivity.zones``.
    """
    return zones.known_zone(context.db, context.profile.id)


NO_ZONE_KNOWN = (
    "Nura does not know which time zone this person is in -- they have nothing "
    "else scheduled yet, and nothing in a conversation can tell you. Say that, "
    "and offer either a task with no time or setting the first reminder in the "
    "app."
)


def _daily_life_id(value: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(value)
    except ValueError:
        return None


def get_tasks(context: ToolContext, args: TaskScopeArgs) -> ToolOutcome:
    """The user's tasks, with their ids so other tools can name one."""
    rows = task_service.list_tasks(context.db, context.profile.id, scope=args.scope)
    lines = []
    for task in rows[:MAX_ROWS]:
        parts = [task.title]
        if task.due_at is not None:
            parts.append(
                productivity_wording.due_label(
                    task.due_at, task.timezone, context.local_date
                )
                or ""
            )
        if task.priority == "important":
            parts.append("important")
        if task_service.is_overdue(task, context.now):
            parts.append("past its due time")
        lines.append(" - ".join(part for part in parts if part) + f" (id {task.id})")
    return ToolOutcome(_clip(_lines(f"Tasks ({args.scope})", lines)))


def get_today_tasks(context: ToolContext, args: NoArgs) -> ToolOutcome:
    """Tasks due today, and anything past its due time."""
    due = task_service.due_today(context.db, context.profile.id, context.local_date)
    overdue = task_service.overdue(context.db, context.profile.id, context.now)
    seen: dict[uuid.UUID, Any] = {task.id: task for task in [*overdue, *due]}
    lines = [
        task.title
        + (" - past its due time" if task_service.is_overdue(task, context.now) else "")
        + f" (id {task.id})"
        for task in list(seen.values())[:MAX_ROWS]
    ]
    return ToolOutcome(_clip(_lines("Tasks for today", lines)))


def get_reminders(context: ToolContext, args: NoArgs) -> ToolOutcome:
    """The reminders set up, and when each next happens."""
    reminder_service.replenish(context.db, context.profile.id, context.now)
    rows = reminder_service.list_reminders(context.db, context.profile.id)
    lines = []
    for reminder in rows[:MAX_ROWS]:
        schedule = productivity_wording.recurrence_sentence(
            recurrence=reminder.recurrence,
            time_of_day=reminder.time_of_day,
            weekdays=reminder.weekdays,
            day_of_month=reminder.day_of_month,
            start_date=reminder.start_date,
        )
        state = productivity_wording.REMINDER_STATUS_LABELS[reminder.status]
        lines.append(f"{reminder.title} - {schedule} ({state.lower()})")
    return ToolOutcome(_clip(_lines("Reminders", lines)))


def get_alarms(context: ToolContext, args: NoArgs) -> ToolOutcome:
    """The alarms set, and the honest sentence about what an alarm is here."""
    rows = alarm_service.list_alarms(context.db, context.profile.id)
    lines = [
        f"{alarm.label} - "
        + productivity_wording.recurrence_sentence(
            recurrence=alarm.recurrence,
            time_of_day=alarm.time_of_day,
            weekdays=alarm.weekdays,
            start_date=alarm.on_date,
        )
        + ("" if alarm.enabled else " (off)")
        for alarm in rows[:MAX_ROWS]
    ]
    body = _lines("Alarms", lines)
    # Section 11, handed to the model rather than left for it to infer. A model
    # that is told an alarm has never been tested on a phone will say so; one
    # that is only shown a list will describe it as an alarm.
    return ToolOutcome(_clip(f"{body}\n{productivity_wording.ALARM_LIMITATION}"))


def get_routines(context: ToolContext, args: NoArgs) -> ToolOutcome:
    """The routines set up, with their steps and their ids."""
    rows = routine_service.list_routines(context.db, context.profile.id)
    lines = []
    for routine in rows[:MAX_ROWS]:
        schedule = productivity_wording.recurrence_sentence(
            recurrence=routine.schedule_type,
            time_of_day=routine.time_of_day,
            weekdays=routine.weekdays,
            start_date=routine.start_date,
        )
        steps = ", ".join(
            step.title for step in sorted(routine.steps, key=lambda s: s.position)
        )
        state = productivity_wording.ROUTINE_STATUS_LABELS[routine.status].lower()
        lines.append(f"{routine.title} - {schedule} ({state}): {steps} (id {routine.id})")
    return ToolOutcome(_clip(_lines("Routines", lines)))


def get_today_routine_runs(context: ToolContext, args: NoArgs) -> ToolOutcome:
    """How today's routines are going."""
    routine_service.replenish(context.db, context.profile.id, context.now)
    runs = routine_service.runs_for_today(context.db, context.profile.id, context.now)
    lines = []
    for run in runs[:MAX_ROWS]:
        progress = routine_service.progress(run)
        lines.append(
            f"{run.routine.title} - "
            + productivity_wording.ROUTINE_RUN_STATUS_LABELS[run.status].lower()
            + ", "
            + productivity_wording.routine_run_sentence(
                done=progress.done,
                total=progress.total,
                next_title=(
                    None if progress.next_step is None else progress.next_step.title
                ),
            )
        )
    return ToolOutcome(_clip(_lines("Routines today", lines)))


# --- the low-risk writes (section 22) ---------------------------------------


def create_task(context: ToolContext, args: CreateTaskArgs) -> ToolOutcome:
    """Creates a task straight away (section 22).

    A task is the clearest case for section 22's low-risk policy: it appears in
    a list, it changes nothing else, and Undo is one tap. Asking "shall I?"
    for every one would make Nura slower than typing it.

    Two things still happen before the row is written. A due time needs a zone,
    and if nobody has told us one the tool says so instead of choosing. And
    section 23's phrasing check runs, so a task that reads as a dose change is
    written down *and* answered with where dose changes come from.
    """
    due_date = _parse_date(args.due_date)
    due_time = _parse_time(args.due_time)
    if due_time is not None and due_date is None:
        return ToolOutcome(
            "A time needs a day as well. Ask which day they mean.", is_error=True
        )

    due_at = None
    timezone = "UTC"
    zone_note = ""
    if due_date is not None:
        found = _zone_for_writes(context)
        if found is None:
            return ToolOutcome(NO_ZONE_KNOWN, is_error=True)
        timezone = found.name
        due_at = recurrence.occurrence_instant(
            due_date, due_time or dt_time(9, 0), recurrence.zone_for(found.name)
        )
        zone_note = f" The time is {found.name}, which is what their other items use."

    try:
        task = task_service.create_task(
            context.db,
            context.profile.id,
            task_service.TaskInput(
                title=args.title,
                notes=args.notes,
                priority=args.priority,
                due_at=due_at,
                timezone=timezone,
                source="assistant",
            ),
            context.now,
        )
    except DomainError as error:
        return ToolOutcome(error.message, is_error=True)

    when = (
        productivity_wording.due_label(task.due_at, task.timezone, context.local_date)
        or "no due date"
    )
    message = f'Added the task "{task.title}" ({when}).{zone_note}'
    if boundaries.mentions_medication_change(
        args.title, args.notes, medication_names=_own_medication_names(context)
    ):
        # Section 23. The note is written -- refusing would leave them with
        # nothing -- and the sentence is mandatory, not optional colour.
        message += (
            " This reads like a change to their medication. Tell them you have "
            "written it down as a note and say exactly this: "
            f'"{productivity_wording.MEDICATION_CHANGE_BOUNDARY}"'
        )
    return ToolOutcome(_clip(message))


def complete_task(context: ToolContext, args: TaskIdArgs) -> ToolOutcome:
    """Marks a task done straight away (section 22)."""
    task_id = _daily_life_id(args.task_id)
    if task_id is None:
        return ToolOutcome("That is not a task id.", is_error=True)
    try:
        task = task_service.get_task(context.db, context.profile.id, task_id)
    except NotFoundError:
        return ToolOutcome("There is no task with that id.", is_error=True)
    updated, applied = task_service.complete_task(context.db, task, context.now)
    if not applied:
        return ToolOutcome(f'"{updated.title}" was already done.')
    return ToolOutcome(f'Marked "{updated.title}" as done.')


def create_reminder(context: ToolContext, args: CreateReminderArgs) -> ToolOutcome:
    """Creates a reminder straight away (section 22).

    The time is required by the argument model, which is section 22's
    clarification rule turned into a schema: "remind me later" cannot reach
    this function, because a call without a time does not validate and the
    model is told why.
    """
    moment = _parse_time(args.time)
    if moment is None:
        return ToolOutcome(productivity_wording.REMINDER_NEEDS_A_TIME, is_error=True)
    found = _zone_for_writes(context)
    if found is None:
        return ToolOutcome(NO_ZONE_KNOWN, is_error=True)

    start = _parse_date(args.start_date) or context.local_date
    try:
        reminder = reminder_service.create_reminder(
            context.db,
            context.profile.id,
            reminder_service.ReminderInput(
                title=args.title,
                time_of_day=moment,
                start_date=start,
                recurrence=args.repeat,
                timezone=found.name,
                weekdays=args.weekdays,
                day_of_month=args.day_of_month,
                source="assistant",
            ),
            context.now,
        )
    except DomainError as error:
        return ToolOutcome(error.message, is_error=True)

    schedule = productivity_wording.recurrence_sentence(
        recurrence=reminder.recurrence,
        time_of_day=reminder.time_of_day,
        weekdays=reminder.weekdays,
        day_of_month=reminder.day_of_month,
        start_date=reminder.start_date,
    )
    message = f'Set a reminder: "{reminder.title}", {schedule} ({found.name}).'
    if boundaries.mentions_medication_change(
        args.title, medication_names=_own_medication_names(context)
    ):
        message += (
            " This reads like a change to their medication. Say exactly this: "
            f'"{productivity_wording.MEDICATION_CHANGE_BOUNDARY}"'
        )
    return ToolOutcome(_clip(message))


def create_alarm(context: ToolContext, args: CreateAlarmArgs) -> ToolOutcome:
    """Creates an alarm straight away, and says what an alarm is here.

    Section 22 lists creating an alarm as low-risk, and it is -- but section 11
    means the reply cannot stop at "done". The limitation sentence is part of
    what this tool returns, so the model is repeating a fact rather than
    deciding how confident to sound.
    """
    moment = _parse_time(args.time)
    if moment is None:
        return ToolOutcome("An alarm needs a time.", is_error=True)
    found = _zone_for_writes(context)
    if found is None:
        return ToolOutcome(NO_ZONE_KNOWN, is_error=True)

    on_date = _parse_date(args.on_date)
    if args.repeat == "one_time" and on_date is None:
        on_date = context.local_date

    try:
        alarm = alarm_service.create_alarm(
            context.db,
            context.profile.id,
            alarm_service.AlarmInput(
                label=args.label,
                time_of_day=moment,
                recurrence=args.repeat,
                timezone=found.name,
                weekdays=args.weekdays,
                on_date=on_date if args.repeat == "one_time" else None,
                source="assistant",
            ),
            context.now,
        )
    except DomainError as error:
        return ToolOutcome(error.message, is_error=True)

    schedule = productivity_wording.recurrence_sentence(
        recurrence=alarm.recurrence,
        time_of_day=alarm.time_of_day,
        weekdays=alarm.weekdays,
        start_date=alarm.on_date,
    )
    return ToolOutcome(
        _clip(
            f'Set an alarm: "{alarm.label}", {schedule} ({found.name}). '
            "Tell them this as well, in your own words: "
            f'"{productivity_wording.ALARM_LIMITATION}"'
        )
    )


# --- the writes that ask first (section 22) ---------------------------------


def update_task(context: ToolContext, args: UpdateTaskArgs) -> ToolOutcome:
    """Proposes a change to a task. Does not make it.

    Creating a task is low-risk because nothing existed before it. Editing one
    is not quite: the person wrote those words, and a model that rephrases a
    title has changed something they chose. So this asks.
    """
    task_id = _daily_life_id(args.task_id)
    if task_id is None:
        return ToolOutcome("That is not a task id.", is_error=True)
    try:
        task = task_service.get_task(context.db, context.profile.id, task_id)
    except NotFoundError:
        return ToolOutcome("There is no task with that id.", is_error=True)

    changes = args.model_dump(exclude_none=True, exclude={"task_id"})
    if not changes:
        return ToolOutcome("There is nothing to change.", is_error=True)
    if "due_time" in changes and "due_date" not in changes and task.due_at is None:
        return ToolOutcome(
            "A time needs a day as well. Ask which day they mean.", is_error=True
        )

    described = ", ".join(
        f"{key.replace('_', ' ')} to {value}" for key, value in changes.items()
    )
    return ToolOutcome(
        "Not changed yet. The user has been asked to confirm. Tell them what "
        "you are about to change and that you have asked them to confirm.",
        pending=PendingAction(
            tool="update_task",
            arguments={"task_id": str(task.id), **changes},
            summary=f'Change "{task.title}": {described}?',
        ),
    )


def create_routine(context: ToolContext, args: CreateRoutineArgs) -> ToolOutcome:
    """Proposes a routine. Does not create it (sections 22 and 24).

    A routine is a standing commitment with a schedule and steps, not a line on
    a list, so section 22's low-risk policy does not reach it. Asking also
    gives the person the one look at the steps that matters: section 24 allows
    Nura to set up a routine *they* decided on, and a confirmation screen is
    where "this is what you asked for" is actually checked.
    """
    moment = _parse_time(args.time)
    if moment is None:
        return ToolOutcome("A routine needs a time.", is_error=True)
    found = _zone_for_writes(context)
    if found is None:
        return ToolOutcome(NO_ZONE_KNOWN, is_error=True)
    if args.repeat == "selected_days" and not args.weekdays:
        return ToolOutcome("Ask which days of the week they mean.", is_error=True)

    schedule = productivity_wording.recurrence_sentence(
        recurrence=args.repeat,
        time_of_day=moment,
        weekdays=args.weekdays,
        start_date=context.local_date,
    )
    steps = ", ".join(args.steps)
    message = (
        "Not created yet. The user has been asked to confirm. Tell them the "
        "steps and the time, and that you have asked them to confirm."
    )
    if boundaries.mentions_clinical_routine(args.title, *args.steps):
        # Section 24. Nura may set up a routine the person or their clinician
        # decided on; it must not be read as Nura prescribing one.
        message += (
            " Say this as well, in your own words: "
            f'"{productivity_wording.CLINICAL_ROUTINE_BOUNDARY}"'
        )
    return ToolOutcome(
        message,
        pending=PendingAction(
            tool="create_routine",
            arguments={
                "title": args.title,
                "time": args.time,
                "repeat": args.repeat,
                "weekdays": args.weekdays,
                "steps": list(args.steps),
            },
            summary=f'Set up "{args.title}" - {schedule}, with: {steps}?',
        ),
    )


def pause_routine(context: ToolContext, args: RoutineIdArgs) -> ToolOutcome:
    """Proposes pausing a routine. Does not pause it.

    Pausing stops something the person set up and keeps happening. That is
    worth one tap, in the same way turning Safety Monitoring off is.
    """
    routine_id = _daily_life_id(args.routine_id)
    if routine_id is None:
        return ToolOutcome("That is not a routine id.", is_error=True)
    try:
        routine = routine_service.get_routine(context.db, context.profile.id, routine_id)
    except NotFoundError:
        return ToolOutcome("There is no routine with that id.", is_error=True)
    if routine.status == "paused":
        return ToolOutcome(f'"{routine.title}" is already paused.')

    return ToolOutcome(
        "Not paused yet. The user has been asked to confirm.",
        pending=PendingAction(
            tool="pause_routine",
            arguments={"routine_id": str(routine.id)},
            summary=f'Pause "{routine.title}"?',
        ),
    )


# --- confirmations ----------------------------------------------------------


def _confirm_update_task(context: ToolContext, action: PendingAction) -> str:
    """Applies a confirmed task edit.

    Re-resolves the task through the profile-scoped lookup rather than trusting
    the id on the pending action: a confirmation that arrives an hour later is
    still checked against who is asking now.
    """
    task_id = _daily_life_id(str(action.arguments.get("task_id", "")))
    if task_id is None:
        return "That task is no longer there, so nothing was changed."
    try:
        task = task_service.get_task(context.db, context.profile.id, task_id)
    except NotFoundError:
        return "That task is no longer there, so nothing was changed."

    fields: dict[str, Any] = {}
    for key in ("title", "notes", "priority"):
        if action.arguments.get(key) is not None:
            fields[key] = action.arguments[key]
    due_date = _parse_date(action.arguments.get("due_date"))
    due_time = _parse_time(action.arguments.get("due_time"))
    if due_date is not None:
        found = _zone_for_writes(context)
        zone_name = found.name if found is not None else task.timezone
        fields["timezone"] = zone_name
        fields["due_at"] = recurrence.occurrence_instant(
            due_date, due_time or dt_time(9, 0), recurrence.zone_for(zone_name)
        )
    if not fields:
        return "There was nothing to change."
    try:
        updated, applied = task_service.update_task(context.db, task, fields, context.now)
    except DomainError as error:
        return error.message
    if not applied:
        return f'"{updated.title}" had already been changed since, so nothing was done.'
    return f'Updated "{updated.title}".'


def _confirm_create_routine(context: ToolContext, action: PendingAction) -> str:
    moment = _parse_time(action.arguments.get("time"))
    if moment is None:
        return "That routine had no time, so nothing was created."
    found = _zone_for_writes(context)
    if found is None:
        return "Nura still does not know which time zone to use, so nothing was created."
    steps = [str(step) for step in action.arguments.get("steps", []) if str(step).strip()]
    if not steps:
        return "That routine had no steps, so nothing was created."
    weekdays = action.arguments.get("weekdays")
    try:
        routine = routine_service.create_routine(
            context.db,
            context.profile.id,
            routine_service.RoutineInput(
                title=str(action.arguments.get("title", "Routine")),
                time_of_day=moment,
                start_date=context.local_date,
                schedule_type=str(action.arguments.get("repeat", "daily")),
                timezone=found.name,
                weekdays=list(weekdays) if weekdays else None,
                source="assistant",
            ),
            [routine_service.StepInput(title=step) for step in steps],
            context.now,
        )
    except DomainError as error:
        return error.message
    return f'Set up "{routine.title}" with {len(steps)} steps.'


def _confirm_pause_routine(context: ToolContext, action: PendingAction) -> str:
    routine_id = _daily_life_id(str(action.arguments.get("routine_id", "")))
    if routine_id is None:
        return "That routine is no longer there."
    try:
        routine = routine_service.get_routine(context.db, context.profile.id, routine_id)
    except NotFoundError:
        return "That routine is no longer there."
    routine_service.set_paused(context.db, routine, paused=True, now=context.now)
    return f'Paused "{routine.title}". Nothing already recorded has changed.'


#: The daily-life pending actions. Looked up rather than branched on, so adding
#: one cannot silently miss the confirmation path -- the same shape the safety
#: tools use.
_DAILY_LIFE_PENDING = {
    "update_task": _confirm_update_task,
    "create_routine": _confirm_create_routine,
    "pause_routine": _confirm_pause_routine,
}


# --- the appointment write (PRD 8, section 14) -------------------------------


def add_appointment_question(context: ToolContext, args: AddQuestionArgs) -> ToolOutcome:
    """Proposes a question. Does not add it (sections 14 and 53).

    Everything that can be checked beforehand is checked here -- that there is
    an appointment, that it has room -- so Confirm does not fail on something
    that was knowable before the user was asked.
    """
    appointment = _appointment_for(context, args.appointment_id)
    if appointment is None:
        return ToolOutcome(
            "There is no upcoming appointment to add a question to. The user "
            "would need to add an appointment first.",
            is_error=True,
        )
    existing = question_service.list_questions(context.db, appointment.id)
    if len(existing) >= question_service.MAX_QUESTIONS:
        return ToolOutcome(
            f"That appointment already has the maximum of "
            f"{question_service.MAX_QUESTIONS} questions.",
            is_error=True,
        )
    return ToolOutcome(
        "Not added yet. The user has been asked to confirm, and will be told "
        "the outcome. Tell them what you are about to add and that you have "
        "asked them to confirm.",
        pending=PendingAction(
            tool="add_appointment_question",
            arguments={
                "text": args.text,
                "appointment_id": str(appointment.id),
            },
            summary=f'Add "{args.text}" to your questions for {appointment.title}?',
        ),
    )


def run_pending_action(context: ToolContext, action: PendingAction) -> str:
    """Carries out a confirmed write, and says what happened.

    Re-resolves the appointment through the profile-scoped lookup rather than
    trusting the id recorded on the pending action: a confirmation that
    arrives an hour later is still checked against who is asking now.
    """
    if action.tool in _SAFETY_PENDING:
        return _SAFETY_PENDING[action.tool](context, action)
    if action.tool in _DAILY_LIFE_PENDING:
        return _DAILY_LIFE_PENDING[action.tool](context, action)

    if action.tool != "add_appointment_question":
        raise ValueError(f"Unknown pending action: {action.tool}")

    appointment = _appointment_for(context, action.arguments.get("appointment_id"))
    if appointment is None:
        return "That appointment is no longer there, so nothing was added."
    text = str(action.arguments.get("text", "")).strip()
    if not text:
        return "There was no question to add."
    question, created = question_service.create_question(
        context.db, appointment, text=text
    )
    appointment_service.refresh_preparation_status(context.db, appointment)
    if not created:
        return f'"{question.text}" was already on your list for {appointment.title}.'
    return f'Added "{question.text}" to your questions for {appointment.title}.'


def _confirm_start_monitoring(context: ToolContext, action: PendingAction) -> str:
    """Starts monitoring after the person said yes (PRD 10, section 4).

    UTC, because this path has no time zone -- which is also why
    ``StartMonitoringArgs`` does not offer "until bedtime". A fixed duration
    is the same length of time in every zone, so nothing here depends on
    guessing one.
    """
    mode = str(action.arguments.get("duration_mode", "1_hour"))
    session = safety_monitoring.start(
        context.db,
        context.profile,
        context.account,
        duration_mode=mode,
        timezone_name="UTC",
        now=context.now,
    )
    label = safety_wording.DURATION_LABELS[session.duration_mode].lower()
    return (
        f"Safety Monitoring is on for {label}. Automatic detection by the "
        "robot is not connected, so Nura will not notice anything by itself."
    )


def _confirm_stop_monitoring(context: ToolContext, action: PendingAction) -> str:
    session = safety_monitoring.active_session(
        context.db, context.profile.id, context.now
    )
    if session is None:
        return "Safety Monitoring was already off."
    safety_monitoring.stop(context.db, session, context.account, now=context.now)
    return "Safety Monitoring is off."


def _confirm_manual_sos(context: ToolContext, action: PendingAction) -> str:
    """Raises the emergency request the person confirmed (section 12).

    Reports what escalation *did*, line by line, and nothing else. Section 96
    forbids hallucinating a delivery, and the sentences come from
    ``services.safety.wording`` rather than from this function.
    """
    event = safety_events.create(
        context.db,
        context.profile,
        event_type="manual_sos",
        trigger_source="mobile_manual",
        now=context.now,
        actor_account_id=context.account.id,
        actor_kind="primary_user",
    )
    context.db.commit()
    attempts = safety_escalation.attempts_for(context.db, event.id)
    lines = [
        safety_wording.escalation_line(
            label=attempt.recipient_label,
            channel=attempt.channel,
            status=attempt.status,
        )
        for attempt in attempts
    ]
    if not lines:
        return "Emergency request recorded. " + safety_wording.NO_EMERGENCY_CONTACTS
    return "Emergency request recorded. " + " ".join(lines)


def _confirm_safety_response(context: ToolContext, action: PendingAction) -> str:
    event = safety_events.active_event(context.db, context.profile.id)
    if event is None:
        return "That safety event has already finished."
    safety_checks.respond(
        context.db, event, response="im_okay", actor=context.account, now=context.now
    )
    return "Recorded that you are okay. Nothing further will be sent."


#: Pending actions the safety tools create. Looked up rather than branched on,
#: so adding one cannot silently miss the confirmation path.
_SAFETY_PENDING = {
    "start_safety_monitoring": _confirm_start_monitoring,
    "stop_safety_monitoring": _confirm_stop_monitoring,
    "manual_sos": _confirm_manual_sos,
    "respond_to_safety_check": _confirm_safety_response,
}


# --- the registry -----------------------------------------------------------


@dataclass(frozen=True)
class Tool:
    """One tool: its schema, its argument model, and what it does."""

    name: str
    description: str
    args_model: type[_Args]
    run: Callable[[ToolContext, Any], ToolOutcome]
    #: The PRD 9 permission category this tool reads, or None for owner-only
    #: (PRD 9, section 63). Owner-only is right for a tool that spans several
    #: categories, because a caregiver is granted them one at a time.
    permission: str | None = None
    #: True for a tool that proposes or makes a change (PRD 8, section 53).
    writes: bool = False
    #: The mirror of ``permission=None``: a tool only a caregiver may use
    #: (PRD 10, section 97). An owner reading their own profile has no alerts
    #: of their own, so showing them the tool would be showing them one that
    #: can only answer "that is not for you".
    caregiver_only: bool = False
    #: The single exception to "a caregiver's changes go through a suggestion"
    #: (PRD 9, section 64; PRD 10, sections 84, 97 and 125). Set on exactly one
    #: tool: acknowledging a safety alert, which writes one timestamp saying a
    #: caregiver said they would look in. It resolves nothing, reaches nobody
    #: and changes no record. Everything else a caregiver would change is still
    #: a suggestion a person approves.
    caregiver_writable: bool = False

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            parameters=self.args_model.model_json_schema(),
        )


TOOLS: tuple[Tool, ...] = (
    # ``permission=None`` on the first and the last two is owner-only, and each
    # is deliberate. Today's summary and the check-in history span categories a
    # caregiver is granted separately -- a caregiver with only `appointments`
    # must not learn symptom counts through a tool that mentions them in passing
    # (PRD 9, section 18) -- and the caregiver home in
    # ``services.caregivers.care_view`` is the permission-filtered equivalent.
    # The write tool is owner-only because PRD 9 section 64 says a caregiver's
    # changes go through a suggestion a person approves.
    Tool(
        "get_today_summary",
        "What is on the user's Today screen: doses still to record, the next "
        "appointment, active symptoms, and whether today's check-in is done.",
        NoArgs,
        get_today_summary,
    ),
    Tool(
        "get_health_summary",
        "Counts from the user's health record by section, plus how many "
        "conditions, medications and symptoms are active.",
        NoArgs,
        get_health_summary,
        permission="general_health_summary",
    ),
    Tool(
        "get_active_medications",
        "The medications the user is currently taking, with dosage and the "
        "times they are scheduled for.",
        NoArgs,
        get_active_medications,
        permission="medications",
    ),
    Tool(
        "get_recent_medication_history",
        "How many doses in a recent window were taken, skipped or missed. Counts only.",
        MedicationHistoryArgs,
        get_recent_medication_history,
        permission="medications",
    ),
    Tool(
        "get_active_symptoms",
        "The symptom episodes the user currently has open, with the severity "
        "and change they last recorded.",
        NoArgs,
        get_active_symptoms,
        permission="symptoms",
    ),
    Tool(
        "get_recent_symptom_entries",
        "Individual symptom entries from a recent window, newest first, with "
        "the severity recorded at the time.",
        RecentSymptomArgs,
        get_recent_symptom_entries,
        permission="symptoms",
    ),
    Tool(
        "get_upcoming_appointments",
        "Appointments the user still has ahead of them, soonest first.",
        NoArgs,
        get_upcoming_appointments,
        permission="appointments",
    ),
    Tool(
        "get_appointment_questions",
        "The questions the user has already written down for an appointment.",
        AppointmentQuestionsArgs,
        get_appointment_questions,
        permission="appointments",
    ),
    Tool(
        "get_daily_checkin_summary",
        "How many daily check-ins the user completed recently and what they recorded.",
        NoArgs,
        get_daily_checkin_summary,
    ),
    Tool(
        "get_safety_status",
        "Whether Safety Monitoring is on, when it ends, how many emergency "
        "contacts there are, and which ways of reaching anybody are not set up.",
        NoArgs,
        get_safety_status,
    ),
    Tool(
        "get_active_safety_event",
        "The safety event in progress, if there is one, and whether Nura is "
        "still waiting for an answer.",
        NoArgs,
        get_active_safety_event,
    ),
    Tool(
        "get_escalation_status",
        "Exactly what the most recent escalation did: which alerts were "
        "created and which channels are not set up. Never proof anybody was "
        "reached.",
        NoArgs,
        get_escalation_status,
    ),
    Tool(
        "start_safety_monitoring",
        "Propose turning Safety Monitoring on. This does not turn it on: the "
        "user is asked to confirm first.",
        StartMonitoringArgs,
        start_safety_monitoring,
        writes=True,
    ),
    Tool(
        "stop_safety_monitoring",
        "Propose turning Safety Monitoring off. This does not turn it off: "
        "the user is asked to confirm first.",
        NoArgs,
        stop_safety_monitoring,
        writes=True,
    ),
    Tool(
        "manual_sos",
        "Propose starting an emergency request. This does not start one: the "
        "user is asked to confirm first.",
        NoArgs,
        manual_sos,
        writes=True,
    ),
    Tool(
        "respond_to_safety_check",
        "Answer a safety check. 'I need help' starts escalation immediately; "
        "'I'm okay' asks the user to confirm before stopping anything.",
        SafetyResponseArgs,
        respond_to_safety_check,
        writes=True,
    ),
    Tool(
        "get_active_safety_alerts",
        "For a caregiver: the safety alerts raised about this person, and "
        "whether each has been acknowledged.",
        NoArgs,
        get_active_safety_alerts,
        permission="safety_alerts",
        caregiver_only=True,
    ),
    Tool(
        "acknowledge_safety_alert",
        "For a caregiver: record that they are checking on the person. This "
        "does not resolve the safety event.",
        AcknowledgeAlertArgs,
        acknowledge_safety_alert,
        permission="safety_alerts",
        writes=True,
        caregiver_writable=True,
        caregiver_only=True,
    ),
    Tool(
        "add_appointment_question",
        "Propose adding a question to an appointment. This does not add it: "
        "the user is asked to confirm first.",
        AddQuestionArgs,
        add_appointment_question,
        writes=True,
    ),
    # --- daily life (PRD 12, sections 21 and 22) -------------------------------
    #
    # ``permission=None`` -- owner-only -- on everything except the two routine
    # reads. Section 42 keeps tasks, alarms and general reminders private to the
    # primary user, and this is where that becomes structural: a caregiver's
    # assistant is not shown a task tool and would be refused one it named.
    #
    # Neither routine write is ``caregiver_writable``. A caregiver who wants a
    # routine paused proposes it through ``caregiver_suggestions``, which the
    # person approves (PRD 9, section 64; PRD 12, sections 16 and 17).
    Tool(
        "get_tasks",
        "The user's own tasks, with an id for each so another tool can name one.",
        TaskScopeArgs,
        get_tasks,
    ),
    Tool(
        "get_today_tasks",
        "Tasks due today, and any task past its due time.",
        NoArgs,
        get_today_tasks,
    ),
    Tool(
        "get_reminders",
        "The reminders the user has set up, how often each repeats, and whether "
        "it is on.",
        NoArgs,
        get_reminders,
    ),
    Tool(
        "get_alarms",
        "The alarms the user has set, and what an alarm can and cannot do in this build.",
        NoArgs,
        get_alarms,
    ),
    Tool(
        "get_routines",
        "The user's routines, their steps and their schedules.",
        NoArgs,
        get_routines,
        permission="routines",
    ),
    Tool(
        "get_today_routine_runs",
        "How today's routines are going: how many steps are done and what is next.",
        NoArgs,
        get_today_routine_runs,
        permission="routines",
    ),
    Tool(
        "create_task",
        "Add a task. This happens straight away. A due date is optional; a due "
        "time needs a due date.",
        CreateTaskArgs,
        create_task,
        writes=True,
    ),
    Tool(
        "complete_task",
        "Mark a task as done. This happens straight away and can be undone in the app.",
        TaskIdArgs,
        complete_task,
        writes=True,
    ),
    Tool(
        "create_reminder",
        "Set a reminder at a time of day, once or repeating. This happens "
        "straight away. A reminder must have a time -- ask if you do not have one.",
        CreateReminderArgs,
        create_reminder,
        writes=True,
    ),
    Tool(
        "create_alarm",
        "Set an alarm. This happens straight away. Always tell the user what an "
        "alarm can and cannot do in this build.",
        CreateAlarmArgs,
        create_alarm,
        writes=True,
    ),
    Tool(
        "update_task",
        "Propose a change to an existing task. This does not change it: the "
        "user is asked to confirm first.",
        UpdateTaskArgs,
        update_task,
        writes=True,
    ),
    Tool(
        "create_routine",
        "Propose a routine the user has decided on, with its steps. This does "
        "not create it: the user is asked to confirm first. Never work a "
        "routine out from their symptoms or diagnosis.",
        CreateRoutineArgs,
        create_routine,
        writes=True,
    ),
    Tool(
        "pause_routine",
        "Propose pausing a routine. This does not pause it: the user is asked "
        "to confirm first.",
        RoutineIdArgs,
        pause_routine,
        writes=True,
    ),
)

BY_NAME = {tool.name: tool for tool in TOOLS}


def specs(context: ToolContext) -> tuple[ToolSpec, ...]:
    """What the provider is told about. Stable order, so the prompt prefix is.

    Filtered by what the caller may use (PRD 9, section 63). A caregiver without
    symptom access is not shown a symptom tool at all, which is better than
    showing one and refusing it: a model that can see a tool will eventually
    tell the user it tried.
    """
    return tuple(tool.spec() for tool in TOOLS if context.may_use(tool))


def run(context: ToolContext, name: str, arguments: dict[str, Any]) -> ToolOutcome:
    """Validates and runs one call from the model (sections 91 and 100).

    A tool that does not exist and arguments that do not fit both come back as
    error results rather than exceptions, because both are things the model
    can be told about and try again from. Nothing about either is shown to the
    user, and the log line names the tool and nothing else -- a tool argument
    can contain the user's own words (section 58).
    """
    tool = BY_NAME.get(name)
    if tool is None:
        logger.info("assistant: model asked for an unknown tool")
        return ToolOutcome(f"There is no tool called {name}.", is_error=True)

    # The second half of PRD 9 section 63. Filtering ``specs`` keeps an
    # unavailable tool out of the model's sight; this keeps it out of its reach,
    # for a model that names one anyway from an earlier turn or from a guess.
    # The same answer as an unknown tool, so the reply cannot be read as "that
    # tool exists but you are not allowed it".
    if not context.may_use(tool):
        logger.info("assistant: refused a tool outside this caller's permissions")
        return ToolOutcome(f"There is no tool called {name}.", is_error=True)

    try:
        args = tool.args_model.model_validate(arguments)
    except ValidationError:
        logger.info("assistant: rejected malformed arguments for %s", name)
        return ToolOutcome(
            f"The arguments for {name} did not match its schema.", is_error=True
        )

    logger.info("assistant: ran %s", name)
    return tool.run(context, args)
