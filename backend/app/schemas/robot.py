"""Robot capability, preference and presentation models.

PRD 11, sections 10, 11, 14, 19, 38, 48, 60, 61, 69, 96, 116 and 122.

Four things a reader should check for and find.

**No device request carries a device id, a profile id or an account id.** The
device's identity comes from its token and the profile comes from the device
record. Section 69 requires a valid device token, a claimed device and a
matching linked profile; the way to be sure the body cannot override any of
that is that there is nowhere in these models to put one -- the same discipline
PRD 10 applied to its device trigger.

**No request carries a layout or a payload.** A device reports what it did; it
does not propose what to show. The only thing an acknowledgement can say is one
of five states and an optional stable failure code, both from closed sets.
Sections 14 and 19, and section 71 for the assistant's side of the same rule.

**No capability can be reported as a free-form string.** ``CapabilityState``
is four values and ``CapabilityKey`` is twelve, with drift guards against the
tuples the database constrains. A firmware that invents a thirteenth gets a
422 rather than a row.

**No presentation response carries more than the robot was sent.** The history
model returns the layout, the status, the timestamps and the payload's own
title and summary -- which are already privacy-filtered, because the builder
filtered them before storing the row (section 22). There is no field here that
could reveal a medication name the robot itself was not shown.
"""

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import (
    ROBOT_ACK_STATES,
    ROBOT_CAPABILITY_KEYS,
    ROBOT_CAPABILITY_SOURCES,
    ROBOT_CAPABILITY_STATES,
    ROBOT_MEDICATION_PRIVACY_LEVELS,
    ROBOT_PRESENTATION_CANCEL_REASONS,
    ROBOT_PRESENTATION_FAILURE_CODES,
    ROBOT_PRESENTATION_LAYOUTS,
    ROBOT_PRESENTATION_MODES,
    ROBOT_PRESENTATION_SOURCES,
    ROBOT_PRESENTATION_STATUSES,
    ROBOT_PRESENTATION_TYPES,
    ROBOT_SLEEP_SCREEN_MODES,
)

CapabilityKey = Literal[
    "display",
    "display_text",
    "display_animation",
    "speaker",
    "tts",
    "audio_playback",
    "microphone",
    "wake_word",
    "camera",
    "camera_detection",
    "buttons",
    "touch",
]
assert set(ROBOT_CAPABILITY_KEYS) == set(CapabilityKey.__args__)  # type: ignore[attr-defined]

CapabilityState = Literal["available", "unavailable", "not_verified", "not_connected"]
assert set(ROBOT_CAPABILITY_STATES) == set(CapabilityState.__args__)  # type: ignore[attr-defined]

CapabilitySource = Literal["device_report", "self_test", "default"]
assert set(ROBOT_CAPABILITY_SOURCES) == set(CapabilitySource.__args__)  # type: ignore[attr-defined]

PresentationType = Literal[
    "face_state",
    "info_card",
    "medication_reminder",
    "appointment_reminder",
    "family_message",
    "assistant_response",
    "safety_check",
    "safety_status",
    "emergency_status",
    "system_status",
    "setup_code",
    # PRD 12, section 30: through the same queue, not a second transport.
    "task_reminder",
    "general_reminder",
    "alarm",
    "routine",
]
assert set(ROBOT_PRESENTATION_TYPES) == set(PresentationType.__args__)  # type: ignore[attr-defined]

PresentationStatus = Literal[
    "queued",
    "sent",
    "acknowledged",
    "displayed",
    "completed",
    "expired",
    "failed",
    "cancelled",
    "not_supported",
]
assert set(ROBOT_PRESENTATION_STATUSES) == set(PresentationStatus.__args__)  # type: ignore[attr-defined]

PresentationLayout = Literal[
    "FACE",
    "TITLE_BODY",
    "TITLE_VALUE",
    "REMINDER",
    "MESSAGE",
    "STATUS",
    "EMERGENCY",
    "PAIRING_CODE",
]
assert set(ROBOT_PRESENTATION_LAYOUTS) == set(PresentationLayout.__args__)  # type: ignore[attr-defined]

PresentationSource = Literal[
    "medication",
    "appointment",
    "family_message",
    "assistant",
    "safety",
    "system",
    "user",
    # PRD 12. One source for all four of its card types: the distinction this
    # field draws is which part of the product asked, and tasks, reminders,
    # alarms and routines are one part.
    "daily_life",
]
assert set(ROBOT_PRESENTATION_SOURCES) == set(PresentationSource.__args__)  # type: ignore[attr-defined]

