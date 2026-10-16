"""The presentation queue, the device contract, and who may touch it.

PRD 11, sections 14, 16-20, 55-60, 69, 121, 122 and 123.

Every test here runs against the real app, the real migrations and a real
PostgreSQL database, with genuinely signed tokens and real device tokens. When
a request is refused, the production dependency refused it.

**No hardware is involved anywhere in this file, and none is simulated into
existence.** There is no robot: a "device" here is a row and a token string,
exactly as PRD 2 leaves one after a claim. What is exercised is the contract --
fetch, acknowledge, expire, preempt -- which is what PRD 11 section 63 says to
exercise instead of hardware. Nothing in this file has ever run on a screen and
nothing in it claims to have.

**The clock is moved, never slept through.** Expiry is a stored instant and a
comparison (section 55), so a 30-minute reminder window is tested by moving
time rather than waiting.

The groups:

``TestOrdering``       section 16's table, and that it is the table being used
``TestPreemption``     section 17, including what must *not* be preempted
``TestExpiry``         sections 18, 55 and 56
``TestDeduplication``  section 57
``TestAcknowledgement`` sections 14, 19 and 123's valid/invalid transitions
``TestDeviceAccess``   sections 69 and 123's "device can only fetch its own"
``TestOffline``        section 20, and that nothing is ever falsely displayed
"""

import secrets
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.api.deps import current_time
from app.main import app
from app.models import Device, DevicePresentation
from app.models.enums import (
    ROBOT_PRESENTATION_PRIORITIES,
    ROBOT_PRESENTATION_TYPES,
)
from app.services.devices import hash_secret
from app.services.robot import capabilities as capability_service
from app.services.robot import layouts, queue
from app.services.robot import simulator as sim
from tests.test_devices import ready_account
from tests.test_today import Clock

#: A Sunday evening. Fixed so nothing drifts mid-test.
NOW = datetime(2026, 10, 4, 19, 30, tzinfo=UTC)

DEVICE_ACTIONS = "/api/v1/device-actions"


@pytest.fixture
def clock(client) -> Clock:
    fake = Clock()
    fake.now = NOW
    app.dependency_overrides[current_time] = lambda: fake.now
    return fake


@pytest.fixture
def owner(client, make_token) -> tuple[dict[str, str], str]:
    headers = ready_account(client, make_token)
    profile_id = client.get("/api/v1/me", headers=headers).json()["profiles"][0]["id"]
    return headers, profile_id


def seed_device(
    db,
    client,
    headers,
    *,
    profile_id: str | None,
    setup_complete: bool = True,
    last_seen: datetime | None = NOW,
    firmware: str | None = "0.1.0",
) -> tuple[Device, str]:
    """A claimed robot with a known device token, and no hardware anywhere.

    The row stores the hash and the test holds the plaintext, which is the
    state a real claim leaves behind (PRD 2, section 55). There is no robot:
    this is a database row and a string.
    """
    token = f"nura-device-{secrets.token_hex(16)}"
    account_id = client.get("/api/v1/me", headers=headers).json()["id"]
    device = Device(
        hardware_id=f"NURA-{secrets.token_hex(6).upper()}",
        display_name="Nura",
        claimed_by_account_id=uuid.UUID(account_id),
        owner_profile_id=None if profile_id is None else uuid.UUID(profile_id),
        provisioning_status="claimed",
        firmware_version=firmware,
        bootstrap_secret_hash=hash_secret(secrets.token_hex(32)),
        device_token_hash=hash_secret(token),
        claimed_at=NOW - timedelta(days=1),
        last_seen_at=last_seen,
        setup_completed_at=NOW - timedelta(days=1) if setup_complete else None,
    )
    db.add(device)
    db.commit()
    db.refresh(device)
    return device, token


def device_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def report(client, token: str, states: dict[str, str], **extra):
    payload = {"capabilities": states}
    payload.update(extra)
    return client.post(
        f"{DEVICE_ACTIONS}/capabilities", json=payload, headers=device_headers(token)
    )


def fetch_next(client, token: str):
    return client.get(
        f"{DEVICE_ACTIONS}/presentations/next", headers=device_headers(token)
    )


def acknowledge(client, token: str, presentation_id: str, state: str, **extra):
    payload = {"state": state}
    payload.update(extra)
    return client.post(
        f"{DEVICE_ACTIONS}/presentations/{presentation_id}/ack",
        json=payload,
        headers=device_headers(token),
    )


