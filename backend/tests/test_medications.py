"""Medication scheduling, doses, adherence and supply (PRD 5, sections 74, 82).

Every test runs against the real app, the real migrations and a real
PostgreSQL database, with a settable clock injected in place of the real one.
That clock is what makes the interesting cases testable at all: a dose does
not become missed because a test waited two hours, it becomes missed because
the clock moved.

**No hardware is involved anywhere in this file.** The robot tests seed a
device row with a known device token -- which is exactly what a claimed robot
holds -- and call the real device-authenticated route. That is PRD 5 section
47's simulated robot event: the authorization contract is genuinely exercised,
and no claim is made that a physical device has ever spoken (sections 44, 73
and 84).
"""

import secrets
import uuid
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.api.deps import current_time
from app.main import app
from app.models import Device, MedicationSchedule, MedicationScheduleTime
from app.services.devices import hash_secret
from app.services.medications import doses as dose_service
from tests.test_devices import ready_account
from tests.test_today import Clock

#: The day every test starts on. A Sunday, so weekday arithmetic in the
#: specific-days tests is easy to check by eye: 2026-09-13 is a Sunday.
TODAY = date(2026, 9, 13)
NOON = datetime(2026, 9, 13, 12, 0, tzinfo=UTC)


# --- helpers ----------------------------------------------------------------


@pytest.fixture
def clock(client) -> Clock:
    """A settable clock, injected in place of the real one.

    Declared here rather than imported from ``test_today``: a fixture is
    resolved by name in the module it is used from, and importing one only
    works by leaving an otherwise-unused name in the namespace.
    """
    fake = Clock()
    app.dependency_overrides[current_time] = lambda: fake.now
    return fake


@pytest.fixture
def account(client, make_token) -> tuple[dict[str, str], str]:
    """A ready account and the profile its medications belong to."""
    headers = ready_account(client, make_token)
    profile_id = client.get("/api/v1/me", headers=headers).json()["profiles"][0]["id"]
    return headers, profile_id


def add_medication(
    client, headers, profile_id, *, name: str = "Metformin", dose: str = "500 mg"
) -> str:
    """A PRD 4 medication record -- what the medication *is*."""
    response = client.post(
        f"/api/v1/profiles/{profile_id}/medications",
        json={"name": name, "dose": dose},
        headers=headers,
    )
    assert response.status_code == 201, response.json()
    return response.json()["id"]


@pytest.fixture
def medication(client, account) -> str:
    headers, profile_id = account
    return add_medication(client, headers, profile_id)


def schedules_url(profile_id: str) -> str:
    return f"/api/v1/profiles/{profile_id}/medication-schedules"


def doses_url(profile_id: str) -> str:
    return f"/api/v1/profiles/{profile_id}/medication-doses"


def supply_url(profile_id: str) -> str:
    return f"/api/v1/profiles/{profile_id}/medication-supply"


def make_schedule(
    client,
    headers,
    profile_id: str,
    medication_id: str,
    *,
    times: list[dict] | None = None,
    schedule_type: str = "daily",
    timezone: str = "UTC",
    start_date: str | None = None,
    end_date: str | None = None,
):
    body = {
        "medication_id": medication_id,
        "schedule_type": schedule_type,
        "timezone": timezone,
        "start_date": start_date or TODAY.isoformat(),
        # `or` would turn an explicitly empty list back into the default,
        # and an empty list is exactly what one test is checking.
        "times": [{"time_of_day": "08:00:00"}] if times is None else times,
    }
    if end_date is not None:
        body["end_date"] = end_date
    return client.post(schedules_url(profile_id), json=body, headers=headers)


def at_utc(iso: str) -> str:
    """The UTC wall time of an API timestamp, as HH:MM.

    PostgreSQL renders ``timestamptz`` in the *session's* zone, so a response
    may legitimately say ``2026-09-14T01:00:00+05:00`` for eight in the
    evening UTC. Comparing instants rather than strings is what stops these
    tests from depending on the machine the database happens to run on.
    """
    return datetime.fromisoformat(iso).astimezone(UTC).strftime("%H:%M")


def on_utc(iso: str) -> str:
    """The UTC calendar day of an API timestamp, as YYYY-MM-DD."""
    return datetime.fromisoformat(iso).astimezone(UTC).date().isoformat()


def list_doses(client, headers, profile_id: str, *, days: int = 20) -> list[dict]:
    """Every dose in a window wide enough to cover the generation horizon."""
    response = client.get(
        doses_url(profile_id),
        params={
            "from_date": (TODAY - timedelta(days=days)).isoformat(),
            "to_date": (TODAY + timedelta(days=days)).isoformat(),
        },
        headers=headers,
    )
    assert response.status_code == 200, response.json()
    return response.json()


def seed_device(db, client, headers, *, profile_id: str | None, hardware_id: str) -> str:
    """A claimed robot with a known device token, and no hardware anywhere.

    The token is the only thing that authenticates a device route, so handing
    a test the plaintext while the row stores its hash is exactly the state a
    real claim leaves behind (PRD 2, section 55).
    """
    token = f"nura-device-{secrets.token_hex(16)}"
    account_id = client.get("/api/v1/me", headers=headers).json()["id"]
    db.add(
        Device(
            hardware_id=hardware_id,
            display_name="Nura",
            claimed_by_account_id=uuid.UUID(account_id),
            owner_profile_id=None if profile_id is None else uuid.UUID(profile_id),
            provisioning_status="claimed",
            bootstrap_secret_hash=hash_secret(secrets.token_hex(32)),
            device_token_hash=hash_secret(token),
            claimed_at=NOON - timedelta(hours=4),
            last_seen_at=NOON,
        )
    )
    db.commit()
    return token


def unsaved_schedule(**kwargs) -> MedicationSchedule:
    """A schedule object for testing recurrence without touching the database."""
    times = kwargs.pop("times")
    schedule = MedicationSchedule(
        profile_id=uuid.uuid4(),
        medication_id=uuid.uuid4(),
        schedule_type=kwargs.pop("schedule_type", "daily"),
        timezone=kwargs.pop("timezone", "UTC"),
        start_date=kwargs.pop("start_date", TODAY),
        end_date=kwargs.pop("end_date", None),
        is_active=True,
    )
    schedule.times = [
        MedicationScheduleTime(time_of_day=entry[0], weekday=entry[1]) for entry in times
    ]
    return schedule


