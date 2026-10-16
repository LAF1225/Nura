"""Safety Monitoring, SOS, check-ins and safety history (PRD 10, sections 111, 114).

Every test runs against the real app, the real migrations and a real PostgreSQL
database, with genuinely signed tokens. There is no mocked authorization: when
a request is refused, the production dependency refused it.

**No hardware is involved anywhere in this file.** PRD 10 section 115 forbids
any acceptance test needing a real ESP32, BLE, a camera, a microphone, a
speaker, a display, a fall detector or a heartbeat -- and the device-trigger
contract is exercised with an authenticated simulated device request, which is
what section 115 says to do instead. Nothing here has ever run on hardware and
nothing in this file claims it has.

**No clock is real either.** Section 82 forbids sleeping for forty-five
seconds, so the ``clock`` fixture is moved forward and the deadlines are
columns the code compares against it. The *timing* tests live in
``test_safety_worker.py``; this file is about state.

Four groups worth finding on purpose.

``TestMonitoring`` covers section 4's "never silently enabled" and section 61's
"do not silently extend".

``TestTriggers`` is section 21 versus section 22 in a pair of tests: a manual
SOS works with monitoring off, and a passive trigger does not.

``TestCheckIn`` covers the three answers and the one that is allowed to arrive
late (section 126).

``TestCapabilities`` is section 64's reason for existing: the UI is driven by
what the backend can actually do, and here that is checked against the things
themselves rather than against a constant.
"""

import secrets
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.api.deps import current_time
from app.main import app
from app.models import Device, SafetyEvent
from app.models.enums import (
    SAFETY_EVENT_TYPES,
    SAFETY_EVENT_TYPES_REQUIRING_MONITORING,
)
from app.services.devices import hash_secret
from app.services.safety import wording
from tests.test_devices import ready_account
from tests.test_today import Clock

#: A Monday evening. Fixed so nothing drifts mid-test.
NOW = datetime(2026, 9, 28, 18, 42, tzinfo=UTC)


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


def safety_url(profile_id: str) -> str:
    return f"/api/v1/profiles/{profile_id}/safety"


def start_monitoring(client, headers, profile_id: str, **body):
    payload = {"duration_mode": "30_minutes", "timezone": "Europe/London"}
    payload.update(body)
    return client.post(
        f"{safety_url(profile_id)}/monitoring/start", json=payload, headers=headers
    )


def status(client, headers, profile_id: str):
    return client.get(f"{safety_url(profile_id)}/status", headers=headers).json()


def sos(client, headers, profile_id: str, **body):
    return client.post(f"{safety_url(profile_id)}/sos", json=body, headers=headers)


def respond(client, headers, profile_id: str, event_id: str, response: str):
    return client.post(
        f"{safety_url(profile_id)}/events/{event_id}/respond",
        json={"response": response},
        headers=headers,
    )


def seed_device(db, client, headers, *, profile_id: str | None) -> str:
    """A claimed robot with a known device token, and no hardware anywhere.

    The row stores the hash and the test holds the plaintext, which is exactly
    the state a real claim leaves behind (PRD 2, section 55). There is no
    robot: this is a database row and a string.
    """
    token = f"nura-device-{secrets.token_hex(16)}"
    account_id = client.get("/api/v1/me", headers=headers).json()["id"]
    db.add(
        Device(
            hardware_id=f"NURA-{secrets.token_hex(6).upper()}",
            display_name="Nura",
            claimed_by_account_id=uuid.UUID(account_id),
            owner_profile_id=None if profile_id is None else uuid.UUID(profile_id),
            provisioning_status="claimed",
            bootstrap_secret_hash=hash_secret(secrets.token_hex(32)),
            device_token_hash=hash_secret(token),
            claimed_at=NOW - timedelta(hours=4),
            last_seen_at=NOW,
        )
    )
    db.commit()
    return token


def device_trigger(client, device_token: str, **body):
    payload = {"event_type": "possible_fall", "idempotency_key": secrets.token_hex(8)}
    payload.update(body)
    return client.post(
        "/api/v1/device-actions/safety-events",
        json=payload,
        headers={"Authorization": f"Bearer {device_token}"},
    )


