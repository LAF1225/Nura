"""Caregivers, suggestions, family messages and emergency contacts.

PRD 9, sections 9, 18, 45, 52, 61, 64, 75, 80 and 81.

**Two authorization paths, and each route says which one it is on.**

``OwnedProfile``   -- the primary user. Walks ``account_profile_roles``, the
                      same dependency every PRD 0-8 route uses, so these routes
                      refuse a caregiver outright.
``CareScopeDep``   -- owner *or* active caregiver, carrying the granted
                      categories. A route then calls ``scope.require(...)``.
``CaregiverScope`` -- caregiver only, for the routes the owner has richer
                      versions of.

Everything the primary user does to a caregiver -- invite, relabel, permission,
revoke -- is on ``OwnedProfile``. A caregiver cannot reach any of it, which is
how section 45's "caregivers must not silently reorder the chain" and section 53's
"the primary user may edit permissions" are enforced: not by checking a role, but
by the dependency.

**Emergency contacts are owner-only, including reads.** There is no
caregiver-scoped route for them anywhere in this file. Section 45 gives the chain
to the primary user, and the surest way to honour that is for a caregiver's
requests to 404 on every verb.

**A missing permission answers 404.** Not 403. The whole codebase answers 404 for
"not yours", because a 403 confirms a thing exists, and section 18 goes further:
the absence of a permission must not reveal anything. A caregiver without
``symptoms`` gets the same answer whether or not this person has ever recorded
one.

The routes are written out rather than generated, for the reason PRD 7 gave: this
is the surface that decides whether somebody's records can be read by another
person, and reading each one in full is worth more than brevity.
"""

import logging
import uuid
from collections.abc import Mapping
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import (
    CaregiverScope,
    CareScopeDep,
    CurrentUser,
    DbSession,
    Now,
    OwnedProfile,
    http_error,
)
from app.models import (
    CaregiverRelationship,
    CaregiverSuggestion,
    EmergencyContact,
    FamilyMessage,
    Profile,
)
from app.models.enums import (
    CAREGIVER_PERMISSION_KEYS,
    CAREGIVER_PERMISSIONS_WITHOUT_A_SOURCE,
)
from app.schemas.caregiver import (
    CallSessionRead,
    CallStartRequest,
    CaregiverAdherenceRead,
    CaregiverAppointmentRead,
    CaregiverHealthCountsRead,
    CaregiverHomeRead,
    CaregiverListRead,
    CaregiverMedicationRead,
    CaregiverNotificationsUpdate,
    CaregiverRead,
    CaregiverReportRead,
    CaregiverSafetyRead,
    CaregiverSymptomRead,
    CareSummaryRead,
    EmergencyContactCreate,
    EmergencyContactListRead,
    EmergencyContactRead,
    EmergencyContactReorder,
    EmergencyContactUpdate,
    FamilyMessageCreate,
    FamilyMessageRead,
    FamilyThreadDetailRead,
    FamilyThreadListRead,
    FamilyThreadRead,
    InvitationPreviewRead,
    InviteCreate,
    InviteCreated,
    PermissionRead,
    PermissionsUpdate,
    RoleUpdate,
    SuggestionCreate,
    SuggestionDecline,
    SuggestionDiff,
    SuggestionListRead,
    SuggestionOwnerRead,
    SuggestionRead,
    SupportedProfileListRead,
    SupportedProfileRead,
    ThreadCreate,
)
from app.schemas.productivity import CaregiverRoutineRead
from app.services.caregivers import calls as call_service
from app.services.caregivers import care_view, wording
from app.services.caregivers import contacts as contact_service
from app.services.caregivers import invitations as invitation_service
from app.services.caregivers import messaging as message_service
from app.services.caregivers import permissions as permission_service
from app.services.caregivers import relationships as relationship_service
from app.services.caregivers import suggestions as suggestion_service
from app.services.caregivers.permissions import CareScope
from app.services.errors import DomainError
from app.services.productivity import wording as productivity_wording
from app.services.safety import wording as safety_wording

logger = logging.getLogger(__name__)

router = APIRouter(tags=["caregivers"])


# --- serialisers -------------------------------------------------------------


def _require(scope: CareScope, permission_key: str) -> None:
    """``scope.require`` as an HTTP refusal rather than an exception.

    The services raise ``DomainError`` and the HTTP layer turns it into a
    response -- the pattern every route in this codebase uses. Without this, a
    missing permission would surface as a 500 instead of the 404 the rule means,
    which is both wrong and a different kind of disclosure.
    """
    try:
        scope.require(permission_key)
    except DomainError as error:
        raise http_error(error) from error


def _plain(mapping: Mapping[Any, bool]) -> dict[str, bool]:
    """A ``dict[Literal[...], bool]`` as the plain mapping the services take.

    The Literal is what refuses an unknown key at the edge; past that edge the
    services work in ordinary strings and assert against the tuples the database
    constraints are built from.
    """
    return {str(key): value for key, value in mapping.items()}


