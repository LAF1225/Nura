"""Privacy, export and deletion (PRD 13, sections 43, 44 and 45).

**Every route here is owner-only.** They depend on ``OwnedProfile``, which
resolves through ``account_profile_roles`` -- a caregiver has no row in it, so
a caregiver reaching any of these gets 404, the same answer as a profile that
does not exist. That is section 13's rule applied without exception: an export
is a complete copy of somebody's record and a delete is irreversible, so
neither is something a permission could ever grant.

**The robot is read here rather than in the service.** PRD 11's architectural
claim is that nothing under ``app/services`` outside the robot package imports
it, and a test enforces that. This file is in ``app/api``, which is where the
Nura Device screen already reads capabilities from, so the privacy hub's robot
rows are assembled here and handed to ``services.privacy.summary``.

**Deletion is two requests and the first one changes nothing.**
``delete-request`` is a read: it returns what would go, counted from the
database, plus the phrase the second request must carry. Section 21 asks for a
warning, confirmation and a final request rather than a one-tap destructive
action, and a GET-shaped first step is what makes the warning something a
person can sit with.
"""

import uuid
from datetime import datetime
from http import HTTPStatus
from typing import cast

from fastapi import APIRouter, Response
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession, Now, OwnedProfile, http_error
from app.models import AccountProfileRole, DataExport, Device
from app.models.enums import DATA_EXPORT_SECTIONS, ROBOT_PRIVACY_LEVELS
from app.schemas.privacy import (
    CapabilityLineRead,
    CaregiverAccessRead,
    ConversationsDeletedRead,
    DeletionConfirm,
    DeletionInventoryRead,
    DeletionResultRead,
    ExportListRead,
    ExportRead,
    ExportStatusValue,
    PrivacySummaryRead,
)
from app.services.errors import DomainError
from app.services.privacy import deletion as deletion_service
from app.services.privacy import export as export_service
from app.services.privacy import summary as summary_service
from app.services.privacy import wording
from app.services.robot import capabilities as robot_capabilities
from app.services.robot import preferences as robot_preferences
from app.services.robot import wording as robot_wording
from app.services.storage import get_object_store

router = APIRouter(prefix="/profiles/{profile_id}/privacy", tags=["privacy"])

NO_CONTENT = HTTPStatus.NO_CONTENT
CREATED = HTTPStatus.CREATED

#: How a preview level reads on the privacy screen. The robot's own settings
#: screen says the same three words; this names them in one place so the two
#: cannot disagree about what ``name_only`` means.
PREVIEW_LEVEL_LABELS = {
    "full": "Full details",
    "name_only": "Name only",
    "private": "Private",
}
assert set(PREVIEW_LEVEL_LABELS) == set(ROBOT_PRIVACY_LEVELS)


def _owned_device(db: DbSession, profile_id: uuid.UUID) -> Device | None:
    """The robot linked to this profile, if there is one.

    Usually there is not, and that is a normal state rather than an error --
    the same position PRD 3 took about the Today card. The privacy screen then
    says no robot is linked, which is different from saying a microphone is
    off.
    """
    return db.execute(
        select(Device).where(
            Device.owner_profile_id == profile_id,
            Device.claimed_by_account_id.is_not(None),
        )
    ).scalar_one_or_none()


def _robot_rows(
    db: DbSession, profile_id: uuid.UUID, now: Now
) -> tuple[tuple[summary_service.CapabilityLine, ...], tuple[tuple[str, str], ...], bool]:
    """The robot's capability states and preview levels (section 10).

    All twelve capabilities even when no robot is linked, because PRD 11
    returns all twelve: a screen that only lists what happens to be reported
    is a screen that silently stops mentioning one.
    """
    device = _owned_device(db, profile_id)
    lines = tuple(
        summary_service.CapabilityLine(
            key=view.key,
            label=robot_wording.CAPABILITY_LABELS[view.key],
            state=view.state,
            state_label=robot_wording.CAPABILITY_STATE_LABELS[view.state],
        )
        for view in robot_capabilities.views(db, device, now)
    )
    if device is None:
        return lines, (), False

    row = robot_preferences.get_or_create(db, device, now)
    previews = (
        ("Medication reminders", PREVIEW_LEVEL_LABELS[row.medication_privacy_level]),
        ("Tasks and routines", PREVIEW_LEVEL_LABELS[row.daily_life_privacy_level]),
        (
            "Family messages",
            "Shown" if row.family_message_display_enabled else "Hidden",
        ),
        ("Read messages aloud", "On" if row.read_messages_aloud else "Off"),
    )
    return lines, previews, True


def _capability_reads(
    lines: tuple[summary_service.CapabilityLine, ...],
) -> list[CapabilityLineRead]:
    return [
        CapabilityLineRead(
            key=line.key,
            label=line.label,
            state=line.state,
            state_label=line.state_label,
        )
        for line in lines
    ]


