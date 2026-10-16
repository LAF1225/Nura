"""What a caregiver may propose, and what approving it does.

PRD 9, sections 20, 21, 22, 23, 24, 25, 26, 64, 74 and 85.

**A caregiver never changes anything.** Section 21 says important changes must
never be applied silently by a caregiver account, and in this codebase they
cannot be applied by one at all: there is no caregiver route that writes to a
medication schedule or an appointment. A caregiver creates a *suggestion*; the
primary user's own account applies it. That is the same shape PRD 8 gave the
assistant's one write (propose, then a person confirms), for the same reason.

**The forbidden changes are absent rather than refused** (section 85).
``change_medication_dose``, ``delete_condition`` and ``change_diagnosis`` are
not validated away -- there is no action type for them, so there is no payload
that could carry one, and the database CHECK constraint on ``action_type`` is
built from the same tuple the registry below is keyed by. A request for one
fails schema validation before any code in this module runs.

**Every payload is validated twice** (section 23). Once when the suggestion is
created, and again at approval, after any amount of time has passed. Nothing
stored in ``payload`` is ever passed to anything without going through its
action's pydantic model first, and ``extra="forbid"`` means a field nobody
declared cannot ride along.

**Approval goes through the normal service layer** (section 24). ``apply``
functions call ``medications.schedules`` and ``appointments.appointments`` --
the same functions the owner's own routes call -- so every rule those services
enforce still applies, future doses are rebuilt the way they always are, and
there is no second code path that can drift. Section 24's five other steps are
in ``approve`` below: re-check the permission, re-find the target, re-validate,
apply, record.

**Approving twice does what approving once did** (section 74).
``applied_resource_id`` is written with the status, so a retried Approve returns
the same suggestion rather than creating a second appointment.
"""

import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import CaregiverSuggestion, Profile, User
from app.models.caregiver import DECLINE_NOTE_MAX_LENGTH
from app.models.enums import (
    APPOINTMENT_TYPES,
    CAREGIVER_SUGGESTION_ACTION_TYPES,
    CAREGIVER_SUGGESTION_OPEN_STATUSES,
    ROUTINE_SCHEDULE_TYPES,
)
from app.models.productivity import (
    BODY_MAX_LENGTH,
    MAX_ROUTINE_STEPS,
    TITLE_MAX_LENGTH,
)
from app.services.appointments import appointments as appointment_service
from app.services.caregivers import audit, permissions, wording
from app.services.caregivers.permissions import CareScope
from app.services.errors import DomainError, NotFoundError
from app.services.medications import schedules as schedule_service
from app.services.productivity import routines as routine_service
from app.services.productivity import wording as productivity_wording

logger = logging.getLogger(__name__)

#: ``HH:MM`` on a 24-hour clock, the same shape the check-in reminder uses.
TIME_PATTERN = r"^([01][0-9]|2[0-3]):[0-5][0-9]$"

#: More than a household generates, and few enough that the review screen is
#: never a backlog nobody can face.
MAX_OPEN_SUGGESTIONS = 20

#: Reminder times a schedule may be moved to in one suggestion.
MAX_SUGGESTED_TIMES = 12


class SuggestionError(DomainError):
    code = "suggestion_error"


class SuggestionNotFoundError(NotFoundError):
    code = "suggestion_not_found"


class InvalidSuggestionError(SuggestionError):
    """The payload did not match the action it claimed to be (section 23)."""

    status_code = 422
    code = "invalid_suggestion"


class SuggestionNotPendingError(SuggestionError):
    """Already approved, declined or withdrawn."""

    status_code = 409
    code = "suggestion_not_pending"


class TooManySuggestionsError(SuggestionError):
    status_code = 409
    code = "too_many_suggestions"


class SuggestionTargetMissingError(SuggestionError):
    """The thing it proposed changing is no longer there (section 24, step 2)."""

    status_code = 409
    code = "suggestion_target_missing"


# --- payloads ---------------------------------------------------------------


class _Payload(BaseModel):
    """Base for every payload: a field nobody declared is refused, not ignored."""

    model_config = ConfigDict(extra="forbid")


class ReminderTimeInput(_Payload):
    time_of_day: str = Field(pattern=TIME_PATTERN)
    #: 0 = Monday, as everywhere else in this codebase. Null on a daily schedule.
    weekday: int | None = Field(default=None, ge=0, le=6)

    def to_time(self) -> time:
        hour, minute = self.time_of_day.split(":")
        return time(hour=int(hour), minute=int(minute))


