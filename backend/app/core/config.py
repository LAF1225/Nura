"""Backend configuration (PRD 0, section 18).

Every setting is read from the environment, with `backend/.env` used during
local development. Nothing secret is committed: `.env.example` at the repo root
lists the names, and real values stay on your machine.
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

#: The `backend/` directory. Used to locate `.env` by absolute path so the app
#: and its tests behave the same regardless of the working directory.
BACKEND_ROOT = Path(__file__).resolve().parents[2]

#: Version of the HTTP API this build serves (PRD 0, section 29).
API_VERSION = "0.1.0"

#: Oldest mobile app build this API still supports. The app can compare its own
#: version against this and prompt the user to update when it falls behind.
MINIMUM_APP_VERSION = "0.1.0"

#: Name reported by ``GET /health``.
SERVICE_NAME = "nura-api"

#: Prefix for all versioned routes (PRD 0, section 15).
API_V1_PREFIX = "/api/v1"


class Settings(BaseSettings):
    """Settings resolved from the environment."""

    model_config = SettingsConfigDict(
        env_file=BACKEND_ROOT / ".env",
        env_file_encoding="utf-8",
        # Ignore mobile-facing variables that also live in the root .env.
        extra="ignore",
    )

    #: SQLAlchemy URL, e.g.
    #: ``postgresql+psycopg://nura:password@localhost:5432/nura_dev``.
    #: Required -- the app refuses to start without it rather than silently
    #: falling back to some other database.
    database_url: str

    #: ``development`` locally, ``production`` when deployed.
    app_env: str = "development"

    #: Secret used to verify auth tokens. Intentionally has no default: a
    #: shipped default secret is worse than a missing one. PRD 1 makes this
    #: required once authentication is implemented.
    jwt_secret: str | None = None

    #: Browser origins allowed to call the API. Native builds do not use CORS;
    #: this exists so `npm run web` can reach the backend during development.
    cors_origins: list[str] = []

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"


@lru_cache
def get_settings() -> Settings:
    """Returns the settings, read once per process."""
    return Settings()  # type: ignore[call-arg]  # values come from the environment
