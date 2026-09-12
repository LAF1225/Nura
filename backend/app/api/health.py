"""Unversioned liveness probe (PRD 0, section 15).

Deliberately kept outside ``/api/v1``: it answers "is this process up?", which
is not a question that changes shape between API versions.

It intentionally does *not* touch the database. The mobile app uses this for
its connection indicator, and a liveness probe that fails because of a
database blip would report the wrong thing. A readiness endpoint that does
check dependencies can be added when something depends on it.
"""

from fastapi import APIRouter

from app.core.config import SERVICE_NAME
from app.schemas.system import HealthResponse

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse)
def read_health() -> HealthResponse:
    return HealthResponse(status="ok", service=SERVICE_NAME)