def _permission_rows(permissions: dict[str, bool]) -> list[PermissionRead]:
    """Every category with its answer, its label and whether it does anything.

    Always all eight, in the fixed order of ``CAREGIVER_PERMISSION_KEYS``: a
    screen that only lists the keys with stored rows is a screen that silently
    stops offering a category somebody added.
    """
    return [
        PermissionRead(
            key=key,  # type: ignore[arg-type]
            allowed=bool(permissions.get(key)),
            label=wording.PERMISSION_LABELS[key],
            description=wording.PERMISSION_DESCRIPTIONS[key],
            has_data=key not in CAREGIVER_PERMISSIONS_WITHOUT_A_SOURCE,
        )
        for key in CAREGIVER_PERMISSION_KEYS
    ]


def _caregiver_read(relationship: CaregiverRelationship) -> CaregiverRead:
    permissions = permission_service.permission_map(relationship)
    return CaregiverRead(
        id=relationship.id,
        invited_name=relationship.invited_name,
        role=relationship.role,  # type: ignore[arg-type]
        role_label=wording.ROLE_LABELS[relationship.role],
        status=relationship.status,  # type: ignore[arg-type]
        invite_email=relationship.invite_email,
        invite_phone=relationship.invite_phone,
        invite_expires_at=relationship.invite_expires_at,
        accepted_at=relationship.accepted_at,
        revoked_at=relationship.revoked_at,
        created_at=relationship.created_at,
        permissions=_permission_rows(permissions),
        granted_count=sum(1 for allowed in permissions.values() if allowed),
    )


def _safety_section(home: care_view.CaregiverHome) -> CaregiverSafetyRead | None:
    """The safety block on a caregiver's home, or nothing (PRD 10, s31 and 50).

    None when ``safety_alerts`` was not granted, which is section 18's rule
    applied to PRD 10's data: an absent key cannot be read to learn whether
    anything has ever happened to this person.
    """
    if home.unread_safety_alerts is None:
        return None
    latest = home.latest_safety_alert
    return CaregiverSafetyRead(
        unread_count=home.unread_safety_alerts,
        latest_alert_id=getattr(latest, "id", None),
        latest_event_label=(
            safety_wording.EVENT_TYPE_LABELS[latest.event_type]
            if latest is not None
            else None
        ),
        latest_at=getattr(latest, "triggered_at", None),
        latest_acknowledged=getattr(latest, "acknowledged_at", None) is not None,
    )


def _suggestion_read(
    db: Session,
    profile: Profile,
    suggestion: CaregiverSuggestion,
    *,
    for_owner: bool,
) -> SuggestionRead:
    """One suggestion, with its diff read at this moment (section 86).

    ``for_owner`` adds the private decline note and nothing else. Sections 25 and
    88: a reason the primary user wrote is theirs, and a caregiver never receives
    it.
    """
    view = suggestion_service.describe(db, profile, suggestion)
    diff = SuggestionDiff(
        subject=view.subject,
        current=view.current,
        proposed=view.proposed,
        target_missing=view.target_missing,
    )
    fields = {
        "id": suggestion.id,
        "action_type": suggestion.action_type,
        "action_label": wording.ACTION_LABELS[suggestion.action_type],
        "category": suggestion.category,
        "status": suggestion.status,
        "diff": diff,
        "caregiver_name": suggestion.relationship_row.invited_name,
        "created_at": suggestion.created_at,
        "reviewed_at": suggestion.reviewed_at,
    }
    if for_owner:
        return SuggestionOwnerRead(**fields, decline_note=suggestion.decline_note)  # type: ignore[arg-type]
    return SuggestionRead(**fields)  # type: ignore[arg-type]


def _message_read(message: FamilyMessage) -> FamilyMessageRead:
    """One line, with a check-in's sentence rendered from its stored code."""
    text = message.text
    if message.message_type == "check_in" and message.check_in_code:
        text = wording.check_in_sentence(message.check_in_code)
    return FamilyMessageRead(
        id=message.id,
        message_type=message.message_type,  # type: ignore[arg-type]
        side=message.sender_side,  # type: ignore[arg-type]
        text=text,
        check_in_code=message.check_in_code,  # type: ignore[arg-type]
        created_at=message.created_at,
        read_at=message.read_at,
        client_message_id=message.client_message_id,
    )


def _thread_read(
    summary: message_service.ThreadSummary, *, scope: CareScope
) -> FamilyThreadRead:
    """A thread row, named from the reader's own side.

    The owner sees the caregiver's name; the caregiver sees the person they
    support. Neither is told anything about the other's account.
    """
    with_name = (
        summary.relationship.invited_name
        if scope.is_owner
        else scope.profile.preferred_name
    )
    return FamilyThreadRead(
        id=summary.thread.id,
        relationship_id=summary.relationship.id,
        with_name=with_name,
        unread=summary.unread,
        last_message=(
            _message_read(summary.last_message)
            if summary.last_message is not None
            else None
        ),
        last_message_at=summary.thread.last_message_at,
    )


