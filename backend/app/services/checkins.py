"""Daily check-in rules (PRD 3, sections 10-14, 28 and 39).

Three things decided here, each of which the HTTP layer would otherwise have
to guess at:

**Which day is "today".** The user's, not the server's. The client sends the
date on its own clock; the server accepts anything within a day of its own UTC
date, which covers every real time zone (UTC-12 to UTC+14) while stopping the
"today" endpoint from being used to write arbitrary history.

**One row per person per day.** Changing an answer updates the existing row.
A late offline submission cannot create a second one.

**Which edit wins.** The most recent explicit user edit. A client may say when
its edit was made; if the stored row has been changed more recently than that,
the stored row stands and is returned unchanged, so a stale queued submission
never silently overwrites a newer answer (PRD 3, section 28).
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import DailyCheckIn
from app.services.errors import DomainError

logger = logging.getLogger(__name__)

#: How far the client's local date may sit from the server's UTC date. Real
#: offsets run from UTC-12 to UTC+14, so one day either way is the whole world.
LOCAL_DATE_TOLERANCE = timedelta(days=1)

#: Window for the "this week" summary (PRD 3, section 12). A count, not a
#: trend: no charts, no correlations, no interpretation.
RECENT_WINDOW_DAYS = 7


class LocalDateOutOfRangeError(DomainError):
    """The date sent is too far from the server's idea of now to be a local today."""

    status_code = 422
    code = "local_date_out_of_range"


@dataclass(frozen=True)
class CheckInResult:
    """The stored check-in, and whether this submission is what is stored.

    ``applied`` is False when a newer edit already existed; the caller returns
    the row anyway, so an app reconciling a queued submission converges on the
    server's answer rather than retrying forever.
    """

    checkin: DailyCheckIn
    applied: bool


def validate_local_date(local_date: date, now: datetime) -> date:
    """Refuses a date that cannot plausibly be anybody's today."""
    if abs(local_date - now.date()) > LOCAL_DATE_TOLERANCE:
        raise LocalDateOutOfRangeError("That date is not today.")
    return local_date


def _as_utc(moment: datetime) -> datetime:
    """Treats a datetime with no offset as UTC, so comparisons never explode.

    Stored timestamps are always offset-aware. A client that sends a bare
    ``2026-09-21T09:00:00`` means UTC by convention, and reading it that way
    is better than a 500 from comparing an aware value with a naive one.
    """
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


def get_checkin(db: Session, profile_id: uuid.UUID, on_date: date) -> DailyCheckIn | None:
    return db.execute(
        select(DailyCheckIn).where(
            DailyCheckIn.profile_id == profile_id,
            DailyCheckIn.checkin_date == on_date,
        )
    ).scalar_one_or_none()


def window_start(end_date: date, days: int = RECENT_WINDOW_DAYS) -> date:
    """First day of a window of ``days`` ending on ``end_date`` inclusive."""
    return end_date - timedelta(days=days - 1)


def recent_checkins(
    db: Session,
    profile_id: uuid.UUID,
    end_date: date,
    days: int = RECENT_WINDOW_DAYS,
) -> list[DailyCheckIn]:
    """The window ending on ``end_date`` inclusive, most recent first."""
    start_date = window_start(end_date, days)
    return list(
        db.execute(
            select(DailyCheckIn)
            .where(
                DailyCheckIn.profile_id == profile_id,
                DailyCheckIn.checkin_date >= start_date,
                DailyCheckIn.checkin_date <= end_date,
            )
            .order_by(DailyCheckIn.checkin_date.desc())
        )
        .scalars()
        .all()
    )


def submit_checkin(
    db: Session,
    profile_id: uuid.UUID,
    on_date: date,
    wellbeing_level: str,
    note: str | None,
    now: datetime,
    client_updated_at: datetime | None = None,
) -> CheckInResult:
    """Records or changes how someone says they are feeling today.

    ``client_updated_at`` is when the user actually made this choice, which is
    not the same as when the request arrived -- an offline submission may be
    hours old by the time it syncs. Supplying it is what makes the
    latest-edit-wins rule work; omitting it means "apply this now".
    """
    existing = get_checkin(db, profile_id, on_date)

    if existing is None:
        checkin = DailyCheckIn(
            profile_id=profile_id,
            checkin_date=on_date,
            wellbeing_level=wellbeing_level,
            note=note,
        )
        db.add(checkin)
        db.commit()
        db.refresh(checkin)
        # The level is not logged: how someone feels is theirs, and the note
        # never leaves the database at all (PRD 3, section 44).
        logger.info("checkins: recorded a check-in")
        return CheckInResult(checkin=checkin, applied=True)

    if client_updated_at is not None and existing.updated_at > _as_utc(client_updated_at):
        logger.info("checkins: kept a newer stored check-in over an older submission")
        return CheckInResult(checkin=existing, applied=False)

    existing.wellbeing_level = wellbeing_level
    existing.note = note
    db.commit()
    db.refresh(existing)
    logger.info("checkins: updated today's check-in")
    return CheckInResult(checkin=existing, applied=True)
