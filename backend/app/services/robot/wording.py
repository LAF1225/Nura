"""Every word the robot shows, in one module.

PRD 11, sections 7, 8, 9, 20, 22, 34, 35, 36, 46, 47, 75, 78, 79, 86 and 95.

Section 75 asks for reviewable robot-copy modules and warns against scattered
inline health and emergency text. This is that module, and the reason it is
worth the indirection is the same one PRD 10 found: when all the prose is in
one file, the test that checks none of it over-claims is exhaustive rather
than a spot check.

**Four rules, each with a test in ``tests/test_robot_wording.py``.**

*Nothing here says help is coming.* Section 8 names the sentence -- "Help is
on the way." -- and forbids it unless a real provider confirmed something
equivalent. No provider exists, so the emergency screen reports what PRD 10
actually did: an in-app alert record was created, calling is not configured.
The lines come from PRD 10's own status, assembled by ``emergency_lines``.

*Nothing here says a detector is watching.* Section 9 names that sentence too
-- "Fall detection active" -- and ``monitoring_lines`` cannot produce it: the
only thing it says is that Safety Monitoring is on and until when, which is
what PRD 10 knows.

*Nothing here says the robot did something it cannot do.* There is no "Nura
called", no "message read aloud", no "reminder spoken". Section 20 is explicit
that an offline robot must not be described as having displayed anything, and
``OFFLINE_NOTE`` is the sentence the app shows instead.

*Nothing here diagnoses.* Event wording is PRD 10's -- imported, not rewritten
-- so the robot cannot develop a second, looser vocabulary for the same events.
Section 28 then keeps faces out of it: a concerned face is never chosen because
a symptom was severe.

Lengths: every constant here is already inside the limits in ``layouts.py``,
and anything built from user data goes through ``layouts.shorten`` rather than
being trusted to fit (section 77).
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from app.models.enums import (
    ROBOT_CAPABILITY_KEYS,
    ROBOT_CAPABILITY_STATES,
    ROBOT_CHIME_KINDS,
    ROBOT_FACE_STATES,
    ROBOT_MEDICATION_PRIVACY_LEVELS,
    ROBOT_PRESENTATION_CANCEL_REASONS,
    ROBOT_PRESENTATION_FAILURE_CODES,
    ROBOT_PRESENTATION_MODES,
    ROBOT_PRESENTATION_STATUSES,
    ROBOT_PRESENTATION_TYPES,
    ROBOT_SLEEP_SCREEN_MODES,
)
from app.services.safety.wording import format_time

# --- what things are called --------------------------------------------------

#: The heading on each kind of card. Short, because it sits above the content
#: on a 240-pixel-wide screen, and categorical rather than descriptive: a
#: person glancing from a desk reads the first line to know what this is about.
PRESENTATION_TITLES: dict[str, str] = {
    "face_state": "Nura",
    "info_card": "Nura",
    "medication_reminder": "Medication",
    "appointment_reminder": "Appointment",
    "family_message": "Message",
    "assistant_response": "Nura",
    "safety_check": "Are you okay?",
    "safety_status": "Safety Monitoring",
    "emergency_status": "EMERGENCY MODE",
    "system_status": "Nura",
    "setup_code": "Pairing code",
    # PRD 12's four. "Task" and "Reminder" rather than "Your task" and "Don't
    # forget": a heading on a shelf display should say what kind of thing this
    # is, and nothing about a daily-life card needs urgency (PRD 12, s3, s33).
    "task_reminder": "Task",
    "general_reminder": "Reminder",
    "alarm": "Alarm",
    "routine": "Routine",
}
assert set(PRESENTATION_TITLES) == set(ROBOT_PRESENTATION_TYPES)

#: How a mode is described in the app, when the app has to name one. The robot
#: itself never shows these -- it shows the card for the mode.
MODE_LABELS: dict[str, str] = {
    "companion": "Companion",
    "information": "Showing information",
    "focus": "Focus",
    "sleep": "Sleep",
    "privacy": "Privacy",
    "safety": "Safety Monitoring",
    "emergency": "Emergency",
    "offline": "Offline",
    "setup": "Setup",
    "error": "Needs attention",
}
assert set(MODE_LABELS) == set(ROBOT_PRESENTATION_MODES)

#: Face states, for the settings screen and the simulator. Section 28 is why
#: there is no label here implying a judgement: ``concerned`` is described as
#: attentive, not worried about anybody's health.
FACE_LABELS: dict[str, str] = {
    "idle": "Resting",
    "listening": "Listening",
    "thinking": "Thinking",
    "speaking": "Speaking",
    "happy": "Pleased",
    "concerned": "Attentive",
    "sleeping": "Asleep",
    "privacy": "Privacy",
    "offline": "Offline",
}
assert set(FACE_LABELS) == set(ROBOT_FACE_STATES)

#: What each capability is, in a person's words rather than a firmware
#: engineer's (section 46).
CAPABILITY_LABELS: dict[str, str] = {
    "display": "Screen",
    "display_text": "Text on screen",
    "display_animation": "Animation",
    "speaker": "Speaker",
    "tts": "Spoken words",
    "audio_playback": "Sounds and chimes",
    "microphone": "Microphone",
    "wake_word": "Listening for its name",
    "camera": "Camera",
    "camera_detection": "Camera detection",
    "buttons": "Buttons",
    "touch": "Touch screen",
}
assert set(CAPABILITY_LABELS) == set(ROBOT_CAPABILITY_KEYS)

#: Sections 12, 47 and 91. ``Not tested yet`` is the whole point of
#: ``not_verified``: the part is wired into the build and nobody has proven it
#: does anything. It is not a promise and it is not a failure.
CAPABILITY_STATE_LABELS: dict[str, str] = {
    "available": "Working",
    "unavailable": "Not fitted",
    "not_verified": "Not tested yet",
    "not_connected": "Not reported",
}
assert set(CAPABILITY_STATE_LABELS) == set(ROBOT_CAPABILITY_STATES)

#: Section 22. The middle one exists because a tablet name on its own is often
#: harmless while the dose and the reason are not.
MEDICATION_PRIVACY_LABELS: dict[str, str] = {
    "full": "Full details",
    "name_only": "Medication name only",
    "private": "Private reminder",
}
assert set(MEDICATION_PRIVACY_LABELS) == set(ROBOT_MEDICATION_PRIVACY_LEVELS)

MEDICATION_PRIVACY_DESCRIPTIONS: dict[str, str] = {
    "full": "Name, dose and time on the screen.",
    "name_only": "The name and the time, without the dose.",
    "private": "Only that a medication is due. Open the app for the details.",
}
assert set(MEDICATION_PRIVACY_DESCRIPTIONS) == set(ROBOT_MEDICATION_PRIVACY_LEVELS)

SLEEP_SCREEN_LABELS: dict[str, str] = {
    "dim": "Dim the screen",
    "sleeping_face": "Sleeping face",
    "blank": "Blank screen",
}
assert set(SLEEP_SCREEN_LABELS) == set(ROBOT_SLEEP_SCREEN_MODES)

#: Section 81. Named so a payload can ask for one; nothing has ever played.
CHIME_LABELS: dict[str, str] = {
    "reminder": "Reminder",
    "message": "Message",
    "safety": "Safety",
    "success": "Done",
    "error": "Problem",
}
assert set(CHIME_LABELS) == set(ROBOT_CHIME_KINDS)


# --- the robot's own screens -------------------------------------------------

#: Section 34. Calm, and it does not blame the network or the person.
OFFLINE_TITLE = "Nura offline"
OFFLINE_BODY = "Trying to reconnect"

#: Section 36. A person-readable state, never a firmware error.
ERROR_TITLE = "Nura needs attention"
ERROR_WIFI = "Wi-Fi connection unavailable"
ERROR_GENERIC = "Open the Nura app to see what is wrong"

#: Section 33. The state is shown, and nothing claims a camera or microphone
#: has been switched off in hardware -- that is a thing only the device can
#: report, and no device reports it.
PRIVACY_TITLE = "Privacy"
PRIVACY_BODY = "Nura is not showing anything right now"

#: Section 31. Shown instead of a face when the sleep screen is not blank.
SLEEP_BODY = "Good night"

#: For a robot that is claimed and online but whose setup nobody finished in
#: the app. No pairing code is involved -- that is PRD 2's, and section 35
#: forbids a second mechanism for it.
SETUP_TITLE = "Almost ready"
SETUP_BODY = "Finish setting up in the Nura app"

#: Section 86: an action-heavy card on a robot with no buttons becomes a card
#: that says where the buttons are.
USE_THE_APP = "Use the Nura app to respond."

#: Sections 78 and 79.
MESSAGE_CONTINUE = "Open the Nura app to read more."
ASSISTANT_CONTINUE = "Continue in the Nura app"

#: Section 20, shown in the **app**, never on the robot: the robot is not
#: there to show it. This is the sentence that replaces any suggestion that a
#: queued card was seen.
OFFLINE_NOTE = "Robot offline — this item remains available on your phone."

#: Section 95. The app's own preview, labelled so it cannot be mistaken for
#: something the hardware did.
PREVIEW_LABEL = "Preview only"
PREVIEW_NOTE = (
    "This is how the card would look on Nura's screen. "
    "It does not mean the robot showed it."
)

#: Sections 46 and 47. Shown instead of controls that would not do anything.
NO_AUDIO_HARDWARE = "Not available on this device"
NO_DISPLAY_HARDWARE = "This Nura has not reported a screen"
NOT_TESTED_NOTE = (
    "Nura has this part in its software but has never proven it works. "
    "Settings are kept for when it does."
)

#: The sentence the whole of PRD 11 is honest about. Section 135's list, said
#: once, in the place the app reads it from.
NO_HARDWARE_NOTE = (
    "The Nura robot has not been built. Everything here is ready for it, "
    "and nothing here has run on a screen or a speaker."
)


# --- sentences built from state ----------------------------------------------


def monitoring_lines(*, ends_at: datetime | None, zone: str) -> tuple[str, ...]:
    """The subtle Safety Monitoring indicator (section 9).

    Says that monitoring is on, and until when if there is an end. It cannot
    say a detector is active, because there is no sentence here that could --
    which is section 9's requirement met by absence rather than by a check.
    """
    if ends_at is None:
        return ("ON until you turn it off",)
    return (f"ON until {format_time(ends_at, zone)}",)


def emergency_lines(
    *,
    alert_labels: tuple[str, ...],
    calling_configured: bool,
    has_contacts: bool,
) -> tuple[str, ...]:
    """What the robot says during an emergency (sections 8 and 72).

    Built from PRD 10's state: who an alert record was created for, and whether
    any calling provider exists. Deliberately not from free-form model output
    -- section 72 requires the emergency copy to be deterministic, and the
    assistant has no way to reach this function.

    The first line is the one sentence that is true of every deployment: Nura
    is dealing with the request. What follows is a record of what was actually
    done, including the parts that could not be done.
    """
    lines = ["Nura is processing your safety request."]
    if alert_labels:
        people = ", ".join(alert_labels)
        lines.append(f"In-app alert created for {people}.")
    elif has_contacts:
        lines.append("No caregiver has in-app safety alerts turned on.")
    else:
        lines.append("No emergency contacts have been added yet.")
    if not calling_configured:
        lines.append("Calling is not configured.")
    return tuple(lines)


def emergency_cancelled_lines() -> tuple[str, ...]:
    """Section 114. The robot must not be left showing a stale emergency."""
    return ("Emergency request cancelled.", "Nothing further will be sent.")


def safety_check_lines(*, name: str | None, seconds: int) -> tuple[str, ...]:
    """The on-robot version of PRD 10's check-in (sections 7 and 9).

    Serious information, so there is no face and no humour: section 7 lists a
    Safety Monitoring prompt as one of the contexts that must look serious.
    """
    who = f"{name}, are you okay?" if name else "Are you okay?"
    return (who, f"Answer in the app within {seconds} seconds.")


def acknowledgement_line(label: str) -> str:
    """Section 115, and the clause at the end of it.

    Says that somebody acknowledged the alert, which the backend knows because
    they pressed a button in their own app. It does not say anybody is coming,
    is nearby, or has left -- none of which this system can know.
    """
    return f"{label} acknowledged the safety alert."


def no_response_line(seconds: int) -> str:
    return f"No answer after {seconds} seconds."


def dose_window_line(*, due_at: datetime, zone: str) -> str:
    return format_time(due_at, zone)


def appointment_when_line(*, when: datetime, zone: str, days_away: int) -> str:
    """ "Tomorrow · 3:30 PM" (section 23)."""
    clock = format_time(when, zone)
    if days_away <= 0:
        return f"Today · {clock}"
    if days_away == 1:
        return f"Tomorrow · {clock}"
    local = when.astimezone(ZoneInfo(zone))
    return f"{local.day} {local:%b} · {clock}"


def pairing_code_body(code: str) -> str:
    """Section 35 reuses PRD 2's code; this only groups it for reading."""
    if len(code) == 6:
        return f"{code[:3]} {code[3:]}"
    return code


