"""Appointment records (PRD 7, sections 4-8, 38, 40-42 and 48).

Manual entry only. There is no calendar sync in PRD 7 and nothing here reaches
outward: an appointment exists because somebody typed it (section 4).

Three rules live here rather than in the HTTP layer.

**Nothing is inferred from the clock.** An appointment whose time has passed is
listed under Past, but its status stays ``scheduled`` until the user says what
happened. Marking it ``missed`` automatically would tell somebody they missed an
appointment they attended, on the evidence that they did not open an app
(section 7).

**Cancelling keeps the row.** It is history, and a cancelled appointment is
often re-made; deleting is for one entered by mistake.

**An appointment carries its own time zone.** ``scheduled_at`` is the instant
and ``timezone`` is where it was arranged, so 3:30 PM in London stays 3:30 PM in
London when the clocks change and when the user is travelling (section 42).
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.models import Appointment, AppointmentQuestion, AppointmentReport, Clinician
from app.models.enums import APPOINTMENT_OPEN_STATUSES
from app.services.errors import DomainError, NotFoundError
from app.services.medications.doses import zone_for

logger = logging.getLogger(__name__)

#: How many appointments one profile may hold. High enough that nobody real
#: reaches it, low enough that a broken client cannot fill the table.
MAX_APPOINTMENTS = 500

#: Fields a client may set on create or PATCH. Everything else -- the status
#: timestamps, the preparation status -- is the server's own.
EDITABLE_FIELDS = frozenset(
    {
        "clinician_id",
        "title",
        "appointment_type",
        "scheduled_at",
        "timezone",
        "location_name",
        "address",
        "phone",
        "notes",
        "visit_notes",
        "follow_up_date",
        "reminders_enabled",
    }
)


class AppointmentNotFoundError(NotFoundError):
    """No such appointment for this profile."""


class TooManyAppointmentsError(DomainError):
    status_code = 409
    code = "too_many_appointments"


class UnknownClinicianError(DomainError):
    """The clinician id is not one of this profile's own."""

    status_code = 422
    code = "unknown_clinician"


def _log(action: str) -> None:
    """One line saying what happened, never what it was about.

    No title, no clinician, no location, no notes. An appointment says who
    somebody is seeing and when, which is health information
    (PRD 7, section 57).
    """
    logger.info("appointments: %s", action)


# --- reading ----------------------------------------------------------------


def _with_children() -> tuple[Any, ...]:
    """Eager loads for a row that will be rendered in full.

    Questions and reports are shown on the detail screen and counted on the
    list, so loading them with the appointment saves a query per row.
    """
    return (
        selectinload(Appointment.questions),
        selectinload(Appointment.reports),
        selectinload(Appointment.clinician),
    )


def list_appointments(
    db: Session,
    profile_id: uuid.UUID,
    *,
    scope: str | None = None,
    now: datetime | None = None,
) -> list[Appointment]:
    """This profile's appointments, in the order the scope wants them.

    ``upcoming`` is soonest first, because the next one is what somebody opened
    the screen for. ``past`` and ``cancelled`` are most recent first, because
    history reads backwards (PRD 7, section 41).

    An appointment still marked ``scheduled`` whose time has gone counts as
    past: it belongs in the history list, but its *status* is left alone until
    the user says what happened.
    """
    query = select(Appointment).where(Appointment.profile_id == profile_id)

    if scope == "upcoming":
        moment = now or datetime.now(tz=ZoneInfo("UTC"))
        query = query.where(
            Appointment.status.in_(APPOINTMENT_OPEN_STATUSES),
            Appointment.scheduled_at >= moment,
        ).order_by(Appointment.scheduled_at.asc())
    elif scope == "past":
        moment = now or datetime.now(tz=ZoneInfo("UTC"))
        query = query.where(
            or_(
                Appointment.status.in_(("completed", "missed")),
                Appointment.scheduled_at < moment,
            ),
            Appointment.status != "cancelled",
        ).order_by(Appointment.scheduled_at.desc())
    elif scope == "cancelled":
        query = query.where(Appointment.status == "cancelled").order_by(
            Appointment.scheduled_at.desc()
        )
    else:
        query = query.order_by(Appointment.scheduled_at.desc())

    return list(db.execute(query.options(*_with_children())).scalars().all())


def get_appointment(
    db: Session, profile_id: uuid.UUID, appointment_id: uuid.UUID
) -> Appointment:
    """One appointment, by profile *and* id together (PRD 7, section 51).

    Never by id alone. An appointment belonging to another profile is answered
    the same way as one that does not exist, so an id is never confirmed.
    """
    appointment = db.execute(
        select(Appointment)
        .where(
            Appointment.id == appointment_id,
            Appointment.profile_id == profile_id,
        )
        .options(*_with_children())
    ).scalar_one_or_none()

    if appointment is None:
        raise AppointmentNotFoundError("That appointment could not be found.")
    return appointment


