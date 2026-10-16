"""The assistant's safety tools, and what each caller may reach.

PRD 10, sections 56, 57, 58, 95, 96, 97 and 111.

The tool layer is exercised directly rather than through a model, for the PRD
8 reason: what is being tested is authorization and behaviour, and a scripted
reply in the middle only adds a way for the test to pass by luck.

**Section 57 is the one this file is really about.** The model may not create
a sensor event from a speculative interpretation, and the last test checks
that by absence across every tool in the registry: no argument model anywhere
has an event type, a trigger source or a confidence, so the idea has nowhere
to go.
"""

import uuid
from datetime import UTC, datetime

import pytest

from app.api.deps import current_time
from app.main import app
from app.models import AccountProfileRole, Profile, User
from app.services.assistant import tools
from app.services.caregivers import permissions as caregiver_permissions
from tests.test_caregivers import active_caregiver
from tests.test_devices import ready_account
from tests.test_safety import device_trigger, safety_url, seed_device, start_monitoring
from tests.test_safety import status as safety_status
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


def owner_context(db, profile_id: str) -> tools.ToolContext:
    """The person's own assistant, with their own scope."""
    profile = db.get(Profile, uuid.UUID(profile_id))
    assert profile is not None
    row = (
        db.query(AccountProfileRole)
        .filter(AccountProfileRole.profile_id == uuid.UUID(profile_id))
        .first()
    )
    assert row is not None
    account = db.get(User, row.account_id)
    assert account is not None
    return tools.ToolContext(
        db=db,
        profile=profile,
        now=NOW,
        local_date=NOW.date(),
        allowed=tools.OWNER_SCOPE,
        is_owner=True,
        account=account,
    )


def caregiver_context(db, client, profile_id: str, caregiver) -> tools.ToolContext:
    """A caregiver's assistant, with the scope their permissions give them.

    Built through ``resolve_scope`` rather than from a literal set, so what
    the tools see is what the stored rows actually grant (PRD 9, section 63).
    """
    profile = db.get(Profile, uuid.UUID(profile_id))
    assert profile is not None
    account_id = client.get("/api/v1/me", headers=caregiver).json()["id"]
    account = db.get(User, uuid.UUID(account_id))
    assert account is not None
    scope = caregiver_permissions.resolve_scope(db, account, profile.id)
    return tools.ToolContext(
        db=db,
        profile=profile,
        now=NOW,
        local_date=NOW.date(),
        allowed=scope.granted,
        is_owner=False,
        account=account,
    )


