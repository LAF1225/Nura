"""The six health record types (PRD 4, sections 20, 25, 26 and 27).

Every route is nested under the profile the record belongs to, and every one
of them resolves that profile through ``OwnedProfile`` -- so a record is
reachable only through a profile the signed-in account owns, and an id that
belongs to someone else is a 404 rather than a 403 (PRD 4, section 25).

The routes are written out per resource rather than generated from a table.
They are repetitive, and that is the point: this is the authorization surface
for someone's medical records, and being able to read each resource's four
routes in full -- without following an abstraction -- is worth more here than
brevity.

Writes are resource-specific by design. There is deliberately no
"save my whole medical profile" endpoint, so a later feature can update one
record without resubmitting everything else (PRD 4, section 27).
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import DbSession, OwnedProfile, http_error
from app.models import (
    Allergy,
    Clinician,
    HealthRecord,
    MedicalCondition,
    MedicalNote,
    Medication,
    Procedure,
    Profile,
)
from app.schemas.health import (
    AllergyCreate,
    AllergyRead,
    AllergyUpdate,
    ClinicianCreate,
    ClinicianRead,
    ClinicianUpdate,
    ConditionCreate,
    ConditionRead,
    ConditionUpdate,
    MedicalNoteCreate,
    MedicalNoteRead,
    MedicalNoteUpdate,
    MedicationCreate,
    MedicationRead,
    MedicationUpdate,
    ProcedureCreate,
    ProcedureRead,
    ProcedureUpdate,
)
from app.services import health
from app.services.errors import DomainError

#: Mounted by `router.py` under `/api/v1`, so every path below begins
#: `/api/v1/profiles/{profile_id}/…`.
router = APIRouter(prefix="/profiles/{profile_id}", tags=["health"])

NO_CONTENT = status.HTTP_204_NO_CONTENT
CREATED = status.HTTP_201_CREATED


def _record[Record: HealthRecord](
    db: DbSession, model: type[Record], profile: Profile, record_id: uuid.UUID
) -> Record:
    """One record of this profile's, or a 404 that reveals nothing."""
    try:
        return health.get_record(db, model, profile.id, record_id)
    except DomainError as error:
        raise http_error(error) from error


# --- conditions -------------------------------------------------------------

conditions = APIRouter(prefix="/conditions")


@conditions.get("", response_model=list[ConditionRead])
def list_conditions(profile: OwnedProfile, db: DbSession) -> list[MedicalCondition]:
    return health.list_records(db, MedicalCondition, profile.id)


@conditions.post("", response_model=ConditionRead, status_code=CREATED)
def create_condition(
    payload: ConditionCreate, profile: OwnedProfile, db: DbSession
) -> MedicalCondition:
    return health.create_record(
        db, MedicalCondition, profile, payload.model_dump(), "conditions"
    )


@conditions.patch("/{record_id}", response_model=ConditionRead)
def update_condition(
    record_id: uuid.UUID,
    payload: ConditionUpdate,
    profile: OwnedProfile,
    db: DbSession,
) -> MedicalCondition:
    record = _record(db, MedicalCondition, profile, record_id)
    return health.update_record(
        db, record, payload.model_dump(exclude_unset=True), "conditions"
    )


@conditions.delete("/{record_id}", status_code=NO_CONTENT)
def delete_condition(record_id: uuid.UUID, profile: OwnedProfile, db: DbSession) -> None:
    health.delete_record(
        db, _record(db, MedicalCondition, profile, record_id), "conditions"
    )


# --- medications ------------------------------------------------------------

medications = APIRouter(prefix="/medications")


@medications.get("", response_model=list[MedicationRead])
def list_medications(
    profile: OwnedProfile,
    db: DbSession,
    active: Annotated[
        bool | None,
        Query(description="Only medications being taken now, or only past ones."),
    ] = None,
) -> list[Medication]:
    """Every medication record, or only the current or only the past ones.

    The filter is on the stored flag the user set, never derived from
    ``end_date``: someone may have stopped a medication without recording when.
    """
    records = health.list_records(db, Medication, profile.id)
    if active is None:
        return records
    return [record for record in records if record.is_active is active]


@medications.post("", response_model=MedicationRead, status_code=CREATED)
def create_medication(
    payload: MedicationCreate, profile: OwnedProfile, db: DbSession
) -> Medication:
    return health.create_record(
        db, Medication, profile, payload.model_dump(), "medications"
    )


@medications.patch("/{record_id}", response_model=MedicationRead)
def update_medication(
    record_id: uuid.UUID,
    payload: MedicationUpdate,
    profile: OwnedProfile,
    db: DbSession,
) -> Medication:
    record = _record(db, Medication, profile, record_id)
    return health.update_record(
        db, record, payload.model_dump(exclude_unset=True), "medications"
    )


@medications.delete("/{record_id}", status_code=NO_CONTENT)
def delete_medication(record_id: uuid.UUID, profile: OwnedProfile, db: DbSession) -> None:
    health.delete_record(db, _record(db, Medication, profile, record_id), "medications")


# --- allergies --------------------------------------------------------------

allergies = APIRouter(prefix="/allergies")


