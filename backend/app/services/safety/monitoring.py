"""Safety Monitoring sessions: started on purpose, ended exactly when asked.

PRD 10, sections 4, 5, 6, 7, 8, 9, 10, 21, 22, 61 and 62.

**Monitoring is never silently enabled** (section 4). A session exists because
somebody pressed Start, and the row records which account did. Section 10
reserves ``caregiver_future`` as a source and this module refuses it: a
caregiver switching monitoring on for somebody without their knowledge is the
surveillance product this whole system is written against, and section 58 says
the caregiver assistant may not do it either.

**The server computes when it ends** (sections 5 and 61). The client sends a
*mode*, never an instant, so "do not invent a hidden monitoring period" is
checkable by reading one function instead of trusting every caller.
``until_bedtime`` needs a bedtime the user set (section 6) and refuses rather
than guessing -- nothing here infers one from behaviour, and an app that got
``bedtime_not_set`` back asks for a time.

**Expiry is lazy *and* durable.** ``active_session`` ends a session whose time
has passed, so a read is always correct even if no worker ever ran; the worker
in ``scripts/safety_maintenance.py`` does the same thing for the profile nobody
opened. That split is section 80's distinction between state correctness and
timely escalation, and it is the pattern PRD 5 already uses for missed doses.

**One session at a time.** A partial unique index enforces it, and starting a
second ends the first with ``superseded`` rather than failing -- somebody who
pressed Start twice meant to be monitored, and an error message is a worse
answer than one session.
"""

import logging
import uuid
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Profile, SafetyMonitoringSession, User
from app.models.enums import (
    DEFAULT_SAFETY_RESPONSE_TIMEOUT_SECONDS,
    SAFETY_MONITORING_ACTIVE_STATUSES,
    SAFETY_MONITORING_DURATION_MODES,
    SAFETY_MONITORING_OPEN_ENDED_MODES,
    SAFETY_MONITORING_SOURCES_ALLOWED,
    SAFETY_RESPONSE_TIMEOUT_SECONDS,
    SECOND_PROMPT_TIMEOUT_SECONDS,
)
from app.services.errors import DomainError, NotFoundError

# The zone helper the medication generator already uses. Imported rather than
# copied: there should be one answer to "is this a real IANA zone", and a
# second copy is a second answer waiting to drift.
from app.services.medications.doses import zone_for
from app.services.safety import audit

logger = logging.getLogger(__name__)

#: Fixed minutes for the two preset durations (section 5).
PRESET_MINUTES = {"30_minutes": 30, "1_hour": 60}

#: Bounds on ``custom`` (section 5). Five minutes is the shortest that is not a
#: mistake; twelve hours is long enough for a night and short enough that
#: nobody is monitored for a week because they chose the wrong units.
MIN_CUSTOM_MINUTES = 5
MAX_CUSTOM_MINUTES = 12 * 60


class MonitoringNotFoundError(NotFoundError):
    code = "monitoring_session_not_found"


class BedtimeNotSetError(DomainError):
    """``until_bedtime`` was chosen and no bedtime exists (section 6).

    409 rather than 400: the request was well-formed and the state is wrong,
    and the app's answer is to ask for a time rather than to report a bug.
    """

    status_code = 409
    code = "bedtime_not_set"


class InvalidDurationError(DomainError):
    code = "invalid_monitoring_duration"


class MonitoringSourceError(DomainError):
    """A source PRD 10 does not accept (section 10)."""

    status_code = 403
    code = "monitoring_source_not_allowed"


def parse_wall_time(value: str) -> time:
    """``HH:MM`` as a time, or a refusal.

    The same format ``daily_checkin_reminder_time`` uses, parsed in one place
    so a malformed setting cannot reach the arithmetic below.
    """
    try:
        hour_text, minute_text = value.split(":")
        return time(hour=int(hour_text), minute=int(minute_text))
    except (ValueError, TypeError) as error:
        raise InvalidDurationError("That bedtime is not a valid time.") from error


def next_occurrence(wall: time, zone: ZoneInfo, now: datetime) -> datetime:
    """The next time it is ``wall`` o'clock in ``zone``, strictly after now.

    Today if it has not happened yet, tomorrow otherwise. Somebody starting
    "until bedtime" at eleven at night, with a bedtime of ten, meant tomorrow
    night -- not a session that ended twenty-three hours ago.
    """
    local_now = now.astimezone(zone)
    candidate = datetime.combine(local_now.date(), wall, tzinfo=zone)
    if candidate <= local_now:
        candidate = datetime.combine(
            local_now.date() + timedelta(days=1), wall, tzinfo=zone
        )
    return candidate.astimezone(now.tzinfo or candidate.tzinfo)