def _contact_read(contact: EmergencyContact) -> EmergencyContactRead:
    return EmergencyContactRead(
        id=contact.id,
        name=contact.name,
        phone=contact.phone,
        relationship_label=contact.relationship_label,
        priority=contact.priority,
        is_active=contact.is_active,
        has_account=contact.account_id is not None,
    )


# --- the primary user's caregiver list ---------------------------------------


@router.get("/profiles/{profile_id}/caregivers", response_model=CaregiverListRead)
def list_caregivers(
    profile: OwnedProfile, db: DbSession, include_inactive: bool = Query(default=False)
) -> CaregiverListRead:
    """The caregivers and open invitations for this profile (section 55).

    ``OwnedProfile``: a caregiver cannot read the list of other caregivers.
    Section 66 rules out unnecessary caregiver-to-caregiver exposure, and who
    else is helping somebody is exactly that.
    """
    # One query, filtered here: ``has_any`` has to know about the revoked and
    # declined rows even when the list does not show them, so that an empty
    # list can read as "nobody yet" rather than "nobody right now".
    all_rows = relationship_service.list_relationships(
        db, profile.id, include_inactive=True
    )
    shown = (
        all_rows
        if include_inactive
        else [
            row for row in all_rows if row.status in relationship_service.LISTED_STATUSES
        ]
    )
    return CaregiverListRead(
        caregivers=[_caregiver_read(row) for row in shown],
        has_any=bool(all_rows),
    )


@router.post(
    "/profiles/{profile_id}/caregivers/invitations",
    response_model=InviteCreated,
    status_code=status.HTTP_201_CREATED,
)
def create_invitation(
    payload: InviteCreate,
    profile: OwnedProfile,
    user: CurrentUser,
    db: DbSession,
    now: Now,
) -> InviteCreated:
    """Creates a pending relationship and returns its token once (section 13).

    **Nura does not send it.** There is no mail or SMS infrastructure in this
    backend, so the token comes back to the primary user to pass on however they
    already talk to this person -- the same handoff PRD 2 uses for a provisioning
    token. ``delivery`` says so in the response, because the app has to tell them.
    """
    try:
        minted = invitation_service.invite(
            db,
            profile,
            user,
            invited_name=payload.invited_name,
            role=payload.role,
            permission_keys=_plain(payload.permissions),
            email=payload.email,
            phone=payload.phone,
            now=now,
        )
    except DomainError as error:
        raise http_error(error) from error

    assert minted.relationship.invite_expires_at is not None
    return InviteCreated(
        caregiver=_caregiver_read(minted.relationship),
        token=minted.token,
        expires_at=minted.relationship.invite_expires_at,
    )


@router.patch(
    "/profiles/{profile_id}/caregivers/{relationship_id}", response_model=CaregiverRead
)
def update_caregiver_role(
    relationship_id: uuid.UUID,
    payload: RoleUpdate,
    profile: OwnedProfile,
    user: CurrentUser,
    db: DbSession,
    now: Now,
) -> CaregiverRead:
    """Relabels a relationship. Changes no permission (section 54)."""
    try:
        relationship = relationship_service.get_relationship(
            db, profile.id, relationship_id
        )
        updated = relationship_service.set_role(
            db, relationship, payload.role, user, now=now
        )
    except DomainError as error:
        raise http_error(error) from error
    return _caregiver_read(updated)


@router.delete(
    "/profiles/{profile_id}/caregivers/{relationship_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def revoke_caregiver(
    relationship_id: uuid.UUID,
    profile: OwnedProfile,
    user: CurrentUser,
    db: DbSession,
    now: Now,
) -> Response:
    """Ends the relationship now (section 52).

    Immediate and total: the next request from that caregiver is refused, because
    ``granted_keys`` returns nothing for a relationship that is not active and
    every check reads the row. There is no session to expire. A pending
    invitation is withdrawn the same way, and its token stops working.
    """
    try:
        relationship = relationship_service.get_relationship(
            db, profile.id, relationship_id
        )
        relationship_service.revoke(db, relationship, user, now=now)
    except DomainError as error:
        raise http_error(error) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/profiles/{profile_id}/caregivers/{relationship_id}/permissions",
    response_model=list[PermissionRead],
)
def read_permissions(
    relationship_id: uuid.UUID, profile: OwnedProfile, db: DbSession
) -> list[PermissionRead]:
    try:
        relationship = relationship_service.get_relationship(
            db, profile.id, relationship_id
        )
    except DomainError as error:
        raise http_error(error) from error
    return _permission_rows(permission_service.permission_map(relationship))


