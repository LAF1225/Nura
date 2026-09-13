"""Robot provisioning, claiming, heartbeats and presence (PRD 2, section 68).

Every request here goes through the real app and a real database. The robot's
side is played by plain HTTP calls carrying exactly what the firmware sends, so
these tests pin the contract in docs/device/provisioning-protocol.md.
"""

import secrets
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.api.v1.devices import current_time
from app.main import app
from app.models import Device, ProvisioningSession
from app.services import devices as device_service

HARDWARE_ID = "NURA-3C84279A1B2C"
OTHER_HARDWARE_ID = "NURA-3C84279AFFFF"


class Clock:
    """A settable clock, injected in place of the real one."""

    def __init__(self) -> None:
        self.now = datetime(2026, 9, 13, 12, 0, tzinfo=UTC)

    def advance(self, **kwargs: float) -> None:
        self.now += timedelta(**kwargs)


@pytest.fixture
def clock(client) -> Clock:
    fake = Clock()
    app.dependency_overrides[current_time] = lambda: fake.now
    return fake


def new_secret() -> str:
    return secrets.token_hex(32)


def ready_account(client, make_token, *, setup_mode: str = "self") -> dict[str, str]:
    """An account that has finished PRD 1 onboarding, driven through the API."""
    headers = {"Authorization": f"Bearer {make_token()}"}
    client.patch(
        "/api/v1/onboarding",
        json={"setup_mode": setup_mode, "status": "setup_mode_selected"},
        headers=headers,
    )
    role = "setup_helper" if setup_mode == "assisted" else "self"
    client.post(
        "/api/v1/profiles",
        json={"preferred_name": "Ada", "role": role},
        headers=headers,
    )
    response = client.patch(
        "/api/v1/onboarding",
        json={
            "accept_terms": True,
            "acknowledge_privacy": True,
            "status": "ready_for_pairing",
        },
        headers=headers,
    )
    assert response.json()["status"] == "ready_for_pairing"
    return headers


def start_session(client, headers, hardware_id: str = HARDWARE_ID):
    return client.post(
        "/api/v1/devices/provisioning-sessions",
        json={"hardware_id": hardware_id},
        headers=headers,
    )


def claim(client, token: str, secret: str, hardware_id: str = HARDWARE_ID):
    return client.post(
        "/api/v1/devices/claim",
        json={
            "hardware_id": hardware_id,
            "provisioning_token": token,
            "bootstrap_secret": secret,
            "firmware_version": "0.1.0",
        },
    )


def heartbeat(client, device_token: str, **body):
    return client.post(
        "/api/v1/devices/heartbeat",
        json={"firmware_version": "0.1.0", **body},
        headers={"Authorization": f"Bearer {device_token}"},
    )


def pair(client, headers, secret: str | None = None, hardware_id: str = HARDWARE_ID):
    """Session + claim + first heartbeat. Returns (device_id, device_token)."""
    token = start_session(client, headers, hardware_id).json()["provisioning_token"]
    claimed = claim(client, token, secret or new_secret(), hardware_id)
    assert claimed.status_code == 200, claimed.json()
    device_token = claimed.json()["device_token"]
    assert heartbeat(client, device_token).status_code == 200
    return claimed.json()["device_id"], device_token


def error_code(response) -> str:
    return response.json()["detail"]["code"]


# --- provisioning sessions ----------------------------------------------------


def test_provisioning_session_requires_authentication(client) -> None:
    response = client.post(
        "/api/v1/devices/provisioning-sessions", json={"hardware_id": HARDWARE_ID}
    )
    assert response.status_code == 401


def test_provisioning_session_requires_finished_onboarding(client, auth_headers) -> None:
    """PRD 2, section 5: pairing starts from ready_for_pairing."""
    response = start_session(client, auth_headers)
    assert response.status_code == 409
    assert error_code(response) == "onboarding_incomplete"