class ChangeReminderTimePayload(_Payload):
    """The times the caregiver is proposing, in full.

    A replacement list rather than a diff: a schedule with two reminders moved
    by one is unambiguous only if the whole list is restated, and
    ``update_schedule`` already takes exactly this shape.
    """

    times: list[ReminderTimeInput] = Field(min_length=1, max_length=MAX_SUGGESTED_TIMES)


class PauseReminderPayload(_Payload):
    """Nothing to say. Pausing is the whole proposal.

    Deliberately carries no reason: a free-text field here would be a caregiver
    writing something clinical into a record the primary user did not author,
    and section 28's caution about caregivers rewriting history applies just as
    much to annotating it.
    """


class AddAppointmentPayload(_Payload):
    title: str = Field(min_length=1, max_length=120)
    scheduled_at: datetime
    timezone: str = Field(min_length=1, max_length=64)
    appointment_type: str = Field(default="other")
    location_name: str | None = Field(default=None, max_length=120)

    def check(self) -> None:
        if self.appointment_type not in APPOINTMENT_TYPES:
            raise InvalidSuggestionError("That is not an appointment type.")


class ChangeAppointmentTimePayload(_Payload):
    scheduled_at: datetime
    timezone: str | None = Field(default=None, min_length=1, max_length=64)


# --- what an action is ------------------------------------------------------


@dataclass(frozen=True)
class SuggestionView:
    """The explicit diff section 86 asks for.

    ``current`` is read at the moment the screen is built, not stored, so a
    reminder somebody moved themselves yesterday shows today's real time rather
    than the one that was there when the suggestion was made.
    """

    #: What is being changed, in the user's own words: a medication name, an
    #: appointment title.
    subject: str
    #: What it says now. Null when the thing does not exist yet.
    current: str | None
    #: What the caregiver is proposing.
    proposed: str
    #: True when the target has gone, so the review screen can say so rather
    #: than offering Approve on something that cannot be applied.
    target_missing: bool = False


@dataclass(frozen=True)
class Action:
    """One proposable change: who may propose it, and what approval does."""

    name: str
    category: str
    #: The caregiver permission required both to propose and to have it applied.
    #: Re-checked at approval, which is what makes a suggestion from somebody
    #: whose symptom access was withdrawn last week unapprovable (section 24).
    permission: str
    target_type: str | None
    payload_model: type[_Payload]
    #: Whether a target id is required. ``add_appointment`` has none: the thing
    #: being proposed does not exist yet.
    needs_target: bool
    describe: Callable[[Session, Profile, CaregiverSuggestion], SuggestionView]
    apply: Callable[[Session, Profile, CaregiverSuggestion, datetime], uuid.UUID]


# --- medication actions -----------------------------------------------------


def _schedule_or_none(
    db: Session, profile: Profile, suggestion: CaregiverSuggestion
) -> Any:
    if suggestion.target_resource_id is None:
        return None
    try:
        return schedule_service.get_schedule(
            db, profile.id, suggestion.target_resource_id
        )
    except NotFoundError:
        return None


def _current_times(schedule: Any) -> str:
    times = [entry.time_of_day for entry in schedule.times]
    return wording.format_times(times) if times else "No reminder times set"


def _describe_change_times(
    db: Session, profile: Profile, suggestion: CaregiverSuggestion
) -> SuggestionView:
    schedule = _schedule_or_none(db, profile, suggestion)
    payload = ChangeReminderTimePayload.model_validate(suggestion.payload)
    proposed = wording.format_times([entry.to_time() for entry in payload.times])
    if schedule is None:
        return SuggestionView(
            subject="A medication reminder",
            current=None,
            proposed=proposed,
            target_missing=True,
        )
    return SuggestionView(
        subject=schedule.medication.name,
        current=_current_times(schedule),
        proposed=proposed,
    )


def _apply_change_times(
    db: Session, profile: Profile, suggestion: CaregiverSuggestion, now: datetime
) -> uuid.UUID:
    schedule = _schedule_or_none(db, profile, suggestion)
    if schedule is None:
        raise SuggestionTargetMissingError("That reminder is no longer there.")
    payload = ChangeReminderTimePayload.model_validate(suggestion.payload)
    schedule_service.update_schedule(
        db,
        schedule,
        now,
        times=[
            schedule_service.TimeInput(time_of_day=entry.to_time(), weekday=entry.weekday)
            for entry in payload.times
        ],
    )
    return schedule.id


