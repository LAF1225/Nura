"""Safety monitoring, SOS, escalation and caregiver-alert models.

PRD 10, sections 10, 12, 16, 17, 19, 20, 50, 57, 64, 85, 105 and 106.

Five things a reader should check for and find.

**No request carries a profile id, an account id or a session id in its body.**
Every one of those comes from the path or from the verified token. Section 105
says never to trust profile identity from a request body, and the way to be
sure is that there is nowhere in these models to put one -- including on the
device-trigger model, where it would be most tempting.

**No request names an event type the sender may not raise.** ``SosEventType``
is two values, not eight: an app can raise a manual SOS or a call for help and
nothing else. ``DeviceEventType`` is the ``possible_*`` set plus ``test_event``
-- a device may observe, and section 57 is satisfied by the *absence* of a
field rather than by a check, because the assistant's tools take no event type
at all.

**No response carries a diagnosis.** Event types are returned as their stored
codes and the labels come from ``services.safety.wording``, which is the one
module a reviewer has to read to be sure nothing says "seizure detected"
(section 52).

**No caregiver-facing model carries health data** (sections 50 and 85).
``SafetyAlertRead`` has an event type, two timestamps and an outcome. It has no
symptom, no medication, no note, and no emergency-contact name -- a caregiver
is not shown who else is in the chain.

**No model carries a phone number into a log or a snapshot.** The escalation
read models carry a label, because section 42's display needs a name; nothing
carries the number that label belongs to.
"""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import (
    SAFETY_CAPABILITY_KEYS,
    SAFETY_CAPABILITY_STATES,
    SAFETY_ESCALATION_ATTEMPT_STATUSES,
    SAFETY_ESCALATION_CHANNELS,
    SAFETY_ESCALATION_OUTCOMES,
    SAFETY_EVENT_RESOLUTIONS,
    SAFETY_EVENT_STATUSES,
    SAFETY_EVENT_TYPES,
    SAFETY_EVENT_TYPES_FROM_USER,
    SAFETY_EVENT_TYPES_REQUIRING_MONITORING,
    SAFETY_FALSE_POSITIVE_REASONS,
    SAFETY_MONITORING_DURATION_MODES,
    SAFETY_MONITORING_END_REASONS,
    SAFETY_MONITORING_STATUSES,
    SAFETY_RESPONSE_TIMEOUT_SECONDS,
    SAFETY_TRIGGER_SOURCES_ALLOWED,
    SAFETY_USER_RESPONSES,
)
from app.models.safety import IDEMPOTENCY_KEY_MAX_LENGTH, TIMEZONE_MAX_LENGTH
from app.services.safety.monitoring import MAX_CUSTOM_MINUTES, MIN_CUSTOM_MINUTES

MonitoringStatus = Literal["active", "ended", "cancelled", "expired", "error"]
DurationMode = Literal[
    "30_minutes", "1_hour", "until_bedtime", "until_turned_off", "custom"
]
EndReason = Literal["stopped_by_user", "duration_reached", "superseded", "system_error"]
ResponseTimeout = Literal[15, 30, 45, 60, 90]
SafetyEventType = Literal[
    "manual_sos",
    "possible_fall",
    "possible_prolonged_immobility",
    "possible_vomiting",
    "possible_seizure_like_activity",
    "possible_distress",
    "call_for_help",
    "test_event",
]
#: What an app may raise (sections 12 and 14). Two values, and that is the
#: whole enforcement: a client cannot post a ``possible_fall``, because the
#: schema has no such value to accept.
SosEventType = Literal["manual_sos", "call_for_help"]
#: What a device may report (sections 16, 19 and 20). The observed set plus
#: the harness's ``test_event``; never ``manual_sos``, which is a person's act.
DeviceEventType = Literal[
    "possible_fall",
    "possible_prolonged_immobility",
    "possible_vomiting",
    "possible_seizure_like_activity",
    "possible_distress",
    "test_event",
]
TriggerSource = Literal["mobile_manual", "developer_simulation"]
SafetyEventStatus = Literal[
    "checking_user", "second_prompt", "escalating", "escalated", "resolved", "cancelled"
]
UserResponse = Literal["im_okay", "need_help", "false_alarm"]
EventResolution = Literal[
    "user_confirmed_ok",
    "help_requested",
    "no_response_escalated",
    "false_alarm",
    "cancelled_by_user",
    "resolved_after_contact",
    "test_event",
    "system_error",
]
FalsePositiveReason = Literal["normal_movement", "sensor_error", "user_testing", "other"]
EscalationChannel = Literal["in_app", "push", "sms_future", "voice_call_future"]
EscalationAttemptStatus = Literal[
    "pending", "attempted", "delivered", "failed", "skipped", "not_configured"
]
EscalationOutcome = Literal[
    "complete",
    "partial",
    "failed",
    "no_contacts",
    "providers_not_configured",
    "cancelled",
]
CapabilityKey = Literal[
    "manual_sos",
    "in_app_safety_checks",
    "caregiver_in_app_alerts",
    "push_delivery",
    "sms_delivery",
    "audio_calling",
    "robot_detection",
]
CapabilityState = Literal["available", "not_configured", "not_connected", "unavailable"]

