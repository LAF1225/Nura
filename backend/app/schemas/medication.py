"""Medication scheduling request/response models (PRD 5, sections 8, 21, 51).

Models, never ORM rows, for the same reason as everywhere else: the API's
shape is decided here rather than falling out of whatever columns a table
happens to have.

Two things a reader should check for and find absent:

**No client ever sets ``source``.** How an action arrived is the server's own
observation -- through a user's token, or through a device's -- so a request
cannot claim to be a robot's voice confirmation (PRD 5, sections 17 and 46).

**No client ever sets a dose's status directly.** A dose moves by *doing*
something to it: Taken, Snooze, Skip. There is no ``PATCH /doses/{id}`` with
``status`` in the body, which is what keeps every transition, every supply
decrement and every idempotency rule in one service (PRD 5, section 70).
"""

import uuid
from datetime import date, datetime, time
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from app.models.enums import (
    DOSE_SOURCES,
    DOSE_STATUSES,
    DOSE_WINDOWS,
    SCHEDULE_TYPES,
    SKIP_REASON_CODES,
)
from app.models.medication import SKIP_REASON_TEXT_MAX_LENGTH, TIMEZONE_MAX_LENGTH
from app.services.medications.doses import MAX_SNOOZES, SNOOZE_OPTIONS_MINUTES

ScheduleType = Literal["daily", "specific_days"]
DoseStatus = Literal["scheduled", "snoozed", "taken", "skipped", "missed", "cancelled"]
DoseSource = Literal["app", "robot_voice", "caregiver", "system"]
DoseWindow = Literal["upcoming", "due", "overdue", "completed"]
SkipReasonCode = Literal[
    "none", "feeling_unwell", "ran_out", "clinician_advised", "too_late", "other"
]

# Guard every Literal against drifting from the tuple the database CHECK
# constraints are generated from. A mismatch is a startup failure rather than
# a request that is accepted by the API and rejected by Postgres.
assert set(SCHEDULE_TYPES) == set(ScheduleType.__args__)  # type: ignore[attr-defined]
assert set(DOSE_STATUSES) == set(DoseStatus.__args__)  # type: ignore[attr-defined]
assert set(DOSE_SOURCES) == set(DoseSource.__args__)  # type: ignore[attr-defined]
assert set(DOSE_WINDOWS) == set(DoseWindow.__args__)  # type: ignore[attr-defined]
assert set(SKIP_REASON_CODES) == set(SkipReasonCode.__args__)  # type: ignore[attr-defined]

Timezone = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=1, max_length=TIMEZONE_MAX_LENGTH
    ),
]
#: 0 is Monday, matching ``date.weekday()``.
Weekday = Annotated[int, Field(ge=0, le=6)]
DoseCount = Annotated[int, Field(ge=0, le=100_000)]


# --- schedules --------------------------------------------------------------


class ScheduleTimeBase(BaseModel):
    #: A wall-clock time in the schedule's zone. Seconds are accepted and
    #: ignored by everything downstream; nobody schedules a tablet for 08:00:30.
    time_of_day: time
    #: Null on an every-day schedule, required on a specific-days one.
    weekday: Weekday | None = None


