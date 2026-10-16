"""The check-in, the deadlines, and what happens when nobody answers.

PRD 10, sections 8, 23, 24, 25, 26, 27, 28, 44, 45, 46, 47, 48, 76, 78, 79,
80, 112, 126 and 127.

**Every deadline is a column** (section 28). ``response_deadline_at`` is
written the moment the check starts and ``second_prompt_deadline_at`` the
moment the second prompt is sent. Nothing is held in memory, nothing depends
on a screen staying open, and a backend that restarts mid-countdown resumes by
running the same query it would have run anyway. Section 79 asks for a durable
mechanism and the durable mechanism is a ``WHERE deadline <= now``.

**The exact second-prompt timing, since section 8 asks for it in writing.**
The first wait is the session's ``response_timeout_seconds`` -- 15, 30, 45, 60
or 90, defaulting to 45. If the second prompt is enabled, running out of the
first wait *sends another prompt* rather than escalating, and starts a second
wait of ``SECOND_PROMPT_TIMEOUT_SECONDS``: **20 seconds, always**, whatever the
first was. Running out of that escalates. If the second prompt is off, running
out of the first wait escalates directly. Worst case with the longest timeout
and the second prompt on: 110 seconds from trigger to escalation.

**The race in section 76 is settled by the database.** Every transition takes
``SELECT ... FOR UPDATE`` on the event row first and re-reads the status it
locked. If the user's "I'm okay" wins, the worker finds a resolved event and
does nothing. If the worker wins, the user's answer is recorded as a late one
(section 126): already-created alerts stay, unsent attempts are skipped, and
the event resolves. Section 78 is explicit that disabling a button is not
enough, and no button is involved in either path.

**An event never gets stuck** (section 127). The only non-terminal statuses
are the ones with a deadline on them or an escalation in flight, and the
worker's query covers both.

**"I'm okay" contacts nobody** (section 25). It resolves the event, cancels
what has not gone out, and that is all -- there is no "they are fine now"
message to a caregiver, because nobody asked for one and section 25 says not
to.
"""

import logging
import uuid
from datetime import datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import SafetyEvent, SafetyMonitoringSession, User
from app.models.enums import (
    DEFAULT_SAFETY_RESPONSE_TIMEOUT_SECONDS,
    SAFETY_EVENT_AWAITING_RESPONSE_STATUSES,
    SAFETY_EVENT_EMERGENCY_STATUSES,
    SAFETY_EVENT_LIVE_STATUSES,
    SAFETY_FALSE_POSITIVE_REASONS,
    SAFETY_USER_RESPONSES,
)
from app.services.errors import DomainError
from app.services.safety import audit, escalation

logger = logging.getLogger(__name__)


class ActiveEventError(DomainError):
    """Something was asked for that a live safety event makes unsafe.

    Section 62: stopping monitoring while an event is in flight needs explicit
    confirmation. A distinct code, so the app can tell "confirm this" apart
    from "that already finished" and show the right dialog.
    """

    status_code = 409
    code = "safety_event_in_progress"


class EventNotLiveError(DomainError):
    """The event has already finished.

    409: the request made sense, the event moved on. Answering an event that
    resolved while the screen was open is common enough that the app handles
    this code by refreshing rather than by showing an error.
    """

    status_code = 409
    code = "safety_event_not_live"


def lock(db: Session, event: SafetyEvent) -> SafetyEvent:
    """Takes the row lock section 78 asks for, and returns the fresh row.

    ``with_for_update`` rather than an optimistic check: two writers here are
    a user and a worker racing over whether somebody's emergency contacts get
    called, and the cost of a row lock held for a few milliseconds is nothing
    against the cost of both branches running.
    """
    locked = db.execute(
        select(SafetyEvent).where(SafetyEvent.id == event.id).with_for_update()
    ).scalar_one()
    db.refresh(locked)
    return locked


def timeout_for(session: SafetyMonitoringSession | None) -> int:
    """The first wait, in seconds. The session's, or the default."""
    if session is None:
        return DEFAULT_SAFETY_RESPONSE_TIMEOUT_SECONDS
    return session.response_timeout_seconds


def begin_check(
    db: Session,
    event: SafetyEvent,
    session: SafetyMonitoringSession | None,
    *,
    now: datetime,
) -> SafetyEvent:
    """Asks the user whether they are okay, and starts the clock (section 23).

    The prompt itself is the app's job -- it renders
    ``wording.check_in_prompt`` -- and this is the server half: the status, the
    moment it started, and the instant it runs out.
    """
    seconds = timeout_for(session)
    event.status = "checking_user"
    event.check_started_at = now
    event.response_deadline_at = now + timedelta(seconds=seconds)
    event.updated_at = now
    audit.record(
        db,
        profile_id=event.profile_id,
        actor_account_id=None,
        actor_kind="system",
        event_type="user_prompted",
        safety_event_id=event.id,
        now=now,
        meta=audit.timeout_meta(seconds, second_prompt=False),
    )
    return event