# --- the vocabulary itself ---------------------------------------------------


class TestNeutralWording:
    def test_every_sensor_observed_type_says_possible(self):
        """Sections 16 and 52, enforced against the tuple rather than hoped for.

        The word ``possible`` is mandatory for anything a sensor observed, and
        the alternatives section 52 forbids -- "seizure detected", "fall
        confirmed" -- are impossible to store because no such value exists.
        """
        for event_type in SAFETY_EVENT_TYPES_REQUIRING_MONITORING:
            assert event_type.startswith("possible_"), event_type

    def test_no_label_anywhere_states_a_medical_cause(self):
        """Section 52, checked over every string in the wording module.

        This is the test section 120 is really asking for: with all the prose
        in one module, "nothing diagnoses" is exhaustive rather than a spot
        check.
        """
        forbidden = (
            "seizure detected",
            "fall confirmed",
            "vomiting detected",
            "unconscious",
            "lost consciousness",
            "diagnos",
        )
        for text in _every_sentence():
            lowered = text.lower()
            for phrase in forbidden:
                assert phrase not in lowered, f"{phrase!r} in {text!r}"

    def test_no_sentence_claims_somebody_was_reached(self):
        """Sections 38 and 42.

        "Caregiver notified" and "Ayesha has been contacted" are section 38's
        and section 42's own bad examples. Neither can be produced, because
        neither verb appears anywhere in the module that writes every sentence.
        """
        for text in _every_sentence():
            lowered = text.lower()
            for claim in ("notified", "has been contacted", "we called", "sms sent"):
                assert claim not in lowered, f"{claim!r} in {text!r}"

    def test_no_sentence_guarantees_anything(self):
        """Section 72: never display a guarantee of emergency response."""
        for text in _every_sentence():
            lowered = text.lower()
            assert "guarantee" not in lowered
            assert "will reach" not in lowered


def _every_sentence() -> list[str]:
    """Every user-facing string the safety features can produce."""
    texts: list[str] = []
    for name in dir(wording):
        if name.startswith("_"):
            continue
        value = getattr(wording, name)
        if isinstance(value, str):
            texts.append(value)
        elif isinstance(value, dict):
            texts.extend(str(item) for item in value.values())
    texts.append(wording.check_in_prompt("Ada"))
    texts.append(wording.no_response_sentence(45))
    for event_type in SAFETY_EVENT_TYPES:
        texts.append(
            wording.caregiver_alert_sentence(
                event_type=event_type, when=NOW, zone="UTC", no_response_seconds=45
            )
        )
    for channel in ("in_app", "push", "sms_future", "voice_call_future"):
        for state in ("attempted", "not_configured", "failed", "skipped", "delivered"):
            texts.append(
                wording.escalation_line(label="Ayesha", channel=channel, status=state)
            )
    return texts


# --- monitoring --------------------------------------------------------------


