"""What Nura is told about the user before it asks for anything.

PRD 8, sections 11, 12, 51 and 78.

The shortest module in the assistant, on purpose. Section 12 asks for context
that is relevant, minimal, authorized and purpose-specific, and section 51
says to use explicit retrieval services rather than giving the model
unrestricted access -- so the answer to "how much of the record goes in the
prompt?" is: almost none of it. The model gets a date, a line saying what
*kinds* of records exist and how many, and ten tools it can call when a
question actually needs the contents.

That is the difference between minimal and merely small. This block contains
no medication name, no condition, no symptom, no note, no clinician and no
appointment title -- only counts. Somebody who asks Nura what the weather is
like has not had their prescriptions sent anywhere, and a test asserts it.

**Counts rather than nothing**, because the alternative costs a round trip
on every single message: without them the model cannot tell whether asking
about medications is worth a tool call, so it either always calls or never
does. Three numbers buy the judgement that saves the call.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.models import Appointment, Medication, SymptomEpisode
from app.models.enums import APPOINTMENT_OPEN_STATUSES, SYMPTOM_ACTIVE_STATUSES
from app.services.appointments import wording


def _scalar(db: Session, statement: Select[tuple[int]]) -> int:
    return int(db.execute(statement).scalar_one() or 0)


def build_block(
    db: Session,
    profile_id: uuid.UUID,
    *,
    local_date: date,
    now: datetime,
    mode: str = "normal",
) -> str:
    """The situational header for one reply.

    In Privacy mode it is the date alone: section 68 asks Nura not to bring
    up the record unless the current question needs it, and a standing line
    about how many symptoms somebody has is exactly the kind of thing that
    gets read over a shoulder. The tools still work -- a question that needs
    the record still gets an answer -- but nothing is volunteered.
    """
    lines = [f"Today is {wording.format_day(local_date)}."]

    if mode == "privacy":
        lines.append(
            "Privacy mode is on, so nothing about their records is included "
            "here. Use a tool if the question needs one."
        )
        return "\n".join(lines)

    medications = _scalar(
        db,
        select(func.count(Medication.id)).where(
            Medication.profile_id == profile_id,
            Medication.is_active.is_(True),
        ),
    )
    symptoms = _scalar(
        db,
        select(func.count(SymptomEpisode.id)).where(
            SymptomEpisode.profile_id == profile_id,
            SymptomEpisode.status.in_(SYMPTOM_ACTIVE_STATUSES),
        ),
    )
    appointments = _scalar(
        db,
        select(func.count(Appointment.id)).where(
            Appointment.profile_id == profile_id,
            Appointment.status.in_(APPOINTMENT_OPEN_STATUSES),
            Appointment.scheduled_at >= now,
        ),
    )

    # Through the shared wording helpers, so the assistant never says
    # "1 active medications" -- the same rule the rest of the app follows.
    lines.append(
        "They have "
        + wording.join_items(
            [
                wording.plural(medications, "active medication"),
                wording.plural(symptoms, "open symptom record"),
                wording.plural(appointments, "upcoming appointment"),
            ]
        )
        + " on file. These are counts only -- use a tool to read any of them."
    )
    return "\n".join(lines)