@router.patch(
    "/profiles/{profile_id}/caregivers/{relationship_id}/permissions",
    response_model=CaregiverRead,
)
def update_permissions(
    relationship_id: uuid.UUID,
    payload: PermissionsUpdate,
    profile: OwnedProfile,
    user: CurrentUser,
    db: DbSession,
    now: Now,
) -> CaregiverRead:
    """Changes what one caregiver may see (section 53).

    Effective immediately on success: the next request builds a fresh scope from
    these rows, so there is no window in which the old set still applies.
    """
    try:
        relationship = relationship_service.get_relationship(
            db, profile.id, relationship_id
        )
        updated = relationship_service.update_permissions(
            db, relationship, _plain(payload.permissions), user, now=now
        )
    except DomainError as error:
        raise http_error(error) from error
    return _caregiver_read(updated)


@router.get("/profiles/{profile_id}/care-summary", response_model=CareSummaryRead)
def read_care_summary(
    profile: OwnedProfile, scope: CareScopeDep, db: DbSession
) -> CareSummaryRead:
    """Counts for the Care screen, in one request."""
    rows = relationship_service.list_relationships(db, profile.id)
    return CareSummaryRead(
        caregiver_count=sum(1 for row in rows if row.status == "active"),
        pending_invitation_count=sum(1 for row in rows if row.status == "pending"),
        pending_suggestion_count=suggestion_service.open_count(db, profile.id),
        unread_message_count=message_service.unread_count(db, scope),
        emergency_contact_count=len(contact_service.list_contacts(db, profile.id)),
    )


@router.get("/caregiver-permissions", response_model=list[PermissionRead])
def read_permission_catalogue() -> list[PermissionRead]:
    """Every category, with its label and description. No profile involved.

    Here so the invitation form has section 15's wording *before* a relationship
    exists. The alternative was a copy of the labels in the app, which is exactly
    the drift section 15 is about: a category described one way on the invitation
    screen and another on the permission screen is a category nobody has really
    consented to.

    Nothing about anybody is returned -- it is the same eight rows for every
    caller, which is why it needs no profile in the path.
    """
    return _permission_rows(dict.fromkeys(CAREGIVER_PERMISSION_KEYS, False))


# --- invitations (the caregiver's side) --------------------------------------


@router.get("/caregiver-invitations/{token}", response_model=InvitationPreviewRead)
def read_invitation(
    token: str, user: CurrentUser, db: DbSession, now: Now
) -> InvitationPreviewRead:
    """What this token is for, and nothing more (sections 15 and 81).

    Authentication is required, which is stricter than section 81 asks for and
    matches section 14's own ordering -- sign in, *then* review. It costs nothing
    and means a leaked link alone does not even reveal a first name.

    **No profile id is returned.** Accepting is done with the token, so a holder
    never learns one -- which matters because a profile id is the key to every
    other route in this file.

    Both lists section 15 asks for are built here: what this caregiver will be
    able to access, and what they will not, as labels rather than keys.
    """
    try:
        relationship = invitation_service.find_by_token(db, token, now)
    except DomainError as error:
        raise http_error(error) from error

    preview = invitation_service.preview(relationship)
    will_access, will_not_access = wording.granted_summary(preview.permissions)
    return InvitationPreviewRead(
        invited_name=preview.invited_name,
        profile_name=preview.profile_name,
        role=preview.role,  # type: ignore[arg-type]
        role_label=wording.ROLE_LABELS[preview.role],
        permissions=_permission_rows(preview.permissions),
        will_access=will_access,
        will_not_access=will_not_access,
        expires_at=preview.expires_at,
    )


@router.post("/caregiver-invitations/{token}/accept", response_model=SupportedProfileRead)
def accept_invitation(
    token: str, user: CurrentUser, db: DbSession, now: Now
) -> SupportedProfileRead:
    """Accepts, and returns the relationship as the caregiver's switcher needs it.

    Single-use (sections 13 and 75): the token is consumed in the same
    transaction that activates the relationship, so a replayed request finds it
    spent and answers ``invitation_not_found`` -- while the relationship it
    created is already active and already in ``/caregiver/profiles``.
    """
    try:
        relationship = invitation_service.accept(db, token, user, now=now)
    except DomainError as error:
        raise http_error(error) from error
    return _supported_profile_read(relationship)


@router.post(
    "/caregiver-invitations/{token}/decline", status_code=status.HTTP_204_NO_CONTENT
)
def decline_invitation(
    token: str, user: CurrentUser, db: DbSession, now: Now
) -> Response:
    """Refuses an invitation, consuming the token."""
    try:
        invitation_service.decline(db, token, user, now=now)
    except DomainError as error:
        raise http_error(error) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- the caregiver's own surface ---------------------------------------------


