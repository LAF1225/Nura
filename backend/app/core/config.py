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

    #: Supabase project URL, e.g. ``https://abcdefgh.supabase.co``. Not a
    #: secret. Everything the backend needs to verify tokens is derived from
    #: it. Leave unset and protected routes report that auth is not configured
    #: rather than letting anything through.
    supabase_url: str | None = None

    #: Only for projects still signing with the legacy HS256 shared secret.
    #: Leave unset for asymmetric (JWKS) projects, which is the default for new
    #: Supabase projects and the path that requires no shared secret at all.
    supabase_jwt_secret: str | None = None

    #: Where robots should reach this API once they are on Wi-Fi, e.g.
    #: ``https://api.nura.example``. Handed to the robot during provisioning.
    #: In development it may be left unset, in which case the address the
    #: phone used to reach the backend is used -- that is the LAN address, which
    #: the robot on the same Wi-Fi can reach too. Required outside development.
    device_api_base_url: str | None = None

    #: Where private user media -- symptom photos -- is kept. Relative paths
    #: resolve against `backend/`. Must not be inside anything served
    #: statically: the only way to these bytes is the authenticated route
    #: (PRD 6, section 63). The default is gitignored.
    private_media_root: str = ".private-media"

    #: Largest symptom photo the API will accept, in bytes (PRD 6, section 34).
    #: The app compresses before uploading, so this is a backstop rather than
    #: the usual size.
    max_photo_bytes: int = 6 * 1024 * 1024

    #: How many photos one symptom entry may carry (PRD 6, section 31).
    max_photos_per_entry: int = 5

    #: Whether the reviewed urgent-care safety rules are switched on
    #: (PRD 6, section 44). **False, and it must stay false until a clinician
    #: has reviewed the rule set and its wording.** The rules layer exists, is
    #: tested and is deliberately inert: with this off, a symptom recorded as
    #: worsening produces the generic "consider contacting a healthcare
    #: professional" guidance and nothing stronger. Turning it on is a
    #: clinical and legal decision, not a deployment one.
    symptom_red_flag_rules_enabled: bool = False

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"

    @property
    def media_root_path(self) -> Path:
        """The private media root as an absolute path."""
        root = Path(self.private_media_root)
        return root if root.is_absolute() else BACKEND_ROOT / root

    @property
    def supabase_base_url(self) -> str | None:
        """Project URL with any trailing slash removed."""
        if not self.supabase_url:
            return None
        return self.supabase_url.rstrip("/")

    @property
    def supabase_issuer(self) -> str | None:
        """The ``iss`` claim Supabase puts in its access tokens."""
        base = self.supabase_base_url
        return f"{base}/auth/v1" if base else None

    @property
    def supabase_jwks_url(self) -> str | None:
        """Where the project publishes its public signing keys."""
        base = self.supabase_base_url
        return f"{base}/auth/v1/.well-known/jwks.json" if base else None

    @property
    def auth_configured(self) -> bool:
        """Whether this backend can verify a token at all."""
        return bool(self.supabase_url)


@lru_cache
def get_settings() -> Settings:
    """Returns the settings, read once per process."""
    return Settings()  # type: ignore[call-arg]  # values come from the environment