def _export_read(export: DataExport, now: datetime) -> ExportRead:
    """One export row, with its expiry already compared.

    ``downloadable`` is derived here rather than left to the client, which is
    PRD 11's rule for expiry: the server decides, every read.
    """
    expired = export_service.is_expired(export, now)
    stored = cast(ExportStatusValue, export.status)
    status: ExportStatusValue = "expired" if expired and stored == "ready" else stored
    categories = export.categories or {}
    return ExportRead(
        id=export.id,
        status=status,
        status_label=wording.EXPORT_STATUS_LABELS[status],
        requested_at=export.requested_at,
        generated_at=export.generated_at,
        expires_at=export.expires_at,
        byte_size=export.byte_size,
        file_count=export.file_count,
        schema_version=export.schema_version,
        included_categories=list(categories.get("included", [])),
        excluded_categories=list(categories.get("excluded", [])),
        failure_reason=export.failure_reason,
        downloadable=status == "ready",
    )


# --- the hub (section 4) -----------------------------------------------------


@router.get("/summary", response_model=PrivacySummaryRead)
def read_privacy_summary(
    profile: OwnedProfile, db: DbSession, now: Now
) -> PrivacySummaryRead:
    """Everything the Privacy & Security screen shows, in one request.

    One request rather than eight, for the same reason PRD 3's Today is one:
    a privacy screen that arrives in pieces is a privacy screen that shows
    somebody a half-answer about who can see their data.
    """
    robot_lines, previews, linked = _robot_rows(db, profile.id, now)
    data = summary_service.build_summary(
        db,
        profile.id,
        now,
        robot_capabilities=robot_lines,
        robot_previews=previews,
        robot_linked=linked,
    )
    return PrivacySummaryRead(
        profile_id=data.profile_id,
        assistant_mode=data.assistant_mode,
        privacy_mode=data.privacy_mode,
        privacy_mode_note=data.privacy_mode_note,
        privacy_mode_limit=data.privacy_mode_limit,
        microphone_note=data.microphone_note,
        camera_note=data.camera_note,
        photo_permission_note=data.photo_permission_note,
        robot_input_capabilities=_capability_reads(data.robot_input_capabilities),
        memory_count=data.memory_count,
        active_memory_count=data.active_memory_count,
        conversation_count=data.conversation_count,
        caregivers=[
            CaregiverAccessRead(
                relationship_id=line.relationship_id,
                name=line.name,
                role=line.role,
                granted=list(line.granted),
                accepted_at=line.accepted_at,
            )
            for line in data.caregivers
        ],
        safety_monitoring_active=data.safety_monitoring_active,
        safety_capabilities=_capability_reads(data.safety_capabilities),
        robot_linked=data.robot_linked,
        robot_capabilities=_capability_reads(data.robot_capabilities),
        robot_previews=[[label, value] for label, value in data.robot_previews],
        external_capabilities=_capability_reads(data.external_capabilities),
        latest_export=(
            None if data.latest_export is None else _export_read(data.latest_export, now)
        ),
        export_note=data.export_note,
        export_privacy_note=data.export_privacy_note,
        deletion_warning=data.deletion_warning,
        deletion_keeps=data.deletion_keeps,
        deletion_reauth_limitation=data.deletion_reauth_limitation,
        data_categories=list(data.data_categories),
        security_statements=list(data.security_statements),
        build_honesty_note=data.build_honesty_note,
    )


# --- conversations (section 7) ----------------------------------------------


@router.post("/conversations/delete-all", response_model=ConversationsDeletedRead)
def delete_all_conversations(
    profile: OwnedProfile, db: DbSession
) -> ConversationsDeletedRead:
    """Removes every conversation on this profile (section 7).

    A ``POST`` rather than a ``DELETE`` on a collection, because it is an
    action with a result somebody reads -- how many went -- and because a
    bare ``DELETE /conversations`` is one mistyped URL away from a client that
    meant to delete one.

    It takes nothing else with it. Section 7 is explicit, and the test asserts
    the memory and health-record counts either side.
    """
    deleted = summary_service.delete_all_conversations(db, profile.id)
    return ConversationsDeletedRead(deleted=deleted, note=wording.CONVERSATIONS_NOTE)


# --- export (sections 17-20 and 43) -----------------------------------------


@router.get("/export", response_model=ExportListRead)
def list_exports(profile: OwnedProfile, db: DbSession, now: Now) -> ExportListRead:
    """Every export this profile has asked for, newest first."""
    return ExportListRead(
        exports=[
            _export_read(export, now)
            for export in export_service.list_exports(db, profile.id)
        ],
        note=wording.EXPORT_NOTE,
        privacy_note=wording.EXPORT_PRIVACY_NOTE,
        secrets_note=wording.EXPORT_SECRETS_NOTE,
        sections=list(DATA_EXPORT_SECTIONS),
    )


@router.post("/export", response_model=ExportRead, status_code=CREATED)
def create_export(
    profile: OwnedProfile, user: CurrentUser, db: DbSession, now: Now
) -> ExportRead:
    """Builds an archive now (sections 18 and 43).

    Synchronous: see ``services.privacy.export``. The response is the finished
    row, so a client never has to poll -- and ``requested``/``generating``
    never appear in this build.

    The account comes from ``CurrentUser`` -- the verified token -- rather than
    from the profile's links. ``OwnedProfile`` has already established that
    this account owns this profile, and reading the id back off the row would
    be choosing one of several links rather than using the one that
    authorized the request.
    """
    try:
        export = export_service.create_export(
            db, profile, user.id, get_object_store(), now
        )
    except DomainError as error:
        raise http_error(error) from error
    return _export_read(export, now)