def capability_sentence(*, key: str, state: str) -> str:
    """One capability, as the settings screen reads it out (sections 46, 47)."""
    return f"{CAPABILITY_LABELS[key]}: {CAPABILITY_STATE_LABELS[state]}"


# --- the app's own words for a presentation's history (section 96) ----------

#: What a kind of card is called *in the app*, which is not what the card's
#: own heading says. "Medication" is a title on a 240-pixel screen; "Medication
#: reminder" is what a history row needs to read as a sentence.
PRESENTATION_KIND_LABELS: dict[str, str] = {
    "face_state": "Companion face",
    "info_card": "Information",
    "medication_reminder": "Medication reminder",
    "appointment_reminder": "Appointment reminder",
    "family_message": "Family message",
    "assistant_response": "Nura reply",
    "safety_check": "Safety check",
    "safety_status": "Safety status",
    "emergency_status": "Emergency status",
    "system_status": "System status",
    "setup_code": "Pairing code",
    "task_reminder": "Task reminder",
    "general_reminder": "Reminder",
    "alarm": "Alarm",
    "routine": "Routine",
}
assert set(PRESENTATION_KIND_LABELS) == set(ROBOT_PRESENTATION_TYPES)

#: Section 14's statuses in a person's words. ``sent`` is deliberately "sent to
#: Nura" rather than "shown": the whole of section 14 is that those are not the
#: same thing, and the label is where somebody would otherwise blur them.
PRESENTATION_STATUS_LABELS: dict[str, str] = {
    "queued": "waiting",
    "sent": "sent to Nura",
    "acknowledged": "received by Nura",
    "displayed": "on screen",
    "completed": "shown",
    "expired": "expired",
    "failed": "could not be shown",
    "cancelled": "withdrawn",
    "not_supported": "not supported on this Nura",
}
assert set(PRESENTATION_STATUS_LABELS) == set(ROBOT_PRESENTATION_STATUSES)