def _describe_pause(
    db: Session, profile: Profile, suggestion: CaregiverSuggestion
) -> SuggestionView:
    schedule = _schedule_or_none(db, profile, suggestion)
    pausing = suggestion.action_type == "pause_medication_reminder"
    proposed = "Reminders paused" if pausing else "Reminders back on"
    if schedule is None:
        return SuggestionView(
            subject="A medication reminder",
            current=None,
            proposed=proposed,
            target_missing=True,
        )
    paused_now = schedule.paused_at is not None or not schedule.is_active
    return SuggestionView(
        subject=schedule.medication.name,
        current="Reminders paused" if paused_now else _current_times(schedule),
        proposed=proposed,
    )


def _apply_pause(
    db: Session, profile: Profile, suggestion: CaregiverSuggestion, now: datetime
) -> uuid.UUID:
    schedule = _schedule_or_none(db, profile, suggestion)
    if schedule is None:
        raise SuggestionTargetMissingError("That reminder is no longer there.")
    schedule_service.set_paused(
        db,
        schedule,
        paused=suggestion.action_type == "pause_medication_reminder",
        now=now,
    )
    return schedule.id


# --- appointment actions ----------------------------------------------------


def _appointment_or_none(
    db: Session, profile: Profile, suggestion: CaregiverSuggestion
) -> Any:
    if suggestion.target_resource_id is None:
        return None
    try:
        return appointment_service.get_appointment(
            db, profile.id, suggestion.target_resource_id
        )
    except NotFoundError:
        return None


def _describe_add_appointment(
    db: Session, profile: Profile, suggestion: CaregiverSuggestion
) -> SuggestionView:
    payload = AddAppointmentPayload.model_validate(suggestion.payload)
    return SuggestionView(
        subject=payload.title,
        current=None,
        proposed=wording.format_moment(payload.scheduled_at, payload.timezone),
    )


def _apply_add_appointment(
    db: Session, profile: Profile, suggestion: CaregiverSuggestion, now: datetime
) -> uuid.UUID:
    payload = AddAppointmentPayload.model_validate(suggestion.payload)
    payload.check()
    appointment = appointment_service.create_appointment(
        db,
        profile.id,
        appointment_service.AppointmentInput(
            title=payload.title,
            scheduled_at=payload.scheduled_at,
            timezone=payload.timezone,
            appointment_type=payload.appointment_type,
            location_name=payload.location_name,
        ),
    )
    return appointment.id


def _describe_change_appointment_time(
    db: Session, profile: Profile, suggestion: CaregiverSuggestion
) -> SuggestionView:
    appointment = _appointment_or_none(db, profile, suggestion)
    payload = ChangeAppointmentTimePayload.model_validate(suggestion.payload)
    zone = payload.timezone or (
        appointment.timezone if appointment is not None else "UTC"
    )
    proposed = wording.format_moment(payload.scheduled_at, zone)
    if appointment is None:
        return SuggestionView(
            subject="An appointment",
            current=None,
            proposed=proposed,
            target_missing=True,
        )
    return SuggestionView(
        subject=appointment.title,
        current=wording.format_moment(appointment.scheduled_at, appointment.timezone),
        proposed=proposed,
    )


def _apply_change_appointment_time(
    db: Session, profile: Profile, suggestion: CaregiverSuggestion, now: datetime
) -> uuid.UUID:
    appointment = _appointment_or_none(db, profile, suggestion)
    if appointment is None:
        raise SuggestionTargetMissingError("That appointment is no longer there.")
    payload = ChangeAppointmentTimePayload.model_validate(suggestion.payload)
    fields: dict[str, Any] = {"scheduled_at": payload.scheduled_at}
    if payload.timezone is not None:
        fields["timezone"] = payload.timezone
    appointment_service.update_appointment(db, appointment, fields)
    return appointment.id


# --- routine actions (PRD 12, sections 16, 17 and 43) -----------------------
#
# The three PRD 9 section 85 named and left out, because through PRD 0-11 there
# was nothing to add a routine to. Each one applies through
# ``services.productivity.routines``, which is the same module the owner's own
# routes call -- so every rule those functions enforce still applies, the runs
# are rebuilt the way they always are, and there is no second code path to
# drift.
#
# What a caregiver cannot propose is as important: there is no action for a
# task, an alarm or a personal reminder, because section 42 keeps those private
# to the primary user and the surest way to honour that is to have no action
# type that could carry the request.


