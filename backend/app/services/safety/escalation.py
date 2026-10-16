"""Who gets reached, in what order, and what actually happened.

PRD 10, sections 29, 30, 31, 32, 33, 34, 35, 38, 39, 40, 41, 42, 75, 86, 87,
88, 124 and 127.

**The policy, written out** (section 40 asks for exactly this).

    1. Freeze the plan: the caregivers permitted right now, the active
       emergency contacts in their current priority order, the capability map,
       and the response timeout. This snapshot is stored on the event
       (sections 87 and 88) and the rest of the run reads it, so a chain
       reordered mid-emergency does not change who is being reached.
    2. Caregivers first, all of them at once, priority 0. A caregiver alert is
       an in-app record and costs nothing to create; there is no reason to
       make one wait behind a phone call that cannot happen.
    3. Then the emergency contacts, one at a time in priority order. For each,
       try the external channels in order -- a call before a text, because a
       call wakes somebody -- and **stop the whole chain at the first contact
       actually reached**. Section 40 says to continue when a contact is
       unavailable or fails; it does not say to ring everybody.
    4. Record the outcome.

Today step 3 reaches nobody, because no external provider exists. Every
contact therefore gets a row saying ``not_configured``, which is what makes
the user-facing list in section 42 truthful: *in-app alert created for Ayesha;
phone call for Ayesha: not set up in this build*. A chain that silently did
nothing would look identical to one that worked.

**Permission is re-checked here, not inherited** (section 86). The caregivers
in the plan are the ones with ``safety_alerts`` granted on an *active*
relationship at the moment escalation starts. A caregiver revoked a minute ago
is not in the plan, and a permission withdrawn between two escalations changes
the second one.

**Permission and preference are different things** (section 93). The
permission decides whether an alert exists for a caregiver at all. The
preference -- ``notify_safety_alerts`` on the relationship -- decides only
whether a push would be sent to them, and it can never create access: a
caregiver with the preference on and the permission off is not in the plan.

**Nothing claims a delivery.** An attempt moves to ``delivered`` only when a
provider says so, and no provider in this build ever says so (section 38). The
in-app channel records ``attempted``: the alert exists, and nobody has read it.

**Idempotent by construction** (section 75). Attempts are unique on (event,
recipient, channel) and alerts on (event, account), so a worker that runs the
same escalation twice updates rows rather than creating them. A second call to
``start`` on an event that already escalated returns what is there.

**It cannot get stuck** (section 127). The whole run is wrapped: anything that
raises leaves the event ``escalated`` with the outcome ``failed`` rather than
sitting in ``escalating`` forever.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    CaregiverRelationship,
    SafetyAlert,
    SafetyEscalationAttempt,
    SafetyEvent,
)
from app.models.enums import CAREGIVER_ACTIVE_STATUSES
from app.services.caregivers import contacts as contact_service
from app.services.caregivers import permissions as caregiver_permissions
from app.services.safety import audit, capabilities, providers, wording

logger = logging.getLogger(__name__)

#: The permission a caregiver needs to be in the plan at all (section 31).
SAFETY_PERMISSION = "safety_alerts"

#: The external channels tried for an emergency contact, in order. A call
#: before a text, because a call wakes somebody and a text does not.
CONTACT_CHANNELS = ("voice_call_future", "sms_future")

#: The channels tried for a caregiver. The in-app record always; a push only
#: when there is a provider *and* the caregiver asked for one.
CAREGIVER_CHANNELS = ("in_app", "push")

#: Caregivers sit at priority 0, outside the contact chain. Section 32: an
#: emergency contact and a caregiver are separate concepts and separate
#: pathways, and a shared numbering would imply one ordering over both.
CAREGIVER_PRIORITY = 0

#: The statuses that mean something actually happened.
REACHED_STATUSES = ("attempted", "delivered")


@dataclass(frozen=True)
class Recipient:
    """One person the plan will try, and the little that is known about them."""

    key: str
    label: str
    priority: int
    is_caregiver: bool
    contact_id: uuid.UUID | None = None
    relationship_id: uuid.UUID | None = None
    account_id: uuid.UUID | None = None
    phone: str | None = None
    #: Only meaningful for a caregiver: whether they asked to be pushed.
    wants_push: bool = False


def permitted_caregivers(
    db: Session, profile_id: uuid.UUID
) -> list[CaregiverRelationship]:
    """Active caregivers with ``safety_alerts`` granted, right now (section 31).

    Reads ``granted_keys``, which returns nothing for a relationship that is
    not active -- so revocation needs no separate check here, exactly as it
    needs none anywhere else in PRD 9's authorization path. A role is not
    consulted: section 31 says role names do not grant access, and the way to
    be sure is that this function never looks at the column.
    """
    relationships = (
        db.execute(
            select(CaregiverRelationship).where(
                CaregiverRelationship.profile_id == profile_id,
                CaregiverRelationship.status.in_(CAREGIVER_ACTIVE_STATUSES),
            )
        )
        .scalars()
        .all()
    )
    return [
        relationship
        for relationship in relationships
        if SAFETY_PERMISSION in caregiver_permissions.granted_keys(relationship)
    ]


def build_plan(db: Session, profile_id: uuid.UUID) -> list[Recipient]:
    """Everybody escalation will try, in the order it will try them.

    Caregivers first at priority 0, then the active emergency contacts in the
    priority order the user put them in (section 30). The PRD 9 chain is reused
    directly and nothing here re-sorts it: section 30 forbids a second
    competing priority model, so this function reads
    ``contacts.list_contacts`` and preserves its order.
    """
    plan: list[Recipient] = []

    for relationship in permitted_caregivers(db, profile_id):
        if relationship.caregiver_account_id is None:
            # Cannot happen for an active relationship -- a CHECK constraint
            # forbids it -- but an alert needs an account to belong to, and
            # asserting here would turn a data oddity into a failed escalation.
            continue
        plan.append(
            Recipient(
                key=f"caregiver:{relationship.id}",
                label=relationship.invited_name,
                priority=CAREGIVER_PRIORITY,
                is_caregiver=True,
                relationship_id=relationship.id,
                account_id=relationship.caregiver_account_id,
                wants_push=bool(relationship.notify_safety_alerts),
            )
        )

    for contact in contact_service.list_contacts(db, profile_id, active_only=True):
        plan.append(
            Recipient(
                key=f"contact:{contact.id}",
                label=contact.name,
                priority=contact.priority,
                is_caregiver=False,
                contact_id=contact.id,
                account_id=contact.account_id,
                phone=contact.phone,
            )
        )

    return plan


def snapshot(
    plan: list[Recipient], *, response_timeout_seconds: int | None
) -> dict[str, Any]:
    """The plan frozen at the moment escalation began (sections 87 and 88).

    Names and positions only. **No phone number goes in here**: section 121
    keeps safety logs to required operational data, a snapshot is read back by
    anybody who can read the event, and a number is not needed to answer "who
    was in the chain".
    """
    return {
        "response_timeout_seconds": response_timeout_seconds,
        "capabilities": capabilities.capability_map(),
        "recipients": [
            {
                "label": recipient.label,
                "priority": recipient.priority,
                "kind": "caregiver" if recipient.is_caregiver else "contact",
            }
            for recipient in plan
        ],
    }


def _attempt_row(
    db: Session,
    event: SafetyEvent,
    recipient: Recipient,
    channel: str,
    now: datetime,
) -> SafetyEscalationAttempt:
    """The attempt row for this (event, recipient, channel), made once.

    Section 75's idempotency in one place: a second escalation run for the same
    event finds the row it made last time and updates it, which is why a
    duplicated worker run cannot contact anybody twice.
    """
    existing = db.execute(
        select(SafetyEscalationAttempt).where(
            SafetyEscalationAttempt.safety_event_id == event.id,
            SafetyEscalationAttempt.recipient_key == recipient.key,
            SafetyEscalationAttempt.channel == channel,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    attempt = SafetyEscalationAttempt(
        safety_event_id=event.id,
        profile_id=event.profile_id,
        contact_id=recipient.contact_id,
        caregiver_relationship_id=recipient.relationship_id,
        recipient_key=recipient.key,
        recipient_label=recipient.label,
        priority=recipient.priority,
        channel=channel,
        status="pending",
    )
    db.add(attempt)
    db.flush()
    return attempt


def _apply(
    db: Session,
    event: SafetyEvent,
    attempt: SafetyEscalationAttempt,
    outcome: providers.DeliveryOutcome,
    now: datetime,
) -> None:
    """Writes one provider answer onto one attempt, and records it."""
    attempt.status = outcome.status
    attempt.provider = outcome.provider
    attempt.failure_code = outcome.failure_code
    attempt.attempted_at = now
    attempt.confirmed_at = outcome.confirmed_at
    attempt.updated_at = now

    event_type = {
        "delivered": "provider_confirmed",
        "failed": "provider_failed",
    }.get(outcome.status, "provider_attempted")
    audit.record(
        db,
        profile_id=event.profile_id,
        actor_account_id=None,
        actor_kind="system",
        event_type=event_type,
        safety_event_id=event.id,
        now=now,
        meta=audit.attempt_meta(
            channel=attempt.channel,
            status=outcome.status,
            failure_code=outcome.failure_code,
        ),
    )


def _alert_for(
    db: Session, event: SafetyEvent, recipient: Recipient, now: datetime
) -> SafetyAlert | None:
    """The in-app alert row for one caregiver, made once (sections 83 and 75)."""
    assert recipient.account_id is not None
    existing = db.execute(
        select(SafetyAlert).where(
            SafetyAlert.safety_event_id == event.id,
            SafetyAlert.recipient_account_id == recipient.account_id,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    assert recipient.relationship_id is not None
    alert = SafetyAlert(
        safety_event_id=event.id,
        profile_id=event.profile_id,
        recipient_account_id=recipient.account_id,
        relationship_id=recipient.relationship_id,
        created_at=now,
    )
    db.add(alert)
    db.flush()
    audit.record(
        db,
        profile_id=event.profile_id,
        actor_account_id=None,
        actor_kind="system",
        event_type="alert_created",
        safety_event_id=event.id,
        now=now,
    )
    return alert


def _summary_for(event: SafetyEvent) -> str:
    """The sentence a caregiver's alert carries (section 37).

    Built from the event's own fields and nothing else: a type, a time, and
    how long the silence was. Section 85 keeps unrelated health data out of a
    caregiver alert, and this function has none to leak.
    """
    zone = event.session.timezone if event.session is not None else "UTC"
    silence = None
    if event.response_deadline_at is not None and event.user_response is None:
        silence = int(
            (
                event.response_deadline_at
                - (event.check_started_at or event.triggered_at)
            ).total_seconds()
        )
    return wording.caregiver_alert_sentence(
        event_type=event.event_type,
        when=event.triggered_at,
        zone=zone,
        no_response_seconds=silence,
    )


def _decide_outcome(attempts: list[SafetyEscalationAttempt]) -> str:
    """How the whole run went (section 41).

    Read it as four questions in order: was there anybody, did anything
    happen, did everything happen, and if not, was the reason that nothing is
    configured? The last distinction is the one worth keeping: "Nura could not
    reach anybody" and "Nura has no way to reach anybody in this build" are
    different problems, and only the second is fixable by a deployment.
    """
    if not attempts:
        return "no_contacts"
    reached = [a for a in attempts if a.status in REACHED_STATUSES]
    unconfigured = [a for a in attempts if a.status == "not_configured"]
    if not reached:
        return "providers_not_configured" if unconfigured else "failed"
    if len(reached) == len(attempts):
        return "complete"
    return "partial"


def start(
    db: Session,
    event: SafetyEvent,
    *,
    now: datetime,
    reason: str,
) -> SafetyEvent:
    """Walks the plan. The caller holds the event row lock and commits.

    Returns the event with ``escalation_outcome`` set. Calling it again on an
    event that has already escalated is a no-op: the attempts and the alerts
    are already there, and section 75 says a repeat must not reach anybody
    twice.
    """
    if event.escalation_started_at is not None:
        return event

    plan = build_plan(db, event.profile_id)
    timeout = (
        event.session.response_timeout_seconds if event.session is not None else None
    )

    event.status = "escalating"
    event.escalation_started_at = now
    event.escalation_snapshot = snapshot(plan, response_timeout_seconds=timeout)
    event.updated_at = now
    db.flush()

    audit.record(
        db,
        profile_id=event.profile_id,
        actor_account_id=None,
        actor_kind="system",
        event_type="escalation_started",
        safety_event_id=event.id,
        now=now,
        meta=audit.escalation_meta(recipient_count=len(plan), reason=reason),
    )

    try:
        attempts = _run(db, event, plan, now)
        outcome = _decide_outcome(attempts)
    except Exception:  # pragma: no cover - defended, not expected
        # Section 127. An event left in ``escalating`` is an event nobody will
        # ever look at again, which is the worst possible failure mode for this
        # feature. Whatever went wrong, the row says so.
        logger.exception("safety: escalation failed")
        outcome = "failed"

    event.status = "escalated"
    event.escalation_finished_at = now
    event.escalation_outcome = outcome
    event.updated_at = now
    audit.record(
        db,
        profile_id=event.profile_id,
        actor_account_id=None,
        actor_kind="system",
        event_type="escalation_finished",
        safety_event_id=event.id,
        now=now,
        meta=audit.outcome_meta(outcome),
    )
    logger.info("safety.escalation.finished outcome=%s", outcome)
    return event


def _run(
    db: Session, event: SafetyEvent, plan: list[Recipient], now: datetime
) -> list[SafetyEscalationAttempt]:
    """The chain itself. Caregivers, then contacts until one is reached."""
    notifier = providers.get_notification_provider()
    caller = providers.get_call_provider()
    available = capabilities.available_channels()
    summary = _summary_for(event)
    attempts: list[SafetyEscalationAttempt] = []

    for recipient in plan:
        if not recipient.is_caregiver:
            continue
        _alert_for(db, event, recipient, now)
        attempt = _attempt_row(db, event, recipient, "in_app", now)
        _apply(
            db,
            event,
            attempt,
            notifier.send_in_app_alert(
                recipient=providers.AlertRecipient(
                    label=recipient.label, account_id=recipient.account_id
                ),
                summary=summary,
            ),
            now,
        )
        attempts.append(attempt)

        # A push only when there is a provider *and* the caregiver asked for
        # one (section 93). No provider exists, so this is never reached today.
        if "push" in available and recipient.wants_push:
            push = _attempt_row(db, event, recipient, "push", now)
            _apply(
                db,
                event,
                push,
                notifier.send_push_alert(
                    recipient=providers.AlertRecipient(
                        label=recipient.label, account_id=recipient.account_id
                    ),
                    title=wording.PUSH_TITLE,
                    body=wording.PUSH_BODY,
                ),
                now,
            )
            attempts.append(push)

    for recipient in plan:
        if recipient.is_caregiver:
            continue
        reached = False
        for channel in CONTACT_CHANNELS:
            attempt = _attempt_row(db, event, recipient, channel, now)
            target = providers.AlertRecipient(
                label=recipient.label,
                account_id=recipient.account_id,
                phone=recipient.phone,
            )
            if channel == "voice_call_future":
                outcome = (
                    caller.start_emergency_call(recipient=target, event_id=event.id)
                    if channel in available
                    else providers.DeliveryOutcome(
                        status="not_configured", failure_code="calling_not_configured"
                    )
                )
            else:
                outcome = (
                    notifier.send_sms_alert(recipient=target, body=summary)
                    if channel in available
                    else providers.DeliveryOutcome(
                        status="not_configured", failure_code="sms_not_configured"
                    )
                )
            _apply(db, event, attempt, outcome, now)
            attempts.append(attempt)
            if outcome.status in REACHED_STATUSES:
                reached = True
                break
        if reached:
            # Section 40: the chain stops at the first contact actually
            # reached. Everybody after them keeps their place in the snapshot
            # and gets no row, because nothing was tried.
            break

    return attempts


def cancel_unsent(db: Session, event: SafetyEvent, now: datetime) -> int:
    """Skips what has not gone out yet (sections 45 and 76).

    Already-attempted rows are left exactly as they are. Section 45 says
    delivered alerts cannot be recalled and section 76 says to preserve them;
    rewriting an attempt's history to make a cancellation look tidy would be
    the same lie as claiming a delivery.
    """
    pending = list(
        db.execute(
            select(SafetyEscalationAttempt).where(
                SafetyEscalationAttempt.safety_event_id == event.id,
                SafetyEscalationAttempt.status == "pending",
            )
        )
        .scalars()
        .all()
    )
    for attempt in pending:
        attempt.status = "skipped"
        attempt.updated_at = now
    return len(pending)


def attempts_for(db: Session, event_id: uuid.UUID) -> list[SafetyEscalationAttempt]:
    """Every attempt for an event, caregivers first then the chain in order."""
    return list(
        db.execute(
            select(SafetyEscalationAttempt)
            .where(SafetyEscalationAttempt.safety_event_id == event_id)
            .order_by(
                SafetyEscalationAttempt.priority.asc(),
                SafetyEscalationAttempt.created_at.asc(),
            )
        )
        .scalars()
        .all()
    )


def retryable(
    db: Session, now: datetime, *, limit: int = 100
) -> list[SafetyEscalationAttempt]:
    """Failed attempts that are due for another try (sections 112 and 124).

    Bounded by ``providers.MAX_RETRIES`` and spaced by its backoff, both read
    from one place. ``not_configured`` is never retried: a build with no SMS
    provider will not grow one in thirty seconds, and retrying it would fill
    the trail with rows that say the same thing.
    """
    candidates = (
        db.execute(
            select(SafetyEscalationAttempt)
            .where(
                SafetyEscalationAttempt.status == "failed",
                SafetyEscalationAttempt.retry_count < providers.MAX_RETRIES,
            )
            .order_by(SafetyEscalationAttempt.attempted_at.asc())
            .limit(limit)
        )
        .scalars()
        .all()
    )
    due = []
    for attempt in candidates:
        wait = providers.retry_due_after(attempt.retry_count)
        if wait is None or attempt.attempted_at is None:
            continue
        if attempt.attempted_at + timedelta(seconds=wait) <= now:
            due.append(attempt)
    return due


def retry(db: Session, attempt: SafetyEscalationAttempt, now: datetime) -> None:
    """One more try at one attempt. The caller commits.

    Increments ``retry_count`` whatever happens, so a channel that keeps
    failing stops being tried rather than being tried forever.
    """
    event = db.get(SafetyEvent, attempt.safety_event_id)
    if event is None:  # pragma: no cover - the FK makes this impossible
        return
    notifier = providers.get_notification_provider()
    caller = providers.get_call_provider()
    target = providers.AlertRecipient(label=attempt.recipient_label)

    if attempt.channel == "in_app":
        outcome = notifier.send_in_app_alert(
            recipient=target, summary=_summary_for(event)
        )
    elif attempt.channel == "push":
        outcome = notifier.send_push_alert(
            recipient=target, title=wording.PUSH_TITLE, body=wording.PUSH_BODY
        )
    elif attempt.channel == "sms_future":
        outcome = notifier.send_sms_alert(recipient=target, body=_summary_for(event))
    else:
        outcome = caller.start_emergency_call(recipient=target, event_id=event.id)

    attempt.retry_count += 1
    _apply(db, event, attempt, outcome, now)
