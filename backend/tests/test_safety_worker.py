"""The durable timeout path: the worker, and what it is and is not for.

PRD 10, sections 27, 28, 79, 80, 81, 82 and 112.

Section 80 asks for one distinction to be drawn explicitly and tested
explicitly, and this file is the second half of it.

    *State correctness* -- a deadline that has passed is acted on the moment
    anybody reads the event. Tested in ``test_safety.py``, where no worker
    ever runs.

    *Timely escalation* -- a deadline that has passed is acted on even though
    nobody is reading anything. That needs ``scripts/safety_maintenance.py``,
    and section 80 says not to claim timing works if the worker has never
    run. It runs here, against a real database, with a frozen clock.

**No test sleeps** (section 82). Every deadline is a column, so moving time
means moving a variable.

**The honest limit, stated once:** without this script scheduled, escalation
happens when the event is next read -- which may be much later, or never. The
script is a cron job, not a daemon, and nothing in this project schedules it
for a deployment.
"""

import secrets
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.api.deps import current_time
from app.main import app
from app.models import SafetyAlert, SafetyEscalationAttempt, SafetyEvent
from app.services.safety import providers
from scripts import safety_maintenance
from tests.test_caregivers import active_caregiver
from tests.test_devices import ready_account
from tests.test_safety import device_trigger, seed_device, start_monitoring
from tests.test_today import Clock

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


@pytest.fixture
def caregiver(client, make_token) -> dict[str, str]:
    return {"Authorization": f"Bearer {make_token()}"}


def raise_trigger(client, db, headers, profile_id: str, **monitoring) -> str:
    """Monitoring on, a simulated device trigger, a check-in waiting."""
    token = seed_device(db, client, headers, profile_id=profile_id)
    start_monitoring(client, headers, profile_id, **monitoring)
    created = device_trigger(client, token, idempotency_key=secrets.token_hex(8))
    assert created.status_code == 201, created.text
    return created.json()["event_id"]


def event_row(db, event_id: str) -> SafetyEvent:
    row = db.get(SafetyEvent, uuid.UUID(event_id))
    assert row is not None
    db.refresh(row)
    return row


class TestDeadlines:
    def test_a_deadline_in_the_future_is_left_alone(self, client, owner, db, clock):
        """Section 112's first case. Nothing happens early."""
        headers, profile_id = owner
        event_id = raise_trigger(client, db, headers, profile_id)

        result = safety_maintenance.run(db, NOW + timedelta(seconds=10))
        assert result.events_advanced == 0
        assert event_row(db, event_id).status == "checking_user"

    def test_a_deadline_in_the_past_escalates(self, client, owner, db, clock):
        """Sections 27 and 112, and the claim this file exists to support.

        Nobody read anything. The worker found the row by its deadline column
        and escalated, which is what "timely" means for somebody whose phone
        is in another room.
        """
        headers, profile_id = owner
        event_id = raise_trigger(client, db, headers, profile_id)

        result = safety_maintenance.run(db, NOW + timedelta(seconds=46))
        assert result.events_advanced == 1
        assert result.escalations_started == 1

        row = event_row(db, event_id)
        assert row.status == "escalated"
        assert row.escalation_started_at is not None
        assert row.user_response is None

    def test_the_second_prompt_delays_escalation_by_exactly_twenty_seconds(
        self, client, owner, db, clock
    ):
        """Section 8's timing, run end to end through the worker.

        45 seconds, a second prompt, 20 more, then escalation. Worst case
        with the longest timeout is 110 seconds, which is the number
        ``services.safety.checks`` documents.
        """
        headers, profile_id = owner
        event_id = raise_trigger(
            client, db, headers, profile_id, second_prompt_enabled=True
        )

        safety_maintenance.run(db, NOW + timedelta(seconds=46))
        row = event_row(db, event_id)
        assert row.status == "second_prompt"
        assert row.escalation_started_at is None

        safety_maintenance.run(db, NOW + timedelta(seconds=60))
        assert event_row(db, event_id).status == "second_prompt"

        safety_maintenance.run(db, NOW + timedelta(seconds=67))
        row = event_row(db, event_id)
        assert row.status == "escalated"

    def test_the_timeout_the_session_chose_is_the_one_used(
        self, client, owner, db, clock
    ):
        """Section 7: the timeout is stored on the session, not on a setting.

        An event inherits the timeout in force when monitoring started, not
        the one in force when the event happened to be processed.
        """
        headers, profile_id = owner
        event_id = raise_trigger(
            client, db, headers, profile_id, response_timeout_seconds=90
        )

        safety_maintenance.run(db, NOW + timedelta(seconds=60))
        assert event_row(db, event_id).status == "checking_user"

        safety_maintenance.run(db, NOW + timedelta(seconds=91))
        assert event_row(db, event_id).status == "escalated"

    def test_an_answered_event_is_untouched(self, client, owner, db, clock):
        """Section 76: the worker finds a resolved event and does nothing."""
        headers, profile_id = owner
        event_id = raise_trigger(client, db, headers, profile_id)
        client.post(
            f"/api/v1/profiles/{profile_id}/safety/events/{event_id}/respond",
            json={"response": "im_okay"},
            headers=headers,
        )

        result = safety_maintenance.run(db, NOW + timedelta(minutes=5))
        assert result.events_advanced == 0
        assert event_row(db, event_id).escalation_started_at is None