class RoutineStepInput(_Payload):
    """One step of a proposed routine."""

    title: str = Field(min_length=1, max_length=TITLE_MAX_LENGTH)
    optional: bool = False


class AddRoutinePayload(_Payload):
    """A whole routine, proposed (section 16).

    The steps come with it rather than being added afterwards: a routine with
    no steps generates no runs, and a caregiver who proposed an empty one would
    be proposing something the person could approve and then find does nothing.

    ``source`` is not a field here. An approved suggestion is stored as
    ``caregiver_suggestion`` by the applier below, so section 43's
    attributability is the server's doing and not something a payload claims.
    """

    title: str = Field(min_length=1, max_length=TITLE_MAX_LENGTH)
    time_of_day: str = Field(pattern=TIME_PATTERN)
    timezone: str = Field(min_length=1, max_length=64)
    start_date: date
    schedule_type: str = Field(default="daily")
    description: str | None = Field(default=None, max_length=BODY_MAX_LENGTH)
    weekdays: list[int] | None = Field(default=None)
    steps: list[RoutineStepInput] = Field(min_length=1, max_length=MAX_ROUTINE_STEPS)

    def check(self) -> None:
        if self.schedule_type not in ROUTINE_SCHEDULE_TYPES:
            raise InvalidSuggestionError("That is not a repeat a routine has.")
        if self.schedule_type == "selected_days" and not self.weekdays:
            raise InvalidSuggestionError("Choose at least one day.")
        if self.weekdays and any(day < 0 or day > 6 for day in self.weekdays):
            raise InvalidSuggestionError("That is not a day of the week.")

    def to_time(self) -> time:
        hour, minute = self.time_of_day.split(":")
        return time(hour=int(hour), minute=int(minute))


class ChangeRoutineTimePayload(_Payload):
    """A new time, and optionally new days, for a routine that exists."""

    time_of_day: str = Field(pattern=TIME_PATTERN)
    weekdays: list[int] | None = Field(default=None)

    def check(self) -> None:
        if self.weekdays and any(day < 0 or day > 6 for day in self.weekdays):
            raise InvalidSuggestionError("That is not a day of the week.")

    def to_time(self) -> time:
        hour, minute = self.time_of_day.split(":")
        return time(hour=int(hour), minute=int(minute))


class PauseRoutinePayload(_Payload):
    """Nothing to say. Pausing is the whole proposal.

    Carries no reason, for the reason ``PauseReminderPayload`` carries none: a
    free-text field here would be a caregiver writing something into a record
    the primary user did not author.
    """


def _routine_or_none(
    db: Session, profile: Profile, suggestion: CaregiverSuggestion
) -> Any:
    if suggestion.target_resource_id is None:
        return None
    try:
        return routine_service.get_routine(db, profile.id, suggestion.target_resource_id)
    except NotFoundError:
        return None


def _routine_schedule_label(routine: Any) -> str:
    return productivity_wording.recurrence_sentence(
        recurrence=routine.schedule_type,
        time_of_day=routine.time_of_day,
        weekdays=routine.weekdays,
        start_date=routine.start_date,
    )


def _describe_add_routine(
    db: Session, profile: Profile, suggestion: CaregiverSuggestion
) -> SuggestionView:
    payload = AddRoutinePayload.model_validate(suggestion.payload)
    steps = ", ".join(step.title for step in payload.steps)
    proposed = productivity_wording.recurrence_sentence(
        recurrence=payload.schedule_type,
        time_of_day=payload.to_time(),
        weekdays=payload.weekdays,
        start_date=payload.start_date,
    )
    return SuggestionView(
        subject=payload.title,
        current=None,
        proposed=f"{proposed} \u00b7 {steps}",
    )


def _apply_add_routine(
    db: Session, profile: Profile, suggestion: CaregiverSuggestion, now: datetime
) -> uuid.UUID:
    payload = AddRoutinePayload.model_validate(suggestion.payload)
    payload.check()
    routine = routine_service.create_routine(
        db,
        profile.id,
        routine_service.RoutineInput(
            title=payload.title,
            time_of_day=payload.to_time(),
            start_date=payload.start_date,
            schedule_type=payload.schedule_type,
            timezone=payload.timezone,
            description=payload.description,
            weekdays=payload.weekdays,
            # Section 43: an approved caregiver suggestion stays attributable
            # for as long as the routine exists.
            source="caregiver_suggestion",
        ),
        [
            routine_service.StepInput(title=step.title, optional=step.optional)
            for step in payload.steps
        ],
        now,
    )
    return routine.id


