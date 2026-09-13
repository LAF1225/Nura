"""Robot provisioning, claiming and presence rules (PRD 2, sections 29-36).

Everything that decides whether a robot may join an account lives here, so the
HTTP layer stays thin and the rules can be read -- and tested -- in one place.
The protocol these rules implement is written up in
``docs/device/provisioning-protocol.md``.
"""

import hashlib
import hmac
import logging
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models import Device, ProvisioningSession, User
from app.models.enums import ONBOARDING_STATUSES

logger = logging.getLogger(__name__)

PROVISIONING_TOKEN_PREFIX = "npt_"
DEVICE_TOKEN_PREFIX = "ndt_"

#: How long the app has to get the token to the robot and the robot to claim.
PROVISIONING_SESSION_TTL = timedelta(minutes=10)

#: Normal heartbeat cadence, and the faster one used while setup is finishing
#: so the introduction plays within seconds of the user tapping Continue.
HEARTBEAT_INTERVAL_SECONDS = 30
SETUP_HEARTBEAT_INTERVAL_SECONDS = 5
SETUP_WINDOW = timedelta(minutes=5)

#: Three missed heartbeats. Below this a robot is online (PRD 2, section 35).
ONLINE_THRESHOLD = timedelta(seconds=90)

DEFAULT_DISPLAY_NAME = "Nura"


class ProvisioningError(Exception):
    """A rule refused the request. ``code`` is stable and safe to show."""

    status_code = 400
    code = "provisioning_error"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class OnboardingIncompleteError(ProvisioningError):
    status_code = 409
    code = "onboarding_incomplete"


class AlreadyClaimedError(ProvisioningError):
    status_code = 409
    code = "already_claimed"


class ProvisioningTokenInvalidError(ProvisioningError):
    # One error for unknown, expired, consumed and mismatched tokens alike, so
    # a caller probing the endpoint learns nothing about which it was.
    status_code = 401
    code = "provisioning_token_invalid"


class IdentityMismatchError(ProvisioningError):
    status_code = 403
    code = "identity_mismatch"


class DeviceNotOnlineError(ProvisioningError):
    status_code = 409
    code = "device_not_online"


class ProfileNotFoundError(ProvisioningError):
    status_code = 404
    code = "profile_not_found"


# --- secrets ---------------------------------------------------------------


def generate_token(prefix: str) -> str:
    """256 random bits, URL-safe, with a prefix saying what kind of token it is."""
    return prefix + secrets.token_urlsafe(32)


def hash_secret(value: str) -> str:
    """SHA-256 hex digest. Tokens and secrets are only ever stored like this.

    A plain hash (not a password hash) is right here: every value hashed is
    256 bits of randomness, so there is nothing to brute-force.
    """
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def secret_matches(value: str, expected_hash: str) -> bool:
    return hmac.compare_digest(hash_secret(value), expected_hash)


# --- presence --------------------------------------------------------------


def connection_status(device: Device, now: datetime) -> str:
    """``unknown`` / ``online`` / ``offline``, from heartbeats alone.

    Computed on every read rather than stored, so it cannot go stale. Finishing
    BLE provisioning does not make a robot online (PRD 2, section 34); only a
    heartbeat does.
    """
    if device.last_seen_at is None:
        return "unknown"
    if now - device.last_seen_at <= ONLINE_THRESHOLD:
        return "online"
    return "offline"


def has_checked_in_since_claim(device: Device) -> bool:
    """True once the robot has sent a heartbeat with the token from its latest claim."""
    return (
        device.claimed_at is not None
        and device.last_seen_at is not None
        and device.last_seen_at >= device.claimed_at
    )


def account_has_connected_robot(user: User) -> bool:
    """The requirement for the ``robot_connected`` onboarding status."""
    return any(has_checked_in_since_claim(device) for device in user.devices)


# --- provisioning sessions --------------------------------------------------


def _default_profile_id(user: User) -> uuid.UUID | None:
    """The profile a new robot is for, when the app does not say.

    In assisted setup that is the person being helped, not the account holder.
    """
    preferred_role = "setup_helper" if user.setup_mode == "assisted" else "self"
    for link in user.profile_roles:
        if link.role == preferred_role:
            return link.profile_id
    return user.profile_roles[0].profile_id if user.profile_roles else None


