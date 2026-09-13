"""Version 1 of the API (PRD 0 section 15; PRD 1 section 35).

Routes for health records and devices get mounted here as later PRDs add them,
all under the ``/api/v1`` prefix.
"""

from fastapi import APIRouter

from app.api.v1 import devices, me, onboarding, profiles
from app.core.config import API_V1_PREFIX, API_VERSION, MINIMUM_APP_VERSION
from app.schemas.system import VersionResponse

router = APIRouter(prefix=API_V1_PREFIX)


@router.get("/version", response_model=VersionResponse, tags=["system"])
def read_version() -> VersionResponse:
    """Lets the app check what it is talking to, and whether it needs updating."""
    return VersionResponse(
        api_version=API_VERSION,
        minimum_app_version=MINIMUM_APP_VERSION,
    )


router.include_router(me.router)
router.include_router(onboarding.router)
router.include_router(profiles.router)
router.include_router(devices.router)
