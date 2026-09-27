"""How much of a medication is left (PRD 5, sections 31-35).

Deliberately the simplest thing that is useful: a number the user keeps, a
threshold they choose, and a decrement when they mark a dose taken. No pack
sizes, no units, no pharmacy, no inventory (PRD 5, section 31).

Two rules the whole module exists to keep:

**Only Taken moves the count.** Snooze, Skip and Missed leave it alone -- a
dose that was not taken is still in the packet (PRD 5, section 33).

**The count is the user's, and it is approximate.** Nura never corrects it,
never infers it from a prescription, and warns in cautious words because the
number came from a person estimating (PRD 5, section 34). Every value here is
editable by hand, including after Nura has changed it.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Medication, MedicationSupply

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SupplyOutcome:
    """What a decrement did, for the response that follows an action."""

    #: None when this medication has no supply tracking turned on.
    remaining: int | None
    #: True once the remaining count has reached the user's own threshold.
    low: bool = False


def get_supply(
    db: Session, profile_id: uuid.UUID, medication_id: uuid.UUID
) -> MedicationSupply | None:
    """This medication's supply record, or None if tracking was never set up."""
    return db.execute(
        select(MedicationSupply).where(
            MedicationSupply.medication_id == medication_id,
            MedicationSupply.profile_id == profile_id,
        )
    ).scalar_one_or_none()


def list_supply(
    db: Session, profile_id: uuid.UUID
) -> list[tuple[MedicationSupply, Medication]]:
    """Every supply record this profile keeps, with its medication.

    Joined rather than fetched per row: the screen shows a name against every
    count, and a request per row is exactly what PRD 3 section 16 warns
    against. An inner join also means a supply row whose medication has gone
    simply drops out instead of raising.
    """
    return list(
        db.execute(
            select(MedicationSupply, Medication)
            .join(Medication, Medication.id == MedicationSupply.medication_id)
            .where(MedicationSupply.profile_id == profile_id)
            .order_by(Medication.name.asc())
        )
        .tuples()
        .all()
    )


def is_low(supply: MedicationSupply) -> bool:
    """Whether Nura should mention a refill.

    Needs tracking on, a count, and a threshold the user set. Without a
    threshold there is no warning at all -- Nura does not invent one, because
    it has no idea how long a repeat prescription takes to arrive.
    """
    return (
        supply.tracking_enabled
        and supply.remaining_doses is not None
        and supply.refill_threshold_doses is not None
        and supply.remaining_doses <= supply.refill_threshold_doses
    )


def upsert_supply(
    db: Session,
    profile_id: uuid.UUID,
    medication_id: uuid.UUID,
    *,
    tracking_enabled: bool | None = None,
    remaining_doses: int | None = None,
    remaining_set: bool = False,
    refill_threshold_doses: int | None = None,
    threshold_set: bool = False,
    last_refill_date: date | None = None,
    last_refill_set: bool = False,
) -> MedicationSupply:
    """Creates or updates the supply record for one medication.

    The ``*_set`` flags distinguish "not mentioned" from "explicitly cleared",
    the same way the health setup PATCH does: omitting the threshold must
    leave it alone, while sending null must turn the warning off.
    """
    supply = get_supply(db, profile_id, medication_id)
    if supply is None:
        supply = MedicationSupply(profile_id=profile_id, medication_id=medication_id)
        db.add(supply)

    if tracking_enabled is not None:
        supply.tracking_enabled = tracking_enabled
    if remaining_set:
        supply.remaining_doses = remaining_doses
    if threshold_set:
        supply.refill_threshold_doses = refill_threshold_doses
    if last_refill_set:
        supply.last_refill_date = last_refill_date

    db.commit()
    db.refresh(supply)
    # A count is not a medical value, but it is still about someone's
    # medication, so the log says what happened and nothing else.
    logger.info("medication.supply.update success")
    return supply


def refill(
    db: Session,
    profile_id: uuid.UUID,
    medication_id: uuid.UUID,
    *,
    remaining_doses: int,
    on_date: date,
) -> MedicationSupply:
    """Records a refill: the user says how many they now have (PRD 5, s35).

    The new count replaces the old rather than being added to it. People count
    what is in front of them, not what they added to what they think was left.
    """
    supply = upsert_supply(
        db,
        profile_id,
        medication_id,
        tracking_enabled=True,
        remaining_doses=remaining_doses,
        remaining_set=True,
        last_refill_date=on_date,
        last_refill_set=True,
    )
    logger.info("medication.supply.refill success")
    return supply


def consume_one(db: Session, medication_id: uuid.UUID) -> SupplyOutcome:
    """Takes one off the count, if this medication is being tracked.

    Called only from the Taken transition, and only when that transition
    actually happens -- a re-sent Taken finds the dose already taken and never
    reaches here, which is what stops a retry from eating the packet
    (PRD 5, sections 33 and 48).

    Stops at zero rather than going negative: a count that has run out is
    information, and a negative one is only ever a bug looking like data.
    """
    supply = db.execute(
        select(MedicationSupply).where(MedicationSupply.medication_id == medication_id)
    ).scalar_one_or_none()

    if supply is None or not supply.tracking_enabled or supply.remaining_doses is None:
        return SupplyOutcome(remaining=None)

    supply.remaining_doses = max(0, supply.remaining_doses - 1)
    return SupplyOutcome(remaining=supply.remaining_doses, low=is_low(supply))


def return_one(db: Session, medication_id: uuid.UUID) -> int | None:
    """Puts one back, when a taken dose is corrected to skipped.

    Best-effort by design: it can only act on tracking that is on *now*, and
    the count stays editable by hand, which is the real answer to a supply
    figure that has drifted (PRD 5, section 33).
    """
    supply = db.execute(
        select(MedicationSupply).where(MedicationSupply.medication_id == medication_id)
    ).scalar_one_or_none()

    if supply is None or not supply.tracking_enabled or supply.remaining_doses is None:
        return None

    supply.remaining_doses += 1
    return supply.remaining_doses