# The same guard as everywhere else: a Literal that drifts from the tuple the
# database CHECK constraints are built from is a startup failure, not a request
# Postgres rejects at three in the morning.
assert set(SAFETY_MONITORING_STATUSES) == set(MonitoringStatus.__args__)  # type: ignore[attr-defined]
assert set(SAFETY_MONITORING_DURATION_MODES) == set(DurationMode.__args__)  # type: ignore[attr-defined]
assert set(SAFETY_MONITORING_END_REASONS) == set(EndReason.__args__)  # type: ignore[attr-defined]
assert set(SAFETY_RESPONSE_TIMEOUT_SECONDS) == set(ResponseTimeout.__args__)  # type: ignore[attr-defined]
assert set(SAFETY_EVENT_TYPES) == set(SafetyEventType.__args__)  # type: ignore[attr-defined]
assert set(SAFETY_EVENT_TYPES_FROM_USER) == set(SosEventType.__args__)  # type: ignore[attr-defined]
assert set(SAFETY_EVENT_TYPES_REQUIRING_MONITORING) | {"test_event"} == set(
    DeviceEventType.__args__  # type: ignore[attr-defined]
)
assert set(SAFETY_TRIGGER_SOURCES_ALLOWED) == set(TriggerSource.__args__)  # type: ignore[attr-defined]
assert set(SAFETY_EVENT_STATUSES) == set(SafetyEventStatus.__args__)  # type: ignore[attr-defined]
assert set(SAFETY_USER_RESPONSES) == set(UserResponse.__args__)  # type: ignore[attr-defined]
assert set(SAFETY_EVENT_RESOLUTIONS) == set(EventResolution.__args__)  # type: ignore[attr-defined]
assert set(SAFETY_FALSE_POSITIVE_REASONS) == set(FalsePositiveReason.__args__)  # type: ignore[attr-defined]
assert set(SAFETY_ESCALATION_CHANNELS) == set(EscalationChannel.__args__)  # type: ignore[attr-defined]
assert set(SAFETY_ESCALATION_ATTEMPT_STATUSES) == set(EscalationAttemptStatus.__args__)  # type: ignore[attr-defined]
assert set(SAFETY_ESCALATION_OUTCOMES) == set(EscalationOutcome.__args__)  # type: ignore[attr-defined]
assert set(SAFETY_CAPABILITY_KEYS) == set(CapabilityKey.__args__)  # type: ignore[attr-defined]
assert set(SAFETY_CAPABILITY_STATES) == set(CapabilityState.__args__)  # type: ignore[attr-defined]

TimezoneName = Annotated[str, Field(min_length=1, max_length=TIMEZONE_MAX_LENGTH)]
IdempotencyKey = Annotated[
    str, Field(min_length=1, max_length=IDEMPOTENCY_KEY_MAX_LENGTH)
]
CustomMinutes = Annotated[int, Field(ge=MIN_CUSTOM_MINUTES, le=MAX_CUSTOM_MINUTES)]


# --- monitoring --------------------------------------------------------------


