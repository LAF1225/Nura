"""Caregiver, family and emergency-contact request/response models.

PRD 9, sections 7, 15, 18, 22, 23, 67, 75, 81 and 88.

Five things a reader should check for and find.

**No request carries an account id, a profile id or a relationship id in its
body.** Every one of those comes from the path or from the verified token.
Section 75 says account and profile ids are never trusted alone; the way to be
sure is that there is nowhere in these models to put one.

**No request carries a permission flag the server would believe.** There is no
``is_caregiver``, no ``can_view``, no ``role_grants``. Section 75's "client flags
cannot elevate privilege" is satisfied by absence: the only permission input is
``PermissionsUpdate``, which the *primary user* sends about somebody else.

**No caregiver-facing response carries free clinical text.** The caregiver views
in ``services.caregivers.care_view`` are assembled to be smaller than the owner's
(section 67), and these models are the same size: no medication skip reason, no
appointment notes, no symptom free text, no report snapshot, no condition names.

**A decline note has no field in any caregiver-facing model.** Sections 25 and 88
say a private reason stays private, so ``SuggestionRead`` -- which both sides
receive -- has no place for it. The note is stored and readable only by the
account that wrote it, through ``SuggestionOwnerRead``.

**An invitation preview says almost nothing** (section 81). A name, a role and
the permission list the caregiver is being asked to agree to. No health
information, no counts, not even whether the profile has any records.
"""

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.models.caregiver import (
    CONTACT_NAME_MAX_LENGTH,
    CONTACT_PHONE_MAX_LENGTH,
    CONTACT_RELATIONSHIP_MAX_LENGTH,
    DECLINE_NOTE_MAX_LENGTH,
    FAMILY_MESSAGE_MAX_LENGTH,
    INVITED_NAME_MAX_LENGTH,
)
from app.models.enums import (
    AUDIO_CALL_STATES,
    CARE_NOTIFICATION_KEYS,
    CAREGIVER_NOTIFICATION_KEYS,
    CAREGIVER_PERMISSION_KEYS,
    CAREGIVER_RELATIONSHIP_STATUSES,
    CAREGIVER_ROLES,
    CAREGIVER_SUGGESTION_ACTION_TYPES,
    CAREGIVER_SUGGESTION_CATEGORIES,
    CAREGIVER_SUGGESTION_STATUSES,
    FAMILY_CHECK_IN_CODES,
    FAMILY_MESSAGE_TYPES_ALLOWED,
)
from app.models.symptom import CLIENT_ID_MAX_LENGTH
from app.schemas.productivity import CaregiverRoutineRead

CaregiverRole = Literal[
    "primary_caregiver", "family", "caregiver", "emergency_contact", "other"
]
RelationshipStatus = Literal["pending", "active", "declined", "revoked", "expired"]
PermissionKey = Literal[
    "medications",
    "appointments",
    "symptoms",
    "reports",
    "safety_alerts",
    "communication",
    "routines",
    "general_health_summary",
]
SuggestionCategory = Literal["medications", "appointments", "routines"]
SuggestionActionType = Literal[
    "change_medication_reminder_time",
    "pause_medication_reminder",
    "resume_medication_reminder",
    "add_appointment",
    "change_appointment_time",
    # PRD 12, section 16. There is deliberately no task, alarm or reminder
    # action: section 42 keeps those private to the primary user.
    "add_routine",
    "change_routine_time",
    "pause_routine",
]
SuggestionStatus = Literal["pending", "approved", "declined", "expired", "cancelled"]
MessageType = Literal["text", "check_in"]
CheckInCode = Literal[
    "im_okay",
    "not_great",
    "please_call_me",
    "need_help",
    "how_are_you",
    "thinking_of_you",
]
MessageSide = Literal["primary_user", "caregiver", "system"]
CallState = Literal["idle", "ringing", "connecting", "active", "ended", "failed"]
CaregiverNotificationKey = Literal[
    "messages", "appointment_updates", "suggestion_outcomes", "safety_alerts"
]
CareNotificationKey = Literal[
    "caregiver_messages",
    "suggestion_requests",
    "appointment_suggestions",
    "routine_suggestions",
]