#: What a device may say happened (section 19). This is the whole vocabulary a
#: device has for reporting on a presentation, and it is five words.
AckState = Literal[
    "received", "render_started", "render_completed", "failed", "unsupported"
]
assert set(ROBOT_ACK_STATES) == set(AckState.__args__)  # type: ignore[attr-defined]

FailureCode = Literal[
    "render_failed",
    "unsupported_layout",
    "unsupported_capability",
    "unsupported_protocol_version",
    "no_display",
    "device_error",
]
assert set(ROBOT_PRESENTATION_FAILURE_CODES) == set(FailureCode.__args__)  # type: ignore[attr-defined]

CancelReason = Literal[
    "preempted",
    "source_resolved",
    "source_cancelled",
    "superseded",
    "preference_changed",
    "capability_withdrawn",
    "device_unlinked",
]
assert set(ROBOT_PRESENTATION_CANCEL_REASONS) == set(CancelReason.__args__)  # type: ignore[attr-defined]

PresentationMode = Literal[
    "companion",
    "information",
    "focus",
    "sleep",
    "privacy",
    "safety",
    "emergency",
    "offline",
    "setup",
    "error",
]
assert set(ROBOT_PRESENTATION_MODES) == set(PresentationMode.__args__)  # type: ignore[attr-defined]

MedicationPrivacyLevel = Literal["full", "name_only", "private"]
assert set(ROBOT_MEDICATION_PRIVACY_LEVELS) == set(MedicationPrivacyLevel.__args__)  # type: ignore[attr-defined]

SleepScreenMode = Literal["dim", "sleeping_face", "blank"]
assert set(ROBOT_SLEEP_SCREEN_MODES) == set(SleepScreenMode.__args__)  # type: ignore[attr-defined]

Level = Annotated[int, Field(ge=0, le=100)]


# --- capabilities (sections 10, 11, 61 and 122) ------------------------------


class CapabilityRead(BaseModel):
    """One capability, both states, and the words for them.

    ``state`` is what the app must act on and ``reported_state`` is what the
    device said. They differ when ``stale`` is true -- section 124's case --
    and both are returned because a settings screen needs the first and a
    developer needs the second.

    The labels travel with the values for the reason PRD 10's do: section 47
    makes the UI a function of the backend's answer, and a screen that wrote
    its own word for ``not_verified`` would eventually write a kinder one.
    """

    key: CapabilityKey
    state: CapabilityState
    reported_state: CapabilityState
    label: str
    state_label: str
    source: CapabilitySource
    reported_at: datetime | None
    firmware_version: str | None
    stale: bool


class CapabilitiesRead(BaseModel):
    """Every capability, plus what follows from them (sections 10 and 47)."""

    device_id: uuid.UUID
    capabilities: list[CapabilityRead]
    #: Derived, so a screen cannot decide for itself that audio is available.
    display_available: bool
    text_available: bool
    animation_available: bool
    audio_available: bool
    speech_available: bool
    input_available: bool
    #: Section 135's sentence, sent from the server so it is written once.
    hardware_note: str


class DeviceCapabilityReport(BaseModel):
    """What a robot reports about itself (section 61).

    No device id and no profile id: both come from the token. A partial report
    is valid and does not erase anything it leaves out -- a robot that has just
    finished a display self-test says so without making a claim about its
    microphone.
    """

    model_config = ConfigDict(extra="forbid")

    capabilities: dict[CapabilityKey, CapabilityState]
    #: ``self_test`` when this is a startup check's result (section 92),
    #: ``device_report`` otherwise. ``default`` is not accepted: that value
    #: means "nobody has said", and a device saying it would be a contradiction.
    source: Literal["device_report", "self_test"] = "device_report"
    firmware_version: str | None = Field(default=None, max_length=32)


# --- preferences (sections 48 and 122) ---------------------------------------


class PresentationPreferencesRead(BaseModel):
    """How this robot is set up, and how that resolves (section 48)."""

    device_id: uuid.UUID
    brightness: Level
    volume: Level
    #: Null means "follow my accessibility setting" (sections 30 and 105).
    reduced_motion: bool | None
    #: What that resolves to right now, so the screen can show the effect of a
    #: null without reimplementing the rule.
    effective_reduced_motion: bool
    medication_privacy_level: MedicationPrivacyLevel
    read_medications_aloud: bool
    read_messages_aloud: bool
    read_assistant_aloud: bool
    sleep_screen_mode: SleepScreenMode
    face_animation_enabled: bool
    family_message_display_enabled: bool
    #: How much of a task, reminder or routine the robot may show
    #: (PRD 12, section 32). Defaults to ``full``, unlike the medication
    #: preview -- see ``services.robot.preferences.DEFAULTS``.
    daily_life_privacy_level: MedicationPrivacyLevel
    #: Off means no task, reminder, alarm or routine card is ever queued, and
    #: every one of them still works on the phone (PRD 12, section 31).
    daily_life_display_enabled: bool
    updated_at: datetime


