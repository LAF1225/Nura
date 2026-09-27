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

#: How someone says they are feeling in the daily check-in (PRD 3, sections 10
#: and 14). Three plain options and nothing else: this is a wellbeing prompt,
#: not symptom tracking, and no clinical meaning is attached to any of them.
WELLBEING_LEVELS = ("good", "okay", "not_great")

#: --- the health record (PRD 4) ---------------------------------------------

#: Where a health record came from (PRD 4, section 32). Everything written in
#: PRD 4 is \`user\`: there is no caregiver or import path yet, and the API sets
#: this itself rather than trusting a client, so a record can never claim a
#: provenance it does not have.
RECORD_SOURCES = ("user", "caregiver", "clinician_import", "system_import")

#: Where a condition stands (PRD 4, section 9). \`uncertain\` is deliberately
#: present: people are often told "possibly X", and forcing that into
#: "active" would overstate it.
CONDITION_STATUSES = ("active", "resolved", "historical", "uncertain")

#: How a medication is taken (PRD 4, section 10).
MEDICATION_FORMS = (
    "tablet",
    "capsule",
    "liquid",
    "injection",
    "inhaler",
    "cream",
    "other",
)

#: What someone is allergic to (PRD 4, section 12).
ALLERGY_TYPES = ("medication", "food", "environmental", "other")

#: How bad a reaction is -- as the *user* described it. Nura never infers this
#: (PRD 4, section 12).
ALLERGY_SEVERITIES = ("mild", "moderate", "severe", "unknown")

#: What a medical note is for (PRD 4, section 16).
MEDICAL_NOTE_CATEGORIES = (
    "general",
    "important",
    "accessibility",
    "care_instruction",
    "other",
)

#: Blood groups, plus the two answers that are not a group (PRD 4, section 15).
#: "I don't know" and "I'd rather not say" are real answers, and storing them
#: is better than leaving the field empty and guessing which was meant.
BLOOD_TYPES = (
    "A+",
    "A-",
    "B+",
    "B-",
    "AB+",
    "AB-",
    "O+",
    "O-",
    "unknown",
    "prefer_not_to_say",
)

#: Progress through the gradual health setup (PRD 4, section 18). Unlike the
#: onboarding state machine, this one is not a gate: nothing in the app is
#: blocked by an incomplete health profile.
HEALTH_PROFILE_STATUSES = ("not_started", "in_progress", "complete")

#: The sections of the health profile, in the order setup offers them
#: (PRD 4, sections 7 and 17). Used for the resume point and for the
#: completeness figure, so the two can never disagree about what counts.
HEALTH_SECTIONS = (
    "conditions",
    "medications",
    "allergies",
    "clinicians",
    "procedures",
    "blood_type",
    "medical_notes",
)

#: --- medication scheduling (PRD 5) -----------------------------------------

#: How a schedule repeats (PRD 5, section 9). Deliberately only two: "every
#: day" and "on these weekdays". Several times a day is not a third type -- it
#: is several time rows on one schedule -- and a date range is a start and an
#: end on any schedule, not a shape of its own. Tapering, sliding scales and
#: every-N-hours are out of scope (PRD 5, section 10).
SCHEDULE_TYPES = ("daily", "specific_days")

#: Where a dose stands (PRD 5, section 21). ``scheduled`` and ``snoozed`` are
#: waiting; ``taken`` and ``skipped`` are what the person recorded; ``missed``
#: is what the grace period concluded when nobody recorded anything; and
#: ``cancelled`` is a future dose withdrawn because the schedule changed. Only
#: ``cancelled`` is excluded from adherence (section 27).
DOSE_STATUSES = ("scheduled", "snoozed", "taken", "skipped", "missed", "cancelled")

#: Who recorded a dose action (PRD 5, section 17). ``app`` is the only one PRD
#: 5 produces through the app; ``robot_voice`` is produced by the future robot
#: hook, which is real and authenticated but has no hardware behind it yet
#: (sections 45 and 47). ``caregiver`` and ``system`` are reserved for later
#: PRDs and nothing writes them.
DOSE_SOURCES = ("app", "robot_voice", "caregiver", "system")

#: Why a dose was skipped (PRD 5, section 20). Recorded exactly as chosen and
#: never interpreted: Nura does not conclude anything medical from "feeling
#: unwell", and does not escalate on it (section 19).
SKIP_REASON_CODES = (
    "none",
    "feeling_unwell",
    "ran_out",
    "clinician_advised",
    "too_late",
    "other",
)

#: Where a dose sits relative to now (PRD 5, section 54). Derived on every
#: read from ``scheduled_for`` and the grace period -- never stored, for the
#: same reason a robot's connection status is never stored: a value that means
#: "right now" is wrong the moment it is written.
DOSE_WINDOWS = ("upcoming", "due", "overdue", "completed")


#: --- symptoms (PRD 6) ------------------------------------------------------

#: Where a symptom episode stands (PRD 6, section 10). ``recurring`` is an
#: episode of something that has happened before -- active, with a link back to
#: the bout it follows -- so a symptom returning never merges two separate
#: events into one (section 38). Nothing infers ``resolved``: only the user
#: saying so sets it.
SYMPTOM_EPISODE_STATUSES = ("active", "resolved", "recurring", "historical")

#: The two statuses that mean "this is going on now". Used by the active list,
#: the Today card and the summary, so they can never disagree.
SYMPTOM_ACTIVE_STATUSES = ("active", "recurring")

#: How the symptom has changed since last time (PRD 6, section 23). ``unsure``
#: is a real answer and is stored as one rather than left blank, because "I
#: don't know" and "I didn't say" are different things.
SYMPTOM_CHANGE_STATES = ("improving", "same", "worsening", "unsure")

#: How a symptom record was captured (PRD 6, section 57). PRD 6's production
#: flows write only the first two: the manual form and the in-app guided
#: conversation. The other three are reserved so a later PRD adds a writer
#: rather than re-deciding the vocabulary, and nothing writes them today --
#: in particular there is no speech recognition anywhere in this system.
SYMPTOM_SOURCES = (
    "manual_app",
    "guided_app",
    "robot_voice_future",
    "caregiver_future",
    "import_future",
)

#: The sources PRD 6 will actually accept from a client. A request claiming to
#: be a future robot's voice is refused rather than stored (section 57).
SYMPTOM_SOURCES_ALLOWED = ("manual_app", "guided_app")

#: Image types a symptom photo may be (PRD 6, section 34). Checked against the
#: bytes as well as the declared type, so a mislabelled upload is refused.
#: Nothing looks *at* these images: PRD 6 section 32 rules out any analysis.
SYMPTOM_PHOTO_CONTENT_TYPES = ("image/jpeg", "image/png", "image/heic", "image/heif")

#: Appearance options, already established in PRD 0.
THEMES = ("system", "light", "dark")


def sql_in_list(values: tuple[str, ...]) -> str:
    """Renders a tuple as a SQL ``IN`` list for use in a CHECK constraint."""
    quoted = ", ".join(f"'{value}'" for value in values)
    return f"({quoted})"
