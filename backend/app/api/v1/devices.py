"""Robot pairing, claiming and presence (PRD 2, section 33).

Two kinds of caller use this router, and they authenticate differently:

- **The app**, with the user's access token: provisioning sessions, listing,
  renaming, status and completing setup.
- **The robot**, over its own Wi-Fi connection: ``/claim`` with a
  provisioning token, then ``/heartbeat`` with the device token it received.

Authorization rule for app routes: a device is reachable only if the signed-in
account claimed it. Anything else is 404, not 403, so ids are not confirmed to
exist -- the same rule as profiles.

PRD 11 adds the robot's display and companion behaviour to the same prefix:
capabilities, presentation preferences, presentation history and the Nura
Device screen's own status read. They are here rather than in a router of their
own so that the authorization rule above is applied in one place for every
route that names a device -- and so that the absence of any caregiver path is
visible at a glance, which is PRD 11 section 70.
"""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.deps import (
    CurrentDevice,
    CurrentUser,
    DbSession,
    Now,
    current_time,
    http_error,
)
from app.core.config import Settings, get_settings
from app.models import (
    Device,
    DevicePresentation,
    DevicePresentationPreferences,
    ProvisioningSession,
    User,
)
from app.schemas.device import (
    DeviceClaim,
    DeviceClaimed,
    DeviceRead,
    DeviceStatusRead,
    DeviceUpdate,
    HeartbeatCreate,
    HeartbeatRead,
    ProvisioningSessionCreate,
    ProvisioningSessionCreated,
    ProvisioningSessionRead,
)
from app.schemas.robot import (
    CapabilitiesRead,
    CapabilityRead,
    PresentationHistoryRead,
    PresentationPreferencesRead,
    PresentationPreferencesUpdate,
    PresentationRead,
    RobotStatusRead,
)
from app.services import devices as device_service
from app.services.errors import DomainError
from app.services.robot import capabilities as robot_capabilities
from app.services.robot import preferences as robot_preferences
from app.services.robot import presenter as robot_presenter
from app.services.robot import queue as robot_queue
from app.services.robot import wording as robot_wording

router = APIRouter(prefix="/devices", tags=["devices"])


#: Re-exported so ``app.api.v1.devices.current_time`` keeps working as the
#: dependency tests override.
__all__ = ["current_time", "router"]

AppSettings = Annotated[Settings, Depends(get_settings)]

DEVICE_NOT_FOUND = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND,
    detail={"code": "device_not_found", "message": "Device not found."},
)


def _owned_device(user: User, device_id: uuid.UUID) -> Device:
    for device in user.devices:
        if device.id == device_id:
            return device
    raise DEVICE_NOT_FOUND


def _device_read(device: Device, now: datetime) -> DeviceRead:
    return DeviceRead(
        id=device.id,
        hardware_id=device.hardware_id,
        display_name=device.display_name,
        device_type=device.device_type,
        firmware_version=device.firmware_version,
        provisioning_status=device.provisioning_status,  # type: ignore[arg-type]
        connection_status=device_service.connection_status(device, now),  # type: ignore[arg-type]
        last_seen_at=device.last_seen_at,
        claimed_at=device.claimed_at,
        setup_completed_at=device.setup_completed_at,
        introduced_at=device.introduced_at,
        owner_profile_id=device.owner_profile_id,
        created_at=device.created_at,
        updated_at=device.updated_at,
    )


def _device_api_base_url(settings: Settings, request: Request) -> str:
    """Where the robot should call once it is on Wi-Fi.

    In development the phone reached us on the computer's LAN address, which
    the robot on the same Wi-Fi can reach too, so that address is used when
    nothing is configured. A deployed backend must say explicitly.
    """
    if settings.device_api_base_url:
        return settings.device_api_base_url.rstrip("/")
    if settings.is_development:
        return str(request.base_url).rstrip("/")
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={
            "code": "device_api_not_configured",
            "message": "DEVICE_API_BASE_URL is not set on this server.",
        },
    )


# --- app: provisioning sessions ----------------------------------------------


@router.post(
    "/provisioning-sessions",
    response_model=ProvisioningSessionCreated,
    status_code=status.HTTP_201_CREATED,
)
def create_provisioning_session(
    payload: ProvisioningSessionCreate,
    user: CurrentUser,
    db: DbSession,
    request: Request,
    settings: AppSettings,
    now: Now,
) -> ProvisioningSessionCreated:
    """Issues a short-lived, single-use token for one robot (PRD 2, section 32)."""
    base_url = _device_api_base_url(settings, request)
    try:
        session, token = device_service.create_provisioning_session(
            db, user, payload.hardware_id, payload.profile_id, now
        )
    except device_service.ProvisioningError as error:
        raise http_error(error) from error

    return ProvisioningSessionCreated(
        id=session.id,
        hardware_id=session.hardware_id,
        provisioning_token=token,
        expires_at=session.expires_at,
        device_api_base_url=base_url,
    )