class ScheduleTimeRead(ScheduleTimeBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID


class MedicationScheduleRead(BaseModel):
    """A schedule, with just enough of its medication to render a row.

    The name and dose are included because every screen that lists schedules
    shows them, and a second request per row to fetch them would be the
    clearest possible example of what PRD 3 section 16 warns against.
    """

    id: uuid.UUID
    profile_id: uuid.UUID
    medication_id: uuid.UUID
    medication_name: str
    medication_dose: str | None
    schedule_type: ScheduleType
    timezone: str
    start_date: date
    end_date: date | None
    #: False while paused. Reminders stop; nothing recorded is affected.
    is_active: bool
    paused_at: datetime | None
    times: list[ScheduleTimeRead]
    created_at: datetime
    updated_at: datetime


class MedicationScheduleCreate(BaseModel):
    medication_id: uuid.UUID
    schedule_type: ScheduleType = "daily"
    #: An IANA name such as ``Europe/London``. Required, and deliberately
    #: without a default: a schedule that quietly fell back to UTC would
    #: remind somebody in London at the wrong time for half the year
    #: (PRD 5, section 12).
    timezone: Timezone
    start_date: date
    end_date: date | None = None
    times: list[ScheduleTimeBase]


class MedicationScheduleUpdate(BaseModel):
    """A PATCH. Everything omitted is left exactly as it was.

    ``times`` is all-or-nothing: send the whole list or none of it. Merging
    individual time rows would add a way for the list on screen and the list
    stored to disagree, for no benefit.
    """

    schedule_type: ScheduleType | None = None
    timezone: Timezone | None = None
    start_date: date | None = None
    end_date: date | None = None
    times: list[ScheduleTimeBase] | None = None


class MedicationSchedulePause(BaseModel):
    paused: bool


# --- doses ------------------------------------------------------------------


class MedicationDoseRead(BaseModel):
    """One scheduled moment, and what happened at it."""

    id: uuid.UUID
    profile_id: uuid.UUID
    medication_id: uuid.UUID
    medication_name: str
    medication_dose: str | None
    #: Null once the schedule behind it was deleted. The dose still stands.
    schedule_id: uuid.UUID | None
    scheduled_for: datetime
    #: The user's own calendar day, in the schedule's zone.
    local_date: date
    status: DoseStatus
    #: Derived on every read from the clock, never stored (PRD 5, section 54).
    window: DoseWindow
    action_at: datetime | None
    source: DoseSource | None
    skip_reason_code: SkipReasonCode | None
    skip_reason_text: str | None
    snoozed_until: datetime | None
    snooze_count: int
    #: Taken after the grace period. A fact about a time, not a judgement --
    #: no copy anywhere scolds about it (PRD 5, sections 24 and 25).
    late: bool
    #: False once the snooze limit is reached. Taken and Skip never stop being
    #: available (PRD 5, section 18).
    can_snooze: bool


class DoseActionRead(BaseModel):
    """The stored dose after an action, plus what the action actually did.

    ``applied`` is False when the dose was already in the state asked for, or
    when a robot's confirmation arrived after the person had recorded
    something themselves. The dose is returned either way, so a client
    reconciling a queued action adopts the server's answer instead of retrying
    (PRD 5, sections 48, 49 and 63).
    """

    dose: MedicationDoseRead
    applied: bool
    #: Null when this medication is not being tracked.
    supply_remaining: int | None = None
    low_supply: bool = False


class DoseTakenAction(BaseModel):
    #: When the user actually pressed Taken, which is not when the request
    #: arrived: an offline action may be hours old by the time it syncs
    #: (PRD 5, section 62).
    action_at: datetime | None = None


class DoseSkipAction(BaseModel):
    #: Stored exactly as chosen and never interpreted (PRD 5, section 19).
    reason_code: SkipReasonCode | None = None
    reason_text: (
        Annotated[
            str,
            StringConstraints(
                strip_whitespace=True, max_length=SKIP_REASON_TEXT_MAX_LENGTH
            ),
        ]
        | None
    ) = None
    action_at: datetime | None = None

    @field_validator("reason_text")
    @classmethod
    def _blank_is_none(cls, value: str | None) -> str | None:
        """A cleared text box is no reason, not an empty string."""
        if value is None:
            return None
        return value.strip() or None


class DoseSnoozeAction(BaseModel):
    minutes: Literal[10, 30, 60] = 10


assert set(SNOOZE_OPTIONS_MINUTES) == set(
    DoseSnoozeAction.model_fields["minutes"].annotation.__args__  # type: ignore[union-attr]
)


class SnoozeOptionsRead(BaseModel):
    """What the app should offer, so the durations live in one place."""

    minutes: list[int] = list(SNOOZE_OPTIONS_MINUTES)
    max_snoozes: int = MAX_SNOOZES


# --- adherence --------------------------------------------------------------


class AdherenceRead(BaseModel):
    """taken / (taken + skipped + missed), with the parts shown.

    The counts are returned alongside the percentage so the app can state the
    denominator rather than presenting a bare number that looks like a grade
    (PRD 5, section 27).
    """

    profile_id: uuid.UUID
    from_date: date
    to_date: date
    taken: int
    skipped: int
    missed: int
    total: int
    #: Null when nothing was due in the window. "0%" for a week with no doses
    #: would say something about the person that the data does not.
    percent: int | None


# --- supply -----------------------------------------------------------------


class MedicationSupplyRead(BaseModel):
    profile_id: uuid.UUID
    medication_id: uuid.UUID
    medication_name: str
    tracking_enabled: bool
    remaining_doses: int | None
    refill_threshold_doses: int | None
    last_refill_date: date | None
    #: At or below the user's own threshold. Never a figure Nura estimated.
    low: bool


class MedicationSupplyUpdate(BaseModel):
    """A PATCH. Omitting a field leaves it; sending null clears it."""

    tracking_enabled: bool | None = None
    remaining_doses: DoseCount | None = None
    refill_threshold_doses: DoseCount | None = None


class MedicationRefillCreate(BaseModel):
    """A new supply has been picked up, and this is how many there now are."""

    remaining_doses: DoseCount
    #: Defaults to the server's date. The app sends the user's local day.
    refilled_on: date | None = None


# --- Today ------------------------------------------------------------------


class TodayNextDoseRead(BaseModel):
    dose_id: uuid.UUID
    medication_id: uuid.UUID
    medication_name: str
    medication_dose: str | None
    scheduled_for: datetime
    status: DoseStatus
    window: DoseWindow
    can_snooze: bool


class TodayLowSupplyRead(BaseModel):
    medication_id: uuid.UUID
    medication_name: str
    remaining_doses: int


class TodayMedicationsRead(BaseModel):
    """The medication block of ``/api/v1/today`` (PRD 5, section 53).

    Kept minimal: the one dose a person is most likely to act on, three
    counts, and anything running low. The Care tab is where the full picture
    lives.
    """

    #: Null when nothing is waiting -- including for someone with no schedules
    #: at all, which is a normal state and not an error.
    next_due: TodayNextDoseRead | None
    due_today_count: int
    overdue_count: int
    remaining_today_count: int
    low_supply: list[TodayLowSupplyRead]
    #: False when this profile has no schedules, so Today can leave the card
    #: out rather than render an empty one.
    has_schedules: bool
