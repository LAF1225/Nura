"""What each source puts on the robot, and what it refuses to put there.

PRD 11, sections 21-26, 33, 51-54, 56, 71, 72, 78, 86, 101, 113-115 and
125-128.

Section 125 is medication, 126 family messages, 127 safety and 128 the
assistant. Each of those sections lists cases; each case is a test here, and
every one of them runs against real doses, real messages, real PRD 9
permissions and real PRD 10 events -- not fixtures standing in for them.

**The reconciler is what is being tested as much as the builders.** PRD 11 does
not hook into PRD 5, 7, 9 or 10; it reads their state and makes the queue
match. So "a taken dose cancels a stale card" is not a notification that fires,
it is what the next read discovers -- which is why these tests mostly take the
shape *change the source, reconcile, look at the queue*.

**No hardware anywhere.** The robot is a row and a token.
"""

import uuid
from datetime import timedelta

import pytest

from app.api.deps import current_time
from app.main import app
from app.models import DevicePresentation, FamilyMessage, FamilyThread
from app.services.robot import layouts, preferences, presenter, queue
from app.services.robot import simulator as sim
from app.services.robot.builders import assistant as assistant_builder
from app.services.robot.builders import messages as message_builder
from tests.test_caregivers import active_caregiver
from tests.test_devices import ready_account
from tests.test_family import open_thread, send
from tests.test_medications import add_medication, make_schedule
from tests.test_robot_presentations import (
    NOW,
    hand_over,
    render_ack,
    seed_device,
    with_display,
)
from tests.test_safety import start_monitoring
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


@pytest.fixture
def robot(db, client, clock, owner):
    """A claimed robot with a reported screen, linked to the owner's profile."""
    headers, profile_id = owner
    device, token = seed_device(db, client, headers, profile_id=profile_id)
    with_display(db, device, clock.now)
    return device, token


@pytest.fixture
def caregiver(client, make_token) -> dict[str, str]:
    return {"Authorization": f"Bearer {make_token()}"}


def a_dose_due_now(
    client, headers, profile_id: str, clock, *, once: bool = False, **medication_kwargs
):
    """A real PRD 5 dose that reads as ``due`` right now.

    Scheduled ten minutes ahead rather than exactly now: PRD 5 never
    backfills, so a time that has already arrived produces no dose at all --
    and PRD 5 calls a dose ``due`` from half an hour before its moment, so ten
    minutes ahead is due without the test having to move the clock.
    """
    medication_id = add_medication(client, headers, profile_id, **medication_kwargs)
    due = clock.now + timedelta(minutes=10)
    response = make_schedule(
        client,
        headers,
        profile_id,
        medication_id,
        times=[{"time_of_day": due.strftime("%H:%M:%S")}],
        timezone="UTC",
        start_date=due.date().isoformat(),
        # ``once`` stops the schedule producing tomorrow's dose as well, which
        # a test about reconnecting a day later needs.
        end_date=due.date().isoformat() if once else None,
    )
    assert response.status_code == 201, response.text
    doses = client.get(
        f"/api/v1/profiles/{profile_id}/medication-doses",
        params={
            "from_date": clock.now.date().isoformat(),
            "to_date": clock.now.date().isoformat(),
        },
        headers=headers,
    ).json()
    assert doses, "the schedule produced no dose"
    return doses[0]


def cards(db, device, presentation_type: str) -> list[DevicePresentation]:
    return [
        row
        for row in queue.open_presentations(db, device.id)
        if row.presentation_type == presentation_type
    ]


# --- section 125 -------------------------------------------------------------


