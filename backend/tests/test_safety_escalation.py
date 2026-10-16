"""Escalation: who is reached, in what order, and what is truthfully claimed.

PRD 10, sections 29-42, 50, 75-78, 83-87, 104, 110, 111 and 124.

This is the file where PRD 10's truthfulness constraint is checked rather than
asserted. Three things it exists to prove:

**Nothing claims a delivery.** The only channel that works is an in-app alert
record, and even that is recorded as ``attempted``. ``delivered`` is reachable
in the vocabulary and nothing in this build ever writes it, which is tested
directly.

**``not_configured`` is told to the user.** A chain that silently did nothing
would look identical to one that worked. Every contact gets a row saying the
channel is not set up, and the rendered line says so in words.

**A caregiver gets exactly what ``safety_alerts`` grants and nothing else.**
Not the health record, not the emergency-contact chain, not the monitoring
controls -- and nothing at all once the permission is withdrawn.

No hardware anywhere, and no real provider anywhere: the recording provider
used by two tests is installed only by ``set_notification_provider``, which no
setting value can reach (section 110).
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.api.deps import current_time
from app.main import app
from app.models import SafetyAlert, SafetyEscalationAttempt
from app.services.safety import providers
from tests.test_caregivers import active_caregiver
from tests.test_devices import ready_account
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


@pytest.fixture
def recording():
    """A provider that records what it was asked to send (section 110).

    Test-only by construction: ``build_notification_provider`` has no branch
    that returns it, so no deployment can be configured into it. It returns
    ``attempted`` unless a test explicitly asks for ``confirm``.
    """
    provider = providers.RecordingNotificationProvider()
    providers.set_notification_provider(provider)
    yield provider
    providers.set_notification_provider(None)


def safety_url(profile_id: str) -> str:
    return f"/api/v1/profiles/{profile_id}/safety"


def add_contact(
    client, headers, profile_id: str, name: str, phone: str = "+447700900000"
):
    return client.post(
        f"/api/v1/profiles/{profile_id}/emergency-contacts",
        json={"name": name, "phone": phone},
        headers=headers,
    ).json()


def sos(client, headers, profile_id: str, **body):
    return client.post(f"{safety_url(profile_id)}/sos", json=body, headers=headers)


def alerts_for(client, headers, profile_id: str):
    return client.get(
        f"/api/v1/profiles/{profile_id}/care/safety-alerts", headers=headers
    )


# --- the chain ---------------------------------------------------------------


class TestContactChain:
    def test_the_chain_is_walked_in_the_priority_the_user_set(self, client, owner, clock):
        """Section 30: the PRD 9 chain, reused directly and not re-sorted.

        Nothing in PRD 10 has its own ordering. The attempts come back in the
        order the contacts were put in, which is what makes section 30's "do
        not create a second competing priority model" checkable rather than a
        statement of intent.
        """
        headers, profile_id = owner
        add_contact(client, headers, profile_id, "Spouse")
        add_contact(client, headers, profile_id, "Child")
        add_contact(client, headers, profile_id, "Neighbour")

        event = sos(client, headers, profile_id).json()
        labels = [
            attempt["recipient_label"]
            for attempt in event["attempts"]
            if not attempt["is_caregiver"]
        ]
        # Two channels per contact, both unavailable, in priority order.
        assert labels[:2] == ["Spouse", "Spouse"]
        assert labels[2:4] == ["Child", "Child"]
        assert labels[4:6] == ["Neighbour", "Neighbour"]

    def test_reordering_the_chain_changes_who_comes_first(self, client, owner, clock):
        """Section 30 again, from the other side.

        The PRD 9 reorder route is the only thing that decides this. If PRD 10
        had grown its own ordering, this test would still pass for the first
        event and fail for the second.
        """
        headers, profile_id = owner
        first = add_contact(client, headers, profile_id, "Spouse")
        second = add_contact(client, headers, profile_id, "Child")
        client.post(
            f"/api/v1/profiles/{profile_id}/emergency-contacts/reorder",
            json={"order": [second["id"], first["id"]]},
            headers=headers,
        )
        event = sos(client, headers, profile_id).json()
        contacts = [a for a in event["attempts"] if not a["is_caregiver"]]
        assert contacts[0]["recipient_label"] == "Child"

    def test_an_inactive_contact_is_not_tried(self, client, owner, clock):
        """Section 45's activate/deactivate, honoured by escalation."""
        headers, profile_id = owner
        contact = add_contact(client, headers, profile_id, "Spouse")
        client.patch(
            f"/api/v1/profiles/{profile_id}/emergency-contacts/{contact['id']}",
            json={"is_active": False},
            headers=headers,
        )
        event = sos(client, headers, profile_id).json()
        assert event["attempts"] == []
        assert event["escalation_outcome"] == "no_contacts"

    def test_the_chain_is_frozen_when_escalation_starts(self, client, owner, clock):
        """Sections 87 and 88.

        A contact deleted afterwards leaves an attempt that still says who was
        tried, and the snapshot still says who was in the chain -- which is
        what makes an old event readable without reconstructing what the
        configuration used to be.
        """
        headers, profile_id = owner
        contact = add_contact(client, headers, profile_id, "Spouse")
        event = sos(client, headers, profile_id).json()
        client.delete(
            f"/api/v1/profiles/{profile_id}/emergency-contacts/{contact['id']}",
            headers=headers,
        )
        detail = client.get(
            f"{safety_url(profile_id)}/events/{event['id']}", headers=headers
        ).json()
        assert detail["attempts"][0]["recipient_label"] == "Spouse"

    def test_the_snapshot_holds_no_phone_number(self, client, owner, db, clock):
        """Section 121: safety logs carry only required operational data.

        A number is not needed to answer "who was in the chain", and a
        snapshot is readable by anybody who can read the event.
        """
        from app.models import SafetyEvent

        headers, profile_id = owner
        add_contact(client, headers, profile_id, "Spouse", phone="+447700900123")
        event_id = sos(client, headers, profile_id).json()["id"]
        row = db.get(SafetyEvent, uuid.UUID(event_id))
        assert row is not None
        assert "447700900123" not in str(row.escalation_snapshot)
        assert row.escalation_snapshot["recipients"][0]["label"] == "Spouse"


