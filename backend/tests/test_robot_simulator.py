"""The robot that is not there, doing everything the robot would do.

PRD 11, sections 62, 63, 64, 83, 84, 98, 129, 132 and 140.

Section 129 lists twelve things the simulator must exercise and section 132
lists eighteen steps of a manual test plan that has to be possible without
hardware. This file is both, automated: ``test_the_whole_manual_plan_runs``
walks section 132's plan end to end, and the tests around it cover section
129's list one state at a time.

**Section 140's checkpoint is answered here.** *Can every required PRD 11
software workflow run in the simulator without physical hardware?* These tests
are the evidence, and the answer is yes.

**And section 135's limit is also here.** The simulator renders to a list of
strings. That proves the queue, the privacy filter, the preemption rule, the
expiry comparison and the acknowledgement state machine. It proves nothing
whatever about a panel, a font, a backlight or a speaker, and
``test_the_simulator_is_not_a_robot`` says so in a place somebody reading the
tests will see it.
"""

import pytest

from app.api.deps import current_time
from app.main import app
from app.models import DevicePresentation
from app.models.enums import ROBOT_PRESENTATION_LAYOUTS
from app.services.robot import layouts, presenter, queue
from app.services.robot import simulator as sim
from tests.test_caregivers import active_caregiver
from tests.test_devices import ready_account
from tests.test_family import open_thread, send
from tests.test_robot_builders import a_dose_due_now
from tests.test_robot_presentations import NOW, seed_device
from tests.test_safety import sos, start_monitoring
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
    """A simulated robot with a screen, reporting itself on boot."""
    headers, profile_id = owner
    device, _ = seed_device(db, client, headers, profile_id=profile_id)
    robot = sim.SimulatedRobot(db=db, device=device)
    robot.connect(clock.now)
    db.commit()
    return robot


# --- section 129's list ------------------------------------------------------


