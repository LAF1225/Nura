"""Today, check-in and dashboard request/response models (PRD 3, sections 15,
16, 20 and 49).

Models, never ORM rows: the API's shape is decided here rather than falling
out of whatever columns a table happens to have.
"""

import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.checkin import NOTE_MAX_LENGTH
from app.models.dashboard import CARD_KEY_MAX_LENGTH
from app.models.enums import WELLBEING_LEVELS
from app.schemas.appointment import TodayAppointmentsRead
from app.schemas.medication import TodayMedicationsRead
from app.schemas.productivity import (
    ReminderCountsRead,
    RoutineCountsRead,
    TaskCountsRead,
)
from app.schemas.symptom import TodaySymptomsRead

WellbeingLevel = Literal["good", "okay", "not_great"]
CheckInStatus = Literal["completed", "not_completed"]

# Guards the Literal above against drifting from the database CHECK constraint,
# which is generated from the same tuple.
assert set(WELLBEING_LEVELS) == set(WellbeingLevel.__args__)  # type: ignore[attr-defined]

Note = Annotated[str, Field(max_length=NOTE_MAX_LENGTH)]
CardKey = Annotated[str, Field(min_length=1, max_length=CARD_KEY_MAX_LENGTH)]


# --- daily check-in ---------------------------------------------------------


class DailyCheckInRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    profile_id: uuid.UUID
    #: The user's local calendar day, not a UTC date (PRD 3, section 39).
    checkin_date: date
    wellbeing_level: WellbeingLevel
    note: str | None
    created_at: datetime
    updated_at: datetime


class DailyCheckInUpdate(BaseModel):
    """The body of a check-in submission.

    Only ``wellbeing_level`` is required. Everything else exists so the server
    can place the answer correctly: which day it is where the user is, which
    person it is about, and when they actually chose it.
    """

    wellbeing_level: WellbeingLevel
    #: Optional, in the user's own words (PRD 3, section 10).
    note: Note | None = None
    #: The date on the client's own clock. Defaults to the server's UTC date,
    #: which is only ever right by accident, so the app always sends it.
    local_date: date | None = None
    #: Defaults to the person this account's Nura is for.
    profile_id: uuid.UUID | None = None
    #: When the user made this choice -- not when the request arrived. An
    #: offline submission may be hours old by the time it syncs, and this is
    #: what lets the server keep a newer answer (PRD 3, section 28).
    client_updated_at: datetime | None = None

    @field_validator("note")
    @classmethod
    def _tidy_note(cls, value: str | None) -> str | None:
        """Trims, and treats a blank note as no note.

        Without this, clearing the text field would store an empty string that
        renders as a note the user did not write.
        """
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class DailyCheckInSaved(BaseModel):
    """The stored check-in, plus whether this submission is what is stored.

    ``applied`` is False when the server already had a more recent edit. The
    body still carries the stored check-in, so a client reconciling a queued
    submission can simply adopt it (PRD 3, section 28).
    """

    checkin: DailyCheckInRead
    applied: bool


class DailyCheckInTodayRead(BaseModel):
    """Today's check-in for the resolved profile, or nothing yet."""

    local_date: date
    profile_id: uuid.UUID
    checkin: DailyCheckInRead | None


class RecentCheckInsRead(BaseModel):
    """A plain count and the rows behind it (PRD 3, section 12).

    No averages, no streaks, no trend: a number of completed days, and the
    entries themselves so a client can show them without a second request.
    """

    profile_id: uuid.UUID
    from_date: date
    to_date: date
    window_days: int
    completed_count: int
    checkins: list[DailyCheckInRead]


# --- dashboard cards --------------------------------------------------------


class DashboardCardRead(BaseModel):
    key: str
    title: str
    #: False while the feature behind the card does not exist. Clients must not
    #: offer or render these (PRD 3, sections 18 and 59).
    available: bool
    visible: bool
    position: int


class DashboardPreferencesRead(BaseModel):
    profile_id: uuid.UUID | None
    cards: list[DashboardCardRead]


class DashboardCardUpdate(BaseModel):
    card_key: CardKey
    visible: bool


class DashboardPreferencesUpdate(BaseModel):
    """The whole layout, in display order.

    Position comes from the order of this list rather than a number the client
    has to keep consistent, so two cards can never claim the same slot.
    """

    cards: list[DashboardCardUpdate]
    profile_id: uuid.UUID | None = None


# --- today ------------------------------------------------------------------


class TodayProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    #: What the greeting uses (PRD 3, section 8).
    preferred_name: str


class TodayDeviceRead(BaseModel):
    device_id: uuid.UUID
    display_name: str
    #: Derived by the backend from heartbeats, never by the app.
    connection_status: Literal["unknown", "online", "offline"]
    last_seen_at: datetime | None
    setup_completed: bool


class TodayCheckInRead(BaseModel):
    status: CheckInStatus
    checkin: DailyCheckInRead | None
    recent_completed_count: int
    recent_window_days: int


class TodayDailyLifeRead(BaseModel):
    """Tasks, reminders, routines and alarms on Today (PRD 12, sections 19, 58).

    Counts and one sentence. The rows themselves arrive through ``important``,
    in the order PRD 12 section 18 sets -- which is why there are no lists
    here for a client to re-sort.
    """

    tasks: TaskCountsRead
    reminders: ReminderCountsRead
    routines: RoutineCountsRead
    next_alarm_at: datetime | None
    alarm_count: int
    #: "3 tasks, 1 routine and 2 reminders today."
    summary_label: str
    #: False for anybody who has never made one of these, and the card is then
    #: not drawn at all (PRD 12, section 19).
    has_anything: bool


class TodayItemRead(BaseModel):
    """An Important Today item.

    The shape was fixed in PRD 3 so later modules could fill the section
    without the client changing how it renders. PRD 5 is the first to do it:
    medication doses that are overdue, due, or next up. Appointments and
    follow-ups will arrive the same way (PRD 3, sections 21 and 60).
    """

    id: str
    type: str
    title: str
    subtitle: str | None = None
    due_at: datetime | None = None
    priority: Literal["normal", "important"] = "normal"
    #: A route in the app, e.g. ``/devices/{id}``.
    action_route: str | None = None


class TodaySummaryRead(BaseModel):
    """Everything Today needs in one response (PRD 3, section 16)."""

    local_date: date
    #: Null only for an account that has not created a profile yet.
    profile: TodayProfileRead | None
    daily_checkin: TodayCheckInRead
    #: Null when no robot is linked. That is a normal state, not an error
    #: (PRD 3, sections 23 and 54).
    device: TodayDeviceRead | None
    cards: list[DashboardCardRead]
    #: Null only for an account with no profile yet.
    medications: TodayMedicationsRead | None
    #: Null for the same reason. ``has_episodes`` is False for anybody who
    #: has never logged a symptom, and the card is then not drawn at all
    #: (PRD 6, section 39).
    symptoms: TodaySymptomsRead | None
    #: The next appointment and two counts (PRD 7, section 9). Null only for an
    #: account with no profile yet. Unlike the two above, an empty one does not
    #: hide the card -- PRD 7 section 9 gives "No upcoming appointments" its own
    #: wording.
    appointments: TodayAppointmentsRead | None
    #: Null only for an account with no profile yet. ``has_anything`` is False
    #: for anybody who has never made a task, a reminder or a routine
    #: (PRD 12, section 19).
    daily_life: TodayDailyLifeRead | None
    important: list[TodayItemRead]
