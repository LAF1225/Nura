"""Safety monitoring, SOS, safety history and caregiver safety alerts.

PRD 10, sections 12, 19, 21, 22, 42, 45, 50, 62, 65, 76, 78, 85, 103 and 104.

**Two authorization paths, the same two PRD 9 established.**

``OwnedProfile``   -- the primary user. Walks ``account_profile_roles``, so a
                      caregiver is refused outright on every monitoring and
                      SOS route. Section 10 says caregivers must not activate
                      monitoring and section 104 says not to add ``caregiver``
                      to that table; both are satisfied by the dependency
                      rather than by a check inside a handler.
``CareScopeDep``   -- owner or active caregiver, carrying granted categories.
                      Used by the two alert routes, which then require
                      ``safety_alerts`` and answer 404 without it.

**Everything the user does to an event is owner-only**, including reading one.
A caregiver's view of safety is the alert list and nothing else: section 50
says they may see permitted safety events only, and the alert carries exactly
the fields section 85 allows.

**A missing permission answers 404**, not 403, for the reason the whole
codebase answers 404: a 403 confirms that something exists.

**Transitions take a row lock before they decide anything** (section 78). That
happens in ``services.safety.checks``; these handlers do not re-implement it,
and none of them reads a status and then writes one.
"""

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import (
    CareScopeDep,
    CurrentUser,
    DbSession,
    Now,
    OwnedProfile,
    http_error,
)
from app.models import SafetyAlert, SafetyEscalationAttempt, SafetyEvent
from app.models.enums import SAFETY_CAPABILITY_KEYS
from app.schemas.safety import (
    CapabilitiesRead,
    CapabilityRead,
    EscalationAttemptRead,
    FalseAlarmUpdate,
    MonitoringSessionRead,
    MonitoringStart,
    SafetyAlertListRead,
    SafetyAlertRead,
    SafetyEventDetailRead,
    SafetyEventListRead,
    SafetyEventRead,
    SafetyResponse,
    SafetyStatusRead,
    SosCreate,
)
from app.services.caregivers.permissions import CareScope
from app.services.errors import DomainError
from app.services.safety import alerts as alert_service
from app.services.safety import capabilities as capability_service
from app.services.safety import checks as check_service
from app.services.safety import escalation as escalation_service
from app.services.safety import events as event_service
from app.services.safety import monitoring as monitoring_service
from app.services.safety import status as status_service
from app.services.safety import wording

logger = logging.getLogger(__name__)

router = APIRouter(tags=["safety"])


# --- serialisers -------------------------------------------------------------


def _require_safety(scope: CareScope) -> CareScope:
    """``safety_alerts``, or 404 (sections 31 and 104).

    Re-checked on every request rather than trusted from when the alert was
    created, which is section 86: a caregiver whose permission was withdrawn
    this morning does not see last night's alerts.
    """
    try:
        scope.require("safety_alerts")
    except DomainError as error:
        raise http_error(error) from error
    return scope


def _capability_rows() -> list[CapabilityRead]:
    """Every capability with its state and both labels (section 106)."""
    current = capability_service.capability_map()
    return [
        CapabilityRead(
            key=key,  # type: ignore[arg-type]
            state=current[key],  # type: ignore[arg-type]
            label=wording.CAPABILITY_LABELS[key],
            state_label=wording.CAPABILITY_STATE_LABELS[current[key]],
        )
        for key in SAFETY_CAPABILITY_KEYS
    ]


def _attempt_read(attempt: SafetyEscalationAttempt) -> EscalationAttemptRead:
    return EscalationAttemptRead(
        id=attempt.id,
        recipient_label=attempt.recipient_label,
        is_caregiver=attempt.caregiver_relationship_id is not None,
        priority=attempt.priority,
        channel=attempt.channel,  # type: ignore[arg-type]
        status=attempt.status,  # type: ignore[arg-type]
        failure_code=attempt.failure_code,
        attempted_at=attempt.attempted_at,
        confirmed_at=attempt.confirmed_at,
        line=wording.escalation_line(
            label=attempt.recipient_label,
            channel=attempt.channel,
            status=attempt.status,
        ),
    )