class MonitoringStart(BaseModel):
    """Start watching over somebody (sections 5, 7 and 8).

    ``ends_at`` is deliberately absent. A client sends the *mode* and the
    server works out the instant, which is what makes section 61's "do not
    silently extend" a property of one function rather than a promise about
    every caller -- and what stops a phone with a wrong clock from arranging to
    be monitored for a week.
    """

    duration_mode: DurationMode
    #: The IANA zone the user is in. Needed because "until bedtime" is a
    #: wall-clock time, and a wall-clock time without a zone is a different
    #: instant every few months.
    timezone: TimezoneName
    response_timeout_seconds: ResponseTimeout = 45
    second_prompt_enabled: bool = False
    #: Only for ``custom``. Bounded, so a mistyped unit cannot become a week.
    custom_minutes: CustomMinutes | None = None


class MonitoringSessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: MonitoringStatus
    started_at: datetime
    ends_at: datetime | None
    duration_mode: DurationMode
    timezone: str
    response_timeout_seconds: int
    second_prompt_enabled: bool
    second_prompt_timeout_seconds: int
    ended_at: datetime | None
    end_reason: EndReason | None


# --- capabilities ------------------------------------------------------------


class CapabilityRead(BaseModel):
    """One capability, its state, and the words for both (section 106).

    The labels travel with the value so a screen cannot invent its own
    vocabulary for "not configured" -- section 64's whole point is that the UI
    is driven by the backend's answer rather than by what a screen assumed.
    """

    key: CapabilityKey
    state: CapabilityState
    label: str
    state_label: str


class CapabilitiesRead(BaseModel):
    capabilities: list[CapabilityRead]
    #: Section 74's condition, computed rather than written into a screen.
    external_delivery_available: bool
    #: The sentence to show when it is false. Sent from the server so the
    #: wording is reviewable in one place (section 120).
    warning: str | None


# --- events ------------------------------------------------------------------


class EscalationAttemptRead(BaseModel):
    """One attempt, as section 42 wants it displayed.

    ``line`` is the rendered sentence and the fields beside it are what it was
    rendered from, so a client can group or re-order without reconstructing the
    prose. There is no phone number here and no account id -- a name is what
    the screen needs.
    """

    id: uuid.UUID
    recipient_label: str
    is_caregiver: bool
    priority: int
    channel: EscalationChannel
    status: EscalationAttemptStatus
    failure_code: str | None
    attempted_at: datetime | None
    confirmed_at: datetime | None
    line: str


class SafetyEventRead(BaseModel):
    """One event in the history (section 49)."""

    id: uuid.UUID
    event_type: SafetyEventType
    #: From ``services.safety.wording``. Always begins "Possible" for anything
    #: a sensor observed (sections 16 and 52).
    event_label: str
    triggered_at: datetime
    status: SafetyEventStatus
    resolution: EventResolution | None
    resolution_label: str | None
    escalation_outcome: EscalationOutcome | None
    escalation_outcome_label: str | None
    user_response: UserResponse | None
    false_positive: bool | None


class SafetyEventDetailRead(SafetyEventRead):
    """One event in full (section 51)."""

    description: str
    #: Null when the user answered, or when nobody was asked.
    no_response_seconds: int | None
    no_response_label: str | None
    response_deadline_at: datetime | None
    second_prompt_deadline_at: datetime | None
    escalation_started_at: datetime | None
    resolved_at: datetime | None
    false_positive_reason: FalsePositiveReason | None
    attempts: list[EscalationAttemptRead]
    #: How many caregivers got an in-app alert record. A count, because the
    #: primary user's screen does not need to list their own caregivers back
    #: to them here.
    alert_count: int


class SafetyEventListRead(BaseModel):
    events: list[SafetyEventRead]


class SosCreate(BaseModel):
    """Raise an emergency request (sections 12, 13, 14 and 77).

    ``event_type`` is two values. ``call_for_help`` is section 14's
    "Nura, emergency" contract: the app posts it when it recognises the phrase,
    and it behaves identically to pressing SOS -- no countdown, straight to
    escalation.

    ``client_event_id`` is what makes a retry safe. Section 77 forbids parallel
    duplicate emergencies, and the server additionally folds any SOS raised
    while one is already live into that one, so a client that forgot to send a
    key is still safe.
    """

    event_type: SosEventType = "manual_sos"
    client_event_id: IdempotencyKey | None = None