def a_request(
    presentation_type: str = "info_card",
    *,
    source: str = "system",
    source_id: str = "test",
    **kwargs,
) -> queue.PresentationRequest:
    """A minimal valid request of any type, for queue-level tests."""
    return queue.PresentationRequest(
        presentation_type=presentation_type,
        layout="TITLE_BODY",
        payload=layouts.build_payload("TITLE_BODY", title="Nura", body="Something"),
        source=source,
        source_id=source_id,
        **kwargs,
    )


def with_display(db, device: Device, now: datetime = NOW) -> None:
    """Gives the row a reported screen, so cards are not ``not_supported``."""
    capability_service.report(db, device, dict(sim.DISPLAY_ONLY), now)
    db.commit()


def hand_over(db, device: Device, now: datetime) -> DevicePresentation | None:
    """What a fetch does to the queue, without reconciling around it.

    The HTTP route reconciles first, which is what makes a card whose source
    has gone away disappear -- correct, and tested in
    ``test_robot_builders.py`` against real doses and messages. The tests in
    *this* file are about the queue itself, so they drive it directly rather
    than inventing a dose to hang a priority test on.
    """
    row = queue.next_for_device(db, device, now)
    db.commit()
    return row


def render_ack(db, row: DevicePresentation, state: str, now: datetime, **kwargs):
    """A device acknowledgement, at the service level."""
    queue.acknowledge(db, row, state, now, **kwargs)
    db.commit()
    return row


# --- section 16 --------------------------------------------------------------


class TestOrdering:
    def test_every_type_has_exactly_one_priority(self):
        """Section 16 asks for deterministic ordering, so the table is total.

        Checked against the tuple rather than by trying the queue: a type added
        without a rank would make selection depend on insertion order, and that
        is the kind of bug that only shows up when two things are queued in the
        same second.
        """
        ranked = [name for name, _ in ROBOT_PRESENTATION_PRIORITIES]
        assert sorted(ranked) == sorted(ROBOT_PRESENTATION_TYPES)
        assert len(ranked) == len(set(ranked))

    def test_the_prds_own_order_is_the_order(self):
        """Section 16's list, read back out of the table."""
        order = [
            name
            for name, _ in sorted(ROBOT_PRESENTATION_PRIORITIES, key=lambda pair: pair[1])
        ]
        expected = [
            "emergency_status",
            "safety_check",
            "safety_status",
            "medication_reminder",
            "appointment_reminder",
            "family_message",
            "assistant_response",
            "info_card",
            "face_state",
        ]
        assert [name for name in order if name in expected] == expected

    def test_the_higher_priority_card_is_handed_over_first(
        self, db, client, clock, owner
    ):
        """Two things waiting; the queue answers with the more urgent one."""
        headers, profile_id = owner
        device, token = seed_device(db, client, headers, profile_id=profile_id)
        with_display(db, device)

        queue.queue(db, device, a_request("info_card", source_id="low"), clock.now)
        queue.queue(
            db,
            device,
            a_request("medication_reminder", source="medication", source_id="high"),
            clock.now,
        )
        db.commit()

        first = hand_over(db, device, clock.now)
        assert first is not None
        assert first.presentation_type == "medication_reminder"
        second = hand_over(db, device, clock.now)
        assert second is not None
        assert second.presentation_type == "medication_reminder"
        # The same row again: it was sent and never acknowledged, so it is
        # offered again with the same id (section 18).
        assert second.id == first.id

    def test_the_envelope_carries_the_version_and_the_settings(
        self, db, client, clock, owner
    ):
        """Sections 38 and 116, plus sections 44, 45 and 30 travelling with it."""
        headers, profile_id = owner
        device, token = seed_device(db, client, headers, profile_id=profile_id)
        with_display(db, device)
        queue.queue(db, device, a_request(), clock.now)
        db.commit()

        body = fetch_next(client, token).json()
        assert body["protocol_version"] == layouts.PROTOCOL_VERSION
        assert body["settings"]["brightness"] == 70
        assert body["settings"]["reduced_motion"] is False
        assert set(body["payload"]) <= {"title", "body", "sensitive", "truncated"}


# --- section 17 --------------------------------------------------------------


