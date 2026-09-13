"""Robot pairing, claiming and presence (PRD 2, section 33).

Two kinds of caller use this router, and they authenticate differently:

- **The app**, with the user's access token: provisioning sessions, listing,
  renaming, status and completing setup.
- **The robot**, over its own Wi-Fi connection: ``/claim`` with a
  provisioning token, then ``/heartbeat`` with the device token it received.

Authorization rule for app routes: a device is reachable only if the signed-in
account claimed it. Anything else is 404, not 403, so ids are not confirmed to
exist -- the same rule as profiles.
"""

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.deps import CurrentDevice, CurrentUser, DbSession
from app.core.config import Settings, get_settings
from app.models import Device, ProvisioningSession, User
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
from app.services import devices as device_service

router = APIRouter(prefix="/devices", tags=["devices"])


def current_time() -> datetime:
    """The clock, as a dependency so tests can move it."""
    return datetime.now(UTC)


Now = Annotated[datetime, Depends(current_time)]
AppSettings = Annotated[Settings, Depends(get_settings)]

DEVICE_NOT_FOUND = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND,
    detail={"code": "device_not_found", "message": "Device not found."},
)


def _http_error(error: device_service.ProvisioningError) -> HTTPException:
    """A rule refusal as ``{"detail": {"code", "message"}}``.

    The code is what the app and firmware branch on; the message is safe to
    show, but clients use their own wording.
    """
    return HTTPException(
        status_code=error.status_code,
        detail={"code": error.code, "message": error.message},
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
        raise _http_error(error) from error

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
        raise _http_error(error) from error

    return DeviceClaimed(
        device_id=device.id,
        device_token=device_token,
        heartbeat_interval_seconds=device_service.SETUP_HEARTBEAT_INTERVAL_SECONDS,
    )


@router.post("/heartbeat", response_model=HeartbeatRead)
def heartbeat(
    payload: HeartbeatCreate, device: CurrentDevice, db: DbSession, now: Now
) -> HeartbeatRead:
    """The robot's periodic "I'm online" (PRD 2, section 35)."""
    result = device_service.record_heartbeat(
        db,
        device,
        firmware_version=payload.firmware_version,
        introduction_played=payload.introduction_played,
        now=now,
    )
    return HeartbeatRead(
        heartbeat_interval_seconds=result.heartbeat_interval_seconds,
        introduce=result.introduce,
        server_time=now,
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
        raise _http_error(error) from error
    return _device_read(device, now)