def send_second_prompt(
    db: Session,
    event: SafetyEvent,
    session: SafetyMonitoringSession | None,
    *,
    now: datetime,
) -> SafetyEvent:
    """Asks once more, on the shorter wait (section 8)."""
    seconds = (
        session.second_prompt_timeout_seconds
        if session is not None
        else 20  # the same constant; a sessionless event cannot reach here
    )
    event.status = "second_prompt"
    event.second_prompt_at = now
    event.second_prompt_deadline_at = now + timedelta(seconds=seconds)
    event.updated_at = now
    audit.record(
        db,
        profile_id=event.profile_id,
        actor_account_id=None,
        actor_kind="system",
        event_type="second_prompt_sent",
        safety_event_id=event.id,
        now=now,
        meta=audit.timeout_meta(seconds, second_prompt=True),
    )
    logger.info("safety.check.second_prompt")
    return event


def escalate_now(
    db: Session, event: SafetyEvent, *, now: datetime, reason: str
) -> SafetyEvent:
    """Starts escalation for this event. Idempotent."""
    return escalation.start(db, event, now=now, reason=reason)


def _resolve(
    db: Session,
    event: SafetyEvent,
    *,
    resolution: str,
    now: datetime,
    actor_account_id: uuid.UUID | None,
    actor_kind: str,
    late: bool,
) -> SafetyEvent:
    """Ends the event and stops anything that has not gone out."""
    escalation.cancel_unsent(db, event, now)
    event.status = "cancelled" if resolution == "cancelled_by_user" else "resolved"
    event.resolution = resolution
    event.resolved_at = now
    event.updated_at = now
    audit.record(
        db,
        profile_id=event.profile_id,
        actor_account_id=actor_account_id,
        actor_kind=actor_kind,
        event_type=(
            "event_cancelled" if resolution == "cancelled_by_user" else "event_resolved"
        ),
        safety_event_id=event.id,
        now=now,
        meta=audit.resolution_meta(resolution, late=late),
    )
    return event


def respond(
    db: Session,
    event: SafetyEvent,
    *,
    response: str,
    actor: User | None,
    now: datetime,
    actor_kind: str = "primary_user",
) -> SafetyEvent:
    """The user's answer to a safety check (sections 25, 26 and 126).

    Three answers:

    ``im_okay``      resolves the event, cancels what has not gone out, and
                     contacts nobody (section 25).
    ``need_help``    skips the rest of the countdown and escalates at once
                     (section 26). The event stays live afterwards, because
                     escalation starting is not the same as the person being
                     all right -- it ends when they say so or cancel it.
    ``false_alarm``  resolves it and labels it in one step (section 23's
                     optional dismissal).

    Works after escalation has already begun. Section 126 says a late "I'm
    okay" records the response, stops the unsent steps and preserves the
    history, which is exactly what happens: the alerts stay, the pending
    attempts become ``skipped``, and the trail says the answer was late.
    """
    assert response in SAFETY_USER_RESPONSES, response
    event = lock(db, event)
    if event.status not in SAFETY_EVENT_LIVE_STATUSES:
        raise EventNotLiveError("That safety event has already finished.")

    late = event.status in SAFETY_EVENT_EMERGENCY_STATUSES
    event.user_response = response
    event.response_at = now
    actor_id = actor.id if actor is not None else None

    if response == "need_help":
        audit.record(
            db,
            profile_id=event.profile_id,
            actor_account_id=actor_id,
            actor_kind=actor_kind,
            event_type="user_requested_help",
            safety_event_id=event.id,
            now=now,
        )
        escalate_now(db, event, now=now, reason="help_requested")
        db.commit()
        db.refresh(event)
        logger.info("safety.check.help_requested")
        return event

    audit.record(
        db,
        profile_id=event.profile_id,
        actor_account_id=actor_id,
        actor_kind=actor_kind,
        event_type="user_responded_ok",
        safety_event_id=event.id,
        now=now,
        meta=audit.resolution_meta("user_confirmed_ok", late=late),
    )
    if response == "false_alarm":
        event.false_positive = True
        _resolve(
            db,
            event,
            resolution="false_alarm",
            now=now,
            actor_account_id=actor_id,
            actor_kind=actor_kind,
            late=late,
        )
    else:
        _resolve(
            db,
            event,
            resolution="user_confirmed_ok",
            now=now,
            actor_account_id=actor_id,
            actor_kind=actor_kind,
            late=late,
        )
    db.commit()
    db.refresh(event)
    logger.info("safety.check.resolved late=%s", late)
    return event


