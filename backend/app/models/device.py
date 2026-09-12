"""Device -- a Nura robot belonging to a user (PRD 0, sections 16 and 17)."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.user import User

#: The hardware Nura is built around (PRD 0, section 17).
DEVICE_TYPE_XIAO_ESP32S3 = "xiao-esp32-s3"


class Device(Base, TimestampMixin):
    """A paired Nura unit.

    Identity rules (PRD 0, section 17):
      - ``id`` is an internal UUID and is the stable identity.
      - ``device_identifier`` is provisioned on the hardware itself and is what
        BLE discovery reports. It is unique but is not the primary key.
      - ``display_name`` is user-facing and editable ("Bedroom Nura"). It is
        never identity, and it is not the owner's own name.
    """

    __tablename__ = "devices"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    device_identifier: Mapped[str] = mapped_column(
        String(128), nullable=False, unique=True, index=True
    )
    display_name: Mapped[str] = mapped_column(String(64), nullable=False)
    device_type: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=DEVICE_TYPE_XIAO_ESP32S3
    )
    firmware_version: Mapped[str | None] = mapped_column(String(32))
    #: Last time the device contacted the backend. Null until it first checks in.
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    owner: Mapped[User] = relationship(back_populates="devices")