class TestWhoSeesWhat:
    def test_the_owner_gets_the_safety_tools_and_not_a_caregivers(
        self, client, owner, db, clock
    ):
        """Section 56 for the owner, section 97 for what is not theirs.

        An owner has no alerts of their own, so a tool that could only answer
        "that is not for you" is kept out of the list rather than shown and
        refused.
        """
        _, profile_id = owner
        names = {spec.name for spec in tools.specs(owner_context(db, profile_id))}
        assert {
            "get_safety_status",
            "get_active_safety_event",
            "get_escalation_status",
            "start_safety_monitoring",
            "stop_safety_monitoring",
            "manual_sos",
            "respond_to_safety_check",
        } <= names
        assert "get_active_safety_alerts" not in names
        assert "acknowledge_safety_alert" not in names

    def test_a_caregiver_needs_the_permission_for_the_alert_tools(
        self, client, owner, make_token, db, clock
    ):
        """Sections 58 and 97, and PRD 9 section 63 behind them.

        Without ``safety_alerts`` the tools are not in the list at all, which
        is better than showing one and refusing it: a model that can see a
        tool will eventually tell the user it tried.
        """
        headers, profile_id = owner
        caregiver = {"Authorization": f"Bearer {make_token()}"}
        relationship_id = active_caregiver(
            client, owner, caregiver, permissions={"medications": True}
        )
        without = {
            spec.name
            for spec in tools.specs(caregiver_context(db, client, profile_id, caregiver))
        }
        assert "get_active_safety_alerts" not in without

        client.patch(
            f"/api/v1/profiles/{profile_id}/caregivers/{relationship_id}/permissions",
            json={"permissions": {"safety_alerts": True}},
            headers=headers,
        )
        granted = {
            spec.name
            for spec in tools.specs(caregiver_context(db, client, profile_id, caregiver))
        }
        assert "get_active_safety_alerts" in granted
        assert "acknowledge_safety_alert" in granted

    def test_a_caregiver_cannot_start_monitoring_through_the_assistant(
        self, client, owner, make_token, db, clock
    ):
        """Section 58, said twice: not in the list, and refused if named.

        Section 10 keeps monitoring the person's own decision, and a caregiver
        assistant is exactly the back door that would undo it. The refusal is
        the same answer an unknown tool gets, so a reply cannot be read as
        "that tool exists but you are not allowed it".
        """
        headers, profile_id = owner
        caregiver = {"Authorization": f"Bearer {make_token()}"}
        active_caregiver(client, owner, caregiver, permissions={"safety_alerts": True})
        context = caregiver_context(db, client, profile_id, caregiver)

        names = {spec.name for spec in tools.specs(context)}
        assert "start_safety_monitoring" not in names
        assert "manual_sos" not in names
        assert "respond_to_safety_check" not in names

        refused = tools.run(context, "start_safety_monitoring", {})
        assert refused.is_error
        assert "no tool called" in refused.content

    def test_a_caregiver_can_acknowledge_and_that_is_all_they_can_write(
        self, client, owner, make_token, db, clock
    ):
        """Sections 84, 97 and 125.

        One timestamp, and it resolves nothing. Every other caregiver change
        still goes through a suggestion the person approves (PRD 9, s64).
        """
        headers, profile_id = owner
        caregiver = {"Authorization": f"Bearer {make_token()}"}
        active_caregiver(client, owner, caregiver, permissions={"safety_alerts": True})
        client.post(f"{safety_url(profile_id)}/sos", json={}, headers=headers)

        context = caregiver_context(db, client, profile_id, caregiver)
        listed = tools.run(context, "get_active_safety_alerts", {})
        assert "Please check on them." in listed.content

        alert_id = client.get(
            f"/api/v1/profiles/{profile_id}/care/safety-alerts", headers=caregiver
        ).json()["alerts"][0]["id"]
        said = tools.run(context, "acknowledge_safety_alert", {"alert_id": alert_id})
        db.commit()
        assert "does not resolve" in said.content

        detail = client.get(f"{safety_url(profile_id)}/events", headers=headers).json()[
            "events"
        ][0]
        assert detail["status"] == "escalated"
        assert detail["resolution"] is None


