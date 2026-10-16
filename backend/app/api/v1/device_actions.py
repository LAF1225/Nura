"""What a robot is allowed to do to a person's data (PRD 5, sections 45-47;
PRD 10, sections 19, 20 and 105; PRD 11, sections 19, 59, 60, 61 and 69).

Five things: confirm that a dose was taken, for the future "I took it"
behaviour; report a possible distress event, for the future detectors; report
what the hardware can actually do; collect the next thing to show; and say what
happened when it tried. They are here rather than beside the app's own routes
because the two authenticate completely differently, and a reader who is
checking who can do what should not have to notice which dependency a route
used. Everything under ``/device-actions`` is authenticated by a **device
token** and nothing else.

The rules, all of which are checked on every request (PRD 5, section 46):

  - The caller presents a device token issued at claim. A user's access token
    does not work here, and the robot never holds one -- PRD 2 put the user's
    credentials nowhere near the hardware and PRD 5 keeps it that way.
  - The device must be claimed and must be linked to a profile. A robot that
    has not been set up for anybody cannot act on anybody.
  - The dose must belong to *that* profile. It is fetched by profile and id
    together, so there is no path that loads a dose and authorizes it after.
  - Anything else is a 404. A robot with a valid token learns nothing about
    which dose ids exist on other accounts.
  - The action is idempotent, and it never overrides what the person recorded
    themselves (PRD 5, sections 48 and 49).

**None of this needs the hardware.** Every contract here is real,
authenticated and tested with simulated device requests, which is what PRD 10
section 115 and PRD 11 section 63 ask for; what does not exist yet is a robot
that speaks, senses or draws anything. No claim is made here that voice
confirmation has been tried on a physical device (PRD 5, sections 44 and 73),
that any detector has produced a real reading (PRD 10, sections 53 and 117), or
that any screen has ever rendered a presentation (PRD 11, sections 135 and
141). **No physical acknowledgement has ever been received**, which is why no
row in ``device_presentations`` has ever been marked displayed outside a test.
"""

import logging
import uuid

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel

from app.api.deps import CurrentDevice, DbSession, Now, http_error
from app.models import Profile
from app.schemas.medication import DoseStatus
from app.schemas.robot import (
    DeviceCapabilityReport,
    DeviceCapabilityReportRead,
    PresentationAcknowledgement,
    PresentationAckRead,
    PresentationEnvelopeRead,
)
from app.schemas.safety import DeviceSafetyEventCreate, DeviceSafetyEventRead
from app.services.errors import DomainError
from app.services.medications import doses as dose_service
from app.services.robot import capabilities as robot_capabilities
from app.services.robot import layouts
from app.services.robot import presenter as robot_presenter
from app.services.robot import queue as robot_queue
from app.services.safety import events as safety_events

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/device-actions", tags=["device actions"])

#: One answer for "no such dose", "not your profile" and "you are not set up
#: for anybody". A robot on somebody's shelf should not be able to tell those
#: apart by trying ids.
NOT_FOUND = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND,
    detail={"code": "dose_not_found", "message": "Not found."},
)


class DeviceDoseActionRead(BaseModel):
    """What the robot is told back.

    Deliberately thin: an id, a status and whether anything changed. No
    medication name, no dose, no supply count and no history -- the robot has
    no use for them, and medication data has no business sitting in a device's
    memory or logs (PRD 5, section 58).
    """

    dose_id: uuid.UUID
    status: DoseStatus
    #: False when the person had already recorded this dose themselves. Not an
    #: error: the robot agreeing with what is already true is the expected
    #: outcome of somebody saying "I took it" after tapping Taken.
    applied: bool


@router.post("/medication-doses/{dose_id}/taken", response_model=DeviceDoseActionRead)
def device_mark_taken(
    dose_id: uuid.UUID, device: CurrentDevice, db: DbSession, now: Now
) -> DeviceDoseActionRead:
    """A linked robot confirms a dose was taken (PRD 5, section 45).

    Recorded with ``source = robot_voice`` so history can always say where a
    confirmation came from. If the person already marked the dose taken or
    skipped in the app, their record stands and this changes nothing --
    a robot that mishears must never be able to rewrite what somebody said
    about their own medication (PRD 5, section 49).
    """
    if device.owner_profile_id is None:
        # Claimed, but not set up for a person yet. Nothing to act on.
        logger.info("device_action.medication_taken refused: device has no profile")
        raise NOT_FOUND

    try:
        dose = dose_service.get_dose(db, device.owner_profile_id, dose_id)
    except DomainError:
        logger.info("device_action.medication_taken refused: dose not found")
        raise NOT_FOUND from None

    try:
        result = dose_service.record_taken(db, dose, now, source="robot_voice")
    except DomainError as error:
        raise http_error(error) from error

    # The medication is not named, here or anywhere else in this file.
    logger.info("device_action.medication_taken success applied=%s", result.applied)
    return DeviceDoseActionRead(
        dose_id=result.dose.id,
        status=result.dose.status,  # type: ignore[arg-type]
        applied=result.applied,
    )


