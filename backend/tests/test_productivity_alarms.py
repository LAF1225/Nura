"""Alarms, and the one thing an alarm in this build cannot claim.

PRD 12, sections 10, 11, 54, 71 and 83.

The group that matters most is ``TestAlarmHonesty``. Section 11 says not to
claim clock-app reliability that has not been verified, and the position in
this build is further back than that: **the app has never been run on a
physical phone**, so no notification has fired, no alarm has fired and no
vibration has been felt. The limitation sentence is part of the list response
rather than a string in the app, and there is a test here that would fail if a
future change dropped it.
"""

import uuid
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.api.deps import current_time
from app.main import app
from tests.test_devices import ready_account
from tests.test_today import Clock

TODAY = date(2026, 9, 13)
NOON = datetime(2026, 9, 13, 12, 0, tzinfo=UTC)


@pytest.fixture
def clock(client) -> Clock:
    fake = Clock()
    fake.now = NOON
    app.dependency_overrides[current_time] = lambda: fake.now
    return fake


@pytest.fixture
def account(client, make_token) -> tuple[dict[str, str], str]:
    headers = ready_account(client, make_token)
    profile_id = client.get("/api/v1/me", headers=headers).json()["profiles"][0]["id"]
    return headers, profile_id


def alarms_url(profile_id: str) -> str:
    return f"/api/v1/profiles/{profile_id}/alarms"


def create_alarm(client, headers, profile_id, **fields) -> dict:
    body = {
        "label": "Wake up",
        "time_of_day": "07:00",
        "recurrence": "one_time",
        "on_date": (TODAY + timedelta(days=1)).isoformat(),
        **fields,
    }
    response = client.post(alarms_url(profile_id), json=body, headers=headers)
    assert response.status_code in (200, 201), response.json()
    return response.json()


class TestAlarmCrud:
    def test_a_one_off_alarm_knows_when_it_next_goes_off(self, client, account, clock):
        headers, profile_id = account
        alarm = create_alarm(client, headers, profile_id)["alarm"]
        assert alarm["recurrence"] == "one_time"
        assert alarm["enabled"] is True
        assert alarm["sound_key"] == "default"
        assert alarm["sound_label"] == "Default"
        assert alarm["next_fire_at"] is not None
        assert alarm["schedule_label"] == "14 September 2026 at 7:00 AM"

    def test_a_repeating_alarm_names_its_days(self, client, account, clock):
        headers, profile_id = account
        alarm = create_alarm(
            client,
            headers,
            profile_id,
            recurrence="selected_days",
            weekdays=[0, 1, 2, 3, 4],
            on_date=None,
        )["alarm"]
        assert alarm["schedule_label"] == "Weekdays at 7:00 AM"
        assert alarm["weekdays"] == [0, 1, 2, 3, 4]

    def test_a_one_off_alarm_needs_a_date(self, client, account, clock):
        headers, profile_id = account
        response = client.post(
            alarms_url(profile_id),
            json={"label": "Wake up", "time_of_day": "07:00", "recurrence": "one_time"},
            headers=headers,
        )
        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "invalid_alarm"

    def test_a_repeating_alarm_does_not_take_a_date(self, client, account, clock):
        headers, profile_id = account
        response = client.post(
            alarms_url(profile_id),
            json={
                "label": "Wake up",
                "time_of_day": "07:00",
                "recurrence": "daily",
                "on_date": TODAY.isoformat(),
            },
            headers=headers,
        )
        assert response.status_code == 422

    def test_selected_days_needs_days(self, client, account, clock):
        headers, profile_id = account
        response = client.post(
            alarms_url(profile_id),
            json={
                "label": "Wake up",
                "time_of_day": "07:00",
                "recurrence": "selected_days",
            },
            headers=headers,
        )
        assert response.status_code == 422

    def test_a_sound_nura_does_not_have_is_refused(self, client, account, clock):
        headers, profile_id = account
        response = client.post(
            alarms_url(profile_id),
            json={
                "label": "Wake up",
                "time_of_day": "07:00",
                "recurrence": "daily",
                "sound_key": "airhorn",
            },
            headers=headers,
        )
        assert response.status_code == 422

    def test_turning_one_off_keeps_it_and_clears_its_next_moment(
        self, client, account, clock
    ):
        """Section 10's switch. Derived on every read, so a disabled alarm
        stops being "next" without anything having to remember to clear it."""
        headers, profile_id = account
        alarm_id = create_alarm(client, headers, profile_id)["alarm"]["id"]
        off = client.patch(
            f"{alarms_url(profile_id)}/{alarm_id}",
            json={"enabled": False},
            headers=headers,
        ).json()
        assert off["enabled"] is False
        assert off["next_fire_at"] is None

        listing = client.get(alarms_url(profile_id), headers=headers).json()
        assert len(listing["alarms"]) == 1
        assert listing["enabled_count"] == 0

    def test_a_one_off_whose_day_has_gone_has_no_next_moment(
        self, client, account, clock
    ):
        headers, profile_id = account
        alarm_id = create_alarm(client, headers, profile_id)["alarm"]["id"]
        clock.advance(days=3)
        alarm = client.get(f"{alarms_url(profile_id)}/{alarm_id}", headers=headers).json()
        assert alarm["next_fire_at"] is None
        assert alarm["enabled"] is True

    def test_a_daily_alarm_keeps_its_local_time_across_a_dst_change(
        self, client, account, clock
    ):
        """Section 35, for an alarm. Seven o'clock stays seven o'clock."""
        headers, profile_id = account
        clock.now = datetime(2026, 3, 27, 12, 0, tzinfo=UTC)
        alarm_id = create_alarm(
            client,
            headers,
            profile_id,
            recurrence="daily",
            timezone="Europe/London",
            on_date=None,
        )["alarm"]["id"]

        london = ZoneInfo("Europe/London")
        for day in (0, 1, 2, 3):
            clock.now = datetime(2026, 3, 27 + day, 12, 0, tzinfo=UTC)
            alarm = client.get(
                f"{alarms_url(profile_id)}/{alarm_id}", headers=headers
            ).json()
            local = datetime.fromisoformat(alarm["next_fire_at"]).astimezone(london)
            assert (local.hour, local.minute) == (7, 0), day

    def test_the_same_client_id_twice_is_one_alarm(self, client, account, clock):
        headers, profile_id = account
        first = create_alarm(client, headers, profile_id, client_alarm_id="a1")
        second = create_alarm(client, headers, profile_id, client_alarm_id="a1")
        assert first["created"] is True
        assert second["created"] is False
        assert second["alarm"]["id"] == first["alarm"]["id"]

    def test_deleting_removes_it(self, client, account, clock):
        headers, profile_id = account
        alarm_id = create_alarm(client, headers, profile_id)["alarm"]["id"]
        assert (
            client.delete(
                f"{alarms_url(profile_id)}/{alarm_id}", headers=headers
            ).status_code
            == 204
        )
        assert (
            client.get(
                f"{alarms_url(profile_id)}/{alarm_id}", headers=headers
            ).status_code
            == 404
        )

    def test_another_account_gets_a_404(self, client, account, make_token, clock):
        headers, profile_id = account
        alarm_id = create_alarm(client, headers, profile_id)["alarm"]["id"]
        stranger = ready_account(client, make_token)
        assert (
            client.get(
                f"{alarms_url(profile_id)}/{alarm_id}", headers=stranger
            ).status_code
            == 404
        )


