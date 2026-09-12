"""Onboarding progress (PRD 1, sections 30, 31 and 35).

Reading this endpoint on launch is what lets the app resume at the right step
instead of restarting the flow.
"""

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentUser, DbSession
from app.schemas.onboarding import OnboardingRead, OnboardingUpdate
from app.services import onboarding as onboarding_service

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


def _read(user: CurrentUser) -> OnboardingRead:
    return OnboardingRead.model_validate(onboarding_service.describe(user))


@router.get("", response_model=OnboardingRead)
def read_onboarding(user: CurrentUser) -> OnboardingRead:
    return _read(user)


@router.patch("", response_model=OnboardingRead)
def update_onboarding(
    payload: OnboardingUpdate, user: CurrentUser, db: DbSession
) -> OnboardingRead:
    """Applies onboarding changes, with the server enforcing the rules.

    Consent is recorded as a timestamp so there is a record of *when* it was
    given. A status that the account does not yet qualify for is rejected with
    a message the app can show directly.
    """
    data = payload.model_dump(exclude_unset=True)

    if "setup_mode" in data and data["setup_mode"] is not None:
        user.setup_mode = data["setup_mode"]

    now = datetime.now(UTC)
    if "accept_terms" in data and data["accept_terms"] is not None:
        user.terms_accepted_at = now if data["accept_terms"] else None
    if "acknowledge_privacy" in data and data["acknowledge_privacy"] is not None:
        user.privacy_acknowledged_at = now if data["acknowledge_privacy"] else None

    # Flush so the requirement checks below see the values just set.
    db.flush()

    if "status" in data and data["status"] is not None:
        try:
            onboarding_service.advance_to(user, data["status"])
        except onboarding_service.OnboardingTransitionError as error:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail=str(error)
            ) from error

    db.commit()
    db.refresh(user)
    return _read(user)