# --- provider truthfulness ----------------------------------------------------


class TestProviderTruthfulness:
    def test_every_external_channel_reports_not_configured(self, client, owner, clock):
        """Sections 35 and 39, and the codes PRD 9 already uses.

        ``calling_not_configured`` is deliberately the same string
        ``services.caregivers.calls`` returns: one code for "Nura cannot ring
        anybody", whichever feature asked.
        """
        headers, profile_id = owner
        add_contact(client, headers, profile_id, "Spouse")
        event = sos(client, headers, profile_id).json()
        by_channel = {a["channel"]: a for a in event["attempts"]}
        assert by_channel["voice_call_future"]["status"] == "not_configured"
        assert by_channel["voice_call_future"]["failure_code"] == "calling_not_configured"
        assert by_channel["sms_future"]["status"] == "not_configured"
        assert by_channel["sms_future"]["failure_code"] == "sms_not_configured"

    def test_nothing_in_this_build_is_ever_marked_delivered(
        self, client, owner, caregiver, db, clock
    ):
        """Section 38, checked against the table rather than the screen.

        ``delivered`` exists in the vocabulary so a real provider can use it.
        Nothing writes it, because nothing delivers anything.
        """
        headers, profile_id = owner
        active_caregiver(client, owner, caregiver, permissions={"safety_alerts": True})
        add_contact(client, headers, profile_id, "Spouse")
        sos(client, headers, profile_id)
        statuses = {row.status for row in db.query(SafetyEscalationAttempt).all()}
        assert statuses
        assert "delivered" not in statuses

    def test_the_user_is_shown_facts_not_claims(self, client, owner, caregiver, clock):
        """Section 42, as the two sentences the PRD writes out.

        Good: "In-app alert created for Ayesha." / "Phone call for Spouse: not
        set up in this build." Bad: "Ayesha has been contacted."
        """
        headers, profile_id = owner
        active_caregiver(client, owner, caregiver, permissions={"safety_alerts": True})
        add_contact(client, headers, profile_id, "Spouse")
        event = sos(client, headers, profile_id).json()
        lines = [attempt["line"] for attempt in event["attempts"]]
        assert "In-app alert created for Ayesha." in lines
        assert "Phone call for Spouse: not set up in this build." in lines
        for line in lines:
            assert "has been contacted" not in line

    def test_the_outcome_distinguishes_nobody_from_nothing_configured(
        self, client, owner, caregiver, clock
    ):
        """Section 41, across the three outcomes this build can produce.

        "Nura could not reach anybody" and "Nura has no way to reach anybody"
        are different problems, and only the second is fixable by a
        deployment.
        """
        headers, profile_id = owner
        first = sos(client, headers, profile_id).json()
        assert first["escalation_outcome"] == "no_contacts"
        client.post(
            f"{safety_url(profile_id)}/events/{first['id']}/cancel", headers=headers
        )

        add_contact(client, headers, profile_id, "Spouse")
        second = sos(client, headers, profile_id).json()
        assert second["escalation_outcome"] == "providers_not_configured"
        client.post(
            f"{safety_url(profile_id)}/events/{second['id']}/cancel", headers=headers
        )

        active_caregiver(client, owner, caregiver, permissions={"safety_alerts": True})
        third = sos(client, headers, profile_id).json()
        assert third["escalation_outcome"] == "partial"

    def test_a_configured_provider_stops_the_chain_at_the_first_contact_reached(
        self, client, owner, recording, clock
    ):
        """Section 40's policy, exercised with the recording provider.

        The only way to see the "stop at the first contact reached" branch,
        because nothing in a real deployment can reach one. The provider
        records and claims nothing stronger than ``attempted``.
        """
        headers, profile_id = owner
        add_contact(client, headers, profile_id, "Spouse")
        add_contact(client, headers, profile_id, "Child")
        event = sos(client, headers, profile_id).json()

        labels = {a["recipient_label"] for a in event["attempts"]}
        assert labels == {"Spouse"}
        assert [channel for channel, _, _ in recording.sent] == ["sms_future"]

        # ``partial`` rather than ``complete``, and that is the honest answer:
        # the text went, the call did not, and section 41 keeps those apart.
        # Only the first contact is in the chain at all, because section 40
        # stops at the first one actually reached.
        assert event["escalation_outcome"] == "partial"
        by_channel = {a["channel"]: a["status"] for a in event["attempts"]}
        assert by_channel == {
            "voice_call_future": "not_configured",
            "sms_future": "attempted",
        }

    def test_the_recording_provider_cannot_be_configured_into_a_deployment(self):
        """Section 110: test-only, and that is a property rather than a note.

        No setting value reaches ``RecordingNotificationProvider``. The only
        way in is ``set_notification_provider``, which tests call and nothing
        else does.
        """
        from app.core.config import Settings

        for name in ("recording", "mock", "test", "log", "fake"):
            settings = Settings(
                database_url="postgresql+psycopg://x/y", safety_push_provider=name
            )
            with pytest.raises(providers.SafetyProviderConfigurationError):
                providers.build_notification_provider(settings)