def cancel(db: Session, event: SafetyEvent, actor: User, *, now: datetime) -> SafetyEvent:
    """Stops an emergency request (section 45).

    "This stops further escalation attempts that have not already been sent."
    Already-delivered alerts cannot be recalled and are not touched -- a
    cancellation that quietly deleted the alerts a caregiver can already see
    would be worse than no cancellation at all.
    """
    event = lock(db, event)
    if event.status not in SAFETY_EVENT_LIVE_STATUSES:
        raise EventNotLiveError("That safety event has already finished.")
    _resolve(
        db,
        event,
        resolution="cancelled_by_user",
        now=now,
        actor_account_id=actor.id,
        actor_kind="primary_user",
        late=event.status in SAFETY_EVENT_EMERGENCY_STATUSES,
    )
    db.commit()
    db.refresh(event)
    logger.info("safety.event.cancelled")
    return event


def mark_false_alarm(
    db: Session,
    event: SafetyEvent,
    actor: User,
    *,
    false_positive: bool,
    reason: str | None,
    now: datetime,
) -> SafetyEvent:
    """Labels a finished event (sections 47 and 48).

    Asked after a safe dismissal and answerable either way: "No / Not sure"
    stores ``false_positive = false`` rather than leaving the field null, so
    "they said it was real" and "nobody asked" stay distinguishable.

    Section 48: none of this trains anything. There is no model in this
    project that reads these columns, and a later PRD that wants one needs a
    governance decision first -- which is a sentence in
    ``docs/architecture/safety-monitoring.md``, not a comment nobody reads.
    """
    assert reason is None or reason in SAFETY_FALSE_POSITIVE_REASONS, reason
    event.false_positive = false_positive
    event.false_positive_reason = reason if false_positive else None
    event.updated_at = now
    audit.record(
        db,
        profile_id=event.profile_id,
        actor_account_id=actor.id,
        actor_kind="primary_user",
        event_type="false_alarm_marked",
        safety_event_id=event.id,
        now=now,
        meta=audit.false_alarm_meta(false_positive=false_positive, reason=reason),
    )
    db.commit()
    db.refresh(event)
    logger.info("safety.event.false_alarm=%s", false_positive)
    return event


def advance(db: Session, event: SafetyEvent, now: datetime) -> SafetyEvent:
    """Moves one event past a deadline that has passed. The caller commits.

    Called by the worker and by the status endpoint, which is what makes
    section 80's distinction work: the *state* is correct the moment anybody
    looks, and the worker is what makes escalation *timely* for somebody whose
    phone is in another room. A test that never runs the worker still sees the
    right state; a test of timeliness has to run it, and
    ``tests/test_safety_worker.py`` does.

    Idempotent, and takes the row lock first, so running it twice in parallel
    escalates once.
    """
    event = lock(db, event)
    if event.status not in SAFETY_EVENT_AWAITING_RESPONSE_STATUSES:
        return event

    session = event.session

    if event.status == "checking_user":
        if event.response_deadline_at is None or event.response_deadline_at > now:
            return event
        audit.record(
            db,
            profile_id=event.profile_id,
            actor_account_id=None,
            actor_kind="system",
            event_type="response_timeout",
            safety_event_id=event.id,
            now=now,
            meta=audit.timeout_meta(timeout_for(session), second_prompt=False),
        )
        if session is not None and session.second_prompt_enabled:
            send_second_prompt(db, event, session, now=now)
            return event
        escalate_now(db, event, now=now, reason="no_response")
        return event

    # second_prompt
    if event.second_prompt_deadline_at is None or event.second_prompt_deadline_at > now:
        return event
    audit.record(
        db,
        profile_id=event.profile_id,
        actor_account_id=None,
        actor_kind="system",
        event_type="response_timeout",
        safety_event_id=event.id,
        now=now,
        meta=audit.timeout_meta(
            session.second_prompt_timeout_seconds if session else 20,
            second_prompt=True,
        ),
    )
    escalate_now(db, event, now=now, reason="no_response")
    return event


def due_events(db: Session, now: datetime, *, limit: int = 200) -> list[SafetyEvent]:
    """Every event whose deadline has passed (sections 79 and 81).

    One query over two indexed columns. Deliberately the whole mechanism:
    section 79 warns against heavy infrastructure, and a comparison against
    two timestamps is what a safety timeout actually is.
    """
    return list(
        db.execute(
            select(SafetyEvent)
            .where(
                SafetyEvent.status.in_(SAFETY_EVENT_AWAITING_RESPONSE_STATUSES),
                or_(
                    SafetyEvent.response_deadline_at <= now,
                    SafetyEvent.second_prompt_deadline_at <= now,
                ),
            )
            .order_by(SafetyEvent.triggered_at.asc())
            .limit(limit)
        )
        .scalars()
        .all()
    )