class TestMonitoring:
    def test_monitoring_starts_off(self, client, owner, clock):
        """Section 4: never silently enabled."""
        headers, profile_id = owner
        body = status(client, headers, profile_id)
        assert body["monitoring"] is None
        assert body["monitoring_sentence"] == "Safety Monitoring is off."
        assert body["emergency_mode"] is False

    def test_starting_records_the_duration_the_user_chose(self, client, owner, clock):
        """Sections 5 and 9: the mode is stored, not only the end instant.

        Section 5 says not to invent a hidden monitoring period. Keeping the
        mode means a session can always say *why* it ends when it does, rather
        than leaving somebody to reverse-engineer it from a timestamp.
        """
        headers, profile_id = owner
        created = start_monitoring(client, headers, profile_id, duration_mode="1_hour")
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["duration_mode"] == "1_hour"
        assert body["status"] == "active"
        assert datetime.fromisoformat(body["ends_at"]) == NOW + timedelta(hours=1)
        assert body["response_timeout_seconds"] == 45

    def test_the_server_decides_when_it_ends(self, client, owner, clock):
        """Section 61, enforced by the request having nowhere to say otherwise.

        A client cannot send ``ends_at``; the schema has no such field, so a
        phone with a wrong clock cannot arrange to be monitored for a week.
        """
        headers, profile_id = owner
        response = client.post(
            f"{safety_url(profile_id)}/monitoring/start",
            json={
                "duration_mode": "30_minutes",
                "timezone": "UTC",
                "ends_at": "2030-01-01T00:00:00Z",
            },
            headers=headers,
        )
        assert response.status_code == 201
        assert datetime.fromisoformat(response.json()["ends_at"]) == NOW + timedelta(
            minutes=30
        )

    def test_until_turned_off_has_no_end(self, client, owner, clock):
        """Section 5's fourth preset, and the one null ``ends_at`` that is honest."""
        headers, profile_id = owner
        body = start_monitoring(
            client, headers, profile_id, duration_mode="until_turned_off"
        ).json()
        assert body["ends_at"] is None
        assert (
            "until you turn it off"
            in status(client, headers, profile_id)["monitoring_sentence"]
        )

    def test_until_bedtime_needs_a_bedtime(self, client, owner, clock):
        """Section 6: bedtime comes from an explicit setting, never inferred.

        Refusing with a stable code is what lets the app ask for a time. A
        service that guessed ten o'clock would be inventing the hidden period
        section 5 forbids, in a politer costume.
        """
        headers, profile_id = owner
        refused = start_monitoring(
            client, headers, profile_id, duration_mode="until_bedtime"
        )
        assert refused.status_code == 409
        assert refused.json()["detail"]["code"] == "bedtime_not_set"

        client.patch("/api/v1/me", json={"safety_bedtime": "22:30"}, headers=headers)
        created = start_monitoring(
            client,
            headers,
            profile_id,
            duration_mode="until_bedtime",
            timezone="Europe/London",
        )
        assert created.status_code == 201
        # 18:42 UTC is 19:42 London, so bedtime is later the same evening.
        ends = datetime.fromisoformat(created.json()["ends_at"])
        assert ends == datetime(2026, 9, 28, 21, 30, tzinfo=UTC)

    def test_monitoring_expires_without_anything_running(self, client, owner, clock):
        """Section 61 and section 80's state-correctness half.

        No worker runs in this test. The status endpoint advances the clock's
        consequences itself, so the state is right the moment anybody looks --
        which is the claim, separate from the *timeliness* claim the worker
        tests make.
        """
        headers, profile_id = owner
        start_monitoring(client, headers, profile_id, duration_mode="30_minutes")
        clock.now = NOW + timedelta(minutes=31)
        body = status(client, headers, profile_id)
        assert body["monitoring"] is None

    def test_stopping_is_immediate_when_nothing_is_happening(self, client, owner, clock):
        """Section 62's first half."""
        headers, profile_id = owner
        start_monitoring(client, headers, profile_id)
        stopped = client.post(
            f"{safety_url(profile_id)}/monitoring/stop", headers=headers
        )
        assert stopped.status_code == 200
        assert stopped.json()["monitoring"] is None

    def test_stopping_during_an_event_needs_confirmation(self, client, owner, clock):
        """Section 62's second half.

        And stopping monitoring does not cancel the event: somebody turning
        monitoring off has not said they are all right, and section 45 gives
        cancelling an emergency its own route with its own confirmation.
        """
        headers, profile_id = owner
        start_monitoring(client, headers, profile_id)
        event = sos(client, headers, profile_id).json()

        refused = client.post(
            f"{safety_url(profile_id)}/monitoring/stop", headers=headers
        )
        assert refused.status_code == 409
        assert refused.json()["detail"]["code"] == "safety_event_in_progress"

        confirmed = client.post(
            f"{safety_url(profile_id)}/monitoring/stop?confirm_active_event=true",
            headers=headers,
        )
        assert confirmed.status_code == 200
        assert confirmed.json()["monitoring"] is None
        assert confirmed.json()["active_event"]["id"] == event["id"]

    def test_starting_twice_leaves_one_session(self, client, owner, clock):
        """Somebody who pressed Start twice meant to be monitored.

        The first session ends as ``superseded`` rather than the second
        failing: a partial unique index makes two active sessions impossible,
        and an error message would be a worse answer than one session.
        """
        headers, profile_id = owner
        first = start_monitoring(client, headers, profile_id).json()
        second = start_monitoring(
            client, headers, profile_id, duration_mode="1_hour"
        ).json()
        assert first["id"] != second["id"]
        assert status(client, headers, profile_id)["monitoring"]["id"] == second["id"]

    def test_a_caregiver_cannot_start_monitoring(self, client, owner, make_token, clock):
        """Section 10, and it is the dependency that refuses, not a check.

        ``OwnedProfile`` walks ``account_profile_roles``, which a caregiver has
        no row in -- so this is 404 for the same reason every PRD 0-9 route is.
        """
        from tests.test_caregivers import active_caregiver

        caregiver = {"Authorization": f"Bearer {make_token()}"}
        active_caregiver(client, owner, caregiver, permissions={"safety_alerts": True})
        _, profile_id = owner
        assert start_monitoring(client, caregiver, profile_id).status_code == 404
        assert (
            client.get(f"{safety_url(profile_id)}/status", headers=caregiver).status_code
            == 404
        )