# --- caregivers ----------------------------------------------------------------


class TestCaregiverAlerts:
    def test_a_caregiver_with_the_permission_gets_an_alert_record(
        self, client, owner, caregiver, clock
    ):
        """Sections 31, 37 and 83.

        The record proves an alert exists. It does not prove the caregiver saw
        it -- ``read_at`` is null until they open the list, and nothing else
        in the system can fill it in.
        """
        headers, profile_id = owner
        active_caregiver(client, owner, caregiver, permissions={"safety_alerts": True})
        sos(client, headers, profile_id)

        body = alerts_for(client, caregiver, profile_id).json()
        assert len(body["alerts"]) == 1
        alert = body["alerts"][0]
        assert alert["event_type"] == "manual_sos"
        assert alert["acknowledged_at"] is None
        assert "Please check on them." in alert["sentence"]

    def test_a_caregiver_without_the_permission_gets_nothing(
        self, client, owner, caregiver, db, clock
    ):
        """Section 31, and section 18's rule applied to PRD 10's data.

        Not an empty list -- a 404, the same answer a caregiver gets for any
        category they were not granted. An empty list would confirm that this
        person has a safety history to be empty of.
        """
        headers, profile_id = owner
        active_caregiver(client, owner, caregiver, permissions={"medications": True})
        sos(client, headers, profile_id)

        assert alerts_for(client, caregiver, profile_id).status_code == 404
        assert db.query(SafetyAlert).count() == 0

    def test_a_role_does_not_grant_safety_alerts(self, client, owner, caregiver, clock):
        """Section 31: role names do not grant access.

        ``emergency_contact`` as a *role* is the one that invites the opposite
        assumption, so it is the one tested.
        """
        headers, profile_id = owner
        active_caregiver(
            client, owner, caregiver, role="emergency_contact", permissions={}
        )
        sos(client, headers, profile_id)
        assert alerts_for(client, caregiver, profile_id).status_code == 404

    def test_a_revoked_permission_stops_new_alerts_immediately(
        self, client, owner, caregiver, db, clock
    ):
        """Section 86, both halves.

        No new alerts after the permission goes, and the historical row stays
        -- deleting evidence of what the system did is not a retention policy.
        """
        headers, profile_id = owner
        relationship_id = active_caregiver(
            client, owner, caregiver, permissions={"safety_alerts": True}
        )
        first = sos(client, headers, profile_id).json()
        client.post(
            f"{safety_url(profile_id)}/events/{first['id']}/cancel", headers=headers
        )
        assert db.query(SafetyAlert).count() == 1

        client.patch(
            f"/api/v1/profiles/{profile_id}/caregivers/{relationship_id}/permissions",
            json={"permissions": {"safety_alerts": False}},
            headers=headers,
        )
        sos(client, headers, profile_id)

        assert db.query(SafetyAlert).count() == 1
        assert alerts_for(client, caregiver, profile_id).status_code == 404

    def test_a_revoked_caregiver_is_not_in_the_plan(
        self, client, owner, caregiver, db, clock
    ):
        """Section 86 through the relationship rather than the permission.

        ``granted_keys`` returns nothing for a relationship that is not
        active, so revocation needs no separate check in the escalation code.
        """
        headers, profile_id = owner
        relationship_id = active_caregiver(
            client, owner, caregiver, permissions={"safety_alerts": True}
        )
        client.delete(
            f"/api/v1/profiles/{profile_id}/caregivers/{relationship_id}",
            headers=headers,
        )
        sos(client, headers, profile_id)
        assert db.query(SafetyAlert).count() == 0

    def test_acknowledging_does_not_resolve_the_event(
        self, client, owner, caregiver, clock
    ):
        """Sections 84 and 125.

        One timestamp. It is not proof of physical contact and it does not end
        the emergency -- the person is still in it until they say otherwise.
        """
        headers, profile_id = owner
        active_caregiver(client, owner, caregiver, permissions={"safety_alerts": True})
        event = sos(client, headers, profile_id).json()
        alert = alerts_for(client, caregiver, profile_id).json()["alerts"][0]

        acknowledged = client.post(
            f"/api/v1/profiles/{profile_id}/care/safety-alerts/{alert['id']}/acknowledge",
            headers=caregiver,
        ).json()
        assert acknowledged["acknowledged_at"] is not None

        detail = client.get(
            f"{safety_url(profile_id)}/events/{event['id']}", headers=headers
        ).json()
        assert detail["status"] == "escalated"
        assert detail["resolution"] is None

    def test_opening_the_list_is_what_marks_an_alert_read(
        self, client, owner, caregiver, clock
    ):
        """Section 37, and the only honest way to write ``read_at``."""
        headers, profile_id = owner
        active_caregiver(client, owner, caregiver, permissions={"safety_alerts": True})
        sos(client, headers, profile_id)

        first = alerts_for(client, caregiver, profile_id).json()
        assert first["alerts"][0]["read_at"] is None
        second = alerts_for(client, caregiver, profile_id).json()
        assert second["alerts"][0]["read_at"] is not None
        assert second["unread_count"] == 0

    def test_an_alert_carries_no_health_data(self, client, owner, caregiver, clock):
        """Sections 50 and 85.

        A real symptom and a real medication are recorded first, so this is
        not passing because the record is empty.
        """
        headers, profile_id = owner
        client.post(
            f"/api/v1/profiles/{profile_id}/medications",
            json={"name": "Salbutamol"},
            headers=headers,
        )
        client.post(
            f"/api/v1/profiles/{profile_id}/symptoms",
            json={"name": "Headache", "first_entry": {"severity": 6}},
            headers=headers,
        )
        active_caregiver(client, owner, caregiver, permissions={"safety_alerts": True})
        sos(client, headers, profile_id)

        body = alerts_for(client, caregiver, profile_id).text
        assert "Salbutamol" not in body
        assert "Headache" not in body

    def test_a_caregiver_cannot_reach_the_owners_safety_routes(
        self, client, owner, caregiver, clock
    ):
        """Section 104, and PRD 9's boundary held exactly where it was.

        Every category granted, including ``safety_alerts``, and still 404 on
        monitoring, SOS, history and the event detail. The caregiver's whole
        view of safety is the alert list.
        """
        headers, profile_id = owner
        active_caregiver(
            client,
            owner,
            caregiver,
            permissions={
                "medications": True,
                "appointments": True,
                "symptoms": True,
                "reports": True,
                "safety_alerts": True,
                "communication": True,
                "routines": True,
                "general_health_summary": True,
            },
        )
        event = sos(client, headers, profile_id).json()
        for path in (
            f"{safety_url(profile_id)}/status",
            f"{safety_url(profile_id)}/capabilities",
            f"{safety_url(profile_id)}/events",
            f"{safety_url(profile_id)}/events/{event['id']}",
        ):
            assert client.get(path, headers=caregiver).status_code == 404, path
        assert sos(client, caregiver, profile_id).status_code == 404
        assert (
            client.post(
                f"{safety_url(profile_id)}/events/{event['id']}/respond",
                json={"response": "im_okay"},
                headers=caregiver,
            ).status_code
            == 404
        )

    def test_one_caregivers_alerts_are_not_anothers(
        self, client, owner, caregiver, make_token, clock
    ):
        """PRD 9 section 66, applied to PRD 10's rows.

        Alerts are scoped to the relationship, so a second caregiver sees
        their own and never the first one's.
        """
        headers, profile_id = owner
        active_caregiver(client, owner, caregiver, permissions={"safety_alerts": True})
        second = {"Authorization": f"Bearer {make_token()}"}
        active_caregiver(client, owner, second, permissions={"safety_alerts": True})
        sos(client, headers, profile_id)

        first = alerts_for(client, caregiver, profile_id).json()["alerts"]
        other = alerts_for(client, second, profile_id).json()["alerts"]
        first_ids = {alert["id"] for alert in first}
        second_ids = {alert["id"] for alert in other}
        assert first_ids and second_ids
        assert first_ids.isdisjoint(second_ids)

    def test_the_caregiver_home_omits_safety_when_it_is_not_granted(
        self, client, owner, caregiver, clock
    ):
        """Section 18, applied to PRD 10's section on the caregiver home.

        Absent, not empty: an omitted key cannot be read to learn whether
        anything has ever happened to this person.
        """
        headers, profile_id = owner
        active_caregiver(client, owner, caregiver, permissions={"medications": True})
        sos(client, headers, profile_id)
        home = client.get(
            f"/api/v1/profiles/{profile_id}/care/home", headers=caregiver
        ).json()
        assert home["safety"] is None


