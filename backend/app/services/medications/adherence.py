"""The adherence figure (PRD 5, section 27).

One number, defined once, with its denominator stated plainly:

    taken / (taken + skipped + missed)

Cancelled doses are excluded -- nobody was ever asked to take them -- and so
is anything still in the future, which has not happened yet and would
otherwise drag every percentage down as the day went on.

**What this number is not.** It is not a score, not a grade, and not a
clinical measure. Nura never calls it adequate or inadequate, never sets a
target, and never draws a conclusion from it (PRD 5, sections 27 and 57).
The app shows it as a plain sentence for the user's own information.
"""

import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import MedicationDose

#: Counted in the denominator. The definition lives here rather than in a
#: query so the documentation and the code cannot drift.
COUNTED_STATUSES = ("taken", "skipped", "missed")


@dataclass(frozen=True)
class Adherence:
    from_date: date
    to_date: date
    taken: int
    skipped: int
    missed: int
    #: taken + skipped + missed. Zero when nothing was due in the window.
    total: int
    #: None when the total is zero: "0%" for a week with no doses would be a
    #: statement about the person, and it is only a statement about the data.
    percent: int | None


def calculate(
    db: Session,
    profile_id: uuid.UUID,
    *,
    from_date: date,
    to_date: date,
    medication_id: uuid.UUID | None = None,
) -> Adherence:
    """Counts a window of the user's own local days.

    Filtered on ``local_date`` so "the last 7 days" is seven of *their* days,
    not seven UTC days with an evening dose spilling over the edge.
    """
    query = (
        select(MedicationDose.status, func.count(MedicationDose.id))
        .where(
            MedicationDose.profile_id == profile_id,
            MedicationDose.local_date >= from_date,
            MedicationDose.local_date <= to_date,
            MedicationDose.status.in_(COUNTED_STATUSES),
        )
        .group_by(MedicationDose.status)
    )
    if medication_id is not None:
        query = query.where(MedicationDose.medication_id == medication_id)

    counts = {status: int(count) for status, count in db.execute(query).all()}
    taken = counts.get("taken", 0)
    skipped = counts.get("skipped", 0)
    missed = counts.get("missed", 0)
    total = taken + skipped + missed

    return Adherence(
        from_date=from_date,
        to_date=to_date,
        taken=taken,
        skipped=skipped,
        missed=missed,
        total=total,
        # Rounded down, so a figure never claims more than happened.
        percent=None if total == 0 else int(taken * 100 / total),
    )