def _event_read(event: SafetyEvent) -> SafetyEventRead:
    return SafetyEventRead(
        id=event.id,
        event_type=event.event_type,  # type: ignore[arg-type]
        event_label=wording.EVENT_TYPE_LABELS[event.event_type],
        triggered_at=event.triggered_at,
        status=event.status,  # type: ignore[arg-type]
        resolution=event.resolution,  # type: ignore[arg-type]
        resolution_label=(
            wording.RESOLUTION_LABELS[event.resolution] if event.resolution else None
        ),
        escalation_outcome=event.escalation_outcome,  # type: ignore[arg-type]
        escalation_outcome_label=(
            wording.OUTCOME_LABELS[event.escalation_outcome]
            if event.escalation_outcome
            else None
        ),
        user_response=event.user_response,  # type: ignore[arg-type]
        false_positive=event.false_positive,
    )


def _silence_seconds(event: SafetyEvent) -> int | None:
    """How long the wait was, when nobody answered it."""
    if event.user_response is not None:
        return None
    if event.response_deadline_at is None or event.check_started_at is None:
        return None
    return int((event.response_deadline_at - event.check_started_at).total_seconds())


def _event_detail(db: DbSession, event: SafetyEvent) -> SafetyEventDetailRead:
    """One event in full (section 51), with its escalation list."""
    attempts = escalation_service.attempts_for(db, event.id)
    silence = _silence_seconds(event)
    base = _event_read(event)
    return SafetyEventDetailRead(
        **base.model_dump(),
        description=wording.EVENT_TYPE_DESCRIPTIONS[event.event_type],
        no_response_seconds=silence,
        no_response_label=(
            wording.no_response_sentence(silence) if silence is not None else None
        ),
        response_deadline_at=event.response_deadline_at,
        second_prompt_deadline_at=event.second_prompt_deadline_at,
        escalation_started_at=event.escalation_started_at,
        resolved_at=event.resolved_at,
        false_positive_reason=event.false_positive_reason,  # type: ignore[arg-type]
        attempts=[_attempt_read(attempt) for attempt in attempts],
        alert_count=len(event.alerts),
    )


def _alert_read(view: alert_service.AlertView) -> SafetyAlertRead:
    return SafetyAlertRead(
        id=view.id,
        safety_event_id=view.safety_event_id,
        event_type=view.event_type,  # type: ignore[arg-type]
        event_label=wording.EVENT_TYPE_LABELS[view.event_type],
        triggered_at=view.triggered_at,
        created_at=view.created_at,
        read_at=view.read_at,
        acknowledged_at=view.acknowledged_at,
        event_status=view.event_status,  # type: ignore[arg-type]
        event_resolution=view.event_resolution,  # type: ignore[arg-type]
        escalation_outcome=view.escalation_outcome,  # type: ignore[arg-type]
        sentence=wording.caregiver_alert_sentence(
            event_type=view.event_type,
            when=view.triggered_at,
            zone=view.zone,
            no_response_seconds=view.no_response_seconds,
        ),
    )


# --- monitoring --------------------------------------------------------------