def test_provisioning_session_rejects_malformed_hardware_id(client, make_token) -> None:
    headers = ready_account(client, make_token)
    for bad in ("nura-3c84279a1b2c", "NURA-123", "Bedroom Nura", ""):
        response = start_session(client, headers, bad)
        assert response.status_code == 422, bad


def test_provisioning_session_issues_a_short_lived_hashed_token(
    client, make_token, clock, db
) -> None:
    headers = ready_account(client, make_token)
    response = start_session(client, headers)

    assert response.status_code == 201
    body = response.json()
    assert body["provisioning_token"].startswith("npt_")
    assert datetime.fromisoformat(body["expires_at"]) == clock.now + timedelta(minutes=10)
    # Development: the robot is told the address the phone used.
    assert body["device_api_base_url"] == "http://testserver"

    stored = db.get(ProvisioningSession, uuid.UUID(body["id"]))
    assert stored is not None
    assert stored.token_hash != body["provisioning_token"]
    assert stored.token_hash == device_service.hash_secret(body["provisioning_token"])


def test_session_state_moves_from_pending_to_claimed(client, make_token) -> None:
    headers = ready_account(client, make_token)
    created = start_session(client, headers).json()
    url = f"/api/v1/devices/provisioning-sessions/{created['id']}"

    assert client.get(url, headers=headers).json()["state"] == "pending"

    claimed = claim(client, created["provisioning_token"], new_secret())
    after = client.get(url, headers=headers).json()
    assert after["state"] == "claimed"
    assert after["device_id"] == claimed.json()["device_id"]


def test_session_state_expires(client, make_token, clock) -> None:
    headers = ready_account(client, make_token)
    created = start_session(client, headers).json()
    clock.advance(minutes=10, seconds=1)

    url = f"/api/v1/devices/provisioning-sessions/{created['id']}"
    assert client.get(url, headers=headers).json()["state"] == "expired"


def test_another_account_cannot_read_a_session(client, make_token) -> None:
    owner = ready_account(client, make_token)
    stranger = ready_account(client, make_token)
    created = start_session(client, owner).json()

    response = client.get(
        f"/api/v1/devices/provisioning-sessions/{created['id']}", headers=stranger
    )
    assert response.status_code == 404


# --- claiming -----------------------------------------------------------------


def test_unclaimed_device_can_be_claimed(client, make_token, db) -> None:
    headers = ready_account(client, make_token)
    token = start_session(client, headers).json()["provisioning_token"]

    response = claim(client, token, new_secret())

    assert response.status_code == 200
    body = response.json()
    assert body["device_token"].startswith("ndt_")
    assert body["heartbeat_interval_seconds"] == 5

    device = db.get(Device, uuid.UUID(body["device_id"]))
    assert device is not None
    assert device.hardware_id == HARDWARE_ID
    assert device.display_name == "Nura"
    assert device.provisioning_status == "claimed"
    assert device.owner_profile_id is not None
    assert device.device_token_hash == device_service.hash_secret(body["device_token"])


def test_assisted_setup_links_the_robot_to_the_person_being_helped(
    client, make_token, db
) -> None:
    headers = ready_account(client, make_token, setup_mode="assisted")
    device_id, _ = pair(client, headers)

    me = client.get("/api/v1/me", headers=headers).json()
    helped = next(p for p in me["profiles"] if p["role"] == "setup_helper")
    device = db.get(Device, uuid.UUID(device_id))
    assert device is not None
    assert str(device.owner_profile_id) == helped["id"]


def test_expired_provisioning_token_is_refused(client, make_token, clock) -> None:
    headers = ready_account(client, make_token)
    token = start_session(client, headers).json()["provisioning_token"]
    clock.advance(minutes=11)

    response = claim(client, token, new_secret())
    assert response.status_code == 401
    assert error_code(response) == "provisioning_token_invalid"


def test_unknown_provisioning_token_is_refused(client) -> None:
    response = claim(client, "npt_" + "x" * 43, new_secret())
    assert response.status_code == 401
    assert error_code(response) == "provisioning_token_invalid"


