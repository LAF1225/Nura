"""What Today and Care need to know about appointments (PRD 7, sections 9-11).

Appointments join the Today response rather than adding a request, for the same
reason medications and symptoms did (PRD 3, section 16).

Unlike those two, this card draws something for *everybody*: PRD 7 section 9
specifies the empty state -- "No upcoming appointments" with a way to add one --
so ``has_appointments`` is reported but the card is not hidden when it is false.

**An appointment is never an alert.** PRD 7 section 10 says outright that
appointments in Important Today are not emergencies. So the wording is a time
and a place, nothing is coloured as a warning, and the strongest thing the
section can do is raise a row's prominence on the day itself.
"""

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Appointment, AppointmentQuestion, AppointmentReport
from app.models.enums import APPOINTMENT_OPEN_STATUSES
from app.services.appointments import appointments as appointment_service

#: How many appointment rows Important Today will carry. Two: somebody with
#: three appointments tomorrow needs the screen, not the summary.
MAX_IMPORTANT_ITEMS = 2

#: How far ahead Important Today looks (PRD 7, section 10). Today and tomorrow,
#: exactly as the PRD lists them -- an appointment next week is something to
#: know, not something to do today, and putting it here would make the section
#: permanent furniture.
IMPORTANT_WINDOW_DAYS = 1


@dataclass(frozen=True)
class AppointmentSnapshot:
    """One appointment as a summary talks about it."""

    appointment: Appointment
    #: The appointment's date in its own zone (PRD 7, section 42).
    local_date: date
    #: 0 for today, 1 for tomorrow, negative for one that has passed.
    days_away: int
    question_count: int
    report_count: int

    @property
    def preparation_complete(self) -> bool:
        return self.appointment.preparation_status == "complete"

    @property
    def is_today(self) -> bool:
        return self.days_away == 0


@dataclass(frozen=True)
class AppointmentSummary:
    """Today's appointments, as the dashboard talks about them."""

    #: The soonest one still ahead. None when there is nothing upcoming, which
    #: is the state PRD 7 section 9 gives its own wording to.
    next_appointment: AppointmentSnapshot | None = None
    upcoming_count: int = 0
    #: Ordered for Important Today: today first, then tomorrow.
    important: list[AppointmentSnapshot] = field(default_factory=list)
    #: False for somebody who has never added one. Reported, but it does not
    #: hide the card -- see the module docstring.
    has_appointments: bool = False


def _counts(
    db: Session, appointment_ids: list[uuid.UUID]
) -> tuple[dict[uuid.UUID, int], dict[uuid.UUID, int]]:
    """Questions and report versions per appointment, in two queries.

    Counted rather than loaded: the summary shows "3 added", not the questions
    themselves, and loading them to count them is how a dashboard gets slow.
    """
    if not appointment_ids:
        return {}, {}

    questions = {
        appointment_id: int(count)
        for appointment_id, count in db.execute(
            select(
                AppointmentQuestion.appointment_id,
                func.count(AppointmentQuestion.id),
            )
            .where(AppointmentQuestion.appointment_id.in_(appointment_ids))
            .group_by(AppointmentQuestion.appointment_id)
        ).all()
    }
    reports = {
        appointment_id: int(count)
        for appointment_id, count in db.execute(
            select(AppointmentReport.appointment_id, func.count(AppointmentReport.id))
            .where(AppointmentReport.appointment_id.in_(appointment_ids))
            .group_by(AppointmentReport.appointment_id)
        ).all()
    }
    return questions, reports


def snapshot_for(
    db: Session, appointment: Appointment, local_today: date
) -> AppointmentSnapshot:
    """One appointment with its counts, for a screen that needs just the one."""
    questions, reports = _counts(db, [appointment.id])
    appointment_day = appointment_service.local_date(appointment)
    return AppointmentSnapshot(
        appointment=appointment,
        local_date=appointment_day,
        days_away=(appointment_day - local_today).days,
        question_count=questions.get(appointment.id, 0),
        report_count=reports.get(appointment.id, 0),
    )


def build_summary(
    db: Session, profile_id: uuid.UUID, local_date: date, now: datetime
) -> AppointmentSummary:
    """Assembles the appointment part of Today.

    Reads only. Nothing is marked missed, completed or prepared as a side effect
    of drawing a screen -- PRD 7 section 7 rules out inferring what happened at an
    appointment, and a dashboard would be the worst place to do it.
    """
    upcoming = (
        db.execute(
            select(Appointment)
            .where(
                Appointment.profile_id == profile_id,
                Appointment.status.in_(APPOINTMENT_OPEN_STATUSES),
                Appointment.scheduled_at >= now,
            )
            .order_by(Appointment.scheduled_at.asc())
        )
        .scalars()
        .all()
    )

    questions, reports = _counts(db, [row.id for row in upcoming])

    snapshots: list[AppointmentSnapshot] = []
    for row in upcoming:
        appointment_day = appointment_service.local_date(row)
        snapshots.append(
            AppointmentSnapshot(
                appointment=row,
                local_date=appointment_day,
                days_away=(appointment_day - local_date).days,
                question_count=questions.get(row.id, 0),
                report_count=reports.get(row.id, 0),
            )
        )

    important = [
        snapshot
        for snapshot in snapshots
        if 0 <= snapshot.days_away <= IMPORTANT_WINDOW_DAYS
    ]

    return AppointmentSummary(
        next_appointment=snapshots[0] if snapshots else None,
        upcoming_count=len(snapshots),
        important=important[:MAX_IMPORTANT_ITEMS],
        has_appointments=appointment_service.has_any(db, profile_id),
    )
