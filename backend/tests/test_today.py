"""Today, daily check-ins and dashboard preferences (PRD 3, sections 63-65).

Every test here runs against the real app and a real database, and none of
them needs a robot: where a device is involved it is a seeded row with a
controlled ``last_seen_at``, which is exactly what the app sees when hardware
exists (PRD 3, sections 6 and 51).
"""

import secrets
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.api.v1.devices import current_time
from app.main import app
from app.models import Device
from app.services.devices import hash_secret
from tests.test_devices import ready_account

TODAY = "2026-09-13"


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


def seed_device(db, client, headers, *, last_seen: datetime | None) -> Device:
    """A claimed robot with a chosen presence, without any hardware.

    This is the developer path PRD 3 section 25 asks for: the device row and
    its ``last_seen_at`` are the only things that decide online or offline, so
    setting them directly produces the genuine article.
    """
    account_id = client.get("/api/v1/me", headers=headers).json()["id"]
    device = Device(
        hardware_id="NURA-3C84279A1B2C",
        display_name="Nura",
        claimed_by_account_id=uuid.UUID(account_id),
        provisioning_status="claimed",
        bootstrap_secret_hash=hash_secret(secrets.token_hex(32)),
        device_token_hash=hash_secret(secrets.token_hex(32)),
        claimed_at=datetime(2026, 9, 13, 8, 0, tzinfo=UTC),
        last_seen_at=last_seen,
    )
    db.add(device)
    db.commit()
    return device


def submit(client, headers, level: str, **body):
    return client.put(
        "/api/v1/daily-checkins/today",
        json={"wellbeing_level": level, "local_date": TODAY, **body},
        headers=headers,
    )


def profile_id_of(client, headers) -> str:
    return client.get("/api/v1/me", headers=headers).json()["profiles"][0]["id"]


# --- daily check-in ---------------------------------------------------------


def test_submits_and_reads_back_todays_checkin(client, make_token, clock):
    headers = ready_account(client, make_token)

    response = submit(client, headers, "good", note="  Slept well  ")
    assert response.status_code == 200, response.json()
    body = response.json()
    assert body["applied"] is True
    assert body["checkin"]["wellbeing_level"] == "good"
    # Trimmed, because a stray space is not part of what someone wrote.
    assert body["checkin"]["note"] == "Slept well"
    assert body["checkin"]["checkin_date"] == TODAY

    read = client.get(f"/api/v1/daily-checkins/today?local_date={TODAY}", headers=headers)
    assert read.json()["checkin"]["wellbeing_level"] == "good"


def test_changing_todays_answer_updates_the_same_row(client, make_token, clock):
    """PRD 3, section 11: one row per profile per date, never a duplicate."""
    headers = ready_account(client, make_token)

    first = submit(client, headers, "okay").json()["checkin"]
    second = submit(client, headers, "not_great", note="Headache").json()["checkin"]

    assert second["id"] == first["id"]
    assert second["wellbeing_level"] == "not_great"

    recent = client.get(
        f"/api/v1/daily-checkins/recent?local_date={TODAY}", headers=headers
    ).json()
    assert recent["completed_count"] == 1
    assert len(recent["checkins"]) == 1


def test_clearing_the_note_removes_it(client, make_token, clock):
    headers = ready_account(client, make_token)
    submit(client, headers, "okay", note="Tired")
    cleared = submit(client, headers, "okay", note="   ").json()["checkin"]
    assert cleared["note"] is None


def test_a_stale_offline_submission_does_not_overwrite_a_newer_answer(
    client, make_token, clock
):
    """PRD 3, section 28: the latest explicit user edit wins."""
    headers = ready_account(client, make_token)

    submit(client, headers, "good")
    current = submit(client, headers, "not_great").json()["checkin"]

    # Real time, not the injected clock: `updated_at` is written by the
    # database, and the rule compares two genuine wall-clock moments.
    stored_at = datetime.fromisoformat(current["updated_at"])

    # A queued submission made before that edit finally reaches the server.
    stale = submit(
        client,
        headers,
        "okay",
        client_updated_at=(stored_at - timedelta(hours=2)).isoformat(),
    )
    body = stale.json()
    assert body["applied"] is False
    # The client is handed the stored answer, so it can converge on it.
    assert body["checkin"]["wellbeing_level"] == "not_great"
    assert body["checkin"]["updated_at"] == current["updated_at"]


def test_a_queued_submission_newer_than_the_stored_one_is_applied(
    client, make_token, clock
):
    headers = ready_account(client, make_token)
    stored = submit(client, headers, "good").json()["checkin"]
    edited_at = datetime.fromisoformat(stored["updated_at"]) + timedelta(seconds=1)

    applied = submit(
        client, headers, "okay", client_updated_at=edited_at.isoformat()
    ).json()
    assert applied["applied"] is True
    assert applied["checkin"]["wellbeing_level"] == "okay"


def test_rejects_a_date_that_cannot_be_anyones_today(client, make_token, clock):
    headers = ready_account(client, make_token)
    response = submit(client, headers, "good", local_date="2026-08-01")
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "local_date_out_of_range"