def test_token_is_bound_to_the_hardware_id_it_was_issued_for(client, make_token) -> None:
    headers = ready_account(client, make_token)
    token = start_session(client, headers, HARDWARE_ID).json()["provisioning_token"]

    response = claim(client, token, new_secret(), OTHER_HARDWARE_ID)
    assert response.status_code == 401


def test_single_use_token_cannot_be_used_by_another_robot(client, make_token) -> None:
    headers = ready_account(client, make_token)
    token = start_session(client, headers).json()["provisioning_token"]
    assert claim(client, token, new_secret()).status_code == 200

    # Same hardware id, different physical board.
    assert claim(client, token, new_secret()).status_code == 403
    # Different hardware id altogether.
    assert claim(client, token, new_secret(), OTHER_HARDWARE_ID).status_code == 401


def test_retrying_a_claim_rotates_the_device_token(client, make_token, db) -> None:
    """A robot whose claim response was lost can retry, and the old token dies."""
    headers = ready_account(client, make_token)
    token = start_session(client, headers).json()["provisioning_token"]
    secret = new_secret()

    first = claim(client, token, secret).json()
    second = claim(client, token, secret)

    assert second.status_code == 200
    assert second.json()["device_id"] == first["device_id"]
    assert second.json()["device_token"] != first["device_token"]
    assert heartbeat(client, first["device_token"]).status_code == 401
    assert heartbeat(client, second.json()["device_token"]).status_code == 200


def test_claimed_device_cannot_be_claimed_by_another_account(client, make_token) -> None:
    owner = ready_account(client, make_token)
    stranger = ready_account(client, make_token)
    secret = new_secret()

    # The stranger gets a session first, before the owner claims.
    stranger_token = start_session(client, stranger).json()["provisioning_token"]
    pair(client, owner, secret)

    # A new session for someone else's robot is refused up front...
    refused = start_session(client, stranger)
    assert refused.status_code == 409
    assert error_code(refused) == "already_claimed"

    # ...and a session obtained earlier cannot steal it either, even with the
    # genuine robot's secret.
    stolen = claim(client, stranger_token, secret)
    assert stolen.status_code == 409
    assert error_code(stolen) == "already_claimed"


def test_different_board_with_a_copied_hardware_id_is_refused(client, make_token) -> None:
    headers = ready_account(client, make_token)
    pair(client, headers, new_secret())

    token = start_session(client, headers).json()["provisioning_token"]
    response = claim(client, token, new_secret())

    assert response.status_code == 403
    assert error_code(response) == "identity_mismatch"


def test_reprovisioning_keeps_one_device_record(client, make_token, db) -> None:
    """PRD 2, section 66: a Wi-Fi change must not create a second device."""
    headers = ready_account(client, make_token)
    secret = new_secret()
    device_id, old_token = pair(client, headers, secret)
    client.patch(
        f"/api/v1/devices/{device_id}",
        json={"display_name": "Bedroom Nura"},
        headers=headers,
    )

    again_id, new_token = pair(client, headers, secret)

    assert again_id == device_id
    assert new_token != old_token
    devices = client.get("/api/v1/devices", headers=headers).json()
    assert len(devices) == 1
    assert devices[0]["display_name"] == "Bedroom Nura"
    assert db.query(Device).filter(Device.hardware_id == HARDWARE_ID).count() == 1


def test_claim_rejects_a_malformed_bootstrap_secret(client, make_token) -> None:
    headers = ready_account(client, make_token)
    token = start_session(client, headers).json()["provisioning_token"]
    assert claim(client, token, "not-hex").status_code == 422


# --- ownership ----------------------------------------------------------------