@allergies.get("", response_model=list[AllergyRead])
def list_allergies(profile: OwnedProfile, db: DbSession) -> list[Allergy]:
    return health.list_records(db, Allergy, profile.id)


@allergies.post("", response_model=AllergyRead, status_code=CREATED)
def create_allergy(
    payload: AllergyCreate, profile: OwnedProfile, db: DbSession
) -> Allergy:
    return health.create_record(db, Allergy, profile, payload.model_dump(), "allergies")


@allergies.patch("/{record_id}", response_model=AllergyRead)
def update_allergy(
    record_id: uuid.UUID,
    payload: AllergyUpdate,
    profile: OwnedProfile,
    db: DbSession,
) -> Allergy:
    record = _record(db, Allergy, profile, record_id)
    return health.update_record(
        db, record, payload.model_dump(exclude_unset=True), "allergies"
    )


@allergies.delete("/{record_id}", status_code=NO_CONTENT)
def delete_allergy(record_id: uuid.UUID, profile: OwnedProfile, db: DbSession) -> None:
    health.delete_record(db, _record(db, Allergy, profile, record_id), "allergies")


# --- clinicians -------------------------------------------------------------

clinicians = APIRouter(prefix="/clinicians")


@clinicians.get("", response_model=list[ClinicianRead])
def list_clinicians(profile: OwnedProfile, db: DbSession) -> list[Clinician]:
    return health.list_records(db, Clinician, profile.id)


@clinicians.post("", response_model=ClinicianRead, status_code=CREATED)
def create_clinician(
    payload: ClinicianCreate, profile: OwnedProfile, db: DbSession
) -> Clinician:
    return health.create_record(
        db, Clinician, profile, payload.model_dump(), "clinicians"
    )


@clinicians.patch("/{record_id}", response_model=ClinicianRead)
def update_clinician(
    record_id: uuid.UUID,
    payload: ClinicianUpdate,
    profile: OwnedProfile,
    db: DbSession,
) -> Clinician:
    record = _record(db, Clinician, profile, record_id)
    return health.update_record(
        db, record, payload.model_dump(exclude_unset=True), "clinicians"
    )


@clinicians.delete("/{record_id}", status_code=NO_CONTENT)
def delete_clinician(record_id: uuid.UUID, profile: OwnedProfile, db: DbSession) -> None:
    health.delete_record(db, _record(db, Clinician, profile, record_id), "clinicians")


# --- procedures -------------------------------------------------------------

procedures = APIRouter(prefix="/procedures")


@procedures.get("", response_model=list[ProcedureRead])
def list_procedures(profile: OwnedProfile, db: DbSession) -> list[Procedure]:
    return health.list_records(db, Procedure, profile.id)


@procedures.post("", response_model=ProcedureRead, status_code=CREATED)
def create_procedure(
    payload: ProcedureCreate, profile: OwnedProfile, db: DbSession
) -> Procedure:
    return health.create_record(
        db, Procedure, profile, payload.model_dump(), "procedures"
    )


@procedures.patch("/{record_id}", response_model=ProcedureRead)
def update_procedure(
    record_id: uuid.UUID,
    payload: ProcedureUpdate,
    profile: OwnedProfile,
    db: DbSession,
) -> Procedure:
    record = _record(db, Procedure, profile, record_id)
    return health.update_record(
        db, record, payload.model_dump(exclude_unset=True), "procedures"
    )


@procedures.delete("/{record_id}", status_code=NO_CONTENT)
def delete_procedure(record_id: uuid.UUID, profile: OwnedProfile, db: DbSession) -> None:
    health.delete_record(db, _record(db, Procedure, profile, record_id), "procedures")


# --- medical notes ----------------------------------------------------------

medical_notes = APIRouter(prefix="/medical-notes")


@medical_notes.get("", response_model=list[MedicalNoteRead])
def list_medical_notes(profile: OwnedProfile, db: DbSession) -> list[MedicalNote]:
    return health.list_records(db, MedicalNote, profile.id)


@medical_notes.post("", response_model=MedicalNoteRead, status_code=CREATED)
def create_medical_note(
    payload: MedicalNoteCreate, profile: OwnedProfile, db: DbSession
) -> MedicalNote:
    return health.create_record(
        db, MedicalNote, profile, payload.model_dump(), "medical_notes"
    )


@medical_notes.patch("/{record_id}", response_model=MedicalNoteRead)
def update_medical_note(
    record_id: uuid.UUID,
    payload: MedicalNoteUpdate,
    profile: OwnedProfile,
    db: DbSession,
) -> MedicalNote:
    record = _record(db, MedicalNote, profile, record_id)
    return health.update_record(
        db, record, payload.model_dump(exclude_unset=True), "medical_notes"
    )


@medical_notes.delete("/{record_id}", status_code=NO_CONTENT)
def delete_medical_note(
    record_id: uuid.UUID, profile: OwnedProfile, db: DbSession
) -> None:
    health.delete_record(
        db, _record(db, MedicalNote, profile, record_id), "medical_notes"
    )


for sub_router in (
    conditions,
    medications,
    allergies,
    clinicians,
    procedures,
    medical_notes,
):
    router.include_router(sub_router)
