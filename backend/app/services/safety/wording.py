"""Every sentence the safety features say, in one module.

PRD 10, sections 3, 16, 23, 37, 38, 42, 51, 52, 66, 72, 73, 74 and 120.

Section 120 asks for this explicitly, and names the reason: it is the same
discipline that caught three inline sentences during PRD 9's copy audit. When
one file writes all the prose, the test that checks none of it diagnoses
anything is exhaustive rather than a spot check.

**Three rules, and a test for each.**

*Nothing here states a medical cause.* Section 52 lists the words that are
forbidden -- "seizure detected", "fall confirmed", "unconscious" -- and a test
reads every string in this module and asserts none of them appears. What is
allowed is what was observed: "a possible fall", "no response after 45
seconds".

*Nothing here claims a delivery that did not happen.* Section 38 is explicit
that "Caregiver notified" is the wrong sentence when there is no push provider,
and section 42 that "Ayesha has been contacted" is wrong unless somebody was.
Every sentence below reports a *record* -- an alert was created, calling is not
configured -- and a test asserts no sentence contains "notified", "contacted",
"called" or "delivered" as a completed act.

*Nothing here promises protection.* Section 72 forbids any guarantee of
emergency response. The warnings in sections 73 and 74 are written here in
full, because a warning assembled from fragments at a call site is a warning
somebody will eventually reassemble wrongly.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from app.models.enums import (
    SAFETY_CAPABILITY_KEYS,
    SAFETY_CAPABILITY_STATES,
    SAFETY_ESCALATION_ATTEMPT_STATUSES,
    SAFETY_ESCALATION_CHANNELS,
    SAFETY_ESCALATION_OUTCOMES,
    SAFETY_EVENT_RESOLUTIONS,
    SAFETY_EVENT_TYPES,
    SAFETY_FALSE_POSITIVE_REASONS,
    SAFETY_MONITORING_DURATION_MODES,
)

#: What happened, in words that describe rather than diagnose (sections 16, 51
#: and 52). Every one of the sensor-observed types keeps the word "possible",
#: because that is the only honest thing a system with no clinical validation
#: can say -- and because section 52 names the alternatives and forbids them.
EVENT_TYPE_LABELS: dict[str, str] = {
    "manual_sos": "Emergency request",
    "possible_fall": "Possible fall",
    "possible_prolonged_immobility": "Possible prolonged immobility",
    "possible_vomiting": "Possible vomiting",
    "possible_seizure_like_activity": "Possible seizure-like activity",
    "possible_distress": "Possible distress",
    "call_for_help": "Call for help",
    "test_event": "Test event",
}
assert set(EVENT_TYPE_LABELS) == set(SAFETY_EVENT_TYPES)

#: A longer line for the event detail screen (section 51). Still an
#: observation, never a conclusion: "Nura noticed" and "you asked", not "Nura
#: determined".
EVENT_TYPE_DESCRIPTIONS: dict[str, str] = {
    "manual_sos": "You asked Nura for help.",
    "possible_fall": "Something was observed that may have been a fall.",
    "possible_prolonged_immobility": (
        "Something was observed that may have been a long period without movement."
    ),
    "possible_vomiting": "Something was observed that may have been vomiting.",
    "possible_seizure_like_activity": (
        "Something was observed that may have been seizure-like activity."
    ),
    "possible_distress": "Something unusual was observed.",
    "call_for_help": "You asked for help out loud.",
    "test_event": "A test, raised to check that this works.",
}
assert set(EVENT_TYPE_DESCRIPTIONS) == set(SAFETY_EVENT_TYPES)

#: How long monitoring was asked for (section 5).
DURATION_LABELS: dict[str, str] = {
    "30_minutes": "30 minutes",
    "1_hour": "1 hour",
    "until_bedtime": "Until bedtime",
    "until_turned_off": "Until turned off",
    "custom": "A set time",
}
assert set(DURATION_LABELS) == set(SAFETY_MONITORING_DURATION_MODES)

#: How an event ended (section 46). ``resolved_after_contact`` reads the way it
#: does because nothing automatic may ever set it: a person established that
#: somebody was all right, and no code in this system can know that.
RESOLUTION_LABELS: dict[str, str] = {
    "user_confirmed_ok": "You said you were okay",
    "help_requested": "You asked for help",
    "no_response_escalated": "No response, so escalation started",
    "false_alarm": "Marked as a false alarm",
    "cancelled_by_user": "Cancelled",
    "resolved_after_contact": "Resolved after someone checked in",
    "test_event": "Test event",
    "system_error": "Ended because something went wrong",
}
assert set(RESOLUTION_LABELS) == set(SAFETY_EVENT_RESOLUTIONS)

#: How the whole escalation went (section 41). Read these next to section 42's
#: bad example -- "Ayesha has been contacted" -- and the difference is the
#: point: every one of these describes what Nura *did*, not what reached
#: anybody.
OUTCOME_LABELS: dict[str, str] = {
    "complete": "Every step Nura could take was taken",
    "partial": "Some steps were taken and some are not available",
    "failed": "Nura could not complete any step",
    "no_contacts": "There was nobody to reach",
    "providers_not_configured": "No way of reaching anyone is set up",
    "cancelled": "Cancelled before it finished",
}
assert set(OUTCOME_LABELS) == set(SAFETY_ESCALATION_OUTCOMES)

#: What each channel is, in the app's words.
CHANNEL_LABELS: dict[str, str] = {
    "in_app": "In-app alert",
    "push": "Push notification",
    "sms_future": "Text message",
    "voice_call_future": "Phone call",
}
assert set(CHANNEL_LABELS) == set(SAFETY_ESCALATION_CHANNELS)

#: What one attempt came to. ``attempted`` says what was done and stops there,
#: because section 38 says an alert record is not proof anybody saw it.
ATTEMPT_STATUS_LABELS: dict[str, str] = {
    "pending": "Not started",
    "attempted": "Alert created",
    "delivered": "Confirmed by the provider",
    "failed": "Did not go through",
    "skipped": "Skipped",
    "not_configured": "Not set up in this build",
}
assert set(ATTEMPT_STATUS_LABELS) == set(SAFETY_ESCALATION_ATTEMPT_STATUSES)

#: The capability names the app shows (sections 64 and 106).
CAPABILITY_LABELS: dict[str, str] = {
    "manual_sos": "Emergency request",
    "in_app_safety_checks": "Safety check-in prompts",
    "caregiver_in_app_alerts": "In-app alerts for caregivers",
    "push_delivery": "Push notifications",
    "sms_delivery": "Text messages",
    "audio_calling": "Audio calling",
    "robot_detection": "Automatic detection by the robot",
}
assert set(CAPABILITY_LABELS) == set(SAFETY_CAPABILITY_KEYS)

#: What each capability state means, said plainly. "Not set up in this build"
#: rather than "unavailable": a person reading this should learn whether the
#: thing could ever work, not merely that it does not right now.
CAPABILITY_STATE_LABELS: dict[str, str] = {
    "available": "Available",
    "not_configured": "Not set up in this build",
    "not_connected": "Not connected yet",
    "unavailable": "Not available",
}
assert set(CAPABILITY_STATE_LABELS) == set(SAFETY_CAPABILITY_STATES)

#: Why it was a false alarm (section 47).
FALSE_POSITIVE_LABELS: dict[str, str] = {
    "normal_movement": "Normal movement",
    "sensor_error": "Something was misread",
    "user_testing": "I was testing it",
    "other": "Something else",
}
assert set(FALSE_POSITIVE_LABELS) == set(SAFETY_FALSE_POSITIVE_REASONS)

# --- the standing warnings ---------------------------------------------------

#: Section 66, shown whenever monitoring is on. The honest version of what is
#: running: Nura will prompt and record, and nothing is watching automatically.
#: A screen that said "Fall detection active" with no detector behind it is the
#: exact thing section 66 forbids.
MONITORING_WITHOUT_DETECTION = (
    "Safety Monitoring is on. Automatic detection by the robot is not connected "
    "yet, so Nura will not notice anything by itself. You can still ask for help "
    "at any time."
)

#: Section 73, shown before monitoring starts when the chain is empty.
NO_EMERGENCY_CONTACTS = (
    "No emergency contacts are set up. Nura can still check on you and record "
    "what happened, but it has nobody to reach."
)

#: Section 74, and it must be explicit. This is the sentence that stops somebody
#: relying on this build as a safety system.
NO_DELIVERY_PROVIDERS = (
    "External notifications and calling are not set up in this build. Nura can "
    "record what happened and show it in the app, but it cannot reach anybody "
    "for you."
)

#: Section 67, when the phone cannot reach the backend.
OFFLINE_WARNING = (
    "Nura cannot reach the server right now, so it cannot start or record an "
    "emergency request. Use your phone to call someone directly."
)

#: Section 70, when the backend answers but something is wrong with it.
DEGRADED_WARNING = (
    "Nura is having trouble reaching the server. Safety Monitoring may not work "
    "until the connection comes back."
)

#: Section 68. Said next to a contact's number, so nobody reads tapping it as
#: Nura placing the call.
DIALER_NOTE = "This opens your phone's dialler. Nura does not place the call."

#: Section 123's future push copy, written now so there is one place to change
#: when there is a provider. Deliberately says nothing: a lock screen is not an
#: authenticated surface, and the event detail is behind the app.
PUSH_TITLE = "Nura safety alert"
PUSH_BODY = "Please open Nura to review."


def check_in_prompt(name: str | None = None) -> str:
    """Section 23's question. Cautious, short, and not an accusation.

    The name is used when there is one because "Ayesha, are you okay?" reads
    like a person asking, and a prompt somebody must answer in 45 seconds
    should sound like one.
    """
    opening = "Nura noticed something unusual."
    question = f"{name}, are you okay?" if name else "Are you okay?"
    return f"{opening} {question}"


def caregiver_alert_sentence(
    *, event_type: str, when: datetime, zone: str, no_response_seconds: int | None
) -> str:
    """What a caregiver's in-app alert says (section 37).

    One observed fact, one time, and one request. No medical claim, no health
    data, and no instruction beyond "please check on them" -- section 85 is
    clear that a caregiver alert must not expose unrelated health information,
    and the surest way is for this function to be given none.
    """
    label = EVENT_TYPE_LABELS[event_type].lower()
    moment = format_moment(when, zone)
    if no_response_seconds is None:
        return f"Nura recorded {label} at {moment}. Please check on them."
    return (
        f"Nura recorded {label} at {moment} and did not get a response after "
        f"{no_response_seconds} seconds. Please check on them."
    )


def escalation_line(*, label: str, channel: str, status: str) -> str:
    """One line of section 42's escalation list.

    "In-app alert created for Ayesha." / "Phone call: not set up in this build."
    Facts, in that order, and never a claim that the person has been reached.
    """
    if status == "attempted" and channel == "in_app":
        return f"In-app alert created for {label}."
    if status == "not_configured":
        return f"{CHANNEL_LABELS[channel]} for {label}: not set up in this build."
    if status == "delivered":
        return f"{CHANNEL_LABELS[channel]} for {label}: confirmed by the provider."
    if status == "failed":
        return f"{CHANNEL_LABELS[channel]} for {label}: did not go through."
    if status == "skipped":
        return f"{CHANNEL_LABELS[channel]} for {label}: skipped."
    return f"{CHANNEL_LABELS[channel]} for {label}: not started."


def monitoring_sentence(*, active: bool, ends_at: datetime | None, zone: str) -> str:
    """Section 4's status line. "OFF", or "ON until 10:30 PM"."""
    if not active:
        return "Safety Monitoring is off."
    if ends_at is None:
        return "Safety Monitoring is on until you turn it off."
    return f"Safety Monitoring is on until {format_time(ends_at, zone)}."


def no_response_sentence(seconds: int) -> str:
    """Section 51's response line. A fact about silence, not about a person."""
    return f"No response after {seconds} seconds."


def format_time(value: datetime, zone: str) -> str:
    """A wall-clock time in the given zone, as "10:30 PM".

    Rendered here rather than in the app for the PRD 7 reason: Hermes has no
    time-zone database, and a safety screen is the last place to find that out.
    """
    local = value.astimezone(ZoneInfo(zone))
    hour = local.hour % 12 or 12
    suffix = "AM" if local.hour < 12 else "PM"
    return f"{hour}:{local.minute:02d} {suffix}"


def format_moment(value: datetime, zone: str) -> str:
    """A date and time, as "2 Oct, 6:42 PM"."""
    local = value.astimezone(ZoneInfo(zone))
    return f"{local.day} {local:%b}, {format_time(value, zone)}"
