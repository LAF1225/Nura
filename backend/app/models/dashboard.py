"""Which cards a profile wants on Today, and in what order (PRD 3, section 20).

A row per card the user has an opinion about. Cards they have never touched
have no row and fall back to the registry defaults in
``app/services/dashboard.py``, so a card added by a later PRD appears for
everyone without a data migration.

``card_key`` has no CHECK constraint on purpose. The set of cards is expected
to grow every time a feature area lands, and a constraint here would mean a
migration each time. The API validates keys against the registry instead,
which is the thing that actually knows whether a card exists (PRD 3,
section 59).
"""

import uuid

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

CARD_KEY_MAX_LENGTH = 40


class DashboardPreference(Base, TimestampMixin):
    """One card's visibility and position for one profile."""

    __tablename__ = "dashboard_preferences"
    __table_args__ = (
        UniqueConstraint("profile_id", "card_key", name="uq_dashboard_card_per_profile"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    #: Matches a key in the dashboard card registry, e.g. ``daily_checkin``.
    card_key: Mapped[str] = mapped_column(String(CARD_KEY_MAX_LENGTH), nullable=False)
    visible: Mapped[bool] = mapped_column(nullable=False, server_default="true")
    #: Ascending. Ties are broken by the registry's own order, so a layout
    #: saved before a new card existed still renders deterministically.
    position: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