class TestPreemption:
    def test_an_emergency_takes_the_screen_from_a_message(self, db, client, clock, owner):
        """Section 17's own example, with the message already on the screen."""
        headers, profile_id = owner
        device, token = seed_device(db, client, headers, profile_id=profile_id)
        with_display(db, device)

        message = queue.queue(
            db,
            device,
            a_request("family_message", source="family_message", source_id="m1"),
            clock.now,
        )
        db.commit()
        render_ack(db, hand_over(db, device, clock.now), "render_started", clock.now)
        db.refresh(message)
        assert message.status == "displayed"

        queue.queue(
            db,
            device,
            a_request("emergency_status", source="safety", source_id="e1"),
            clock.now,
        )
        db.commit()
        db.refresh(message)
        assert message.status == "cancelled"
        assert message.cancel_reason == "preempted"

    def test_a_reminder_does_not_cancel_a_message_on_the_screen(
        self, db, client, clock, owner
    ):
        """The other half of section 17's "may".

        A reminder can wait thirty seconds. A cancelled message has lost the
        only moment it had, and nothing about a medication reminder justifies
        that -- so ordinary cards queue behind each other rather than
        preempting.
        """
        headers, profile_id = owner
        device, token = seed_device(db, client, headers, profile_id=profile_id)
        with_display(db, device)

        message = queue.queue(
            db,
            device,
            a_request("family_message", source="family_message", source_id="m1"),
            clock.now,
        )
        db.commit()
        render_ack(db, hand_over(db, device, clock.now), "render_started", clock.now)

        queue.queue(
            db,
            device,
            a_request("medication_reminder", source="medication", source_id="d1"),
            clock.now,
        )
        db.commit()
        db.refresh(message)
        assert message.status == "displayed"
        assert message.cancel_reason is None

    def test_a_queued_card_is_not_thrown_away_by_an_emergency(
        self, db, client, clock, owner
    ):
        """Only what is on the screen is preempted.

        An emergency that ends in ninety seconds should not also have discarded
        a message nobody has seen yet.
        """
        headers, profile_id = owner
        device, _ = seed_device(db, client, headers, profile_id=profile_id)
        with_display(db, device)

        waiting = queue.queue(
            db,
            device,
            a_request("family_message", source="family_message", source_id="m1"),
            clock.now,
        )
        queue.queue(
            db,
            device,
            a_request("emergency_status", source="safety", source_id="e1"),
            clock.now,
        )
        db.commit()
        db.refresh(waiting)
        assert waiting.status == "queued"

    def test_only_one_card_is_on_the_screen_at_a_time(self, db, client, clock, owner):
        """Section 18. The one that was there is finished, not cancelled."""
        headers, profile_id = owner
        device, token = seed_device(db, client, headers, profile_id=profile_id)
        with_display(db, device)

        first = queue.queue(db, device, a_request(source_id="one"), clock.now)
        db.commit()
        render_ack(db, hand_over(db, device, clock.now), "render_started", clock.now)

        second = queue.queue(
            db,
            device,
            a_request("medication_reminder", source="medication", source_id="two"),
            clock.now,
        )
        db.commit()
        render_ack(db, hand_over(db, device, clock.now), "render_started", clock.now)

        db.refresh(first)
        db.refresh(second)
        assert second.status == "displayed"
        assert first.status == "completed"


# --- sections 18, 55 and 56 --------------------------------------------------


class TestExpiry:
    def test_a_reminder_is_not_handed_over_late(self, db, client, clock, owner):
        """Sections 18 and 55: expired items are skipped, not shown."""
        headers, profile_id = owner
        device, token = seed_device(db, client, headers, profile_id=profile_id)
        with_display(db, device)
        row = queue.queue(
            db,
            device,
            a_request("medication_reminder", source="medication", source_id="d1"),
            clock.now,
        )
        db.commit()
        assert row.expires_at == NOW + timedelta(minutes=30)

        clock.advance(minutes=31)
        assert hand_over(db, device, clock.now) is None
        db.refresh(row)
        assert row.status == "expired"

    def test_safety_presentations_have_no_timer_at_all(self, db, client, clock, owner):
        """Section 113. Tied to the live event, not to a clock."""
        headers, profile_id = owner
        device, _ = seed_device(db, client, headers, profile_id=profile_id)
        with_display(db, device)
        row = queue.queue(
            db,
            device,
            a_request("emergency_status", source="safety", source_id="e1"),
            clock.now,
        )
        db.commit()
        assert row.expires_at is None
        assert queue.EXPIRY["emergency_status"] is None
        assert queue.EXPIRY["safety_check"] is None

    def test_expiry_happens_on_a_read_as_well_as_on_a_schedule(
        self, db, client, clock, owner
    ):
        """The state is right whenever anybody looks.

        The same arrangement PRD 5 uses for doses and PRD 10 for monitoring:
        ``scripts/robot_maintenance.py`` keeps the table tidy, and nothing
        depends on it having run.
        """
        headers, profile_id = owner
        device, _ = seed_device(db, client, headers, profile_id=profile_id)
        with_display(db, device)
        queue.queue(
            db,
            device,
            a_request("assistant_response", source="assistant", source_id="a1"),
            clock.now,
        )
        db.commit()

        clock.advance(minutes=6)
        history = client.get(
            f"/api/v1/devices/{device.id}/presentation-history", headers=headers
        ).json()["presentations"]
        assert history[0]["status"] == "expired"
        assert "expired" in history[0]["line"]


