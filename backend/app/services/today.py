"""Everything the Today screen needs, assembled once (PRD 3, section 16).

Today will eventually draw on every feature area in the app. If each one had
its own request, opening the app would mean a dozen round trips and a screen
that fills in piece by piece. So the server assembles the day: who this is
for, whether they have checked in, whether their Nura is connected, and which
cards to place.

What is *not* here is as deliberate as what is: no medications, appointments,
symptoms or routines, because those modules do not exist yet, and a summary
that invents them would be a summary of nothing (PRD 3, sections 16 and 21).
"""

from dataclasses import dataclass, field
from datetime import date, datetime

from sqlalchemy.orm import Session

from app.models import DailyCheckIn, Device, Profile, User
from app.services import checkins as checkin_service
from app.services import dashboard as dashboard_service
from app.services import devices as device_service
from app.services import profiles as profile_service


@dataclass(frozen=True)
class DeviceSummary:
    """A robot as Today talks about it.

    ``connection_status`` is the backend's own derivation from heartbeats --
    the app never decides a robot is online (PRD 2, section 34; PRD 3,
    section 23). An account with no robot gets no summary at all, which the
    client renders as "not connected yet" rather than as an error
    (PRD 3, section 54).
    """

    device_id: str
    display_name: str
    connection_status: str
    last_seen_at: datetime | None
    setup_completed: bool


@dataclass(frozen=True)
class CheckInSummary:
    checkin: DailyCheckIn | None
    #: How many days in the recent window have a check-in. A count only; PRD 3
    #: section 12 rules out trends, charts and interpretation.
    recent_completed_count: int
    recent_window_days: int

    @property
    def status(self) -> str:
        return "completed" if self.checkin is not None else "not_completed"


@dataclass(frozen=True)
class TodaySummary:
    local_date: date
    profile: Profile | None
    daily_checkin: CheckInSummary
    device: DeviceSummary | None
    cards: list[dashboard_service.ResolvedCard]
    #: Reserved for the Important Today section. Always empty in PRD 3: no
    #: module produces items yet, and inventing them is explicitly ruled out
    #: (PRD 3, sections 21 and 60).
    important: list[object] = field(default_factory=list)


def _device_for(user: User, profile: Profile | None) -> Device | None:
    """The robot Today should talk about.

    A robot set up for this person wins; otherwise the account's first one, so
    an account whose single robot predates the profile link still sees it.
    """
    owned = sorted(user.devices, key=lambda device: device.created_at)
    if profile is not None:
        for device in owned:
            if device.owner_profile_id == profile.id:
                return device
    return owned[0] if owned else None


def build_summary(
    db: Session, user: User, local_date: date, now: datetime
) -> TodaySummary:
    """Assembles the day for the signed-in account."""
    profile = profile_service.primary_profile(user)

    if profile is None:
        # Part-way through setup: no person, so nothing to be about. Today
        # still renders, with the greeting falling back and the check-in card
        # standing down (PRD 3, section 8).
        return TodaySummary(
            local_date=local_date,
            profile=None,
            daily_checkin=CheckInSummary(
                checkin=None,
                recent_completed_count=0,
                recent_window_days=checkin_service.RECENT_WINDOW_DAYS,
            ),
            device=None,
            cards=dashboard_service.default_cards(),
        )

    recent = checkin_service.recent_checkins(db, profile.id, local_date)
    today_checkin = next(
        (entry for entry in recent if entry.checkin_date == local_date), None
    )

    device = _device_for(user, profile)
    device_summary = (
        None
        if device is None
        else DeviceSummary(
            device_id=str(device.id),
            display_name=device.display_name,
            connection_status=device_service.connection_status(device, now),
            last_seen_at=device.last_seen_at,
            setup_completed=device.setup_completed_at is not None,
        )
    )

    return TodaySummary(
        local_date=local_date,
        profile=profile,
        daily_checkin=CheckInSummary(
            checkin=today_checkin,
            recent_completed_count=len(recent),
            recent_window_days=checkin_service.RECENT_WINDOW_DAYS,
        ),
        device=device_summary,
        cards=dashboard_service.resolve_cards(db, profile.id),
    )