# --- schedule CRUD ----------------------------------------------------------


def test_a_schedule_can_be_created_read_updated_and_deleted(
    client, account, medication, clock
):
    headers, profile_id = account

    created = make_schedule(client, headers, profile_id, medication)
    assert created.status_code == 201, created.json()
    schedule = created.json()
    assert schedule["medication_name"] == "Metformin"
    assert schedule["medication_dose"] == "500 mg"
    assert schedule["is_active"] is True
    assert [entry["time_of_day"] for entry in schedule["times"]] == ["08:00:00"]

    listed = client.get(schedules_url(profile_id), headers=headers)
    assert [item["id"] for item in listed.json()] == [schedule["id"]]

    changed = client.patch(
        f"{schedules_url(profile_id)}/{schedule['id']}",
        json={"times": [{"time_of_day": "09:00:00"}]},
        headers=headers,
    )
    assert changed.status_code == 200
    assert [entry["time_of_day"] for entry in changed.json()["times"]] == ["09:00:00"]

    removed = client.delete(
        f"{schedules_url(profile_id)}/{schedule['id']}", headers=headers
    )
    assert removed.status_code == 204
    assert client.get(schedules_url(profile_id), headers=headers).json() == []


def test_a_medication_may_have_several_schedules(client, account, medication, clock):
    headers, profile_id = account
    assert make_schedule(client, headers, profile_id, medication).status_code == 201
    second = make_schedule(
        client,
        headers,
        profile_id,
        medication,
        times=[{"time_of_day": "22:00:00"}],
    )
    assert second.status_code == 201
    assert len(client.get(schedules_url(profile_id), headers=headers).json()) == 2


def test_a_schedule_cannot_be_attached_to_another_profiles_medication(
    client, make_token, account, clock
):
    headers, profile_id = account
    other_headers = ready_account(client, make_token)
    other_profile = client.get("/api/v1/me", headers=other_headers).json()["profiles"][0][
        "id"
    ]
    theirs = add_medication(client, other_headers, other_profile, name="Warfarin")

    response = make_schedule(client, headers, profile_id, theirs)
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "medication_not_found"


# --- validation -------------------------------------------------------------


def test_a_schedule_needs_at_least_one_time(client, account, medication, clock):
    headers, profile_id = account
    response = make_schedule(client, headers, profile_id, medication, times=[])
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_schedule"


def test_an_every_day_schedule_does_not_take_weekdays(client, account, medication, clock):
    headers, profile_id = account
    response = make_schedule(
        client,
        headers,
        profile_id,
        medication,
        times=[{"time_of_day": "08:00:00", "weekday": 0}],
    )
    assert response.status_code == 422


def test_a_specific_days_schedule_needs_weekdays(client, account, medication, clock):
    headers, profile_id = account
    response = make_schedule(
        client,
        headers,
        profile_id,
        medication,
        schedule_type="specific_days",
        times=[{"time_of_day": "08:00:00"}],
    )
    assert response.status_code == 422


def test_the_same_time_cannot_be_added_twice(client, account, medication, clock):
    headers, profile_id = account
    response = make_schedule(
        client,
        headers,
        profile_id,
        medication,
        times=[{"time_of_day": "08:00:00"}, {"time_of_day": "08:00:00"}],
    )
    assert response.status_code == 422