def _describe_change_routine_time(
    db: Session, profile: Profile, suggestion: CaregiverSuggestion
) -> SuggestionView:
    routine = _routine_or_none(db, profile, suggestion)
    payload = ChangeRoutineTimePayload.model_validate(suggestion.payload)
    proposed = productivity_wording.recurrence_sentence(
        recurrence=(
            "selected_days"
            if payload.weekdays
            else (routine.schedule_type if routine is not None else "daily")
        ),
        time_of_day=payload.to_time(),
        weekdays=payload.weekdays or (routine.weekdays if routine is not None else None),
        start_date=routine.start_date if routine is not None else None,
    )
    if routine is None:
        return SuggestionView(
            subject="A routine",
            current=None,
            proposed=proposed,
            target_missing=True,
        )
    return SuggestionView(
        subject=routine.title,
        current=_routine_schedule_label(routine),
        proposed=proposed,
    )


def _apply_change_routine_time(
    db: Session, profile: Profile, suggestion: CaregiverSuggestion, now: datetime
) -> uuid.UUID:
    routine = _routine_or_none(db, profile, suggestion)
    if routine is None:
        raise SuggestionTargetMissingError("That routine is no longer there.")
    payload = ChangeRoutineTimePayload.model_validate(suggestion.payload)
    payload.check()
    fields: dict[str, Any] = {"time_of_day": payload.to_time()}
    if payload.weekdays:
        fields["schedule_type"] = "selected_days"
        fields["weekdays"] = payload.weekdays
    routine_service.update_routine(db, routine, fields, now)
    return routine.id


def _describe_pause_routine(
    db: Session, profile: Profile, suggestion: CaregiverSuggestion
) -> SuggestionView:
    routine = _routine_or_none(db, profile, suggestion)
    if routine is None:
        return SuggestionView(
            subject="A routine",
            current=None,
            proposed="Routine paused",
            target_missing=True,
        )
    return SuggestionView(
        subject=routine.title,
        current=(
            "Routine paused"
            if routine.status == "paused"
            else _routine_schedule_label(routine)
        ),
        proposed="Routine paused",
    )


def _apply_pause_routine(
    db: Session, profile: Profile, suggestion: CaregiverSuggestion, now: datetime
) -> uuid.UUID:
    routine = _routine_or_none(db, profile, suggestion)
    if routine is None:
        raise SuggestionTargetMissingError("That routine is no longer there.")
    PauseRoutinePayload.model_validate(suggestion.payload)
    routine_service.set_paused(db, routine, paused=True, now=now)
    return routine.id


# --- the registry -----------------------------------------------------------

ACTIONS: dict[str, Action] = {
    "change_medication_reminder_time": Action(
        name="change_medication_reminder_time",
        category="medications",
        permission="medications",
        target_type="medication_schedule",
        payload_model=ChangeReminderTimePayload,
        needs_target=True,
        describe=_describe_change_times,
        apply=_apply_change_times,
    ),
    "pause_medication_reminder": Action(
        name="pause_medication_reminder",
        category="medications",
        permission="medications",
        target_type="medication_schedule",
        payload_model=PauseReminderPayload,
        needs_target=True,
        describe=_describe_pause,
        apply=_apply_pause,
    ),
    "resume_medication_reminder": Action(
        name="resume_medication_reminder",
        category="medications",
        permission="medications",
        target_type="medication_schedule",
        payload_model=PauseReminderPayload,
        needs_target=True,
        describe=_describe_pause,
        apply=_apply_pause,
    ),
    "add_appointment": Action(
        name="add_appointment",
        category="appointments",
        permission="appointments",
        target_type="appointment",
        payload_model=AddAppointmentPayload,
        needs_target=False,
        describe=_describe_add_appointment,
        apply=_apply_add_appointment,
    ),
    "change_appointment_time": Action(
        name="change_appointment_time",
        category="appointments",
        permission="appointments",
        target_type="appointment",
        payload_model=ChangeAppointmentTimePayload,
        needs_target=True,
        describe=_describe_change_appointment_time,
        apply=_apply_change_appointment_time,
    ),
    "add_routine": Action(
        name="add_routine",
        category="routines",
        permission="routines",
        target_type="routine",
        payload_model=AddRoutinePayload,
        # Nothing to point at: the routine being proposed does not exist yet,
        # exactly as with ``add_appointment``.
        needs_target=False,
        describe=_describe_add_routine,
        apply=_apply_add_routine,
    ),
    "change_routine_time": Action(
        name="change_routine_time",
        category="routines",
        permission="routines",
        target_type="routine",
        payload_model=ChangeRoutineTimePayload,
        needs_target=True,
        describe=_describe_change_routine_time,
        apply=_apply_change_routine_time,
    ),
    "pause_routine": Action(
        name="pause_routine",
        category="routines",
        permission="routines",
        target_type="routine",
        payload_model=PauseRoutinePayload,
        needs_target=True,
        describe=_describe_pause_routine,
        apply=_apply_pause_routine,
    ),
}