def _supported_profile_read(
    relationship: CaregiverRelationship,
) -> SupportedProfileRead:
    return SupportedProfileRead(
        relationship_id=relationship.id,
        profile_id=relationship.profile_id,
        profile_name=relationship.profile.preferred_name,
        role=relationship.role,  # type: ignore[arg-type]
        role_label=wording.ROLE_LABELS[relationship.role],
        granted=sorted(permission_service.granted_keys(relationship)),  # type: ignore[arg-type]
        notifications=relationship_service.notification_preferences(relationship),  # type: ignore[arg-type]
        accepted_at=relationship.accepted_at,
    )


@router.get("/caregiver/profiles", response_model=SupportedProfileListRead)
def list_supported_profiles(user: CurrentUser, db: DbSession) -> SupportedProfileListRead:
    """The people this account supports (sections 16, 56 and 57).

    The only route in the API that returns profiles the caller does not own, and
    it returns a name, a role and a permission set -- no health information at
    all. Active relationships only, so a revoked one disappears from the switcher
    immediately (section 52).
    """
    rows = permission_service.supported_profiles(db, user.id)
    return SupportedProfileListRead(
        profiles=[_supported_profile_read(row) for row in rows]
    )


@router.get("/profiles/{profile_id}/care/home", response_model=CaregiverHomeRead)
def read_caregiver_home(
    scope: CaregiverScope,
    db: DbSession,
    now: Now,
    local_date: Annotated[str | None, Query()] = None,
) -> CaregiverHomeRead:
    """The caregiver's Today, assembled permission by permission (sections 17, 60).

    Every section is **absent** rather than empty when the category is not
    granted (section 18), so the response cannot be read to learn whether this
    person records symptoms.
    """
    day = date.fromisoformat(local_date) if local_date else now.date()
    home = care_view.build_home(db, scope, local_date=day, now=now)
    return CaregiverHomeRead(
        profile_id=scope.profile.id,
        profile_name=home.profile_name,
        role=home.role,  # type: ignore[arg-type]
        role_label=wording.ROLE_LABELS[home.role],
        granted=home.granted,  # type: ignore[arg-type]
        granted_without_data=home.granted_without_data,  # type: ignore[arg-type]
        medications=(
            [
                CaregiverMedicationRead(
                    medication_id=row.medication_id,
                    name=row.name,
                    dose=row.dose,
                    schedule_label=row.schedule_label,
                    reminders_paused=row.reminders_paused,
                    supply_low=row.supply_low,
                    remaining_doses=row.remaining_doses,
                    schedule_id=row.schedule_id,
                )
                for row in home.medications
            ]
            if home.medications is not None
            else None
        ),
        adherence=(
            CaregiverAdherenceRead(
                from_date=home.adherence.from_date.isoformat(),
                to_date=home.adherence.to_date.isoformat(),
                taken=home.adherence.taken,
                skipped=home.adherence.skipped,
                missed=home.adherence.missed,
                percent=home.adherence.percent,
            )
            if home.adherence is not None
            else None
        ),
        doses_remaining_today=home.doses_remaining_today,
        doses_overdue=home.doses_overdue,
        appointments=(
            [
                CaregiverAppointmentRead(
                    appointment_id=row.appointment_id,
                    title=row.title,
                    when_label=row.when_label,
                    day_label=row.day_label,
                    appointment_type=row.appointment_type,
                    location_name=row.location_name,
                    question_count=row.question_count,
                    preparation_status=row.preparation_status,
                )
                for row in home.appointments
            ]
            if home.appointments is not None
            else None
        ),
        symptoms=(
            [
                CaregiverSymptomRead(
                    episode_id=row.episode_id,
                    name=row.name,
                    status=row.status,
                    severity=row.severity,
                    change_state=row.change_state,
                    last_recorded_at=row.last_recorded_at,
                )
                for row in home.symptoms
            ]
            if home.symptoms is not None
            else None
        ),
        reports=(
            [
                CaregiverReportRead(
                    report_id=row.report_id,
                    appointment_title=row.appointment_title,
                    version=row.version,
                    generated_at=row.generated_at,
                    status=row.status,
                )
                for row in home.reports
            ]
            if home.reports is not None
            else None
        ),
        routines=(
            [
                CaregiverRoutineRead(
                    routine_id=row.routine_id,
                    title=row.title,
                    schedule_label=row.schedule_label,
                    step_count=row.step_count,
                    paused=row.paused,
                    today_status=row.today_status,  # type: ignore[arg-type]
                    today_done=row.today_done,
                    today_total=row.today_total,
                    today_progress_label=(
                        None
                        if row.today_done is None or row.today_total is None
                        else productivity_wording.progress_sentence(
                            row.today_done, row.today_total
                        )
                    ),
                )
                for row in home.routines
            ]
            if home.routines is not None
            else None
        ),
        health_counts=(
            CaregiverHealthCountsRead(
                active_conditions=home.health_counts.active_conditions,
                active_medications=home.health_counts.active_medications,
                active_symptoms=home.health_counts.active_symptoms,
                allergies=home.health_counts.allergies,
            )
            if home.health_counts is not None
            else None
        ),
        unread_messages=home.unread_messages,
        safety=_safety_section(home),
        pending_suggestions=home.pending_suggestions or 0,
        calling_available=home.calling_available,
    )


