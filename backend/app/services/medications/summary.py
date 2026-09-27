"""What Today needs to know about medications (PRD 5, sections 28, 29 and 53).

Today already assembles the whole day in one request, and medications join
that response rather than adding a second one (PRD 3, section 16). The payload
is kept small on purpose: the next dose, three counts, and anything running
low. Everything else is a tap away on the Care tab.

**Nothing here is an alarm.** A medication reminder is a routine part of
somebody's day, not an emergency, and the ordering below says so: an overdue
dose sorts first because it is the one still waiting to be recorded, and it is
still described in plain, unhurried words (PRD 5, sections 24 and 29).
"""

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Medication, MedicationDose, MedicationSupply
from app.services.medications import doses as dose_service
from app.services.medications import supply as supply_service

#: How many medication rows Important Today will carry. Enough to be useful,
#: few enough that the section stays a glance rather than a list
#: (PRD 3, section 21).
MAX_IMPORTANT_ITEMS = 3

#: Where each window sorts in Important Today (PRD 5, section 29).
WINDOW_ORDER = {"overdue": 0, "due": 1, "upcoming": 2, "completed": 3}


@dataclass(frozen=True)
class LowSupply:
    medication_id: uuid.UUID
    medication_name: str
    remaining_doses: int


@dataclass(frozen=True)
class MedicationSummary:
    """Today's medications, as the dashboard talks about them."""

    #: The soonest dose still waiting to be recorded, overdue ones included.
    next_due: MedicationDose | None
    #: Doses on the user's local day, whatever their status.
    due_today_count: int
    #: Past their grace period and still unrecorded -- today's or earlier.
    overdue_count: int
    #: Still to be recorded today, which is what "2 later today" counts.
    remaining_today_count: int
    #: Ordered for Important Today: overdue, then due, then upcoming.
    important: list[MedicationDose] = field(default_factory=list)
    low_supply: list[LowSupply] = field(default_factory=list)
    #: False when this profile has no schedules at all, which is what lets
    #: Today leave the medication card out entirely rather than showing an
    #: empty one (PRD 3, section 18).
    has_schedules: bool = False


def _waiting(dose: MedicationDose) -> bool:
    """Still expecting the person to record something."""
    return dose.status in ("scheduled", "snoozed", "missed")


def build_summary(
    db: Session, profile_id: uuid.UUID, local_date: date, now: datetime
) -> MedicationSummary:
    """Assembles the medication part of Today.

    Reads only: the caller replenishes first, so this never generates doses
    as a side effect of drawing a screen.
    """
    from app.models import MedicationSchedule

    today = dose_service.list_doses(
        db, profile_id, from_date=local_date, to_date=local_date
    )

    # Overdue doses from earlier days still want recording, so they are
    # fetched beyond today's window -- someone who did not open the app
    # yesterday should not have yesterday's dose disappear silently.
    unrecorded = (
        db.execute(
            select(MedicationDose)
            .where(
                MedicationDose.profile_id == profile_id,
                MedicationDose.status.in_(("scheduled", "snoozed", "missed")),
                MedicationDose.local_date <= local_date,
            )
            .order_by(MedicationDose.scheduled_for.asc())
            .options(selectinload(MedicationDose.medication))
        )
        .scalars()
        .all()
    )

    overdue = [dose for dose in unrecorded if dose_service.window(dose, now) == "overdue"]

    # The next thing to do: whatever is waiting soonest, today or ahead of it.
    upcoming = (
        db.execute(
            select(MedicationDose)
            .where(
                MedicationDose.profile_id == profile_id,
                MedicationDose.status.in_(("scheduled", "snoozed")),
                MedicationDose.scheduled_for >= now,
            )
            .order_by(MedicationDose.scheduled_for.asc())
            .limit(1)
            .options(selectinload(MedicationDose.medication))
        )
        .scalars()
        .all()
    )

    candidates = [*overdue, *upcoming]
    candidates.sort(
        key=lambda dose: (
            WINDOW_ORDER[dose_service.window(dose, now)],
            dose_service.due_at(dose),
        )
    )

    has_schedules = (
        db.execute(
            select(MedicationSchedule.id)
            .where(MedicationSchedule.profile_id == profile_id)
            .limit(1)
        ).scalar_one_or_none()
        is not None
    )

    return MedicationSummary(
        next_due=candidates[0] if candidates else None,
        due_today_count=len(today),
        overdue_count=len(overdue),
        remaining_today_count=len([dose for dose in today if _waiting(dose)]),
        important=candidates[:MAX_IMPORTANT_ITEMS],
        low_supply=low_supply(db, profile_id),
        has_schedules=has_schedules,
    )


def low_supply(db: Session, profile_id: uuid.UUID) -> list[LowSupply]:
    """Medications at or below the threshold the user chose (PRD 5, s34).

    Only ever the user's own numbers. Nura does not estimate how long a supply
    will last, and does not warn about a medication whose threshold nobody
    set.
    """
    rows = (
        db.execute(
            select(MedicationSupply, Medication)
            .join(Medication, Medication.id == MedicationSupply.medication_id)
            .where(
                MedicationSupply.profile_id == profile_id,
                MedicationSupply.tracking_enabled.is_(True),
            )
        )
        .tuples()
        .all()
    )

    return [
        LowSupply(
            medication_id=medication.id,
            medication_name=medication.name,
            remaining_doses=supply.remaining_doses or 0,
        )
        for supply, medication in rows
        if supply_service.is_low(supply)
    ]
