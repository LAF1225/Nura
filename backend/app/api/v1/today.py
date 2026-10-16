"""The Today screen's one request (PRD 3, section 16).

Everything the screen needs arrives together: who it is for, whether they have
checked in, whether their Nura is connected, which medications are due, which
symptoms are active, when the next appointment is, and which cards to place. As
feature areas land, they join this response rather than adding a request -- the
alternative is an app that opens with six spinners.
"""

from datetime import datetime

from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession, Now, http_error
from app.api.v1.checkins import LocalDateQuery
from app.models import MedicationDose
from app.schemas.appointment import TodayAppointmentRead, TodayAppointmentsRead
from app.schemas.medication import (
    TodayLowSupplyRead,
    TodayMedicationsRead,
    TodayNextDoseRead,
)
from app.schemas.productivity import (
    ReminderCountsRead,
    RoutineCountsRead,
    TaskCountsRead,
)
from app.schemas.symptom import TodaySymptomRead, TodaySymptomsRead
from app.schemas.today import (
    DailyCheckInRead,
    DashboardCardRead,
    TodayCheckInRead,
    TodayDailyLifeRead,
    TodayDeviceRead,
    TodayItemRead,
    TodayProfileRead,
    TodaySummaryRead,
)
from app.services import checkins as checkin_service
from app.services import today as today_service
from app.services.appointments import appointments as appointment_record_service
from app.services.appointments import summary as appointment_service
from app.services.appointments.wording import relative_day, when_label
from app.services.errors import DomainError
from app.services.medications import doses as dose_service
from app.services.medications import summary as medication_service
from app.services.productivity import reminders as reminder_service
from app.services.productivity import summary as daily_life_service
from app.services.productivity import wording as productivity_wording
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


#: Where tapping an Important Today appointment row goes.
APPOINTMENTS_ROUTE = "/appointments"

#: What Important Today adds for an appointment whose preparation is not
#: finished. An offer, not a warning: PRD 7 section 10 says outright that an
#: appointment in this section is not an emergency.
PREPARE_HINT = "Not prepared yet"


def _appointment_item(
    snapshot: appointment_service.AppointmentSnapshot, now: datetime
) -> TodayItemRead:
    """One appointment row (PRD 7, sections 9 and 10).

    ``important`` priority is used only for an appointment *today* that has not
    been prepared for -- the one case worth noticing more than the others. It
    raises the row's prominence in the app; it does not make it an alert, and
    nothing here escalates to anybody.
    """
    appointment = snapshot.appointment
    zone = appointment_record_service.local_zone(appointment)
    local_today = now.astimezone(zone).date()
    unprepared = not snapshot.preparation_complete
    label = when_label(appointment.scheduled_at, zone, local_today)
    return TodayItemRead(
        id=f"appointment:{appointment.id}",
        type="appointment",
        title=appointment.title,
        subtitle=f"{label} \u00b7 {PREPARE_HINT}" if unprepared else label,
        due_at=appointment.scheduled_at,
        priority="important" if snapshot.is_today and unprepared else "normal",
        action_route=f"{APPOINTMENTS_ROUTE}/{appointment.id}",
    )


def _appointment_items(
    summary: appointment_service.AppointmentSummary, now: datetime
) -> list[TodayItemRead]:
    """Appointments today and tomorrow (PRD 7, section 10).

    Only those two days. An appointment next week is something to know rather
    than something to do today, and putting it here would make the section
    permanent furniture that people stop reading.
    """
    return [_appointment_item(snapshot, now) for snapshot in summary.important]


def _today_appointment_read(
    snapshot: appointment_service.AppointmentSnapshot, now: datetime
) -> TodayAppointmentRead:
    """The next appointment, with its labels rendered in its own zone (s42)."""
    appointment = snapshot.appointment
    zone = appointment_record_service.local_zone(appointment)
    local_today = now.astimezone(zone).date()
    clinician = appointment.clinician
    return TodayAppointmentRead(
        appointment_id=appointment.id,
        title=appointment.title,
        appointment_type=appointment.appointment_type,  # type: ignore[arg-type]
        scheduled_at=appointment.scheduled_at,
        timezone=appointment.timezone,
        when_label=when_label(appointment.scheduled_at, zone, local_today),
        relative_day=relative_day(snapshot.local_date, local_today),
        clinician_name=None if clinician is None else clinician.name,
        clinician_specialty=None if clinician is None else clinician.specialty,
        location_name=appointment.location_name,
        preparation_status=appointment.preparation_status,  # type: ignore[arg-type]
        question_count=snapshot.question_count,
        report_count=snapshot.report_count,
    )


def _appointments_read(
    summary: appointment_service.AppointmentSummary, now: datetime
) -> TodayAppointmentsRead:
    next_up = summary.next_appointment
    return TodayAppointmentsRead(
        next=None if next_up is None else _today_appointment_read(next_up, now),
        upcoming_count=summary.upcoming_count,
        has_appointments=summary.has_appointments,
    )


# --- daily life (PRD 12, sections 18 and 19) --------------------------------

#: Where tapping a daily-life row goes. One hub rather than four routes: a
#: person who taps a task wants their list, and the list is where Done lives.
DAILY_LIFE_ROUTE = "/daily"
ROUTINES_ROUTE = "/daily/routines"

#: What Important Today says about a task. Stated, never scolded about: a task
#: past its due time is a fact about a clock, and PRD 12 section 18 keeps all
#: of this well below anything safety-critical.
TASK_SUBTITLE = {True: "Past its due time", False: "Due today"}

