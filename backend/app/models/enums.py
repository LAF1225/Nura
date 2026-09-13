"""Domain value sets (PRD 1, sections 17, 20, 31 and 34).

Defined once and reused by the models (as database CHECK constraints) and by
the API schemas (as validation), so the database and the API can never drift
apart on what counts as a valid value.

These are plain tuples rather than PostgreSQL ENUM types on purpose: adding a
value to a native enum needs a migration with ``ALTER TYPE``, whereas a CHECK
constraint is straightforward to replace and easy to read in psql.
"""

#: Who the account holder is setting Nura up for (PRD 1, section 17).
SETUP_MODES = ("self", "assisted")

#: Onboarding state machine (PRD 1, section 31). Order matters: it defines
#: both progression and where a partially-onboarded user resumes.
#:
#: PRD 1 ends at ``ready_for_pairing``. PRD 2 adds ``robot_connected``, reached
#: once a robot the account owns has been claimed and seen online. It is not
#: ``onboarding_complete``: detailed setup in later PRDs still follows
#: (PRD 2, section 41).
ONBOARDING_STATUSES = (
    "not_started",
    "authenticated",
    "setup_mode_selected",
    "basic_profile_complete",
    "preferences_complete",
    "consent_complete",
    "ready_for_pairing",
    "robot_connected",
    "onboarding_complete",
)

#: The last status PRD 1 is responsible for reaching.
ONBOARDING_FINAL_STATUS_PRD1 = "ready_for_pairing"

#: Whether a robot is linked to an account (PRD 2, section 31). The PRD's
#: "claim pending" stage is an unconsumed provisioning session rather than a
#: device row, so a device row only exists once a robot has actually reached
#: the backend. ``unclaimed`` is reserved for a future ownership release.
DEVICE_PROVISIONING_STATUSES = ("unclaimed", "claimed")

#: Derived from heartbeats on every read, never stored (PRD 2, section 34).
DEVICE_CONNECTION_STATUSES = ("unknown", "online", "offline")

#: How an account relates to a profile (PRD 1, section 34). Deliberately just
#: these two -- caregiver permission categories belong to a later PRD.
PROFILE_ROLES = ("self", "setup_helper")

#: Privacy-conscious alternative to a date of birth (PRD 1, section 20).
AGE_RANGES = (
    "under_18",
    "18_29",
    "30_44",
    "45_59",
    "60_74",
    "75_plus",
    "prefer_not_to_say",
)

#: Appearance options, already established in PRD 0.
THEMES = ("system", "light", "dark")


def sql_in_list(values: tuple[str, ...]) -> str:
    """Renders a tuple as a SQL ``IN`` list for use in a CHECK constraint."""
    quoted = ", ".join(f"'{value}'" for value in values)
    return f"({quoted})"
