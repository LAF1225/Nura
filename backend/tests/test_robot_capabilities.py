"""What the robot says it can do, and what the app is allowed to conclude.

PRD 11, sections 10, 11, 12, 46, 47, 61, 90, 91, 92, 122 and 124.

Section 124 names six cases and every one of them is a test here. The first is
the one the whole model exists for: **compile support does not imply
available**. The backend has never seen the firmware, cannot know whether a
driver compiled, and therefore has no way to write ``available`` by itself --
and ``not_verified`` is reachable only through a device's own report.

**No hardware is involved.** The "device" reporting here is an authenticated
HTTP request with a device token, which is the contract PRD 11 section 63 asks
to be verified without hardware. No screen, speaker or microphone has ever
reported anything to this backend.
"""

from datetime import timedelta

import pytest

from app.api.deps import current_time
from app.main import app
from app.models import DeviceCapability
from app.models.enums import ROBOT_CAPABILITY_KEYS
from app.services.robot import capabilities as capability_service
from app.services.robot import simulator as sim
from tests.test_devices import ready_account
from tests.test_robot_presentations import NOW, report, seed_device
from tests.test_today import Clock


@pytest.fixture
def clock(client) -> Clock:
    """A settable clock, injected in place of the real one.

    Declared here rather than imported: a fixture is resolved by name in the
    module it is used from, and importing one only works by leaving an
    otherwise-unused name in the namespace (the same note
    ``test_medications.py`` carries).
    """
    fake = Clock()
    fake.now = NOW
    app.dependency_overrides[current_time] = lambda: fake.now
    return fake


@pytest.fixture
def owner(client, make_token) -> tuple[dict[str, str], str]:
    headers = ready_account(client, make_token)
    profile_id = client.get("/api/v1/me", headers=headers).json()["profiles"][0]["id"]
    return headers, profile_id


class TestWhatTheBackendMayConclude:
    def test_nothing_reported_reads_as_not_connected(self, db, client, clock, owner):
        """Section 10's fourth state, and section 12's rule from the other side.

        A robot that has said nothing is not ``unavailable`` -- that would
        claim the part is absent -- and not ``not_verified``, which would claim
        a driver exists. It is *not reported*, which is the only thing the
        backend actually knows.
        """
        headers, profile_id = owner
        device, _ = seed_device(db, client, headers, profile_id=profile_id)
        body = client.get(
            f"/api/v1/devices/{device.id}/capabilities", headers=headers
        ).json()

        assert len(body["capabilities"]) == len(ROBOT_CAPABILITY_KEYS)
        assert {row["state"] for row in body["capabilities"]} == {"not_connected"}
        assert body["display_available"] is False
        assert body["audio_available"] is False
        assert body["input_available"] is False

    def test_every_key_is_returned_even_when_nothing_has_said_anything(
        self, db, client, clock, owner
    ):
        """Section 10 forbids one generic boolean; this is the other half.

        All twelve keys, in their fixed order. A client that only saw the keys
        that happened to be present would silently stop asking about one
        somebody added.
        """
        headers, profile_id = owner
        device, _ = seed_device(db, client, headers, profile_id=profile_id)
        body = client.get(
            f"/api/v1/devices/{device.id}/capabilities", headers=headers
        ).json()
        assert [row["key"] for row in body["capabilities"]] == list(ROBOT_CAPABILITY_KEYS)

    def test_the_backend_never_writes_not_verified_by_itself(self, db):
        """Section 12 and section 91, checked as an absence.

        ``not_verified`` means "the driver is there and nothing has been
        proven", which is a statement about a build. The backend has never seen
        a build. So the only writer is a device report, and a database with no
        reports in it contains no such row.
        """
        assert capability_service.UNREPORTED_STATE == "not_connected"
        rows = db.query(DeviceCapability).filter(DeviceCapability.source == "default")
        assert rows.count() == 0

    def test_the_audio_section_is_not_offered_without_audio(
        self, db, client, clock, owner
    ):
        """Sections 46 and 47: do not present live controls as if they work."""
        headers, profile_id = owner
        device, token = seed_device(db, client, headers, profile_id=profile_id)
        report(client, token, dict(sim.DISPLAY_ONLY))

        body = client.get(
            f"/api/v1/devices/{device.id}/capabilities", headers=headers
        ).json()
        assert body["display_available"] is True
        assert body["text_available"] is True
        assert body["audio_available"] is False
        assert body["speech_available"] is False

    def test_reading_aloud_needs_both_a_speaker_and_speech(
        self, db, client, clock, owner
    ):
        """Sections 25 and 42. A speaker alone cannot say words."""
        headers, profile_id = owner
        device, token = seed_device(db, client, headers, profile_id=profile_id)
        report(
            client,
            token,
            {**sim.DISPLAY_ONLY, "speaker": "available", "audio_playback": "available"},
        )
        body = client.get(
            f"/api/v1/devices/{device.id}/capabilities", headers=headers
        ).json()
        assert body["audio_available"] is True
        assert body["speech_available"] is False

        report(client, token, {"tts": "available"})
        body = client.get(
            f"/api/v1/devices/{device.id}/capabilities", headers=headers
        ).json()
        assert body["speech_available"] is True