# The registry and the database constraint are built from the same tuple, so a
# status quo where one allows something the other does not cannot arise.
assert set(ACTIONS) == set(CAREGIVER_SUGGESTION_ACTION_TYPES)


def describe(
    db: Session, profile: Profile, suggestion: CaregiverSuggestion
) -> SuggestionView:
    """The current-versus-proposed pair for one suggestion (section 86).

    A payload that no longer parses -- because a later version changed a model
    -- renders as a suggestion whose target is missing rather than raising.
    A review screen that 500s is worse than one that says a care request can no
    longer be applied.
    """
    action = ACTIONS[suggestion.action_type]
    try:
        return action.describe(db, profile, suggestion)
    except ValidationError:
        logger.warning("caregivers: stored payload no longer validates")
        return SuggestionView(
            subject=wording.ACTION_LABELS[suggestion.action_type],
            current=None,
            proposed="No longer available",
            target_missing=True,
        )


# --- creating ---------------------------------------------------------------


def _open_count(db: Session, profile_id: uuid.UUID) -> int:
    return len(
        db.execute(
            select(CaregiverSuggestion.id).where(
                CaregiverSuggestion.profile_id == profile_id,
                CaregiverSuggestion.status.in_(CAREGIVER_SUGGESTION_OPEN_STATUSES),
            )
        )
        .scalars()
        .all()
    )


def find_by_client_id(
    db: Session, relationship_id: uuid.UUID, client_id: str | None
) -> CaregiverSuggestion | None:
    """A suggestion this client already created, if any (section 74)."""
    if not client_id:
        return None
    return db.execute(
        select(CaregiverSuggestion).where(
            CaregiverSuggestion.relationship_id == relationship_id,
            CaregiverSuggestion.client_suggestion_id == client_id,
        )
    ).scalar_one_or_none()


def _validate_target(
    db: Session,
    profile: Profile,
    action: Action,
    target_id: uuid.UUID | None,
) -> None:
    """Refuses a target that is not this profile's, or is missing when required.

    A caregiver naming another profile's schedule id gets "not found" -- the
    lookup is scoped by ``profile.id``, so a guessed UUID resolves to nothing
    rather than to a stranger's medication (section 57).
    """
    if action.needs_target:
        if target_id is None:
            raise InvalidSuggestionError("This change needs something to change.")
        if action.target_type == "medication_schedule":
            try:
                schedule_service.get_schedule(db, profile.id, target_id)
            except NotFoundError as error:
                raise SuggestionTargetMissingError("Not found.") from error
        elif action.target_type == "appointment":
            try:
                appointment_service.get_appointment(db, profile.id, target_id)
            except NotFoundError as error:
                raise SuggestionTargetMissingError("Not found.") from error
        elif action.target_type == "routine":
            try:
                routine_service.get_routine(db, profile.id, target_id)
            except NotFoundError as error:
                raise SuggestionTargetMissingError("Not found.") from error
    elif target_id is not None:
        raise InvalidSuggestionError("This change does not take a target.")