class PresentationPreferencesUpdate(BaseModel):
    """A partial change. Every field optional, nothing inferred.

    ``reduced_motion`` can be set to null to go back to following the
    account's accessibility preference, which is why it is typed
    ``bool | None`` rather than omitted-means-unchanged -- and why the route
    inspects ``model_fields_set`` rather than filtering out nulls.
    """

    model_config = ConfigDict(extra="forbid")

    brightness: Level | None = None
    volume: Level | None = None
    reduced_motion: bool | None = None
    medication_privacy_level: MedicationPrivacyLevel | None = None
    read_medications_aloud: bool | None = None
    read_messages_aloud: bool | None = None
    read_assistant_aloud: bool | None = None
    sleep_screen_mode: SleepScreenMode | None = None
    face_animation_enabled: bool | None = None
    family_message_display_enabled: bool | None = None
    daily_life_privacy_level: MedicationPrivacyLevel | None = None
    daily_life_display_enabled: bool | None = None


# --- presentations (sections 60, 96 and 122) ---------------------------------


class PresentationRead(BaseModel):
    """One presentation as the app sees it (section 96).

    ``title`` and ``summary`` come from the stored payload, which the builder
    already filtered to the privacy level in force when it was built. A robot
    that was sent "Reminder due" has a history row that says "Reminder due";
    there is no path by which the app can read back more than the robot got.
    """

    id: uuid.UUID
    presentation_type: PresentationType
    status: PresentationStatus
    layout: PresentationLayout
    source: PresentationSource
    priority: int
    title: str | None
    summary: str | None
    sensitive: bool
    created_at: datetime
    available_at: datetime
    expires_at: datetime | None
    sent_at: datetime | None
    displayed_at: datetime | None
    completed_at: datetime | None
    ack_state: AckState | None
    failure_code: FailureCode | None
    cancel_reason: CancelReason | None
    #: The rendered sentence for this row's state, so a history screen does not
    #: assemble "Medication reminder — expired" itself.
    line: str


class PresentationHistoryRead(BaseModel):
    presentations: list[PresentationRead]


class RobotStatusRead(BaseModel):
    """Everything the Nura Device screen needs in one request (section 46)."""

    device_id: uuid.UUID
    display_name: str
    connection_status: Literal["unknown", "online", "offline"]
    last_seen_at: datetime | None
    #: Derived on every read and never stored (section 4).
    mode: PresentationMode
    mode_label: str
    face: str | None
    #: What is queued but not yet shown (section 65).
    queue_depth: int
    #: The presentation the robot is on, if the robot said it drew one. Null
    #: when nothing has been acknowledged, which is every deployment today.
    current: PresentationRead | None
    setup_complete: bool
    #: Section 20's sentence, for a robot that is not online.
    offline_note: str | None


# --- the device side (sections 59, 60 and 122) -------------------------------


class PresentationEnvelopeRead(BaseModel):
    """What a device is handed (sections 38 and 116).

    Typed loosely on purpose: ``payload`` and ``settings`` are built and
    validated by ``services.robot.layouts``, which is the one place that
    decides what a layout may contain. Re-declaring the shape here would be a
    second definition to keep in step, and the firmware reads the protocol
    document rather than this model.
    """

    protocol_version: int
    presentation_id: uuid.UUID
    type: PresentationType
    priority: int
    mode: PresentationMode
    layout: PresentationLayout
    payload: dict[str, Any]
    settings: dict[str, Any]
    expires_at: datetime | None = None


class PresentationAcknowledgement(BaseModel):
    """What a device says happened (sections 19 and 60).

    Two fields, both from closed sets, and no presentation id: the id is in
    the path. A device cannot acknowledge a presentation belonging to another
    robot, because the lookup is by device and id together.
    """

    model_config = ConfigDict(extra="forbid")

    state: AckState
    #: Optional, and only meaningful for ``failed`` and ``unsupported``. A
    #: device that does not say gets the default for its state -- never a
    #: free-text reason, which section 67 rules out.
    failure_code: FailureCode | None = None


class PresentationAckRead(BaseModel):
    presentation_id: uuid.UUID
    status: PresentationStatus
    #: True when this acknowledgement changed anything. A repeated
    #: acknowledgement is accepted and reports false, which is what lets a
    #: device retry a lost response safely (section 18).
    applied: bool


class DeviceCapabilityReportRead(BaseModel):
    """The device's own report, read back (section 61)."""

    device_id: uuid.UUID
    accepted: int
    capabilities: dict[str, CapabilityState]