# --- triggers ----------------------------------------------------------------


class TestTriggers:
    def test_manual_sos_works_with_monitoring_off(self, client, owner, clock):
        """Section 21, and section 12's "skip the normal countdown".

        Escalation happens inside the request, so the response already carries
        the list the app shows -- there is no countdown to wait out and no
        second call to make.
        """
        headers, profile_id = owner
        assert status(client, headers, profile_id)["monitoring"] is None
        created = sos(client, headers, profile_id)
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["event_type"] == "manual_sos"
        assert body["status"] == "escalated"
        assert body["escalation_started_at"] is not None

    def test_a_passive_trigger_is_refused_while_monitoring_is_off(
        self, client, owner, db, clock
    ):
        """Section 22, and section 4 behind it.

        Nura does not watch while Safety Monitoring is off, so an event
        arriving then is refused with a reason a device can act on -- rather
        than quietly processed, which would be monitoring somebody who did not
        ask.
        """
        headers, profile_id = owner
        token = seed_device(db, client, headers, profile_id=profile_id)
        refused = device_trigger(client, token)
        assert refused.status_code == 409
        assert refused.json()["detail"]["code"] == "monitoring_not_active"
        assert db.query(SafetyEvent).count() == 0

    def test_a_passive_trigger_is_accepted_while_monitoring_is_on(
        self, client, owner, db, clock
    ):
        """Section 22's other half, and section 23's check-in.

        The event begins a check rather than escalating: section 23 says ask
        first, and the deadline is a stored column rather than a timer.
        """
        headers, profile_id = owner
        token = seed_device(db, client, headers, profile_id=profile_id)
        start_monitoring(client, headers, profile_id)

        accepted = device_trigger(client, token)
        assert accepted.status_code == 201, accepted.text
        assert accepted.json()["status"] == "checking_user"

        current = status(client, headers, profile_id)["active_event"]
        assert current["event_type"] == "possible_fall"
        assert current["event_label"] == "Possible fall"
        deadline = datetime.fromisoformat(current["response_deadline_at"])
        assert deadline == NOW + timedelta(seconds=45)

    def test_a_device_cannot_report_for_another_profile(
        self, client, owner, make_token, db, clock
    ):
        """Sections 20 and 105: the profile comes from the device, never a body.

        There is no profile field on the request model, so this test sends the
        nearest thing -- a device linked to nobody -- and gets the same 404
        anybody guessing ids would get.
        """
        headers, profile_id = owner
        other = ready_account(client, make_token)
        token = seed_device(db, client, other, profile_id=None)
        start_monitoring(client, headers, profile_id)
        assert device_trigger(client, token).status_code == 404

    def test_a_device_retry_does_not_make_a_second_event(self, client, owner, db, clock):
        """Section 20's duplicate protection, with the same idempotency key."""
        headers, profile_id = owner
        token = seed_device(db, client, headers, profile_id=profile_id)
        start_monitoring(client, headers, profile_id)

        key = "trigger-1"
        first = device_trigger(client, token, idempotency_key=key)
        second = device_trigger(client, token, idempotency_key=key)
        assert first.json()["event_id"] == second.json()["event_id"]
        assert first.json()["created"] is True
        assert second.json()["created"] is False
        assert db.query(SafetyEvent).count() == 1

    def test_pressing_sos_twice_is_one_emergency(self, client, owner, db, clock):
        """Section 77, and without the client having to remember a key.

        Two guards: an explicit ``client_event_id`` if one was sent, and
        otherwise any event still live for this profile. Somebody pressing SOS
        again because nothing visibly happened must not alert everybody twice.
        """
        headers, profile_id = owner
        first = sos(client, headers, profile_id).json()
        second = sos(client, headers, profile_id).json()
        assert first["id"] == second["id"]
        assert db.query(SafetyEvent).count() == 1

    def test_a_client_cannot_claim_a_sensor_event(self, client, owner, clock):
        """Sections 16 and 57, refused by the schema before anything runs.

        ``SosEventType`` has two values. A client posting ``possible_fall`` is
        a 422 from pydantic, not a decision any safety code makes -- the same
        way PRD 9 made a forbidden suggestion unrepresentable.
        """
        headers, profile_id = owner
        start_monitoring(client, headers, profile_id)
        for event_type in (
            "possible_fall",
            "possible_seizure_like_activity",
            "test_event",
        ):
            refused = sos(client, headers, profile_id, event_type=event_type)
            assert refused.status_code == 422, event_type

    def test_the_emergency_phrase_contract_behaves_like_sos(self, client, owner, clock):
        """Section 14: the phrase bypasses the countdown and escalates at once.

        The app posts ``call_for_help`` when it recognises "Nura, emergency".
        The backend treats it identically to pressing SOS; what differs is only
        how the app came to send it, and recording that difference is what
        makes the eventual voice path answerable afterwards.
        """
        headers, profile_id = owner
        body = sos(client, headers, profile_id, event_type="call_for_help").json()
        assert body["event_type"] == "call_for_help"
        assert body["status"] == "escalated"


