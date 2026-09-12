"""Onboarding progression rules (PRD 1, sections 29-31).

The server is authoritative about progress (PRD 1, section 37). The app drives
the flow, but it cannot declare itself finished without actually having done
the things each step requires -- most importantly the consent gate, which
PRD 1 section 53 requires to genuinely block completion.

Progress is held in a single column, ``users.onboarding_status``. The step
*number* shown in the UI is derived from it here, so there is no second field
that can disagree about where to resume.
"""

from dataclasses import dataclass

from app.models import User
from app.models.enums import ONBOARDING_STATUSES

#: Which numbered step the user is on for a given status. Step 0 means
#: onboarding has not started; the flow after authentication is five steps
#: (PRD 1, section 29: "Step 3 of 5", not a twelve-step wizard).
STEP_FOR_STATUS: dict[str, int] = {
    "not_started": 0,
    "authenticated": 1,  # choose setup mode
    "setup_mode_selected": 2,  # basic profile
    "basic_profile_complete": 3,  # preferences
    "preferences_complete": 4,  # privacy and consent
    "consent_complete": 5,  # ready to pair
    "ready_for_pairing": 5,
    "onboarding_complete": 5,
}

TOTAL_STEPS = 5


class OnboardingTransitionError(Exception):
    """Raised when a status cannot be reached yet, with a usable reason."""


@dataclass(frozen=True)
class OnboardingProgress:
    status: str
    setup_mode: str | None
    terms_accepted: bool
    privacy_acknowledged: bool
    step: int
    total_steps: int
    #: True once PRD 1's flow is finished and pairing can begin.
    ready_for_pairing: bool


def status_rank(status: str) -> int:
    """Position of a status in the state machine. Higher means further along."""
    try:
        return ONBOARDING_STATUSES.index(status)
    except ValueError as error:
        raise OnboardingTransitionError(f"Unknown onboarding status: {status}") from error


def unmet_requirement(user: User, target_status: str) -> str | None:
    """Why `user` cannot be at `target_status` yet, or None if they can.

    Requirements are cumulative: reaching a status means satisfying every
    requirement up to and including it. That is what stops a client from
    jumping straight to `ready_for_pairing` and skipping the consent gate.
    """
    target = status_rank(target_status)

    if target >= status_rank("setup_mode_selected") and user.setup_mode is None:
        return "Choose who Nura is being set up for first."

    if target >= status_rank("basic_profile_complete") and not user.profile_roles:
        return "Add a basic profile first."

    if target >= status_rank("consent_complete"):
        if user.terms_accepted_at is None:
            return "The Terms of Service must be accepted first."
        if user.privacy_acknowledged_at is None:
            return "The Privacy Policy must be acknowledged first."

    return None


def advance_to(user: User, target_status: str) -> str:
    """Moves the account to `target_status`, enforcing the requirements.

    Progress only ever moves forward. A user editing an earlier answer
    (PRD 1, section 44) keeps the furthest status they reached, so going back
    to change a preference does not send them through the rest of the flow
    again.

    Returns the status the account ended up at.
    """
    reason = unmet_requirement(user, target_status)
    if reason is not None:
        raise OnboardingTransitionError(reason)

    if status_rank(target_status) > status_rank(user.onboarding_status):
        user.onboarding_status = target_status
    return user.onboarding_status


def describe(user: User) -> OnboardingProgress:
    """Everything the app needs to render progress and resume at the right step."""
    status = user.onboarding_status
    return OnboardingProgress(
        status=status,
        setup_mode=user.setup_mode,
        terms_accepted=user.terms_accepted_at is not None,
        privacy_acknowledged=user.privacy_acknowledged_at is not None,
        step=STEP_FOR_STATUS.get(status, 0),
        total_steps=TOTAL_STEPS,
        ready_for_pairing=status_rank(status) >= status_rank("ready_for_pairing"),
    )
