"""Response models for the system endpoints (PRD 0, sections 15 and 29)."""

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Body of ``GET /health``."""

    status: str
    service: str


class VersionResponse(BaseModel):
    """Body of ``GET /api/v1/version``.

    Field names are snake_case because they are part of the wire contract the
    mobile app already expects; the app maps them to camelCase on its side.
    """

    api_version: str
    minimum_app_version: str