@router.get("/profiles/{profile_id}/safety/status", response_model=SafetyStatusRead)
def read_safety_status(
    profile: OwnedProfile, db: DbSession, now: Now
) -> SafetyStatusRead:
    """Where safety stands for this person right now (sections 59 and 60).

    Reading this advances any deadline that has passed, which is section 80's
    state-correctness half: whoever looks sees the true state whether or not
    the maintenance worker has run. The worker is what makes escalation
    *timely* for somebody who is not looking, and that is a separate claim,
    tested separately.
    """
    current = status_service.current(db, profile.id, now)
    zone = current.monitoring.timezone if current.monitoring else "UTC"
    return SafetyStatusRead(
        monitoring=(
            MonitoringSessionRead.model_validate(current.monitoring)
            if current.monitoring
            else None
        ),
        monitoring_sentence=wording.monitoring_sentence(
            active=current.monitoring is not None,
            ends_at=current.monitoring.ends_at if current.monitoring else None,
            zone=zone,
        ),
        active_event=(
            _event_detail(db, current.active_event) if current.active_event else None
        ),
        emergency_mode=current.emergency_mode,
        capabilities=_capability_rows(),
        emergency_contact_count=current.emergency_contact_count,
        no_contacts_warning=(
            None if current.has_emergency_contacts else wording.NO_EMERGENCY_CONTACTS
        ),
        no_providers_warning=(
            None if current.external_delivery_available else wording.NO_DELIVERY_PROVIDERS
        ),
        detection_notice=(
            wording.MONITORING_WITHOUT_DETECTION
            if current.monitoring is not None
            and current.capabilities["robot_detection"] != "available"
            else None
        ),
        check_prompt=wording.check_in_prompt(profile.preferred_name),
    )


@router.get("/profiles/{profile_id}/safety/capabilities", response_model=CapabilitiesRead)
def read_safety_capabilities(profile: OwnedProfile) -> CapabilitiesRead:
    """What this build can actually do (sections 64, 65 and 106).

    Profile-scoped although nothing in the answer depends on the profile:
    capabilities are a deployment fact today, and a future robot makes them a
    per-person fact. Putting the id in the path now means that change is a
    change to one function rather than to every caller.
    """
    available = capability_service.external_delivery_available()
    return CapabilitiesRead(
        capabilities=_capability_rows(),
        external_delivery_available=available,
        warning=None if available else wording.NO_DELIVERY_PROVIDERS,
    )


@router.post(
    "/profiles/{profile_id}/safety/monitoring/start",
    response_model=MonitoringSessionRead,
    status_code=status.HTTP_201_CREATED,
)
def start_monitoring(
    payload: MonitoringStart,
    profile: OwnedProfile,
    user: CurrentUser,
    db: DbSession,
    now: Now,
) -> MonitoringSessionRead:
    """Starts Safety Monitoring (sections 4, 5, 6, 7 and 8).

    Owner-only, which is section 10: a caregiver cannot reach this route at
    all, because ``OwnedProfile`` resolves through ``account_profile_roles``
    and a caregiver has no row there.

    ``until_bedtime`` with no bedtime set answers 409 ``bedtime_not_set``
    rather than guessing one (section 6). The app's response is to ask for a
    time.
    """
    try:
        session = monitoring_service.start(
            db,
            profile,
            user,
            duration_mode=payload.duration_mode,
            timezone_name=payload.timezone,
            now=now,
            response_timeout_seconds=payload.response_timeout_seconds,
            second_prompt_enabled=payload.second_prompt_enabled,
            custom_minutes=payload.custom_minutes,
        )
    except DomainError as error:
        raise http_error(error) from error
    return MonitoringSessionRead.model_validate(session)


@router.post(
    "/profiles/{profile_id}/safety/monitoring/stop",
    response_model=SafetyStatusRead,
)
def stop_monitoring(
    profile: OwnedProfile,
    user: CurrentUser,
    db: DbSession,
    now: Now,
    confirm_active_event: Annotated[bool, Query()] = False,
) -> SafetyStatusRead:
    """Stops Safety Monitoring (section 62).

    If no safety event is live, this stops immediately. If one is, the request
    needs ``confirm_active_event=true`` -- section 62 asks for explicit
    confirmation, and a query parameter the app only sends after showing a
    dialog is how that confirmation reaches the server.

    Stopping does **not** cancel a live event. Somebody turning monitoring off
    has not said they are all right, and section 45 gives cancelling an
    emergency its own route with its own confirmation.
    """
    live = event_service.active_event(db, profile.id)
    if live is not None and not confirm_active_event:
        raise http_error(
            check_service.ActiveEventError(
                "There is a safety event in progress. Confirm before stopping."
            )
        )
    session = monitoring_service.active_session(db, profile.id, now)
    if session is not None:
        monitoring_service.stop(db, session, user, now=now)
    return read_safety_status(profile, db, now)