@router.get("/export/{export_id}", response_model=ExportRead)
def read_export(
    export_id: uuid.UUID, profile: OwnedProfile, db: DbSession, now: Now
) -> ExportRead:
    try:
        export = export_service.get_export(db, profile.id, export_id)
    except DomainError as error:
        raise http_error(error) from error
    return _export_read(export, now)


@router.get(
    "/export/{export_id}/content",
    response_class=Response,
    responses={
        200: {
            "content": {"application/zip": {}},
            "description": "The archive bytes.",
        }
    },
)
def download_export(
    export_id: uuid.UUID, profile: OwnedProfile, db: DbSession, now: Now
) -> Response:
    """The archive itself (sections 18 and 27).

    An authenticated route and no signed URL, exactly as PRD 6 chose for a
    symptom photo and PRD 7 for a report: a signed URL is a bearer token in a
    query string, and this one would be a bearer token for somebody's entire
    record. The profile is re-checked for every byte, and the expiry is
    compared here as well as in the service.

    ``no-store`` because a cached copy of a complete health export in a shared
    proxy is the worst version of the thing this route exists to prevent.
    """
    try:
        export = export_service.get_export(db, profile.id, export_id)
        data = export_service.read_archive(db, export, get_object_store(), now)
    except DomainError as error:
        raise http_error(error) from error

    return Response(
        content=data,
        media_type="application/zip",
        headers={
            "Cache-Control": "private, no-store",
            "Content-Disposition": f'attachment; filename="nura-export-{export.id}.zip"',
            "Content-Length": str(len(data)),
        },
    )


@router.delete("/export/{export_id}", status_code=NO_CONTENT)
def delete_export(export_id: uuid.UUID, profile: OwnedProfile, db: DbSession) -> None:
    """Removes the row and the bytes (section 43)."""
    try:
        export = export_service.get_export(db, profile.id, export_id)
    except DomainError as error:
        raise http_error(error) from error
    export_service.delete_export(db, export, get_object_store())


# --- deletion (sections 21-24 and 44) ---------------------------------------


@router.post("/delete-request", response_model=DeletionInventoryRead)
def request_deletion(
    profile: OwnedProfile, user: CurrentUser, db: DbSession
) -> DeletionInventoryRead:
    """What deleting this profile would remove. Changes nothing.

    A ``POST`` because section 44 names it one, and harmless because it only
    counts. The counts come from the database, so the warning a person reads
    is the scope the service actually has rather than a paragraph somebody
    wrote once.
    """
    data = deletion_service.inventory(db, profile, user.id)
    return DeletionInventoryRead(
        profile_id=data.profile_id,
        profile_name=data.profile_name,
        rows=data.rows,
        row_total=data.row_total,
        file_count=data.file_count,
        caregiver_count=data.caregiver_count,
        device_count=data.device_count,
        other_profile_count=data.other_profile_count,
        title=wording.DELETION_TITLE,
        warning=wording.DELETION_WARNING,
        keeps=wording.DELETION_KEEPS,
        reauth_limitation=wording.DELETION_REAUTH_LIMITATION,
        confirm_prompt=wording.DELETION_CONFIRM_PROMPT,
        confirmation_phrase=deletion_service.CONFIRMATION_PHRASE,
    )


@router.post("/delete-confirm", response_model=DeletionResultRead)
def confirm_deletion(
    payload: DeletionConfirm,
    profile: OwnedProfile,
    user: CurrentUser,
    db: DbSession,
    now: Now,
) -> DeletionResultRead:
    """Deletes this profile's data (sections 22, 23 and 44).

    Both halves of the confirmation are required: the exact phrase, and an
    explicit acknowledgement. Neither has a default, so an empty body cannot
    satisfy this.
    """
    if not payload.acknowledged:
        raise http_error(
            deletion_service.DeletionNotConfirmedError(
                "Confirm that you understand this cannot be undone."
            )
        )
    try:
        result = deletion_service.delete_profile(
            db,
            profile,
            user.id,
            get_object_store(),
            now,
            confirmation=payload.confirmation_phrase,
        )
    except DomainError as error:
        raise http_error(error) from error

    remaining = len(
        db.execute(
            select(AccountProfileRole.profile_id.distinct()).where(
                AccountProfileRole.account_id == user.id
            )
        ).all()
    )
    return DeletionResultRead(
        profile_id=result.profile_id,
        rows_deleted=result.rows_deleted,
        files_deleted=result.files_deleted,
        files_missing=result.files_missing,
        caregivers_revoked=result.caregivers_revoked,
        devices_unlinked=result.devices_unlinked,
        completed_at=result.completed_at,
        other_profiles_remaining=remaining,
    )