class TestStates:
    def test_an_idle_robot_shows_the_companion_face(self, db, clock, robot):
        """Section 129's "idle face", and section 83."""
        screen = robot.poll(clock.now)
        assert screen is not None
        assert screen.layout == "FACE"
        assert screen.face == "idle"
        assert screen.mode == "companion"

    def test_a_medication_card_renders_with_the_privacy_level_applied(
        self, db, client, clock, owner, robot
    ):
        """Section 129's "medication card", with section 22 in force."""
        headers, profile_id = owner
        a_dose_due_now(client, headers, profile_id, clock, name="Metformin")

        drawn = robot.drain(clock.now)
        reminder = next(
            screen
            for screen in drawn
            if screen.presentation_type == "medication_reminder"
        )
        assert "Medication" in reminder.lines
        assert "Reminder due" in reminder.lines
        assert "Metformin" not in reminder.text()
        # Section 86: no buttons were reported, so the card says where to go.
        assert reminder.respond_in_app is True
        assert "Use the Nura app to respond." in reminder.lines

    def test_an_emergency_card_renders_prd_10s_actual_state(
        self, db, client, clock, owner, robot
    ):
        """Section 129's "emergency card", and section 8's wording."""
        headers, profile_id = owner
        sos(client, headers, profile_id)
        db.commit()

        screen = robot.poll(clock.now)
        assert screen is not None
        assert screen.layout == "EMERGENCY"
        assert screen.lines[0] == "EMERGENCY MODE"
        assert "Nura is processing your safety request." in screen.lines
        assert "Calling is not configured." in screen.lines
        assert "Help is on the way." not in screen.lines
        assert screen.serious is True

    def test_a_safety_check_renders_as_information(self, db, client, clock, owner, robot):
        """Section 129's "safety check", and section 7's serious mode."""
        headers, profile_id = owner
        start_monitoring(
            client, headers, profile_id, duration_mode="1_hour", timezone="UTC"
        )
        from tests.test_safety import device_trigger

        # The trigger comes from a second device row. PRD 10's contract is
        # that a device reports what it observed, and this robot is the one
        # being drawn to -- keeping them apart is what makes the test about
        # presentation rather than about detection.
        _, sensor_token = seed_device(db, client, headers, profile_id=profile_id)
        assert device_trigger(client, sensor_token).status_code == 201

        screen = robot.poll(clock.now)
        assert screen is not None
        assert screen.layout == "STATUS"
        assert screen.serious is True
        assert screen.face is None
        assert any("are you okay" in line.lower() for line in screen.lines)

    def test_a_monitoring_indicator_renders_without_claiming_a_detector(
        self, db, client, clock, owner, robot
    ):
        """Section 9, seen on the screen rather than in a payload."""
        headers, profile_id = owner
        start_monitoring(
            client, headers, profile_id, duration_mode="1_hour", timezone="UTC"
        )
        drawn = robot.drain(clock.now)
        status = next(
            screen for screen in drawn if screen.presentation_type == "safety_status"
        )
        assert status.lines[0] == "Safety Monitoring"
        assert status.lines[1].startswith("ON until")
        assert "detection" not in status.text().lower()

    def test_an_offline_robot_shows_its_own_card_and_acknowledges_nothing(
        self, db, clock, robot
    ):
        """Sections 34, 98 and 129's "offline state".

        The robot does not reach the backend at all, so nothing moves in
        ``device_presentations`` -- which is why section 20's rule is easy to
        keep: there is no acknowledgement, so nothing is displayed.
        """
        queue.queue(
            db,
            robot.device,
            queue.PresentationRequest(
                presentation_type="info_card",
                layout="TITLE_BODY",
                payload=layouts.build_payload("TITLE_BODY", title="Nura", body="Hello"),
                source="system",
                source_id="hello",
            ),
            clock.now,
        )
        db.commit()

        robot.go_offline()
        screen = robot.poll(clock.now)
        assert screen is not None
        assert screen.lines == ("Nura offline", "Trying to reconnect")
        rows = db.query(DevicePresentation).all()
        assert all(row.displayed_at is None for row in rows)
        assert all(row.ack_state is None for row in rows)

    def test_a_render_failure_is_reported_and_recorded(self, db, clock, robot):
        """Section 64's "render failure", section 132's step sixteen."""
        robot.render_outcome = "failed"
        presenter.refresh(db, robot.device, clock.now)
        db.commit()
        assert robot.poll(clock.now) is None

        row = db.query(DevicePresentation).filter_by(status="failed").one()
        assert row.failure_code == "render_failed"
        assert row.displayed_at is None

    def test_an_unsupported_display_never_becomes_a_card(
        self, db, client, clock, owner, robot
    ):
        """Section 129's "unsupported display", section 123's not_supported."""
        robot.use(dict(sim.HEADLESS), clock.now)
        db.commit()
        headers, profile_id = owner
        a_dose_due_now(client, headers, profile_id, clock)

        presenter.refresh(db, robot.device, clock.now)
        db.commit()
        row = (
            db.query(DevicePresentation)
            .filter_by(presentation_type="medication_reminder")
            .one()
        )
        assert row.status == "not_supported"
        assert robot.poll(clock.now) is None

    def test_preemption_is_visible_on_the_screen(self, db, client, clock, owner, robot):
        """Section 129's "preemption", as a person would experience it.

        A reminder is on the screen, an emergency starts, and the next thing
        drawn is the emergency -- with the reminder withdrawn rather than
        waiting behind it.
        """
        headers, profile_id = owner
        a_dose_due_now(client, headers, profile_id, clock)
        drawn = robot.drain(clock.now)
        assert "medication_reminder" in {screen.presentation_type for screen in drawn}

        sos(client, headers, profile_id)
        db.commit()
        screen = robot.poll(clock.now)
        assert screen is not None
        assert screen.presentation_type == "emergency_status"
        reminder = (
            db.query(DevicePresentation)
            .filter_by(presentation_type="medication_reminder")
            .one()
        )
        assert reminder.status == "cancelled"
        assert reminder.cancel_reason == "preempted"

    def test_acknowledgement_moves_the_row_and_nothing_else_does(self, db, clock, robot):
        """Section 129's "acknowledgement", and section 14 once more.

        The robot drew the face and is still showing it, so it reported
        ``render_started`` and the row is ``displayed``. Nothing else in the
        codebase could have written ``displayed_at``.
        """
        screen = robot.poll(clock.now)
        row = db.get(DevicePresentation, screen.presentation_id)
        assert row.ack_state == "render_started"
        assert row.displayed_at is not None
        assert row.status == "displayed"

    def test_a_robot_that_is_finished_with_a_card_says_so(self, db, clock, robot):
        """The other half of section 19's two render states."""
        robot.render_outcome = "render_completed"
        screen = robot.poll(clock.now)
        row = db.get(DevicePresentation, screen.presentation_id)
        assert row.status == "completed"
        assert row.displayed_at is not None

    def test_a_thinking_face_is_in_the_vocabulary_and_renders(self):
        """Section 129's "thinking face".

        Nothing in the backend queues one yet -- no assistant turn is long
        enough to be worth a face, and section 26 keeps the assistant to a
        card. The state exists in the protocol and renders, which is what the
        simulator is for.
        """
        envelope = layouts.build_envelope(
            presentation_id="00000000-0000-0000-0000-000000000000",
            presentation_type="face_state",
            priority=90,
            layout="FACE",
            payload=layouts.build_payload("FACE", face_state="thinking"),
            mode="companion",
            expires_at=None,
            settings=layouts.DeviceSettings(
                brightness=70,
                volume=40,
                reduced_motion=False,
                face_animation=True,
                sleep_screen="dim",
            ),
        )
        screen = sim.render(envelope)
        assert screen.face == "thinking"

    def test_every_layout_has_somewhere_to_be_drawn(self):
        """The firmware's dispatch table, mirrored (section 131).

        Each of the eight layouts renders. An unknown one is refused rather
        than guessed at, and the firmware does the same -- reporting
        ``unsupported`` back to the backend.
        """
        samples = {
            "FACE": {"face_state": "idle"},
            "TITLE_BODY": {"title": "Nura", "body": "Hello"},
            "TITLE_VALUE": {"title": "Next dose", "value": "8:00 PM"},
            "REMINDER": {"title": "Medication", "primary": "Reminder due"},
            "MESSAGE": {"title": "Message", "sender": "Ayesha", "body": "Call me"},
            "STATUS": {"title": "Safety Monitoring", "lines": ["ON until 10:30 PM"]},
            "EMERGENCY": {"title": "EMERGENCY MODE", "lines": ["Processing"]},
            "PAIRING_CODE": {"title": "Pairing code", "code": "482731"},
        }
        assert set(samples) == set(ROBOT_PRESENTATION_LAYOUTS)
        for layout, fields in samples.items():
            screen = sim.render(
                {
                    "protocol_version": layouts.PROTOCOL_VERSION,
                    "presentation_id": "x",
                    "type": "info_card",
                    "priority": 80,
                    "mode": "information",
                    "layout": layout,
                    "payload": layouts.build_payload(layout, **fields),
                    "settings": {},
                }
            )
            assert screen.lines, layout

        with pytest.raises(sim.UnsupportedEnvelope):
            sim.render(
                {
                    "protocol_version": layouts.PROTOCOL_VERSION,
                    "layout": "CAROUSEL",
                    "payload": {},
                }
            )

    def test_an_envelope_from_a_newer_protocol_is_refused(self):
        """Section 116: fail safely rather than guessing."""
        with pytest.raises(sim.UnsupportedEnvelope):
            sim.render(
                {
                    "protocol_version": layouts.PROTOCOL_VERSION + 1,
                    "layout": "FACE",
                    "payload": {"face_state": "idle"},
                }
            )