# --- events ------------------------------------------------------------------


@router.get("/profiles/{profile_id}/safety/events", response_model=SafetyEventListRead)
def list_safety_events(
    profile: OwnedProfile,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=event_service.MAX_EVENTS)] = 20,
) -> SafetyEventListRead:
    """Safety history, newest first (section 49)."""
    return SafetyEventListRead(
        events=[
            _event_read(event)
            for event in event_service.list_events(db, profile.id, limit=limit)
        ]
    )


@router.get(
    "/profiles/{profile_id}/safety/events/{event_id}",
    response_model=SafetyEventDetailRead,
)
def read_safety_event(
    event_id: uuid.UUID, profile: OwnedProfile, db: DbSession
) -> SafetyEventDetailRead:
    """One event in full, with every attempt that was made (section 51)."""
    try:
        event = event_service.get_event(db, profile.id, event_id)
    except DomainError as error:
        raise http_error(error) from error
    return _event_detail(db, event)


@router.post(
    "/profiles/{profile_id}/safety/sos",
    response_model=SafetyEventDetailRead,
    status_code=status.HTTP_201_CREATED,
)
def raise_sos(
    payload: SosCreate,
    profile: OwnedProfile,
    user: CurrentUser,
    db: DbSession,
    now: Now,
) -> SafetyEventDetailRead:
    """An emergency request (sections 12, 14 and 21).

    Works whether or not monitoring is on -- section 21 -- and skips the
    countdown entirely: escalation begins inside this request, so the response
    already carries the attempt list the app shows (section 26).

    ``event_type: call_for_help`` is section 14's "Nura, emergency" contract.
    The backend treats it identically; what differs is only how the app came
    to send it, and recording that difference is what makes the eventual voice
    path answerable afterwards.

    Press-and-hold or tap-then-confirm (section 13) is the app's job. The
    server cannot tell a deliberate press from an accidental one, which is
    exactly why cancelling (section 45) exists.
    """
    try:
        event = event_service.create(
            db,
            profile,
            event_type=payload.event_type,
            trigger_source="mobile_manual",
            now=now,
            actor_account_id=user.id,
            actor_kind="primary_user",
            client_event_id=payload.client_event_id,
        )
        db.commit()
    except DomainError as error:
        db.rollback()
        raise http_error(error) from error
    db.refresh(event)
    return _event_detail(db, event)


@router.post(
    "/profiles/{profile_id}/safety/events/{event_id}/respond",
    response_model=SafetyEventDetailRead,
)
def respond_to_safety_event(
    event_id: uuid.UUID,
    payload: SafetyResponse,
    profile: OwnedProfile,
    user: CurrentUser,
    db: DbSession,
    now: Now,
) -> SafetyEventDetailRead:
    """ "I'm okay" or "I need help" (sections 24, 25, 26 and 126).

    The same route the future robot's voice check-in will call (section 24),
    which is why the response vocabulary is two words rather than a sentence:
    whatever recognises the speech maps onto the same two codes.

    Answering late is allowed and is not the same as answering in time. The
    event records which it was, already-created alerts stay, and anything not
    yet sent is skipped (section 126).
    """
    try:
        event = event_service.get_event(db, profile.id, event_id)
        event = check_service.respond(
            db, event, response=payload.response, actor=user, now=now
        )
    except DomainError as error:
        raise http_error(error) from error
    return _event_detail(db, event)