class TestWritesAskFirst:
    def test_starting_monitoring_asks_before_it_acts(self, client, owner, db, clock):
        """Sections 4 and 56: switching monitoring on is never quiet."""
        headers, profile_id = owner
        context = owner_context(db, profile_id)
        outcome = tools.run(context, "start_safety_monitoring", {})
        assert outcome.pending is not None
        assert outcome.pending.summary == "Turn Safety Monitoring on for 1 hour?"
        assert safety_status(client, headers, profile_id)["monitoring"] is None

        tools.run_pending_action(context, outcome.pending)
        db.commit()
        assert safety_status(client, headers, profile_id)["monitoring"] is not None

    def test_the_assistant_does_not_offer_until_bedtime(self):
        """It has no time zone, and guessing one would end monitoring wrongly.

        The Safety screen offers all four presets because the phone knows the
        zone. The assistant offers the three it can work out honestly.
        """
        model = tools.BY_NAME["start_safety_monitoring"].args_model
        allowed = model.model_fields["duration_mode"].annotation
        assert set(allowed.__args__) == {"30_minutes", "1_hour", "until_turned_off"}

    def test_an_sos_asks_first_and_then_reports_only_facts(
        self, client, owner, db, clock
    ):
        """Sections 13, 57 and 96.

        The fast path for a real emergency does not go through the model at
        all -- "Nura, emergency" is matched deterministically before any
        provider is called. This tool is for ambiguous phrasing, so it asks;
        and what it reports afterwards is the escalation's own lines.
        """
        headers, profile_id = owner
        client.post(
            f"/api/v1/profiles/{profile_id}/emergency-contacts",
            json={"name": "Ayesha", "phone": "+447700900000"},
            headers=headers,
        )
        context = owner_context(db, profile_id)

        outcome = tools.run(context, "manual_sos", {})
        assert outcome.pending is not None
        assert (
            client.get(f"{safety_url(profile_id)}/events", headers=headers).json()[
                "events"
            ]
            == []
        )

        said = tools.run_pending_action(context, outcome.pending)
        db.commit()
        assert "Emergency request recorded." in said
        assert "not set up in this build" in said
        assert "has been contacted" not in said

    def test_need_help_acts_at_once_and_im_okay_asks(self, client, owner, db, clock):
        """Sections 25 and 26, and the asymmetry that is the point.

        Erring towards help is a safe error. Erring towards "they are fine" is
        not: a model that ended an escalation because it misread a sentence
        would have done the one unrecoverable thing in this feature.
        """
        headers, profile_id = owner
        token = seed_device(db, client, headers, profile_id=profile_id)
        start_monitoring(client, headers, profile_id)
        device_trigger(client, token)
        context = owner_context(db, profile_id)

        asked = tools.run(context, "respond_to_safety_check", {"response": "im_okay"})
        assert asked.pending is not None
        assert safety_status(client, headers, profile_id)["active_event"] is not None

        acted = tools.run(context, "respond_to_safety_check", {"response": "need_help"})
        db.commit()
        assert acted.pending is None
        assert safety_status(client, headers, profile_id)["emergency_mode"] is True

    def test_a_model_cannot_mark_a_false_alarm(self):
        """Section 48: labelling an event is a judgement, and it is the
        person's.

        ``false_alarm`` is in the HTTP vocabulary and absent from the tool's,
        so the only way to label one is a person pressing it on a screen.
        """
        model = tools.BY_NAME["respond_to_safety_check"].args_model
        allowed = model.model_fields["response"].annotation
        assert set(allowed.__args__) == {"im_okay", "need_help"}


class TestWhatTheModelIsTold:
    def test_the_status_tool_says_what_is_not_configured(self, client, owner, db, clock):
        """Section 96: the model is handed facts it can repeat.

        A model told plainly that there is no push provider cannot truthfully
        report one, and this is how it is told -- rather than by a rule in a
        prompt that a long conversation can drift away from.
        """
        headers, profile_id = owner
        start_monitoring(client, headers, profile_id)
        said = tools.run(owner_context(db, profile_id), "get_safety_status", {}).content
        assert "Safety Monitoring is on" in said
        assert "not connected yet" in said
        assert "cannot reach anybody" in said

    def test_the_escalation_tool_returns_the_rendered_lines(
        self, client, owner, make_token, db, clock
    ):
        """Section 96's example, which is literally two of these lines."""
        headers, profile_id = owner
        caregiver = {"Authorization": f"Bearer {make_token()}"}
        active_caregiver(client, owner, caregiver, permissions={"safety_alerts": True})
        client.post(f"{safety_url(profile_id)}/sos", json={}, headers=headers)

        said = tools.run(
            owner_context(db, profile_id), "get_escalation_status", {}
        ).content
        assert "In-app alert created for Ayesha." in said
        assert "notified" not in said

    def test_no_safety_tool_can_invent_a_sensor_event(self):
        """Section 57, enforced by absence across the whole registry.

        Not one argument model has an event type, a trigger source or a
        confidence. A speculative reading of something somebody typed has
        nowhere to become a ``possible_seizure_like_activity``.
        """
        for tool in tools.TOOLS:
            fields = set(tool.args_model.model_fields)
            assert not fields & {"event_type", "trigger_source", "confidence"}, tool.name