def compute_ends_at(
    *,
    duration_mode: str,
    zone: ZoneInfo,
    now: datetime,
    bedtime: str | None,
    custom_minutes: int | None,
) -> datetime | None:
    """When a session with this mode ends, or None for the open-ended one.

    The only function that answers this. Section 61 forbids silently extending
    monitoring, and section 5 forbids inventing a period; both are properties
    of this function rather than of every caller.
    """
    assert duration_mode in SAFETY_MONITORING_DURATION_MODES, duration_mode

    if duration_mode in SAFETY_MONITORING_OPEN_ENDED_MODES:
        return None
    if duration_mode in PRESET_MINUTES:
        return now + timedelta(minutes=PRESET_MINUTES[duration_mode])
    if duration_mode == "until_bedtime":
        if not bedtime:
            raise BedtimeNotSetError("No bedtime has been set.")
        return next_occurrence(parse_wall_time(bedtime), zone, now)
    # custom
    if custom_minutes is None:
        raise InvalidDurationError("A custom duration needs a number of minutes.")
    if not MIN_CUSTOM_MINUTES <= custom_minutes <= MAX_CUSTOM_MINUTES:
        raise InvalidDurationError(
            f"A custom duration must be between {MIN_CUSTOM_MINUTES} minutes "
            f"and {MAX_CUSTOM_MINUTES // 60} hours."
        )
    return now + timedelta(minutes=custom_minutes)


def _end(
    db: Session,
    session: SafetyMonitoringSession,
    *,
    status: str,
    end_reason: str,
    now: datetime,
    actor_account_id: uuid.UUID | None,
    actor_kind: str,
    event_type: str,
) -> SafetyMonitoringSession:
    """Closes a session and records why. The caller commits."""
    session.status = status
    session.ended_at = now
    session.end_reason = end_reason
    session.updated_at = now
    audit.record(
        db,
        profile_id=session.profile_id,
        actor_account_id=actor_account_id,
        actor_kind=actor_kind,
        event_type=event_type,
        monitoring_session_id=session.id,
        now=now,
        meta=audit.end_meta(end_reason),
    )
    return session


def _current(db: Session, profile_id: uuid.UUID) -> SafetyMonitoringSession | None:
    """The row marked active, whether or not its time has passed."""
    return db.execute(
        select(SafetyMonitoringSession).where(
            SafetyMonitoringSession.profile_id == profile_id,
            SafetyMonitoringSession.status.in_(SAFETY_MONITORING_ACTIVE_STATUSES),
        )
    ).scalar_one_or_none()


def active_session(
    db: Session, profile_id: uuid.UUID, now: datetime
) -> SafetyMonitoringSession | None:
    """The session watching over this person right now, if any.

    Ends an expired one as it finds it, and commits that. Section 61 says
    monitoring ends when ``ends_at`` is reached and the UI updates; doing it on
    read means that is true the moment anybody looks, with or without the
    worker -- the same way PRD 5 replenishes doses on every read rather than
    depending on its maintenance script.
    """
    session = _current(db, profile_id)
    if session is None:
        return None
    if session.ends_at is not None and session.ends_at <= now:
        _end(
            db,
            session,
            status="expired",
            end_reason="duration_reached",
            now=now,
            actor_account_id=None,
            actor_kind="system",
            event_type="monitoring_expired",
        )
        db.commit()
        logger.info("safety.monitoring.expired")
        return None
    return session


def monitoring_is_active(db: Session, profile_id: uuid.UUID, now: datetime) -> bool:
    """Section 22's gate, as one call. A passive trigger asks this first."""
    return active_session(db, profile_id, now) is not None


def peek_session(
    db: Session, profile_id: uuid.UUID, now: datetime
) -> SafetyMonitoringSession | None:
    """The active session, without ending an expired one.

    Added by PRD 11, which needs to know whether monitoring is on in order to
    draw a line on a robot's screen. ``active_session`` is the right call for
    anything that acts on monitoring, because it ends a session whose time has
    passed and commits that. Drawing a screen is not acting on monitoring, and
    a display request that expired somebody's monitoring session as a side
    effect would make the display path load-bearing for safety -- which is the
    opposite of what PRD 11 section 100 asks for.

    So this reads, and reports ``None`` for a session whose time has passed
    without writing anything. The next caller that genuinely acts on
    monitoring -- the app, the assistant, the maintenance worker -- ends it.
    """
    session = _current(db, profile_id)
    if session is None:
        return None
    if session.ends_at is not None and session.ends_at <= now:
        return None
    return session


def get_session(
    db: Session, profile_id: uuid.UUID, session_id: uuid.UUID
) -> SafetyMonitoringSession:
    session = db.execute(
        select(SafetyMonitoringSession).where(
            SafetyMonitoringSession.id == session_id,
            SafetyMonitoringSession.profile_id == profile_id,
        )
    ).scalar_one_or_none()
    if session is None:
        raise MonitoringNotFoundError("Not found.")
    return session