@router.patch(
    "/profiles/{profile_id}/care/notifications", response_model=SupportedProfileRead
)
def update_caregiver_notifications(
    payload: CaregiverNotificationsUpdate,
    scope: CaregiverScope,
    db: DbSession,
    now: Now,
) -> SupportedProfileRead:
    """What this caregiver wants to hear about, for this person (section 48).

    Theirs to set, not the primary user's: these decide what reaches their own
    phone. ``safety_alerts`` can be switched on and is stored faithfully; nothing
    will fire it until PRD 10 (sections 48 and 94).
    """
    assert scope.relationship is not None
    updated = relationship_service.set_notification_preferences(
        db, scope.relationship, _plain(payload.notifications), now=now
    )
    return _supported_profile_read(updated)


# --- suggestions -------------------------------------------------------------


@router.get(
    "/profiles/{profile_id}/caregiver-suggestions", response_model=SuggestionListRead
)
def list_suggestions(
    scope: CareScopeDep,
    db: DbSession,
    open_only: bool = Query(default=False),
) -> SuggestionListRead:
    """Care requests. The owner sees everyone's; a caregiver sees only their own.

    Narrowed by relationship for a caregiver, which is section 66 again: what
    somebody else proposed about this person is not theirs to read.
    """
    relationship_id = None if scope.is_owner else scope.relationship.id  # type: ignore[union-attr]
    rows = suggestion_service.list_for_profile(
        db, scope.profile.id, relationship_id=relationship_id, open_only=open_only
    )
    return SuggestionListRead(
        suggestions=[
            _suggestion_read(db, scope.profile, row, for_owner=scope.is_owner)
            for row in rows
        ],
        pending_count=sum(1 for row in rows if row.status == "pending"),
    )


@router.post(
    "/profiles/{profile_id}/caregiver-suggestions",
    response_model=SuggestionRead,
    status_code=status.HTTP_201_CREATED,
)
def create_suggestion(
    payload: SuggestionCreate,
    scope: CaregiverScope,
    db: DbSession,
    now: Now,
) -> SuggestionRead:
    """A caregiver proposes a change (sections 20, 22, 23 and 64).

    ``CaregiverScope``: the owner cannot create one, because the owner changes
    their own records directly. The permission for the action's category is
    checked here and again at approval.
    """
    try:
        suggestion = suggestion_service.create(
            db,
            scope,
            action_type=payload.action_type,
            payload=payload.payload,
            target_resource_id=payload.target_resource_id,
            client_suggestion_id=payload.client_suggestion_id,
            now=now,
        )
    except DomainError as error:
        raise http_error(error) from error
    return _suggestion_read(db, scope.profile, suggestion, for_owner=False)


@router.post(
    "/profiles/{profile_id}/caregiver-suggestions/{suggestion_id}/approve",
    response_model=SuggestionOwnerRead,
)
def approve_suggestion(
    suggestion_id: uuid.UUID,
    profile: OwnedProfile,
    user: CurrentUser,
    db: DbSession,
    now: Now,
) -> SuggestionRead:
    """The primary user says yes, and the change happens (section 24).

    ``OwnedProfile``: only the person themselves approves. Approving twice
    returns the same result rather than applying it twice (section 74).
    """
    try:
        suggestion = suggestion_service.get(db, profile.id, suggestion_id)
        approved = suggestion_service.approve(db, profile, suggestion, user, now=now)
    except DomainError as error:
        raise http_error(error) from error
    return _suggestion_read(db, profile, approved, for_owner=True)


@router.post(
    "/profiles/{profile_id}/caregiver-suggestions/{suggestion_id}/decline",
    response_model=SuggestionOwnerRead,
)
def decline_suggestion(
    suggestion_id: uuid.UUID,
    payload: SuggestionDecline,
    profile: OwnedProfile,
    user: CurrentUser,
    db: DbSession,
    now: Now,
) -> SuggestionRead:
    """The primary user says no (section 25).

    The optional note is kept and never returned to the caregiver: the
    caregiver-facing model has no field for it.
    """
    try:
        suggestion = suggestion_service.get(db, profile.id, suggestion_id)
        declined = suggestion_service.decline(
            db, suggestion, user, note=payload.note, now=now
        )
    except DomainError as error:
        raise http_error(error) from error
    return _suggestion_read(db, profile, declined, for_owner=True)