class TestReports:
    def test_a_device_report_is_accepted_and_read_back(self, db, client, clock, owner):
        """Section 61, and section 124's "available report accepted"."""
        headers, profile_id = owner
        device, token = seed_device(db, client, headers, profile_id=profile_id)

        response = report(client, token, {"display": "available"})
        assert response.status_code == 200
        assert response.json()["accepted"] == 1
        assert response.json()["capabilities"]["display"] == "available"

    def test_unavailable_is_accepted_too(self, db, client, clock, owner):
        """Section 124's "unavailable report accepted"."""
        headers, profile_id = owner
        device, token = seed_device(db, client, headers, profile_id=profile_id)
        report(client, token, {"camera": "unavailable"})
        body = client.get(
            f"/api/v1/devices/{device.id}/capabilities", headers=headers
        ).json()
        states = {row["key"]: row["state"] for row in body["capabilities"]}
        assert states["camera"] == "unavailable"

    def test_not_verified_persists(self, db, client, clock, owner):
        """Section 124's "not_verified persists", and section 91's point.

        Nothing upgrades it. Not another report about something else, not
        time passing, not the app reading it twice.
        """
        headers, profile_id = owner
        device, token = seed_device(db, client, headers, profile_id=profile_id)
        report(client, token, dict(sim.UNVERIFIED_DISPLAY), source="self_test")

        for _ in range(2):
            body = client.get(
                f"/api/v1/devices/{device.id}/capabilities", headers=headers
            ).json()
            states = {row["key"]: row["state"] for row in body["capabilities"]}
            assert states["display"] == "not_verified"
            assert body["display_available"] is False
            assert body["text_available"] is False

    def test_a_partial_report_erases_nothing(self, db, client, clock, owner):
        """A self-test of one part is not a claim about the others."""
        headers, profile_id = owner
        device, token = seed_device(db, client, headers, profile_id=profile_id)
        report(client, token, dict(sim.DISPLAY_ONLY))
        report(client, token, {"buttons": "available"})

        body = client.get(
            f"/api/v1/devices/{device.id}/capabilities", headers=headers
        ).json()
        states = {row["key"]: row["state"] for row in body["capabilities"]}
        assert states["buttons"] == "available"
        assert states["display"] == "available"

    def test_an_invented_capability_is_refused(self, db, client, clock, owner):
        """A firmware inventing a key is a protocol mismatch, not a row."""
        headers, profile_id = owner
        _, token = seed_device(db, client, headers, profile_id=profile_id)
        assert report(client, token, {"laser": "available"}).status_code == 422
        assert report(client, token, {"display": "probably"}).status_code == 422

    def test_a_device_cannot_report_default_as_a_source(self, db, client, clock, owner):
        """``default`` means "nobody has said", so a device saying it is a
        contradiction. Refused by the schema rather than by a check."""
        headers, profile_id = owner
        _, token = seed_device(db, client, headers, profile_id=profile_id)
        response = report(client, token, {"display": "available"}, source="default")
        assert response.status_code == 422

    def test_a_report_carries_no_profile_or_device_id(self, db, client, clock, owner):
        """Section 69, enforced by the schema having nowhere to put one."""
        headers, profile_id = owner
        _, token = seed_device(db, client, headers, profile_id=profile_id)
        response = report(
            client,
            token,
            {"display": "available"},
            profile_id=profile_id,
        )
        assert response.status_code == 422


class TestStaleReports:
    def test_a_report_from_an_older_firmware_stops_counting_as_proof(
        self, db, client, clock, owner
    ):
        """Section 124's "stale capability report handled".

        The useful definition of stale is not "old": it is "proven by a build
        that is no longer running". A display that passed its self-test two
        versions ago has not been proven by the version running now, so it
        reads as ``not_verified`` until the robot says so again -- and the row
        still records what the device actually said.
        """
        headers, profile_id = owner
        device, token = seed_device(db, client, headers, profile_id=profile_id)
        report(client, token, dict(sim.DISPLAY_ONLY), firmware_version="0.1.0")

        device.firmware_version = "0.2.0"
        db.commit()

        body = client.get(
            f"/api/v1/devices/{device.id}/capabilities", headers=headers
        ).json()
        row = next(r for r in body["capabilities"] if r["key"] == "display")
        assert row["reported_state"] == "available"
        assert row["state"] == "not_verified"
        assert row["stale"] is True
        assert body["display_available"] is False

    def test_a_report_nobody_has_repeated_in_a_month_goes_stale(
        self, db, client, clock, owner
    ):
        """Hardware gets pulled apart on a workbench.

        A screen that worked a month ago is not evidence about today, so the
        state decays to ``not_verified`` rather than staying a promise.
        """
        headers, profile_id = owner
        device, token = seed_device(db, client, headers, profile_id=profile_id)
        report(client, token, dict(sim.DISPLAY_ONLY))

        clock.advance(days=31)
        body = client.get(
            f"/api/v1/devices/{device.id}/capabilities", headers=headers
        ).json()
        row = next(r for r in body["capabilities"] if r["key"] == "display")
        assert row["state"] == "not_verified"
        assert row["stale"] is True

    def test_staleness_never_upgrades_anything(self):
        """``effective_state`` can only move towards less certainty."""
        for state in ("unavailable", "not_verified", "not_connected"):
            resolved, stale = capability_service.effective_state(
                reported_state=state,
                reported_at=NOW - timedelta(days=400),
                reported_firmware="0.0.1",
                device_firmware="9.9.9",
                now=NOW,
            )
            assert resolved == state
            assert stale is True