def find_by_client_id(
    db: Session, profile_id: uuid.UUID, client_appointment_id: str
) -> Appointment | None:
    """The appointment a client already created with this id, if any (s53)."""
    return db.execute(
        select(Appointment)
        .where(
            Appointment.profile_id == profile_id,
            Appointment.client_appointment_id == client_appointment_id,
        )
        .options(*_with_children())
    ).scalar_one_or_none()


def next_upcoming(
    db: Session, profile_id: uuid.UUID, now: datetime
) -> Appointment | None:
    """The soonest appointment still ahead (PRD 7, section 9)."""
    return db.execute(
        select(Appointment)
        .where(
            Appointment.profile_id == profile_id,
            Appointment.status.in_(APPOINTMENT_OPEN_STATUSES),
            Appointment.scheduled_at >= now,
        )
        .order_by(Appointment.scheduled_at.asc())
        .limit(1)
        .options(*_with_children())
    ).scalar_one_or_none()


def has_any(db: Session, profile_id: uuid.UUID) -> bool:
    """Whether this profile has ever recorded an appointment.

    What lets Today draw an invitation rather than an empty card
    (PRD 7, section 9).
    """
    return (
        db.execute(
            select(Appointment.id).where(Appointment.profile_id == profile_id).limit(1)
        ).scalar_one_or_none()
        is not None
    )


def local_zone(appointment: Appointment) -> ZoneInfo:
    """The appointment's own zone, falling back to UTC if it is unknown here.

    A zone name that this machine cannot resolve must not stop an appointment
    being read: the fallback shows the right instant in the wrong zone, which is
    recoverable, where an exception on a list screen is not.
    """
    try:
        return zone_for(appointment.timezone)
    except DomainError:
        logger.warning("appointments: an appointment has an unresolvable time zone")
        return ZoneInfo("UTC")


def local_date(appointment: Appointment) -> date:
    """The calendar date the appointment is on, *there* (PRD 7, section 42)."""
    return appointment.scheduled_at.astimezone(local_zone(appointment)).date()


def previous_visit(
    db: Session, profile_id: uuid.UUID, appointment: Appointment
) -> Appointment | None:
    """The last appointment with the same clinician before this one.

    What "since my previous appointment with this clinician" means
    (PRD 7, section 14). Requires a linked clinician: two appointments that
    merely share a typed title are not evidence of the same doctor, and
    guessing would set a report period from a coincidence.

    Cancelled appointments do not count -- nobody was seen -- and neither does
    a future one.
    """
    if appointment.clinician_id is None:
        return None

    return db.execute(
        select(Appointment)
        .where(
            Appointment.profile_id == profile_id,
            Appointment.clinician_id == appointment.clinician_id,
            Appointment.id != appointment.id,
            Appointment.scheduled_at < appointment.scheduled_at,
            Appointment.status != "cancelled",
        )
        .order_by(Appointment.scheduled_at.desc())
        .limit(1)
    ).scalar_one_or_none()


# --- preparation status -----------------------------------------------------


def preparation_state(db: Session, appointment_id: uuid.UUID) -> str:
    """How far preparation has got, worked out from what exists.

    ``complete`` means a report has been generated and stored. ``in_progress``
    means the person has started -- they have added at least one question -- and
    ``not_started`` means neither (PRD 7, sections 6 and 10).

    Derived rather than declared, so the column can never say a report exists
    when it does not. The one stored copy is a cache that this function is the
    only writer of.
    """
    ready = db.execute(
        select(AppointmentReport.id)
        .where(
            AppointmentReport.appointment_id == appointment_id,
            AppointmentReport.status == "ready",
        )
        .limit(1)
    ).scalar_one_or_none()
    if ready is not None:
        return "complete"

    question = db.execute(
        select(AppointmentQuestion.id)
        .where(AppointmentQuestion.appointment_id == appointment_id)
        .limit(1)
    ).scalar_one_or_none()
    return "in_progress" if question is not None else "not_started"


def refresh_preparation_status(db: Session, appointment: Appointment) -> Appointment:
    """Brings the cached status back in line. Commits only if it moved."""
    state = preparation_state(db, appointment.id)
    if appointment.preparation_status != state:
        appointment.preparation_status = state
        db.commit()
        db.refresh(appointment)
    return appointment


# --- writing ----------------------------------------------------------------