class TestMedication:
    def test_a_private_preview_does_not_name_the_medication(
        self, db, client, clock, owner, robot
    ):
        """Section 22, and section 104's conservative default.

        ``private`` is the default, so this is also the test that a robot
        arriving in a household does not start naming somebody's tablets on a
        screen in the living room before anybody has chosen anything.
        """
        headers, profile_id = owner
        device, _ = robot
        a_dose_due_now(client, headers, profile_id, clock, name="Metformin")

        presenter.refresh(db, device, clock.now)
        db.commit()
        card = cards(db, device, "medication_reminder")[0]
        assert card.payload["primary"] == "Reminder due"
        assert "Metformin" not in str(card.payload)
        assert card.payload["sensitive"] is False

    def test_full_details_show_the_name_the_dose_and_the_time(
        self, db, client, clock, owner, robot
    ):
        """Section 21's own example, once somebody has asked for it."""
        headers, profile_id = owner
        device, _ = robot
        a_dose_due_now(client, headers, profile_id, clock, name="Metformin")
        client.patch(
            f"/api/v1/devices/{device.id}/presentation-preferences",
            json={"medication_privacy_level": "full"},
            headers=headers,
        )

        presenter.refresh(db, device, clock.now)
        db.commit()
        card = cards(db, device, "medication_reminder")[0]
        assert card.payload["primary"] == "Metformin"
        assert "500 mg" in card.payload["secondary"]
        assert card.payload["sensitive"] is True

    def test_name_only_leaves_out_the_dose(self, db, client, clock, owner, robot):
        """The middle level: the amount is often what says what it is for."""
        headers, profile_id = owner
        device, _ = robot
        a_dose_due_now(client, headers, profile_id, clock, name="Metformin")
        client.patch(
            f"/api/v1/devices/{device.id}/presentation-preferences",
            json={"medication_privacy_level": "name_only"},
            headers=headers,
        )

        presenter.refresh(db, device, clock.now)
        db.commit()
        card = cards(db, device, "medication_reminder")[0]
        assert card.payload["primary"] == "Metformin"
        assert "500 mg" not in card.payload["secondary"]

    def test_privacy_mode_overrides_a_full_preference(
        self, db, client, clock, owner, robot
    ):
        """Section 33.

        A person who chose "full details" and then put Nura in Privacy Mode
        gets the private card: the mode is something they are doing now and the
        preference is something they set once.
        """
        headers, profile_id = owner
        device, _ = robot
        a_dose_due_now(client, headers, profile_id, clock)
        client.patch(
            f"/api/v1/devices/{device.id}/presentation-preferences",
            json={"medication_privacy_level": "full"},
            headers=headers,
        )
        client.patch(
            f"/api/v1/profiles/{profile_id}/assistant/preferences",
            json={"mode": "privacy"},
            headers=headers,
        )

        presenter.refresh(db, device, clock.now)
        db.commit()
        card = cards(db, device, "medication_reminder")[0]
        assert card.payload["primary"] == "Reminder due"

    def test_changing_the_privacy_level_replaces_a_card_already_queued(
        self, db, client, clock, owner, robot
    ):
        """Sections 22 and 33, in the direction that matters.

        Found by the manual walk-through: the dedupe key originally named only
        the dose and the snooze count, so switching the preference folded the
        rebuild into the card already there -- and somebody who had just asked
        for a private preview kept looking at the name of their tablet. The
        level is part of the occasion now, so the old card is withdrawn and a
        new one is built.
        """
        headers, profile_id = owner
        device, _ = robot
        a_dose_due_now(client, headers, profile_id, clock, name="Metformin")
        client.patch(
            f"/api/v1/devices/{device.id}/presentation-preferences",
            json={"medication_privacy_level": "full"},
            headers=headers,
        )
        presenter.refresh(db, device, clock.now)
        db.commit()
        full = cards(db, device, "medication_reminder")[0]
        assert full.payload["primary"] == "Metformin"

        client.patch(
            f"/api/v1/devices/{device.id}/presentation-preferences",
            json={"medication_privacy_level": "private"},
            headers=headers,
        )
        presenter.refresh(db, device, clock.now)
        db.commit()

        open_cards = cards(db, device, "medication_reminder")
        assert len(open_cards) == 1
        assert open_cards[0].id != full.id
        assert open_cards[0].payload["primary"] == "Reminder due"
        db.refresh(full)
        assert full.status == "cancelled"
        assert "Metformin" not in str(open_cards[0].payload)

    def test_privacy_mode_replaces_a_full_card_that_is_on_the_screen(
        self, db, client, clock, owner, robot
    ):
        """The same rule, driven by the mode rather than the preference.

        The stronger half of section 33: somebody turning Privacy Mode on
        wants less on the screen *now*, not from the next dose onwards.
        """
        headers, profile_id = owner
        device, _ = robot
        a_dose_due_now(client, headers, profile_id, clock, name="Metformin")
        client.patch(
            f"/api/v1/devices/{device.id}/presentation-preferences",
            json={"medication_privacy_level": "full"},
            headers=headers,
        )
        presenter.refresh(db, device, clock.now)
        db.commit()
        render_ack(db, hand_over(db, device, clock.now), "render_started", clock.now)

        client.patch(
            f"/api/v1/profiles/{profile_id}/assistant/preferences",
            json={"mode": "privacy"},
            headers=headers,
        )
        presenter.refresh(db, device, clock.now)
        db.commit()

        open_cards = cards(db, device, "medication_reminder")
        assert len(open_cards) == 1
        assert open_cards[0].payload["primary"] == "Reminder due"

    def test_a_level_can_be_configured_back_to(self, db, client, clock, owner, robot):
        """The second half of what the walk-through found.

        With the level in the dedupe key, a card withdrawn *because the level
        changed* would otherwise keep occupying its key -- so full → private →
        full left the dose with no card at all. The cancel reason is what
        distinguishes "the person reconfigured" from "the occasion is over",
        and only the first may be rebuilt.
        """
        headers, profile_id = owner
        device, _ = robot
        a_dose_due_now(client, headers, profile_id, clock, name="Metformin")

        def level(value: str) -> None:
            client.patch(
                f"/api/v1/devices/{device.id}/presentation-preferences",
                json={"medication_privacy_level": value},
                headers=headers,
            )
            presenter.refresh(db, device, clock.now)
            db.commit()

        level("full")
        assert cards(db, device, "medication_reminder")[0].payload["primary"] == (
            "Metformin"
        )
        level("private")
        assert cards(db, device, "medication_reminder")[0].payload["primary"] == (
            "Reminder due"
        )
        # Back again, which is the case that used to leave nothing at all.
        level("full")
        open_cards = cards(db, device, "medication_reminder")
        assert len(open_cards) == 1
        assert open_cards[0].payload["primary"] == "Metformin"

        # And a dose that has been *taken* is still not rebuilt, because that
        # occasion really is over.
        dose = client.get(
            f"/api/v1/profiles/{profile_id}/medication-doses",
            params={
                "from_date": clock.now.date().isoformat(),
                "to_date": clock.now.date().isoformat(),
            },
            headers=headers,
        ).json()[0]
        client.post(
            f"/api/v1/profiles/{profile_id}/medication-doses/{dose['id']}/taken",
            json={},
            headers=headers,
        )
        presenter.refresh(db, device, clock.now)
        db.commit()
        assert cards(db, device, "medication_reminder") == []

    def test_a_taken_dose_cancels_its_card(self, db, client, clock, owner, robot):
        """Section 125's "taken dose cancels stale card", section 56's rule.

        Nothing notified the robot. The dose stopped being due, and the next
        reconciliation found that out.
        """
        headers, profile_id = owner
        device, _ = robot
        dose = a_dose_due_now(client, headers, profile_id, clock)
        presenter.refresh(db, device, clock.now)
        db.commit()
        assert cards(db, device, "medication_reminder")

        client.post(
            f"/api/v1/profiles/{profile_id}/medication-doses/{dose['id']}/taken",
            json={},
            headers=headers,
        )
        presenter.refresh(db, device, clock.now)
        db.commit()
        assert cards(db, device, "medication_reminder") == []
        row = (
            db.query(DevicePresentation)
            .filter_by(presentation_type="medication_reminder")
            .one()
        )
        assert row.status == "cancelled"
        assert row.cancel_reason == "source_resolved"

    def test_an_expired_dose_is_not_shown_on_reconnect(
        self, db, client, clock, owner, robot
    ):
        """Section 125's "expired dose not shown on reconnect"."""
        headers, profile_id = owner
        device, token = robot
        a_dose_due_now(client, headers, profile_id, clock, once=True)
        presenter.refresh(db, device, clock.now)
        db.commit()

        # The robot was unplugged for a day.
        clock.advance(days=1)
        from tests.test_robot_presentations import fetch_next

        # There *is* something to hand over -- the companion face, because the
        # queue is otherwise empty (section 83). What there is not is a day-old
        # reminder to take a tablet.
        handed_over = fetch_next(client, token).json()
        assert handed_over["type"] == "face_state"
        assert cards(db, device, "medication_reminder") == []
        stale = (
            db.query(DevicePresentation)
            .filter_by(presentation_type="medication_reminder")
            .one()
        )
        assert stale.status in {"expired", "cancelled"}

    def test_no_display_does_not_affect_the_phone(self, db, client, clock, owner):
        """Section 125's last case, and sections 51 and 102.

        The robot has no screen. The dose is still a dose, the phone's own
        reminder is PRD 5's, and the card is recorded as not supported rather
        than silently dropped -- so the app can say why nothing appeared.
        """
        headers, profile_id = owner
        device, token = seed_device(db, client, headers, profile_id=profile_id)
        from tests.test_robot_presentations import report

        report(client, token, dict(sim.HEADLESS))
        dose = a_dose_due_now(client, headers, profile_id, clock)

        presenter.refresh(db, device, clock.now)
        db.commit()
        row = (
            db.query(DevicePresentation)
            .filter_by(presentation_type="medication_reminder")
            .one()
        )
        assert row.status == "not_supported"
        assert row.failure_code == "no_display"

        still_there = client.get(
            f"/api/v1/profiles/{profile_id}/medication-doses",
            params={
                "from_date": clock.now.date().isoformat(),
                "to_date": clock.now.date().isoformat(),
            },
            headers=headers,
        ).json()
        assert [row for row in still_there if row["id"] == dose["id"]][0][
            "status"
        ] == "scheduled"

    def test_a_snoozed_dose_gets_a_new_card_at_its_new_time(
        self, db, client, clock, owner, robot
    ):
        """The dedupe key carries the snooze count, so this is a new occasion.

        Without that, the second reminder would fold into the card that was
        already withdrawn and the person would never be reminded again.
        """
        headers, profile_id = owner
        device, _ = robot
        dose = a_dose_due_now(client, headers, profile_id, clock)
        presenter.refresh(db, device, clock.now)
        db.commit()
        first = cards(db, device, "medication_reminder")[0]

        client.post(
            f"/api/v1/profiles/{profile_id}/medication-doses/{dose['id']}/snooze",
            json={"minutes": 10},
            headers=headers,
        )
        presenter.refresh(db, device, clock.now)
        db.commit()
        clock.advance(minutes=10)
        presenter.refresh(db, device, clock.now)
        db.commit()

        second = cards(db, device, "medication_reminder")
        assert second, "the snoozed dose produced no new card"
        assert second[0].id != first.id

    def test_there_are_no_buttons_so_the_card_says_where_to_answer(
        self, db, client, clock, owner, robot
    ):
        """Section 86. No device has ever reported input hardware."""
        headers, profile_id = owner
        device, _ = robot
        a_dose_due_now(client, headers, profile_id, clock)
        presenter.refresh(db, device, clock.now)
        db.commit()
        card = cards(db, device, "medication_reminder")[0]
        assert card.payload["respond_in_app"] is True
        assert card.payload.get("actions", []) == []
        assert "prompt" not in card.payload

    def test_with_buttons_the_card_offers_the_three_actions(
        self, db, client, clock, owner
    ):
        """Section 21's future actions, offered only when there is a button."""
        headers, profile_id = owner
        device, token = seed_device(db, client, headers, profile_id=profile_id)
        from tests.test_robot_presentations import report

        report(client, token, dict(sim.WITH_BUTTONS))
        a_dose_due_now(client, headers, profile_id, clock)

        presenter.refresh(db, device, clock.now)
        db.commit()
        card = cards(db, device, "medication_reminder")[0]
        assert card.payload["actions"] == ["taken", "snooze", "skip"]
        assert card.payload["prompt"] == "Taken?"
        assert card.payload["respond_in_app"] is False


