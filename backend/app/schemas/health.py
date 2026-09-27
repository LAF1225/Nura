"""Health record request/response models (PRD 4, sections 9-16, 22 and 31).

Three rules the shapes here enforce, before anything reaches the database:

**Only a name is ever required.** Everything else is optional, because a
profile someone fills in gradually is worth more than one they abandon at a
field they cannot answer (PRD 4, section 3).

**A date is stored at the precision the user has.** Every approximate date is a
date *or* a year, never both, and never a year quietly turned into the 1st of
January (PRD 4, section 31).

**``source`` is not an input.** It says where a record came from, so a client
cannot set it -- a record must never be able to claim it came from a clinician
when a person typed it in (PRD 4, section 32).
"""

import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

from app.models.enums import (
    ALLERGY_SEVERITIES,
    ALLERGY_TYPES,
    BLOOD_TYPES,
    CONDITION_STATUSES,
    HEALTH_PROFILE_STATUSES,
    HEALTH_SECTIONS,
    MEDICAL_NOTE_CATEGORIES,
    MEDICATION_FORMS,
)
from app.models.health import (
    EARLIEST_YEAR,
    NAME_MAX_LENGTH,
    NOTES_MAX_LENGTH,
    SHORT_TEXT_MAX_LENGTH,
)

ConditionStatus = Literal["active", "resolved", "historical", "uncertain"]
MedicationForm = Literal[
    "tablet", "capsule", "liquid", "injection", "inhaler", "cream", "other"
]
AllergyType = Literal["medication", "food", "environmental", "other"]
AllergySeverity = Literal["mild", "moderate", "severe", "unknown"]
NoteCategory = Literal[
    "general", "important", "accessibility", "care_instruction", "other"
]
BloodType = Literal[
    "A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-", "unknown", "prefer_not_to_say"
]
HealthProfileStatus = Literal["not_started", "in_progress", "complete"]
HealthSection = Literal[
    "conditions",
    "medications",
    "allergies",
    "clinicians",
    "procedures",
    "blood_type",
    "medical_notes",
]
RecordSource = Literal["user", "caregiver", "clinician_import", "system_import"]

# Guards every Literal above against drifting from the database CHECK
# constraints, which are generated from these same tuples.
assert set(CONDITION_STATUSES) == set(ConditionStatus.__args__)  # type: ignore[attr-defined]
assert set(MEDICATION_FORMS) == set(MedicationForm.__args__)  # type: ignore[attr-defined]
assert set(ALLERGY_TYPES) == set(AllergyType.__args__)  # type: ignore[attr-defined]
assert set(ALLERGY_SEVERITIES) == set(AllergySeverity.__args__)  # type: ignore[attr-defined]
assert set(MEDICAL_NOTE_CATEGORIES) == set(NoteCategory.__args__)  # type: ignore[attr-defined]
assert set(BLOOD_TYPES) == set(BloodType.__args__)  # type: ignore[attr-defined]
assert set(HEALTH_PROFILE_STATUSES) == set(HealthProfileStatus.__args__)  # type: ignore[attr-defined]
assert set(HEALTH_SECTIONS) == set(HealthSection.__args__)  # type: ignore[attr-defined]


def _blank_to_none(value: object) -> object:
    """An emptied text field means "no value", not an empty string.

    Without this, clearing a field in the app would store `""`, which then
    renders as a value the user did not write.
    """
    if isinstance(value, str) and value.strip() == "":
        return None
    return value


