"""Account and per-account settings.

Naming note (PRD 1, sections 32-34): the table is still ``users`` because PRD 0
created it and renaming it would churn every reference, but conceptually a row
here is an **account holder** -- the identity that signs in. The *person Nura is
for* lives in ``profiles``, because in assisted setup they are not the same
person. ``AccountProfileRole`` joins the two.

Still foundational only: no diagnoses, medications, symptoms or allergies.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.enums import ONBOARDING_STATUSES, SETUP_MODES, THEMES, sql_in_list

#: ``HH:MM`` on a 24-hour clock.
REMINDER_TIME_PATTERN = r"^([01][0-9]|2[0-3]):[0-5][0-9]$"

if TYPE_CHECKING:
    # Import for typing only. At runtime these modules import this one, so a
    # real import here would be circular; SQLAlchemy resolves relationships by
    # name from its registry instead.
    from app.models.device import Device
    from app.models.profile import AccountProfileRole


class User(Base, TimestampMixin):
    """An account holder.

    ``id`` is Nura's own identifier and is the only thing other tables
    reference. ``auth_provider_id`` is the subject (``sub``) issued by the
    authentication provider; it is how a signed-in caller is matched to a row,
    and it is only ever read from a verified token -- never from a request body
    (PRD 1, section 36).
    """

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            f"setup_mode IS NULL OR setup_mode IN {sql_in_list(SETUP_MODES)}",
            name="ck_users_setup_mode",
        ),
        CheckConstraint(
            f"onboarding_status IN {sql_in_list(ONBOARDING_STATUSES)}",
            name="ck_users_onboarding_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    auth_provider_id: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True, index=True
    )
    # Either may be absent: sign-up can happen by phone or by email, and Apple's
    # private relay means an email is not guaranteed to be a real inbox.
    email: Mapped[str | None] = mapped_column(String(320), unique=True)
    phone: Mapped[str | None] = mapped_column(String(32), unique=True)

    # --- onboarding (PRD 1, sections 30 and 31) ---
    #: Null until the user answers "who are you setting up Nura for?".
    setup_mode: Mapped[str | None] = mapped_column(String(16))
    #: Single source of truth for onboarding progress. The step *number* shown
    #: in the UI ("Step 3 of 5") is derived from this rather than stored
    #: separately, so the two can never disagree about where to resume.
    onboarding_status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="not_started"
    )

    # --- consent (PRD 1, section 27) ---
    # Recorded as timestamps rather than booleans: knowing *when* someone
    # accepted is what makes a consent record meaningful. Null means not given.
    # Kept as two separate columns because the PRD forbids merging the two
    # acknowledgements into one control.
    terms_accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    privacy_acknowledged_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )

    settings: Mapped["UserSettings | None"] = relationship(
        back_populates="user", cascade="all, delete-orphan", uselist=False
    )
    #: Robots this account has claimed (PRD 2, section 31).
    devices: Mapped[list["Device"]] = relationship(
        back_populates="claimed_by", cascade="all, delete-orphan"
    )
    profile_roles: Mapped[list["AccountProfileRole"]] = relationship(
        back_populates="account", cascade="all, delete-orphan"
    )


class UserSettings(Base, TimestampMixin):
    """Per-account preferences. Exactly one row per account.

    ``language`` lives here rather than on the profile, following PRD 1
    section 32, even though it is collected on the profile screen during
    onboarding.
    """

    __tablename__ = "user_settings"
    __table_args__ = (
        CheckConstraint(f"theme IN {sql_in_list(THEMES)}", name="ck_user_settings_theme"),
        CheckConstraint(
            "daily_checkin_reminder_time IS NULL OR "
            f"daily_checkin_reminder_time ~ '{REMINDER_TIME_PATTERN}'",
            name="ck_user_settings_daily_checkin_reminder_time",
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

    # --- accessibility preferences (PRD 1, section 22) ---
    # All default to off. The user is never asked to name or disclose a
    # disability -- these are plain comfort settings.
    larger_text: Mapped[bool] = mapped_column(nullable=False, server_default="false")
    high_contrast: Mapped[bool] = mapped_column(nullable=False, server_default="false")
    reduce_motion: Mapped[bool] = mapped_column(nullable=False, server_default="false")
    voice_first_preference: Mapped[bool] = mapped_column(
        nullable=False, server_default="false"
    )
    simplified_interface: Mapped[bool] = mapped_column(
        nullable=False, server_default="false"
    )

    # --- daily check-in reminder (PRD 3, section 38) ---
    # The preference only. Nura does not schedule or deliver notifications
    # yet -- there is no notification foundation to build on, and PRD 3 asks
    # for the configuration model rather than the delivery. Recording it now
    # means the reminder feature, when it arrives, finds the user's answer
    # already there instead of asking again.
    daily_checkin_reminder_enabled: Mapped[bool] = mapped_column(
        nullable=False, server_default="false"
    )
    #: Local wall-clock time as ``HH:MM``, e.g. ``09:00``. A string rather than
    #: a ``Time`` column on purpose: this is the time on the user's own clock,
    #: not an instant the server can compute against, and storing it as text
    #: keeps that obvious at every layer.
    daily_checkin_reminder_time: Mapped[str | None] = mapped_column(String(5))

    user: Mapped[User] = relationship(back_populates="settings")
