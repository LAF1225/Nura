"""Version 1 of the API (PRD 0, sections 15 and 29).

Routes for users, devices and health records get mounted here as later PRDs
add them, all under the ``/api/v1`` prefix.
"""

from fastapi import APIRouter

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
