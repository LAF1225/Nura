"""The presentation queue: ordering, preemption, expiry, acknowledgement.

PRD 11, sections 13-20, 55-57, 66, 67, 73, 83, 84, 87, 113, 114 and 123.

Section 73 lists what this has to do, and it is worth reading the list as one
sentence: build, apply privacy, apply priority, deduplicate, queue, expire,
select next, record acknowledgement. Privacy belongs to the builders, because
it is a property of the content; everything else is here.

**Ordering is a table, not a rule.** ``ROBOT_PRESENTATION_PRIORITIES`` ranks
every type once, the rank is copied onto the row, and selection is
``ORDER BY priority, available_at, created_at``. Section 16 asks only that the
ordering be deterministic; a rule evaluated at selection time would have been
deterministic too, right up until a second place evaluated it differently.

**Only safety preempts.** Section 17's example is an SOS taking the screen from
a family message, and that is what happens: a presentation in the safety band
cancels the ordinary cards that are on the screen. A medication reminder does
*not* cancel a displayed message, because a reminder can wait thirty seconds
and a cancelled message has lost the only moment it had. Section 17 says
higher priority *may* interrupt; this is where the "may" is decided.

**Nothing is displayed without a device saying so.** ``acknowledge`` is the
only writer of ``displayed_at``, and the CHECK constraint on the table means
even a future bug cannot write it from anywhere else. Sections 14, 19 and 141.

**A duplicate build finds the row that already exists.** Section 57's key is
``source:source_id:type``, computed by the builder, so a retried request, a
replayed job and two concurrent workers all converge on one card. For
everything except the idle face, that holds for the whole life of the row:
a dose reminded once is not reminded again by a retry an hour later. The face
is the exception, because a face is a state the robot returns to rather than an
occasion that happened once -- so its key folds only into a card that is still
open.

**Expiry is a stored instant and a comparison.** The same shape PRD 10 uses for
its deadlines: no timers, and a backend that restarted or a robot that was
unplugged for a day both behave identically. Safety and emergency
presentations have no expiry at all (section 113) -- they are tied to the live
PRD 10 event and are withdrawn when it resolves, which is section 114.
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy import update as sql_update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Device, DevicePresentation
from app.models.enums import (
    ROBOT_ACK_STATES,
    ROBOT_PRESENTATION_CANCEL_REASONS,
    ROBOT_PRESENTATION_FAILURE_CODES,
    ROBOT_PRESENTATION_OPEN_STATUSES,
    ROBOT_PRESENTATION_PRIORITIES,
    ROBOT_PRESENTATION_SOURCES,
    ROBOT_PRESENTATION_TYPES,
    ROBOT_SAFETY_PRIORITY_CEILING,
)
from app.models.robot import DEDUPE_KEY_MAX_LENGTH
from app.services.errors import DomainError
from app.services.robot import capabilities as capability_service
from app.services.robot import layouts, modes, preferences

logger = logging.getLogger(__name__)

#: The rank of each type, from the table in ``enums``.
PRIORITY: dict[str, int] = dict(ROBOT_PRESENTATION_PRIORITIES)

#: Section 55, with the values documented as that section asks.
#:
#: ``None`` means *no timer*, and it is not a longer timeout: section 113 ties
#: safety and emergency presentations to the live PRD 10 event, and the idle
#: face has nothing to expire into -- it is replaced, not withdrawn.
EXPIRY: dict[str, timedelta | None] = {
    # A reminder nobody saw within half an hour is no longer "now"
    # (section 56).
    "medication_reminder": timedelta(minutes=30),
    "appointment_reminder": timedelta(hours=24),
    "family_message": timedelta(hours=24),
    "assistant_response": timedelta(minutes=5),
    "info_card": timedelta(minutes=30),
    "system_status": timedelta(hours=1),
    # In the vocabulary for the firmware's own use; see ``builders``.
    "setup_code": timedelta(minutes=5),
    # PRD 12's four, and each window is the answer to "how long is this still
    # about now?".
    #
    # A task's card lives for an hour: a task due at four is still worth seeing
    # at half past, and by six it is one of the overdue ones the app lists
    # rather than something to put on a shelf.
    "task_reminder": timedelta(hours=1),
    # A reminder matches its occurrence's own grace period, so the card goes
    # when the occurrence stops being answerable (PRD 12, section 8).
    "general_reminder": timedelta(hours=2),
    # An alarm is a moment. Ten minutes later it is not an alarm any more, and
    # a card still saying "7:00 AM" at half past is worse than no card.
    "alarm": timedelta(minutes=10),
    # A routine card is progress through today's run, so it is good for the
    # rest of the day; the reconciler withdraws it the moment the run is done.
    "routine": timedelta(hours=12),
    "face_state": None,
    "safety_check": None,
    "safety_status": None,
    "emergency_status": None,
}
assert set(EXPIRY) == set(ROBOT_PRESENTATION_TYPES)

#: What a quiet mode silences (PRD 11, sections 31, 32 and 33). Medication and
#: appointment reminders are deliberately absent: section 31 says they follow
#: the reminder settings PRD 5 and PRD 7 already have, and a robot is not the
#: place to re-decide whether somebody should be reminded to take a tablet.
#:
#: PRD 12's three ordinary daily-life cards join the list, for the reason PRD 11
#: suppressed a family message: a task on a screen in a dark bedroom is not
#: what Sleep mode is for, and the phone's own notification is unaffected --
#: nothing about a task, a reminder or a routine depends on the robot
#: (PRD 12, section 31).
#:
#: ``alarm`` is **not** in this list, and that is the whole point of it being a
#: separate type. Section 4 defines an alarm as a time-critical alert whose
#: purpose is to get attention at a specific time; an alarm that Sleep mode
#: silenced would be an alarm that does not work, since the hour it is for is
#: exactly the hour the robot would be asleep. What the robot cannot do is
#: *sound* it -- the speaker reports ``not_connected`` -- so the card is
#: information and says so (PRD 12, section 65).
SUPPRESSED_IN_QUIET_MODES = (
    "family_message",
    "assistant_response",
    "info_card",
    "task_reminder",
    "general_reminder",
    "routine",
)

#: Types that are never suppressed, never preempted and never expired by a
#: timer. Section 72, and the reason PRD 10 exists.
SAFETY_TYPES = ("emergency_status", "safety_check", "safety_status")

#: How many rows the history endpoint will return (section 96).
MAX_HISTORY = 50


class PresentationNotFoundError(DomainError):
    """No such presentation for this device. 404 and nothing else."""

    status_code = 404
    code = "presentation_not_found"


class InvalidAcknowledgementError(DomainError):
    """A device reported a transition this presentation cannot make."""

    status_code = 409
    code = "invalid_acknowledgement"


@dataclass(frozen=True)
class PresentationRequest:
    """What a builder asks for. Not yet a row, and possibly never one.

    ``requires`` names the capability keys that have to be ``available`` for
    this to be worth sending (section 87). A request whose capabilities are
    missing is recorded as ``not_supported`` rather than dropped, so section
    96's history can say "Medication reminder — not supported on this Nura"
    instead of leaving a person wondering whether anything happened.
    """

    presentation_type: str
    layout: str
    payload: dict[str, object]
    source: str
    #: The thing this was built from -- a dose id, a message id, a face name.
    #: Section 57's middle term, and the reason a retry is free.
    source_id: str
    requires: tuple[str, ...] = ("display", "display_text")
    #: Overrides ``EXPIRY`` when a source knows better, e.g. a reminder that
    #: should stop at the end of the dose's own window.
    expires_at: datetime | None = None
    available_at: datetime | None = None
    #: True only for the idle face. See the module docstring.
    repeatable: bool = False
    #: Extra context for the log line. Never content (section 67).
    meta: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        assert self.presentation_type in ROBOT_PRESENTATION_TYPES
        assert self.source in ROBOT_PRESENTATION_SOURCES
        assert self.layout in layouts.LAYOUT_FIELDS

    @property
    def priority(self) -> int:
        return PRIORITY[self.presentation_type]

    @property
    def dedupe_key(self) -> str:
        return dedupe_key(self.source, self.source_id, self.presentation_type)


def dedupe_key(source: str, source_id: str, presentation_type: str) -> str:
    """Section 57's deterministic key, truncated to the column width.

    Truncated from the *front* of nothing -- the pieces are already short, and
    an id that would overflow the column is a bug rather than something to
    silently shorten. The assertion says so.
    """
    key = f"{source}:{source_id}:{presentation_type}"
    assert len(key) <= DEDUPE_KEY_MAX_LENGTH, key
    return key


# --- reading -----------------------------------------------------------------


def get(
    db: Session, device_id: uuid.UUID, presentation_id: uuid.UUID
) -> DevicePresentation:
    """One presentation of this device's, or a 404 that confirms nothing.

    The device is part of the lookup rather than checked afterwards, so there
    is no path that loads a presentation first and authorizes it second --
    section 69, and the same shape PRD 5 uses for doses. A robot cannot learn
    which presentation ids exist for anybody else by trying.
    """
    row = db.execute(
        select(DevicePresentation).where(
            DevicePresentation.id == presentation_id,
            DevicePresentation.device_id == device_id,
        )
    ).scalar_one_or_none()
    if row is None:
        raise PresentationNotFoundError("Not found.")
    return row


def open_presentations(db: Session, device_id: uuid.UUID) -> list[DevicePresentation]:
    return list(
        db.execute(
            select(DevicePresentation)
            .where(
                DevicePresentation.device_id == device_id,
                DevicePresentation.status.in_(ROBOT_PRESENTATION_OPEN_STATUSES),
            )
            .order_by(
                DevicePresentation.priority.asc(),
                DevicePresentation.available_at.asc(),
                DevicePresentation.created_at.asc(),
            )
        )
        .scalars()
        .all()
    )


def queue_depth(db: Session, device_id: uuid.UUID) -> int:
    """Section 65's diagnostic. Counts what is still the device's business."""
    return len(open_presentations(db, device_id))


def history(
    db: Session, device_id: uuid.UUID, *, limit: int = MAX_HISTORY
) -> list[DevicePresentation]:
    """Most recent first (section 96)."""
    return list(
        db.execute(
            select(DevicePresentation)
            .where(DevicePresentation.device_id == device_id)
            .order_by(DevicePresentation.created_at.desc())
            .limit(min(limit, MAX_HISTORY))
        )
        .scalars()
        .all()
    )


def has_pending(db: Session, device_id: uuid.UUID, now: datetime) -> bool:
    """Whether a fetch would return something (section 58).

    What the heartbeat answers with. Deliberately not "is the queue
    non-empty": a presentation the device has already acknowledged is still
    open and is not worth another round trip.
    """
    return (
        db.execute(
            select(DevicePresentation.id)
            .where(
                DevicePresentation.device_id == device_id,
                DevicePresentation.status.in_(("queued", "sent")),
                DevicePresentation.available_at <= now,
            )
            .limit(1)
        ).scalar_one_or_none()
        is not None
    )


def showing_card(db: Session, device_id: uuid.UUID) -> bool:
    """Whether something other than a face is open (section 6)."""
    return any(
        row.presentation_type != "face_state" for row in open_presentations(db, device_id)
    )


# --- expiry ------------------------------------------------------------------


def expire_due(db: Session, now: datetime, device_id: uuid.UUID | None = None) -> int:
    """Marks every presentation whose moment has passed (sections 18 and 55).

    Run on every read path, which is what makes the state right whenever
    anybody looks -- the same arrangement PRD 10 uses, and for the same reason:
    a device that comes back after a week must not be handed yesterday's
    "take this now". ``scripts/robot_maintenance.py`` runs it on a schedule as
    well, but unlike PRD 10's worker nothing *depends* on that: there is no
    deadline here whose passing has to cause something to happen.
    """
    statement = (
        sql_update(DevicePresentation)
        .where(
            DevicePresentation.status.in_(ROBOT_PRESENTATION_OPEN_STATUSES),
            DevicePresentation.expires_at.is_not(None),
            DevicePresentation.expires_at <= now,
        )
        .values(status="expired", completed_at=now)
    )
    if device_id is not None:
        statement = statement.where(DevicePresentation.device_id == device_id)
    result = db.execute(statement)
    # ``rowcount`` is on the DBAPI cursor result rather than on the typed
    # ``Result`` protocol, which mypy knows and SQLAlchemy provides.
    expired = int(getattr(result, "rowcount", 0) or 0)
    if expired:
        logger.info("robot.presentation_expired count=%d", expired)
    return expired


# --- queueing ----------------------------------------------------------------


def queue(
    db: Session,
    device: Device,
    request: PresentationRequest,
    now: datetime,
    *,
    mode: modes.RobotMode | None = None,
) -> DevicePresentation | None:
    """Puts one presentation in front of one robot, or explains why not.

    Returns ``None`` when nothing was recorded, which happens in exactly two
    cases and both are deliberate:

      - the robot has not been linked to anybody, so there is nobody the card
        would belong to;
      - a quiet mode suppresses this kind of card (sections 31 and 33).

    Everything else produces a row, including the cases where the robot cannot
    show it. A ``not_supported`` row is a record that Nura had something to say
    and this hardware could not say it, which is what section 20 needs the app
    to be able to tell somebody.
    """
    if device.owner_profile_id is None:
        return None

    expire_due(db, now, device.id)
    resolved = mode or modes.resolve(db, device, now)

    if (
        request.presentation_type in SUPPRESSED_IN_QUIET_MODES
        and not modes.accepts_ordinary_cards(resolved.mode)
    ):
        logger.info(
            "robot.presentation_suppressed type=%s mode=%s",
            request.presentation_type,
            resolved.mode,
        )
        return None

    existing = _existing_for(db, device.id, request)
    if existing is not None:
        return existing

    states = capability_service.capability_map(db, device, now)
    unsupported = _unsupported_reason(states, request.requires)

    available_at = request.available_at or now
    expires_at = request.expires_at
    if expires_at is None:
        window = EXPIRY[request.presentation_type]
        expires_at = None if window is None else available_at + window

    row = DevicePresentation(
        device_id=device.id,
        profile_id=device.owner_profile_id,
        presentation_type=request.presentation_type,
        priority=request.priority,
        layout=request.layout,
        payload=dict(request.payload),
        source=request.source,
        dedupe_key=request.dedupe_key,
        protocol_version=layouts.PROTOCOL_VERSION,
        available_at=available_at,
        expires_at=expires_at,
        status="queued" if unsupported is None else "not_supported",
        failure_code=unsupported,
        completed_at=None if unsupported is None else now,
    )
    try:
        # A SAVEPOINT rather than the caller's transaction: two callers racing
        # on the same key is an ordinary outcome, and losing the race must not
        # roll back whatever the caller was in the middle of.
        with db.begin_nested():
            db.add(row)
            db.flush()
    except IntegrityError:
        # The other one won; use its row, which is section 18's idempotency
        # holding even under concurrency.
        existing = _existing_for(db, device.id, request)
        if existing is None:
            raise
        return existing

    if unsupported is None:
        _preempt(db, row, now)

    # Section 67 and 68: the type, the status and the layout, and not one word
    # of the payload.
    logger.info(
        "robot.presentation_queued type=%s layout=%s status=%s",
        row.presentation_type,
        row.layout,
        row.status,
    )
    return row


def _existing_for(
    db: Session, device_id: uuid.UUID, request: PresentationRequest
) -> DevicePresentation | None:
    """The row this request has already produced, if any (section 57).

    One exception, and it is narrow: a row withdrawn because a *preference*
    changed does not block a rebuild. That card described the same occasion
    rendered a way the person has since reconfigured away from -- a full
    medication preview they made private -- and reconfiguring back has to be
    able to produce it again. A row withdrawn for any other reason still
    blocks: the dose was taken, the message was read, the event resolved, and
    that occasion is over.
    """
    statement = select(DevicePresentation).where(
        DevicePresentation.device_id == device_id,
        DevicePresentation.dedupe_key == request.dedupe_key,
        DevicePresentation.cancel_reason.is_distinct_from("preference_changed"),
    )
    if request.repeatable:
        statement = statement.where(
            DevicePresentation.status.in_(ROBOT_PRESENTATION_OPEN_STATUSES)
        )
    return db.execute(
        statement.order_by(DevicePresentation.created_at.desc()).limit(1)
    ).scalar_one_or_none()


def _unsupported_reason(states: dict[str, str], requires: tuple[str, ...]) -> str | None:
    """Which stable code to record when the hardware cannot do this.

    ``no_display`` rather than ``unsupported_capability`` for the display keys,
    because "this Nura has no screen" is the sentence the app wants and
    "a capability was unsupported" is not.
    """
    missing = [key for key in requires if states.get(key) != "available"]
    if not missing:
        return None
    if set(missing) & {"display", "display_text"}:
        return "no_display"
    return "unsupported_capability"


def _preempt(db: Session, row: DevicePresentation, now: datetime) -> None:
    """Section 17. Safety takes the screen; nothing else does.

    Only cards that are *on the screen* are cancelled -- ``sent``,
    ``acknowledged`` or ``displayed``. A queued card has not had its turn yet
    and keeps it, because an emergency that ends in ninety seconds should not
    also have thrown away a message that nobody has seen.
    """
    if row.priority > ROBOT_SAFETY_PRIORITY_CEILING:
        return
    for other in open_presentations(db, row.device_id):
        if other.id == row.id:
            continue
        if other.priority <= row.priority:
            continue
        if other.status == "queued":
            continue
        cancel(db, other, reason="preempted", now=now)


# --- selection ---------------------------------------------------------------


def next_for_device(
    db: Session, device: Device, now: datetime
) -> DevicePresentation | None:
    """The one thing this robot should be showing next (sections 16, 18).

    ``queued`` and ``sent`` are both candidates. A ``sent`` row that was never
    acknowledged is handed over again with the same id, which is what makes a
    robot that lost power mid-fetch harmless -- section 18's "duplicate
    presentation IDs are idempotent" seen from the other end. A row the device
    has acknowledged is not re-sent: it already has it.
    """
    expire_due(db, now, device.id)
    row = db.execute(
        select(DevicePresentation)
        .where(
            DevicePresentation.device_id == device.id,
            DevicePresentation.status.in_(("queued", "sent")),
            DevicePresentation.available_at <= now,
        )
        .order_by(
            DevicePresentation.priority.asc(),
            DevicePresentation.available_at.asc(),
            DevicePresentation.created_at.asc(),
        )
        .limit(1)
    ).scalar_one_or_none()
    if row is None:
        return None
    if row.status == "queued":
        row.status = "sent"
        row.sent_at = now
        db.flush()
    return row


def envelope_for(
    db: Session,
    device: Device,
    row: DevicePresentation,
    now: datetime,
    *,
    mode: modes.RobotMode | None = None,
) -> dict[str, object]:
    """The presentation as the device receives it (sections 38 and 116)."""
    _, resolved_preferences = preferences.resolved_for(db, device, now)
    resolved_mode = mode or modes.resolve(
        db,
        device,
        now,
        assume_online=True,
        # What is being handed over *is* the card, so the mode the device is
        # told about is the mode it is about to be in. A face is not a card
        # (section 6), which is why this is read off the row rather than
        # assumed -- a robot handed the companion face used to be told it was
        # in ``information`` mode.
        showing_card=row.presentation_type != "face_state",
    )
    return layouts.build_envelope(
        presentation_id=str(row.id),
        presentation_type=row.presentation_type,
        priority=row.priority,
        layout=row.layout,
        payload=row.payload,
        mode=resolved_mode.mode,
        expires_at=row.expires_at,
        settings=preferences.device_settings(resolved_preferences),
        protocol_version=row.protocol_version,
    )


# --- acknowledgement ---------------------------------------------------------

#: What each device-reported state does to a row (section 19). Written as a
#: table so section 123's "valid ack transition / invalid ack rejected" is one
#: thing to read rather than a chain of ifs.
#:
#: The statuses on the left are the ones the row may be in; anything else is a
#: 409. ``queued`` is absent from all of them on purpose: a device cannot
#: report having rendered something it was never sent.
#:
#: **``render_started`` and ``render_completed`` mean different things about
#: the screen, not about the drawing.** A robot that has drawn a card keeps it
#: there until something replaces it, and reports ``render_started``: the row
#: sits in ``displayed``, which is what makes it preemptable (section 17) and
#: what the Nura Device screen shows as "on screen". ``render_completed`` is
#: for a presentation the device is *finished with* -- a notice it showed and
#: dismissed -- and it is the backend that finishes a displayed card, when a
#: later one is drawn over it.
ACK_RULES: dict[str, tuple[tuple[str, ...], str]] = {
    "received": (("sent",), "acknowledged"),
    "render_started": (("sent", "acknowledged"), "displayed"),
    "render_completed": (("sent", "acknowledged", "displayed"), "completed"),
    "failed": (("sent", "acknowledged", "displayed"), "failed"),
    "unsupported": (("sent", "acknowledged"), "not_supported"),
}
assert set(ACK_RULES) == set(ROBOT_ACK_STATES)

#: What a device's ``failed``/``unsupported`` becomes when it does not say.
DEFAULT_FAILURE_CODES: dict[str, str] = {
    "failed": "render_failed",
    "unsupported": "unsupported_layout",
}


def acknowledge(
    db: Session,
    row: DevicePresentation,
    state: str,
    now: datetime,
    *,
    failure_code: str | None = None,
) -> DevicePresentation:
    """Records what the device says happened (sections 14, 19 and 141).

    The **only** writer of ``displayed_at`` anywhere in this codebase, and the
    CHECK constraint on ``device_presentations`` is what makes that structural
    rather than a convention somebody could break later.

    Repeating the same acknowledgement is harmless and changes nothing, which
    matters because a device whose response was lost will send it again. Moving
    backwards -- reporting ``received`` after ``render_completed`` -- is
    refused, because that is not a retry, it is two devices or a bug.
    """
    if state not in ACK_RULES:
        raise InvalidAcknowledgementError("That is not a state Nura recognises.")
    if failure_code is not None and failure_code not in ROBOT_PRESENTATION_FAILURE_CODES:
        raise InvalidAcknowledgementError("That is not a failure Nura recognises.")

    allowed, becomes = ACK_RULES[state]
    if row.ack_state == state and row.status == becomes:
        return row
    if row.status not in allowed:
        raise InvalidAcknowledgementError("That presentation is not in that state.")

    row.ack_state = state
    row.status = becomes
    if state == "received":
        row.acknowledged_at = row.acknowledged_at or now
    if state in {"render_started", "render_completed"}:
        row.acknowledged_at = row.acknowledged_at or now
        row.displayed_at = row.displayed_at or now
    if becomes in {"completed", "failed", "not_supported"}:
        row.completed_at = now
    if becomes in {"failed", "not_supported"}:
        row.failure_code = failure_code or DEFAULT_FAILURE_CODES[state]

    if state in {"render_started", "render_completed"}:
        _supersede_displayed(db, row, now)

    db.flush()
    logger.info("robot.presentation_%s type=%s", row.status, row.presentation_type)
    return row


def _supersede_displayed(db: Session, row: DevicePresentation, now: datetime) -> None:
    """The screen holds one thing (section 18).

    Once the device says it has drawn this one, anything else that was on the
    screen is finished -- it was shown, and it is not there any more. Written
    as ``completed`` rather than ``cancelled``: it did its job. This is also
    what makes section 84's return to the companion face work, because the
    face card stops being open the moment a reminder replaces it.
    """
    for other in db.execute(
        select(DevicePresentation).where(
            DevicePresentation.device_id == row.device_id,
            DevicePresentation.id != row.id,
            DevicePresentation.status == "displayed",
        )
    ).scalars():
        other.status = "completed"
        other.completed_at = now


def cancel(
    db: Session,
    row: DevicePresentation,
    *,
    reason: str,
    now: datetime,
) -> DevicePresentation:
    """Withdraws a presentation, saying why (sections 18, 113 and 114).

    ``cancel_reason`` is a column of its own rather than a value in
    ``failure_code``, the same way PRD 10 keeps an event's status apart from
    how its escalation went: "the dose was taken" and "the renderer broke" are
    different facts, and one column would have blurred them within a release.
    """
    if reason not in ROBOT_PRESENTATION_CANCEL_REASONS:
        raise InvalidAcknowledgementError("That is not a reason Nura recognises.")
    if row.status not in ROBOT_PRESENTATION_OPEN_STATUSES:
        return row
    row.status = "cancelled"
    row.cancel_reason = reason
    row.completed_at = now
    db.flush()
    logger.info(
        "robot.presentation_cancelled type=%s reason=%s", row.presentation_type, reason
    )
    return row


def cancel_for_source(
    db: Session,
    device_id: uuid.UUID,
    *,
    source: str,
    source_id: str | None = None,
    source_id_prefix: str | None = None,
    reason: str,
    now: datetime,
    presentation_type: str | None = None,
) -> int:
    """Cancels everything still open that came from one thing (section 18).

    This is what makes section 56 true: a dose that has been taken, an
    appointment that was cancelled and a safety event that resolved all reach
    back and withdraw the card they produced, so a robot reconnecting an hour
    later is never handed something that has stopped being true.
    """
    rows = db.execute(
        select(DevicePresentation).where(
            DevicePresentation.device_id == device_id,
            DevicePresentation.status.in_(ROBOT_PRESENTATION_OPEN_STATUSES),
            DevicePresentation.source == source,
        )
    ).scalars()
    cancelled = 0
    for row in rows:
        # Split from both ends: a source id may itself contain a colon -- a
        # medication dose's key carries its snooze count that way -- so the
        # middle is whatever is left between the source and the type.
        _, remainder = row.dedupe_key.split(":", 1)
        row_source_id, row_type = remainder.rsplit(":", 1)
        if source_id is not None and row_source_id != source_id:
            continue
        # A prefix, for a source whose occasion carries more than its id -- a
        # medication card names the dose, the snooze count and the privacy
        # level, and a caller withdrawing "that dose's card" should not have to
        # know the other two.
        if source_id_prefix is not None and not row_source_id.startswith(
            source_id_prefix
        ):
            continue
        if presentation_type is not None and row_type != presentation_type:
            continue
        cancel(db, row, reason=reason, now=now)
        cancelled += 1
    return cancelled


def cancel_types(
    db: Session,
    device_id: uuid.UUID,
    *,
    presentation_types: tuple[str, ...],
    reason: str,
    now: datetime,
) -> int:
    """Cancels every open presentation of these kinds.

    Used when a safety event resolves (section 113) and when a preference
    withdraws a whole category of card -- the cases where the thing that
    changed is the kind of card, not one particular source.
    """
    cancelled = 0
    for row in open_presentations(db, device_id):
        if row.presentation_type in presentation_types:
            cancel(db, row, reason=reason, now=now)
            cancelled += 1
    return cancelled
