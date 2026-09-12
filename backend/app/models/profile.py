"""Profile and AccountProfileRole (PRD 1, sections 28, 33 and 34).

Why a profile is separate from an account: in assisted setup the person who
signs in is not the person Nura is for. Keeping "who signs in" (``users``)
apart from "who Nura is for" (``profiles``) means assisted setup needs no
special-casing, and the eventual caregiver model has somewhere to attach.

Deliberately minimal. There are exactly two roles and no permission columns --
caregiver permissions, invitations and emergency roles all belong to later
PRDs (PRD 1, sections 28 and 34).
"""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.enums import AGE_RANGES, PROFILE_ROLES, sql_in_list

if TYPE_CHECKING:
    from app.models.user import User


class Profile(Base, TimestampMixin):
    """A person Nura is set up for.

    Holds only what onboarding actually asks for (PRD 1, section 18). No
    medical information of any kind -- that is explicitly out of scope
    (PRD 1, section 50).
    """

    __tablename__ = "profiles"
    __table_args__ = (
        CheckConstraint(
            f"age_range IS NULL OR age_range IN {sql_in_list(AGE_RANGES)}",
            name="ck_profiles_age_range",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    #: What Nura calls this person (PRD 1, section 19). Used later by voice
    #: interactions, greetings and reminders.
    preferred_name: Mapped[str] = mapped_column(String(64), nullable=False)
    #: An age *band*, not a date of birth. PRD 1 section 20 prefers this: it is
    #: enough for age-appropriate behaviour without storing a precise
    #: identifier. If a later PRD genuinely needs an exact date, it should be
    #: added alongside with a documented reason.
    age_range: Mapped[str | None] = mapped_column(String(24))
    #: ISO 3166-1 alpha-2, e.g. "GB". Uppercase.
    country_region: Mapped[str | None] = mapped_column(String(2))
    #: Free text and always optional (PRD 1, section 18).
    pronouns: Mapped[str | None] = mapped_column(String(32))
    #: Reserved for the optional profile photo. No upload UI in PRD 1; see
    #: docs/architecture/system-overview.md for why.
    avatar_url: Mapped[str | None] = mapped_column(String(512))

    account_roles: Mapped[list["AccountProfileRole"]] = relationship(
        back_populates="profile", cascade="all, delete-orphan"
    )


class AccountProfileRole(Base, TimestampMixin):
    """How an account relates to a profile.

    ``self``         -- the account holder is the person Nura is for.
    ``setup_helper`` -- the account holder is setting Nura up for someone else.

    Modelled as its own table rather than a column on either side so that one
    account can later relate to several profiles (and vice versa) without a
    migration that reshapes existing data.
    """

    __tablename__ = "account_profile_roles"
    __table_args__ = (
        UniqueConstraint("account_id", "profile_id", name="uq_account_profile"),
        CheckConstraint(
            f"role IN {sql_in_list(PROFILE_ROLES)}", name="ck_account_profile_roles_role"
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
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)

    account: Mapped["User"] = relationship(back_populates="profile_roles")
    profile: Mapped[Profile] = relationship(back_populates="account_roles")
