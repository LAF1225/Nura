"""Every sentence the caregiver features say, in one module.

PRD 9, sections 15, 34, 35, 36, 86 and 88.

The PRD 7 lesson, applied again: when one file writes all the prose, the test
that checks none of it diagnoses anything is exhaustive rather than a spot
check, and the wording can be fixed or translated without rewriting a single
stored row.

Two kinds of text live here.

**Check-in sentences.** A quick check-in is stored as a code, never as the
sentence, so ``im_okay`` renders whatever "I'm okay" should say today. It also
means a check-in can never carry something the sender did not intend to put in a
care thread -- there is no free-text path into one.

**Suggestion diffs.** Section 86 asks for an explicit current-versus-proposed
pair, and both halves are rendered by the server. A medication reminder time is
only meaningful in the schedule's own zone and an appointment in its own, which
is the same reason PRD 7 renders appointment labels server-side: Hermes' ``Intl``
cannot be relied on for a time-zone database.

**Nothing here interprets anything.** No sentence in this module says a dose was
missed too often, that a symptom is concerning, or that a change is a good idea.
A caregiver reading these screens is told what was proposed and what is there
now, and makes up their own mind.
"""

from datetime import datetime, time
from zoneinfo import ZoneInfo

from app.models.enums import (
    CAREGIVER_PERMISSION_KEYS,
    FAMILY_CHECK_IN_CODES,
)
from app.services.appointments import wording as shared

#: What each quick check-in actually says (sections 34, 35 and 36).
#:
#: Plain, short, and none of them an alarm. Section 35 is explicit that PRD 9
#: must not infer emergency severity from a check-in, and section 45 that these
#: are communication rather than escalation -- so "I need help with something"
#: is phrased as the everyday request it usually is, and nothing anywhere treats
#: it as a signal.
CHECK_IN_SENTENCES: dict[str, str] = {
    "im_okay": "I’m okay.",
    "not_great": "Not feeling great.",
    "please_call_me": "Can you call me?",
    "need_help": "I need help with something.",
    "how_are_you": "How are you doing?",
    "thinking_of_you": "Thinking of you.",
}
assert set(CHECK_IN_SENTENCES) == set(FAMILY_CHECK_IN_CODES)

#: How each permission category is named to a person (section 15).
#:
#: Section 15 forbids vague wording such as "access health information", so each
#: label says what would actually be visible. "Health summary" is the honest name
#: for ``general_health_summary``: it is counts, not records.
PERMISSION_LABELS: dict[str, str] = {
    "medications": "Medication reminders",
    "appointments": "Appointments",
    "symptoms": "Symptoms",
    "reports": "Health reports",
    "safety_alerts": "Safety alerts",
    "communication": "Family messages",
    "routines": "Routines",
    "general_health_summary": "Health summary",
}
assert set(PERMISSION_LABELS) == set(CAREGIVER_PERMISSION_KEYS)

#: What a category covers, said once so the invitation screen, the permission
#: screen and the caregiver home cannot describe it differently.
PERMISSION_DESCRIPTIONS: dict[str, str] = {
    "medications": (
        "Which medications, when the reminders are, and how recently they were recorded."
    ),
    "appointments": "Upcoming appointments, and the questions written down for them.",
    "symptoms": "Symptoms being tracked, and what was recorded about them.",
    "reports": "Health summaries prepared for a doctor’s appointment.",
    "safety_alerts": (
        "Safety alerts raised about them, and whether each has been acknowledged."
    ),
    "communication": "Sending and receiving family messages and check-ins.",
    # PRD 12 built the source this used to say did not exist. Section 42 is
    # why the second sentence is here: a caregiver should be able to see where
    # the edge is rather than wonder why the list looks short.
    "routines": (
        "Daily routines and whether they are being done. Tasks, alarms and "
        "personal reminders stay private."
    ),
    "general_health_summary": (
        "How many conditions, medications and symptoms are recorded. "
        "Not the records themselves."
    ),
}
assert set(PERMISSION_DESCRIPTIONS) == set(CAREGIVER_PERMISSION_KEYS)

#: How each role reads in a list (section 5).
ROLE_LABELS: dict[str, str] = {
    "primary_caregiver": "Primary caregiver",
    "family": "Family",
    "caregiver": "Caregiver",
    "emergency_contact": "Emergency contact",
    "other": "Other",
}

#: What each proposable change is called (section 85).
ACTION_LABELS: dict[str, str] = {
    "change_medication_reminder_time": "Change a medication reminder time",
    "pause_medication_reminder": "Pause a medication reminder",
    "resume_medication_reminder": "Turn a medication reminder back on",
    "add_appointment": "Add an appointment",
    "add_routine": "Suggest a routine",
    "change_routine_time": "Change a routine time",
    "pause_routine": "Pause a routine",
    "change_appointment_time": "Change an appointment time",
}


def check_in_sentence(code: str) -> str:
    """The sentence for a stored check-in code.

    Falls back to the code's own words rather than raising: a row written by a
    later version of the app should render as something readable, not as a
    server error in the middle of somebody's care thread.
    """
    return CHECK_IN_SENTENCES.get(code, code.replace("_", " ").capitalize())


def format_time_of_day(value: time) -> str:
    """ "8:00 PM" from a stored reminder time."""
    hour = value.hour % 12 or 12
    meridiem = "AM" if value.hour < 12 else "PM"
    return f"{hour}:{value.minute:02d} {meridiem}"


def format_times(values: list[time]) -> str:
    """ "8:00 AM and 8:00 PM". Order as given, which is the schedule's order."""
    return shared.join_items([format_time_of_day(value) for value in values])


def format_moment(moment: datetime, timezone: str) -> str:
    """ "2 October 2026, 3:30 PM", in the appointment's own zone."""
    return shared.format_moment(moment, ZoneInfo(timezone))


def granted_summary(permissions: dict[str, bool]) -> tuple[list[str], list[str]]:
    """The two lists section 15 asks for: what they can see, and what they cannot.

    Returned as labels in the fixed order of ``CAREGIVER_PERMISSION_KEYS`` rather
    than in dictionary order, so the same permission set always reads the same
    way round.
    """
    allowed = [
        PERMISSION_LABELS[key]
        for key in CAREGIVER_PERMISSION_KEYS
        if permissions.get(key)
    ]
    denied = [
        PERMISSION_LABELS[key]
        for key in CAREGIVER_PERMISSION_KEYS
        if not permissions.get(key)
    ]
    return allowed, denied
