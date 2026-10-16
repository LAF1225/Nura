"""Appointment, question and report request/response models (PRD 7, ss48-52).

Models, never ORM rows, for the same reason as everywhere else: the API's shape
is decided here rather than falling out of whatever columns a table happens to
have.

Four things a reader should check for and find:

**No client sets a status timestamp.** An appointment is cancelled or completed
by *doing* something to it -- ``POST .../cancel``, ``POST .../complete`` -- so
``cancelled_at`` and ``completed_at`` can never disagree with ``status``, and
every transition lives in one service (PRD 7, sections 7 and 38).

**No client sets ``preparation_status``.** It is worked out by the server from
what exists, so it cannot claim a report that is not there (section 6).

**No response carries a storage key or a URL for a report.** A PDF is fetched
through an authenticated route, exactly as a symptom photo is
(sections 35 and 52).

**Display strings for dates come from the server.** ``when_label`` and its
friends are rendered here because an appointment has to be shown in *its own*
time zone (section 42), and the time zone database lives on the server. It also
means one implementation of "Tomorrow at 3:30 PM" rather than one per platform.
"""

import uuid
from datetime import date, datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.models.appointment import (
    ANSWER_NOTE_MAX_LENGTH,
    APPOINTMENT_TITLE_MAX_LENGTH,
    PHONE_MAX_LENGTH,
    QUESTION_MAX_LENGTH,
)
from app.models.enums import (
    APPOINTMENT_PREPARATION_STATUSES,
    APPOINTMENT_STATUSES,
    APPOINTMENT_TYPES,
    REPORT_PERIOD_PRESETS,
    REPORT_SECTIONS,
    REPORT_STATUSES,
    SYMPTOM_CHANGE_STATES,
    WELLBEING_LEVELS,
)
from app.models.health import NAME_MAX_LENGTH, NOTES_MAX_LENGTH, SHORT_TEXT_MAX_LENGTH
from app.models.medication import TIMEZONE_MAX_LENGTH
from app.models.symptom import CLIENT_ID_MAX_LENGTH

AppointmentType = Literal[
    "primary_care",
    "specialist",
    "therapy",
    "physiotherapy",
    "dentist",
    "lab",
    "imaging",
    "other",
]
AppointmentStatus = Literal["scheduled", "completed", "cancelled", "missed"]
PreparationStatus = Literal["not_started", "in_progress", "complete"]
ReportStatus = Literal["pending", "ready", "failed"]
ReportPeriodPreset = Literal["since_last_visit", "7_days", "30_days", "90_days", "custom"]
ChangeState = Literal["improving", "same", "worsening", "unsure"]
WellbeingLevel = Literal["good", "okay", "not_great"]

# Guard every Literal against drifting from the tuple the database CHECK
# constraints are generated from. A mismatch is a startup failure rather than a
# request the API accepts and Postgres rejects.
assert set(APPOINTMENT_TYPES) == set(AppointmentType.__args__)  # type: ignore[attr-defined]
assert set(APPOINTMENT_STATUSES) == set(AppointmentStatus.__args__)  # type: ignore[attr-defined]
assert set(APPOINTMENT_PREPARATION_STATUSES) == set(PreparationStatus.__args__)  # type: ignore[attr-defined]
assert set(REPORT_STATUSES) == set(ReportStatus.__args__)  # type: ignore[attr-defined]
assert set(REPORT_PERIOD_PRESETS) == set(ReportPeriodPreset.__args__)  # type: ignore[attr-defined]
assert set(SYMPTOM_CHANGE_STATES) == set(ChangeState.__args__)  # type: ignore[attr-defined]
assert set(WELLBEING_LEVELS) == set(WellbeingLevel.__args__)  # type: ignore[attr-defined]

Title = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=1, max_length=APPOINTMENT_TITLE_MAX_LENGTH
    ),
]
ShortText = Annotated[
    str, StringConstraints(strip_whitespace=True, max_length=SHORT_TEXT_MAX_LENGTH)
]
Name = Annotated[
    str, StringConstraints(strip_whitespace=True, max_length=NAME_MAX_LENGTH)
]
Phone = Annotated[
    str, StringConstraints(strip_whitespace=True, max_length=PHONE_MAX_LENGTH)
]
LongText = Annotated[
    str, StringConstraints(strip_whitespace=True, max_length=NOTES_MAX_LENGTH)
]
Timezone = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=1, max_length=TIMEZONE_MAX_LENGTH
    ),
]
QuestionText = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=1, max_length=QUESTION_MAX_LENGTH
    ),
]
AnswerNote = Annotated[
    str, StringConstraints(strip_whitespace=True, max_length=ANSWER_NOTE_MAX_LENGTH)
]
ClientId = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=1, max_length=CLIENT_ID_MAX_LENGTH
    ),
]