def test_an_unknown_time_zone_is_refused(client, account, medication, clock):
    headers, profile_id = account
    response = make_schedule(
        client, headers, profile_id, medication, timezone="Mars/Olympus"
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "unknown_timezone"


def test_an_end_date_before_the_start_is_refused(client, account, medication, clock):
    headers, profile_id = account
    response = make_schedule(
        client,
        headers,
        profile_id,
        medication,
        start_date=TODAY.isoformat(),
        end_date=(TODAY - timedelta(days=1)).isoformat(),
    )
    assert response.status_code == 422


# --- dose generation --------------------------------------------------------


def test_creating_a_schedule_fills_the_dose_window(client, account, medication, clock):
    headers, profile_id = account
    make_schedule(client, headers, profile_id, medication)

    doses = list_doses(client, headers, profile_id)
    # Today's 08:00 has already gone by at noon, so the window runs from
    # tomorrow to the horizon: one dose on each of 14 days.
    assert len(doses) == dose_service.GENERATION_HORIZON_DAYS
    assert {entry["status"] for entry in doses} == {"scheduled"}
    assert doses[0]["local_date"] == (TODAY + timedelta(days=1)).isoformat()


def test_a_schedule_never_backfills_the_past(client, account, medication, clock):
    """A schedule created at noon did not exist at 08:00 (PRD 5, section 22)."""
    headers, profile_id = account
    make_schedule(client, headers, profile_id, medication)

    doses = list_doses(client, headers, profile_id)
    assert all(entry["local_date"] > TODAY.isoformat() for entry in doses)


def test_several_times_a_day_produce_a_dose_each(client, account, medication, clock):
    headers, profile_id = account
    make_schedule(
        client,
        headers,
        profile_id,
        medication,
        times=[
            {"time_of_day": "08:00:00"},
            {"time_of_day": "14:00:00"},
            {"time_of_day": "20:00:00"},
        ],
    )

    doses = list_doses(client, headers, profile_id)
    tomorrow = (TODAY + timedelta(days=1)).isoformat()
    on_tomorrow = [entry for entry in doses if entry["local_date"] == tomorrow]
    assert len(on_tomorrow) == 3
    # 20:00 today is still ahead of the noon clock, so it is generated too.
    today_doses = [entry for entry in doses if entry["local_date"] == TODAY.isoformat()]
    assert [at_utc(entry["scheduled_for"]) for entry in today_doses] == ["14:00", "20:00"]


def test_specific_days_produce_only_those_weekdays(client, account, medication, clock):
    headers, profile_id = account
    # Monday, Wednesday, Friday at 09:00.
    make_schedule(
        client,
        headers,
        profile_id,
        medication,
        schedule_type="specific_days",
        times=[
            {"time_of_day": "09:00:00", "weekday": 0},
            {"time_of_day": "09:00:00", "weekday": 2},
            {"time_of_day": "09:00:00", "weekday": 4},
        ],
    )

    doses = list_doses(client, headers, profile_id)
    weekdays = {date.fromisoformat(entry["local_date"]).weekday() for entry in doses}
    assert weekdays == {0, 2, 4}


def test_an_end_date_stops_generation(client, account, medication, clock):
    headers, profile_id = account
    make_schedule(
        client,
        headers,
        profile_id,
        medication,
        end_date=(TODAY + timedelta(days=3)).isoformat(),
    )

    doses = list_doses(client, headers, profile_id)
    assert len(doses) == 3
    assert doses[-1]["local_date"] == (TODAY + timedelta(days=3)).isoformat()


def test_a_future_start_date_waits(client, account, medication, clock):
    headers, profile_id = account
    make_schedule(
        client,
        headers,
        profile_id,
        medication,
        start_date=(TODAY + timedelta(days=5)).isoformat(),
    )

    doses = list_doses(client, headers, profile_id)
    assert doses[0]["local_date"] == (TODAY + timedelta(days=5)).isoformat()


# --- daylight saving and travel ---------------------------------------------


def test_a_reminder_keeps_its_local_time_across_a_daylight_saving_change():
    """8am stays 8am on both sides of the spring change (PRD 5, section 12)."""
    schedule = unsaved_schedule(
        timezone="Europe/London",
        start_date=date(2026, 3, 27),
        times=[(time(8, 0), None)],
    )
    london = ZoneInfo("Europe/London")
    locals_ = [
        occurrence.scheduled_for.astimezone(london).strftime("%H:%M")
        for occurrence in dose_service.occurrences(
            schedule, date(2026, 3, 27), date(2026, 3, 31)
        )
    ]
    assert locals_ == ["08:00"] * 5

    # And the UTC instants did move, which is the whole point: the wall clock
    # stayed put because the offset changed under it.
    instants = [
        occurrence.scheduled_for.strftime("%H:%M")
        for occurrence in dose_service.occurrences(
            schedule, date(2026, 3, 27), date(2026, 3, 31)
        )
    ]
    assert instants[0] == "08:00"  # GMT
    assert instants[-1] == "07:00"  # BST


def test_a_local_time_that_does_not_exist_still_produces_one_dose():
    """01:30 on a spring-forward day. One dose, never zero (PRD 5, s12)."""
    schedule = unsaved_schedule(
        timezone="Europe/London",
        start_date=date(2026, 3, 29),
        times=[(time(1, 30), None)],
    )
    produced = list(
        dose_service.occurrences(schedule, date(2026, 3, 29), date(2026, 3, 29))
    )
    assert len(produced) == 1


def test_a_local_time_that_happens_twice_still_produces_one_dose():
    """01:30 on an autumn day, when the hour repeats. Never two doses."""
    schedule = unsaved_schedule(
        timezone="Europe/London",
        start_date=date(2026, 10, 25),
        times=[(time(1, 30), None)],
    )
    produced = list(
        dose_service.occurrences(schedule, date(2026, 10, 25), date(2026, 10, 25))
    )
    assert len(produced) == 1
    # The earlier of the two, which is still summer time.
    assert produced[0].scheduled_for == datetime(2026, 10, 25, 0, 30, tzinfo=UTC)


def test_changing_the_time_zone_does_not_duplicate_a_day(
    client, account, medication, clock
):
    """Travel regenerates the future rather than reinterpreting it."""
    headers, profile_id = account
    created = make_schedule(
        client, headers, profile_id, medication, timezone="Europe/London"
    )
    schedule_id = created.json()["id"]

    moved = client.patch(
        f"{schedules_url(profile_id)}/{schedule_id}",
        json={"timezone": "America/New_York"},
        headers=headers,
    )
    assert moved.status_code == 200

    doses = list_doses(client, headers, profile_id)
    days = [entry["local_date"] for entry in doses]
    assert len(days) == len(set(days)), "a day was scheduled twice after travelling"


# --- editing, pausing and deleting ------------------------------------------


def take_first_dose(client, headers, profile_id) -> dict:
    """Marks the soonest dose taken and returns it."""
    doses = list_doses(client, headers, profile_id)
    response = client.post(
        f"{doses_url(profile_id)}/{doses[0]['id']}/taken", json={}, headers=headers
    )
    assert response.status_code == 200, response.json()
    return response.json()["dose"]


def test_editing_a_schedule_changes_future_doses_only(client, account, medication, clock):
    headers, profile_id = account
    created = make_schedule(client, headers, profile_id, medication)
    schedule_id = created.json()["id"]

    # Move the clock past tomorrow's 08:00 and record it, so there is history.
    clock.now = datetime(2026, 9, 14, 8, 30, tzinfo=UTC)
    taken = take_first_dose(client, headers, profile_id)
    assert taken["status"] == "taken"

    changed = client.patch(
        f"{schedules_url(profile_id)}/{schedule_id}",
        json={"times": [{"time_of_day": "19:00:00"}]},
        headers=headers,
    )
    assert changed.status_code == 200

    doses = list_doses(client, headers, profile_id)
    still_there = next(entry for entry in doses if entry["id"] == taken["id"])
    assert still_there["status"] == "taken"
    assert at_utc(still_there["scheduled_for"]) == "08:00"

    future = [entry for entry in doses if entry["id"] != taken["id"]]
    assert {at_utc(entry["scheduled_for"]) for entry in future} == {"19:00"}


def test_deleting_a_schedule_keeps_what_was_already_recorded(
    client, account, medication, clock
):
    headers, profile_id = account
    created = make_schedule(client, headers, profile_id, medication)
    schedule_id = created.json()["id"]

    clock.now = datetime(2026, 9, 14, 8, 30, tzinfo=UTC)
    taken = take_first_dose(client, headers, profile_id)

    assert (
        client.delete(
            f"{schedules_url(profile_id)}/{schedule_id}", headers=headers
        ).status_code
        == 204
    )

    doses = list_doses(client, headers, profile_id)
    assert [entry["id"] for entry in doses] == [taken["id"]]
    kept = doses[0]
    assert kept["status"] == "taken"
    # The schedule is gone; the dose is not orphaned, it is simply unattached.
    assert kept["schedule_id"] is None


def test_pausing_stops_future_doses_and_resuming_brings_them_back(
    client, account, medication, clock
):
    headers, profile_id = account
    created = make_schedule(client, headers, profile_id, medication)
    schedule_id = created.json()["id"]
    assert len(list_doses(client, headers, profile_id)) > 0

    paused = client.post(
        f"{schedules_url(profile_id)}/{schedule_id}/pause",
        json={"paused": True},
        headers=headers,
    )
    assert paused.status_code == 200
    assert paused.json()["is_active"] is False
    assert paused.json()["paused_at"] is not None
    assert list_doses(client, headers, profile_id) == []

    resumed = client.post(
        f"{schedules_url(profile_id)}/{schedule_id}/pause",
        json={"paused": False},
        headers=headers,
    )
    assert resumed.json()["is_active"] is True
    assert resumed.json()["paused_at"] is None
    assert len(list_doses(client, headers, profile_id)) > 0


# --- the three actions ------------------------------------------------------


def test_taken_is_idempotent(client, account, medication, clock):
    headers, profile_id = account
    make_schedule(client, headers, profile_id, medication)
    dose_id = list_doses(client, headers, profile_id)[0]["id"]

    first = client.post(
        f"{doses_url(profile_id)}/{dose_id}/taken", json={}, headers=headers
    )
    assert first.status_code == 200
    assert first.json()["applied"] is True

    second = client.post(
        f"{doses_url(profile_id)}/{dose_id}/taken", json={}, headers=headers
    )
    assert second.status_code == 200
    assert second.json()["applied"] is False
    assert second.json()["dose"]["action_at"] == first.json()["dose"]["action_at"]

    taken = [
        entry
        for entry in list_doses(client, headers, profile_id)
        if entry["status"] == "taken"
    ]
    assert len(taken) == 1


def test_a_late_taken_dose_stays_one_dose(client, account, medication, clock):
    headers, profile_id = account
    make_schedule(client, headers, profile_id, medication)
    first = list_doses(client, headers, profile_id)[0]
    dose_id, moment = first["id"], first["scheduled_for"]

    # Long past the grace period: the dose has already become missed.
    clock.now = datetime(2026, 9, 14, 17, 0, tzinfo=UTC)
    listed = list_doses(client, headers, profile_id)
    assert next(e for e in listed if e["id"] == dose_id)["status"] == "missed"

    response = client.post(
        f"{doses_url(profile_id)}/{dose_id}/taken", json={}, headers=headers
    )
    assert response.status_code == 200
    dose = response.json()["dose"]
    assert dose["status"] == "taken"
    assert dose["late"] is True

    # The same row, and no second dose for that moment. (The window itself is
    # one longer, because the clock moved a day and the rolling horizon moved
    # with it -- that is generation working, not a duplicate.)
    assert dose["id"] == dose_id
    for_that_moment = [
        entry
        for entry in list_doses(client, headers, profile_id)
        if entry["scheduled_for"] == moment
    ]
    assert len(for_that_moment) == 1


def test_skip_stores_the_reason(client, account, medication, clock):
    headers, profile_id = account
    make_schedule(client, headers, profile_id, medication)
    dose_id = list_doses(client, headers, profile_id)[0]["id"]

    response = client.post(
        f"{doses_url(profile_id)}/{dose_id}/skip",
        json={"reason_code": "feeling_unwell", "reason_text": "Upset stomach"},
        headers=headers,
    )
    assert response.status_code == 200
    dose = response.json()["dose"]
    assert dose["status"] == "skipped"
    assert dose["skip_reason_code"] == "feeling_unwell"
    assert dose["skip_reason_text"] == "Upset stomach"


def test_skip_without_a_reason_is_recorded_as_no_reason(
    client, account, medication, clock
):
    headers, profile_id = account
    make_schedule(client, headers, profile_id, medication)
    dose_id = list_doses(client, headers, profile_id)[0]["id"]

    response = client.post(
        f"{doses_url(profile_id)}/{dose_id}/skip", json={}, headers=headers
    )
    assert response.json()["dose"]["skip_reason_code"] == "none"
    assert response.json()["dose"]["skip_reason_text"] is None


def test_an_unknown_skip_reason_is_refused(client, account, medication, clock):
    headers, profile_id = account
    make_schedule(client, headers, profile_id, medication)
    dose_id = list_doses(client, headers, profile_id)[0]["id"]

    response = client.post(
        f"{doses_url(profile_id)}/{dose_id}/skip",
        json={"reason_code": "doctor_said_to_double_it"},
        headers=headers,
    )
    assert response.status_code == 422


def test_snooze_moves_the_reminder_and_leaves_the_dose_incomplete(
    client, account, medication, clock
):
    headers, profile_id = account
    make_schedule(client, headers, profile_id, medication)
    dose_id = list_doses(client, headers, profile_id)[0]["id"]

    clock.now = datetime(2026, 9, 14, 8, 5, tzinfo=UTC)
    response = client.post(
        f"{doses_url(profile_id)}/{dose_id}/snooze",
        json={"minutes": 30},
        headers=headers,
    )
    assert response.status_code == 200
    dose = response.json()["dose"]
    assert dose["status"] == "snoozed"
    assert dose["snooze_count"] == 1
    assert at_utc(dose["snoozed_until"]) == "08:35"
    assert on_utc(dose["snoozed_until"]) == "2026-09-14"
    # Still unrecorded: nothing has been said about whether it was taken.
    assert dose["action_at"] is None


def test_snoozing_is_capped(client, account, medication, clock):
    headers, profile_id = account
    make_schedule(client, headers, profile_id, medication)
    dose_id = list_doses(client, headers, profile_id)[0]["id"]
    url = f"{doses_url(profile_id)}/{dose_id}/snooze"

    clock.now = datetime(2026, 9, 14, 8, 5, tzinfo=UTC)
    for _ in range(dose_service.MAX_SNOOZES):
        assert client.post(url, json={"minutes": 10}, headers=headers).status_code == 200

    refused = client.post(url, json={"minutes": 10}, headers=headers)
    assert refused.status_code == 409
    assert refused.json()["detail"]["code"] == "snooze_limit_reached"

    # Taken and Skip are still available, which is the point of a cap rather
    # than a lockout (PRD 5, section 18).
    taken = client.post(
        f"{doses_url(profile_id)}/{dose_id}/taken", json={}, headers=headers
    )
    assert taken.status_code == 200
    assert taken.json()["dose"]["status"] == "taken"


def test_an_unsupported_snooze_duration_is_refused(client, account, medication, clock):
    headers, profile_id = account
    make_schedule(client, headers, profile_id, medication)
    dose_id = list_doses(client, headers, profile_id)[0]["id"]

    response = client.post(
        f"{doses_url(profile_id)}/{dose_id}/snooze",
        json={"minutes": 5},
        headers=headers,
    )
    assert response.status_code == 422


def test_snoozing_a_recorded_dose_is_refused(client, account, medication, clock):
    headers, profile_id = account
    make_schedule(client, headers, profile_id, medication)
    dose_id = list_doses(client, headers, profile_id)[0]["id"]
    client.post(f"{doses_url(profile_id)}/{dose_id}/taken", json={}, headers=headers)

    response = client.post(
        f"{doses_url(profile_id)}/{dose_id}/snooze",
        json={"minutes": 10},
        headers=headers,
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "dose_not_actionable"


# --- missed -----------------------------------------------------------------


def test_an_unrecorded_dose_becomes_missed_after_the_grace_period(
    client, account, medication, clock
):
    headers, profile_id = account
    make_schedule(client, headers, profile_id, medication)
    dose_id = list_doses(client, headers, profile_id)[0]["id"]

    # An hour late is not missed. The grace period is deliberately generous.
    clock.now = datetime(2026, 9, 14, 9, 0, tzinfo=UTC)
    listed = list_doses(client, headers, profile_id)
    assert next(e for e in listed if e["id"] == dose_id)["status"] == "scheduled"
    assert next(e for e in listed if e["id"] == dose_id)["window"] == "due"

    clock.now = datetime(2026, 9, 14, 10, 30, tzinfo=UTC)
    listed = list_doses(client, headers, profile_id)
    entry = next(e for e in listed if e["id"] == dose_id)
    assert entry["status"] == "missed"
    assert entry["window"] == "overdue"


def test_a_snoozed_dose_is_measured_from_its_snooze(client, account, medication, clock):
    headers, profile_id = account
    make_schedule(client, headers, profile_id, medication)
    dose_id = list_doses(client, headers, profile_id)[0]["id"]

    clock.now = datetime(2026, 9, 14, 8, 5, tzinfo=UTC)
    client.post(
        f"{doses_url(profile_id)}/{dose_id}/snooze",
        json={"minutes": 60},
        headers=headers,
    )

    # 10:30 is past the original 08:00 plus grace, but not past 09:05 plus
    # grace -- so snoozing genuinely bought an hour.
    clock.now = datetime(2026, 9, 14, 10, 30, tzinfo=UTC)
    listed = list_doses(client, headers, profile_id)
    assert next(e for e in listed if e["id"] == dose_id)["status"] == "snoozed"

    clock.now = datetime(2026, 9, 14, 11, 30, tzinfo=UTC)
    listed = list_doses(client, headers, profile_id)
    assert next(e for e in listed if e["id"] == dose_id)["status"] == "missed"


# --- offline conflict resolution --------------------------------------------


def test_a_stale_queued_action_does_not_overwrite_a_newer_one(
    client, account, medication, clock
):
    """The most recent explicit user action wins (PRD 5, section 63)."""
    headers, profile_id = account
    make_schedule(client, headers, profile_id, medication)
    dose_id = list_doses(client, headers, profile_id)[0]["id"]

    clock.now = datetime(2026, 9, 14, 12, 0, tzinfo=UTC)
    current = client.post(
        f"{doses_url(profile_id)}/{dose_id}/skip",
        json={"reason_code": "ran_out", "action_at": "2026-09-14T11:00:00Z"},
        headers=headers,
    )
    assert current.json()["applied"] is True

    # A Taken the user pressed two hours earlier, offline, arriving now.
    stale = client.post(
        f"{doses_url(profile_id)}/{dose_id}/taken",
        json={"action_at": "2026-09-14T09:00:00Z"},
        headers=headers,
    )
    assert stale.status_code == 200
    assert stale.json()["applied"] is False
    assert stale.json()["dose"]["status"] == "skipped"


def test_a_queued_action_newer_than_the_stored_one_is_applied(
    client, account, medication, clock
):
    headers, profile_id = account
    make_schedule(client, headers, profile_id, medication)
    dose_id = list_doses(client, headers, profile_id)[0]["id"]

    clock.now = datetime(2026, 9, 14, 12, 0, tzinfo=UTC)
    client.post(
        f"{doses_url(profile_id)}/{dose_id}/skip",
        json={"action_at": "2026-09-14T09:00:00Z"},
        headers=headers,
    )
    later = client.post(
        f"{doses_url(profile_id)}/{dose_id}/taken",
        json={"action_at": "2026-09-14T11:00:00Z"},
        headers=headers,
    )
    assert later.json()["applied"] is True
    assert later.json()["dose"]["status"] == "taken"


# --- adherence --------------------------------------------------------------


def adherence(client, headers, profile_id: str, **params) -> dict:
    response = client.get(
        f"/api/v1/profiles/{profile_id}/medication-adherence",
        params=params,
        headers=headers,
    )
    assert response.status_code == 200, response.json()
    return response.json()


def test_adherence_counts_taken_skipped_and_missed(client, account, medication, clock):
    headers, profile_id = account
    make_schedule(client, headers, profile_id, medication)

    # Day 1: taken. Day 2: skipped. Day 3: nothing, so missed.
    clock.now = datetime(2026, 9, 14, 8, 30, tzinfo=UTC)
    take_first_dose(client, headers, profile_id)

    clock.now = datetime(2026, 9, 15, 8, 30, tzinfo=UTC)
    doses = list_doses(client, headers, profile_id)
    pending = next(e for e in doses if e["local_date"] == "2026-09-15")
    client.post(f"{doses_url(profile_id)}/{pending['id']}/skip", json={}, headers=headers)

    clock.now = datetime(2026, 9, 16, 23, 0, tzinfo=UTC)
    result = adherence(client, headers, profile_id, days=7, to_date="2026-09-16")
    assert result["taken"] == 1
    assert result["skipped"] == 1
    assert result["missed"] == 1
    assert result["total"] == 3
    assert result["percent"] == 33


def test_adherence_is_null_when_nothing_was_due(client, account, clock):
    headers, profile_id = account
    result = adherence(client, headers, profile_id)
    assert result["total"] == 0
    assert result["percent"] is None


def test_future_doses_do_not_drag_adherence_down(client, account, medication, clock):
    headers, profile_id = account
    make_schedule(client, headers, profile_id, medication)

    clock.now = datetime(2026, 9, 14, 8, 30, tzinfo=UTC)
    take_first_dose(client, headers, profile_id)

    result = adherence(client, headers, profile_id, days=7, to_date="2026-09-14")
    assert result["total"] == 1
    assert result["percent"] == 100


# --- supply and refills -----------------------------------------------------


def enable_supply(client, headers, profile_id, medication_id, **body) -> dict:
    response = client.patch(
        f"{supply_url(profile_id)}/{medication_id}",
        json={"tracking_enabled": True, **body},
        headers=headers,
    )
    assert response.status_code == 200, response.json()
    return response.json()


def test_supply_decrements_only_when_a_dose_is_taken(client, account, medication, clock):
    headers, profile_id = account
    enable_supply(
        client,
        headers,
        profile_id,
        medication,
        remaining_doses=10,
        refill_threshold_doses=2,
    )
    make_schedule(client, headers, profile_id, medication)
    doses = list_doses(client, headers, profile_id)

    taken = client.post(
        f"{doses_url(profile_id)}/{doses[0]['id']}/taken", json={}, headers=headers
    )
    assert taken.json()["supply_remaining"] == 9

    client.post(
        f"{doses_url(profile_id)}/{doses[1]['id']}/skip", json={}, headers=headers
    )
    client.post(
        f"{doses_url(profile_id)}/{doses[2]['id']}/snooze",
        json={"minutes": 10},
        headers=headers,
    )

    current = client.get(supply_url(profile_id), headers=headers).json()[0]
    assert current["remaining_doses"] == 9


def test_a_repeated_taken_does_not_decrement_twice(client, account, medication, clock):
    headers, profile_id = account
    enable_supply(client, headers, profile_id, medication, remaining_doses=5)
    make_schedule(client, headers, profile_id, medication)
    dose_id = list_doses(client, headers, profile_id)[0]["id"]

    url = f"{doses_url(profile_id)}/{dose_id}/taken"
    client.post(url, json={}, headers=headers)
    client.post(url, json={}, headers=headers)

    assert (
        client.get(supply_url(profile_id), headers=headers).json()[0]["remaining_doses"]
        == 4
    )


def test_correcting_a_taken_dose_to_skipped_puts_one_back(
    client, account, medication, clock
):
    headers, profile_id = account
    enable_supply(client, headers, profile_id, medication, remaining_doses=5)
    make_schedule(client, headers, profile_id, medication)
    dose_id = list_doses(client, headers, profile_id)[0]["id"]

    client.post(f"{doses_url(profile_id)}/{dose_id}/taken", json={}, headers=headers)
    client.post(f"{doses_url(profile_id)}/{dose_id}/skip", json={}, headers=headers)

    assert (
        client.get(supply_url(profile_id), headers=headers).json()[0]["remaining_doses"]
        == 5
    )


def test_supply_never_goes_negative(client, account, medication, clock):
    headers, profile_id = account
    enable_supply(client, headers, profile_id, medication, remaining_doses=1)
    make_schedule(client, headers, profile_id, medication)
    doses = list_doses(client, headers, profile_id)

    for entry in doses[:3]:
        client.post(
            f"{doses_url(profile_id)}/{entry['id']}/taken", json={}, headers=headers
        )

    assert (
        client.get(supply_url(profile_id), headers=headers).json()[0]["remaining_doses"]
        == 0
    )


def test_low_supply_is_reported_at_the_threshold(client, account, medication, clock):
    headers, profile_id = account
    record = enable_supply(
        client,
        headers,
        profile_id,
        medication,
        remaining_doses=3,
        refill_threshold_doses=2,
    )
    assert record["low"] is False

    make_schedule(client, headers, profile_id, medication)
    doses = list_doses(client, headers, profile_id)
    client.post(
        f"{doses_url(profile_id)}/{doses[0]['id']}/taken", json={}, headers=headers
    )
    second = client.post(
        f"{doses_url(profile_id)}/{doses[1]['id']}/taken", json={}, headers=headers
    )
    assert second.json()["supply_remaining"] == 1
    assert second.json()["low_supply"] is True


def test_supply_without_a_threshold_never_warns(client, account, medication, clock):
    headers, profile_id = account
    enable_supply(client, headers, profile_id, medication, remaining_doses=0)
    assert client.get(supply_url(profile_id), headers=headers).json()[0]["low"] is False


def test_a_refill_replaces_the_count(client, account, medication, clock):
    headers, profile_id = account
    enable_supply(client, headers, profile_id, medication, remaining_doses=2)

    response = client.post(
        f"{supply_url(profile_id)}/{medication}/refill",
        json={"remaining_doses": 30, "refilled_on": "2026-09-13"},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["remaining_doses"] == 30
    assert response.json()["last_refill_date"] == "2026-09-13"


def test_supply_can_be_corrected_by_hand(client, account, medication, clock):
    headers, profile_id = account
    enable_supply(client, headers, profile_id, medication, remaining_doses=10)
    corrected = client.patch(
        f"{supply_url(profile_id)}/{medication}",
        json={"remaining_doses": 7},
        headers=headers,
    )
    assert corrected.json()["remaining_doses"] == 7
    # Tracking was not mentioned, so it is left alone.
    assert corrected.json()["tracking_enabled"] is True


def test_a_negative_supply_is_refused(client, account, medication, clock):
    headers, profile_id = account
    response = client.patch(
        f"{supply_url(profile_id)}/{medication}",
        json={"remaining_doses": -1},
        headers=headers,
    )
    assert response.status_code == 422


# --- the PRD 4 medication record, once it has a schedule --------------------


def test_marking_a_medication_inactive_stops_future_scheduling(
    client, account, medication, clock
):
    headers, profile_id = account
    created = make_schedule(client, headers, profile_id, medication)
    schedule_id = created.json()["id"]
    assert len(list_doses(client, headers, profile_id)) > 0

    response = client.patch(
        f"/api/v1/profiles/{profile_id}/medications/{medication}",
        json={"is_active": False},
        headers=headers,
    )
    assert response.status_code == 200

    assert list_doses(client, headers, profile_id) == []
    schedule = client.get(
        f"{schedules_url(profile_id)}/{schedule_id}", headers=headers
    ).json()
    # Paused, not deleted: turning the medication back on restores it.
    assert schedule["is_active"] is False


def test_a_medication_with_dose_history_cannot_be_deleted(
    client, account, medication, clock
):
    headers, profile_id = account
    make_schedule(client, headers, profile_id, medication)
    clock.now = datetime(2026, 9, 14, 8, 30, tzinfo=UTC)
    take_first_dose(client, headers, profile_id)

    response = client.delete(
        f"/api/v1/profiles/{profile_id}/medications/{medication}", headers=headers
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "medication_has_history"
    # And the history is still there.
    assert len(list_doses(client, headers, profile_id)) > 0


def test_a_medication_with_no_history_still_deletes(client, account, medication, clock):
    headers, profile_id = account
    make_schedule(client, headers, profile_id, medication)
    response = client.delete(
        f"/api/v1/profiles/{profile_id}/medications/{medication}", headers=headers
    )
    assert response.status_code == 204


# --- the future robot hook (simulated, PRD 5 sections 45-47) ----------------


def test_a_linked_device_can_confirm_a_dose(client, db, account, medication, clock):
    headers, profile_id = account
    token = seed_device(
        db, client, headers, profile_id=profile_id, hardware_id="NURA-3C84279A1B2C"
    )
    make_schedule(client, headers, profile_id, medication)
    dose_id = list_doses(client, headers, profile_id)[0]["id"]

    response = client.post(
        f"/api/v1/device-actions/medication-doses/{dose_id}/taken",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200, response.json()
    assert response.json() == {"dose_id": dose_id, "status": "taken", "applied": True}

    # The app sees it, and sees where it came from.
    stored = next(
        entry
        for entry in list_doses(client, headers, profile_id)
        if entry["id"] == dose_id
    )
    assert stored["source"] == "robot_voice"
    # Nothing about the medication went back to the device.
    assert set(response.json()) == {"dose_id", "status", "applied"}


def test_a_robot_confirmation_never_overrides_the_person(
    client, db, account, medication, clock
):
    """App marks Taken, robot says so later: one Taken, no error (PRD 5, s49)."""
    headers, profile_id = account
    token = seed_device(
        db, client, headers, profile_id=profile_id, hardware_id="NURA-3C84279A1B2C"
    )
    make_schedule(client, headers, profile_id, medication)
    dose_id = list_doses(client, headers, profile_id)[0]["id"]

    client.post(f"{doses_url(profile_id)}/{dose_id}/skip", json={}, headers=headers)

    response = client.post(
        f"/api/v1/device-actions/medication-doses/{dose_id}/taken",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["applied"] is False
    assert response.json()["status"] == "skipped"


def test_a_device_cannot_touch_another_profiles_dose(
    client, db, make_token, account, medication, clock
):
    headers, profile_id = account
    make_schedule(client, headers, profile_id, medication)
    dose_id = list_doses(client, headers, profile_id)[0]["id"]

    other_headers = ready_account(client, make_token)
    other_profile = client.get("/api/v1/me", headers=other_headers).json()["profiles"][0][
        "id"
    ]
    other_token = seed_device(
        db,
        client,
        other_headers,
        profile_id=other_profile,
        hardware_id="NURA-AABBCCDDEEFF",
    )

    response = client.post(
        f"/api/v1/device-actions/medication-doses/{dose_id}/taken",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert response.status_code == 404


def test_a_device_not_set_up_for_anybody_cannot_act(
    client, db, account, medication, clock
):
    headers, profile_id = account
    token = seed_device(
        db, client, headers, profile_id=None, hardware_id="NURA-3C84279A1B2C"
    )
    make_schedule(client, headers, profile_id, medication)
    dose_id = list_doses(client, headers, profile_id)[0]["id"]

    response = client.post(
        f"/api/v1/device-actions/medication-doses/{dose_id}/taken",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404


def test_a_user_token_cannot_call_the_device_route(client, account, medication, clock):
    headers, profile_id = account
    make_schedule(client, headers, profile_id, medication)
    dose_id = list_doses(client, headers, profile_id)[0]["id"]

    response = client.post(
        f"/api/v1/device-actions/medication-doses/{dose_id}/taken", headers=headers
    )
    assert response.status_code == 401


def test_the_device_route_needs_a_token(client, account, medication, clock):
    headers, profile_id = account
    make_schedule(client, headers, profile_id, medication)
    dose_id = list_doses(client, headers, profile_id)[0]["id"]
    assert (
        client.post(
            f"/api/v1/device-actions/medication-doses/{dose_id}/taken"
        ).status_code
        == 401
    )


# --- authorization ----------------------------------------------------------


@pytest.fixture
def stranger(client, make_token) -> dict[str, str]:
    """A second, unrelated account."""
    return ready_account(client, make_token)


def test_another_account_cannot_reach_these_schedules(
    client, account, medication, stranger, clock
):
    headers, profile_id = account
    created = make_schedule(client, headers, profile_id, medication)
    schedule_id = created.json()["id"]
    url = f"{schedules_url(profile_id)}/{schedule_id}"

    assert client.get(schedules_url(profile_id), headers=stranger).status_code == 404
    assert client.get(url, headers=stranger).status_code == 404
    assert client.patch(url, json={}, headers=stranger).status_code == 404
    assert client.delete(url, headers=stranger).status_code == 404
    assert (
        client.post(f"{url}/pause", json={"paused": True}, headers=stranger).status_code
        == 404
    )
    # Including POST, so a stranger cannot even add to somebody else's profile.
    assert make_schedule(client, stranger, profile_id, medication).status_code == 404


def test_another_account_cannot_act_on_a_dose(
    client, account, medication, stranger, clock
):
    headers, profile_id = account
    make_schedule(client, headers, profile_id, medication)
    dose_id = list_doses(client, headers, profile_id)[0]["id"]

    for action in ("taken", "snooze", "skip"):
        response = client.post(
            f"{doses_url(profile_id)}/{dose_id}/{action}", json={}, headers=stranger
        )
        assert response.status_code == 404, action
    assert client.get(doses_url(profile_id), headers=stranger).status_code == 404


def test_another_account_cannot_read_or_change_supply(
    client, account, medication, stranger, clock
):
    headers, profile_id = account
    enable_supply(client, headers, profile_id, medication, remaining_doses=10)

    assert client.get(supply_url(profile_id), headers=stranger).status_code == 404
    assert (
        client.patch(
            f"{supply_url(profile_id)}/{medication}",
            json={"remaining_doses": 0},
            headers=stranger,
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"{supply_url(profile_id)}/{medication}/refill",
            json={"remaining_doses": 99},
            headers=stranger,
        ).status_code
        == 404
    )


def test_an_unknown_dose_is_not_found(client, account, clock):
    headers, profile_id = account
    response = client.post(
        f"{doses_url(profile_id)}/{uuid.uuid4()}/taken", json={}, headers=headers
    )
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "dose_not_found"


def test_medication_routes_need_authentication(client, account, clock):
    _, profile_id = account
    assert client.get(schedules_url(profile_id)).status_code == 401
    assert client.get(doses_url(profile_id)).status_code == 401
    assert client.get(supply_url(profile_id)).status_code == 401
    assert (
        client.get(f"/api/v1/profiles/{profile_id}/medication-adherence").status_code
        == 401
    )


# --- Today ------------------------------------------------------------------


def today(client, headers, on_date: str = "2026-09-13") -> dict:
    response = client.get(
        "/api/v1/today", params={"local_date": on_date}, headers=headers
    )
    assert response.status_code == 200, response.json()
    return response.json()


def test_today_reports_no_medications_for_someone_with_no_schedules(
    client, account, clock
):
    headers, _ = account
    block = today(client, headers)["medications"]
    assert block["has_schedules"] is False
    assert block["next_due"] is None
    assert block["due_today_count"] == 0
    assert today(client, headers)["important"] == []


def test_today_reports_the_next_dose(client, account, medication, clock):
    headers, profile_id = account
    make_schedule(
        client,
        headers,
        profile_id,
        medication,
        times=[{"time_of_day": "08:00:00"}, {"time_of_day": "20:00:00"}],
    )

    block = today(client, headers)["medications"]
    assert block["has_schedules"] is True
    assert block["next_due"]["medication_name"] == "Metformin"
    assert block["next_due"]["medication_dose"] == "500 mg"
    assert at_utc(block["next_due"]["scheduled_for"]) == "20:00"
    assert on_utc(block["next_due"]["scheduled_for"]) == "2026-09-13"
    # 08:00 today was already past when the schedule was made, so only 20:00
    # exists for today.
    assert block["due_today_count"] == 1
    assert block["remaining_today_count"] == 1
    assert block["overdue_count"] == 0


def test_today_puts_an_overdue_dose_in_important_today(
    client, account, medication, clock
):
    headers, profile_id = account
    make_schedule(client, headers, profile_id, medication)

    clock.now = datetime(2026, 9, 14, 11, 0, tzinfo=UTC)
    payload = today(client, headers, "2026-09-14")
    assert payload["medications"]["overdue_count"] == 1

    items = payload["important"]
    assert items[0]["type"] == "medication_dose"
    assert items[0]["title"] == "Metformin — 500 mg"
    assert items[0]["priority"] == "important"
    # Neutral wording, and nothing that reads as an emergency.
    assert items[0]["subtitle"] == "Not marked as taken"


def test_important_today_puts_overdue_before_upcoming(client, account, medication, clock):
    headers, profile_id = account
    second = add_medication(client, headers, profile_id, name="Ramipril", dose="5 mg")
    make_schedule(client, headers, profile_id, medication)
    make_schedule(
        client,
        headers,
        profile_id,
        second,
        times=[{"time_of_day": "21:00:00"}],
    )

    clock.now = datetime(2026, 9, 14, 11, 0, tzinfo=UTC)
    items = today(client, headers, "2026-09-14")["important"]

    # Three things are waiting: this morning's Metformin, last night's
    # Ramipril -- both past their grace period -- and tonight's Ramipril.
    # Overdue sorts first, oldest first within that, and the upcoming one
    # last (PRD 5, section 29).
    assert [item["priority"] for item in items] == ["important", "important", "normal"]
    assert items[0]["title"].startswith("Ramipril")  # last night, the oldest
    assert items[1]["title"].startswith("Metformin")  # this morning
    assert items[2]["title"].startswith("Ramipril")  # tonight, not yet due


def test_today_reports_low_supply(client, account, medication, clock):
    headers, profile_id = account
    enable_supply(
        client,
        headers,
        profile_id,
        medication,
        remaining_doses=2,
        refill_threshold_doses=5,
    )
    make_schedule(client, headers, profile_id, medication)

    low = today(client, headers)["medications"]["low_supply"]
    assert low == [
        {
            "medication_id": medication,
            "medication_name": "Metformin",
            "remaining_doses": 2,
        }
    ]


def test_the_medications_card_is_offered(client, account, clock):
    headers, _ = account
    cards = {
        card["key"]: card
        for card in client.get("/api/v1/dashboard-preferences", headers=headers).json()[
            "cards"
        ]
    }
    assert cards["medications"]["available"] is True
    assert cards["medications"]["visible"] is True


def test_today_still_works_for_an_account_with_no_profile(client, auth_headers, clock):
    response = client.get("/api/v1/today", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["medications"] is None
    assert response.json()["important"] == []


# --- history ----------------------------------------------------------------


def test_history_covers_a_range_of_local_days(client, account, medication, clock):
    headers, profile_id = account
    make_schedule(client, headers, profile_id, medication)

    clock.now = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)
    response = client.get(
        doses_url(profile_id),
        params={"from_date": "2026-09-14", "to_date": "2026-09-16"},
        headers=headers,
    )
    assert response.status_code == 200
    days = [entry["local_date"] for entry in response.json()]
    assert days == ["2026-09-14", "2026-09-15", "2026-09-16"]


def test_history_can_be_filtered_to_one_medication(client, account, medication, clock):
    headers, profile_id = account
    second = add_medication(client, headers, profile_id, name="Ramipril", dose="5 mg")
    make_schedule(client, headers, profile_id, medication)
    make_schedule(
        client, headers, profile_id, second, times=[{"time_of_day": "21:00:00"}]
    )

    response = client.get(
        doses_url(profile_id),
        params={
            "from_date": TODAY.isoformat(),
            "to_date": (TODAY + timedelta(days=3)).isoformat(),
            "medication_id": second,
        },
        headers=headers,
    )
    assert {entry["medication_name"] for entry in response.json()} == {"Ramipril"}


def test_todays_doses_are_returned_for_the_clients_own_day(
    client, account, medication, clock
):
    headers, profile_id = account
    make_schedule(
        client,
        headers,
        profile_id,
        medication,
        times=[{"time_of_day": "08:00:00"}, {"time_of_day": "20:00:00"}],
    )

    response = client.get(
        f"{doses_url(profile_id)}/today",
        params={"local_date": "2026-09-14"},
        headers=headers,
    )
    assert response.status_code == 200
    assert {entry["local_date"] for entry in response.json()} == {"2026-09-14"}
    assert len(response.json()) == 2