# --- section 126 -------------------------------------------------------------


class TestFamilyMessages:
    def _a_message(self, client, owner_account, caregiver, text="Call me when free"):
        headers, profile_id = owner_account
        relationship_id = active_caregiver(
            client, owner_account, caregiver, permissions={"communication": True}
        )
        thread_id = open_thread(client, headers, profile_id, relationship_id)
        response = send(
            client, caregiver, profile_id, thread_id, message_type="text", text=text
        )
        assert response.status_code == 201, response.text
        return relationship_id, response.json()["id"]

    def test_an_authorized_message_becomes_a_card(
        self, db, client, clock, owner, robot, caregiver
    ):
        """Section 24. The message exists because PRD 9 allowed it."""
        device, _ = robot
        self._a_message(client, owner, caregiver)

        presenter.refresh(db, device, clock.now)
        db.commit()
        card = cards(db, device, "family_message")[0]
        assert card.payload["sender"] == "Ayesha"
        assert card.payload["body"] == "Call me when free"

    def test_nothing_but_a_stored_message_can_make_one(self):
        """Section 126's first case, satisfied by the signature.

        ``build`` takes a ``FamilyMessage``. There is no parameter through
        which text could be supplied, so there is no path by which something
        that was never an authorized message becomes a card on a robot.
        """
        import inspect

        parameters = inspect.signature(message_builder.build).parameters
        assert list(parameters)[0] == "message"
        assert parameters["message"].annotation is FamilyMessage
        assert "text" not in parameters

    def test_a_withdrawn_permission_stops_new_cards_and_withdraws_waiting_ones(
        self, db, client, clock, owner, robot, caregiver
    ):
        """PRD 10 section 86's lesson, applied to PRD 9's permissions.

        The message itself stays -- section 101 forbids invalidating it -- and
        it simply stops being queued. Checked when the card is built, not
        remembered from when the message was sent.
        """
        headers, profile_id = owner
        device, _ = robot
        relationship_id, _ = self._a_message(client, owner, caregiver)
        presenter.refresh(db, device, clock.now)
        db.commit()
        assert cards(db, device, "family_message")

        client.patch(
            f"/api/v1/profiles/{profile_id}/caregivers/{relationship_id}/permissions",
            json={"permissions": {"communication": False}},
            headers=headers,
        )
        presenter.refresh(db, device, clock.now)
        db.commit()
        assert cards(db, device, "family_message") == []
        assert db.query(FamilyMessage).count() == 1

    def test_the_preference_is_required(self, db, client, clock, owner, robot, caregiver):
        """Section 24's "robot message display is enabled"."""
        headers, _ = owner
        device, _ = robot
        self._a_message(client, owner, caregiver)
        client.patch(
            f"/api/v1/devices/{device.id}/presentation-preferences",
            json={"family_message_display_enabled": False},
            headers=headers,
        )

        presenter.refresh(db, device, clock.now)
        db.commit()
        assert cards(db, device, "family_message") == []

    def test_a_long_message_is_cut_at_a_word_and_points_at_the_app(
        self, db, client, clock, owner, robot, caregiver
    ):
        """Sections 77 and 78. Not clipped by the screen running out."""
        device, _ = robot
        long_text = (
            "Can you call me when you get a moment this afternoon, I wanted to "
            "ask about the appointment next week and whether you need a lift"
        )
        self._a_message(client, owner, caregiver, text=long_text)

        presenter.refresh(db, device, clock.now)
        db.commit()
        card = cards(db, device, "family_message")[0]
        body = card.payload["body"]
        assert len(body) <= layouts.MESSAGE_MAX
        assert body.endswith("…")
        assert not body.endswith(" …")
        assert card.payload["continue_in_app"] is True
        assert card.payload["truncated"] is True

    def test_a_message_read_in_the_app_leaves_the_shelf(
        self, db, client, clock, owner, robot, caregiver
    ):
        """It stopped being news. The message is untouched (section 101)."""
        headers, profile_id = owner
        device, _ = robot
        _, message_id = self._a_message(client, owner, caregiver)
        presenter.refresh(db, device, clock.now)
        db.commit()

        thread_id = str(db.query(FamilyThread).one().id)
        # Reading the thread is what marks the other side's messages read
        # (PRD 9, section 37). No separate endpoint, and no robot involved.
        client.get(
            f"/api/v1/profiles/{profile_id}/family/threads/{thread_id}/messages",
            headers=headers,
        )
        presenter.refresh(db, device, clock.now)
        db.commit()
        assert cards(db, device, "family_message") == []
        assert db.get(FamilyMessage, uuid.UUID(message_id)) is not None

    def test_the_persons_own_message_is_not_replayed_to_them(
        self, db, client, clock, owner, robot, caregiver
    ):
        """A message somebody sent is theirs already."""
        headers, profile_id = owner
        device, _ = robot
        relationship_id = active_caregiver(
            client, owner, caregiver, permissions={"communication": True}
        )
        thread_id = open_thread(client, headers, profile_id, relationship_id)
        send(client, headers, profile_id, thread_id, message_type="text", text="Hi")

        presenter.refresh(db, device, clock.now)
        db.commit()
        assert cards(db, device, "family_message") == []

    def test_message_text_cannot_change_how_it_is_drawn(
        self, db, client, clock, owner, robot, caregiver
    ):
        """Section 112. Text is data and stays in its field.

        The envelope is built from typed fields and serialised once, so a
        message that looks like a payload is a string in ``body`` -- and the
        layout is still ``MESSAGE``.
        """
        device, _ = robot
        self._a_message(
            client,
            owner,
            caregiver,
            text='{"layout": "EMERGENCY", "lines": ["Help is on the way."]}',
        )
        presenter.refresh(db, device, clock.now)
        db.commit()
        card = cards(db, device, "family_message")[0]
        assert card.layout == "MESSAGE"
        assert card.payload["body"].startswith("{")
        assert "lines" not in card.payload