def test_owner_can_retrieve_their_device(client, make_token) -> None:
    headers = ready_account(client, make_token)
    device_id, _ = pair(client, headers)

    listed = client.get("/api/v1/devices", headers=headers)
    single = client.get(f"/api/v1/devices/{device_id}", headers=headers)

    assert listed.status_code == 200
    assert [device["id"] for device in listed.json()] == [device_id]
    assert single.status_code == 200
    assert single.json()["hardware_id"] == HARDWARE_ID
    # Nothing secret leaves the server.
    assert "device_token_hash" not in single.json()
    assert "bootstrap_secret_hash" not in single.json()


def test_unrelated_account_cannot_reach_a_device(client, make_token) -> None:
    owner = ready_account(client, make_token)
    stranger = ready_account(client, make_token)
    device_id, _ = pair(client, owner)

    assert client.get("/api/v1/devices", headers=stranger).json() == []
    for method, path, body in (
        ("get", f"/api/v1/devices/{device_id}", None),
        ("get", f"/api/v1/devices/{device_id}/status", None),
        ("patch", f"/api/v1/devices/{device_id}", {"display_name": "Mine now"}),
        ("post", f"/api/v1/devices/{device_id}/complete-setup", None),
    ):
        response = client.request(method, path, json=body, headers=stranger)
        # 404, not 403: the id is not confirmed to exist.
        assert response.status_code == 404, path


def test_device_list_requires_authentication(client) -> None:
    assert client.get("/api/v1/devices").status_code == 401


def test_rename_validates_the_display_name(client, make_token) -> None:
    headers = ready_account(client, make_token)
    device_id, _ = pair(client, headers)
    url = f"/api/v1/devices/{device_id}"

    for bad in ("", "   ", "x" * 41, "Bad\nname"):
        assert (
            client.patch(url, json={"display_name": bad}, headers=headers).status_code
            == 422
        )

    renamed = client.patch(url, json={"display_name": "  Mum's   Nura "}, headers=headers)
    assert renamed.status_code == 200
    assert renamed.json()["display_name"] == "Mum's Nura"
    # A label only: identity is unchanged.
    assert renamed.json()["id"] == device_id
    assert renamed.json()["hardware_id"] == HARDWARE_ID


# --- heartbeats and presence ------------------------------------------------------


def test_heartbeat_requires_a_device_token(client, make_token, auth_headers) -> None:
    assert client.post("/api/v1/devices/heartbeat", json={}).status_code == 401
    assert heartbeat(client, "ndt_" + "x" * 43).status_code == 401
    # A user's login token is not a device credential.
    user_token = auth_headers["Authorization"].removeprefix("Bearer ")
    assert heartbeat(client, user_token).status_code == 401


def test_device_token_cannot_reach_user_routes(client, make_token) -> None:
    headers = ready_account(client, make_token)
    _, device_token = pair(client, headers)
    response = client.get(
        "/api/v1/devices", headers={"Authorization": f"Bearer {device_token}"}
    )
    assert response.status_code == 401


def test_heartbeat_updates_last_seen(client, make_token, clock, db) -> None:
    headers = ready_account(client, make_token)
    token = start_session(client, headers).json()["provisioning_token"]
    claimed = claim(client, token, new_secret()).json()

    clock.advance(seconds=3)
    response = heartbeat(client, claimed["device_token"], firmware_version="0.1.1")

    assert response.status_code == 200
    device = db.get(Device, uuid.UUID(claimed["device_id"]))
    assert device is not None
    assert device.last_seen_at == clock.now
    assert device.firmware_version == "0.1.1"