#: The one required field on most records, trimmed so a stray space is not a name.
RecordName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=NAME_MAX_LENGTH),
]
# Optional text fields put the length limit on the `str` side of the union and
# the blank-to-null step outside it. The order matters: a constraint applied to
# `str | None` is asked to measure the length of `None`, which is an error
# rather than a validation failure.
#: An optional single-line value.
ShortText = Annotated[
    Annotated[
        str, StringConstraints(strip_whitespace=True, max_length=SHORT_TEXT_MAX_LENGTH)
    ]
    | None,
    BeforeValidator(_blank_to_none),
]
#: An optional name-length value, e.g. a clinician the user typed in free text.
NameText = Annotated[
    Annotated[str, StringConstraints(strip_whitespace=True, max_length=NAME_MAX_LENGTH)]
    | None,
    BeforeValidator(_blank_to_none),
]
#: Optional longer free text.
LongText = Annotated[
    Annotated[str, StringConstraints(strip_whitespace=True, max_length=NOTES_MAX_LENGTH)]
    | None,
    BeforeValidator(_blank_to_none),
]
#: A dose as written -- "half", "12.5" -- kept apart from its unit.
DoseText = Annotated[
    Annotated[str, StringConstraints(strip_whitespace=True, max_length=50)] | None,
    BeforeValidator(_blank_to_none),
]
DoseUnitText = Annotated[
    Annotated[str, StringConstraints(strip_whitespace=True, max_length=30)] | None,
    BeforeValidator(_blank_to_none),
]
PhoneText = Annotated[
    Annotated[str, StringConstraints(strip_whitespace=True, max_length=40)] | None,
    BeforeValidator(_blank_to_none),
]
EmailText = Annotated[
    Annotated[str, StringConstraints(strip_whitespace=True, max_length=320)] | None,
    BeforeValidator(_blank_to_none),
]
#: A note's body: required on create, and still non-empty if a PATCH sends it.
NoteBody = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=NOTES_MAX_LENGTH),
]
#: A four-digit year the user actually remembers.
ApproximateYear = Annotated[int | None, Field(ge=EARLIEST_YEAR, le=2200)]


def _one_precision(exact: date | None, year: int | None, label: str) -> None:
    """Refuses a date *and* a year for the same event (PRD 4, section 31)."""
    if exact is not None and year is not None:
        raise ValueError(f"Give either a {label} date or a year, not both.")