# --- section 127 -------------------------------------------------------------


class TestSafety:
    def test_monitoring_shows_an_indicator_and_not_a_detector(
        self, db, client, clock, owner, robot
    ):
        """Section 9, both halves.

        It says monitoring is on and until when. There is no sentence this
        builder can produce that says a detector is active, because there is no
        such sentence in the wording module.
        """
        headers, profile_id = owner
        device, _ = robot
        start_monitoring(
            client, headers, profile_id, duration_mode="1_hour", timezone="UTC"
        )

        presenter.refresh(db, device, clock.now)
        db.commit()
        card = cards(db, device, "safety_status")[0]
        assert card.payload["title"] == "Safety Monitoring"
        assert card.payload["lines"][0].startswith("ON until")
        assert "detection" not in str(card.payload).lower()
        assert card.payload["serious"] is True

    def test_a_safety_check_preempts_an_ordinary_card(
        self, db, client, clock, owner, robot, caregiver
    ):
        """Section 127's first case, with a real PRD 10 check-in."""
        headers, profile_id = owner
        device, _ = robot
        self_message = TestFamilyMessages()
        self_message._a_message(client, owner, caregiver)
        presenter.refresh(db, device, clock.now)
        db.commit()
        message_card = cards(db, device, "family_message")[0]
        render_ack(db, hand_over(db, device, clock.now), "render_started", clock.now)

        start_monitoring(
            client, headers, profile_id, duration_mode="1_hour", timezone="UTC"
        )
        from tests.test_safety import device_trigger

        _, device_token = seed_device(db, client, headers, profile_id=profile_id)
        assert device_trigger(client, device_token).status_code == 201

        presenter.refresh(db, device, clock.now)
        db.commit()
        checks = cards(db, device, "safety_check")
        assert checks, "no safety check card"
        assert checks[0].priority < message_card.priority

    def test_an_emergency_card_says_what_prd_10_actually_did(
        self, db, client, clock, owner, robot, caregiver
    ):
        """Sections 8 and 127.

        The caregiver has ``safety_alerts``, so an alert *record* exists and
        the card names them. Calling is not configured -- no provider exists --
        and the card says that too. What it never says is that help is coming.
        """
        headers, profile_id = owner
        device, _ = robot
        active_caregiver(client, owner, caregiver, permissions={"safety_alerts": True})
        client.post(
            f"/api/v1/profiles/{profile_id}/emergency-contacts",
            json={"name": "Spouse", "phone": "+447700900001"},
            headers=headers,
        )
        from tests.test_safety import sos

        assert sos(client, headers, profile_id).status_code == 201

        presenter.refresh(db, device, clock.now)
        db.commit()
        card = cards(db, device, "emergency_status")[0]
        lines = card.payload["lines"]
        assert lines[0] == "Nura is processing your safety request."
        assert "In-app alert created for Ayesha." in lines
        assert "Calling is not configured." in lines
        assert not any("on the way" in line.lower() for line in lines)
        assert card.payload["serious"] is True

    def test_a_resolved_event_clears_the_emergency_card(
        self, db, client, clock, owner, robot
    ):
        """Sections 113 and 127's "resolved event clears emergency mode"."""
        headers, profile_id = owner
        device, _ = robot
        from tests.test_safety import respond, sos

        event = sos(client, headers, profile_id).json()
        presenter.refresh(db, device, clock.now)
        db.commit()
        assert cards(db, device, "emergency_status")

        respond(client, headers, profile_id, event["id"], "im_okay")
        presenter.refresh(db, device, clock.now)
        db.commit()
        remaining = [
            row
            for row in cards(db, device, "emergency_status")
            if "cancelled" not in str(row.payload)
        ]
        assert remaining == []

    def test_a_cancelled_sos_says_so_rather_than_going_quiet(
        self, db, client, clock, owner, robot
    ):
        """Section 114. Nothing is left showing a stale emergency."""
        headers, profile_id = owner
        device, _ = robot
        event = None
        from tests.test_safety import sos

        event = sos(client, headers, profile_id).json()
        presenter.refresh(db, device, clock.now)
        db.commit()

        client.post(
            f"/api/v1/profiles/{profile_id}/safety/events/{event['id']}/cancel",
            json={},
            headers=headers,
        )
        presenter.refresh(db, device, clock.now)
        db.commit()
        notice = [
            row
            for row in cards(db, device, "emergency_status")
            if "cancelled" in str(row.payload).lower()
        ]
        assert notice, "no cancellation notice"
        assert notice[0].payload["lines"][0] == "Emergency request cancelled."
        assert notice[0].expires_at is not None

    def test_a_caregiver_acknowledgement_never_implies_arrival(self):
        """Section 115's clause.

        It says somebody pressed a button in their own app, because that is
        what the backend knows.
        """
        from app.services.robot import wording

        line = wording.acknowledgement_line("Ayesha")
        assert line == "Ayesha acknowledged the safety alert."
        for forbidden in ("on the way", "arriving", "nearby", "coming", "left"):
            assert forbidden not in line.lower()

    def test_drawing_a_screen_never_advances_a_safety_deadline(
        self, db, client, clock, owner, robot
    ):
        """Section 100, as a property of the code rather than a promise.

        PRD 10 escalates when a deadline passes and somebody reads the state.
        A *display* request is not somebody reading the state: if it were, the
        presentation path would be load-bearing for safety. So the robot's
        reconciliation uses ``monitoring.peek_session``, which reports an
        expired session as gone without ending it.
        """
        headers, profile_id = owner
        device, _ = robot
        start_monitoring(
            client, headers, profile_id, duration_mode="30_minutes", timezone="UTC"
        )
        clock.advance(minutes=31)

        presenter.refresh(db, device, clock.now)
        db.commit()
        from app.models import SafetyMonitoringSession

        session = db.query(SafetyMonitoringSession).one()
        assert session.status == "active"
        assert cards(db, device, "safety_status") == []