@router.get("/provisioning-sessions/{session_id}", response_model=ProvisioningSessionRead)
def read_provisioning_session(
    session_id: uuid.UUID, user: CurrentUser, db: DbSession, now: Now
) -> ProvisioningSessionRead:
    """Has the robot claimed yet? Polled while the robot joins Wi-Fi."""
    session = db.get(ProvisioningSession, session_id)
    if session is None or session.account_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "session_not_found", "message": "Setup session not found."},
        )
    return ProvisioningSessionRead(
        id=session.id,
        hardware_id=session.hardware_id,
        state=device_service.session_state(session, now),  # type: ignore[arg-type]
        expires_at=session.expires_at,
        device_id=session.device_id,
    )


# --- robot: claim and heartbeat ---------------------------------------------


@router.post("/claim", response_model=DeviceClaimed)
def claim_device(payload: DeviceClaim, db: DbSession, now: Now) -> DeviceClaimed:
    """Called by the robot once it is on Wi-Fi (PRD 2, section 29).

    No user token is involved: the provisioning token proves the account
    agreed, and the bootstrap secret proves which physical robot is asking.
    """
    try:
        device, device_token = device_service.claim_device(
            db,
            hardware_id=payload.hardware_id,
            provisioning_token=payload.provisioning_token,
            bootstrap_secret=payload.bootstrap_secret,
            firmware_version=payload.firmware_version,
            now=now,
        )
    except device_service.ProvisioningError as error:
        raise http_error(error) from error

    return DeviceClaimed(
        device_id=device.id,
        device_token=device_token,
        heartbeat_interval_seconds=device_service.SETUP_HEARTBEAT_INTERVAL_SECONDS,
    )


@router.post("/heartbeat", response_model=HeartbeatRead)
def heartbeat(
    payload: HeartbeatCreate, device: CurrentDevice, db: DbSession, now: Now
) -> HeartbeatRead:
    """The robot's periodic "I'm online" (PRD 2, section 35).

    PRD 11 section 58 asks for the existing heartbeat to be extended rather
    than a second transport added, so this reconciles the robot's queue and
    answers whether there is anything to fetch. It carries the *flag* and not
    the presentation: a heartbeat is retried and logged, and section 67 keeps
    payloads out of anything that is.

    Reconciliation here is also what makes the flag trustworthy -- the answer
    is built from what is true now, so a robot is never told to fetch a
    reminder for a dose that has since been taken.
    """
    result = device_service.record_heartbeat(
        db,
        device,
        firmware_version=payload.firmware_version,
        introduction_played=payload.introduction_played,
        now=now,
    )
    pending = False
    if device.owner_profile_id is not None:
        robot_presenter.refresh(db, device, now, assume_online=True)
        pending = robot_queue.has_pending(db, device.id, now)
        db.commit()
    return HeartbeatRead(
        heartbeat_interval_seconds=result.heartbeat_interval_seconds,
        introduce=result.introduce,
        server_time=now,
        presentation_pending=pending,
    )


# --- app: the account's devices ---------------------------------------------


@router.get("", response_model=list[DeviceRead])
def list_devices(user: CurrentUser, now: Now) -> list[DeviceRead]:
    """Robots claimed by the signed-in account, oldest first."""
    return [
        _device_read(device, now)
        for device in sorted(user.devices, key=lambda device: device.created_at)
    ]


@router.get("/{device_id}", response_model=DeviceRead)
def read_device(device_id: uuid.UUID, user: CurrentUser, now: Now) -> DeviceRead:
    return _device_read(_owned_device(user, device_id), now)


@router.patch("/{device_id}", response_model=DeviceRead)
def update_device(
    device_id: uuid.UUID,
    payload: DeviceUpdate,
    user: CurrentUser,
    db: DbSession,
    now: Now,
) -> DeviceRead:
    """Renames a robot. The name is a label only (PRD 2, section 37)."""
    device = _owned_device(user, device_id)
    device.display_name = payload.display_name
    db.commit()
    db.refresh(device)
    return _device_read(device, now)


@router.get("/{device_id}/status", response_model=DeviceStatusRead)
def read_device_status(
    device_id: uuid.UUID, user: CurrentUser, now: Now
) -> DeviceStatusRead:
    device = _owned_device(user, device_id)
    return DeviceStatusRead(
        device_id=device.id,
        connection_status=device_service.connection_status(device, now),  # type: ignore[arg-type]
        last_seen_at=device.last_seen_at,
        checked_in_since_claim=device_service.has_checked_in_since_claim(device),
        online_threshold_seconds=int(device_service.ONLINE_THRESHOLD.total_seconds()),
        provisioning_status=device.provisioning_status,  # type: ignore[arg-type]
        firmware_version=device.firmware_version,
        setup_completed=device.setup_completed_at is not None,
        introduction_pending=device.introduction_requested_at is not None,
    )


