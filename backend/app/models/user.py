"""User and UserSettings (PRD 0, section 16).

Foundational entities only. No diagnoses, medications, symptoms, allergies or
emergency events -- those belong to later PRDs.
"""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    # Import for typing only. At runtime `device.py` imports this module, so a
    # real import here would be circular; SQLAlchemy resolves the relationship
    # by name from its registry instead.
    from app.models.device import Device


class User(Base, TimestampMixin):
    """An account holder.

    ``id`` is Nura's own identifier and is the only thing other tables
    reference. ``auth_provider_id`` is the subject issued by the authentication
    provider; it is how a signed-in caller is matched to a row, and it is never
    accepted from a request body (PRD 0, section 18).
    """

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    auth_provider_id: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True, index=True
    )
    # Either may be absent: sign-up can happen by phone or by email.
    email: Mapped[str | None] = mapped_column(String(320), unique=True)
    phone: Mapped[str | None] = mapped_column(String(32), unique=True)

    settings: Mapped["UserSettings | None"] = relationship(
        back_populates="user", cascade="all, delete-orphan", uselist=False
    )
    devices: Mapped[list["Device"]] = relationship(
        back_populates="owner", cascade="all, delete-orphan"
    )


class UserSettings(Base, TimestampMixin):
    """Per-user preferences. Exactly one row per user."""

    __tablename__ = "user_settings"
    __table_args__ = (
        # The app only understands these three values; reject anything else at
        # the database level rather than trusting every writer.
        CheckConstraint(
            "theme IN ('system', 'light', 'dark')", name="ck_user_settings_theme"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    theme: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="system"
    )
    language: Mapped[str] = mapped_column(String(10), nullable=False, server_default="en")

    user: Mapped[User] = relationship(back_populates="settings")
