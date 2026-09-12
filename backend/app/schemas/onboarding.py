"""Onboarding request/response models (PRD 1, sections 30 and 31)."""

from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.models.enums import ONBOARDING_STATUSES, SETUP_MODES

SetupMode = Literal["self", "assisted"]
OnboardingStatus = Literal[
    "not_started",
    "authenticated",
    "setup_mode_selected",
    "basic_profile_complete",
    "preferences_complete",
    "consent_complete",
    "ready_for_pairing",
    "onboarding_complete",
]

# Keeps these in step with the database CHECK constraints.
assert set(SETUP_MODES) == set(SetupMode.__args__)  # type: ignore[attr-defined]
assert set(ONBOARDING_STATUSES) == set(OnboardingStatus.__args__)  # type: ignore[attr-defined]


class OnboardingRead(BaseModel):
    """Where the user is in onboarding, and what the UI should show."""

    model_config = ConfigDict(from_attributes=True)

    status: OnboardingStatus
    setup_mode: SetupMode | None
    terms_accepted: bool
    privacy_acknowledged: bool
    #: For "Step 3 of 5" (PRD 1, section 29).
    step: int
    total_steps: int
    ready_for_pairing: bool


class OnboardingUpdate(BaseModel):
    """PATCH body. Only the fields present are applied."""

    setup_mode: SetupMode | None = None
    #: Requested progress. The server refuses statuses whose requirements are
    #: not met, and never moves progress backwards.
    status: OnboardingStatus | None = None
    #: Two separate acknowledgements on purpose -- PRD 1 section 27 forbids
    #: merging them into a single control.
    accept_terms: bool | None = None
    acknowledge_privacy: bool | None = None