# --- appointments -----------------------------------------------------------


class ClinicianBriefRead(BaseModel):
    """Just enough of a clinician to render a row.

    Included because every screen that shows an appointment shows who it is
    with, and a second request per row would be the clearest possible example of
    what PRD 3 section 16 warns against.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    specialty: str | None = None


class AppointmentRead(BaseModel):
    """One appointment, with the labels a screen needs already rendered."""

    id: uuid.UUID
    profile_id: uuid.UUID
    title: str
    appointment_type: AppointmentType
    status: AppointmentStatus
    preparation_status: PreparationStatus
    scheduled_at: datetime
    timezone: str
    #: The appointment's date *in its own zone* (PRD 7, section 42).
    local_date: date
    #: "2 October 2026", "3:30 PM", "Tomorrow at 3:30 PM".
    day_label: str
    time_label: str
    when_label: str
    #: "Today", "Tomorrow", "Yesterday", or null for anything further away.
    relative_day: str | None
    clinician: ClinicianBriefRead | None
    location_name: str | None
    address: str | None
    phone: str | None
    notes: str | None
    visit_notes: str | None
    follow_up_date: date | None
    reminders_enabled: bool
    cancelled_at: datetime | None
    completed_at: datetime | None
    question_count: int
    report_count: int
    created_at: datetime
    updated_at: datetime


class AppointmentDetailRead(AppointmentRead):
    """An appointment with its questions and its report versions."""

    questions: list["AppointmentQuestionRead"] = Field(default_factory=list)
    #: Metadata only. A version's frozen content is fetched on its own, because
    #: a detail screen listing five snapshots would carry five whole reports.
    reports: list["ReportRead"] = Field(default_factory=list)


class AppointmentSaved(BaseModel):
    """A create, and whether this request is what created it.

    ``created`` is False for a replay of a ``client_appointment_id`` the server
    already has, which is what makes an offline draft safe to retry
    (PRD 7, section 53).
    """

    appointment: AppointmentDetailRead
    created: bool


class AppointmentCreate(BaseModel):
    """Everything a client may say when adding an appointment (s8).

    Only the title, the moment and the zone are required. Every other field is
    optional because PRD 7 section 8 says to keep them optional: somebody noting
    down a date should not be stopped by a form.
    """

    title: Title
    scheduled_at: datetime
    #: An IANA name such as ``Europe/London``. Deliberately without a default:
    #: an appointment that quietly fell back to UTC would show the wrong time
    #: for most of the world (PRD 7, section 42).
    timezone: Timezone
    appointment_type: AppointmentType = "other"
    clinician_id: uuid.UUID | None = None
    location_name: Name | None = None
    address: ShortText | None = None
    phone: Phone | None = None
    notes: LongText | None = None
    reminders_enabled: bool = True
    #: The client's own id, so a retry cannot create the appointment twice.
    client_appointment_id: ClientId | None = None


class AppointmentUpdate(BaseModel):
    """A PATCH. Everything omitted is left exactly as it was.

    There is no ``status`` here: an appointment is cancelled or completed
    through its own route, so the status and its timestamp can never disagree.
    """

    title: Title | None = None
    scheduled_at: datetime | None = None
    timezone: Timezone | None = None
    appointment_type: AppointmentType | None = None
    clinician_id: uuid.UUID | None = None
    location_name: Name | None = None
    address: ShortText | None = None
    phone: Phone | None = None
    notes: LongText | None = None
    visit_notes: LongText | None = None
    follow_up_date: date | None = None
    reminders_enabled: bool | None = None


class AppointmentComplete(BaseModel):
    """Marks an appointment attended, with the optional notes from s38."""

    visit_notes: LongText | None = None
    follow_up_date: date | None = None


# --- questions --------------------------------------------------------------


class AppointmentQuestionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    appointment_id: uuid.UUID
    text: str
    position: int
    is_answered: bool
    answer_note: str | None
    created_at: datetime
    updated_at: datetime


class AppointmentQuestionCreate(BaseModel):
    """One question, in the user's words (PRD 7, section 23).

    Nothing normalises ``text``. It is read out in a consulting room by the
    person who wrote it.
    """

    text: QuestionText
    client_question_id: ClientId | None = None


class AppointmentQuestionUpdate(BaseModel):
    text: QuestionText | None = None
    is_answered: bool | None = None
    answer_note: AnswerNote | None = None


class AppointmentQuestionSaved(BaseModel):
    question: AppointmentQuestionRead
    #: False for a replay of a known client id (PRD 7, section 53).
    created: bool


class AppointmentQuestionReorder(BaseModel):
    """The list as the client is displaying it (PRD 7, section 23)."""

    question_ids: list[uuid.UUID]


# --- preparation ------------------------------------------------------------


class ReportPeriodRead(BaseModel):
    """The period, and the story of how it was chosen (PRD 7, section 14)."""

    start: date
    end: date
    label: str
    preset: ReportPeriodPreset
    #: What the client asked for, which is not always what was applied.
    requested_preset: ReportPeriodPreset
    #: Why the request could not be honoured, in one sentence, or null.
    note: str | None = None
    #: "Since your appointment on 1 September 2026", when that is the period.
    since_label: str | None = None
    days: int


class SymptomNoteRead(BaseModel):
    """One thing the person wrote, offered for inclusion (PRD 7, section 16)."""

    entry_id: uuid.UUID
    recorded_at: datetime
    text: str


class SymptomReviewRead(BaseModel):
    """One symptom over the period, counted (PRD 7, sections 15 and 16).

    Deliberately carries no "recommended" or "significant" flag. Which symptom
    matters is the user's call, and a flag here would be Nura making it
    (section 15).
    """

    episode_id: uuid.UUID
    name: str
    body_site: str | None
    status: str
    is_ongoing: bool
    entry_count: int
    first_noticed_label: str | None
    latest_severity: int | None
    severity_min: int | None
    severity_max: int | None
    latest_change_state: ChangeState | None
    associated_symptoms: list[str] = Field(default_factory=list)
    exacerbating_factors: list[str] = Field(default_factory=list)
    relieving_factors: list[str] = Field(default_factory=list)
    #: Carried through so a summary cannot read as more definite than the person
    #: was (PRD 7, section 47).
    negated_items: list[str] = Field(default_factory=list)
    uncertain_items: list[str] = Field(default_factory=list)
    context_dependent_items: list[str] = Field(default_factory=list)
    notes: list[SymptomNoteRead] = Field(default_factory=list)
    #: Counted so the app can say photos exist. They are never in the report
    #: (PRD 7, section 28).
    photo_count: int = 0


class MedicationReviewRead(BaseModel):
    medication_id: uuid.UUID
    name: str
    display_name: str
    dose: str | None
    dose_unit: str | None
    #: "Twice daily", from the reminder schedule where there is one.
    frequency: str | None
    reason: str | None
    is_active: bool


class SkipNoteRead(BaseModel):
    dose_id: uuid.UUID
    local_date: date
    medication_name: str
    reason_code: str | None
    #: The user's own words. Only ever included in a report if they ask
    #: (PRD 7, section 19).
    reason_text: str | None


class AdherenceReviewRead(BaseModel):
    from_date: date
    to_date: date
    taken: int
    skipped: int
    missed: int
    total: int
    #: Never labelled adequate or inadequate (PRD 7, section 18).
    percent: int | None
    skip_notes: list[SkipNoteRead] = Field(default_factory=list)


class CheckInNoteRead(BaseModel):
    checkin_date: date
    wellbeing_level: WellbeingLevel
    note: str


class CheckInReviewRead(BaseModel):
    good: int
    okay: int
    not_great: int
    total: int
    days_in_period: int
    notes: list[CheckInNoteRead] = Field(default_factory=list)


class ConditionItemRead(BaseModel):
    condition_id: uuid.UUID
    name: str
    status: str
    diagnosed_label: str | None


class AllergyItemRead(BaseModel):
    allergy_id: uuid.UUID
    allergen: str
    reaction: str | None
    severity: str


class ProcedureItemRead(BaseModel):
    procedure_id: uuid.UUID
    name: str
    performed_label: str | None


class MedicalNoteItemRead(BaseModel):
    note_id: uuid.UUID
    title: str
    body: str
    category: str


class BaselineReviewRead(BaseModel):
    conditions: list[ConditionItemRead] = Field(default_factory=list)
    allergies: list[AllergyItemRead] = Field(default_factory=list)
    procedures: list[ProcedureItemRead] = Field(default_factory=list)
    blood_type: str | None = None


class QuestionSuggestionRead(BaseModel):
    """A deterministic prompt the user may accept (PRD 7, section 24)."""

    key: str
    prompt: str
    question_text: str
    reason: str


class PreparationRead(BaseModel):
    """Everything the preparation flow reads, in one response (s13, s49).

    No diagnostic interpretation anywhere in it, and nothing ranked.
    """

    appointment: AppointmentRead
    period: ReportPeriodRead
    symptoms: list[SymptomReviewRead] = Field(default_factory=list)
    medications: list[MedicationReviewRead] = Field(default_factory=list)
    adherence: AdherenceReviewRead | None = None
    daily_checkins: CheckInReviewRead | None = None
    baseline: BaselineReviewRead | None = None
    medical_notes: list[MedicalNoteItemRead] = Field(default_factory=list)
    questions: list[AppointmentQuestionRead] = Field(default_factory=list)
    suggestions: list[QuestionSuggestionRead] = Field(default_factory=list)
    #: False for an appointment with nothing recorded to review. A real state,
    #: not an error (PRD 7, section 46).
    has_health_data: bool = False
    #: The default selection for the report screen: every section on, every
    #: symptom in the review ticked. The user changes it from there
    #: (PRD 7, section 25).
    default_selection: "ReportSelectionRead"


# --- reports ----------------------------------------------------------------


class ReportSelectionInput(BaseModel):
    """What the user chose to include (PRD 7, sections 25 and 50).

    Symptoms are chosen one by one rather than by a single switch, because
    PRD 7 section 15 forbids Nura deciding which symptom matters more.
    """

    include: dict[str, bool] = Field(default_factory=dict)
    symptom_episode_ids: list[uuid.UUID] = Field(default_factory=list)
    symptom_note_entry_ids: list[uuid.UUID] = Field(default_factory=list)
    #: Null means "the active ones", which is what the review screen shows. An
    #: empty list means the user unticked them all, and is honoured.
    medication_ids: list[uuid.UUID] | None = None
    checkin_note_dates: list[date] = Field(default_factory=list)
    medical_note_ids: list[uuid.UUID] = Field(default_factory=list)
    focus: ShortText | None = None
    include_appendix: bool = False
    #: Free-text skip reasons, off unless asked for (PRD 7, section 19).
    include_skip_reason_notes: bool = False

    @model_validator(mode="after")
    def _check_include_keys(self) -> "ReportSelectionInput":
        unknown = sorted(set(self.include) - set(REPORT_SECTIONS))
        if unknown:
            raise ValueError(f"Unknown report sections: {', '.join(unknown)}")
        return self


class ReportSelectionRead(ReportSelectionInput):
    """The same shape, returned so the app can restore the user's last answers."""