# The same guard as everywhere else: a Literal that drifts from the tuple the
# database CHECK constraints are built from is a startup failure, not a request
# Postgres rejects at three in the morning.
assert set(CAREGIVER_ROLES) == set(CaregiverRole.__args__)  # type: ignore[attr-defined]
assert set(CAREGIVER_RELATIONSHIP_STATUSES) == set(RelationshipStatus.__args__)  # type: ignore[attr-defined]
assert set(CAREGIVER_PERMISSION_KEYS) == set(PermissionKey.__args__)  # type: ignore[attr-defined]
assert set(CAREGIVER_SUGGESTION_CATEGORIES) == set(SuggestionCategory.__args__)  # type: ignore[attr-defined]
assert set(CAREGIVER_SUGGESTION_ACTION_TYPES) == set(SuggestionActionType.__args__)  # type: ignore[attr-defined]
assert set(CAREGIVER_SUGGESTION_STATUSES) == set(SuggestionStatus.__args__)  # type: ignore[attr-defined]
assert set(FAMILY_MESSAGE_TYPES_ALLOWED) == set(MessageType.__args__)  # type: ignore[attr-defined]
assert set(FAMILY_CHECK_IN_CODES) == set(CheckInCode.__args__)  # type: ignore[attr-defined]
assert set(AUDIO_CALL_STATES) == set(CallState.__args__)  # type: ignore[attr-defined]
assert set(CAREGIVER_NOTIFICATION_KEYS) == set(CaregiverNotificationKey.__args__)  # type: ignore[attr-defined]
assert set(CARE_NOTIFICATION_KEYS) == set(CareNotificationKey.__args__)  # type: ignore[attr-defined]

InvitedName = Annotated[
    str,
    StringConstraints(
        min_length=1, max_length=INVITED_NAME_MAX_LENGTH, strip_whitespace=True
    ),
]
ContactName = Annotated[
    str,
    StringConstraints(
        min_length=1, max_length=CONTACT_NAME_MAX_LENGTH, strip_whitespace=True
    ),
]
Phone = Annotated[
    str,
    StringConstraints(
        min_length=3, max_length=CONTACT_PHONE_MAX_LENGTH, strip_whitespace=True
    ),
]
RelationshipLabel = Annotated[
    str,
    StringConstraints(
        min_length=1, max_length=CONTACT_RELATIONSHIP_MAX_LENGTH, strip_whitespace=True
    ),
]
MessageText = Annotated[
    str,
    StringConstraints(
        min_length=1, max_length=FAMILY_MESSAGE_MAX_LENGTH, strip_whitespace=True
    ),
]
DeclineNote = Annotated[
    str,
    StringConstraints(
        min_length=1, max_length=DECLINE_NOTE_MAX_LENGTH, strip_whitespace=True
    ),
]
ClientId = Annotated[
    str, StringConstraints(min_length=1, max_length=CLIENT_ID_MAX_LENGTH)
]


# --- permissions -------------------------------------------------------------


class PermissionRead(BaseModel):
    """One category, with the words a person is shown (section 15).

    The label and description come from the server because section 15 forbids
    vague wording and the honest description of ``safety_alerts`` today is
    "nothing yet" -- which is a fact about the deployment, not a string the app
    should be guessing at.
    """

    key: PermissionKey
    allowed: bool
    label: str
    description: str
    #: False when the category is granted but has nothing behind it:
    #: ``safety_alerts`` until PRD 10, and ``routines`` while Nura keeps none.
    has_data: bool


class PermissionsUpdate(BaseModel):
    """What the primary user is changing (section 53).

    Keys that are absent are left alone, so a client sending one toggle does not
    silently deny the rest. Unknown keys are refused by the Literal.
    """

    model_config = ConfigDict(extra="forbid")

    permissions: dict[PermissionKey, bool] = Field(min_length=1)


# --- relationships -----------------------------------------------------------


class CaregiverRead(BaseModel):
    """One caregiver, as the primary user's list shows them."""

    id: uuid.UUID
    invited_name: str
    role: CaregiverRole
    role_label: str
    status: RelationshipStatus
    #: Only ever the address the *primary user* typed when inviting. Not the
    #: caregiver's account email: the account is Supabase's, and a caregiver's
    #: contact details are not the profile owner's to be handed back.
    invite_email: str | None = None
    invite_phone: str | None = None
    invite_expires_at: datetime | None = None
    accepted_at: datetime | None = None
    revoked_at: datetime | None = None
    created_at: datetime
    permissions: list[PermissionRead]
    #: How many categories are granted. The app shows "3 of 8" without counting.
    granted_count: int


class CaregiverListRead(BaseModel):
    caregivers: list[CaregiverRead]
    #: True once this profile has ever had a caregiver, so an empty list can be
    #: "nobody yet" rather than "nobody right now".
    has_any: bool


