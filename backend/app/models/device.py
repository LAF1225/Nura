"""Devices and provisioning sessions -- Nura robots (PRD 2, sections 29-35).

See ``docs/device/provisioning-protocol.md`` for the full flow. In short: the
app asks for a short-lived provisioning session, hands its token to the robot
over verified BLE, and the robot exchanges that token for a device record and
its own long-lived device token.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.enums import DEVICE_PROVISIONING_STATUSES, sql_in_list
from app.models.user import User

if TYPE_CHECKING:
    from app.models.profile import Profile

#: The hardware Nura is built around (PRD 0, section 17).
DEVICE_TYPE_XIAO_ESP32S3 = "xiao-esp32-s3"

#: `NURA-` followed by the 12 hex digits of the ESP32-S3 factory MAC.
HARDWARE_ID_PATTERN = r"^NURA-[0-9A-F]{12}$"
HARDWARE_ID_LENGTH = 17


class Device(Base, TimestampMixin):
    """A Nura robot that has reached the backend at least once.

    Identity rules (PRD 0, section 17; PRD 2, section 37):
      - ``id`` is an internal UUID and is the stable identity.
      - ``hardware_id`` comes from the hardware itself and is what BLE
        discovery reports. It is unique but is not the primary key.
      - ``display_name`` is user-facing and editable ("Bedroom Nura"). It is
        never identity, and it is not the owner's own name.

    Credentials are stored only as SHA-256 hashes. Neither the bootstrap
    secret nor the device token can be recovered from this table.
    """

    __tablename__ = "devices"
    __table_args__ = (
        CheckConstraint(
            f"provisioning_status IN {sql_in_list(DEVICE_PROVISIONING_STATUSES)}",
            name="ck_devices_provisioning_status",
        ),
        CheckConstraint(
            f"hardware_id ~ '{HARDWARE_ID_PATTERN}'", name="ck_devices_hardware_id"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    hardware_id: Mapped[str] = mapped_column(
        String(HARDWARE_ID_LENGTH), nullable=False, unique=True, index=True
    )
    #: The account that claimed the robot. Nullable so a future ownership
    #: release can unlink it without losing the device's identity record.
    claimed_by_account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    #: The person this Nura is for. In assisted setup that is not the account
    #: holder (PRD 1, section 28).
    owner_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="SET NULL")
    )
    display_name: Mapped[str] = mapped_column(
        String(64), nullable=False, server_default="Nura"
    )
    device_type: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=DEVICE_TYPE_XIAO_ESP32S3
    )
    firmware_version: Mapped[str | None] = mapped_column(String(32))
    provisioning_status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="claimed"
    )

    #: Hash of the secret the robot generated on first boot. Every later claim
    #: must present the same secret (prototype trust on first claim).
    bootstrap_secret_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    #: Hash of the robot's current device token. Rotated on every claim.
    device_token_hash: Mapped[str | None] = mapped_column(String(64), unique=True)

    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: Last heartbeat. Null until the robot first checks in with its token.
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    setup_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: Set when the app finishes setup; cleared once the robot has played it.
    introduction_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    introduced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    claimed_by: Mapped[User | None] = relationship(back_populates="devices")
    owner_profile: Mapped["Profile | None"] = relationship()


class ProvisioningSession(Base, TimestampMixin):
    """A short-lived permission for one robot to join one account (PRD 2, section 32).

    The token itself is shown to the app exactly once and stored only as a
    hash. It expires quickly, can be consumed by a single claim, and is bound
    to the ``hardware_id`` the app read over verified BLE.
    """

    __tablename__ = "provisioning_sessions"
    __table_args__ = (
        CheckConstraint(
            f"hardware_id ~ '{HARDWARE_ID_PATTERN}'",
            name="ck_provisioning_sessions_hardware_id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    profile_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="SET NULL")
    )
    hardware_id: Mapped[str] = mapped_column(
        String(HARDWARE_ID_LENGTH), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    device_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("devices.id", ondelete="SET NULL")
    )

    account: Mapped[User] = relationship()
    device: Mapped[Device | None] = relationship()
