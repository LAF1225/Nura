"""Everything the Today screen needs, assembled once (PRD 3, section 16).

Today will eventually draw on every feature area in the app. If each one had
its own request, opening the app would mean a dozen round trips and a screen
that fills in piece by piece. So the server assembles the day: who this is
for, whether they have checked in, whether their Nura is connected, and which
cards to place.

PRD 5 added the first feature area to actually join it -- the next medication
dose, three counts, and anything running low. PRD 6 added the second: which
symptoms are active, and whether the person has recorded any of them as getting
worse. PRD 7 adds the third: the next appointment, and whether it has been
prepared for. PRD 12 adds the fourth: tasks due today,
reminders waiting, and how today's routines are going.

**Daily life sits below everything medical here, and that is structural.**
PRD 12 section 18 ends with the rule -- *daily-life items must never obscure
safety-critical items* -- so the Important Today list is assembled in a fixed
order in ``api.v1.today``, with medications first and daily life last. Nothing
in the daily-life summary can change where its rows land.
"""

from dataclasses import dataclass, field
from datetime import date, datetime

from sqlalchemy.orm import Session

from app.models import DailyCheckIn, Device, Profile, User
from app.services import checkins as checkin_service
from app.services import dashboard as dashboard_service
from app.services import devices as device_service
from app.services import profiles as profile_service
from app.services.appointments import summary as appointment_service
from app.services.medications import doses as dose_service
from app.services.medications import summary as medication_service
from app.services.productivity import summary as daily_life_service
from app.services.symptoms import summary as symptom_service


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
    #: Null for an account with no profile yet: medications belong to a
    #: person, so there is nobody to have any.
    medications: medication_service.MedicationSummary | None = None
    #: Null for the same reason. ``has_episodes`` is False for anybody who
    #: has never logged a symptom, which is what lets Today leave the card
    #: out entirely (PRD 6, section 39).
    symptoms: symptom_service.SymptomSummary | None = None
    #: Null for the same reason. Unlike the two above, a false
    #: ``has_appointments`` does *not* hide the card: PRD 7 section 9 specifies
    #: what an empty appointments card says.
    appointments: appointment_service.AppointmentSummary | None = None
    #: Tasks, reminders, routines and alarms (PRD 12, sections 18 and 19). Null
    #: for an account with no profile yet. ``has_anything`` is False for
    #: anybody who has never made one, which is what keeps the card invisible
    #: until it is relevant.
    daily_life: daily_life_service.DailyLifeSummary | None = None
    #: The Important Today section (PRD 3, section 21). Doses that are
    #: overdue, due or next up; an appointment today or tomorrow; a symptom
    #: recorded as worsening. Ordinary reminders, never framed as emergencies
    #: (PRD 5, section 29; PRD 7, section 10).
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

    # Bring doses up to date before anything reads them: top the window up
    # ahead, and record whatever quietly became missed while the app was
    # closed. Opening Today is the commonest moment for that to happen, which
    # is why PRD 5 needs no background worker to be correct (section 71).
    dose_service.replenish(db, profile.id, now)

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
        medications=medication_service.build_summary(db, profile.id, local_date, now),
        symptoms=symptom_service.build_summary(db, profile.id, now),
        appointments=appointment_service.build_summary(db, profile.id, local_date, now),
        # Replenishes reminder occurrences and routine runs on the way, the
        # same way ``dose_service.replenish`` above does -- which is why PRD 12
        # needs no background worker to be correct (PRD 12, section 63).
        daily_life=daily_life_service.build_summary(db, profile.id, local_date, now),
    )