class SafetyResponse(BaseModel):
    """The user's answer to a safety check (sections 23, 25 and 26)."""

    response: UserResponse


class FalseAlarmUpdate(BaseModel):
    """Label a finished event (sections 47 and 48).

    ``false_positive`` is required and ``reason`` optional, because "No / Not
    sure" is a real answer worth recording -- and because section 48 wants the
    label stored rather than inferred from the absence of one.
    """

    false_positive: bool
    reason: FalsePositiveReason | None = None


class DeviceSafetyEventCreate(BaseModel):
    """What a future robot posts (sections 19, 20, 54 and 105).

    No profile id. The device token resolves the device, the device resolves
    the profile it is linked to, and a body claiming a different one has
    nowhere to say so -- section 105's "never trust profile identity only from
    the request body", enforced by the model rather than by a check.

    ``confidence`` is accepted and **not stored** (section 54). It is
    engineering metadata about a detector's own output, not a probability that
    somebody is ill, and ``safety_events`` has no column for it because a
    column is a thing a screen eventually reads.
    """

    event_type: DeviceEventType
    trigger_source: TriggerSource = "developer_simulation"
    #: When the detector saw it. Advisory: the server records its own clock, so
    #: a device with a wrong time cannot backdate an emergency.
    observed_at: datetime | None = None
    #: Required. Section 20 asks for duplicate protection on device triggers,
    #: and a key the device chooses is the only thing that can provide it
    #: across a retry that never saw the first response.
    idempotency_key: IdempotencyKey
    confidence: Annotated[float, Field(ge=0.0, le=1.0)] | None = None


class DeviceSafetyEventRead(BaseModel):
    """What the robot is told back.

    Deliberately thin, the way the medication device action is: an id, a
    status, and whether this request created the event. No name, no contact,
    no health data -- a device has no use for any of it, and none of it has
    any business in a robot's memory or logs.
    """

    event_id: uuid.UUID
    status: SafetyEventStatus
    created: bool


# --- status ------------------------------------------------------------------


class SafetyStatusRead(BaseModel):
    """Everything the Safety screen needs, in one request (sections 59 and 60)."""

    monitoring: MonitoringSessionRead | None
    monitoring_sentence: str
    active_event: SafetyEventDetailRead | None
    #: Section 43. Derived from the active event, never stored.
    emergency_mode: bool
    capabilities: list[CapabilityRead]
    emergency_contact_count: int
    #: Section 73's warning, or null when there is nobody to warn about.
    no_contacts_warning: str | None
    #: Section 74's warning, or null when some provider exists.
    no_providers_warning: str | None
    #: Section 66's sentence, present whenever monitoring is on and nothing is
    #: watching automatically.
    detection_notice: str | None
    #: Section 23's question, ready to show. Server-rendered so the wording
    #: lives in one reviewable module.
    check_prompt: str


# --- caregiver alerts ---------------------------------------------------------


class SafetyAlertRead(BaseModel):
    """One alert, as a caregiver sees it (sections 37, 50, 83 and 85).

    The whole model is nine fields and none of them is health data. A
    caregiver learns what was observed, when, whether there was a response and
    how the escalation went -- which is what section 37's example sentence
    says, and nothing beyond it.
    """

    id: uuid.UUID
    safety_event_id: uuid.UUID
    event_type: SafetyEventType
    event_label: str
    triggered_at: datetime
    created_at: datetime
    read_at: datetime | None
    acknowledged_at: datetime | None
    event_status: SafetyEventStatus
    event_resolution: EventResolution | None
    escalation_outcome: EscalationOutcome | None
    #: The sentence from ``services.safety.wording``. Section 37's wording,
    #: rendered once on the server.
    sentence: str


class SafetyAlertListRead(BaseModel):
    alerts: list[SafetyAlertRead]
    unread_count: int