@router.post("/{device_id}/complete-setup", response_model=DeviceRead)
def complete_setup(
    device_id: uuid.UUID, user: CurrentUser, db: DbSession, now: Now
) -> DeviceRead:
    """Finishes first-time setup once the robot is genuinely online.

    PRD 2, sections 36-41.
    """
    device = _owned_device(user, device_id)
    try:
        device = device_service.complete_setup(db, user, device, now)
    except device_service.ProvisioningError as error:
        raise http_error(error) from error
    return _device_read(device, now)


# --- app: the robot's display and companion behaviour (PRD 11) --------------
#
# These share the ``/devices/{device_id}`` prefix and ``_owned_device`` with
# everything above, which is the point of putting them here rather than in a
# router of their own: PRD 2's rule -- a device is reachable only if the
# signed-in account claimed it, and anything else is a 404 -- is applied in one
# place for every route that names a device. PRD 11 section 69 adds nothing to
# it, and section 70 is satisfied by what is absent: a caregiver has no route
# here at all, because a caregiver scope is never resolved in this file.


def _presentation_read(row: DevicePresentation) -> PresentationRead:
    """One presentation, with its own payload's title and summary.

    The payload was already reduced to the privacy level in force when the
    builder stored it (PRD 11, section 22), so reading it back cannot reveal
    more than the robot was sent.
    """
    title, summary = robot_wording.summary_of(row.payload)
    return PresentationRead(
        id=row.id,
        presentation_type=row.presentation_type,  # type: ignore[arg-type]
        status=row.status,  # type: ignore[arg-type]
        layout=row.layout,  # type: ignore[arg-type]
        source=row.source,  # type: ignore[arg-type]
        priority=row.priority,
        title=title,
        summary=summary,
        sensitive=bool(row.payload.get("sensitive")),
        created_at=row.created_at,
        available_at=row.available_at,
        expires_at=row.expires_at,
        sent_at=row.sent_at,
        displayed_at=row.displayed_at,
        completed_at=row.completed_at,
        ack_state=row.ack_state,  # type: ignore[arg-type]
        failure_code=row.failure_code,  # type: ignore[arg-type]
        cancel_reason=row.cancel_reason,  # type: ignore[arg-type]
        line=robot_wording.history_line(
            presentation_type=row.presentation_type,
            status=row.status,
            failure_code=row.failure_code,
            cancel_reason=row.cancel_reason,
        ),
    )


def _capability_read(view: robot_capabilities.CapabilityView) -> CapabilityRead:
    return CapabilityRead(
        key=view.key,  # type: ignore[arg-type]
        state=view.state,  # type: ignore[arg-type]
        reported_state=view.reported_state,  # type: ignore[arg-type]
        label=robot_wording.CAPABILITY_LABELS[view.key],
        state_label=robot_wording.CAPABILITY_STATE_LABELS[view.state],
        source=view.source,  # type: ignore[arg-type]
        reported_at=view.reported_at,
        firmware_version=view.firmware_version,
        stale=view.stale,
    )


def _preferences_read(
    device: Device,
    row: DevicePresentationPreferences,
    resolved: robot_preferences.EffectivePreferences,
) -> PresentationPreferencesRead:
    return PresentationPreferencesRead(
        device_id=device.id,
        brightness=row.brightness,
        volume=row.volume,
        reduced_motion=row.reduced_motion,
        effective_reduced_motion=resolved.reduced_motion,
        medication_privacy_level=row.medication_privacy_level,  # type: ignore[arg-type]
        read_medications_aloud=row.read_medications_aloud,
        read_messages_aloud=row.read_messages_aloud,
        read_assistant_aloud=row.read_assistant_aloud,
        sleep_screen_mode=row.sleep_screen_mode,  # type: ignore[arg-type]
        face_animation_enabled=row.face_animation_enabled,
        family_message_display_enabled=row.family_message_display_enabled,
        daily_life_privacy_level=row.daily_life_privacy_level,  # type: ignore[arg-type]
        daily_life_display_enabled=row.daily_life_display_enabled,
        updated_at=row.updated_at,
    )