class ReportGenerate(BaseModel):
    """A request to generate one version (PRD 7, sections 31 and 50)."""

    period_preset: ReportPeriodPreset = "since_last_visit"
    #: Required for ``custom``, ignored otherwise.
    period_start: date | None = None
    period_end: date | None = None
    selection: ReportSelectionInput = Field(default_factory=ReportSelectionInput)
    #: The client's own id, so a double tap makes one version rather than two.
    client_report_id: ClientId | None = None


class ReportRead(BaseModel):
    """One version's metadata. Never a URL and never a storage key (s52)."""

    id: uuid.UUID
    appointment_id: uuid.UUID
    version: int
    status: ReportStatus
    period_start: date
    period_end: date
    period_preset: ReportPeriodPreset
    period_label: str
    include_appendix: bool
    generated_at: datetime
    #: "Report v2 · Generated 2 Oct 2026, 9:15 AM" is built from these two.
    generated_label: str
    byte_size: int | None
    page_count: int | None
    #: "Nura_Health_Summary_2026-10-02.pdf" (PRD 7, section 33).
    file_name: str
    selection: ReportSelectionRead


class ReportDetailRead(ReportRead):
    """A version with its frozen content, for the in-app preview (s32).

    The preview renders this snapshot -- the same one the PDF is made from -- so
    what somebody approves on screen and what they export cannot disagree.
    """

    snapshot: dict[str, Any]