def test_accepts_a_local_date_a_day_either_side_of_utc(client, make_token, clock):
    """Kiritimati is UTC+14 and Baker Island UTC-12; both are somebody's today."""
    headers = ready_account(client, make_token)
    assert submit(client, headers, "good", local_date="2026-09-14").status_code == 200
    assert submit(client, headers, "good", local_date="2026-09-12").status_code == 200


def test_rejects_an_unknown_wellbeing_value(client, make_token, clock):
    headers = ready_account(client, make_token)
    assert submit(client, headers, "terrible").status_code == 422


def test_an_account_without_a_profile_cannot_check_in(client, auth_headers, clock):
    response = client.put(
        "/api/v1/daily-checkins/today",
        json={"wellbeing_level": "good", "local_date": TODAY},
        headers=auth_headers,
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "profile_required"


# --- authorization ----------------------------------------------------------


def test_one_account_cannot_read_another_profiles_checkin(client, make_token, clock):
    owner = ready_account(client, make_token)
    submit(client, owner, "good")
    owner_profile_id = profile_id_of(client, owner)

    stranger = ready_account(client, make_token)
    response = client.get(
        f"/api/v1/daily-checkins/today?local_date={TODAY}&profile_id={owner_profile_id}",
        headers=stranger,
    )
    # 404, not 403: the endpoint does not confirm that the id exists.
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "profile_not_found"


def test_one_account_cannot_update_another_profiles_checkin(client, make_token, clock):
    owner = ready_account(client, make_token)
    submit(client, owner, "good")
    owner_profile_id = profile_id_of(client, owner)

    stranger = ready_account(client, make_token)
    response = submit(client, stranger, "not_great", profile_id=owner_profile_id)
    assert response.status_code == 404

    # And the owner's answer is untouched.
    still = client.get(
        f"/api/v1/daily-checkins/today?local_date={TODAY}", headers=owner
    ).json()
    assert still["checkin"]["wellbeing_level"] == "good"


def test_recent_returns_only_the_callers_own_profile(client, make_token, clock):
    owner = ready_account(client, make_token)
    submit(client, owner, "good")

    stranger = ready_account(client, make_token)
    recent = client.get(
        f"/api/v1/daily-checkins/recent?local_date={TODAY}", headers=stranger
    ).json()
    assert recent["completed_count"] == 0
    assert recent["checkins"] == []


def test_recent_counts_only_days_inside_the_window(client, make_token, clock):
    headers = ready_account(client, make_token)
    submit(client, headers, "good", local_date="2026-09-12")
    submit(client, headers, "okay", local_date=TODAY)

    week = client.get(
        f"/api/v1/daily-checkins/recent?local_date={TODAY}", headers=headers
    ).json()
    assert week["completed_count"] == 2
    assert week["from_date"] == "2026-09-07"

    one_day = client.get(
        f"/api/v1/daily-checkins/recent?local_date={TODAY}&days=1", headers=headers
    ).json()
    assert one_day["completed_count"] == 1


# --- dashboard preferences --------------------------------------------------


def test_dashboard_defaults_show_the_calm_layout(client, make_token, clock):
    headers = ready_account(client, make_token)
    cards = client.get("/api/v1/dashboard-preferences", headers=headers).json()["cards"]

    by_key = {card["key"]: card for card in cards}
    assert by_key["daily_checkin"]["visible"] is True
    assert by_key["device_status"]["visible"] is True
    # Real, but off until the user asks for it (PRD 3, sections 3 and 19).
    assert by_key["quick_actions"]["visible"] is False
    # Reserved keys are listed but never available, so no client renders them.
    assert by_key["medications"]["available"] is False


def test_dashboard_preferences_persist_and_reorder(client, make_token, clock):
    headers = ready_account(client, make_token)

    saved = client.put(
        "/api/v1/dashboard-preferences",
        json={
            "cards": [
                {"card_key": "device_status", "visible": True},
                {"card_key": "quick_actions", "visible": True},
                {"card_key": "daily_checkin", "visible": False},
            ]
        },
        headers=headers,
    )
    assert saved.status_code == 200, saved.json()

    cards = client.get("/api/v1/dashboard-preferences", headers=headers).json()["cards"]
    assert [card["key"] for card in cards[:3]] == [
        "device_status",
        "quick_actions",
        "daily_checkin",
    ]
    assert cards[2]["visible"] is False
    assert [card["position"] for card in cards[:3]] == [0, 1, 2]


def test_a_card_whose_feature_does_not_exist_cannot_be_enabled(client, make_token, clock):
    headers = ready_account(client, make_token)
    response = client.put(
        "/api/v1/dashboard-preferences",
        json={"cards": [{"card_key": "medications", "visible": True}]},
        headers=headers,
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "unknown_card"


def test_an_unknown_card_key_is_refused(client, make_token, clock):
    headers = ready_account(client, make_token)
    response = client.put(
        "/api/v1/dashboard-preferences",
        json={"cards": [{"card_key": "horoscope", "visible": True}]},
        headers=headers,
    )
    assert response.status_code == 422


def test_one_account_cannot_change_another_profiles_layout(client, make_token, clock):
    owner = ready_account(client, make_token)
    owner_profile_id = profile_id_of(client, owner)

    stranger = ready_account(client, make_token)
    response = client.put(
        "/api/v1/dashboard-preferences",
        json={
            "profile_id": owner_profile_id,
            "cards": [{"card_key": "daily_checkin", "visible": False}],
        },
        headers=stranger,
    )
    assert response.status_code == 404


# --- today summary ----------------------------------------------------------


def test_today_works_with_no_device_and_no_checkin(client, make_token, clock):
    """PRD 3, section 6, state A: the app is fully usable with no robot."""
    headers = ready_account(client, make_token)

    body = client.get(f"/api/v1/today?local_date={TODAY}", headers=headers).json()
    assert body["profile"]["preferred_name"] == "Ada"
    assert body["device"] is None
    assert body["daily_checkin"]["status"] == "not_completed"
    assert body["daily_checkin"]["checkin"] is None
    assert body["daily_checkin"]["recent_completed_count"] == 0
    assert body["important"] == []
    assert [card["key"] for card in body["cards"]][:2] == [
        "daily_checkin",
        "device_status",
    ]


def test_today_reports_a_completed_checkin(client, make_token, clock):
    headers = ready_account(client, make_token)
    submit(client, headers, "okay", note="Fine")

    body = client.get(f"/api/v1/today?local_date={TODAY}", headers=headers).json()
    assert body["daily_checkin"]["status"] == "completed"
    assert body["daily_checkin"]["checkin"]["wellbeing_level"] == "okay"
    assert body["daily_checkin"]["recent_completed_count"] == 1


def test_today_reports_a_seeded_device_as_online(client, make_token, clock, db):
    """PRD 3, section 6, state C -- no hardware involved."""
    headers = ready_account(client, make_token)
    seed_device(db, client, headers, last_seen=clock.now - timedelta(seconds=30))

    device = client.get(f"/api/v1/today?local_date={TODAY}", headers=headers).json()[
        "device"
    ]
    assert device["connection_status"] == "online"
    assert device["display_name"] == "Nura"


def test_today_reports_a_stale_device_as_offline(client, make_token, clock, db):
    """PRD 3, section 6, state B."""
    headers = ready_account(client, make_token)
    seed_device(db, client, headers, last_seen=clock.now - timedelta(minutes=42))

    device = client.get(f"/api/v1/today?local_date={TODAY}", headers=headers).json()[
        "device"
    ]
    assert device["connection_status"] == "offline"
    assert device["last_seen_at"] is not None


def test_today_reports_a_never_seen_device_as_unknown(client, make_token, clock, db):
    headers = ready_account(client, make_token)
    seed_device(db, client, headers, last_seen=None)

    device = client.get(f"/api/v1/today?local_date={TODAY}", headers=headers).json()[
        "device"
    ]
    assert device["connection_status"] == "unknown"
    assert device["last_seen_at"] is None


def test_today_still_renders_for_an_account_with_no_profile(client, auth_headers, clock):
    body = client.get(f"/api/v1/today?local_date={TODAY}", headers=auth_headers).json()
    assert body["profile"] is None
    assert body["device"] is None
    assert body["daily_checkin"]["status"] == "not_completed"
    # Defaults, so the screen still has a layout to render.
    assert any(card["key"] == "daily_checkin" for card in body["cards"])


def test_today_reflects_a_saved_layout(client, make_token, clock):
    headers = ready_account(client, make_token)
    client.put(
        "/api/v1/dashboard-preferences",
        json={
            "cards": [
                {"card_key": "quick_actions", "visible": True},
                {"card_key": "daily_checkin", "visible": True},
                {"card_key": "device_status", "visible": True},
            ]
        },
        headers=headers,
    )
    cards = client.get(f"/api/v1/today?local_date={TODAY}", headers=headers).json()[
        "cards"
    ]
    assert [card["key"] for card in cards][:3] == [
        "quick_actions",
        "daily_checkin",
        "device_status",
    ]


def test_today_needs_authentication(client):
    assert client.get("/api/v1/today").status_code == 401


# --- reminder preference (PRD 3, section 38) --------------------------------


def test_the_daily_checkin_reminder_preference_persists(client, auth_headers):
    response = client.patch(
        "/api/v1/me",
        json={
            "daily_checkin_reminder_enabled": True,
            "daily_checkin_reminder_time": "09:00",
        },
        headers=auth_headers,
    )
    assert response.status_code == 200
    settings = response.json()["settings"]
    assert settings["daily_checkin_reminder_enabled"] is True
    assert settings["daily_checkin_reminder_time"] == "09:00"


def test_a_reminder_time_that_is_not_a_time_is_refused(client, auth_headers):
    response = client.patch(
        "/api/v1/me",
        json={"daily_checkin_reminder_time": "quarter past nine"},
        headers=auth_headers,
    )
    assert response.status_code == 422