class TestIdempotentRuns:
    def test_running_twice_escalates_once(self, client, owner, caregiver, db, clock):
        """Section 112's fourth case, and section 75 behind it.

        The second run finds nothing to advance, and even if it somehow
        re-entered escalation the uniqueness on attempts and alerts would make
        it a no-op. Both are checked.
        """
        headers, profile_id = owner
        active_caregiver(client, owner, caregiver, permissions={"safety_alerts": True})
        client.post(
            f"/api/v1/profiles/{profile_id}/emergency-contacts",
            json={"name": "Spouse", "phone": "+447700900000"},
            headers=headers,
        )
        raise_trigger(client, db, headers, profile_id)

        first = safety_maintenance.run(db, NOW + timedelta(seconds=46))
        attempts = db.query(SafetyEscalationAttempt).count()
        alerts = db.query(SafetyAlert).count()
        assert first.escalations_started == 1
        assert attempts > 0
        assert alerts == 1

        second = safety_maintenance.run(db, NOW + timedelta(seconds=47))
        assert second.events_advanced == 0
        assert db.query(SafetyEscalationAttempt).count() == attempts
        assert db.query(SafetyAlert).count() == alerts

    def test_a_dry_run_changes_nothing(self, client, owner, db, clock):
        """The same flag the medication worker has, and the same promise."""
        headers, profile_id = owner
        event_id = raise_trigger(client, db, headers, profile_id)

        result = safety_maintenance.run(db, NOW + timedelta(seconds=46), dry_run=True)
        assert result.events_advanced == 1
        db.expire_all()
        assert event_row(db, event_id).status == "checking_user"


class TestMonitoringExpiry:
    def test_an_expired_session_is_ended_by_the_worker(self, client, owner, db, clock):
        """Section 61, for the profile nobody opened.

        The status endpoint would end it too. This is the path for somebody
        who never looks, and section 80 wants both tested rather than one
        assumed from the other.
        """
        from app.models import SafetyMonitoringSession

        headers, profile_id = owner
        start_monitoring(client, headers, profile_id, duration_mode="30_minutes")

        result = safety_maintenance.run(db, NOW + timedelta(minutes=31))
        assert result.sessions_expired == 1

        session = (
            db.query(SafetyMonitoringSession)
            .filter(SafetyMonitoringSession.profile_id == uuid.UUID(profile_id))
            .one()
        )
        assert session.status == "expired"
        assert session.end_reason == "duration_reached"

    def test_an_event_already_waiting_still_escalates_after_monitoring_ends(
        self, client, owner, db, clock
    ):
        """The one place the order inside a run matters.

        A trigger needs monitoring (section 22). An *answer* to one that has
        already happened does not -- and neither does the timeout. Somebody
        who fell two minutes before their session ran out must not have their
        escalation quietly dropped because the clock moved on.
        """
        headers, profile_id = owner
        event_id = raise_trigger(client, db, headers, profile_id)

        result = safety_maintenance.run(db, NOW + timedelta(minutes=31))
        assert result.sessions_expired == 1
        assert event_row(db, event_id).status == "escalated"


class TestRetries:
    def test_a_failed_attempt_is_retried_once_the_backoff_has_passed(
        self, client, owner, db, clock
    ):
        """Sections 112 and 124.

        Nothing in this build can fail -- the channels that exist return
        ``attempted`` and the rest return ``not_configured`` -- so the failed
        attempt is written directly. That is the only honest way to exercise
        the retry policy without pretending a provider exists.
        """
        headers, profile_id = owner
        event_id = client.post(
            f"/api/v1/profiles/{profile_id}/safety/sos", json={}, headers=headers
        ).json()["id"]

        attempt = SafetyEscalationAttempt(
            safety_event_id=uuid.UUID(event_id),
            profile_id=uuid.UUID(profile_id),
            recipient_key="contact:flaky",
            recipient_label="Spouse",
            priority=1,
            channel="sms_future",
            status="failed",
            failure_code="provider_error",
            attempted_at=NOW,
            retry_count=0,
        )
        db.add(attempt)
        db.commit()

        early = safety_maintenance.run(db, NOW + timedelta(seconds=10))
        assert early.attempts_retried == 0

        due = safety_maintenance.run(db, NOW + timedelta(seconds=31))
        assert due.attempts_retried == 1
        db.refresh(attempt)
        assert attempt.retry_count == 1
        # No SMS provider, so the retry's honest answer is the same one.
        assert attempt.status == "not_configured"

    def test_a_not_configured_attempt_is_never_retried(self, client, owner, db, clock):
        """Retrying it would fill the trail with rows saying the same thing.

        A build with no SMS provider will not grow one in thirty seconds.
        """
        headers, profile_id = owner
        client.post(
            f"/api/v1/profiles/{profile_id}/emergency-contacts",
            json={"name": "Spouse", "phone": "+447700900000"},
            headers=headers,
        )
        client.post(f"/api/v1/profiles/{profile_id}/safety/sos", json={}, headers=headers)

        result = safety_maintenance.run(db, NOW + timedelta(hours=1))
        assert result.attempts_retried == 0

    def test_retries_stop_at_the_bound(self, client, owner, db, clock):
        """Section 124: bounded, so nothing can spam a contact."""
        headers, profile_id = owner
        event_id = client.post(
            f"/api/v1/profiles/{profile_id}/safety/sos", json={}, headers=headers
        ).json()["id"]
        attempt = SafetyEscalationAttempt(
            safety_event_id=uuid.UUID(event_id),
            profile_id=uuid.UUID(profile_id),
            recipient_key="contact:flaky",
            recipient_label="Spouse",
            priority=1,
            channel="sms_future",
            status="failed",
            failure_code="provider_error",
            attempted_at=NOW,
            retry_count=providers.MAX_RETRIES,
        )
        db.add(attempt)
        db.commit()

        result = safety_maintenance.run(db, NOW + timedelta(hours=1))
        assert result.attempts_retried == 0