@router.post(
    "/profiles/{profile_id}/safety/events/{event_id}/cancel",
    response_model=SafetyEventDetailRead,
)
def cancel_safety_event(
    event_id: uuid.UUID,
    profile: OwnedProfile,
    user: CurrentUser,
    db: DbSession,
    now: Now,
) -> SafetyEventDetailRead:
    """Stops an emergency request (section 45).

    Stops what has not gone out. Alerts that already exist are left exactly as
    they are -- section 45 says already-delivered alerts cannot be recalled,
    and quietly deleting the ones a caregiver can already see would be worse
    than not offering this at all.
    """
    try:
        event = event_service.get_event(db, profile.id, event_id)
        event = check_service.cancel(db, event, user, now=now)
    except DomainError as error:
        raise http_error(error) from error
    return _event_detail(db, event)


@router.post(
    "/profiles/{profile_id}/safety/events/{event_id}/false-alarm",
    response_model=SafetyEventDetailRead,
)
def mark_false_alarm(
    event_id: uuid.UUID,
    payload: FalseAlarmUpdate,
    profile: OwnedProfile,
    user: CurrentUser,
    db: DbSession,
    now: Now,
) -> SafetyEventDetailRead:
    """Labels a finished event as a false alarm, or not (sections 47 and 48).

    "No / Not sure" is stored rather than ignored, so "they said it was real"
    and "nobody asked" stay different facts. Section 48: nothing trains on
    these columns, and nothing may without a governance decision first.
    """
    try:
        event = event_service.get_event(db, profile.id, event_id)
        event = check_service.mark_false_alarm(
            db,
            event,
            user,
            false_positive=payload.false_positive,
            reason=payload.reason,
            now=now,
        )
    except DomainError as error:
        raise http_error(error) from error
    return _event_detail(db, event)


# --- caregiver alerts --------------------------------------------------------


@router.get(
    "/profiles/{profile_id}/care/safety-alerts", response_model=SafetyAlertListRead
)
def list_safety_alerts(
    scope: CareScopeDep, db: DbSession, now: Now
) -> SafetyAlertListRead:
    """A caregiver's safety alerts about this person (sections 50, 83 and 85).

    Requires ``safety_alerts`` on an active relationship, re-checked here
    rather than inherited from when the alert was created (section 86). An
    owner reading their own profile also passes, which is deliberate: it is
    their safety history, and they can already see all of it.

    What comes back is the alert, not the event: a type, a time, an outcome
    and the sentence. No health data of any kind (section 85).
    """
    _require_safety(scope)
    if scope.relationship is None:
        # The owner's own view of what their caregivers were sent. No alert
        # belongs to them, so the list is empty rather than everybody's.
        return SafetyAlertListRead(alerts=[], unread_count=0)
    views = alert_service.list_for_caregiver(db, scope)
    # Opening the list is the caregiver seeing the alert, so this is where
    # ``read_at`` is written -- the only thing in the system that can turn
    # section 37's "a record exists" into "somebody looked". The badge on the
    # care home reads the count without marking anything.
    alert_service.mark_listed_read(db, scope, [view.id for view in views], now=now)
    return SafetyAlertListRead(
        alerts=[_alert_read(view) for view in views],
        unread_count=alert_service.unread_count(db, scope),
    )


@router.post(
    "/profiles/{profile_id}/care/safety-alerts/{alert_id}/acknowledge",
    response_model=SafetyAlertRead,
)
def acknowledge_safety_alert(
    alert_id: uuid.UUID, scope: CareScopeDep, db: DbSession, now: Now
) -> SafetyAlertRead:
    """ "I'm checking on them" (sections 84 and 125).

    Records one timestamp. It does not resolve the event, it does not tell the
    primary user anybody is safe, and it is not proof the caregiver went
    anywhere -- it records that they said they would.
    """
    _require_safety(scope)
    if scope.relationship is None:
        raise http_error(alert_service.AlertNotFoundError("Not found."))
    try:
        alert: SafetyAlert = alert_service.get_for_caregiver(db, scope, alert_id)
        alert = alert_service.acknowledge(db, alert, scope, now=now)
    except DomainError as error:
        raise http_error(error) from error
    views = [
        view
        for view in alert_service.list_for_caregiver(db, scope)
        if view.id == alert.id
    ]
    return _alert_read(views[0])
