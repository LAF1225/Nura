"""The health record's rules (PRD 4, sections 8, 20, 22, 25, 32 and 34).

Six record types with identical lifecycle rules, so the lifecycle lives here
once rather than six times in the HTTP layer. That is not only shorter: it
means the authorization rule -- *a record is reachable only through a profile
the caller owns* -- is written in exactly one place and cannot drift between
resources.

Two rules worth stating plainly, because both are easy to get wrong later:

**Provenance is set by the server.** ``source`` says where a record came from.
A client cannot supply it, so a record can never claim to have come from a
clinician import when a person typed it in (PRD 4, section 32).

**Values are never logged.** Every log line here names the resource and the
action and stops. A condition name, a medication name, an allergen or a note
body must not appear in a log, an error message or an analytics event
(PRD 4, sections 33 and 34).
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

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
from app.models.enums import HEALTH_SECTIONS
from app.services.errors import NotFoundError

logger = logging.getLogger(__name__)


class RecordNotFoundError(NotFoundError):
    """The record does not exist, or belongs to a profile the caller cannot see.

    One answer for both, so a caller probing ids learns nothing (PRD 4,
    section 25).
    """

    code = "record_not_found"


#: Section key -> the model behind it, and what to call it in the app. The
#: order is ``HEALTH_SECTIONS``: the order setup offers them, and the order the
#: overview lists them, so the two can never disagree.
SECTION_MODELS: dict[str, type[HealthRecord]] = {
    "conditions": MedicalCondition,
    "medications": Medication,
    "allergies": Allergy,
    "clinicians": Clinician,
    "procedures": Procedure,
    "medical_notes": MedicalNote,
}

SECTION_TITLES: dict[str, str] = {
    "conditions": "Conditions",
    "medications": "Medications",
    "allergies": "Allergies",
    "clinicians": "Doctors",
    "procedures": "Surgeries & procedures",
    "blood_type": "Blood type",
    "medical_notes": "Medical notes",
}


def _log(resource: str, action: str) -> None:
    """``health.conditions.create success`` -- and never a value (PRD 4, s34)."""
    logger.info("health.%s.%s success", resource, action)


# --- reading ----------------------------------------------------------------


def list_records[Record: HealthRecord](
    db: Session, model: type[Record], profile_id: uuid.UUID
) -> list[Record]:
    """Every record of one type for one profile, newest first."""
    return list(
        db.execute(
            select(model)
            .where(model.profile_id == profile_id)
            .order_by(model.created_at.desc())
        )
        .scalars()
        .all()
    )


def get_record[Record: HealthRecord](
    db: Session, model: type[Record], profile_id: uuid.UUID, record_id: uuid.UUID
) -> Record:
    """One record, or 404.

    The profile is part of the lookup rather than checked afterwards, so there
    is no path where a record is fetched first and authorized second.
    """
    record = db.execute(
        select(model).where(model.id == record_id, model.profile_id == profile_id)
    ).scalar_one_or_none()
    if record is None:
        raise RecordNotFoundError("Not found.")
    return record


# --- writing ----------------------------------------------------------------


def create_record[Record: HealthRecord](
    db: Session,
    model: type[Record],
    profile: Profile,
    fields: dict[str, Any],
    resource: str,
) -> Record:
    """Adds a record, and marks health setup as under way if it had not begun.

    The status nudge is here rather than in the client: someone who adds a
    condition has started their health profile, whether or not they came
    through the setup flow (PRD 4, section 18).
    """
    record = model(profile_id=profile.id, **fields)
    db.add(record)

    if profile.health_profile_status == "not_started":
        profile.health_profile_status = "in_progress"

    db.commit()
    db.refresh(record)
    _log(resource, "create")
    return record


def update_record[Record: HealthRecord](
    db: Session, record: Record, fields: dict[str, Any], resource: str
) -> Record:
    """Applies the fields present in a PATCH and leaves the rest alone."""
    for field, value in fields.items():
        setattr(record, field, value)
    db.commit()
    db.refresh(record)
    _log(resource, "update")
    return record


def delete_record(db: Session, record: HealthRecord, resource: str) -> None:
    """Removes a record. The confirmation happens in the app (PRD 4, s20)."""
    db.delete(record)
    db.commit()
    _log(resource, "delete")


def update_health_setup(
    db: Session,
    profile: Profile,
    *,
    status: str | None = None,
    step: str | None = None,
    step_set: bool = False,
    blood_type: str | None = None,
    blood_type_set: bool = False,
) -> Profile:
    """Records progress through the gradual setup, and the blood type.

    ``step_set`` and ``blood_type_set`` distinguish "not mentioned" from
    "explicitly cleared": a PATCH that omits the step must leave it alone,
    while one that sends null must clear it.
    """
    if status is not None:
        profile.health_profile_status = status
    if step_set:
        profile.health_profile_step = step
    if blood_type_set:
        profile.blood_type = blood_type
        # Answering is starting, even if nothing else has been filled in.
        if profile.health_profile_status == "not_started" and blood_type is not None:
            profile.health_profile_status = "in_progress"

    db.commit()
    db.refresh(profile)
    _log("setup", "update")
    return profile


# --- the summary ------------------------------------------------------------


@dataclass(frozen=True)
class SectionSummary:
    key: str
    title: str
    count: int
    #: True once the section has something in it. See ``build_summary`` for
    #: what that deliberately does *not* mean.
    complete: bool
    updated_at: datetime | None


@dataclass(frozen=True)
class HealthSummary:
    profile_id: uuid.UUID
    blood_type: str | None
    status: str
    step: str | None
    sections: list[SectionSummary]
    completed_sections: int
    total_sections: int
    percent: int
    #: Called out separately because "what are you taking now" and "what have
    #: you ever taken" are different questions (PRD 4, section 22).
    active_conditions: int
    active_medications: int


def _count_and_last_update(
    db: Session, model: type[HealthRecord], profile_id: uuid.UUID
) -> tuple[int, datetime | None]:
    row = db.execute(
        select(func.count(model.id), func.max(model.updated_at)).where(
            model.profile_id == profile_id
        )
    ).one()
    return int(row[0]), row[1]


def build_summary(db: Session, profile: Profile) -> HealthSummary:
    """Counts, per section, plus a completeness figure.

    **Completeness is informational and equal-weight** (PRD 4, section 7): each
    of the seven sections counts for the same, and a section counts once it has
    anything in it. It never blocks anything and is never shown as a warning.

    What it deliberately does not model: "I have no allergies". Someone with
    nothing to add in a section will not reach 100%, and that is accepted
    rather than solved with a "nothing to add" flag per section -- the figure
    is a gentle prompt, not a score, and the app's wording says so.
    """
    sections: list[SectionSummary] = []
    completed = 0

    for key in HEALTH_SECTIONS:
        if key == "blood_type":
            # Not a list of records: one answer on the profile. "Unknown" and
            # "prefer not to say" are answers, so both count as given.
            has_answer = profile.blood_type is not None
            sections.append(
                SectionSummary(
                    key=key,
                    title=SECTION_TITLES[key],
                    count=1 if has_answer else 0,
                    complete=has_answer,
                    updated_at=None,
                )
            )
            completed += 1 if has_answer else 0
            continue

        count, updated_at = _count_and_last_update(db, SECTION_MODELS[key], profile.id)
        sections.append(
            SectionSummary(
                key=key,
                title=SECTION_TITLES[key],
                count=count,
                complete=count > 0,
                updated_at=updated_at,
            )
        )
        completed += 1 if count > 0 else 0

    total = len(HEALTH_SECTIONS)

    active_conditions = int(
        db.execute(
            select(func.count(MedicalCondition.id)).where(
                MedicalCondition.profile_id == profile.id,
                MedicalCondition.status == "active",
            )
        ).scalar_one()
    )
    active_medications = int(
        db.execute(
            select(func.count(Medication.id)).where(
                Medication.profile_id == profile.id,
                Medication.is_active.is_(True),
            )
        ).scalar_one()
    )

    return HealthSummary(
        profile_id=profile.id,
        blood_type=profile.blood_type,
        status=profile.health_profile_status,
        step=profile.health_profile_step,
        sections=sections,
        completed_sections=completed,
        total_sections=total,
        # Rounded, never rounded *up* to 100 from 6/7: a profile is only
        # complete when it is.
        percent=int(completed * 100 / total),
        active_conditions=active_conditions,
        active_medications=active_medications,
    )
