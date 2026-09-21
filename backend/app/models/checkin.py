"""The daily wellbeing check-in (PRD 3, sections 10, 14 and 39).

One row per profile per local calendar day. It records how someone said they
were feeling and, if they chose to add one, a short note in their own words.

Two deliberate limits:

**It is not symptom tracking.** There are three levels and one free-text note.
No severity scales, no body sites, no photos, no inferred condition -- those
belong to PRD 6 (PRD 3, sections 10 and 45).

**The date is the user's local calendar day, not a UTC date.** Someone
checking in at 11pm in Karachi means that day, not the following one, so the
client sends the date it is showing and the server stores it as a plain date
(PRD 3, section 39). ``created_at``/``updated_at`` stay in UTC, as everywhere
else, which is what makes the "latest edit wins" rule in
``app/services/checkins.py`` comparable across devices.
"""

import uuid
from datetime import date

from sqlalchemy import CheckConstraint, Date, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin
from app.models.enums import WELLBEING_LEVELS, sql_in_list

#: Long enough for "Feeling tired today, slept badly" and short enough that it
#: cannot quietly become a health diary (PRD 3, section 10).
NOTE_MAX_LENGTH = 280


class DailyCheckIn(Base, TimestampMixin):
    """How one person said they were feeling on one day.

    The unique constraint is the whole design: there is exactly one primary
    check-in per profile per date, so changing an answer updates that row
    rather than adding a second one (PRD 3, section 11). A queued offline
    submission that arrives late therefore cannot create a duplicate.
    """

    __tablename__ = "daily_checkins"
    __table_args__ = (
        UniqueConstraint("profile_id", "checkin_date", name="uq_daily_checkin_per_day"),
        CheckConstraint(
            f"wellbeing_level IN {sql_in_list(WELLBEING_LEVELS)}",
            name="ck_daily_checkins_wellbeing_level",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    #: The person the check-in is about -- never the account that submitted it.
    #: In assisted setup those differ, and it is the person Nura is for whose
    #: day this describes.
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    #: The user's local calendar date. A plain date, deliberately without a
    #: time zone: it is the day as the user experienced it.
    checkin_date: Mapped[date] = mapped_column(Date, nullable=False)
    wellbeing_level: Mapped[str] = mapped_column(String(16), nullable=False)
    #: Optional, in the user's own words. Never logged, never sent to
    #: analytics, never interpreted (PRD 3, sections 44 and 45).
    note: Mapped[str | None] = mapped_column(String(NOTE_MAX_LENGTH))