def create_provisioning_session(
    db: Session,
    user: User,
    hardware_id: str,
    profile_id: uuid.UUID | None,
    now: datetime,
) -> tuple[ProvisioningSession, str]:
    """Issues a single-use token letting one robot join this account.

    Returns the session and the plaintext token. The token is not stored and
    cannot be retrieved again.
    """
    if ONBOARDING_STATUSES.index(user.onboarding_status) < ONBOARDING_STATUSES.index(
        "ready_for_pairing"
    ):
        # PRD 2, section 5: pairing starts only after PRD 1's flow is done.
        raise OnboardingIncompleteError("Finish setting up your account first.")

    if profile_id is not None:
        if not any(link.profile_id == profile_id for link in user.profile_roles):
            raise ProfileNotFoundError("Profile not found.")
    else:
        profile_id = _default_profile_id(user)

    existing = db.query(Device).filter(Device.hardware_id == hardware_id).one_or_none()
    if (
        existing is not None
        and existing.claimed_by_account_id is not None
        and existing.claimed_by_account_id != user.id
    ):
        # Refused before any Wi-Fi details are sent (PRD 2, section 31).
        raise AlreadyClaimedError("This Nura is already linked to another account.")

    token = generate_token(PROVISIONING_TOKEN_PREFIX)
    session = ProvisioningSession(
        account_id=user.id,
        profile_id=profile_id,
        hardware_id=hardware_id,
        token_hash=hash_secret(token),
        expires_at=now + PROVISIONING_SESSION_TTL,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    logger.info("devices: provisioning session created for %s", hardware_id)
    return session, token


def session_state(session: ProvisioningSession, now: datetime) -> str:
    """``claimed`` / ``expired`` / ``pending``, for the app to poll."""
    if session.consumed_at is not None:
        return "claimed"
    if session.expires_at <= now:
        return "expired"
    return "pending"


# --- claiming ---------------------------------------------------------------


def claim_device(
    db: Session,
    *,
    hardware_id: str,
    provisioning_token: str,
    bootstrap_secret: str,
    firmware_version: str | None,
    now: datetime,
) -> tuple[Device, str]:
    """Links a robot to the account behind a provisioning token.

    Called by the robot itself, over Wi-Fi. Returns the device and a freshly
    issued device token (plaintext, shown once).
    """
    session = (
        db.query(ProvisioningSession)
        .filter(ProvisioningSession.token_hash == hash_secret(provisioning_token))
        # Serialises two claims racing on the same token.
        .with_for_update()
        .one_or_none()
    )
    invalid = ProvisioningTokenInvalidError(
        "The setup session is invalid or has expired."
    )
    if session is None or session.hardware_id != hardware_id or session.expires_at <= now:
        raise invalid

    device = (
        db.query(Device)
        .filter(Device.hardware_id == hardware_id)
        .with_for_update()
        .one_or_none()
    )

    # A robot whose claim response was lost may retry with a consumed token, but
    # only if it is the robot that consumed it -- proven by the secret below.
    # Anyone else gets the generic refusal.
    if session.consumed_at is not None and (
        device is None or session.device_id != device.id
    ):
        raise invalid

    if device is not None:
        if not secret_matches(bootstrap_secret, device.bootstrap_secret_hash):
            logger.warning("devices: bootstrap secret mismatch for %s", hardware_id)
            raise IdentityMismatchError("This Nura's identity doesn't match our records.")
        if (
            device.claimed_by_account_id is not None
            and device.claimed_by_account_id != session.account_id
        ):
            raise AlreadyClaimedError("This Nura is already linked to another account.")
    else:
        device = Device(
            hardware_id=hardware_id,
            bootstrap_secret_hash=hash_secret(bootstrap_secret),
            display_name=DEFAULT_DISPLAY_NAME,
        )
        db.add(device)

    device_token = generate_token(DEVICE_TOKEN_PREFIX)
    device.claimed_by_account_id = session.account_id
    if session.profile_id is not None:
        device.owner_profile_id = session.profile_id
    device.provisioning_status = "claimed"
    device.device_token_hash = hash_secret(device_token)
    device.claimed_at = now
    if firmware_version:
        device.firmware_version = firmware_version

    db.flush()
    session.consumed_at = session.consumed_at or now
    session.device_id = device.id
    db.commit()
    db.refresh(device)
    logger.info("devices: %s claimed", hardware_id)
    return device, device_token


# --- heartbeats and setup completion ----------------------------------------


@dataclass(frozen=True)
class HeartbeatResult:
    heartbeat_interval_seconds: int
    introduce: bool


def record_heartbeat(
    db: Session,
    device: Device,
    *,
    firmware_version: str | None,
    introduction_played: bool,
    now: datetime,
) -> HeartbeatResult:
    device.last_seen_at = now
    if firmware_version:
        device.firmware_version = firmware_version

    if introduction_played and device.introduction_requested_at is not None:
        device.introduced_at = now
        device.introduction_requested_at = None

    introduce = device.introduction_requested_at is not None
    recently_claimed = (
        device.claimed_at is not None and now - device.claimed_at < SETUP_WINDOW
    )
    interval = (
        SETUP_HEARTBEAT_INTERVAL_SECONDS
        if introduce or recently_claimed
        else HEARTBEAT_INTERVAL_SECONDS
    )
    db.commit()
    return HeartbeatResult(heartbeat_interval_seconds=interval, introduce=introduce)


def complete_setup(db: Session, user: User, device: Device, now: datetime) -> Device:
    """Finishes first-time setup: introduction requested, onboarding advanced.

    Refused unless the backend has actually heard from the robot since its
    claim and it is online now (PRD 2, section 36).
    """
    # Imported here: the onboarding service imports this module.
    from app.services import onboarding as onboarding_service

    if (
        not has_checked_in_since_claim(device)
        or connection_status(device, now) != "online"
    ):
        raise DeviceNotOnlineError("Nura isn't online yet.")

    if device.setup_completed_at is None:
        device.setup_completed_at = now
    if device.introduced_at is None and device.introduction_requested_at is None:
        device.introduction_requested_at = now

    db.flush()
    onboarding_service.advance_to(user, "robot_connected")
    db.commit()
    db.refresh(device)
    return device
