"""A visit that is coming up.

PRD 11, sections 23 and 52.

Short, and that is the point. Section 23 shows a clinician, a time and one
prompt, and then says not to put report contents on an idle display. So this
builder has no access to a report, no access to visit notes and no access to
the question list -- what it can see is the appointment's own title, who it is
with, and when. A reader checking whether a doctor's report can reach the robot
can check it by reading the four lines that build the payload.

Section 52 keeps the app the source of truth: the appointment's own reminders
are PRD 7's, this card is additional, and an appointment is never changed by
anything in this file.
"""

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.models import Appointment, Device, DevicePresentation
from app.services.robot import capabilities as capability_service
from app.services.robot import layouts, modes, preferences, queue, wording

logger = logging.getLogger(__name__)

SOURCE = "appointment"
PRESENTATION_TYPE = "appointment_reminder"

#: How far ahead an appointment is worth putting on a shelf. A day: section
#: 55 gives the card a 24-hour life, and a reminder that appears a week early
#: is a notification billboard, which section 3 rules out.
LEAD = timedelta(hours=24)

ACTIONS = ("open_app", "dismiss")


def source_id(appointment: Appointment) -> str:
    return str(appointment.id)


def is_upcoming(appointment: Appointment, now: datetime) -> bool:
    """Within the lead time, still scheduled, and reminders not switched off."""
    if appointment.status != "scheduled" or not appointment.reminders_enabled:
        return False
    return now <= appointment.scheduled_at <= now + LEAD


def days_away(appointment: Appointment, now: datetime) -> int:
    """Whole local days between today and the appointment's own day."""
    zone = ZoneInfo(appointment.timezone)
    local_day = appointment.scheduled_at.astimezone(zone).date()
    return (local_day - now.astimezone(zone).date()).days


def build(
    appointment: Appointment,
    *,
    now: datetime,
    has_input: bool,
) -> queue.PresentationRequest:
    """One appointment card (section 23)."""
    away = days_away(appointment, now)
    who = (
        appointment.clinician.name
        if appointment.clinician is not None
        else appointment.title
    )
    payload = layouts.build_payload(
        "REMINDER",
        title=wording.PRESENTATION_TITLES[PRESENTATION_TYPE],
        primary=who,
        secondary=wording.appointment_when_line(
            when=appointment.scheduled_at, zone=appointment.timezone, days_away=away
        ),
        prompt="Prepare now?" if has_input else None,
        actions=list(ACTIONS) if has_input else [],
        respond_in_app=not has_input,
        sensitive=True,
    )
    return queue.PresentationRequest(
        presentation_type=PRESENTATION_TYPE,
        layout="REMINDER",
        payload=payload,
        source=SOURCE,
        source_id=source_id(appointment),
        # The card stops being useful when the appointment has happened, which
        # is sooner than section 55's 24 hours for one booked for tonight.
        expires_at=min(appointment.scheduled_at, now + LEAD),
    )


def queue_for_appointment(
    db: Session,
    device: Device,
    appointment: Appointment,
    now: datetime,
    *,
    mode: modes.RobotMode | None = None,
) -> DevicePresentation | None:
    if not is_upcoming(appointment, now):
        return None
    states = capability_service.capability_map(db, device, now)
    preferences.resolved_for(db, device, now)
    request = build(appointment, now=now, has_input=capability_service.has_input(states))
    return queue.queue(db, device, request, now, mode=mode)


def cancel_for_appointment(
    db: Session,
    device: Device,
    appointment: Appointment,
    now: datetime,
    *,
    reason: str = "source_resolved",
) -> int:
    return queue.cancel_for_source(
        db,
        device.id,
        source=SOURCE,
        source_id=source_id(appointment),
        reason=reason,
        now=now,
        presentation_type=PRESENTATION_TYPE,
    )