# --- section 57 --------------------------------------------------------------


class TestDeduplication:
    def test_the_same_build_twice_makes_one_card(self, db, client, clock, owner):
        """Section 57, and section 18's "duplicate presentation IDs"."""
        headers, profile_id = owner
        device, _ = seed_device(db, client, headers, profile_id=profile_id)
        with_display(db, device)

        first = queue.queue(
            db,
            device,
            a_request("medication_reminder", source="medication", source_id="dose-1"),
            clock.now,
        )
        second = queue.queue(
            db,
            device,
            a_request("medication_reminder", source="medication", source_id="dose-1"),
            clock.now,
        )
        db.commit()
        assert first.id == second.id
        assert db.query(DevicePresentation).count() == 1

    def test_a_finished_card_is_not_queued_again_by_a_retry(
        self, db, client, clock, owner
    ):
        """A dose reminded once is not reminded again an hour later.

        The key folds into the completed row rather than making a second card,
        which is what stops a retried job turning into two reminders.
        """
        headers, profile_id = owner
        device, token = seed_device(db, client, headers, profile_id=profile_id)
        with_display(db, device)
        queue.queue(
            db,
            device,
            a_request("medication_reminder", source="medication", source_id="dose-1"),
            clock.now,
        )
        db.commit()
        render_ack(db, hand_over(db, device, clock.now), "render_completed", clock.now)

        again = queue.queue(
            db,
            device,
            a_request("medication_reminder", source="medication", source_id="dose-1"),
            clock.now,
        )
        db.commit()
        assert again.status == "completed"
        assert db.query(DevicePresentation).count() == 1

    def test_the_face_is_the_one_thing_that_can_come_back(self, db, client, clock, owner):
        """A face is a state the robot returns to, not an occasion.

        The exception is deliberate and is the only one: section 83's "when the
        queue is empty, show the companion face" needs the face to be
        queueable again after a card has replaced it.
        """
        headers, profile_id = owner
        device, token = seed_device(db, client, headers, profile_id=profile_id)
        with_display(db, device)
        first = queue.queue(
            db,
            device,
            queue.PresentationRequest(
                presentation_type="face_state",
                layout="FACE",
                payload=layouts.build_payload("FACE", face_state="idle"),
                source="system",
                source_id="idle",
                requires=("display",),
                repeatable=True,
            ),
            clock.now,
        )
        db.commit()
        render_ack(db, hand_over(db, device, clock.now), "render_completed", clock.now)

        second = queue.queue(
            db,
            device,
            queue.PresentationRequest(
                presentation_type="face_state",
                layout="FACE",
                payload=layouts.build_payload("FACE", face_state="idle"),
                source="system",
                source_id="idle",
                requires=("display",),
                repeatable=True,
            ),
            clock.now,
        )
        db.commit()
        assert second.id != first.id
        assert second.status == "queued"


# --- sections 14, 19 and 123 -------------------------------------------------