#: What it says about a reminder occurrence, by where it sits.
REMINDER_SUBTITLE = {"due": "Now", "overdue": "Not answered yet"}


def _task_items(
    summary: daily_life_service.DailyLifeSummary, now: datetime
) -> list[TodayItemRead]:
    """Tasks due today or past their due time, important ones first.

    ``important`` priority is used for a task the person *marked* important --
    never for one Nura decided mattered. It raises the row's prominence in the
    app; it does not make it an alert, and nothing here escalates to anybody.
    """
    items = []
    for snapshot in summary.important_tasks:
        task = snapshot.task
        items.append(
            TodayItemRead(
                id=f"task:{task.id}",
                type="task",
                title=task.title,
                subtitle=TASK_SUBTITLE[snapshot.overdue],
                due_at=task.due_at,
                priority="important" if task.priority == "important" else "normal",
                action_route=DAILY_LIFE_ROUTE,
            )
        )
    return items


def _routine_items(
    summary: daily_life_service.DailyLifeSummary,
) -> list[TodayItemRead]:
    """Today's routines that are still open, with how far through they are."""
    items = []
    for snapshot in summary.important_runs:
        run = snapshot.run
        progress = snapshot.progress
        items.append(
            TodayItemRead(
                id=f"routine-run:{run.id}",
                type="routine_run",
                title=run.routine.title,
                subtitle=productivity_wording.routine_run_sentence(
                    done=progress.done,
                    total=progress.total,
                    next_title=(
                        None if progress.next_step is None else progress.next_step.title
                    ),
                ),
                due_at=run.scheduled_for,
                priority="normal",
                action_route=f"{DAILY_LIFE_ROUTE}/run/{run.id}",
            )
        )
    return items


def _reminder_items(
    summary: daily_life_service.DailyLifeSummary,
) -> list[TodayItemRead]:
    """Reminder occurrences waiting for an answer."""
    items = []
    for snapshot in summary.important_reminders:
        occurrence = snapshot.occurrence
        items.append(
            TodayItemRead(
                id=f"reminder-occurrence:{occurrence.id}",
                type="general_reminder",
                title=occurrence.reminder.title,
                subtitle=REMINDER_SUBTITLE.get(snapshot.window),
                due_at=reminder_service.due_at(occurrence),
                priority="normal",
                action_route=f"{DAILY_LIFE_ROUTE}/reminders",
            )
        )
    return items


def _daily_life_items(
    summary: daily_life_service.DailyLifeSummary, now: datetime
) -> list[TodayItemRead]:
    """Section 18's daily-life rows, in section 18's own relative order.

    An important task, then a routine, then a reminder, then an ordinary task.
    The split between the first and the last is done here rather than in the
    service, because it is a question about *display* order and the service
    returns one list of tasks sorted by when they are due.
    """
    tasks = _task_items(summary, now)
    important = [item for item in tasks if item.priority == "important"]
    ordinary = [item for item in tasks if item.priority != "important"]
    return [*important, *_routine_items(summary), *_reminder_items(summary), *ordinary]


def _daily_life_read(
    summary: daily_life_service.DailyLifeSummary,
) -> TodayDailyLifeRead:
    return TodayDailyLifeRead(
        tasks=TaskCountsRead(
            due_today=summary.tasks.due_today,
            overdue=summary.tasks.overdue,
            open_total=summary.tasks.open_total,
        ),
        reminders=ReminderCountsRead(
            due_today=summary.reminders.due_today, due_now=summary.reminders.due_now
        ),
        routines=RoutineCountsRead(
            due_today=summary.routines.due_today,
            in_progress=summary.routines.in_progress,
            completed_today=summary.routines.completed_today,
        ),
        next_alarm_at=summary.next_alarm_at,
        alarm_count=summary.alarm_count,
        summary_label=productivity_wording.today_summary_sentence(
            summary.tasks.due_today,
            summary.routines.due_today,
            summary.reminders.due_today,
        ),
        has_anything=summary.has_anything,
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
        daily_life=(
            None if summary.daily_life is None else _daily_life_read(summary.daily_life)
        ),
        appointments=(
            None
            if summary.appointments is None
            else _appointments_read(summary.appointments, now)
        ),
        # Medications, then appointments, then symptoms, then daily life --
        # ordered by how soon each needs something. A dose is due at a time
        # today; an appointment is somewhere to be today or tomorrow; a symptom
        # recorded as worsening is something to know; a task is something to
        # do. Every group stays empty for the many people who use none of
        # these features.
        #
        # **Daily life is last, and that is PRD 12 section 18's rule rather
        # than a preference.** The section ends with "daily-life items must
        # never obscure safety-critical items", so the order is fixed here, in
        # one list, where it can be read -- and nothing in the daily-life
        # summary can change where its rows land. Symptoms stay above it for
        # the same reason: a symptom somebody recorded as getting worse is
        # health information, and a shopping list is not.
        important=[
            *(
                []
                if summary.medications is None
                else _medication_items(summary.medications, now)
            ),
            *(
                []
                if summary.appointments is None
                else _appointment_items(summary.appointments, now)
            ),
            *([] if summary.symptoms is None else _symptom_items(summary.symptoms)),
            *(
                []
                if summary.daily_life is None
                else _daily_life_items(summary.daily_life, now)
            ),
        ],
    )