@dataclass(frozen=True)
class AppointmentInput:
    """What a client may say about an appointment.

    A dataclass rather than a dict so the fields the API accepts are written
    down once, and so a field the server owns cannot arrive by accident.
    """

    title: str
    scheduled_at: datetime
    timezone: str
    appointment_type: str = "other"
    clinician_id: uuid.UUID | None = None
    location_name: str | None = None
    address: str | None = None
    phone: str | None = None
    notes: str | None = None
    reminders_enabled: bool = True
    client_appointment_id: str | None = None


def _check_clinician(
    db: Session, profile_id: uuid.UUID, clinician_id: uuid.UUID | None
) -> None:
    """Refuses a clinician that is not on this profile's own list.

    Without this, an appointment could point at another account's clinician
    record and read their name back out of it.
    """
    if clinician_id is None:
        return
    found = db.execute(
        select(Clinician.id).where(
            Clinician.id == clinician_id, Clinician.profile_id == profile_id
        )
    ).scalar_one_or_none()
    if found is None:
        raise UnknownClinicianError("That clinician could not be found.")


def _count(db: Session, profile_id: uuid.UUID) -> int:
    return len(
        db.execute(
            select(Appointment.id).where(Appointment.profile_id == profile_id)
        ).all()
    )


def create_appointment(
    db: Session, profile_id: uuid.UUID, data: AppointmentInput
) -> Appointment:
    """Records an appointment. Validates the zone before storing it."""
    if _count(db, profile_id) >= MAX_APPOINTMENTS:
        raise TooManyAppointmentsError("There are too many appointments already.")

    _check_clinician(db, profile_id, data.clinician_id)
    zone_for(data.timezone)  # raises UnknownTimezoneError, which is a 422

    appointment = Appointment(
        profile_id=profile_id,
        clinician_id=data.clinician_id,
        title=data.title,
        appointment_type=data.appointment_type,
        scheduled_at=data.scheduled_at,
        timezone=data.timezone,
        location_name=data.location_name,
        address=data.address,
        phone=data.phone,
        notes=data.notes,
        reminders_enabled=data.reminders_enabled,
        status="scheduled",
        preparation_status="not_started",
        client_appointment_id=data.client_appointment_id,
    )
    db.add(appointment)
    db.commit()
    db.refresh(appointment)
    _log("created an appointment")
    return appointment


def update_appointment(
    db: Session, appointment: Appointment, fields: dict[str, Any]
) -> Appointment:
    """Applies a PATCH. Only the fields a client owns, and only those sent."""
    if "clinician_id" in fields:
        _check_clinician(db, appointment.profile_id, fields["clinician_id"])
    if "timezone" in fields and fields["timezone"] is not None:
        zone_for(fields["timezone"])

    for key, value in fields.items():
        if key in EDITABLE_FIELDS:
            setattr(appointment, key, value)

    db.commit()
    db.refresh(appointment)
    _log("updated an appointment")
    return appointment


def cancel_appointment(
    db: Session, appointment: Appointment, now: datetime
) -> Appointment:
    """Marks an appointment cancelled, keeping everything about it.

    Idempotent, and it keeps the original ``cancelled_at`` rather than pushing
    the timestamp forward on a retry.
    """
    if appointment.status != "cancelled":
        appointment.status = "cancelled"
        appointment.cancelled_at = appointment.cancelled_at or now
        db.commit()
        db.refresh(appointment)
        _log("cancelled an appointment")
    return appointment


def complete_appointment(
    db: Session,
    appointment: Appointment,
    now: datetime,
    *,
    visit_notes: str | None = None,
    follow_up_date: date | None = None,
) -> Appointment:
    """Marks an appointment as attended, with optional notes (s38).

    The notes and the follow-up date are only written when supplied, so
    completing twice cannot blank what somebody wrote the first time.
    """
    if appointment.status != "completed":
        appointment.status = "completed"
        appointment.completed_at = appointment.completed_at or now
    if visit_notes is not None:
        appointment.visit_notes = visit_notes
    if follow_up_date is not None:
        appointment.follow_up_date = follow_up_date

    db.commit()
    db.refresh(appointment)
    _log("marked an appointment completed")
    return appointment


def reopen_appointment(db: Session, appointment: Appointment) -> Appointment:
    """Puts a cancelled or completed appointment back to ``scheduled``.

    For the ordinary mistake of tapping the wrong thing. The timestamps are
    left in place: they record that a decision was once made, and the CHECK
    constraints only require them in the other direction.
    """
    if appointment.status != "scheduled":
        appointment.status = "scheduled"
        db.commit()
        db.refresh(appointment)
        _log("reopened an appointment")
    return appointment


def delete_appointment(db: Session, appointment: Appointment) -> None:
    """Removes an appointment, its questions and its report rows.

    The stored PDF objects must be purged by the caller first: a database
    cascade cannot reach into storage (PRD 7, section 35).
    """
    db.delete(appointment)
    db.commit()
    _log("deleted an appointment")