# --- the check-in ------------------------------------------------------------


class TestCheckIn:
    def start_check(self, client, headers, profile_id, db, **monitoring):
        token = seed_device(db, client, headers, profile_id=profile_id)
        start_monitoring(client, headers, profile_id, **monitoring)
        created = device_trigger(client, token)
        assert created.status_code == 201, created.text
        return created.json()["event_id"]

    def test_im_okay_resolves_and_contacts_nobody(self, client, owner, db, clock):
        """Section 25. No escalation, no alert, and no message to anybody."""
        headers, profile_id = owner
        event_id = self.start_check(client, headers, profile_id, db)
        answered = respond(client, headers, profile_id, event_id, "im_okay")
        assert answered.status_code == 200
        body = answered.json()
        assert body["status"] == "resolved"
        assert body["resolution"] == "user_confirmed_ok"
        assert body["attempts"] == []
        assert body["alert_count"] == 0
        assert status(client, headers, profile_id)["active_event"] is None

    def test_i_need_help_escalates_at_once(self, client, owner, db, clock):
        """Section 26: skip the countdown, begin escalation, enter emergency mode."""
        headers, profile_id = owner
        event_id = self.start_check(client, headers, profile_id, db)
        body = respond(client, headers, profile_id, event_id, "need_help").json()
        assert body["status"] == "escalated"
        assert body["escalation_started_at"] is not None
        assert status(client, headers, profile_id)["emergency_mode"] is True

    def test_a_false_alarm_dismissal_resolves_and_labels_in_one_step(
        self, client, owner, db, clock
    ):
        """Section 23's optional dismissal."""
        headers, profile_id = owner
        event_id = self.start_check(client, headers, profile_id, db)
        body = respond(client, headers, profile_id, event_id, "false_alarm").json()
        assert body["resolution"] == "false_alarm"
        assert body["false_positive"] is True

    def test_a_late_answer_keeps_the_history(self, client, owner, db, clock):
        """Section 126.

        The answer is recorded, unsent steps stop, and nothing that already
        happened is rewritten -- the escalation attempts stay exactly as they
        were, because a tidy-looking cancellation would be the same lie as
        claiming a delivery.
        """
        headers, profile_id = owner
        event = sos(client, headers, profile_id).json()
        before = len(event["attempts"])

        answered = respond(client, headers, profile_id, event["id"], "im_okay").json()
        assert answered["status"] == "resolved"
        assert answered["user_response"] == "im_okay"
        assert len(answered["attempts"]) == before
        assert answered["escalation_started_at"] is not None

    def test_answering_a_finished_event_is_refused_clearly(
        self, client, owner, db, clock
    ):
        """A screen left open is common; a 500 for it is not.

        A stable 409 the app handles by refreshing, rather than an error the
        user is shown.
        """
        headers, profile_id = owner
        event_id = self.start_check(client, headers, profile_id, db)
        respond(client, headers, profile_id, event_id, "im_okay")
        again = respond(client, headers, profile_id, event_id, "im_okay")
        assert again.status_code == 409
        assert again.json()["detail"]["code"] == "safety_event_not_live"

    def test_cancelling_records_who_and_why(self, client, owner, clock):
        """Section 45."""
        headers, profile_id = owner
        event = sos(client, headers, profile_id).json()
        cancelled = client.post(
            f"{safety_url(profile_id)}/events/{event['id']}/cancel", headers=headers
        ).json()
        assert cancelled["status"] == "cancelled"
        assert cancelled["resolution"] == "cancelled_by_user"
        assert status(client, headers, profile_id)["emergency_mode"] is False

    def test_a_false_alarm_label_can_be_no(self, client, owner, db, clock):
        """Sections 47 and 48.

        "No / Not sure" is stored rather than ignored, so "they said it was
        real" and "nobody asked" stay different facts -- which is the whole
        reason the column is nullable.
        """
        headers, profile_id = owner
        event_id = self.start_check(client, headers, profile_id, db)
        respond(client, headers, profile_id, event_id, "im_okay")

        marked = client.post(
            f"{safety_url(profile_id)}/events/{event_id}/false-alarm",
            json={"false_positive": False},
            headers=headers,
        ).json()
        assert marked["false_positive"] is False
        assert marked["false_positive_reason"] is None

        relabelled = client.post(
            f"{safety_url(profile_id)}/events/{event_id}/false-alarm",
            json={"false_positive": True, "reason": "normal_movement"},
            headers=headers,
        ).json()
        assert relabelled["false_positive"] is True
        assert relabelled["false_positive_reason"] == "normal_movement"

    def test_the_second_prompt_waits_before_escalating(self, client, owner, db, clock):
        """Section 8's exact timing, as documented in ``services.safety.checks``.

        45 seconds, then a second prompt, then 20 more. Both deadlines are
        columns, so this test moves a clock rather than sleeping (section 82).
        """
        headers, profile_id = owner
        event_id = self.start_check(
            client, headers, profile_id, db, second_prompt_enabled=True
        )
        from app.services.safety import checks

        event = db.get(SafetyEvent, uuid.UUID(event_id))
        assert event is not None

        clock.now = NOW + timedelta(seconds=46)
        checks.advance(db, event, clock.now)
        db.commit()
        assert event.status == "second_prompt"
        assert event.second_prompt_deadline_at == clock.now + timedelta(seconds=20)

        clock.now = NOW + timedelta(seconds=70)
        checks.advance(db, event, clock.now)
        db.commit()
        assert event.status == "escalated"