class RecordBase(BaseModel):
    """Shared config for every record model read out of the database."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    profile_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


# --- conditions -------------------------------------------------------------


class ConditionCreate(BaseModel):
    name: RecordName
    status: ConditionStatus = "active"
    diagnosed_date: date | None = None
    diagnosed_year: ApproximateYear = None
    diagnosing_clinician: NameText = None
    notes: LongText = None

    @model_validator(mode="after")
    def _check_precision(self) -> "ConditionCreate":
        _one_precision(self.diagnosed_date, self.diagnosed_year, "diagnosis")
        return self


class ConditionUpdate(BaseModel):
    """Every field optional -- a PATCH only changes what it names."""

    name: RecordName | None = None
    status: ConditionStatus | None = None
    diagnosed_date: date | None = None
    diagnosed_year: ApproximateYear = None
    diagnosing_clinician: NameText = None
    notes: LongText = None

    @model_validator(mode="after")
    def _check_precision(self) -> "ConditionUpdate":
        _one_precision(self.diagnosed_date, self.diagnosed_year, "diagnosis")
        return self


class ConditionRead(RecordBase):
    name: str
    status: ConditionStatus
    diagnosed_date: date | None
    diagnosed_year: int | None
    diagnosing_clinician: str | None
    notes: str | None
    source: RecordSource


# --- medications ------------------------------------------------------------


class MedicationCreate(BaseModel):
    name: RecordName
    dose: DoseText = None
    dose_unit: DoseUnitText = None
    form: MedicationForm | None = None
    #: Free text: "one at night", "two puffs when needed". Forcing this into a
    #: schedule would either lose meaning or invent it (PRD 4, section 10).
    frequency_text: ShortText = None
    instructions: ShortText = None
    start_date: date | None = None
    end_date: date | None = None
    prescribing_clinician: NameText = None
    reason: ShortText = None
    #: Set by the user, never inferred from the end date.
    is_active: bool = True
    notes: LongText = None


class MedicationUpdate(BaseModel):
    name: RecordName | None = None
    dose: DoseText = None
    dose_unit: DoseUnitText = None
    form: MedicationForm | None = None
    frequency_text: ShortText = None
    instructions: ShortText = None
    start_date: date | None = None
    end_date: date | None = None
    prescribing_clinician: NameText = None
    reason: ShortText = None
    is_active: bool | None = None
    notes: LongText = None


class MedicationRead(RecordBase):
    name: str
    dose: str | None
    dose_unit: str | None
    form: MedicationForm | None
    frequency_text: str | None
    instructions: str | None
    start_date: date | None
    end_date: date | None
    prescribing_clinician: str | None
    reason: str | None
    is_active: bool
    notes: str | None
    source: RecordSource


# --- allergies --------------------------------------------------------------


class AllergyCreate(BaseModel):
    allergen: RecordName
    allergy_type: AllergyType = "other"
    reaction: ShortText = None
    #: Whatever the user chose. Nura never works severity out from the
    #: reaction text (PRD 4, section 12).
    severity: AllergySeverity = "unknown"
    notes: LongText = None


class AllergyUpdate(BaseModel):
    allergen: RecordName | None = None
    allergy_type: AllergyType | None = None
    reaction: ShortText = None
    severity: AllergySeverity | None = None
    notes: LongText = None


class AllergyRead(RecordBase):
    allergen: str
    allergy_type: AllergyType
    reaction: str | None
    severity: AllergySeverity
    notes: str | None
    source: RecordSource


# --- clinicians -------------------------------------------------------------


class ClinicianCreate(BaseModel):
    name: RecordName
    specialty: NameText = None
    clinic_name: NameText = None
    phone: PhoneText = None
    email: EmailText = None
    address: ShortText = None
    notes: LongText = None


class ClinicianUpdate(BaseModel):
    name: RecordName | None = None
    specialty: NameText = None
    clinic_name: NameText = None
    phone: PhoneText = None
    email: EmailText = None
    address: ShortText = None
    notes: LongText = None


class ClinicianRead(RecordBase):
    name: str
    specialty: str | None
    clinic_name: str | None
    phone: str | None
    email: str | None
    address: str | None
    notes: str | None


# --- procedures -------------------------------------------------------------


class ProcedureCreate(BaseModel):
    name: RecordName
    performed_date: date | None = None
    performed_year: ApproximateYear = None
    hospital: NameText = None
    clinician: NameText = None
    outcome_notes: LongText = None
    notes: LongText = None

    @model_validator(mode="after")
    def _check_precision(self) -> "ProcedureCreate":
        _one_precision(self.performed_date, self.performed_year, "procedure")
        return self


class ProcedureUpdate(BaseModel):
    name: RecordName | None = None
    performed_date: date | None = None
    performed_year: ApproximateYear = None
    hospital: NameText = None
    clinician: NameText = None
    outcome_notes: LongText = None
    notes: LongText = None

    @model_validator(mode="after")
    def _check_precision(self) -> "ProcedureUpdate":
        _one_precision(self.performed_date, self.performed_year, "procedure")
        return self


class ProcedureRead(RecordBase):
    name: str
    performed_date: date | None
    performed_year: int | None
    hospital: str | None
    clinician: str | None
    outcome_notes: str | None
    notes: str | None


# --- medical notes ----------------------------------------------------------


class MedicalNoteCreate(BaseModel):
    title: RecordName
    body: NoteBody
    category: NoteCategory = "general"


class MedicalNoteUpdate(BaseModel):
    title: RecordName | None = None
    body: NoteBody | None = None
    category: NoteCategory | None = None


class MedicalNoteRead(RecordBase):
    title: str
    body: str
    category: NoteCategory


# --- setup and summary ------------------------------------------------------


class HealthSetupRead(BaseModel):
    profile_id: uuid.UUID
    status: HealthProfileStatus
    #: Where to resume, or null.
    step: HealthSection | None
    blood_type: BloodType | None


class HealthSetupUpdate(BaseModel):
    """Progress through the gradual setup, plus the blood type.

    Blood type is written here rather than through `PATCH /profiles/{id}`, so
    that every medical write in the API sits behind a health route and the
    surface that touches medical data stays easy to audit -- even though the
    column itself lives on `profiles` (PRD 4, section 15).
    """

    status: HealthProfileStatus | None = None
    #: Explicit null clears the resume point; omitting it leaves it alone.
    step: HealthSection | None = None
    blood_type: BloodType | None = None


class HealthSectionRead(BaseModel):
    key: HealthSection
    title: str
    count: int
    complete: bool
    #: When anything in this section last changed, for "Updated 2 days ago".
    updated_at: datetime | None


class HealthSummaryRead(BaseModel):
    """The Health overview in one response (PRD 4, sections 6 and 22).

    Counts only. No condition names, medication names or note bodies appear
    here, so the overview -- and anything that later embeds it, such as the
    Today card -- cannot leak sensitive detail (PRD 4, section 47).
    """

    profile_id: uuid.UUID
    status: HealthProfileStatus
    step: HealthSection | None
    blood_type: BloodType | None
    sections: list[HealthSectionRead]
    completed_sections: int
    total_sections: int
    #: Equal weight across the seven sections. Informational only.
    percent: int
    active_conditions: int
    active_medications: int
    #: Kept separate from the condition counts on purpose (PRD 6, s48).
    active_symptoms: int
    symptom_updates_this_week: int