# --- section 128 -------------------------------------------------------------


class TestAssistant:
    def test_a_long_reply_becomes_a_short_card(self, db, clock, robot):
        """Sections 79 and 80. Concise whatever the app is set to."""
        device, _ = robot
        reply = (
            "You have two things today. Your Metformin is due at eight this "
            "evening, and Dr Khan is at half past three tomorrow afternoon. I "
            "can help you get ready for that whenever you like."
        )
        request = assistant_builder.build(
            reply, source_id="m1", serious=False, speak=False, has_input=False
        )
        body = request.payload["body"]
        assert len(body) <= assistant_builder.ROBOT_REPLY_MAX
        assert request.payload["continue_in_app"] is True
        assert request.layout == "TITLE_BODY"

    def test_a_serious_reply_uses_the_information_layout_and_no_face(self, db):
        """Sections 7 and 26."""
        request = assistant_builder.build(
            "Please speak to a doctor about that.",
            source_id="m1",
            serious=True,
            speak=False,
            has_input=False,
        )
        assert request.layout == "TITLE_BODY"
        assert request.payload["serious"] is True
        assert "face_state" not in request.payload

    def test_the_model_cannot_name_a_layout_or_a_payload(self):
        """Section 71, satisfied by the signature.

        ``build`` takes a string and three booleans. The strongest thing a
        confused or compromised model could do is put its own words on the
        owner's own screen.
        """
        import inspect

        parameters = inspect.signature(assistant_builder.build).parameters
        assert set(parameters) == {
            "text",
            "source_id",
            "serious",
            "speak",
            "has_input",
        }
        assert parameters["text"].annotation is str

    def test_no_reply_is_put_on_the_shelf_during_an_emergency(
        self, db, client, clock, owner, robot
    ):
        """Sections 72 and 128's "assistant cannot override emergency".

        Two things make that true and this is the stronger one: a reply waiting
        politely behind an emergency card would still be Nura composing small
        talk during an escalation, so it is not queued at all.
        """
        headers, profile_id = owner
        device, _ = robot
        from tests.test_safety import sos

        sos(client, headers, profile_id)
        db.commit()

        queued = assistant_builder.queue_reply(
            db,
            device,
            text="Here is what I found.",
            source_id="m1",
            serious=False,
            now=clock.now,
        )
        assert queued is None

    def test_a_reply_never_outranks_a_safety_card(self):
        """The other half: the priority table, read directly."""
        assert queue.PRIORITY["assistant_response"] > queue.PRIORITY["safety_check"]
        assert queue.PRIORITY["assistant_response"] > queue.PRIORITY["emergency_status"]
        assert queue.PRIORITY["assistant_response"] > queue.PRIORITY["safety_status"]


