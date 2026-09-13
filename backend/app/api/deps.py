"""Shared FastAPI dependencies (PRD 1, section 36).

The request path for a protected route:

    request -> bearer token -> verify signature -> resolve local account
            -> authorize the resource -> respond

A client-supplied identifier is never part of that chain. The only thing that
establishes who the caller is, is the ``sub`` claim inside a token whose
signature we checked.
"""

import logging
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import (
    InvalidTokenError,
    SupabaseJwksVerifier,
    SupabaseSharedSecretVerifier,
    TokenClaims,
    TokenVerifier,
)
from app.db.session import get_db
from app.models import Device, User, UserSettings
from app.services.devices import hash_secret

logger = logging.getLogger(__name__)

# auto_error=False so a missing header reaches our own handler and produces a
# consistent 401, rather than FastAPI's default 403.
bearer_scheme = HTTPBearer(auto_error=False)

UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    # Sanitised on purpose: the client never learns which check failed.
    detail="Not authenticated.",
    headers={"WWW-Authenticate": "Bearer"},
)


@lru_cache
def get_token_verifier() -> TokenVerifier | None:
    """Builds the verifier once per process, or None if auth is unconfigured.

    Cached because ``PyJWKClient`` holds the fetched-key cache; rebuilding it
    per request would re-fetch the JWKS every time.
    """
    settings = get_settings()
    issuer = settings.supabase_issuer
    if issuer is None:
        return None

    if settings.supabase_jwt_secret:
        logger.info("auth: verifying tokens with the legacy shared secret")
        return SupabaseSharedSecretVerifier(
            secret=settings.supabase_jwt_secret, issuer=issuer
        )

    jwks_url = settings.supabase_jwks_url
    assert jwks_url is not None  # guaranteed whenever issuer is set
    logger.info("auth: verifying tokens against project JWKS")
    return SupabaseJwksVerifier(
        jwks_client=PyJWKClient(jwks_url, cache_keys=True), issuer=issuer
    )


def _provision_account(db: Session, claims: TokenClaims) -> User:
    """Finds the account for these claims, creating it on first sight.

    Supabase owns identity; this table mirrors it. The first authenticated
    request from a new sign-up is what creates the local row, which is why
    there is no separate "register" endpoint to keep in sync.
    """
    user = db.query(User).filter(User.auth_provider_id == claims.subject).one_or_none()
    if user is not None:
        # Keep contact details in step with the provider -- a user may have
        # added a phone number or changed their email since last time.
        if claims.email and user.email != claims.email:
            user.email = claims.email
        if claims.phone and user.phone != claims.phone:
            user.phone = claims.phone
        if db.is_modified(user):
            db.commit()
        return user

    user = User(
        auth_provider_id=claims.subject,
        email=claims.email,
        phone=claims.phone,
        onboarding_status="authenticated",
    )
    user.settings = UserSettings()
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = (
            db.query(User).filter(User.auth_provider_id == claims.subject).one_or_none()
        )
        if existing is None:
            # Not a race on auth_provider_id after all -- something else
            # conflicted, such as the email already belonging to another
            # account. Surface it instead of guessing.
            logger.warning("auth: could not provision an account for a new sign-in")
            raise
        # Two first requests raced. The other one won; use its row.
        return existing

    db.refresh(user)
    logger.info("auth: provisioned a local account for a new sign-in")
    return user


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: Annotated[Session, Depends(get_db)],
    verifier: Annotated[TokenVerifier | None, Depends(get_token_verifier)],
) -> User:
    """Resolves the authenticated account, or raises 401.

    Returns 503 rather than 401 when no auth provider is configured: that is a
    deployment problem, not a problem with the caller's credentials, and
    saying so plainly is what PRD 1 section 52 asks for.

    The verifier arrives as a dependency rather than being fetched inline so
    tests can supply one backed by a locally generated key.
    """
    if verifier is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Authentication is not configured on this server. "
                "Set SUPABASE_URL in the backend environment."
            ),
        )

    if credentials is None or not credentials.credentials:
        raise UNAUTHORIZED

    try:
        claims = verifier.verify(credentials.credentials)
    except InvalidTokenError as error:
        # Reason is logged, never returned.
        logger.info("auth: rejected a token (%s)", error)
        raise UNAUTHORIZED from error

    return _provision_account(db, claims)


def get_current_device(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: Annotated[Session, Depends(get_db)],
) -> Device:
    """Resolves the robot calling a device endpoint, or raises 401 (PRD 2, section 55).

    Robots authenticate with the device token issued at claim, never with a
    user's login token. The two can't be confused: a user JWT has no matching
    token hash here, and a device token fails signature verification on user
    routes.
    """
    if credentials is None or not credentials.credentials:
        raise UNAUTHORIZED

    device = (
        db.query(Device)
        .filter(Device.device_token_hash == hash_secret(credentials.credentials))
        .one_or_none()
    )
    if device is None or device.claimed_by_account_id is None:
        raise UNAUTHORIZED
    return device


CurrentUser = Annotated[User, Depends(get_current_user)]
CurrentDevice = Annotated[Device, Depends(get_current_device)]
DbSession = Annotated[Session, Depends(get_db)]
