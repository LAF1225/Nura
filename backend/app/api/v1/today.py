"""The Today screen's one request (PRD 3, section 16).

Everything the screen needs arrives together: who it is for, whether they have
checked in, whether their Nura is connected, and which cards to place. As
feature areas land, they join this response rather than adding a request --
the alternative is an app that opens with six spinners.
"""

from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession, Now, http_error
from app.api.v1.checkins import LocalDateQuery
from app.schemas.today import (
    DailyCheckInRead,
    DashboardCardRead,
    TodayCheckInRead,
    TodayDeviceRead,
    TodayProfileRead,
    TodaySummaryRead,
)
from app.services import checkins as checkin_service
from app.services import today as today_service
from app.services.errors import DomainError

router = APIRouter(prefix="/today", tags=["today"])


@router.get("", response_model=TodaySummaryRead)
def read_today(
    user: CurrentUser, db: DbSession, now: Now, local_date: LocalDateQuery = None
) -> TodaySummaryRead:
    """Assembles the user's day.

    Works in every state PRD 3 section 6 requires: no robot, a robot that is
    offline, a robot the backend has heard from, and an account that has not
    finished setting up a profile. None of those is an error.
    """
    try:
        on_date = checkin_service.validate_local_date(local_date or now.date(), now)
    except DomainError as error:
        raise http_error(error) from error

    summary = today_service.build_summary(db, user, on_date, now)
    checkin = summary.daily_checkin

    return TodaySummaryRead(
        local_date=summary.local_date,
        profile=(
            None
            if summary.profile is None
            else TodayProfileRead.model_validate(summary.profile)
        ),
        daily_checkin=TodayCheckInRead(
            status=checkin.status,  # type: ignore[arg-type]
            checkin=(
                None
                if checkin.checkin is None
                else DailyCheckInRead.model_validate(checkin.checkin)
            ),
            recent_completed_count=checkin.recent_completed_count,
            recent_window_days=checkin.recent_window_days,
        ),
        device=(
            None
            if summary.device is None
            else TodayDeviceRead(
                device_id=summary.device.device_id,  # type: ignore[arg-type]
                display_name=summary.device.display_name,
                connection_status=summary.device.connection_status,  # type: ignore[arg-type]
                last_seen_at=summary.device.last_seen_at,
                setup_completed=summary.device.setup_completed,
            )
        ),
        cards=[DashboardCardRead(**vars(card)) for card in summary.cards],
        # Always empty in PRD 3: no module produces items yet, and inventing
        # them is explicitly ruled out (PRD 3, section 21).
        important=[],
    )
