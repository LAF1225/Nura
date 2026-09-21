"""Daily wellbeing check-ins (PRD 3, sections 10-15).

Three routes, all about one day at a time. The caller never says whose
check-in it is unless they mean a specific profile they already own: the
server derives the person from the signed-in account, so a client cannot
address someone else's day by guessing an id (PRD 3, sections 15 and 44).

"Today" is the *user's* today. The client sends the date it is showing and the
server accepts it if it is within a day of its own -- see
``app/services/checkins.py``.
"""

import uuid
from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DbSession, Now, http_error
from app.models import Profile, User
from app.schemas.today import (
    DailyCheckInRead,
    DailyCheckInSaved,
    DailyCheckInTodayRead,
    DailyCheckInUpdate,
    RecentCheckInsRead,
)
from app.services import checkins as checkin_service
from app.services import profiles as profile_service
from app.services.errors import DomainError

router = APIRouter(prefix="/daily-checkins", tags=["check-ins"])

LocalDateQuery = Annotated[
    date | None,
    Query(description="The date on the client's own clock, as YYYY-MM-DD."),
]
ProfileQuery = Annotated[
    uuid.UUID | None,
    Query(description="Defaults to the person this account's Nura is for."),
]


def _profile(user: User, profile_id: uuid.UUID | None) -> Profile:
    try:
        return profile_service.resolve_profile(user, profile_id)
    except DomainError as error:
        raise http_error(error) from error


def _local_date(value: date | None, now: datetime) -> date:
    try:
        return checkin_service.validate_local_date(value or now.date(), now)
    except DomainError as error:
        raise http_error(error) from error


@router.get("/today", response_model=DailyCheckInTodayRead)
def read_today_checkin(
    user: CurrentUser,
    db: DbSession,
    now: Now,
    local_date: LocalDateQuery = None,
    profile_id: ProfileQuery = None,
) -> DailyCheckInTodayRead:
    """Today's check-in, or nothing yet. Never an error just for not having one."""
    profile = _profile(user, profile_id)
    on_date = _local_date(local_date, now)
    checkin = checkin_service.get_checkin(db, profile.id, on_date)
    return DailyCheckInTodayRead(
        local_date=on_date,
        profile_id=profile.id,
        checkin=None if checkin is None else DailyCheckInRead.model_validate(checkin),
    )


@router.put("/today", response_model=DailyCheckInSaved)
def save_today_checkin(
    payload: DailyCheckInUpdate, user: CurrentUser, db: DbSession, now: Now
) -> DailyCheckInSaved:
    """Records or changes today's check-in.

    PUT rather than POST because there is one check-in per person per day: the
    same request sent twice leaves the same single row, which is exactly what
    a retried offline submission needs (PRD 3, sections 11 and 27).
    """
    profile = _profile(user, payload.profile_id)
    on_date = _local_date(payload.local_date, now)

    result = checkin_service.submit_checkin(
        db,
        profile_id=profile.id,
        on_date=on_date,
        wellbeing_level=payload.wellbeing_level,
        note=payload.note,
        now=now,
        client_updated_at=payload.client_updated_at,
    )
    return DailyCheckInSaved(
        checkin=DailyCheckInRead.model_validate(result.checkin),
        applied=result.applied,
    )


@router.get("/recent", response_model=RecentCheckInsRead)
def read_recent_checkins(
    user: CurrentUser,
    db: DbSession,
    now: Now,
    local_date: LocalDateQuery = None,
    days: Annotated[int, Query(ge=1, le=31)] = checkin_service.RECENT_WINDOW_DAYS,
    profile_id: ProfileQuery = None,
) -> RecentCheckInsRead:
    """A short recent window: the entries, and how many days have one.

    Deliberately not an analysis. PRD 3 section 12 allows "4 check-ins
    completed" and nothing more -- trends and correlations belong to a PRD
    that has the clinical care to present them responsibly.
    """
    profile = _profile(user, profile_id)
    to_date = _local_date(local_date, now)
    entries = checkin_service.recent_checkins(db, profile.id, to_date, days)
    return RecentCheckInsRead(
        profile_id=profile.id,
        from_date=checkin_service.window_start(to_date, days),
        to_date=to_date,
        window_days=days,
        completed_count=len(entries),
        checkins=[DailyCheckInRead.model_validate(entry) for entry in entries],
    )