class InviteCreate(BaseModel):
    """What the invite form sends (section 11).

    Either an email or a phone, or neither: the contact is a note for the
    inviter's own reference, because Nura has no way to send anything. See
    ``services.caregivers.invitations``.
    """

    model_config = ConfigDict(extra="forbid")

    invited_name: InvitedName
    role: CaregiverRole = "family"
    email: Annotated[str, StringConstraints(max_length=320)] | None = None
    phone: Annotated[str, StringConstraints(max_length=32)] | None = None
    permissions: dict[PermissionKey, bool] = Field(default_factory=dict)


class InviteCreated(BaseModel):
    """The new relationship, plus the one copy of its token.

    The token is here and nowhere else: it is not stored, not logged, and not
    returned by any other endpoint (section 13). If the primary user loses it,
    they revoke the invitation and send another.
    """

    caregiver: CaregiverRead
    token: str
    expires_at: datetime
    #: Said in the response rather than only in the docs, because the app has to
    #: tell the user that sharing the link is their job.
    delivery: Literal["share_manually"] = "share_manually"


class RoleUpdate(BaseModel):
    """Relabelling a relationship (section 54). Grants nothing."""

    model_config = ConfigDict(extra="forbid")

    role: CaregiverRole


class CaregiverNotificationsUpdate(BaseModel):
    """What a caregiver wants to hear about, for one person (section 48)."""

    model_config = ConfigDict(extra="forbid")

    notifications: dict[CaregiverNotificationKey, bool] = Field(min_length=1)


class CareNotificationsUpdate(BaseModel):
    """What the primary user wants to hear about from caregivers (section 48)."""

    model_config = ConfigDict(extra="forbid")

    notifications: dict[CareNotificationKey, bool] = Field(min_length=1)


class CareNotificationsRead(BaseModel):
    notifications: dict[CareNotificationKey, bool]


# --- invitations -------------------------------------------------------------


class InvitationPreviewRead(BaseModel):
    """What a token holder is shown before deciding (sections 15 and 81).

    Everything here is needed to answer "do I want to do this?" and nothing is
    needed for anything else. In particular there is no profile id: accepting is
    done with the token, so the caller never learns one.
    """

    invited_name: str
    #: The first name Nura calls the person. Needed for "support Mum"; not
    #: medical, and the alternative is an invitation nobody can identify.
    profile_name: str
    role: CaregiverRole
    role_label: str
    permissions: list[PermissionRead]
    #: Both lists section 15 asks for, as labels, in a fixed order.
    will_access: list[str]
    will_not_access: list[str]
    expires_at: datetime


class SupportedProfileRead(BaseModel):
    """One person this account supports (sections 16 and 56)."""

    relationship_id: uuid.UUID
    profile_id: uuid.UUID
    profile_name: str
    role: CaregiverRole
    role_label: str
    granted: list[PermissionKey]
    notifications: dict[CaregiverNotificationKey, bool]
    accepted_at: datetime | None = None


class SupportedProfileListRead(BaseModel):
    """The caregiver's switcher (section 16).

    Flat, and the only route that returns profiles the caller does not own. A
    caregiver supporting three people gets three rows, each with its own
    permission set -- section 56's requirement that each relationship is
    independent.
    """

    profiles: list[SupportedProfileRead]


# --- suggestions -------------------------------------------------------------


class SuggestionCreate(BaseModel):
    """A change a caregiver proposes (sections 22 and 23).

    ``payload`` is validated against the action's own model inside
    ``services.caregivers.suggestions`` rather than here, because the shape
    depends on ``action_type`` and a discriminated union of five payloads in the
    schema would put the same rules in two places. What *is* guaranteed here:
    ``action_type`` is one of five, so no request can even name a forbidden
    change (section 85).
    """

    model_config = ConfigDict(extra="forbid")

    action_type: SuggestionActionType
    #: What to change. Absent on ``add_appointment``, which proposes something
    #: that does not exist yet.
    target_resource_id: uuid.UUID | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    #: Makes a retried POST idempotent (section 74).
    client_suggestion_id: ClientId | None = None


class SuggestionDiff(BaseModel):
    """The explicit current-versus-proposed pair section 86 asks for.

    Both halves rendered by the server, and ``current`` read at the moment the
    screen is built rather than stored -- so a reminder the user moved themselves
    yesterday shows today's real time.
    """

    subject: str
    current: str | None
    proposed: str
    #: True when the thing it would change has gone, so the review screen can
    #: say so instead of offering Approve on something unapplicable.
    target_missing: bool