#: Why something could not be shown. Stable codes become plain sentences here
#: and nowhere else, so a firmware code never reaches a screen (section 36).
FAILURE_LABELS: dict[str, str] = {
    "render_failed": "Nura could not draw it",
    "unsupported_layout": "Nura does not know this layout",
    "unsupported_capability": "this Nura does not have the hardware",
    "unsupported_protocol_version": "Nura needs a firmware update",
    "no_display": "this Nura has not reported a screen",
    "device_error": "Nura reported a problem",
}
assert set(FAILURE_LABELS) == set(ROBOT_PRESENTATION_FAILURE_CODES)

#: Why something was withdrawn.
CANCEL_REASON_LABELS: dict[str, str] = {
    "preempted": "something more urgent took the screen",
    "source_resolved": "it was no longer needed",
    "source_cancelled": "what it was about was cancelled",
    "superseded": "replaced by a newer one",
    "preference_changed": "a setting changed",
    "capability_withdrawn": "Nura stopped reporting the hardware",
    "device_unlinked": "the robot was unlinked",
}
assert set(CANCEL_REASON_LABELS) == set(ROBOT_PRESENTATION_CANCEL_REASONS)


def history_line(
    *,
    presentation_type: str,
    status: str,
    failure_code: str | None = None,
    cancel_reason: str | None = None,
) -> str:
    """One row of section 96's history, as a sentence.

    Assembled on the server for the reason PRD 10 assembles its escalation
    lines there: a client that built "Medication reminder — shown" from a type
    and a status would be a second place that could decide ``sent`` means
    shown.
    """
    kind = PRESENTATION_KIND_LABELS[presentation_type]
    state = PRESENTATION_STATUS_LABELS[status]
    if status in {"failed", "not_supported"} and failure_code:
        return f"{kind} — {state}: {FAILURE_LABELS[failure_code]}"
    if status == "cancelled" and cancel_reason:
        return f"{kind} — {state}: {CANCEL_REASON_LABELS[cancel_reason]}"
    return f"{kind} — {state}"


def summary_of(payload: dict[str, object]) -> tuple[str | None, str | None]:
    """A title and one line from a stored payload, for the app's history.

    Reads the payload the robot was sent, which the builder already reduced to
    the privacy level in force (section 22). So a reminder stored as "Reminder
    due" reads back as "Reminder due", and there is no path by which the
    history shows a medication name the robot never received.
    """
    title = payload.get("title")
    for key in ("primary", "body", "value"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return (title if isinstance(title, str) else None), value
    lines = payload.get("lines")
    if isinstance(lines, list) and lines and isinstance(lines[0], str):
        return (title if isinstance(title, str) else None), lines[0]
    face = payload.get("face_state")
    if isinstance(face, str):
        return (title if isinstance(title, str) else None), FACE_LABELS.get(face)
    return (title if isinstance(title, str) else None), None