class ReportSaved(BaseModel):
    report: ReportDetailRead
    #: False for a replay of a known ``client_report_id``.
    created: bool


# --- Today ------------------------------------------------------------------


class TodayAppointmentRead(BaseModel):
    """The next appointment, as the Today card shows it (PRD 7, section 9)."""

    appointment_id: uuid.UUID
    title: str
    appointment_type: AppointmentType
    scheduled_at: datetime
    timezone: str
    when_label: str
    relative_day: str | None
    clinician_name: str | None
    clinician_specialty: str | None
    location_name: str | None
    preparation_status: PreparationStatus
    question_count: int
    report_count: int


class TodayAppointmentsRead(BaseModel):
    """The appointment block of the Today response (PRD 7, section 9)."""

    next: TodayAppointmentRead | None
    upcoming_count: int
    #: False for somebody who has never added one. The card still renders --
    #: PRD 7 section 9 gives the empty state its own wording.
    has_appointments: bool


class AppointmentSummaryRead(BaseModel):
    """Counts for the Care tab (PRD 7, section 5)."""

    profile_id: uuid.UUID
    upcoming_count: int
    past_count: int
    cancelled_count: int
    has_appointments: bool
    next: TodayAppointmentRead | None = None


# Forward references resolved at import rather than on first use, so a mistake
# in one is a startup failure rather than a 500 on one endpoint.
AppointmentDetailRead.model_rebuild()
AppointmentSaved.model_rebuild()
PreparationRead.model_rebuild()