def start(
    db: Session,
    profile: Profile,
    actor: User,
    *,
    duration_mode: str,
    timezone_name: str,
    now: datetime,
    response_timeout_seconds: int = DEFAULT_SAFETY_RESPONSE_TIMEOUT_SECONDS,
    second_prompt_enabled: bool = False,
    custom_minutes: int | None = None,
    source: str = "mobile_app",
) -> SafetyMonitoringSession:
    """Starts watching over somebody, for exactly as long as they asked.

    ``source`` is checked against ``SAFETY_MONITORING_SOURCES_ALLOWED`` rather
    than trusted, which is the whole of section 10: the vocabulary has four
    values so a later PRD need not reopen it, and exactly one of them is
    accepted today.

    A session already running is ended as ``superseded`` and a new one takes
    its place. Section 62's confirmation applies to *stopping* while an event
    is live, and that check lives in ``stop``; starting again is not a way to
    cancel an emergency.
    """
    if source not in SAFETY_MONITORING_SOURCES_ALLOWED:
        logger.info("safety.monitoring.start refused: source not allowed")
        raise MonitoringSourceError("Monitoring cannot be started that way.")
    if response_timeout_seconds not in SAFETY_RESPONSE_TIMEOUT_SECONDS:
        raise InvalidDurationError("That response timeout is not one of the options.")

    zone = zone_for(timezone_name)
    bedtime = actor.settings.safety_bedtime if actor.settings else None
    ends_at = compute_ends_at(
        duration_mode=duration_mode,
        zone=zone,
        now=now,
        bedtime=bedtime,
        custom_minutes=custom_minutes,
    )

    existing = _current(db, profile.id)
    if existing is not None:
        _end(
            db,
            existing,
            status="ended",
            end_reason="superseded",
            now=now,
            actor_account_id=actor.id,
            actor_kind="primary_user",
            event_type="monitoring_stopped",
        )
        db.flush()

    session = SafetyMonitoringSession(
        profile_id=profile.id,
        started_by_account_id=actor.id,
        status="active",
        started_at=now,
        ends_at=ends_at,
        duration_mode=duration_mode,
        timezone=timezone_name,
        response_timeout_seconds=response_timeout_seconds,
        second_prompt_enabled=second_prompt_enabled,
        second_prompt_timeout_seconds=SECOND_PROMPT_TIMEOUT_SECONDS,
        source=source,
    )
    db.add(session)
    db.flush()
    audit.record(
        db,
        profile_id=profile.id,
        actor_account_id=actor.id,
        actor_kind="primary_user",
        event_type="monitoring_started",
        monitoring_session_id=session.id,
        now=now,
        meta=audit.monitoring_meta(duration_mode, response_timeout_seconds),
    )
    db.commit()
    db.refresh(session)
    # Section 122: generic, with no profile and no time in it.
    logger.info("safety.monitoring.started")
    return session


def stop(
    db: Session,
    session: SafetyMonitoringSession,
    actor: User,
    *,
    now: datetime,
) -> SafetyMonitoringSession:
    """Stops monitoring (section 62).

    Stopping does not touch a live safety event. Section 62 requires explicit
    confirmation when one is in flight and the route asks for it; what it must
    not do is cancel the event as a side effect, because somebody turning
    monitoring off has not said they are all right.
    """
    if session.status not in SAFETY_MONITORING_ACTIVE_STATUSES:
        return session
    _end(
        db,
        session,
        status="ended",
        end_reason="stopped_by_user",
        now=now,
        actor_account_id=actor.id,
        actor_kind="primary_user",
        event_type="monitoring_stopped",
    )
    db.commit()
    db.refresh(session)
    logger.info("safety.monitoring.stopped")
    return session


def expire_due(db: Session, now: datetime) -> int:
    """Ends every active session whose time has passed. For the worker.

    Idempotent: a second run finds nothing, because the first one moved the
    status. Returns how many were ended, for the script's summary line.
    """
    due = list(
        db.execute(
            select(SafetyMonitoringSession).where(
                SafetyMonitoringSession.status.in_(SAFETY_MONITORING_ACTIVE_STATUSES),
                SafetyMonitoringSession.ends_at.is_not(None),
                SafetyMonitoringSession.ends_at <= now,
            )
        )
        .scalars()
        .all()
    )
    for session in due:
        _end(
            db,
            session,
            status="expired",
            end_reason="duration_reached",
            now=now,
            actor_account_id=None,
            actor_kind="system",
            event_type="monitoring_expired",
        )
    return len(due)


def list_sessions(
    db: Session, profile_id: uuid.UUID, *, limit: int = 20
) -> list[SafetyMonitoringSession]:
    """Recent sessions, newest first. For the history screen's context."""
    return list(
        db.execute(
            select(SafetyMonitoringSession)
            .where(SafetyMonitoringSession.profile_id == profile_id)
            .order_by(SafetyMonitoringSession.started_at.desc())
            .limit(limit)
        )
        .scalars()
        .all()
    )


def local_today(session: SafetyMonitoringSession, now: datetime) -> date:
    """The session's own local date. Used only for display."""
    return now.astimezone(ZoneInfo(session.timezone)).date()