# --- capabilities and history -------------------------------------------------


class TestCapabilities:
    def test_the_capability_map_is_section_106s_example(self, client, owner, clock):
        """Section 106, value for value.

        Nothing here is a constant in a screen: each value is computed from the
        thing itself -- the notification provider, PRD 9's call provider, the
        detector registry -- which is what stops a capability flag being turned
        on without a capability behind it (section 72).
        """
        headers, profile_id = owner
        body = client.get(
            f"{safety_url(profile_id)}/capabilities", headers=headers
        ).json()
        states = {row["key"]: row["state"] for row in body["capabilities"]}
        assert states == {
            "manual_sos": "available",
            "in_app_safety_checks": "available",
            "caregiver_in_app_alerts": "available",
            "push_delivery": "not_configured",
            "sms_delivery": "not_configured",
            "audio_calling": "not_configured",
            "robot_detection": "not_connected",
        }
        assert body["external_delivery_available"] is False
        assert body["warning"] == wording.NO_DELIVERY_PROVIDERS

    def test_robot_detection_is_not_connected_because_nothing_is_registered(self):
        """Sections 66 and 71, and the honest state of this project.

        ``DETECTORS`` is empty. There is no fall model, no immobility model, no
        seizure-like classifier and no vomiting detector, and none has ever
        been validated against anything (section 117).
        """
        from app.services.safety import detectors

        assert detectors.DETECTORS == ()
        assert detectors.detection_available() is False

    def test_the_monitoring_screen_says_nothing_is_watching(self, client, owner, clock):
        """Section 66: the sentence that must appear, and must be true."""
        headers, profile_id = owner
        start_monitoring(client, headers, profile_id)
        body = status(client, headers, profile_id)
        assert body["detection_notice"] == wording.MONITORING_WITHOUT_DETECTION
        assert "not connected yet" in body["detection_notice"]

    def test_the_no_contacts_warning_appears_and_goes(self, client, owner, clock):
        """Section 73: warn, but still allow monitoring."""
        headers, profile_id = owner
        body = status(client, headers, profile_id)
        assert body["no_contacts_warning"] == wording.NO_EMERGENCY_CONTACTS
        assert start_monitoring(client, headers, profile_id).status_code == 201

        client.post(
            f"/api/v1/profiles/{profile_id}/emergency-contacts",
            json={"name": "Ayesha", "phone": "+447700900000"},
            headers=headers,
        )
        assert status(client, headers, profile_id)["no_contacts_warning"] is None

    def test_the_no_providers_warning_is_explicit(self, client, owner, clock):
        """Section 74: this warning must be explicit, and it is one sentence."""
        headers, profile_id = owner
        warning = status(client, headers, profile_id)["no_providers_warning"]
        assert warning == wording.NO_DELIVERY_PROVIDERS
        assert "cannot reach anybody" in warning