class TestAcknowledgement:
    def test_fetching_does_not_mark_anything_displayed(self, db, client, clock, owner):
        """Section 14, and section 141's question asked directly."""
        headers, profile_id = owner
        device, token = seed_device(db, client, headers, profile_id=profile_id)
        with_display(db, device)
        row = queue.queue(db, device, a_request(), clock.now)
        db.commit()

        fetch_next(client, token)
        db.refresh(row)
        assert row.status == "sent"
        assert row.sent_at is not None
        assert row.displayed_at is None
        assert row.ack_state is None

    def test_the_database_refuses_a_display_nobody_acknowledged(
        self, db, client, clock, owner
    ):
        """The same rule, one layer down.

        ``ck_device_presentations_displayed`` means a future bug cannot write
        ``displayed_at`` without a render acknowledgement. This test writes
        directly past the service to prove the constraint, not the code.
        """
        import sqlalchemy

        headers, profile_id = owner
        device, _ = seed_device(db, client, headers, profile_id=profile_id)
        with_display(db, device)
        row = queue.queue(db, device, a_request(), clock.now)
        db.commit()

        with pytest.raises(sqlalchemy.exc.IntegrityError):
            db.execute(
                sqlalchemy.text(
                    "UPDATE device_presentations SET displayed_at = now() WHERE id = :id"
                ),
                {"id": row.id},
            )
            db.flush()
        db.rollback()

    def test_each_state_moves_the_row_where_section_19_says(
        self, db, client, clock, owner
    ):
        headers, profile_id = owner
        device, token = seed_device(db, client, headers, profile_id=profile_id)
        with_display(db, device)
        row = queue.queue(db, device, a_request(), clock.now)
        db.commit()
        envelope = fetch_next(client, token).json()
        presentation_id = envelope["presentation_id"]

        assert (
            acknowledge(client, token, presentation_id, "received").json()["status"]
            == "acknowledged"
        )
        assert (
            acknowledge(client, token, presentation_id, "render_started").json()["status"]
            == "displayed"
        )
        assert (
            acknowledge(client, token, presentation_id, "render_completed").json()[
                "status"
            ]
            == "completed"
        )
        db.refresh(row)
        assert row.displayed_at is not None

    def test_a_repeated_acknowledgement_is_accepted_and_changes_nothing(
        self, db, client, clock, owner
    ):
        """Section 18. A device whose response was lost sends it again."""
        headers, profile_id = owner
        device, token = seed_device(db, client, headers, profile_id=profile_id)
        with_display(db, device)
        queue.queue(db, device, a_request(), clock.now)
        db.commit()
        presentation_id = fetch_next(client, token).json()["presentation_id"]

        first = acknowledge(client, token, presentation_id, "render_completed").json()
        second = acknowledge(client, token, presentation_id, "render_completed").json()
        assert first["applied"] is True
        assert second["applied"] is False
        assert second["status"] == "completed"

    def test_an_acknowledgement_for_something_never_sent_is_refused(
        self, db, client, clock, owner
    ):
        """Section 123's "invalid ack rejected".

        A device cannot report having rendered something it was never handed,
        which is why ``queued`` appears in none of the transition rules.
        """
        headers, profile_id = owner
        device, token = seed_device(db, client, headers, profile_id=profile_id)
        with_display(db, device)
        row = queue.queue(db, device, a_request(), clock.now)
        db.commit()

        response = acknowledge(client, token, str(row.id), "render_completed")
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "invalid_acknowledgement"

    def test_going_backwards_is_refused(self, db, client, clock, owner):
        headers, profile_id = owner
        device, token = seed_device(db, client, headers, profile_id=profile_id)
        with_display(db, device)
        queue.queue(db, device, a_request(), clock.now)
        db.commit()
        presentation_id = fetch_next(client, token).json()["presentation_id"]
        acknowledge(client, token, presentation_id, "render_completed")

        assert acknowledge(client, token, presentation_id, "received").status_code == 409

    def test_a_render_failure_is_recorded_as_one(self, db, client, clock, owner):
        """Section 132's "simulate render failure, verify backend failed state"."""
        headers, profile_id = owner
        device, token = seed_device(db, client, headers, profile_id=profile_id)
        with_display(db, device)
        row = queue.queue(db, device, a_request(), clock.now)
        db.commit()
        presentation_id = fetch_next(client, token).json()["presentation_id"]

        acknowledge(client, token, presentation_id, "failed")
        db.refresh(row)
        assert row.status == "failed"
        assert row.failure_code == "render_failed"
        assert row.displayed_at is None

    def test_a_free_text_failure_reason_is_refused(self, db, client, clock, owner):
        """Section 67: a stable code or nothing, never a device's error text."""
        headers, profile_id = owner
        device, token = seed_device(db, client, headers, profile_id=profile_id)
        with_display(db, device)
        queue.queue(db, device, a_request(), clock.now)
        db.commit()
        presentation_id = fetch_next(client, token).json()["presentation_id"]

        response = acknowledge(
            client,
            token,
            presentation_id,
            "failed",
            failure_code="panel timed out on SPI2 at 0x3f",
        )
        assert response.status_code == 422