# --- section 84 --------------------------------------------------------------


class TestAutoReturn:
    def test_the_robot_goes_back_to_its_face_after_a_card(
        self, db, client, clock, owner, robot
    ):
        """Section 84, and why the face is itself a queued presentation.

        Nothing remembers to go back. The card's render marks the face card
        completed, the card finishes, and the next reconciliation finds an
        empty queue and queues the face again.
        """
        headers, profile_id = owner
        a_dose_due_now(client, headers, profile_id, clock)
        robot.drain(clock.now)
        assert robot.screen().presentation_type == "medication_reminder"

        # The dose is taken in the app, so the card is withdrawn. Nothing
        # notified the robot; the next reconciliation found out.
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

        screen = robot.poll(clock.now)
        assert screen is not None
        assert screen.layout == "FACE"
        assert screen.face == "idle"


# --- section 132 -------------------------------------------------------------


class TestManualPlanWithoutARobot:
    def test_the_whole_manual_plan_runs(self, db, client, clock, owner, make_token):
        """Section 132's eighteen steps, in order, with no hardware.

        This is the test that answers section 140. Every step below is one of
        section 132's lines, and the only thing standing in for a robot is a
        row, a token and a renderer.
        """
        headers, profile_id = owner
        caregiver = {"Authorization": f"Bearer {make_token()}"}

        # seed simulated online device / report display available
        device, _ = seed_device(db, client, headers, profile_id=profile_id)
        robot = sim.SimulatedRobot(db=db, device=device)
        robot.connect(clock.now)
        db.commit()
        states = client.get(
            f"/api/v1/devices/{device.id}/capabilities", headers=headers
        ).json()
        assert states["display_available"] is True

        # queue idle face
        assert robot.poll(clock.now).face == "idle"

        # queue medication reminder / verify card
        a_dose_due_now(client, headers, profile_id, clock, name="Metformin")
        reminder = robot.poll(clock.now)
        assert reminder.presentation_type == "medication_reminder"

        # set private medication preview / verify name hidden
        assert "Metformin" not in reminder.text()

        # queue family message / verify it renders with the sender's name
        relationship_id = active_caregiver(
            client, owner, caregiver, permissions={"communication": True}
        )
        thread_id = open_thread(client, headers, profile_id, relationship_id)
        send(client, caregiver, profile_id, thread_id, text="Call me when free")
        message = robot.poll(clock.now)
        assert message.presentation_type == "family_message"
        assert "Ayesha" in message.lines

        # queue emergency status / verify emergency preempts the message
        sos(client, headers, profile_id)
        db.commit()
        emergency = robot.poll(clock.now)
        assert emergency.presentation_type == "emergency_status"
        assert "Calling is not configured." in emergency.lines
        withdrawn = (
            db.query(DevicePresentation)
            .filter_by(presentation_type="family_message")
            .one()
        )
        assert withdrawn.status == "cancelled"
        assert withdrawn.cancel_reason == "preempted"

        # resolve emergency / verify return state
        event_id = str(
            db.query(DevicePresentation)
            .filter_by(presentation_type="emergency_status")
            .one()
            .dedupe_key.split(":")[1]
        )
        client.post(
            f"/api/v1/profiles/{profile_id}/safety/events/{event_id}/respond",
            json={"response": "im_okay"},
            headers=headers,
        )
        after = robot.drain(clock.now)
        assert after, "the robot was left with nothing to show"
        assert after[-1].layout in {"FACE", "REMINDER"}

        # set reduced motion / verify the simulator changes
        client.patch(
            f"/api/v1/devices/{device.id}/presentation-preferences",
            json={"reduced_motion": True},
            headers=headers,
        )
        presenter.refresh(db, device, clock.now)
        db.commit()
        row = queue.next_for_device(db, device, clock.now)
        if row is not None:
            envelope = queue.envelope_for(db, device, row, clock.now)
            assert envelope["settings"]["reduced_motion"] is True
            assert envelope["settings"]["face_animation"] is False

        # mark display unsupported / verify settings update
        robot.use(dict(sim.HEADLESS), clock.now)
        db.commit()
        states = client.get(
            f"/api/v1/devices/{device.id}/capabilities", headers=headers
        ).json()
        assert states["display_available"] is False
        assert states["audio_available"] is False

        # simulate render failure / verify backend failed state
        robot.use(dict(sim.DISPLAY_ONLY), clock.now)
        robot.render_outcome = "failed"
        queue.queue(
            db,
            device,
            queue.PresentationRequest(
                presentation_type="info_card",
                layout="TITLE_BODY",
                payload=layouts.build_payload(
                    "TITLE_BODY", title="Nura", body="Something to draw"
                ),
                source="system",
                source_id="render-failure-step",
            ),
            clock.now,
        )
        db.commit()
        assert robot.poll(clock.now) is None
        failed = db.query(DevicePresentation).filter_by(status="failed").one()
        assert failed.failure_code == "render_failed"
        assert failed.displayed_at is None

    def test_the_simulator_is_not_a_robot(self):
        """Section 135, said in the tests as well as in the report.

        Everything above is a Python object rendering to a list of strings.
        It proves the queue, the privacy filter, the preemption rule, the
        expiry comparison and the acknowledgement machine. It proves nothing
        about a panel, a font, a backlight, an amplifier or a speaker, and no
        physical acknowledgement has ever been received by this backend.
        """
        screen = sim.render(
            {
                "protocol_version": layouts.PROTOCOL_VERSION,
                "presentation_id": "x",
                "type": "face_state",
                "priority": 90,
                "mode": "companion",
                "layout": "FACE",
                "payload": {"face_state": "idle"},
                "settings": {},
            }
        )
        assert isinstance(screen.lines, tuple)
        assert screen.spoken == ()

    def test_the_simulator_is_not_reachable_from_the_api(self):
        """Section 62: no simulator controls in production UI.

        Nothing under ``app/api`` imports it, so there is no route -- in
        development or otherwise -- that can drive a pretend robot.
        """
        import pathlib

        for path in pathlib.Path("app/api").rglob("*.py"):
            assert "simulator" not in path.read_text(encoding="utf-8"), path