class TestHistory:
    def test_history_is_newest_first_and_says_how_each_ended(self, client, owner, clock):
        """Section 49."""
        headers, profile_id = owner
        first = sos(client, headers, profile_id).json()
        respond(client, headers, profile_id, first["id"], "im_okay")
        clock.now = NOW + timedelta(hours=1)
        second = sos(client, headers, profile_id).json()

        events = client.get(f"{safety_url(profile_id)}/events", headers=headers).json()[
            "events"
        ]
        assert [row["id"] for row in events] == [second["id"], first["id"]]
        assert events[1]["resolution_label"] == "You said you were okay"

    def test_an_event_detail_reads_as_section_51(self, client, owner, db, clock):
        """Section 51's layout, field by field."""
        headers, profile_id = owner
        token = seed_device(db, client, headers, profile_id=profile_id)
        start_monitoring(client, headers, profile_id)
        event_id = device_trigger(client, token).json()["event_id"]

        detail = client.get(
            f"{safety_url(profile_id)}/events/{event_id}", headers=headers
        ).json()
        assert detail["event_label"] == "Possible fall"
        assert detail["description"].startswith("Something was observed")
        assert detail["no_response_seconds"] == 45
        assert detail["no_response_label"] == "No response after 45 seconds."

    def test_another_account_reaches_no_safety_route(
        self, client, owner, make_token, clock
    ):
        """404 at every depth, for the reason the whole codebase gives."""
        headers, profile_id = owner
        event = sos(client, headers, profile_id).json()
        stranger = {"Authorization": f"Bearer {make_token()}"}
        for path in (
            f"{safety_url(profile_id)}/status",
            f"{safety_url(profile_id)}/capabilities",
            f"{safety_url(profile_id)}/events",
            f"{safety_url(profile_id)}/events/{event['id']}",
        ):
            assert client.get(path, headers=stranger).status_code == 404
        assert sos(client, stranger, profile_id).status_code == 404