class SuggestionRead(BaseModel):
    """One suggestion. The same model both sides receive.

    Deliberately the same, and deliberately without ``decline_note``: sections
    25 and 88 keep a private reason private, and a field that exists only for one
    audience is a field somebody eventually serialises to the other.
    """

    id: uuid.UUID
    action_type: SuggestionActionType
    action_label: str
    category: SuggestionCategory
    status: SuggestionStatus
    diff: SuggestionDiff
    #: Who proposed it, as the primary user's list needs to show.
    caregiver_name: str
    created_at: datetime
    reviewed_at: datetime | None = None


class SuggestionOwnerRead(SuggestionRead):
    """The primary user's own view, which may include their private note."""

    decline_note: str | None = None


class SuggestionListRead(BaseModel):
    suggestions: list[SuggestionRead]
    pending_count: int


class SuggestionDecline(BaseModel):
    """Declining, with an optional note that is never shared back (section 25)."""

    model_config = ConfigDict(extra="forbid")

    note: DeclineNote | None = None


# --- family messaging --------------------------------------------------------


class FamilyMessageRead(BaseModel):
    """One line in a care thread.

    ``text`` is what was typed on a ``text`` message. On a ``check_in`` it is the
    *rendered* sentence for the stored code -- the row keeps the code, and
    ``services.caregivers.wording`` is the one place that turns it into words.
    """

    id: uuid.UUID
    message_type: Literal["text", "check_in", "photo", "system"]
    side: MessageSide
    text: str | None
    check_in_code: CheckInCode | None = None
    created_at: datetime
    read_at: datetime | None = None
    #: Echoed so the app can retire the right optimistic row after a retry.
    client_message_id: str | None = None


class FamilyThreadRead(BaseModel):
    id: uuid.UUID
    relationship_id: uuid.UUID
    #: Who the thread is with, from the reader's side.
    with_name: str
    unread: int
    last_message: FamilyMessageRead | None = None
    last_message_at: datetime | None = None


class FamilyThreadListRead(BaseModel):
    threads: list[FamilyThreadRead]


class FamilyThreadDetailRead(BaseModel):
    thread: FamilyThreadRead
    messages: list[FamilyMessageRead]


class FamilyMessageCreate(BaseModel):
    """Sending one line.

    A ``photo`` cannot be requested: section 33 makes attachments optional and
    the upload route they would need does not exist, so ``photo`` is absent from
    the Literal as well as refused by the service.
    """

    model_config = ConfigDict(extra="forbid")

    message_type: MessageType = "text"
    text: MessageText | None = None
    check_in_code: CheckInCode | None = None
    client_message_id: ClientId | None = None


class ThreadCreate(BaseModel):
    """Starting the conversation with one caregiver.

    One thread per relationship, so this takes the relationship and nothing
    else -- there is no participant list to supply, which is what keeps one
    caregiver out of another's thread (section 66).
    """

    model_config = ConfigDict(extra="forbid")

    relationship_id: uuid.UUID


# --- emergency contacts ------------------------------------------------------


class EmergencyContactRead(BaseModel):
    id: uuid.UUID
    name: str
    phone: str | None
    relationship_label: str | None
    priority: int
    is_active: bool
    #: True when this contact also uses Nura, set only by the caregiver
    #: invitation flow. Never settable from a request (section 75).
    has_account: bool


class EmergencyContactListRead(BaseModel):
    contacts: list[EmergencyContactRead]


class EmergencyContactCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: ContactName
    phone: Phone | None = None
    relationship_label: RelationshipLabel | None = None
    is_active: bool = True


class EmergencyContactUpdate(BaseModel):
    """A PATCH. Priority is absent: it is changed by reordering the whole chain,
    which is the only way to keep it contiguous (section 45)."""

    model_config = ConfigDict(extra="forbid")

    name: ContactName | None = None
    phone: Phone | None = None
    relationship_label: RelationshipLabel | None = None
    is_active: bool | None = None


class EmergencyContactReorder(BaseModel):
    """The chain in the order the screen is showing it (sections 44 and 89)."""

    model_config = ConfigDict(extra="forbid")

    order: list[uuid.UUID] = Field(min_length=1, max_length=50)


# --- the caregiver's home ----------------------------------------------------


class CaregiverMedicationRead(BaseModel):
    """What ``medications`` unlocks (section 19).

    No skip reason, by design: section 19 excludes free-text skip reasons by
    default, and there is no field here one could be put in.
    """

    medication_id: uuid.UUID
    name: str
    dose: str | None
    schedule_label: str | None
    reminders_paused: bool
    supply_low: bool
    remaining_doses: int | None
    #: The schedule a reminder-time suggestion would target.
    schedule_id: uuid.UUID | None


