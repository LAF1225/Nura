"""Verification of authentication tokens (PRD 1, sections 36 and 49).

Nura does not issue its own tokens. Supabase Auth owns identity; this module's
only job is to prove that a bearer token really came from our Supabase project
and has not expired, then hand back the claims inside it.

Two verification modes, because Supabase supports both:

* **Asymmetric (preferred).** The project publishes a JWKS endpoint and signs
  with ES256/RS256. Nothing secret has to be shared with this backend, which is
  why it is the default.
* **Shared secret (legacy).** Older projects sign with HS256 using the
  project's JWT secret. Supported as a fallback when ``SUPABASE_JWT_SECRET``
  is set.

Nothing here ever trusts a value the client sent outside the signed token --
in particular, never a ``user_id`` from a request body (PRD 1, section 36).
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

import jwt
from jwt import PyJWKClient

#: Supabase issues access tokens with this audience.
SUPABASE_AUDIENCE = "authenticated"

#: Algorithms we are willing to accept. Listing them explicitly matters: an
#: empty or permissive list is how "alg: none" style attacks get through.
ASYMMETRIC_ALGORITHMS = ("RS256", "ES256")
SYMMETRIC_ALGORITHMS = ("HS256",)


class InvalidTokenError(Exception):
    """Raised when a token is missing, malformed, expired or not ours.

    Deliberately carries no detail about *why*. The reason is logged
    server-side; the client only ever learns that it was not authorised
    (PRD 1, section 49).
    """


@dataclass(frozen=True)
class TokenClaims:
    """The parts of a verified token Nura actually uses."""

    #: The auth provider's stable user id (``sub``). This is what maps to
    #: ``users.auth_provider_id``.
    subject: str
    email: str | None
    phone: str | None
    expires_at: datetime


class TokenVerifier(Protocol):
    """Anything that can turn a raw token into verified claims."""

    def verify(self, token: str) -> TokenClaims: ...


def _claims_from_payload(payload: dict[str, Any]) -> TokenClaims:
    subject = payload.get("sub")
    if not isinstance(subject, str) or not subject:
        raise InvalidTokenError("token has no subject")

    expires = payload.get("exp")
    if not isinstance(expires, int):
        raise InvalidTokenError("token has no expiry")

    email = payload.get("email")
    phone = payload.get("phone")
    return TokenClaims(
        subject=subject,
        # Supabase sends "" rather than omitting these when absent.
        email=email if isinstance(email, str) and email else None,
        phone=phone if isinstance(phone, str) and phone else None,
        expires_at=datetime.fromtimestamp(expires, tz=UTC),
    )


class SupabaseJwksVerifier:
    """Verifies asymmetrically signed Supabase tokens against the project JWKS.

    ``PyJWKClient`` caches fetched keys, so this is one network call per key
    rotation rather than one per request.
    """

    def __init__(
        self,
        *,
        jwks_client: PyJWKClient,
        issuer: str,
        audience: str = SUPABASE_AUDIENCE,
    ) -> None:
        self._jwks_client = jwks_client
        self._issuer = issuer
        self._audience = audience

    def verify(self, token: str) -> TokenClaims:
        try:
            signing_key = self._jwks_client.get_signing_key_from_jwt(token)
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=list(ASYMMETRIC_ALGORITHMS),
                audience=self._audience,
                issuer=self._issuer,
                options={"require": ["exp", "sub"]},
            )
        except Exception as error:  # noqa: BLE001 - all failures are one outcome
            raise InvalidTokenError(str(error)) from error
        return _claims_from_payload(payload)


class SupabaseSharedSecretVerifier:
    """Verifies HS256 Supabase tokens using the project's JWT secret."""

    def __init__(
        self,
        *,
        secret: str,
        issuer: str,
        audience: str = SUPABASE_AUDIENCE,
    ) -> None:
        self._secret = secret
        self._issuer = issuer
        self._audience = audience

    def verify(self, token: str) -> TokenClaims:
        try:
            payload = jwt.decode(
                token,
                self._secret,
                algorithms=list(SYMMETRIC_ALGORITHMS),
                audience=self._audience,
                issuer=self._issuer,
                options={"require": ["exp", "sub"]},
            )
        except Exception as error:  # noqa: BLE001 - all failures are one outcome
            raise InvalidTokenError(str(error)) from error
        return _claims_from_payload(payload)
