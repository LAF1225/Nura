"""Onboarding flow, consent gate and profile isolation.

Covers PRD 1 section 54's backend list: profile create/update, onboarding
progress persistence, and a user being unable to reach another user's profile.
"""


def auth(make_token, **kwargs) -> dict[str, str]:
    return {"Authorization": f"Bearer {make_token(**kwargs)}"}


def test_new_account_starts_at_the_first_step(client, auth_headers) -> None:
    response = client.get("/api/v1/onboarding", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "authenticated"
    assert body["setup_mode"] is None
    assert body["step"] == 1
    assert body["total_steps"] == 5
    assert body["ready_for_pairing"] is False


def test_setup_mode_persists(client, auth_headers) -> None:
    patched = client.patch(
        "/api/v1/onboarding",
        json={"setup_mode": "assisted", "status": "setup_mode_selected"},
        headers=auth_headers,
    )
    assert patched.status_code == 200
    assert patched.json()["setup_mode"] == "assisted"

    # Read back separately -- persistence, not just the response body.
    reread = client.get("/api/v1/onboarding", headers=auth_headers)
    assert reread.json()["setup_mode"] == "assisted"
    assert reread.json()["status"] == "setup_mode_selected"
    assert reread.json()["step"] == 2


def test_cannot_select_setup_mode_status_without_choosing_one(
    client, auth_headers
) -> None:
    response = client.patch(
        "/api/v1/onboarding",
        json={"status": "setup_mode_selected"},
        headers=auth_headers,
    )

    assert response.status_code == 409
    assert "who Nura is being set up for" in response.json()["detail"]


def test_consent_gate_blocks_completion(client, auth_headers) -> None:
    """PRD 1, section 53: onboarding cannot complete without both acknowledgements."""
    client.patch(
        "/api/v1/onboarding",
        json={"setup_mode": "self", "status": "setup_mode_selected"},
        headers=auth_headers,
    )
    client.post("/api/v1/profiles", json={"preferred_name": "Ada"}, headers=auth_headers)
    client.patch(
        "/api/v1/onboarding",
        json={"status": "preferences_complete"},
        headers=auth_headers,
    )

    # Neither acknowledgement given yet.
    blocked = client.patch(
        "/api/v1/onboarding", json={"status": "ready_for_pairing"}, headers=auth_headers
    )
    assert blocked.status_code == 409
    assert "Terms of Service" in blocked.json()["detail"]

    # Only one of the two is not enough -- they are separate on purpose.
    client.patch("/api/v1/onboarding", json={"accept_terms": True}, headers=auth_headers)
    still_blocked = client.patch(
        "/api/v1/onboarding", json={"status": "ready_for_pairing"}, headers=auth_headers
    )
    assert still_blocked.status_code == 409
    assert "Privacy Policy" in still_blocked.json()["detail"]

    # Both given: the gate opens.
    client.patch(
        "/api/v1/onboarding", json={"acknowledge_privacy": True}, headers=auth_headers
    )
    allowed = client.patch(
        "/api/v1/onboarding", json={"status": "ready_for_pairing"}, headers=auth_headers
    )
    assert allowed.status_code == 200
    assert allowed.json()["ready_for_pairing"] is True
    assert allowed.json()["step"] == 5


def test_progress_never_moves_backwards(client, auth_headers) -> None:
    """Editing an earlier answer keeps the furthest step reached (section 44)."""
    client.patch(
        "/api/v1/onboarding",
        json={"setup_mode": "self", "status": "setup_mode_selected"},
        headers=auth_headers,
    )
    client.post("/api/v1/profiles", json={"preferred_name": "Ada"}, headers=auth_headers)
    client.patch(
        "/api/v1/onboarding",
        json={"status": "basic_profile_complete"},
        headers=auth_headers,
    )

    went_back = client.patch(
        "/api/v1/onboarding", json={"status": "authenticated"}, headers=auth_headers
    )

    assert went_back.status_code == 200
    assert went_back.json()["status"] == "basic_profile_complete"


def test_profile_create_and_update(client, auth_headers) -> None:
    created = client.post(
        "/api/v1/profiles",
        json={
            "preferred_name": "Ada",
            "age_range": "30_44",
            "country_region": "gb",
            "pronouns": "she/her",
        },
        headers=auth_headers,
    )
    assert created.status_code == 201
    body = created.json()
    assert body["preferred_name"] == "Ada"
    assert body["country_region"] == "GB"  # normalised to uppercase
    assert body["role"] == "self"

    updated = client.patch(
        f"/api/v1/profiles/{body['id']}",
        json={"preferred_name": "Ada L"},
        headers=auth_headers,
    )
    assert updated.status_code == 200
    assert updated.json()["preferred_name"] == "Ada L"
    # Omitted fields are untouched by a PATCH.
    assert updated.json()["age_range"] == "30_44"


def test_profile_requires_a_preferred_name(client, auth_headers) -> None:
    response = client.post(
        "/api/v1/profiles", json={"preferred_name": ""}, headers=auth_headers
    )

    assert response.status_code == 422


def test_rejects_an_unknown_age_range(client, auth_headers) -> None:
    response = client.post(
        "/api/v1/profiles",
        json={"preferred_name": "Ada", "age_range": "ancient"},
        headers=auth_headers,
    )

    assert response.status_code == 422


def test_assisted_setup_adds_a_second_profile(client, auth_headers) -> None:
    """The account holder plus the person Nura is actually for."""
    client.post("/api/v1/profiles", json={"preferred_name": "Ada"}, headers=auth_headers)

    helper = client.post(
        "/api/v1/profiles",
        json={"preferred_name": "Grace", "role": "setup_helper"},
        headers=auth_headers,
    )

    assert helper.status_code == 201
    assert helper.json()["role"] == "setup_helper"

    me = client.get("/api/v1/me", headers=auth_headers)
    roles = {p["preferred_name"]: p["role"] for p in me.json()["profiles"]}
    assert roles == {"Ada": "self", "Grace": "setup_helper"}


def test_one_self_profile_per_account(client, auth_headers) -> None:
    client.post("/api/v1/profiles", json={"preferred_name": "Ada"}, headers=auth_headers)

    duplicate = client.post(
        "/api/v1/profiles", json={"preferred_name": "Ada again"}, headers=auth_headers
    )

    assert duplicate.status_code == 409


def test_a_user_cannot_read_another_users_profile(client, make_token) -> None:
    """PRD 1, section 54. Answered 404 so the id's existence is not confirmed."""
    owner = auth(make_token, subject="owner", email="owner@example.com")
    created = client.post(
        "/api/v1/profiles", json={"preferred_name": "Ada"}, headers=owner
    )
    profile_id = created.json()["id"]

    intruder = auth(make_token, subject="intruder", email="intruder@example.com")
    read = client.get(f"/api/v1/profiles/{profile_id}", headers=intruder)
    assert read.status_code == 404

    written = client.patch(
        f"/api/v1/profiles/{profile_id}",
        json={"preferred_name": "Hacked"},
        headers=intruder,
    )
    assert written.status_code == 404

    # And the original is untouched.
    still_owned = client.get(f"/api/v1/profiles/{profile_id}", headers=owner)
    assert still_owned.json()["preferred_name"] == "Ada"


def test_preferences_persist(client, auth_headers) -> None:
    """PRD 1, section 53: interface preferences survive a restart."""
    response = client.patch(
        "/api/v1/me",
        json={"theme": "dark", "language": "ur", "larger_text": True},
        headers=auth_headers,
    )
    assert response.status_code == 200

    settings = client.get("/api/v1/me", headers=auth_headers).json()["settings"]
    assert settings["theme"] == "dark"
    assert settings["language"] == "ur"
    assert settings["larger_text"] is True
    # Untouched preferences keep their defaults.
    assert settings["reduce_motion"] is False


def test_rejects_an_unknown_theme(client, auth_headers) -> None:
    response = client.patch("/api/v1/me", json={"theme": "neon"}, headers=auth_headers)

    assert response.status_code == 422