class CaregiverAdherenceRead(BaseModel):
    """Counts for a week. ``percent`` is null when nothing was due."""

    from_date: str
    to_date: str
    taken: int
    skipped: int
    missed: int
    percent: int | None


class CaregiverAppointmentRead(BaseModel):
    appointment_id: uuid.UUID
    title: str
    when_label: str
    day_label: str
    appointment_type: str
    location_name: str | None
    question_count: int
    preparation_status: str


class CaregiverSymptomRead(BaseModel):
    """What ``symptoms`` unlocks (section 28).

    Severity and change, which is what a summary is. No free text, no photos:
    a symptom photo is as private as anything in this product, and section 28
    grants viewing history rather than images.
    """

    episode_id: uuid.UUID
    name: str
    status: str
    severity: int | None
    change_state: str | None
    last_recorded_at: datetime | None


class CaregiverReportRead(BaseModel):
    """That a report exists (section 29). Not its contents, and not the PDF."""

    report_id: uuid.UUID
    appointment_title: str
    version: int
    generated_at: datetime
    status: str


class CaregiverHealthCountsRead(BaseModel):
    """Counts only (section 67). No condition, medication or allergy names."""

    active_conditions: int
    active_medications: int
    active_symptoms: int
    allergies: int


class CaregiverSafetyRead(BaseModel):
    """What a caregiver sees of safety on their home screen (PRD 10, s31, 50).

    Five fields, and none of them health data. Enough to know something
    happened and to open it; the alert list and its sentences live behind
    ``/profiles/{id}/care/safety-alerts``.
    """

    unread_count: int
    latest_alert_id: uuid.UUID | None = None
    latest_event_label: str | None = None
    latest_at: datetime | None = None
    latest_acknowledged: bool = False


class CaregiverHomeRead(BaseModel):
    """The caregiver's Today, in one request (sections 17 and 60).

    Every section is optional and **absent** when the permission is not granted
    -- not empty, not zero. Section 18 says the absence of a permission must not
    leak, and an omitted key is indistinguishable from a person with nothing
    recorded.
    """

    profile_id: uuid.UUID
    profile_name: str
    role: CaregiverRole
    role_label: str
    granted: list[PermissionKey]
    #: Granted but with nothing behind it yet. **Empty since PRD 12**, which
    #: built the routine records ``routines`` used to promise and nothing
    #: deliver. The field stays for the next permission that is reserved before
    #: its data exists.
    granted_without_data: list[PermissionKey]
    medications: list[CaregiverMedicationRead] | None = None
    adherence: CaregiverAdherenceRead | None = None
    doses_remaining_today: int | None = None
    doses_overdue: int | None = None
    appointments: list[CaregiverAppointmentRead] | None = None
    symptoms: list[CaregiverSymptomRead] | None = None
    reports: list[CaregiverReportRead] | None = None
    #: Absent unless ``routines`` is granted (PRD 12, section 16). Reaches
    #: routines only -- section 42 keeps tasks, alarms and general reminders
    #: private to the primary user.
    routines: list[CaregiverRoutineRead] | None = None
    health_counts: CaregiverHealthCountsRead | None = None
    unread_messages: int | None = None
    #: Absent unless ``safety_alerts`` is granted (PRD 10, sections 31 and 50).
    safety: CaregiverSafetyRead | None = None
    pending_suggestions: int = 0
    #: Whether this server has an audio-calling provider at all (section 38).
    #: False in every deployment today, and the app shows no Call control.
    calling_available: bool = False


# --- the primary user's care summary ----------------------------------------


class CareSummaryRead(BaseModel):
    """What the Care screen needs about caregivers, in one request.

    Counts rather than records: the lists live behind their own routes, and a
    tab that loads four screens' worth of data to render three numbers is what
    PRD 3 section 16 warns against.
    """

    caregiver_count: int
    pending_invitation_count: int
    pending_suggestion_count: int
    unread_message_count: int
    emergency_contact_count: int


# --- calling -----------------------------------------------------------------


class CallStartRequest(BaseModel):
    """Asking for a call (section 38).

    Takes the relationship and nothing else -- no room, no SDP, no vendor
    concept. Today every deployment answers 503 ``calling_not_configured``,
    because section 38 forbids simulating a call that is not happening.
    """

    model_config = ConfigDict(extra="forbid")

    relationship_id: uuid.UUID


class CallSessionRead(BaseModel):
    call_id: str
    state: CallState
    #: Short-lived and opaque, from the provider. Never stored.
    credential: str | None = None
    expires_at: datetime | None = None
