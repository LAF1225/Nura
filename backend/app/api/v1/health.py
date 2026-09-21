"""The health profile as a whole (PRD 4, sections 6, 7, 18 and 22).

Two routes, both about the profile rather than about any one record: what is
in the health profile so far, and how far through setting it up the person is.

The summary is counts only. No condition name, medication name, allergen or
note body appears in it, so the Health overview -- and the optional Today card
that shows the same figure -- cannot leak anything sensitive onto a screen
someone else might glance at (PRD 4, sections 33 and 47).
"""

from fastapi import APIRouter

from app.api.deps import DbSession, OwnedProfile
from app.schemas.health import (
    HealthSectionRead,
    HealthSetupRead,
    HealthSetupUpdate,
    HealthSummaryRead,
)
from app.services import health

router = APIRouter(prefix="/profiles/{profile_id}", tags=["health"])


@router.get("/health-summary", response_model=HealthSummaryRead)
def read_health_summary(profile: OwnedProfile, db: DbSession) -> HealthSummaryRead:
    """Everything the Health overview needs, in one request.

    Works from the first moment: a profile with nothing in it answers with
    zeroes and 0%, which the app renders as an invitation rather than as an
    error (PRD 4, section 37).
    """
    summary = health.build_summary(db, profile)
    return HealthSummaryRead(
        profile_id=summary.profile_id,
        status=summary.status,  # type: ignore[arg-type]
        step=summary.step,  # type: ignore[arg-type]
        blood_type=summary.blood_type,  # type: ignore[arg-type]
        sections=[
            HealthSectionRead(
                key=section.key,  # type: ignore[arg-type]
                title=section.title,
                count=section.count,
                complete=section.complete,
                updated_at=section.updated_at,
            )
            for section in summary.sections
        ],
        completed_sections=summary.completed_sections,
        total_sections=summary.total_sections,
        percent=summary.percent,
        active_conditions=summary.active_conditions,
        active_medications=summary.active_medications,
    )


def _setup_read(profile: OwnedProfile) -> HealthSetupRead:
    return HealthSetupRead(
        profile_id=profile.id,
        status=profile.health_profile_status,  # type: ignore[arg-type]
        step=profile.health_profile_step,  # type: ignore[arg-type]
        blood_type=profile.blood_type,  # type: ignore[arg-type]
    )


@router.get("/health-setup", response_model=HealthSetupRead)
def read_health_setup(profile: OwnedProfile) -> HealthSetupRead:
    """Where this person got to, so setup can resume there (PRD 4, s18)."""
    return _setup_read(profile)


@router.patch("/health-setup", response_model=HealthSetupRead)
def update_health_setup(
    payload: HealthSetupUpdate, profile: OwnedProfile, db: DbSession
) -> HealthSetupRead:
    """Records progress, and the blood type.

    Unlike onboarding, nothing here is gated: a user may mark their health
    profile complete with sections still empty, because "I have nothing to add"
    is a legitimate answer and PRD 4 section 17 forbids blocking on it.

    `exclude_unset` is what separates "left alone" from "cleared": a PATCH that
    omits `step` keeps the current one, while one that sends null clears it.
    """
    fields = payload.model_dump(exclude_unset=True)
    profile = health.update_health_setup(
        db,
        profile,
        status=fields.get("status"),
        step=fields.get("step"),
        step_set="step" in fields,
        blood_type=fields.get("blood_type"),
        blood_type_set="blood_type" in fields,
    )
    return _setup_read(profile)