# --- the deliberate absences -------------------------------------------------


class TestWhatIsNotBuilt:
    def test_nothing_queues_a_pairing_code(self):
        """Section 35: do not create a second pairing mechanism.

        PRD 2's code is generated on the robot and drawn by the robot, before
        any device record exists. The type and the ``PAIRING_CODE`` layout are
        in the protocol so the firmware's dispatch and the simulator cover
        them; no builder produces one, and this is the test that keeps it that
        way.
        """
        import pkgutil

        import app.services.robot.builders as builders_package

        sources = []
        for module in pkgutil.iter_modules(builders_package.__path__):
            path = f"{builders_package.__path__[0]}/{module.name}.py"
            with open(path, encoding="utf-8") as handle:
                sources.append((module.name, handle.read()))

        for name, source in sources:
            assert "setup_code" not in source.split('"""')[-1], name

    def test_the_setup_prompt_shows_no_code(self, db, client, clock, owner):
        """The one thing the backend does say to a half-linked robot."""
        headers, profile_id = owner
        device, token = seed_device(
            db, client, headers, profile_id=profile_id, setup_complete=False
        )
        with_display(db, device, clock.now)

        presenter.refresh(db, device, clock.now)
        db.commit()
        card = cards(db, device, "system_status")[0]
        assert card.payload["body"] == "Finish setting up in the Nura app"
        assert "code" not in card.payload