def test_online_offline_calculation(client, make_token, clock) -> None:
    headers = ready_account(client, make_token)
    token = start_session(client, headers).json()["provisioning_token"]
    claimed = claim(client, token, new_secret()).json()
    status_url = f"/api/v1/devices/{claimed['device_id']}/status"

    # Claimed but no heartbeat yet: not online (PRD 2, section 34).
    before = client.get(status_url, headers=headers).json()
    assert before["connection_status"] == "unknown"
    assert before["checked_in_since_claim"] is False

    heartbeat(client, claimed["device_token"])
    online = client.get(status_url, headers=headers).json()
    assert online["connection_status"] == "online"
    assert online["checked_in_since_claim"] is True
    assert online["online_threshold_seconds"] == 90

    clock.advance(seconds=90)
    assert client.get(status_url, headers=headers).json()["connection_status"] == "online"

    clock.advance(seconds=1)
    assert (
        client.get(status_url, headers=headers).json()["connection_status"] == "offline"
    )

    heartbeat(client, claimed["device_token"])
    assert client.get(status_url, headers=headers).json()["connection_status"] == "online"


def test_heartbeat_interval_slows_after_the_setup_window(
    client, make_token, clock
) -> None:
    headers = ready_account(client, make_token)
    _, device_token = pair(client, headers)

    assert heartbeat(client, device_token).json()["heartbeat_interval_seconds"] == 5
    clock.advance(minutes=6)
    assert heartbeat(client, device_token).json()["heartbeat_interval_seconds"] == 30


# --- completing setup -----------------------------------------------------------


def test_complete_setup_requires_the_robot_to_have_checked_in(client, make_token) -> None:
    headers = ready_account(client, make_token)
    token = start_session(client, headers).json()["provisioning_token"]
    claimed = claim(client, token, new_secret()).json()

    response = client.post(
        f"/api/v1/devices/{claimed['device_id']}/complete-setup", headers=headers
    )
    assert response.status_code == 409
    assert error_code(response) == "device_not_online"


def test_complete_setup_is_refused_for_an_offline_robot(
    client, make_token, clock
) -> None:
    headers = ready_account(client, make_token)
    device_id, _ = pair(client, headers)
    clock.advance(minutes=5)

    response = client.post(f"/api/v1/devices/{device_id}/complete-setup", headers=headers)
    assert response.status_code == 409


def test_complete_setup_requests_the_introduction_and_advances_onboarding(
    client, make_token
) -> None:
    headers = ready_account(client, make_token)
    device_id, device_token = pair(client, headers)

    response = client.post(f"/api/v1/devices/{device_id}/complete-setup", headers=headers)

    assert response.status_code == 200
    assert response.json()["setup_completed_at"] is not None
    onboarding = client.get("/api/v1/onboarding", headers=headers).json()
    assert onboarding["status"] == "robot_connected"

    # The robot learns it should introduce itself on its next heartbeat...
    beat = heartbeat(client, device_token).json()
    assert beat["introduce"] is True
    assert beat["heartbeat_interval_seconds"] == 5

    # ...and once it reports having played it, it is not asked again.
    played = heartbeat(client, device_token, introduction_played=True).json()
    assert played["introduce"] is False
    device = client.get(f"/api/v1/devices/{device_id}", headers=headers).json()
    assert device["introduced_at"] is not None


def test_onboarding_cannot_claim_robot_connected_without_a_robot(
    client, make_token
) -> None:
    headers = ready_account(client, make_token)
    response = client.patch(
        "/api/v1/onboarding", json={"status": "robot_connected"}, headers=headers
    )
    assert response.status_code == 409
    assert "Connect your Nura" in response.json()["detail"]


# --- pure rules -----------------------------------------------------------------


def test_connection_status_thresholds() -> None:
    now = datetime(2026, 9, 13, tzinfo=UTC)
    device = Device(hardware_id=HARDWARE_ID, bootstrap_secret_hash="0" * 64)

    assert device_service.connection_status(device, now) == "unknown"
    device.last_seen_at = now - timedelta(seconds=90)
    assert device_service.connection_status(device, now) == "online"
    device.last_seen_at = now - timedelta(seconds=91)
    assert device_service.connection_status(device, now) == "offline"


def test_tokens_are_unique_prefixed_and_long() -> None:
    tokens = {device_service.generate_token("npt_") for _ in range(100)}
    assert len(tokens) == 100
    assert all(token.startswith("npt_") and len(token) >= 47 for token in tokens)