@router.post(
    "/profiles/{profile_id}/caregiver-suggestions/{suggestion_id}/cancel",
    response_model=SuggestionRead,
)
def cancel_suggestion(
    suggestion_id: uuid.UUID,
    scope: CaregiverScope,
    db: DbSession,
    now: Now,
) -> SuggestionRead:
    """A caregiver withdraws their own suggestion.

    Theirs only: the service refuses a suggestion made under another
    relationship, so one caregiver cannot cancel another's.
    """
    assert scope.relationship is not None
    try:
        suggestion = suggestion_service.get(
            db,
            scope.profile.id,
            suggestion_id,
            relationship_id=scope.relationship.id,
        )
        cancelled = suggestion_service.cancel(db, suggestion, scope, now=now)
    except DomainError as error:
        raise http_error(error) from error
    return _suggestion_read(db, scope.profile, cancelled, for_owner=False)


# --- family messaging --------------------------------------------------------


@router.get("/profiles/{profile_id}/family/threads", response_model=FamilyThreadListRead)
def list_threads(scope: CareScopeDep, db: DbSession) -> FamilyThreadListRead:
    """Care conversations. The owner's caregivers, or the caregiver's one thread."""
    _require(scope, "communication")
    summaries = message_service.list_threads(db, scope)
    return FamilyThreadListRead(
        threads=[_thread_read(summary, scope=scope) for summary in summaries]
    )


@router.post(
    "/profiles/{profile_id}/family/threads",
    response_model=FamilyThreadRead,
    status_code=status.HTTP_201_CREATED,
)
def create_thread(
    payload: ThreadCreate,
    scope: CareScopeDep,
    db: DbSession,
    now: Now,
) -> FamilyThreadRead:
    """Starts the conversation with one caregiver.

    Idempotent: a second request for the same relationship returns the thread
    that already exists, because there is exactly one per pairing.
    """
    _require(scope, "communication")
    try:
        if scope.is_owner:
            relationship = relationship_service.require_active(
                relationship_service.get_relationship(
                    db, scope.profile.id, payload.relationship_id
                )
            )
        else:
            assert scope.relationship is not None
            if payload.relationship_id != scope.relationship.id:
                raise relationship_service.RelationshipNotFoundError("Not found.")
            relationship = scope.relationship
        # The pairing has to allow messages, not just the caller. An owner's
        # scope holds every category, so without this the primary user could
        # start a thread with somebody who was never granted ``communication``.
        if not message_service.pairing_allows_messages(relationship):
            raise message_service.ThreadNotFoundError("Not found.")
        thread = message_service.get_or_create_thread(db, relationship, now=now)
    except DomainError as error:
        raise http_error(error) from error

    summaries = [
        summary
        for summary in message_service.list_threads(db, scope)
        if summary.thread.id == thread.id
    ]
    assert summaries, "the thread was just created inside this scope"
    return _thread_read(summaries[0], scope=scope)


@router.get(
    "/profiles/{profile_id}/family/threads/{thread_id}/messages",
    response_model=FamilyThreadDetailRead,
)
def read_messages(
    thread_id: uuid.UUID,
    scope: CareScopeDep,
    db: DbSession,
    now: Now,
    mark_read: bool = Query(default=True),
) -> FamilyThreadDetailRead:
    """A thread's newest page, marking the other side's messages read.

    ``mark_read`` defaults to true because opening a thread is what reading is;
    section 37 asks for no stronger promise than sent and read, and this is the
    moment the second one becomes true.
    """
    _require(scope, "communication")
    try:
        thread = message_service.get_thread(db, scope, thread_id)
    except DomainError as error:
        raise http_error(error) from error
    if mark_read:
        message_service.mark_read(db, scope, thread, now=now)
    messages = message_service.list_messages(db, thread)
    summaries = [
        summary
        for summary in message_service.list_threads(db, scope)
        if summary.thread.id == thread.id
    ]
    if not summaries:
        raise http_error(message_service.ThreadNotFoundError("Not found."))
    return FamilyThreadDetailRead(
        thread=_thread_read(summaries[0], scope=scope),
        messages=[_message_read(message) for message in messages],
    )


@router.post(
    "/profiles/{profile_id}/family/threads/{thread_id}/messages",
    response_model=FamilyMessageRead,
    status_code=status.HTTP_201_CREATED,
)
def send_message(
    thread_id: uuid.UUID,
    payload: FamilyMessageCreate,
    scope: CareScopeDep,
    user: CurrentUser,
    db: DbSession,
    now: Now,
) -> FamilyMessageRead:
    """Sends one line (sections 31, 34, 35, 36 and 74).

    Idempotent on ``client_message_id``: a retry after a timeout returns the
    message the server already stored rather than adding a second one, which is
    what lets the app keep one id across attempts (section 72).
    """
    _require(scope, "communication")
    try:
        thread = message_service.get_thread(db, scope, thread_id)
        message = message_service.send_message(
            db,
            scope,
            thread,
            sender_account_id=user.id,
            message_type=payload.message_type,
            text=payload.text,
            check_in_code=payload.check_in_code,
            client_message_id=payload.client_message_id,
            now=now,
        )
    except DomainError as error:
        raise http_error(error) from error
    return _message_read(message)