# --- the face, and section 83 ------------------------------------------------


class TestFace:
    def test_an_idle_robot_shows_the_companion_face(self, db, clock, robot):
        """Section 83, and section 5's default state."""
        device, _ = robot
        result = presenter.refresh(db, device, clock.now)
        db.commit()
        assert result.mode.mode == "companion"
        face = cards(db, device, "face_state")[0]
        assert face.payload["face_state"] == "idle"
        assert face.priority == queue.PRIORITY["face_state"]

    def test_a_card_makes_the_mode_information_and_takes_the_face_away(
        self, db, client, clock, owner, robot
    ):
        """Section 6's mode, as a consequence of the queue rather than a state."""
        headers, profile_id = owner
        device, _ = robot
        a_dose_due_now(client, headers, profile_id, clock)

        result = presenter.refresh(db, device, clock.now)
        db.commit()
        assert result.mode.mode == "information"
        assert result.mode.face is None

    def test_sleep_shows_the_sleeping_face(self, db, client, clock, owner, robot):
        """Section 31."""
        headers, profile_id = owner
        device, _ = robot
        client.patch(
            f"/api/v1/profiles/{profile_id}/assistant/preferences",
            json={"mode": "sleep"},
            headers=headers,
        )
        result = presenter.refresh(db, device, clock.now)
        db.commit()
        assert result.mode.mode == "sleep"
        assert cards(db, device, "face_state")[0].payload["face_state"] == "sleeping"

    def test_an_emergency_takes_the_face_away_entirely(
        self, db, client, clock, owner, robot
    ):
        """Sections 7 and 28: serious contexts are never accompanied by a face."""
        headers, profile_id = owner
        device, _ = robot
        from tests.test_safety import sos

        sos(client, headers, profile_id)
        result = presenter.refresh(db, device, clock.now)
        db.commit()
        assert result.mode.mode == "emergency"
        assert result.mode.face is None
        assert cards(db, device, "face_state") == []

    def test_reduced_motion_follows_the_accessibility_setting(
        self, db, client, clock, owner, robot
    ):
        """Sections 30 and 105, and the three states of the column.

        Null means follow; the account's own ``reduce_motion`` is what it
        follows. A deliberate override wins over both.
        """
        headers, _ = owner
        device, _ = robot
        client.patch("/api/v1/me", json={"reduce_motion": True}, headers=headers)

        body = client.get(
            f"/api/v1/devices/{device.id}/presentation-preferences", headers=headers
        ).json()
        assert body["reduced_motion"] is None
        assert body["effective_reduced_motion"] is True

        body = client.patch(
            f"/api/v1/devices/{device.id}/presentation-preferences",
            json={"reduced_motion": False},
            headers=headers,
        ).json()
        assert body["reduced_motion"] is False
        assert body["effective_reduced_motion"] is False

    def test_reduced_motion_turns_the_animation_flag_off_in_the_envelope(
        self, db, clock, robot
    ):
        """Section 29: the firmware gets one field to read, not a rule."""
        device, _ = robot
        row, resolved = preferences.resolved_for(db, device, clock.now)
        row.reduced_motion = True
        db.flush()
        settings = preferences.device_settings(preferences.effective(db, device, row))
        assert settings.reduced_motion is True
        assert settings.face_animation is False


