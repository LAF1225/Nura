"""The Today screen's one request (PRD 3, section 16).

Everything the screen needs arrives together: who it is for, whether they have
checked in, whether their Nura is connected, which medications are due, which
symptoms are active, and which cards to place. As feature areas land, they
join this response rather than adding a request -- the alternative is an app
that opens with six spinners.
"""

from datetime import datetime

from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession, Now, http_error
from app.api.v1.checkins import LocalDateQuery
from app.models import MedicationDose
from app.schemas.medication import (
    TodayLowSupplyRead,
    TodayMedicationsRead,
    TodayNextDoseRead,
)
from app.schemas.symptom import TodaySymptomRead, TodaySymptomsRead
from app.schemas.today import (
    DailyCheckInRead,
    DashboardCardRead,
    TodayCheckInRead,
    TodayDeviceRead,
    TodayItemRead,
    TodayProfileRead,
    TodaySummaryRead,
)
from app.services import checkins as checkin_service
from app.services import today as today_service
from app.services.errors import DomainError
from app.services.medications import doses as dose_service
from app.services.medications import summary as medication_service
from app.services.symptoms import summary as symptom_service

router = APIRouter(prefix="/today", tags=["today"])

#: What Important Today says about a dose, by where it sits relative to now.
#: Plain, unhurried wording: a dose nobody recorded is stated, not scolded
#: about, and no routine reminder is dressed up as an emergency
#: (PRD 5, sections 24, 29 and 57).
DOSE_SUBTITLE = {
    "overdue": "Not marked as taken",
    "due": "Due now",
    "upcoming": "Coming up",
}

#: Where tapping an Important Today medication row goes.
MEDICATIONS_ROUTE = "/medications"


def _dose_title(dose: MedicationDose) -> str:
    """ "Metformin — 500 mg", or just the name when no dose was recorded."""
    medication = dose.medication
    return (
        f"{medication.name} — {medication.dose}" if medication.dose else medication.name
    )


def _medication_items(
    summary: medication_service.MedicationSummary, now: datetime
) -> list[TodayItemRead]:
    """Overdue, then due, then next up -- the order PRD 5 section 29 sets.

    ``important`` is used only for a dose that is past its grace period and
    still unrecorded. It raises the row's prominence in the app; it does not
    make it an alert, and nothing here escalates to anybody.
    """
    items: list[TodayItemRead] = []
    for dose in summary.important:
        where = dose_service.window(dose, now)
        items.append(
            TodayItemRead(
                id=f"medication-dose:{dose.id}",
                type="medication_dose",
                title=_dose_title(dose),
                subtitle=DOSE_SUBTITLE.get(where),
                due_at=dose_service.due_at(dose),
                priority="important" if where == "overdue" else "normal",
                action_route=MEDICATIONS_ROUTE,
            )
        )
    return items


def _medications_read(
    summary: medication_service.MedicationSummary, now: datetime
) -> TodayMedicationsRead:
    next_due = summary.next_due
    return TodayMedicationsRead(
        next_due=(
            None
            if next_due is None
            else TodayNextDoseRead(
                dose_id=next_due.id,
                medication_id=next_due.medication_id,
                medication_name=next_due.medication.name,
                medication_dose=next_due.medication.dose,
                scheduled_for=next_due.scheduled_for,
                status=next_due.status,  # type: ignore[arg-type]
                window=dose_service.window(next_due, now),  # type: ignore[arg-type]
                can_snooze=next_due.snooze_count < dose_service.MAX_SNOOZES,
            )
        ),
        due_today_count=summary.due_today_count,
        overdue_count=summary.overdue_count,
        remaining_today_count=summary.remaining_today_count,
        low_supply=[
            TodayLowSupplyRead(
                medication_id=entry.medication_id,
                medication_name=entry.medication_name,
                remaining_doses=entry.remaining_doses,
            )
            for entry in summary.low_supply
        ],
        has_schedules=summary.has_schedules,
    )


#: Where tapping an Important Today symptom row goes.
SYMPTOMS_ROUTE = "/symptoms"

#: What Important Today says about a symptom. One sentence, stating what the
#: user recorded and nothing else: PRD 6 section 40 forbids labelling a symptom
#: urgent without a reviewed safety rule, and those rules are switched off
#: (section 44). So no symptom row is ever marked important, and none of this
#: wording implies an emergency.
SYMPTOM_SUBTITLE = "You recorded this as worsening"


def _symptom_title(snapshot: symptom_service.EpisodeSnapshot) -> str:
    """ "Headache -- 6/10", or just the name when no number was given."""
    severity = snapshot.severity
    name = snapshot.episode.name
    return f"{name} — {severity}/10" if severity is not None else name


def _symptom_items(summary: symptom_service.SymptomSummary) -> list[TodayItemRead]:
    """Symptoms the user has recorded as worsening (PRD 6, section 40).

    Only ever a recorded change, never an inferred one, and never at
    ``important`` priority: raising the prominence of a symptom Nura has not
    been told is urgent would be Nura making a clinical judgement.
    """
    return [
        TodayItemRead(
            id=f"symptom-episode:{snapshot.episode.id}",
            type="symptom_episode",
            title=_symptom_title(snapshot),
            subtitle=SYMPTOM_SUBTITLE,
            priority="normal",
            action_route=f"{SYMPTOMS_ROUTE}/{snapshot.episode.id}",
        )
        for snapshot in summary.important
    ]


def _symptoms_read(summary: symptom_service.SymptomSummary) -> TodaySymptomsRead:
    recent = summary.most_recent
    return TodaySymptomsRead(
        active_count=summary.active_count,
        worsening_count=summary.worsening_count,
        most_recent=(
            None
            if recent is None
            else TodaySymptomRead(
                episode_id=recent.episode.id,
                name=recent.episode.name,
                severity=recent.severity,
                change_state=recent.change_state,  # type: ignore[arg-type]
                updated_at=recent.updated_at,
            )
        ),
        has_episodes=summary.has_episodes,
    )


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
        medications=(
            None
            if summary.medications is None
            else _medications_read(summary.medications, now)
        ),
        symptoms=(None if summary.symptoms is None else _symptoms_read(summary.symptoms)),
        # Medications first, then symptoms: a dose still waiting to be
        # recorded is something to do now, while a symptom recorded as
        # worsening is something to know. Both stay empty for the many
        # people who use neither feature.
        important=[
            *(
                []
                if summary.medications is None
                else _medication_items(summary.medications, now)
            ),
            *([] if summary.symptoms is None else _symptom_items(summary.symptoms)),
        ],
    )
