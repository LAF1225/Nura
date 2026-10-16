"""What a caregiver is actually shown, category by category.

PRD 9, sections 17, 18, 19, 26, 27, 28, 29, 60 and 67.

This module exists because of section 67: **a caregiver endpoint returns only
what that permission needs.** The owner's own routes return everything -- free
text, notes, skip reasons, photo keys -- and reusing them for caregivers would
have been less code and the wrong answer. So every view below is assembled here,
deliberately smaller than its owner-side equivalent:

- medications: names, doses, reminder times, an adherence *count* and whether
  supply is low. **No skip reason text**, which section 19 rules out by default:
  "feeling unwell" typed into a reminder app is the user talking to themselves.
- appointments: title, when, type, location, and the questions written down.
  No notes field -- an appointment's notes are the user's own.
- symptoms: what is being tracked and the severity recorded, read-only.
  No photos: a symptom photo is as private as anything in this product and
  section 28 grants *viewing selected symptom history*, not images.
- reports: that a report exists, its version and when it was generated.
  **Not the PDF.** Section 29 permits viewing reports and section 52 forbids
  unrestricted generation; serving the file needs its own authenticated route
  and a decision about caching on a caregiver's phone, which PRD 9 does not make.
- health summary: counts. Never a condition, medication or allergy name.

**The absence of a permission reveals nothing** (section 18). ``build_home``
omits a section entirely rather than returning it empty or zero -- a caregiver
without ``symptoms`` cannot tell from the response whether this person has ever
recorded one, because there is no symptom key in the payload at all. That is
also why the counts in ``general_health_summary`` are gated: a count is
information.

**Nothing here writes.** Not one function in this module changes a row. A
caregiver's only route to a change is a suggestion (sections 21 and 64).
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Appointment,
    AppointmentReport,
    Medication,
    MedicationSchedule,
)
from app.services.appointments import appointments as appointment_service
from app.services.appointments import preparation as preparation_service
from app.services.appointments import questions as question_service
from app.services.appointments import wording as appointment_wording
from app.services.caregivers import messaging, suggestions
from app.services.caregivers import wording as care_wording
from app.services.caregivers.permissions import CareScope
from app.services.health import build_summary as build_health_summary
from app.services.medications import adherence as adherence_service
from app.services.medications import summary as medication_summary
from app.services.medications import supply as supply_service
from app.services.productivity import routines as routine_service
from app.services.productivity import wording as productivity_wording
from app.services.safety import alerts as safety_alerts
from app.services.safety.alerts import AlertView
from app.services.symptoms import summary as symptom_summary

logger = logging.getLogger(__name__)

#: The window an adherence figure covers on a caregiver's screen. A week, which
#: is what section 19's "adherence summary" means in practice and short enough
#: that it describes now rather than a history.
ADHERENCE_DAYS = 7

#: How many of anything a caregiver view returns.
MAX_ROWS = 20


@dataclass(frozen=True)
class CaregiverMedicationView:
    """One medication, as somebody helping sees it."""

    medication_id: uuid.UUID
    name: str
    dose: str | None
    #: "Every day at 8:00 AM and 8:00 PM", or None with no active schedule.
    schedule_label: str | None
    reminders_paused: bool
    #: True when supply tracking says it is running low (section 19).
    supply_low: bool
    remaining_doses: int | None
    #: The schedule a reminder-time suggestion would target. None when there is
    #: no schedule to change.
    schedule_id: uuid.UUID | None


@dataclass(frozen=True)
class CaregiverAdherenceView:
    """Counts for the last week. Counts, and no verdict on them."""

    from_date: date
    to_date: date
    taken: int
    skipped: int
    missed: int
    percent: int | None


@dataclass(frozen=True)
class CaregiverAppointmentView:
    appointment_id: uuid.UUID
    title: str
    when_label: str
    day_label: str
    appointment_type: str
    location_name: str | None
    question_count: int
    preparation_status: str


@dataclass(frozen=True)
class CaregiverSymptomView:
    episode_id: uuid.UUID
    name: str
    status: str
    severity: int | None
    change_state: str | None
    last_recorded_at: datetime | None


@dataclass(frozen=True)
class CaregiverReportView:
    report_id: uuid.UUID
    appointment_title: str
    version: int
    generated_at: datetime
    status: str


@dataclass(frozen=True)
class CaregiverHealthCounts:
    """Counts only (section 67). No names, ever."""

    active_conditions: int
    active_medications: int
    active_symptoms: int
    allergies: int


@dataclass(frozen=True)
class CaregiverRoutineView:
    """One routine, as somebody helping sees it (PRD 12, section 16)."""

    routine_id: uuid.UUID
    title: str
    #: "Every day at 7:30 AM", rendered by the one module that writes routine
    #: prose, so the caregiver screen and the owner's screen cannot disagree.
    schedule_label: str
    step_count: int
    paused: bool
    #: Today's run, if there is one. Null means the routine does not run today,
    #: which is different from a run nobody has started.
    today_status: str | None = None
    today_done: int | None = None
    today_total: int | None = None


@dataclass(frozen=True)
class CaregiverHome:
    """The caregiver's Today (sections 17 and 60).

    Every field is optional and omitted when the permission is absent, which is
    section 18 made structural: a missing section is indistinguishable from a
    person who has nothing recorded, because neither is in the response.
    """

    profile_name: str
    role: str
    granted: list[str]
    #: Categories granted but with nothing behind them yet. **Empty since
    #: PRD 12**, which built the routine records ``routines`` used to promise
    #: and nothing deliver. The field stays, because the next PRD that reserves
    #: a permission before its data exists needs it -- and the app keeps the
    #: sentence that renders it.
    granted_without_data: list[str] = field(default_factory=list)
    medications: list[CaregiverMedicationView] | None = None
    adherence: CaregiverAdherenceView | None = None
    doses_remaining_today: int | None = None
    doses_overdue: int | None = None
    appointments: list[CaregiverAppointmentView] | None = None
    symptoms: list[CaregiverSymptomView] | None = None
    reports: list[CaregiverReportView] | None = None
    #: Routines and how today's runs are going. Absent unless ``routines`` is
    #: granted (PRD 12, section 16), and it reaches routines only -- section 42
    #: keeps tasks, alarms and general reminders private.
    routines: list[CaregiverRoutineView] | None = None
    health_counts: CaregiverHealthCounts | None = None
    unread_messages: int | None = None
    #: Safety alerts raised about this person for *this* caregiver, and the
    #: most recent one. Absent unless ``safety_alerts`` is granted (PRD 10,
    #: sections 31 and 50) -- the same omission rule every other section
    #: follows, for the same reason.
    unread_safety_alerts: int | None = None
    latest_safety_alert: AlertView | None = None
    #: What this caregiver has proposed and not yet had answered.
    pending_suggestions: int | None = None
    #: Whether the server has an audio-calling provider at all (section 38).
    calling_available: bool = False


# --- medications -------------------------------------------------------------


def _schedule_label(schedules: list[MedicationSchedule]) -> str | None:
    """ "Every day at 8:00 AM", built from the same helper a report uses.

    Reusing ``preparation.schedule_frequency`` rather than writing a second
    phrasing: a caregiver and a doctor report should describe a medication
    identically, and two renderers drift.
    """
    if not schedules:
        return None
    frequency = preparation_service.schedule_frequency(schedules)
    times = [entry.time_of_day for entry in schedules[0].times]
    if not times:
        return frequency or None
    label = care_wording.format_times(times)
    return f"{frequency} at {label}" if frequency else f"At {label}"


def medications_for(db: Session, profile_id: uuid.UUID) -> list[CaregiverMedicationView]:
    """Active medications with their reminders (section 19)."""
    medications = list(
        db.execute(
            select(Medication)
            .where(Medication.profile_id == profile_id, Medication.is_active.is_(True))
            .order_by(Medication.name.asc())
            .limit(MAX_ROWS)
        )
        .scalars()
        .all()
    )
    schedules: dict[uuid.UUID, list[MedicationSchedule]] = {}
    for schedule in (
        db.execute(
            select(MedicationSchedule).where(MedicationSchedule.profile_id == profile_id)
        )
        .scalars()
        .all()
    ):
        schedules.setdefault(schedule.medication_id, []).append(schedule)

    supplies = {
        supply.medication_id: supply
        for supply, _medication in supply_service.list_supply(db, profile_id)
    }

    views: list[CaregiverMedicationView] = []
    for medication in medications:
        rows = schedules.get(medication.id, [])
        live = [row for row in rows if row.is_active and row.paused_at is None]
        supply = supplies.get(medication.id)
        dose = " ".join(part for part in (medication.dose, medication.dose_unit) if part)
        views.append(
            CaregiverMedicationView(
                medication_id=medication.id,
                name=medication.name,
                dose=dose or None,
                schedule_label=_schedule_label(live),
                reminders_paused=bool(rows) and not live,
                supply_low=supply is not None and supply_service.is_low(supply),
                remaining_doses=supply.remaining_doses if supply is not None else None,
                schedule_id=(live[0].id if live else (rows[0].id if rows else None)),
            )
        )
    return views


def adherence_for(
    db: Session, profile_id: uuid.UUID, local_date: date
) -> CaregiverAdherenceView:
    """A week of counts. ``percent`` is None when nothing was due."""
    window = adherence_service.calculate(
        db,
        profile_id,
        from_date=local_date - timedelta(days=ADHERENCE_DAYS - 1),
        to_date=local_date,
    )
    return CaregiverAdherenceView(
        from_date=window.from_date,
        to_date=window.to_date,
        taken=window.taken,
        skipped=window.skipped,
        missed=window.missed,
        percent=window.percent,
    )


# --- appointments ------------------------------------------------------------


def appointments_for(
    db: Session, profile_id: uuid.UUID, local_date: date, now: datetime
) -> list[CaregiverAppointmentView]:
    """Upcoming appointments, soonest first (section 26).

    Labels are rendered here for the reason PRD 7 renders them server-side: an
    appointment is shown in its own IANA zone and the app has no time-zone
    database to do it with.
    """
    upcoming = appointment_service.list_appointments(
        db, profile_id, scope="upcoming", now=now
    )[:MAX_ROWS]
    views: list[CaregiverAppointmentView] = []
    for appointment in upcoming:
        zone = appointment_service.local_zone(appointment)
        views.append(
            CaregiverAppointmentView(
                appointment_id=appointment.id,
                title=appointment.title,
                when_label=appointment_wording.when_label(
                    appointment.scheduled_at, zone, local_date
                ),
                day_label=appointment_wording.format_day(
                    appointment.scheduled_at.astimezone(zone).date()
                ),
                appointment_type=appointment.appointment_type,
                location_name=appointment.location_name,
                question_count=len(question_service.list_questions(db, appointment.id)),
                preparation_status=appointment.preparation_status,
            )
        )
    return views


# --- symptoms ----------------------------------------------------------------


def symptoms_for(db: Session, profile_id: uuid.UUID) -> list[CaregiverSymptomView]:
    """Active episodes and what was last recorded (section 28).

    Read-only by construction: there is no caregiver route that writes a symptom
    entry, and section 28 forbids a caregiver rewriting self-reported history. A
    caregiver-observation feature with its own provenance is a later PRD's call.
    """
    snapshots = symptom_summary.active_snapshots(db, profile_id)[:MAX_ROWS]
    return [
        CaregiverSymptomView(
            episode_id=snapshot.episode.id,
            name=snapshot.episode.name,
            status=snapshot.episode.status,
            severity=snapshot.severity,
            change_state=snapshot.change_state,
            last_recorded_at=(
                snapshot.latest.recorded_at if snapshot.latest is not None else None
            ),
        )
        for snapshot in snapshots
    ]


# --- reports -----------------------------------------------------------------


def reports_for(db: Session, profile_id: uuid.UUID) -> list[CaregiverReportView]:
    """That reports exist, and when. Never their contents (section 29).

    The snapshot is the whole point of a doctor report and it holds the
    sentences; a caregiver with ``reports`` is told one was prepared for the
    cardiology appointment on the 14th, which is what section 29's "view
    generated appointment reports" means without handing over a PDF this product
    has no caregiver download route for.
    """
    rows = list(
        db.execute(
            select(AppointmentReport, Appointment.title)
            .join(Appointment, Appointment.id == AppointmentReport.appointment_id)
            .where(Appointment.profile_id == profile_id)
            .order_by(AppointmentReport.generated_at.desc())
            .limit(MAX_ROWS)
        ).all()
    )
    return [
        CaregiverReportView(
            report_id=report.id,
            appointment_title=title,
            version=report.version,
            generated_at=report.generated_at,
            status=report.status,
        )
        for report, title in rows
    ]


# --- routines (PRD 12, sections 16, 20 and 42) -------------------------------


def routines_for(
    db: Session, profile_id: uuid.UUID, now: datetime
) -> list[CaregiverRoutineView]:
    """The routines a caregiver with ``routines`` may see.

    Narrower than the owner's own view, like every section in this module. A
    caregiver is told what the routine is called, when it runs, whether it is
    paused, and how far today's run has got -- which is what "view permitted
    routines" means for somebody trying to help. They are not shown the
    individual step completions as a history, because a tick-by-tick log of
    somebody's morning is the surveillance experience PRD 9 section 2 rules
    out.

    **Nothing from the other three categories is reachable through this.**
    Section 42 keeps tasks, alarms and general reminders private to the primary
    user, and this function queries ``routines`` and ``routine_runs`` only --
    there is no join here that could reach a task, and the caregiver API has no
    route that would.
    """
    rows = routine_service.list_routines(db, profile_id)
    runs = {
        run.routine_id: run for run in routine_service.runs_for_today(db, profile_id, now)
    }
    views = []
    for routine in rows[:MAX_ROWS]:
        if routine.status == "archived":
            continue
        run = runs.get(routine.id)
        progress = routine_service.progress(run) if run is not None else None
        views.append(
            CaregiverRoutineView(
                routine_id=routine.id,
                title=routine.title,
                schedule_label=productivity_wording.recurrence_sentence(
                    recurrence=routine.schedule_type,
                    time_of_day=routine.time_of_day,
                    weekdays=routine.weekdays,
                    start_date=routine.start_date,
                ),
                step_count=len(routine.steps),
                paused=routine.status == "paused",
                today_status=None if run is None else run.status,
                today_done=None if progress is None else progress.done,
                today_total=None if progress is None else progress.total,
            )
        )
    return views


# --- the home ----------------------------------------------------------------


def build_home(
    db: Session,
    scope: CareScope,
    *,
    local_date: date,
    now: datetime,
) -> CaregiverHome:
    """One request for the caregiver's Today (sections 17 and 60).

    Built permission by permission. Every ``if`` here is a category the
    caregiver was granted; there is no ``else`` that returns an empty list,
    because section 18 says the absence of a permission must not leak.
    """
    from app.services.caregivers import calls

    assert scope.relationship is not None, "a caregiver home needs a relationship"
    relationship = scope.relationship
    granted = sorted(scope.granted)

    home_kwargs: dict[str, object] = {}

    if scope.allows("medications"):
        home_kwargs["medications"] = medications_for(db, scope.profile.id)
        home_kwargs["adherence"] = adherence_for(db, scope.profile.id, local_date)
        doses = medication_summary.build_summary(db, scope.profile.id, local_date, now)
        home_kwargs["doses_remaining_today"] = doses.remaining_today_count
        home_kwargs["doses_overdue"] = doses.overdue_count

    if scope.allows("appointments"):
        home_kwargs["appointments"] = appointments_for(
            db, scope.profile.id, local_date, now
        )

    if scope.allows("symptoms"):
        home_kwargs["symptoms"] = symptoms_for(db, scope.profile.id)

    if scope.allows("reports"):
        home_kwargs["reports"] = reports_for(db, scope.profile.id)

    if scope.allows("routines"):
        home_kwargs["routines"] = routines_for(db, scope.profile.id, now)

    if scope.allows("general_health_summary"):
        summary = build_health_summary(db, scope.profile, now)
        allergy_count = next(
            (section.count for section in summary.sections if section.key == "allergies"),
            0,
        )
        home_kwargs["health_counts"] = CaregiverHealthCounts(
            active_conditions=summary.active_conditions,
            active_medications=summary.active_medications,
            active_symptoms=summary.active_symptoms,
            allergies=allergy_count,
        )

    if scope.allows("communication"):
        home_kwargs["unread_messages"] = messaging.unread_count(db, scope)

    if scope.allows("safety_alerts"):
        # PRD 10, sections 31 and 50. A count and the latest one: enough for a
        # caregiver to know something happened and open it, and nothing about
        # the person's health. The alert list itself is its own route.
        views = safety_alerts.list_for_caregiver(db, scope, limit=1)
        home_kwargs["unread_safety_alerts"] = safety_alerts.unread_count(db, scope)
        home_kwargs["latest_safety_alert"] = views[0] if views else None

    return CaregiverHome(
        profile_name=scope.profile.preferred_name,
        role=relationship.role,
        granted=granted,
        granted_without_data=[key for key in granted if not scope.usable(key)],
        pending_suggestions=len(
            suggestions.list_for_profile(
                db,
                scope.profile.id,
                relationship_id=relationship.id,
                open_only=True,
            )
        ),
        calling_available=calls.calling_available(),
        **home_kwargs,  # type: ignore[arg-type]
    )
