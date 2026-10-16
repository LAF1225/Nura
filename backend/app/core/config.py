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

    #: A TrueType font to embed in generated PDFs, so a report can carry any
    #: script. Relative paths resolve against `backend/`. Left unset, reports
    #: are typeset in the PDF standard Helvetica, which covers Latin-1 only --
    #: see `services/appointments/pdf.py` for what happens to a character it
    #: cannot draw. Setting this is the whole fix; no code changes with it.
    report_font_path: str | None = None

    #: Whether the reviewed urgent-care safety rules are switched on
    #: (PRD 6, section 44). **False, and it must stay false until a clinician
    #: has reviewed the rule set and its wording.** The rules layer exists, is
    #: tested and is deliberately inert: with this off, a symptom recorded as
    #: worsening produces the generic "consider contacting a healthcare
    #: professional" guidance and nothing stronger. Turning it on is a
    #: clinical and legal decision, not a deployment one.
    symptom_red_flag_rules_enabled: bool = False

    # --- the Nura assistant (PRD 8, section 76) ---
    # Every one of these is server-side. Nothing here is ever sent to the app:
    # the app talks to this backend, and this backend talks to the model
    # provider. A provider key in a mobile build is a key in every user's
    # hands, which is why there is no EXPO_PUBLIC_ equivalent of any of these.

    #: Which model provider to use. ``anthropic`` is the real one. ``scripted``
    #: replays canned replies and is for tests and development fixtures --
    #: it is refused outside development. Left unset, the assistant reports
    #: that it is not configured rather than pretending to think.
    ai_provider: str = "unconfigured"

    #: The model to ask. Pinned in configuration rather than in code so
    #: changing it is a deployment decision.
    ai_model: str = "claude-opus-5"

    #: The provider credential. Has no default, for the same reason
    #: ``jwt_secret`` has none.
    ai_api_key: str | None = None

    #: How long one model request may take before the user is told Nura
    #: cannot answer right now (PRD 8, section 55).
    ai_timeout_seconds: float = 45.0

    #: Ceiling on a single reply (PRD 8, section 77). Conversational, not
    #: essay-length: this is a chat window on a phone.
    ai_max_output_tokens: int = 1500

    #: How hard the model works per reply. ``low`` suits a chat assistant
    #: whose safety behaviour is enforced by deterministic policy rather than
    #: by model judgement (PRD 8, section 74); raise it if replies need more
    #: reasoning than conversation does.
    ai_effort: str = "low"

    #: Whether to ask the provider to re-route a declined request to another
    #: model rather than returning nothing. Harmless to switch off, and worth
    #: switching off if the account serving this deployment has not been
    #: enrolled in the beta that provides it.
    ai_server_side_fallback: bool = True

    #: How many assistant messages one profile may send per hour
    #: (PRD 8, section 97).
    assistant_rate_limit_per_hour: int = 60

    # --- audio calling (PRD 9, sections 38 and 39) ---
    #: Which audio-call provider to use. Unset in every deployment today, and
    #: the only implementation behind that is ``UnconfiguredCallProvider``,
    #: which refuses every call rather than reporting a successful one --
    #: PRD 9 section 38 forbids simulating a call that is not happening.
    #:
    #: Wiring a real provider later means a class in
    #: ``services.caregivers.calls`` and a branch in ``build_provider``;
    #: its credentials belong here, server-side, for the same reason the
    #: model provider's key does.
    audio_call_provider: str | None = None

    # --- safety delivery providers (PRD 10, sections 35 and 109) ---
    # All three are unset in every deployment, and the capability endpoint
    # reports ``not_configured`` because of it rather than because somebody
    # wrote that into a screen. Section 109 is explicit that unset means
    # not configured and that production must not default to a fake provider,
    # which is why there is no "mock" or "log" value any of these accepts:
    # ``services.safety.providers.build_notification_provider`` refuses a name
    # it does not implement rather than falling back to something that cannot
    # do what the name promised.

    #: Where a safety push notification would go. Nothing implements one, so
    #: setting this refuses at startup rather than silently doing nothing.
    safety_push_provider: str | None = None

    #: Where a safety SMS would go. Same.
    safety_sms_provider: str | None = None

    #: Who would place an emergency phone call to a contact. Distinct from
    #: ``audio_call_provider``, which is PRD 9's two-way call between a primary
    #: user and a caregiver who both have the app: this one would ring a
    #: number belonging to somebody who may have no Nura account at all.
    #: Configuring one must never be taken to configure the other.
    safety_call_provider: str | None = None

    #: Whether to log the *shape* of model requests -- token counts, latency,
    #: which tools ran. **Never the conversation itself**, at any setting
    #: (PRD 8, section 58). Off by default; intended for development.
    assistant_log_model_requests: bool = False

    # --- external information providers (PRD 12, sections 25-29 and 73) ---
    # All three are unset in every deployment, and the assistant's capability
    # map reports ``not_configured`` because of it rather than because somebody
    # wrote that into a screen. Section 76 forbids implementing a fake one, so
    # there is no "mock" value any of these accepts: nothing implements a
    # provider, and ``services.productivity.providers`` refuses any name at
    # startup rather than quietly returning something that looks live.
    #
    # Wiring a real one later means a class in that module, a branch in its
    # factory, and this setting. Its credentials belong here, server-side, for
    # the same reason the model provider's key does (section 74).

    #: Who would answer "what is the weather". Nothing implements one.
    weather_provider: str | None = None

    #: Who would answer "what is in the news". Nothing implements one.
    news_provider: str | None = None

    #: Which external calendar Nura would read or write. Nothing implements
    #: one, and section 28 is explicit: never claim an item was added to
    #: Google, Apple or Outlook Calendar unless it actually was.
    external_calendar_provider: str | None = None

    @property
    def assistant_configured(self) -> bool:
        """Whether this backend can reach a model provider at all.

        ``scripted`` needs no key: it is canned text. ``anthropic`` needs one,
        and saying so plainly beats letting every conversation fail at the
        provider with an authentication error.
        """
        if self.ai_provider == "scripted":
            return True
        if self.ai_provider == "anthropic":
            return bool(self.ai_api_key)
        return False

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"

    @property
    def media_root_path(self) -> Path:
        """The private media root as an absolute path."""
        root = Path(self.private_media_root)
        return root if root.is_absolute() else BACKEND_ROOT / root

    @property
    def report_font_file(self) -> Path | None:
        """The embedded report font as an absolute path, if one is configured."""
        if not self.report_font_path:
            return None
        path = Path(self.report_font_path)
        return path if path.is_absolute() else BACKEND_ROOT / path

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