class TestAlarmHonesty:
    def test_the_list_carries_the_limitation_sentence(self, client, account, clock):
        """**Section 11, and section 71's reality.**

        The sentence is part of the response rather than a string in the app,
        so no client can ship an alarm screen without it. If a future change
        removes it, this fails.
        """
        headers, profile_id = account
        listing = client.get(alarms_url(profile_id), headers=headers).json()
        assert "phone notifications" in listing["limitation"]
        assert "never been run on a physical phone" in listing["limitation"]

    def test_it_is_there_for_an_empty_list_too(self, client, account, clock):
        """Somebody deciding whether to set their first alarm is exactly who
        needs to know what an alarm here can do."""
        headers, profile_id = account
        listing = client.get(alarms_url(profile_id), headers=headers).json()
        assert listing["alarms"] == []
        assert listing["limitation"]

    def test_no_sound_has_ever_been_played(self, client, account, clock):
        """``sound_key`` is a stored choice, not a sound anybody heard.

        Asserted against the vocabulary: the four keys exist so the value means
        the same thing on both platforms and on the robot, and nothing in this
        project has an audio implementation behind any of them.
        """
        from app.models.enums import ALARM_SOUND_KEYS

        assert ALARM_SOUND_KEYS == ("default", "gentle", "chime", "bell")

    def test_alarms_are_available_as_a_capability_and_still_unverified(
        self, client, account, clock
    ):
        """Section 25 and section 11 together, which look contradictory and
        are not.

        ``available`` describes what the feature does: an alarm can be created,
        edited, enabled and scheduled, and all of that is true. Whether the
        operating system wakes anybody is a different question, it has never
        been tested, and it is answered by the sentence beside the switch --
        not by a false ``unavailable`` that would be wrong about the part that
        does work.
        """
        headers, profile_id = account
        capabilities = client.get(
            f"/api/v1/profiles/{profile_id}/assistant/external-capabilities",
            headers=headers,
        ).json()
        by_key = {row["key"]: row for row in capabilities["capabilities"]}
        assert by_key["alarms"]["state"] == "available"

        listing = client.get(alarms_url(profile_id), headers=headers).json()
        assert "not been tested" in listing["limitation"]


class TestUpcomingFires:
    def test_a_weekday_alarm_fires_five_times_a_week(self, db, client, account, clock):
        """What the phone's scheduler mirrors into the operating system.

        Derived rather than stored: an alarm has no occurrence rows at all, for
        the reason a robot's connection status has no column.
        """
        from app.services.productivity import alarms as alarm_service

        headers, profile_id = account
        create_alarm(
            client,
            headers,
            profile_id,
            recurrence="selected_days",
            weekdays=[0, 1, 2, 3, 4],
            on_date=None,
        )
        fires = alarm_service.upcoming_fires(db, uuid.UUID(profile_id), clock.now, days=7)
        assert len(fires) == 5
        assert all(fire.fire_at > clock.now for fire in fires)

    def test_a_disabled_alarm_fires_never(self, db, client, account, clock):
        from app.services.productivity import alarms as alarm_service

        headers, profile_id = account
        alarm_id = create_alarm(
            client, headers, profile_id, recurrence="daily", on_date=None
        )["alarm"]["id"]
        client.patch(
            f"{alarms_url(profile_id)}/{alarm_id}",
            json={"enabled": False},
            headers=headers,
        )
        assert alarm_service.upcoming_fires(db, uuid.UUID(profile_id), clock.now) == []

    def test_the_care_summary_names_the_next_one(self, client, account, clock):
        headers, profile_id = account
        create_alarm(client, headers, profile_id, recurrence="daily", on_date=None)
        summary = client.get(
            f"/api/v1/profiles/{profile_id}/daily-life/summary", headers=headers
        ).json()
        assert summary["alarm_count"] == 1
        assert summary["next_alarm_at"] is not None
        assert summary["has_anything"] is True