def create(
    db: Session,
    scope: CareScope,
    *,
    action_type: str,
    # Defaults to empty because some actions carry nothing: pausing a reminder
    # *is* the whole proposal, and its payload model has no fields.
    payload: dict[str, Any] | None = None,
    target_resource_id: uuid.UUID | None = None,
    client_suggestion_id: str | None = None,
    now: datetime,
) -> CaregiverSuggestion:
    """A caregiver proposes a change (sections 20, 22 and 23).

    ``scope`` must be a caregiver's. The permission is checked here, and checked
    again at approval: a suggestion is not a capability somebody keeps after
    their access is withdrawn.
    """
    assert scope.relationship is not None, "a suggestion needs a relationship"
    action = ACTIONS.get(action_type)
    if action is None:
        # Unreachable through the API -- the schema's Literal rejects it first.
        # Kept so a new caller gets a refusal rather than a KeyError.
        raise InvalidSuggestionError("That is not a change Nura can propose.")

    scope.require(action.permission)

    existing = find_by_client_id(db, scope.relationship.id, client_suggestion_id)
    if existing is not None:
        return existing

    if _open_count(db, scope.profile.id) >= MAX_OPEN_SUGGESTIONS:
        raise TooManySuggestionsError("There are too many care requests waiting.")

    try:
        validated = action.payload_model.model_validate(payload or {})
    except ValidationError as error:
        raise InvalidSuggestionError(
            "That change was not described correctly."
        ) from error
    if isinstance(
        validated,
        (AddAppointmentPayload, AddRoutinePayload, ChangeRoutineTimePayload),
    ):
        validated.check()

    _validate_target(db, scope.profile, action, target_resource_id)

    suggestion = CaregiverSuggestion(
        profile_id=scope.profile.id,
        relationship_id=scope.relationship.id,
        category=action.category,
        action_type=action.name,
        target_resource_type=action.target_type,
        target_resource_id=target_resource_id,
        # Dumped from the validated model rather than stored as it arrived, so
        # what is written is what passed validation and nothing else.
        payload=validated.model_dump(mode="json"),
        status="pending",
        client_suggestion_id=client_suggestion_id,
    )
    db.add(suggestion)
    db.flush()
    audit.record(
        db,
        profile_id=scope.profile.id,
        actor_account_id=scope.relationship.caregiver_account_id,
        actor_kind="caregiver",
        event_type="suggestion_created",
        target_type="caregiver_suggestion",
        target_id=suggestion.id,
        now=now,
        meta=audit.suggestion_meta(action.name),
    )
    db.commit()
    db.refresh(suggestion)
    logger.info("caregiver.suggestion.created")
    return suggestion


# --- reading ----------------------------------------------------------------


def list_for_profile(
    db: Session,
    profile_id: uuid.UUID,
    *,
    relationship_id: uuid.UUID | None = None,
    open_only: bool = False,
) -> list[CaregiverSuggestion]:
    """Suggestions for this profile, newest first.

    ``relationship_id`` narrows it to one caregiver's own, which is what the
    caregiver's status list uses (section 88): a caregiver sees what *they*
    proposed and never what somebody else did (section 66).
    """
    query = (
        select(CaregiverSuggestion)
        .options(selectinload(CaregiverSuggestion.relationship_row))
        .where(CaregiverSuggestion.profile_id == profile_id)
        .order_by(CaregiverSuggestion.created_at.desc())
    )
    if relationship_id is not None:
        query = query.where(CaregiverSuggestion.relationship_id == relationship_id)
    if open_only:
        query = query.where(
            CaregiverSuggestion.status.in_(CAREGIVER_SUGGESTION_OPEN_STATUSES)
        )
    return list(db.execute(query).scalars().all())


def get(
    db: Session,
    profile_id: uuid.UUID,
    suggestion_id: uuid.UUID,
    *,
    relationship_id: uuid.UUID | None = None,
) -> CaregiverSuggestion:
    """One suggestion, scoped so a caregiver cannot read another's."""
    query = (
        select(CaregiverSuggestion)
        .options(selectinload(CaregiverSuggestion.relationship_row))
        .where(
            CaregiverSuggestion.id == suggestion_id,
            CaregiverSuggestion.profile_id == profile_id,
        )
    )
    if relationship_id is not None:
        query = query.where(CaregiverSuggestion.relationship_id == relationship_id)
    suggestion = db.execute(query).scalar_one_or_none()
    if suggestion is None:
        raise SuggestionNotFoundError("Not found.")
    return suggestion


def open_count(db: Session, profile_id: uuid.UUID) -> int:
    """How many care requests are waiting. For Today and the Care screen."""
    return _open_count(db, profile_id)


# --- reviewing --------------------------------------------------------------