# --- sections 51 to 54, and 100 to 102 ---------------------------------------


class TestAdditive:
    def test_a_failing_robot_cannot_fail_an_assistant_reply(self, db, clock, owner):
        """Sections 71, 100 and the whole point of ``presentations``.

        The one door into the robot from the rest of the product swallows
        failures, because the caller is in the middle of answering somebody.
        """
        from app.services.robot import presentations

        _, profile_id = owner

        def explode(device):
            raise RuntimeError("the display driver caught fire")

        count = presentations._safely("test", explode, db, uuid.UUID(profile_id))
        assert count == 0

    def test_nothing_outside_the_robot_package_imports_it(self):
        """The architectural claim, checked rather than asserted in prose.

        PRD 11 reconciles from state rather than being notified, so no service
        that owns a dose, an appointment, a message, a safety event, a task or
        a routine needs to know the robot exists. The assistant is the single
        exception, because a reply is an utterance rather than a state.

        PRD 12 made this check sharper. It looks for an *import* now, not for
        any mention of the package: ``services/productivity`` has a comment
        explaining where its robot card gets PRD 11's "Use the Nura app to
        respond." sentence from, and a comment that names the robot is not a
        dependency on it. The thing worth forbidding is code that reaches in,
        and that is what an import statement is.
        """
        import pathlib

        def reaches_in(source: str) -> bool:
            """Whether this file imports the robot package.

            Line by line rather than one regex, because the three shapes worth
            catching are easier to read as three conditions than as one
            pattern: ``from app.services.robot import x``,
            ``import app.services.robot`` and ``from app.services import
            robot``.
            """
            for line in source.splitlines():
                statement = line.strip()
                if not statement.startswith(("from ", "import ")):
                    continue
                if "app.services.robot" in statement:
                    return True
                if statement.startswith("from app.services import") and (
                    "robot" in statement
                ):
                    return True
            return False

        root = pathlib.Path("app/services")
        offenders = []
        for path in root.rglob("*.py"):
            if "robot" in path.parts:
                continue
            if reaches_in(path.read_text(encoding="utf-8")):
                offenders.append(path.as_posix())
        assert offenders == ["app/services/assistant/service.py"]