# --- idempotency and races -----------------------------------------------------


class TestIdempotency:
    def test_escalating_twice_contacts_nobody_twice(
        self, client, owner, caregiver, db, clock
    ):
        """Section 75, at the level the worker could actually repeat it.

        ``escalation.start`` is called again directly, which is what a
        duplicated worker run would do. Attempts are unique on (event,
        recipient, channel) and alerts on (event, account), so the second run
        finds rows rather than making them.
        """
        from app.models import SafetyEvent
        from app.services.safety import escalation

        headers, profile_id = owner
        active_caregiver(client, owner, caregiver, permissions={"safety_alerts": True})
        add_contact(client, headers, profile_id, "Spouse")
        event_id = sos(client, headers, profile_id).json()["id"]

        before_attempts = db.query(SafetyEscalationAttempt).count()
        before_alerts = db.query(SafetyAlert).count()

        row = db.get(SafetyEvent, uuid.UUID(event_id))
        assert row is not None
        escalation.start(db, row, now=clock.now, reason="duplicate_run")
        db.commit()

        assert db.query(SafetyEscalationAttempt).count() == before_attempts
        assert db.query(SafetyAlert).count() == before_alerts

    def test_cancelling_skips_what_had_not_gone_out(self, client, owner, db, clock):
        """Sections 45 and 76.

        Nothing is rewritten. An attempt that already recorded
        ``not_configured`` keeps saying so, because a cancellation that tidied
        up history would be the same lie as claiming a delivery.
        """
        from app.models import SafetyEvent
        from app.services.safety import escalation

        headers, profile_id = owner
        add_contact(client, headers, profile_id, "Spouse")
        event_id = sos(client, headers, profile_id).json()["id"]

        row = db.get(SafetyEvent, uuid.UUID(event_id))
        assert row is not None
        # A pending attempt, as a crashed run would leave behind.
        db.add(
            SafetyEscalationAttempt(
                safety_event_id=row.id,
                profile_id=row.profile_id,
                recipient_key="contact:pending",
                recipient_label="Neighbour",
                priority=9,
                channel="sms_future",
                status="pending",
            )
        )
        db.commit()

        client.post(f"{safety_url(profile_id)}/events/{event_id}/cancel", headers=headers)
        statuses = {
            row.recipient_label: row.status
            for row in escalation.attempts_for(db, uuid.UUID(event_id))
        }
        assert statuses["Neighbour"] == "skipped"
        assert statuses["Spouse"] == "not_configured"

    def test_answering_first_stops_escalation_entirely(self, client, owner, db, clock):
        """Section 76's race, settled the way section 78 asks.

        The user answers while the deadline is still ahead; the worker then
        finds a resolved event and does nothing. No attempt is ever made, so
        there is nothing to recall.
        """
        import secrets

        from app.models import SafetyEvent
        from tests.test_safety import device_trigger, seed_device, start_monitoring

        headers, profile_id = owner
        add_contact(client, headers, profile_id, "Spouse")
        token = seed_device(db, client, headers, profile_id=profile_id)
        start_monitoring(client, headers, profile_id)
        event_id = device_trigger(
            client, token, idempotency_key=secrets.token_hex(8)
        ).json()["event_id"]

        client.post(
            f"{safety_url(profile_id)}/events/{event_id}/respond",
            json={"response": "im_okay"},
            headers=headers,
        )

        from app.services.safety import checks

        clock.now = NOW + timedelta(minutes=5)
        row = db.get(SafetyEvent, uuid.UUID(event_id))
        assert row is not None
        checks.advance(db, row, clock.now)
        db.commit()

        assert row.status == "resolved"
        assert row.escalation_started_at is None
        assert db.query(SafetyEscalationAttempt).count() == 0

    def test_retries_are_bounded(self):
        """Section 124: bounded, backed off, and recorded.

        Read from one place, so the worker and the policy cannot disagree
        about when to stop.
        """
        assert providers.MAX_RETRIES == 2
        assert providers.retry_due_after(0) == 30
        assert providers.retry_due_after(1) == 120
        assert providers.retry_due_after(2) is None