def approve(
    db: Session,
    profile: Profile,
    suggestion: CaregiverSuggestion,
    reviewer: User,
    *,
    now: datetime,
) -> CaregiverSuggestion:
    """The primary user says yes, and the change happens (section 24).

    In order, and all six steps:

    1. the caregiver's permission is revalidated against the *current*
       relationship, so somebody revoked since proposing cannot have their
       suggestion applied;
    2. the target is re-found inside this profile;
    3. the payload is re-validated;
    4. the change is applied through the ordinary service, with every rule and
       every dose rebuild that implies;
    5. the suggestion is marked approved, with what it produced; and
    6. an audit row is written in the same transaction.

    Approving an already-approved suggestion returns it untouched (section 74).
    """
    if suggestion.status == "approved":
        return suggestion
    if suggestion.status not in CAREGIVER_SUGGESTION_OPEN_STATUSES:
        raise SuggestionNotPendingError("That care request has already been answered.")

    action = ACTIONS[suggestion.action_type]
    relationship = suggestion.relationship_row
    # Step 1. Not "was it allowed when they asked" -- "is it allowed now".
    if action.permission not in permissions.granted_keys(relationship):
        raise SuggestionNotPendingError("That caregiver no longer has access.")

    # Steps 2-4. ``apply`` re-reads the target, re-validates the payload and
    # calls the ordinary service, which commits.
    applied_id = action.apply(db, profile, suggestion, now)

    suggestion.status = "approved"
    suggestion.reviewed_at = now
    suggestion.reviewed_by_account_id = reviewer.id
    suggestion.applied_resource_id = applied_id
    audit.record(
        db,
        profile_id=profile.id,
        actor_account_id=reviewer.id,
        actor_kind="primary_user",
        event_type="suggestion_approved",
        target_type="caregiver_suggestion",
        target_id=suggestion.id,
        now=now,
        meta=audit.suggestion_meta(suggestion.action_type),
    )
    db.commit()
    db.refresh(suggestion)
    logger.info("caregiver.suggestion.approved")
    return suggestion


def decline(
    db: Session,
    suggestion: CaregiverSuggestion,
    reviewer: User,
    *,
    note: str | None = None,
    now: datetime,
) -> CaregiverSuggestion:
    """The primary user says no (section 25).

    The note is optional, kept, and **never returned to the caregiver**: section
    25 says a decline reason should not automatically be shared back, and
    section 88 that private reasons stay private unless the primary user chooses
    otherwise. There is no field in the caregiver-facing schema that could carry
    it, so sharing it is a deliberate future feature rather than a leak waiting
    for somebody to notice.
    """
    if suggestion.status not in CAREGIVER_SUGGESTION_OPEN_STATUSES:
        raise SuggestionNotPendingError("That care request has already been answered.")
    suggestion.status = "declined"
    suggestion.reviewed_at = now
    suggestion.reviewed_by_account_id = reviewer.id
    if note:
        suggestion.decline_note = note[:DECLINE_NOTE_MAX_LENGTH]
    audit.record(
        db,
        profile_id=suggestion.profile_id,
        actor_account_id=reviewer.id,
        actor_kind="primary_user",
        event_type="suggestion_declined",
        target_type="caregiver_suggestion",
        target_id=suggestion.id,
        now=now,
        meta=audit.suggestion_meta(suggestion.action_type),
    )
    db.commit()
    db.refresh(suggestion)
    logger.info("caregiver.suggestion.declined")
    return suggestion


def cancel(
    db: Session,
    suggestion: CaregiverSuggestion,
    scope: CareScope,
    *,
    now: datetime,
) -> CaregiverSuggestion:
    """A caregiver withdraws their own suggestion.

    Not in PRD 9's endpoint list, and present because ``cancelled`` is in its
    status vocabulary (section 22) and because a caregiver who proposed the
    wrong time should be able to take it back rather than making the primary
    user decline something nobody wants.
    """
    assert scope.relationship is not None
    if suggestion.relationship_id != scope.relationship.id:
        raise SuggestionNotFoundError("Not found.")
    if suggestion.status not in CAREGIVER_SUGGESTION_OPEN_STATUSES:
        raise SuggestionNotPendingError("That care request has already been answered.")
    suggestion.status = "cancelled"
    suggestion.reviewed_at = now
    audit.record(
        db,
        profile_id=suggestion.profile_id,
        actor_account_id=scope.relationship.caregiver_account_id,
        actor_kind="caregiver",
        event_type="suggestion_cancelled",
        target_type="caregiver_suggestion",
        target_id=suggestion.id,
        now=now,
        meta=audit.suggestion_meta(suggestion.action_type),
    )
    db.commit()
    db.refresh(suggestion)
    logger.info("caregiver.suggestion.cancelled")
    return suggestion