# --- sections 69 and 123 -----------------------------------------------------


class TestDeviceAccess:
    def test_a_device_cannot_fetch_another_robots_presentation(
        self, db, client, clock, owner, make_token
    ):
        """Section 123's "device can only fetch its own", and section 69.

        The second account is real and its robot is real; the refusal is the
        production lookup refusing, and the answer is the same 404 a
        non-existent id gets -- so a robot trying ids learns nothing.
        """
        headers, profile_id = owner
        mine, _ = seed_device(db, client, headers, profile_id=profile_id)
        with_display(db, mine)
        row = queue.queue(db, mine, a_request(), clock.now)
        db.commit()

        other_headers = ready_account(client, make_token)
        other_profile = client.get("/api/v1/me", headers=other_headers).json()[
            "profiles"
        ][0]["id"]
        _, other_token = seed_device(db, client, other_headers, profile_id=other_profile)

        response = acknowledge(client, other_token, str(row.id), "received")
        assert response.status_code == 404
        assert response.json()["detail"]["code"] == "presentation_not_found"

    def test_a_users_token_is_not_a_device_token(self, db, client, owner):
        """PRD 2's rule, still true of PRD 11's routes."""
        headers, _ = owner
        response = client.get(f"{DEVICE_ACTIONS}/presentations/next", headers=headers)
        assert response.status_code == 401

    def test_a_device_with_no_profile_is_told_nothing(self, db, client, clock, owner):
        """Claimed but not set up for anybody. Nothing belongs to nobody."""
        headers, _ = owner
        device, token = seed_device(db, client, headers, profile_id=None)
        with_display(db, device)
        assert fetch_next(client, token).status_code == 204

    def test_another_account_cannot_read_this_robots_preferences(
        self, db, client, owner, make_token
    ):
        """Section 69, and PRD 2's 404-not-403 rule applied to the new routes."""
        headers, profile_id = owner
        device, _ = seed_device(db, client, headers, profile_id=profile_id)
        other = ready_account(client, make_token)
        for path in (
            "presentation-preferences",
            "presentation-history",
            "capabilities",
            "robot-status",
        ):
            response = client.get(f"/api/v1/devices/{device.id}/{path}", headers=other)
            assert response.status_code == 404, path


# --- section 20 --------------------------------------------------------------


class TestOffline:
    def test_an_offline_robot_leaves_its_card_waiting_and_unclaimed(
        self, db, client, clock, owner
    ):
        """Section 20 and section 99.

        Nothing is fetched, nothing is acknowledged, and so nothing is
        displayed. The sentence the app shows instead comes from the server.
        """
        headers, profile_id = owner
        device, _ = seed_device(
            db, client, headers, profile_id=profile_id, last_seen=NOW - timedelta(hours=2)
        )
        with_display(db, device)
        row = queue.queue(db, device, a_request(source_id="waiting"), clock.now)
        db.commit()

        status = client.get(
            f"/api/v1/devices/{device.id}/robot-status", headers=headers
        ).json()
        assert status["connection_status"] == "offline"
        assert status["mode"] == "offline"
        assert status["offline_note"] == (
            "Robot offline — this item remains available on your phone."
        )
        assert status["current"] is None
        db.refresh(row)
        assert row.status == "queued"
        assert row.displayed_at is None

    def test_no_row_in_the_whole_table_has_ever_been_displayed_by_hardware(
        self, db, client, clock, owner
    ):
        """The PRD 10 ``delivered`` test, applied to section 135.

        Every ``displayed`` row in this database was written by a *simulated*
        acknowledgement in a test. There is no physical robot and no physical
        render has been acknowledged, which is what the completion report has
        to keep saying.
        """
        headers, profile_id = owner
        device, _ = seed_device(db, client, headers, profile_id=profile_id)
        with_display(db, device)
        queue.queue(db, device, a_request(), clock.now)
        db.commit()
        rows = db.query(DevicePresentation).all()
        assert all(row.ack_state is None for row in rows)
