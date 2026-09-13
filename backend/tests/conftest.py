"""Test fixtures for the Nura backend.

Two things worth knowing before reading the tests:

**A real database.** Tests run against a real PostgreSQL database (``nura_test``,
created automatically) with the real Alembic migrations applied. That means the
tests also prove the migrations produce a schema the code actually works
against. Each test runs inside a transaction that is rolled back afterwards, so
they stay independent without re-running migrations every time.

**Real signature verification.** Rather than stubbing authentication out, the
suite generates an EC key pair, serves it as a JWKS, and signs genuine ES256
tokens. The production ``SupabaseJwksVerifier`` then verifies them for real, so
expiry, audience and issuer checks are all genuinely exercised -- no Supabase
project required.
"""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
import pytest
import sqlalchemy as sa
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import get_token_verifier
from app.core.config import get_settings
from app.core.security import SUPABASE_AUDIENCE, SupabaseJwksVerifier
from app.db.session import get_db
from app.main import app

TEST_DATABASE_NAME = "nura_test"
TEST_ISSUER = "https://nura-test.supabase.co/auth/v1"
TEST_KEY_ID = "nura-test-key"


def _test_database_url() -> str:
    """The dev database URL with the database name swapped for the test one."""
    url = sa.make_url(get_settings().database_url)
    return url.set(database=TEST_DATABASE_NAME).render_as_string(hide_password=False)


@pytest.fixture(scope="session")
def engine() -> Iterator[sa.Engine]:
    """Creates `nura_test` if needed, migrates it, and yields an engine."""
    admin_url = sa.make_url(get_settings().database_url).set(database="postgres")
    admin_engine = sa.create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as connection:
        exists = connection.execute(
            sa.text("SELECT 1 FROM pg_database WHERE datname = :name"),
            {"name": TEST_DATABASE_NAME},
        ).scalar()
        if not exists:
            connection.execute(sa.text(f'CREATE DATABASE "{TEST_DATABASE_NAME}"'))
    admin_engine.dispose()

    # Apply the real migrations, so the schema under test is the shipped one.
    from alembic.config import Config

    from alembic import command

    alembic_config = Config("alembic.ini")
    alembic_config.set_main_option("sqlalchemy.url", _test_database_url())
    command.upgrade(alembic_config, "head")

    test_engine = sa.create_engine(_test_database_url())
    # Start from an empty database. A run that crashed mid-test, or an older
    # run from before the savepoint fixture existed, would otherwise leave rows
    # behind and cause unique-key failures unrelated to the test at hand.
    with test_engine.begin() as connection:
        connection.execute(
            sa.text(
                "TRUNCATE provisioning_sessions, account_profile_roles, profiles, "
                "user_settings, devices, users RESTART IDENTITY CASCADE"
            )
        )
    yield test_engine
    test_engine.dispose()


@pytest.fixture
def db(engine: sa.Engine) -> Iterator[Session]:
    """A session wrapped in a transaction that is rolled back after each test.

    ``join_transaction_mode="create_savepoint"`` is what makes this work with
    endpoints that call ``commit()``: the session commits a SAVEPOINT rather
    than the outer transaction, so application code behaves exactly as it does
    in production while the test's rollback still discards everything.
    """
    connection = engine.connect()
    transaction = connection.begin()
    session = sessionmaker(
        bind=connection,
        autoflush=False,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )()
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture(scope="session")
def signing_key() -> ec.EllipticCurvePrivateKey:
    """An EC P-256 key pair standing in for the Supabase project's keys."""
    return ec.generate_private_key(ec.SECP256R1())


@pytest.fixture(scope="session")
def verifier(signing_key: ec.EllipticCurvePrivateKey) -> SupabaseJwksVerifier:
    """The production verifier, pointed at our local key instead of a network JWKS."""

    class LocalJwkClient:
        """Stands in for PyJWKClient, returning the local public key."""

        def get_signing_key_from_jwt(self, token: str) -> Any:
            class _Key:
                key = signing_key.public_key()

            return _Key()

    return SupabaseJwksVerifier(
        jwks_client=LocalJwkClient(),  # type: ignore[arg-type]
        issuer=TEST_ISSUER,
    )


@pytest.fixture
def make_token(signing_key: ec.EllipticCurvePrivateKey):
    """Mints a genuinely signed access token.

    Defaults produce a valid token; override the arguments to build the
    expired, wrong-audience and wrong-issuer cases the tests need.
    """

    def _make(
        *,
        subject: str | None = None,
        # Defaults to an address derived from the subject. Emails are unique in
        # the schema, so a fixed default would make two different accounts
        # collide rather than exercising the thing under test.
        email: str | None = None,
        phone: str | None = None,
        expires_in: timedelta = timedelta(hours=1),
        audience: str = SUPABASE_AUDIENCE,
        issuer: str = TEST_ISSUER,
    ) -> str:
        subject = subject or str(uuid.uuid4())
        email = email if email is not None else f"{subject}@example.test"
        now = datetime.now(UTC)
        payload: dict[str, Any] = {
            "sub": subject,
            "aud": audience,
            "iss": issuer,
            "iat": int(now.timestamp()),
            "exp": int((now + expires_in).timestamp()),
        }
        if email:
            payload["email"] = email
        if phone:
            payload["phone"] = phone
        return jwt.encode(
            payload, signing_key, algorithm="ES256", headers={"kid": TEST_KEY_ID}
        )

    return _make


@pytest.fixture
def client(db: Session, verifier: SupabaseJwksVerifier) -> Iterator[TestClient]:
    """A TestClient wired to the transactional session and the local verifier."""
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_token_verifier] = lambda: verifier
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def unconfigured_client(db: Session) -> Iterator[TestClient]:
    """A client for a deployment where no auth provider has been configured."""
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_token_verifier] = lambda: None
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def auth_headers(make_token) -> dict[str, str]:
    """Authorization header for a fresh, valid account."""
    return {"Authorization": f"Bearer {make_token()}"}