#: The same answer for "no such profile", "this device is not set up for
#: anybody" and "that is not your profile". A robot on somebody's shelf should
#: learn nothing by trying.
SAFETY_NOT_FOUND = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND,
    detail={"code": "not_found", "message": "Not found."},
)


@router.post(
    "/safety-events",
    response_model=DeviceSafetyEventRead,
    status_code=status.HTTP_201_CREATED,
)
def device_safety_event(
    payload: DeviceSafetyEventCreate, device: CurrentDevice, db: DbSession, now: Now
) -> DeviceSafetyEventRead:
    """A linked robot reports something it observed (PRD 10, sections 19, 20).

    The rules, all checked on every request (section 20):

      - The caller presents a device token issued at claim. A user's access
        token does not work here, and the robot never holds one.
      - The device must be claimed and linked to a profile. A robot that has
        not been set up for anybody cannot report anything about anybody.
      - **The profile comes from the device, never from the body.** There is no
        profile field on ``DeviceSafetyEventCreate`` to put one in, which is
        section 105 enforced by the schema rather than by a check somebody
        could remove.
      - Safety Monitoring must be active. A ``possible_*`` event arriving while
        monitoring is off is refused with ``monitoring_not_active`` (section
        22) -- Nura does not watch unless it was asked to.
      - ``idempotency_key`` is required, so a retry after a lost response does
        not become a second emergency (section 20).

    ``confidence`` is accepted and discarded. Section 54 calls it engineering
    metadata and not a diagnosis probability; there is no column for it,
    because a column is a thing a screen eventually reads.

    **Nothing here has ever run on hardware.** There is no detector in this
    project (``services.safety.detectors.DETECTORS`` is empty) and no sensor
    has produced a reading. What is tested is this contract, driven by
    authenticated simulated device requests, which is exactly the scope PRD 10
    section 115 sets.
    """
    if device.owner_profile_id is None:
        logger.info("device_action.safety_event refused: device has no profile")
        raise SAFETY_NOT_FOUND

    profile = db.get(Profile, device.owner_profile_id)
    if profile is None:
        logger.info("device_action.safety_event refused: profile is gone")
        raise SAFETY_NOT_FOUND

    before = safety_events.active_event(db, profile.id)
    try:
        event = safety_events.create(
            db,
            profile,
            event_type=payload.event_type,
            trigger_source=payload.trigger_source,
            now=now,
            actor_account_id=None,
            actor_kind="device",
            device_id=device.id,
            idempotency_key=payload.idempotency_key,
        )
        db.commit()
    except DomainError as error:
        db.rollback()
        raise http_error(error) from error

    db.refresh(event)
    created = before is None or before.id != event.id
    # Neither the event type nor the profile is logged. Section 121 keeps
    # safety logs to operational data, and "a device reported something" is it.
    logger.info("device_action.safety_event created=%s", created)
    return DeviceSafetyEventRead(
        event_id=event.id,
        status=event.status,  # type: ignore[arg-type]
        created=created,
    )


# --- the robot's display (PRD 11, sections 19, 59, 60, 61 and 69) -----------
#
# The same three rules as everything above, and the third is the one PRD 11
# section 69 restates: the caller presents a device token, the device must be
# claimed and linked to a profile, and **the profile comes from the device
# record and never from the body**. There is no profile field on any of the
# three models below, which is that rule enforced by the schema rather than by
# a check somebody could remove.
#
# A fourth rule is PRD 11's own: a device may only ever report on its *own*
# presentations. ``robot_queue.get`` takes the device and the presentation id
# together, so a robot trying ids learns nothing -- the answer is the same 404
# for "no such presentation" and "that one is somebody else's".

#: One answer for every way a presentation lookup can fail.
PRESENTATION_NOT_FOUND = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND,
    detail={"code": "presentation_not_found", "message": "Not found."},
)