# --- emergency contacts (owner only, every verb) ----------------------------


@router.get(
    "/profiles/{profile_id}/emergency-contacts",
    response_model=EmergencyContactListRead,
)
def list_emergency_contacts(
    profile: OwnedProfile, db: DbSession
) -> EmergencyContactListRead:
    """The chain in priority order (section 44).

    ``OwnedProfile`` on every emergency-contact route, reads included. Section 45
    gives the chain to the primary user; there is no caregiver-scoped route for
    it anywhere in this file, so a caregiver 404s on every verb.
    """
    return EmergencyContactListRead(
        contacts=[
            _contact_read(contact)
            for contact in contact_service.list_contacts(db, profile.id)
        ]
    )


@router.post(
    "/profiles/{profile_id}/emergency-contacts",
    response_model=EmergencyContactRead,
    status_code=status.HTTP_201_CREATED,
)
def create_emergency_contact(
    payload: EmergencyContactCreate,
    profile: OwnedProfile,
    user: CurrentUser,
    db: DbSession,
    now: Now,
) -> EmergencyContactRead:
    """Adds a contact at the end of the chain."""
    try:
        contact = contact_service.create_contact(
            db,
            profile,
            contact_service.ContactInput(
                name=payload.name,
                phone=payload.phone,
                relationship_label=payload.relationship_label,
                is_active=payload.is_active,
            ),
            user,
            now=now,
        )
    except DomainError as error:
        raise http_error(error) from error
    return _contact_read(contact)


@router.patch(
    "/profiles/{profile_id}/emergency-contacts/{contact_id}",
    response_model=EmergencyContactRead,
)
def update_emergency_contact(
    contact_id: uuid.UUID,
    payload: EmergencyContactUpdate,
    profile: OwnedProfile,
    user: CurrentUser,
    db: DbSession,
    now: Now,
) -> EmergencyContactRead:
    try:
        contact = contact_service.get_contact(db, profile.id, contact_id)
        updated = contact_service.update_contact(
            db,
            contact,
            payload.model_dump(exclude_unset=True),
            user,
            now=now,
        )
    except DomainError as error:
        raise http_error(error) from error
    return _contact_read(updated)


@router.delete(
    "/profiles/{profile_id}/emergency-contacts/{contact_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_emergency_contact(
    contact_id: uuid.UUID,
    profile: OwnedProfile,
    user: CurrentUser,
    db: DbSession,
    now: Now,
) -> Response:
    try:
        contact = contact_service.get_contact(db, profile.id, contact_id)
        contact_service.delete_contact(db, contact, user, now=now)
    except DomainError as error:
        raise http_error(error) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/profiles/{profile_id}/emergency-contacts/reorder",
    response_model=EmergencyContactListRead,
)
def reorder_emergency_contacts(
    payload: EmergencyContactReorder,
    profile: OwnedProfile,
    user: CurrentUser,
    db: DbSession,
    now: Now,
) -> EmergencyContactListRead:
    """Puts the chain in the order the screen is showing (sections 44, 45, 89)."""
    contacts = contact_service.reorder(db, profile, payload.order, user, now=now)
    return EmergencyContactListRead(
        contacts=[_contact_read(contact) for contact in contacts]
    )


# --- calling -----------------------------------------------------------------


@router.post("/profiles/{profile_id}/family/calls", response_model=CallSessionRead)
def start_call(
    payload: CallStartRequest,
    scope: CareScopeDep,
    user: CurrentUser,
    db: DbSession,
) -> CallSessionRead:
    """Asks for an audio call (sections 38, 41 and 76).

    Authorized exactly like a message -- ``communication`` on an active
    relationship -- and then handed to the provider, which in every deployment
    today refuses with 503 ``calling_not_configured``. Section 38 forbids
    simulating a successful call, so this route cannot return ``active``: there
    is nothing behind it that could.
    """
    _require(scope, "communication")
    try:
        if scope.is_owner:
            relationship = relationship_service.require_active(
                relationship_service.get_relationship(
                    db, scope.profile.id, payload.relationship_id
                )
            )
        else:
            assert scope.relationship is not None
            if payload.relationship_id != scope.relationship.id:
                raise relationship_service.RelationshipNotFoundError("Not found.")
            relationship = scope.relationship
        if not message_service.pairing_allows_messages(relationship):
            raise relationship_service.RelationshipNotFoundError("Not found.")
        session = call_service.get_provider().start(
            relationship_id=relationship.id, caller_account_id=user.id
        )
    except DomainError as error:
        raise http_error(error) from error
    return CallSessionRead(
        call_id=session.call_id,
        state=session.state,  # type: ignore[arg-type]
        credential=session.credential,
        expires_at=session.expires_at,
    )