@router.get("/{device_id}/capabilities", response_model=CapabilitiesRead)
def read_device_capabilities(
    device_id: uuid.UUID, user: CurrentUser, db: DbSession, now: Now
) -> CapabilitiesRead:
    """What this robot has told us it can do (PRD 11, sections 10 and 122).

    Every one of the twelve keys is returned, including the ones nothing has
    ever reported -- a client that only saw the keys that happened to be
    present would silently stop asking about one somebody added. The booleans
    underneath are derived from the same states, so a settings screen cannot
    decide for itself that audio is available (section 47).
    """
    device = _owned_device(user, device_id)
    views = robot_capabilities.views(db, device, now)
    states = {view.key: view.state for view in views}
    return CapabilitiesRead(
        device_id=device.id,
        capabilities=[_capability_read(view) for view in views],
        display_available=states.get("display") == "available",
        text_available=robot_capabilities.can_show_text(states),
        animation_available=robot_capabilities.can_animate(states),
        audio_available=robot_capabilities.has_audio(states),
        speech_available=robot_capabilities.can_speak(states),
        input_available=robot_capabilities.has_input(states),
        hardware_note=robot_wording.NO_HARDWARE_NOTE,
    )


@router.get(
    "/{device_id}/presentation-preferences",
    response_model=PresentationPreferencesRead,
)
def read_presentation_preferences(
    device_id: uuid.UUID, user: CurrentUser, db: DbSession, now: Now
) -> PresentationPreferencesRead:
    """How this robot should behave (PRD 11, sections 48 and 49).

    Answered for a robot that cannot do any of it, which is section 49: a
    person may configure what should happen when a speaker exists, and the
    answer does not imply that one does. The capability endpoint is where that
    question is asked.
    """
    device = _owned_device(user, device_id)
    row, resolved = robot_preferences.resolved_for(db, device, now)
    db.commit()
    db.refresh(row)
    return _preferences_read(device, row, resolved)


@router.patch(
    "/{device_id}/presentation-preferences",
    response_model=PresentationPreferencesRead,
)
def update_presentation_preferences(
    device_id: uuid.UUID,
    payload: PresentationPreferencesUpdate,
    user: CurrentUser,
    db: DbSession,
    now: Now,
) -> PresentationPreferencesRead:
    """Changes one or more settings (PRD 11, sections 46 and 48).

    ``model_fields_set`` rather than "drop the nulls", because
    ``reduced_motion`` has three meaningful values and ``null`` is one of
    them: it means *follow my accessibility setting* (sections 30 and 105).
    Filtering nulls out would have made that value unreachable from the app.
    """
    device = _owned_device(user, device_id)
    row = robot_preferences.get_or_create(db, device, now)
    changes = {field: getattr(payload, field) for field in payload.model_fields_set}
    try:
        robot_preferences.update(db, row, changes, now)
    except DomainError as error:
        raise http_error(error) from error
    resolved = robot_preferences.effective(db, device, row)
    db.commit()
    db.refresh(row)
    return _preferences_read(device, row, resolved)


@router.get("/{device_id}/presentation-history", response_model=PresentationHistoryRead)
def read_presentation_history(
    device_id: uuid.UUID, user: CurrentUser, db: DbSession, now: Now
) -> PresentationHistoryRead:
    """What has been put in front of this robot, most recent first (section 96).

    Expiry runs first, so a row whose moment has passed reads as ``expired``
    rather than as ``waiting`` -- the same read-makes-it-true arrangement PRD 5
    uses for doses and PRD 10 for monitoring.
    """
    device = _owned_device(user, device_id)
    robot_queue.expire_due(db, now, device.id)
    rows = robot_queue.history(db, device.id)
    db.commit()
    return PresentationHistoryRead(
        presentations=[_presentation_read(row) for row in rows]
    )


@router.get("/{device_id}/robot-status", response_model=RobotStatusRead)
def read_robot_status(
    device_id: uuid.UUID, user: CurrentUser, db: DbSession, now: Now
) -> RobotStatusRead:
    """One request for the whole Nura Device screen (PRD 11, sections 46, 65).

    Not in section 122's list, which covers the four endpoints the protocol
    needs; this is the screen's own read, assembled server-side for the reason
    PRD 10 assembles its safety status there: the mode, the queue depth and
    the current card are three facts that have to agree, and working them out
    in a client is how two screens come to disagree about whether a robot is
    asleep.

    Reconciliation runs first (``presenter.refresh``), so what the screen shows
    is what the robot would be handed if it asked right now.
    """
    device = _owned_device(user, device_id)
    result = robot_presenter.refresh(db, device, now)
    current = next(
        (
            row
            for row in robot_queue.open_presentations(db, device.id)
            if row.status == "displayed"
        ),
        None,
    )
    db.commit()
    connection = device_service.connection_status(device, now)
    return RobotStatusRead(
        device_id=device.id,
        display_name=device.display_name,
        connection_status=connection,  # type: ignore[arg-type]
        last_seen_at=device.last_seen_at,
        mode=result.mode.mode,  # type: ignore[arg-type]
        mode_label=robot_wording.MODE_LABELS[result.mode.mode],
        face=result.mode.face,
        queue_depth=result.queue_depth,
        current=_presentation_read(current) if current is not None else None,
        setup_complete=device.setup_completed_at is not None,
        offline_note=None if connection == "online" else robot_wording.OFFLINE_NOTE,
    )
