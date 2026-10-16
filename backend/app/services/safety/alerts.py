"""In-app safety alerts, and the only thing a caregiver may see of all this.

PRD 10, sections 31, 32, 37, 38, 50, 83, 84, 85, 86, 93, 97 and 104.

**One permission, checked on every read.** ``safety_alerts`` on an *active*
relationship, through PRD 9's ``CareScope``. Section 104 says the caregiver
path is the PRD 9 relationship path and that ``caregiver`` must not be added to
``account_profile_roles``; nothing here touches that table, and a caregiver
still cannot reach a single route written before PRD 9.

**Section 86 is the subtle one: permission is re-checked at read time, not at
creation time.** An alert row created last night for a caregiver whose
``safety_alerts`` was withdrawn this morning is not returned to them. The row
stays -- section 86 says historical records follow the retention policy, and
deleting evidence of what the system did is not a retention policy -- but the
caregiver's list is built from the permission they hold *now*.

**What a caregiver sees of an event, and what they do not** (sections 50 and
85). The type, the time, whether there was a response, and how the escalation
went. Not the health record, not symptoms, not medications, not the other
caregivers' names, and not the contents of the emergency-contact chain. The
view in this module is assembled field by field for exactly that reason: there
is no "return the event" path that could grow a field somebody did not think
about.

**Acknowledgement is not resolution** (sections 84 and 125). "I'm checking on
them" writes one timestamp. It does not resolve the event, it does not tell
the primary user they are safe, and it is not proof anybody went anywhere.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import SafetyAlert, SafetyEvent
from app.services.caregivers.permissions import CareScope
from app.services.errors import NotFoundError
from app.services.safety import audit

logger = logging.getLogger(__name__)

#: The permission that makes any of this visible (section 31).
SAFETY_PERMISSION = "safety_alerts"

#: How many alerts one request returns.
MAX_ALERTS = 50


class AlertNotFoundError(NotFoundError):
    code = "safety_alert_not_found"


@dataclass(frozen=True)
class AlertView:
    """One alert, with the little of the event a caregiver may see.

    Assembled field by field (section 85). Adding something to this dataclass
    is a deliberate act, which is the point: the alternative -- serialising the
    event row -- is how a symptom count ends up on a caregiver's screen.
    """

    id: uuid.UUID
    safety_event_id: uuid.UUID
    event_type: str
    triggered_at: datetime
    created_at: datetime
    read_at: datetime | None
    acknowledged_at: datetime | None
    #: Where the event stands now, so a caregiver is not left looking at an
    #: alert for something the person already said they were fine about.
    event_status: str
    event_resolution: str | None
    escalation_outcome: str | None
    #: How long the silence was, when there was one. Null when the user
    #: answered, and null for a manual request nobody was asked about.
    no_response_seconds: int | None
    #: The monitoring session's zone, so the sentence says the time the person
    #: it happened to would recognise. "UTC" when there was no session, which
    #: is the case for a manual request raised with monitoring off.
    zone: str


def _no_response_seconds(event: SafetyEvent) -> int | None:
    if event.user_response is not None:
        return None
    if event.response_deadline_at is None or event.check_started_at is None:
        return None
    return int((event.response_deadline_at - event.check_started_at).total_seconds())


def _view(alert: SafetyAlert, event: SafetyEvent) -> AlertView:
    return AlertView(
        id=alert.id,
        safety_event_id=event.id,
        event_type=event.event_type,
        triggered_at=event.triggered_at,
        created_at=alert.created_at,
        read_at=alert.read_at,
        acknowledged_at=alert.acknowledged_at,
        event_status=event.status,
        event_resolution=event.resolution,
        escalation_outcome=event.escalation_outcome,
        no_response_seconds=_no_response_seconds(event),
        zone=event.session.timezone if event.session is not None else "UTC",
    )


def list_for_caregiver(
    db: Session, scope: CareScope, *, limit: int = MAX_ALERTS
) -> list[AlertView]:
    """This caregiver's alerts about this person, newest first.

    The caller has already required ``safety_alerts`` on the scope -- that is
    section 86's re-check, and it happens on the route rather than here so the
    refusal is a 404 like every other missing permission. What this function
    additionally does is scope the query to *this relationship*: a caregiver
    who supports two people sees each person's alerts under that person, and
    never the other's.
    """
    assert scope.relationship is not None
    rows = db.execute(
        select(SafetyAlert, SafetyEvent)
        .join(SafetyEvent, SafetyEvent.id == SafetyAlert.safety_event_id)
        .where(
            SafetyAlert.relationship_id == scope.relationship.id,
            SafetyAlert.recipient_account_id == scope.relationship.caregiver_account_id,
        )
        .order_by(SafetyAlert.created_at.desc())
        .limit(min(limit, MAX_ALERTS))
    ).all()
    return [_view(alert, event) for alert, event in rows]


def get_for_caregiver(db: Session, scope: CareScope, alert_id: uuid.UUID) -> SafetyAlert:
    """One alert of this caregiver's, or 404.

    Scoped by relationship *and* by account, which is one more condition than
    strictly needed -- the relationship already implies the account. It is
    there because the implication is a CHECK constraint away, and an
    authorization query should not depend on a constraint to be correct.
    """
    assert scope.relationship is not None
    alert = db.execute(
        select(SafetyAlert).where(
            SafetyAlert.id == alert_id,
            SafetyAlert.relationship_id == scope.relationship.id,
            SafetyAlert.recipient_account_id == scope.relationship.caregiver_account_id,
        )
    ).scalar_one_or_none()
    if alert is None:
        raise AlertNotFoundError("Not found.")
    return alert


def mark_listed_read(
    db: Session, scope: CareScope, alert_ids: list[uuid.UUID], *, now: datetime
) -> int:
    """Marks the alerts a caregiver just opened as read. Returns how many moved.

    Writes once per alert and never again, so ``read_at`` keeps meaning "the
    first time they saw it" rather than "the last time the app refreshed".
    """
    if not alert_ids or scope.relationship is None:
        return 0
    rows = (
        db.execute(
            select(SafetyAlert).where(
                SafetyAlert.id.in_(alert_ids),
                SafetyAlert.relationship_id == scope.relationship.id,
                SafetyAlert.read_at.is_(None),
            )
        )
        .scalars()
        .all()
    )
    for alert in rows:
        alert.read_at = now
    if rows:
        db.commit()
    return len(rows)


def mark_read(db: Session, alert: SafetyAlert, *, now: datetime) -> SafetyAlert:
    """Records that the caregiver opened it. Writes once and never again.

    Section 37: an alert record proves an alert exists, not that anybody saw
    it. This is the only thing in the system that can turn the second into a
    fact, and it is written by the caregiver's own request.
    """
    if alert.read_at is None:
        alert.read_at = now
        db.commit()
        db.refresh(alert)
    return alert


def acknowledge(
    db: Session, alert: SafetyAlert, scope: CareScope, *, now: datetime
) -> SafetyAlert:
    """ "I'm checking on them" (section 84).

    One timestamp. It does not resolve the event (section 125), it does not
    message the primary user, and it does not claim the caregiver went
    anywhere -- it records that they said they would, which is a different and
    smaller thing that is nonetheless worth being able to answer for later.
    """
    assert scope.relationship is not None
    if alert.acknowledged_at is None:
        alert.acknowledged_at = now
        alert.read_at = alert.read_at or now
        audit.record(
            db,
            profile_id=alert.profile_id,
            actor_account_id=scope.relationship.caregiver_account_id,
            actor_kind="caregiver",
            event_type="alert_acknowledged",
            safety_event_id=alert.safety_event_id,
            now=now,
        )
        db.commit()
        db.refresh(alert)
        logger.info("safety.alert.acknowledged")
    return alert


def unread_count(db: Session, scope: CareScope) -> int:
    """How many of this caregiver's alerts are unopened. For the care home."""
    assert scope.relationship is not None
    return int(
        db.execute(
            select(func.count(SafetyAlert.id)).where(
                SafetyAlert.relationship_id == scope.relationship.id,
                SafetyAlert.read_at.is_(None),
            )
        ).scalar_one()
    )