@router.post("/capabilities", response_model=DeviceCapabilityReportRead)
def device_report_capabilities(
    payload: DeviceCapabilityReport, device: CurrentDevice, db: DbSession, now: Now
) -> DeviceCapabilityReportRead:
    """A robot says what it can actually do (PRD 11, sections 11, 61 and 92).

    This endpoint is the only way ``not_verified`` ever enters the database,
    and that is deliberate (section 12): a compiled display driver is not a
    working screen, the backend cannot tell the difference, and so the backend
    does not guess. A robot whose startup self-test found a panel but has never
    had a frame checked by a person reports ``not_verified`` and the app says
    "Not tested yet".

    A partial report is normal and erases nothing it leaves out. A key or state
    this build does not define is a 422 rather than a silent drop, because a
    firmware inventing a capability is a protocol mismatch its author should
    see.
    """
    try:
        views = robot_capabilities.report(
            db,
            device,
            # The Literal-keyed mapping is widened to str/str for the service,
            # which validates against the tuples the database constrains.
            {str(key): str(state) for key, state in payload.capabilities.items()},
            now,
            source=payload.source,
            firmware_version=payload.firmware_version,
        )
        db.commit()
    except DomainError as error:
        db.rollback()
        raise http_error(error) from error

    # Only the count is logged. The states are not sensitive, but there is no
    # reason for a device id and a hardware inventory to sit in one log line.
    logger.info("device_action.capabilities accepted=%d", len(payload.capabilities))
    return DeviceCapabilityReportRead(
        device_id=device.id,
        accepted=len(payload.capabilities),
        capabilities={view.key: view.state for view in views},  # type: ignore[misc]
    )


@router.get(
    "/presentations/next",
    response_model=PresentationEnvelopeRead,
    responses={204: {"description": "Nothing to show."}},
)
def device_next_presentation(
    device: CurrentDevice, db: DbSession, now: Now
) -> Response | PresentationEnvelopeRead:
    """The next thing this robot should show (PRD 11, sections 18, 58 and 59).

    Reconciliation runs first, so the answer is built from what is true at the
    moment of the request rather than from a queue somebody filled earlier.
    That is what makes section 56 hold without any special handling: a robot
    that has been unplugged for a week is not handed last Tuesday's "take this
    now", because last Tuesday's dose is not due.

    ``204`` when there is nothing, which keeps the firmware's happy path to a
    status-code check. Fetching marks the row ``sent`` and **nothing else** --
    section 14 is explicit that handing over a command is not displaying it,
    and the acknowledgement endpoint below is the only writer of
    ``displayed_at``.
    """
    if device.owner_profile_id is None:
        # Claimed, but not set up for anybody. Nothing belongs to nobody.
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    device.last_seen_at = now
    robot_presenter.refresh(db, device, now, assume_online=True)
    row = robot_queue.next_for_device(db, device, now)
    if row is None:
        db.commit()
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    try:
        envelope = robot_queue.envelope_for(db, device, row, now)
    except layouts.PayloadError:
        # A row written by an older build that this one can no longer render.
        # Marked unsupported rather than sent, because sending it would be
        # handing a device something the protocol says is invalid.
        robot_queue.cancel(db, row, reason="superseded", now=now)
        db.commit()
        logger.warning("device_action.presentation refused its own stored payload")
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    db.commit()
    logger.info("device_action.presentation_sent type=%s", row.presentation_type)
    return PresentationEnvelopeRead(**envelope)  # type: ignore[arg-type]


@router.post("/presentations/{presentation_id}/ack", response_model=PresentationAckRead)
def device_acknowledge_presentation(
    presentation_id: uuid.UUID,
    payload: PresentationAcknowledgement,
    device: CurrentDevice,
    db: DbSession,
    now: Now,
) -> PresentationAckRead:
    """A robot says what it did with a presentation (sections 14, 19 and 60).

    The only place in this codebase that writes ``displayed_at``, and the
    ``ck_device_presentations_displayed`` constraint means it cannot be written
    anywhere else even by mistake. Section 141 asks the question directly --
    *no robot acknowledgement? do not mark displayed* -- and the answer is that
    there is no other writer and the database would refuse one.

    Repeating an acknowledgement is accepted and changes nothing, so a device
    whose response was lost can send it again. Moving backwards is a 409: that
    is not a retry.
    """
    try:
        row = robot_queue.get(db, device.id, presentation_id)
    except DomainError:
        logger.info("device_action.presentation_ack refused: not found")
        raise PRESENTATION_NOT_FOUND from None

    before = row.status
    try:
        robot_queue.acknowledge(
            db, row, payload.state, now, failure_code=payload.failure_code
        )
        db.commit()
    except DomainError as error:
        db.rollback()
        raise http_error(error) from error

    db.refresh(row)
    logger.info(
        "device_action.presentation_ack state=%s status=%s", payload.state, row.status
    )
    return PresentationAckRead(
        presentation_id=row.id,
        status=row.status,  # type: ignore[arg-type]
        applied=row.status != before,
    )
