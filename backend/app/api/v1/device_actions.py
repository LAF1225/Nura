"""What a robot is allowed to do to a person's data (PRD 5, sections 45-47).

There is exactly one thing so far: confirm that a dose was taken, for the
future "I took it" behaviour. It is here rather than beside the app's own
medication routes because the two authenticate completely differently, and a
reader who is checking who can do what should not have to notice which
dependency a route used. Everything under ``/device-actions`` is authenticated
by a **device token** and nothing else.

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

**None of this needs the hardware.** The contract is real, authenticated and
tested; what does not exist yet is a robot that speaks. Nothing in PRD 5
depends on this route being called, and no claim is made here that voice
confirmation has been tried on a physical device (PRD 5, sections 44 and 73).
"""

import logging
import uuid

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.api.deps import CurrentDevice, DbSession, Now, http_error
from app.schemas.medication import DoseStatus
from app.services.errors import DomainError
from app.services.medications import doses as dose_service

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
