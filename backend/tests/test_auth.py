"""Authentication and access control (PRD 1, sections 36, 49 and 54).

Tokens here are genuinely signed and genuinely verified -- see conftest. A test
that passes means the real signature, expiry, audience and issuer checks all
ran, not that a stub waved the request through.
"""

from datetime import timedelta

import jwt


def test_unauthenticated_me_request_is_rejected(client) -> None:
    response = client.get("/api/v1/me")

    assert response.status_code == 401
    # The reason is never disclosed (PRD 1, section 49).
    assert response.json()["detail"] == "Not authenticated."


def test_authenticated_me_request_succeeds(client, make_token) -> None:
    token = make_token(subject="ada", email="ada@example.test")

    response = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    body = response.json()
    # Contact details come from the verified token, never from the request.
    assert body["email"] == "ada@example.test"
    # Settings are provisioned alongside the account, with PRD 0's defaults.
    assert body["settings"]["theme"] == "system"
    assert body["settings"]["language"] == "en"
    assert body["profiles"] == []


def test_first_authenticated_request_provisions_exactly_one_account(
    client, make_token
) -> None:
    """The same subject signing in twice must not create two accounts."""
    token = make_token(subject="repeat-subject")
    headers = {"Authorization": f"Bearer {token}"}

    first = client.get("/api/v1/me", headers=headers)
    second = client.get("/api/v1/me", headers=headers)

    assert first.status_code == second.status_code == 200
    assert first.json()["id"] == second.json()["id"]


def test_expired_token_is_rejected(client, make_token) -> None:
    token = make_token(expires_in=timedelta(seconds=-30))

    response = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401


def test_token_from_another_issuer_is_rejected(client, make_token) -> None:
    token = make_token(issuer="https://attacker.example.com/auth/v1")

    response = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401


def test_token_with_wrong_audience_is_rejected(client, make_token) -> None:
    token = make_token(audience="some-other-service")

    response = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401


def test_token_signed_by_a_different_key_is_rejected(client, make_token) -> None:
    """A well-formed token signed by someone else must not be accepted."""
    from cryptography.hazmat.primitives.asymmetric import ec

    attacker_key = ec.generate_private_key(ec.SECP256R1())
    forged = jwt.encode(
        {
            "sub": "forged-subject",
            "aud": "authenticated",
            "iss": "https://nura-test.supabase.co/auth/v1",
            "exp": 99999999999,
        },
        attacker_key,
        algorithm="ES256",
    )

    response = client.get("/api/v1/me", headers={"Authorization": f"Bearer {forged}"})

    assert response.status_code == 401


def test_unsigned_token_is_rejected(client) -> None:
    """The classic `alg: none` attack."""
    unsigned = jwt.encode(
        {"sub": "nobody", "aud": "authenticated", "exp": 99999999999},
        key="",
        algorithm="none",
    )

    response = client.get("/api/v1/me", headers={"Authorization": f"Bearer {unsigned}"})

    assert response.status_code == 401


def test_garbage_token_is_rejected(client) -> None:
    response = client.get(
        "/api/v1/me", headers={"Authorization": "Bearer not-a-real-token"}
    )

    assert response.status_code == 401


def test_reports_503_when_no_auth_provider_is_configured(
    unconfigured_client, auth_headers
) -> None:
    """A deployment problem is reported as one, not as a bad credential."""
    response = unconfigured_client.get("/api/v1/me", headers=auth_headers)

    assert response.status_code == 503
    assert "not configured" in response.json()["detail"].lower()


def test_public_endpoints_need_no_token(client) -> None:
    assert client.get("/health").status_code == 200
    assert client.get("/api/v1/version").status_code == 200
