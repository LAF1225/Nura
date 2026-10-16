"""Caregiver suggestions, approval and the AI permission boundary.

PRD 9, sections 20-26, 63, 64, 74, 85, 86 and 95.

The whole of PRD 9's "a caregiver proposes, a person decides" is here, driven
over HTTP with two real accounts. Nothing is mocked: when approval changes a
reminder time, it changes it through the same medication service the owner's own
route calls, and the test reads the schedule back to prove it.

Three groups.

``TestSuggestions`` covers the flow, the diff section 86 asks for, idempotency
and -- the most important one -- that a caregiver cannot propose a dose change,
because there is no action type that could carry one (section 85).

``TestApprovalRevalidates`` covers section 24's six steps, and especially the
step people skip: the permission is re-checked at approval, so a suggestion made
last week by somebody revoked yesterday cannot be applied.

``TestAssistantPermissions`` is section 63 at the layer it names. PRD 9 has no
caregiver chat endpoint, so what is tested is the tool layer itself: a
caregiver-scoped context is not shown a tool it lacks the category for, and is
refused if it asks for one anyway.
"""

import uuid
from datetime import UTC, datetime

import pytest

from app.api.deps import current_time
from app.main import app
from app.models import MedicationSchedule, Profile, User
from app.services.assistant import tools
from app.services.caregivers import permissions as permission_service
from tests.test_caregivers import accept, active_caregiver, invite
from tests.test_devices import ready_account
from tests.test_medications import add_medication, make_schedule
from tests.test_today import Clock

NOW = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)


# --- helpers ----------------------------------------------------------------


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
def helper(client, make_token) -> dict[str, str]:
    return {"Authorization": f"Bearer {make_token()}"}


@pytest.fixture
def schedule(client, owner, clock) -> dict:
    """A real PRD 5 reminder schedule for Metformin at 7:00 PM."""
    headers, profile_id = owner
    medication_id = add_medication(client, headers, profile_id)
    response = make_schedule(
        client,
        headers,
        profile_id,
        medication_id,
        times=[{"time_of_day": "19:00:00"}],
    )
    assert response.status_code == 201, response.text
    return response.json()


def suggestions_url(profile_id: str) -> str:
    return f"/api/v1/profiles/{profile_id}/caregiver-suggestions"


def propose(
    client,
    headers,
    profile_id: str,
    *,
    action_type: str,
    target_resource_id: str | None = None,
    payload: dict | None = None,
    client_suggestion_id: str | None = None,
):
    body: dict = {"action_type": action_type, "payload": payload or {}}
    if target_resource_id is not None:
        body["target_resource_id"] = target_resource_id
    if client_suggestion_id is not None:
        body["client_suggestion_id"] = client_suggestion_id
    return client.post(suggestions_url(profile_id), json=body, headers=headers)


# --- suggestions -------------------------------------------------------------


class TestSuggestions:
    def test_a_caregiver_proposes_a_reminder_time_and_the_owner_approves(
        self, client, owner, helper, schedule, db, clock
    ):
        """Section 20's worked example, end to end: 7:00 PM to 8:00 PM.

        The assertion that matters is the last one: the stored schedule really
        moved, because approval went through ``medications.schedules`` -- the same
        function the owner's own route calls -- rather than through a second code
        path (section 24, step 4).
        """
        headers, profile_id = owner
        active_caregiver(client, owner, helper, permissions={"medications": True})

        created = propose(
            client,
            helper,
            profile_id,
            action_type="change_medication_reminder_time",
            target_resource_id=schedule["id"],
            payload={"times": [{"time_of_day": "20:00"}]},
        )
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["status"] == "pending"
        assert body["diff"]["subject"] == "Metformin"
        assert body["diff"]["current"] == "7:00 PM"
        assert body["diff"]["proposed"] == "8:00 PM"

        approved = client.post(
            f"{suggestions_url(profile_id)}/{body['id']}/approve", headers=headers
        )
        assert approved.status_code == 200, approved.text
        assert approved.json()["status"] == "approved"

        row = db.get(MedicationSchedule, uuid.UUID(schedule["id"]))
        assert row is not None
        db.refresh(row)
        assert [entry.time_of_day.strftime("%H:%M") for entry in row.times] == ["20:00"]

    def test_the_diff_reads_the_current_value_at_review_time(
        self, client, owner, helper, schedule, clock
    ):
        """Section 86, and why ``current`` is not stored.

        The owner moves the reminder themselves after the suggestion is made. The
        review screen then shows what is *actually* there now, rather than the
        value that was there when the caregiver proposed -- which would be a diff
        against a reality that no longer exists.
        """
        headers, profile_id = owner
        active_caregiver(client, owner, helper, permissions={"medications": True})
        created = propose(
            client,
            helper,
            profile_id,
            action_type="change_medication_reminder_time",
            target_resource_id=schedule["id"],
            payload={"times": [{"time_of_day": "20:00"}]},
        ).json()

        client.patch(
            f"/api/v1/profiles/{profile_id}/medication-schedules/{schedule['id']}",
            json={"times": [{"time_of_day": "06:30:00"}]},
            headers=headers,
        )

        listed = client.get(suggestions_url(profile_id), headers=headers).json()
        found = next(row for row in listed["suggestions"] if row["id"] == created["id"])
        assert found["diff"]["current"] == "6:30 AM"
        assert found["diff"]["proposed"] == "8:00 PM"

    def test_declining_keeps_the_schedule_and_the_note_private(
        self, client, owner, helper, schedule, db, clock
    ):
        """Sections 25 and 88.

        The note is stored and the caregiver's own view of the same suggestion has
        no field for it -- not an empty string, no field at all.
        """
        headers, profile_id = owner
        active_caregiver(client, owner, helper, permissions={"medications": True})
        created = propose(
            client,
            helper,
            profile_id,
            action_type="change_medication_reminder_time",
            target_resource_id=schedule["id"],
            payload={"times": [{"time_of_day": "20:00"}]},
        ).json()

        declined = client.post(
            f"{suggestions_url(profile_id)}/{created['id']}/decline",
            json={"note": "The nurse asked me to keep it at seven."},
            headers=headers,
        )
        assert declined.status_code == 200
        assert declined.json()["status"] == "declined"
        assert declined.json()["decline_note"] is not None

        row = db.get(MedicationSchedule, uuid.UUID(schedule["id"]))
        db.refresh(row)
        assert [entry.time_of_day.strftime("%H:%M") for entry in row.times] == ["19:00"]

        caregiver_view = client.get(suggestions_url(profile_id), headers=helper).json()
        assert caregiver_view["suggestions"][0]["status"] == "declined"
        assert "decline_note" not in caregiver_view["suggestions"][0]
        assert "nurse" not in str(caregiver_view)

    def test_a_caregiver_cannot_propose_a_dose_change(
        self, client, owner, helper, schedule, clock
    ):
        """Section 85, and why it is unreachable rather than refused.

        There is no ``change_medication_dose`` action type, so the request fails
        the schema's Literal before any caregiver code runs -- and the database
        CHECK constraint, built from the same tuple, would refuse the row even if
        it somehow got that far.
        """
        _, profile_id = owner
        active_caregiver(client, owner, helper, permissions={"medications": True})
        for forbidden in (
            "change_medication_dose",
            "delete_condition",
            "change_diagnosis",
        ):
            response = propose(
                client,
                helper,
                profile_id,
                action_type=forbidden,
                target_resource_id=schedule["id"],
                payload={"dose": "1000 mg"},
            )
            assert response.status_code == 422, forbidden

    def test_a_caregiver_cannot_change_a_medication_directly(
        self, client, owner, helper, schedule, clock
    ):
        """Section 21: important changes are never applied by a caregiver account.

        Not "are checked first" -- there is no route. The medication record, the
        schedule and the pause control all depend on ``OwnedProfile``.
        """
        _, profile_id = owner
        active_caregiver(client, owner, helper, permissions={"medications": True})
        assert (
            client.patch(
                f"/api/v1/profiles/{profile_id}/medication-schedules/{schedule['id']}",
                json={"times": [{"time_of_day": "20:00:00"}]},
                headers=helper,
            ).status_code
            == 404
        )
        assert (
            client.patch(
                f"/api/v1/profiles/{profile_id}/medications/{schedule['medication_id']}",
                json={"dose": "1000 mg"},
                headers=helper,
            ).status_code
            == 404
        )

    def test_a_suggestion_needs_the_matching_permission(
        self, client, owner, helper, schedule, clock
    ):
        """A caregiver with ``appointments`` cannot propose a medication change."""
        _, profile_id = owner
        active_caregiver(client, owner, helper, permissions={"appointments": True})
        response = propose(
            client,
            helper,
            profile_id,
            action_type="change_medication_reminder_time",
            target_resource_id=schedule["id"],
            payload={"times": [{"time_of_day": "20:00"}]},
        )
        assert response.status_code == 404

    def test_a_malformed_payload_is_refused(self, client, owner, helper, schedule, clock):
        """Section 23: the payload is validated against the action's own schema.

        ``extra="forbid"``, so a field nobody declared cannot ride along, and a
        time that is not a time is refused rather than stored for approval to
        trip over later.
        """
        _, profile_id = owner
        active_caregiver(client, owner, helper, permissions={"medications": True})
        for payload in (
            {"times": [{"time_of_day": "tea time"}]},
            {"times": []},
            {"times": [{"time_of_day": "20:00"}], "also_change_the_dose": "1000 mg"},
            {},
        ):
            response = propose(
                client,
                helper,
                profile_id,
                action_type="change_medication_reminder_time",
                target_resource_id=schedule["id"],
                payload=payload,
            )
            assert response.status_code == 422, payload

    def test_a_target_belonging_to_someone_else_is_not_found(
        self, client, owner, helper, make_token, clock
    ):
        """Section 57: no data mixing between supported profiles.

        A caregiver sends a schedule id that is real -- it just belongs to a
        different person. The lookup is scoped by profile, so it resolves to
        nothing rather than to a stranger's medication.
        """
        _, profile_id = owner
        active_caregiver(client, owner, helper, permissions={"medications": True})

        stranger = ready_account(client, make_token)
        stranger_profile = client.get("/api/v1/me", headers=stranger).json()["profiles"][
            0
        ]["id"]
        medication_id = add_medication(client, stranger, stranger_profile)
        other = make_schedule(client, stranger, stranger_profile, medication_id).json()

        response = propose(
            client,
            helper,
            profile_id,
            action_type="change_medication_reminder_time",
            target_resource_id=other["id"],
            payload={"times": [{"time_of_day": "20:00"}]},
        )
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "suggestion_target_missing"

    def test_proposing_twice_with_one_client_id_makes_one_request(
        self, client, owner, helper, schedule, clock
    ):
        """Section 74: a retried POST does not create a second care request."""
        _, profile_id = owner
        active_caregiver(client, owner, helper, permissions={"medications": True})
        first = propose(
            client,
            helper,
            profile_id,
            action_type="change_medication_reminder_time",
            target_resource_id=schedule["id"],
            payload={"times": [{"time_of_day": "20:00"}]},
            client_suggestion_id="retry-1",
        ).json()
        second = propose(
            client,
            helper,
            profile_id,
            action_type="change_medication_reminder_time",
            target_resource_id=schedule["id"],
            payload={"times": [{"time_of_day": "20:00"}]},
            client_suggestion_id="retry-1",
        ).json()
        assert first["id"] == second["id"]
        listed = client.get(suggestions_url(profile_id), headers=helper).json()
        assert len(listed["suggestions"]) == 1

    def test_approving_twice_applies_once(self, client, owner, helper, schedule, clock):
        """Section 74 on the other side of the exchange.

        Proved with ``add_appointment``, where applying twice would be visible:
        two appointments rather than one.
        """
        headers, profile_id = owner
        active_caregiver(client, owner, helper, permissions={"appointments": True})
        created = propose(
            client,
            helper,
            profile_id,
            action_type="add_appointment",
            payload={
                "title": "Blood test",
                "scheduled_at": "2026-10-09T09:00:00+00:00",
                "timezone": "Europe/London",
                "appointment_type": "lab",
            },
        ).json()

        first = client.post(
            f"{suggestions_url(profile_id)}/{created['id']}/approve", headers=headers
        )
        second = client.post(
            f"{suggestions_url(profile_id)}/{created['id']}/approve", headers=headers
        )
        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json()["id"] == second.json()["id"]

        appointments = client.get(
            f"/api/v1/profiles/{profile_id}/appointments?scope=upcoming",
            headers=headers,
        ).json()
        assert [row["title"] for row in appointments] == ["Blood test"]

    def test_a_caregiver_may_withdraw_their_own_suggestion_and_not_anothers(
        self, client, owner, helper, make_token, schedule, clock
    ):
        """``cancelled`` exists in section 22's vocabulary, and this is who may
        use it: the caregiver who proposed, and nobody else (section 66)."""
        headers, profile_id = owner
        active_caregiver(client, owner, helper, permissions={"medications": True})
        second = {"Authorization": f"Bearer {make_token()}"}
        token = invite(
            client,
            headers,
            profile_id,
            name="Bilal",
            permissions={"medications": True},
        ).json()["token"]
        accept(client, second, token)

        created = propose(
            client,
            helper,
            profile_id,
            action_type="pause_medication_reminder",
            target_resource_id=schedule["id"],
        ).json()

        assert (
            client.post(
                f"{suggestions_url(profile_id)}/{created['id']}/cancel", headers=second
            ).status_code
            == 404
        )
        cancelled = client.post(
            f"{suggestions_url(profile_id)}/{created['id']}/cancel", headers=helper
        )
        assert cancelled.status_code == 200
        assert cancelled.json()["status"] == "cancelled"

    def test_a_caregiver_sees_only_their_own_suggestions(
        self, client, owner, helper, make_token, schedule, clock
    ):
        """Section 66, and section 88's status list.

        The owner sees both; each caregiver sees one.
        """
        headers, profile_id = owner
        active_caregiver(client, owner, helper, permissions={"medications": True})
        second = {"Authorization": f"Bearer {make_token()}"}
        token = invite(
            client,
            headers,
            profile_id,
            name="Bilal",
            permissions={"medications": True},
        ).json()["token"]
        accept(client, second, token)

        propose(
            client,
            helper,
            profile_id,
            action_type="pause_medication_reminder",
            target_resource_id=schedule["id"],
        )
        propose(
            client,
            second,
            profile_id,
            action_type="resume_medication_reminder",
            target_resource_id=schedule["id"],
        )

        owner_view = client.get(suggestions_url(profile_id), headers=headers).json()
        assert len(owner_view["suggestions"]) == 2
        mine = client.get(suggestions_url(profile_id), headers=helper).json()
        assert len(mine["suggestions"]) == 1
        assert mine["suggestions"][0]["action_type"] == "pause_medication_reminder"

    def test_the_owner_cannot_create_a_suggestion(self, client, owner, schedule, clock):
        """The owner changes their own records directly. A suggestion to oneself
        would make "whose suggestion is this?" a question with no answer."""
        headers, profile_id = owner
        response = propose(
            client,
            headers,
            profile_id,
            action_type="pause_medication_reminder",
            target_resource_id=schedule["id"],
        )
        assert response.status_code == 404

    def test_pausing_a_reminder_withdraws_future_doses(
        self, client, owner, helper, schedule, db, clock
    ):
        """Section 21 lists disabling reminders among the changes needing approval.

        Approval runs the ordinary ``set_paused``, so the future doses it
        withdraws are withdrawn exactly as they would be for the owner.
        """
        headers, profile_id = owner
        active_caregiver(client, owner, helper, permissions={"medications": True})
        created = propose(
            client,
            helper,
            profile_id,
            action_type="pause_medication_reminder",
            target_resource_id=schedule["id"],
        ).json()
        client.post(
            f"{suggestions_url(profile_id)}/{created['id']}/approve", headers=headers
        )

        row = db.get(MedicationSchedule, uuid.UUID(schedule["id"]))
        db.refresh(row)
        assert row.paused_at is not None
        assert row.is_active is False


# --- what approval re-checks -------------------------------------------------


class TestApprovalRevalidates:
    def test_a_revoked_caregivers_suggestion_cannot_be_approved(
        self, client, owner, helper, schedule, db, clock
    ):
        """Section 24, step 1, and the step that is easiest to skip.

        The permission is checked against the relationship *now*, not against
        what was true when the suggestion was made. A suggestion is not a
        capability somebody keeps after their access ends.
        """
        headers, profile_id = owner
        relationship_id = active_caregiver(
            client, owner, helper, permissions={"medications": True}
        )
        created = propose(
            client,
            helper,
            profile_id,
            action_type="change_medication_reminder_time",
            target_resource_id=schedule["id"],
            payload={"times": [{"time_of_day": "20:00"}]},
        ).json()

        client.delete(
            f"/api/v1/profiles/{profile_id}/caregivers/{relationship_id}",
            headers=headers,
        )

        refused = client.post(
            f"{suggestions_url(profile_id)}/{created['id']}/approve", headers=headers
        )
        assert refused.status_code == 409
        assert refused.json()["detail"]["code"] == "suggestion_not_pending"

        row = db.get(MedicationSchedule, uuid.UUID(schedule["id"]))
        db.refresh(row)
        assert [entry.time_of_day.strftime("%H:%M") for entry in row.times] == ["19:00"]

    def test_withdrawing_the_category_also_stops_approval(
        self, client, owner, helper, schedule, clock
    ):
        """The relationship is still active -- only the category was withdrawn."""
        headers, profile_id = owner
        relationship_id = active_caregiver(
            client, owner, helper, permissions={"medications": True}
        )
        created = propose(
            client,
            helper,
            profile_id,
            action_type="pause_medication_reminder",
            target_resource_id=schedule["id"],
        ).json()

        client.patch(
            f"/api/v1/profiles/{profile_id}/caregivers/{relationship_id}/permissions",
            json={"permissions": {"medications": False}},
            headers=headers,
        )
        refused = client.post(
            f"{suggestions_url(profile_id)}/{created['id']}/approve", headers=headers
        )
        assert refused.status_code == 409

    def test_a_deleted_target_is_reported_rather_than_applied(
        self, client, owner, helper, schedule, clock
    ):
        """Section 24, step 2: verify the target still exists.

        The review screen is told the target has gone, so it can say so instead of
        offering Approve on something unapplicable.
        """
        headers, profile_id = owner
        active_caregiver(client, owner, helper, permissions={"medications": True})
        created = propose(
            client,
            helper,
            profile_id,
            action_type="change_medication_reminder_time",
            target_resource_id=schedule["id"],
            payload={"times": [{"time_of_day": "20:00"}]},
        ).json()

        client.delete(
            f"/api/v1/profiles/{profile_id}/medication-schedules/{schedule['id']}",
            headers=headers,
        )

        listed = client.get(suggestions_url(profile_id), headers=headers).json()
        found = next(row for row in listed["suggestions"] if row["id"] == created["id"])
        assert found["diff"]["target_missing"] is True

        refused = client.post(
            f"{suggestions_url(profile_id)}/{created['id']}/approve", headers=headers
        )
        assert refused.status_code == 409
        assert refused.json()["detail"]["code"] == "suggestion_target_missing"

    def test_an_already_answered_suggestion_cannot_be_declined_again(
        self, client, owner, helper, schedule, clock
    ):
        headers, profile_id = owner
        active_caregiver(client, owner, helper, permissions={"medications": True})
        created = propose(
            client,
            helper,
            profile_id,
            action_type="pause_medication_reminder",
            target_resource_id=schedule["id"],
        ).json()
        client.post(
            f"{suggestions_url(profile_id)}/{created['id']}/decline",
            json={},
            headers=headers,
        )
        again = client.post(
            f"{suggestions_url(profile_id)}/{created['id']}/decline",
            json={},
            headers=headers,
        )
        assert again.status_code == 409

    def test_a_caregiver_cannot_approve_anything(
        self, client, owner, helper, schedule, clock
    ):
        """Approval depends on ``OwnedProfile``: only the person themselves."""
        _, profile_id = owner
        active_caregiver(client, owner, helper, permissions={"medications": True})
        created = propose(
            client,
            helper,
            profile_id,
            action_type="pause_medication_reminder",
            target_resource_id=schedule["id"],
        ).json()
        assert (
            client.post(
                f"{suggestions_url(profile_id)}/{created['id']}/approve", headers=helper
            ).status_code
            == 404
        )


# --- the assistant's tool layer (section 63) ---------------------------------


def any_account(db) -> User:
    """Any account, for a ToolContext that is only being asked what it lists.

    PRD 10 made ``ToolContext.account`` required: the safety tools write rows
    that record who acted. These tests never run one, so which account it is
    does not matter -- but having to pass one is the point, and defaulting it
    would be the thing PRD 9 refused to do with ``allowed``.
    """
    user = db.query(User).first()
    assert user is not None
    return user


class TestAssistantPermissions:
    """PRD 9 section 63, at the layer it names.

    There is no caregiver chat endpoint in PRD 9 -- that would need
    conversations, memory and preferences scoped to a caregiver account, none of
    which section 80 or 83 asks for. What section 63 *does* require is that the
    tool layer uses the caregiver's relationship scope, and that is what these
    tests cover: ``ToolContext.allowed`` has no default, so a future caregiver
    assistant cannot be written without choosing a scope.
    """

    def caregiver_context(self, db, profile_id: str, granted: set[str]):
        profile = db.get(Profile, uuid.UUID(profile_id))
        assert profile is not None
        return tools.ToolContext(
            db=db,
            profile=profile,
            now=NOW,
            local_date=NOW.date(),
            allowed=frozenset(granted),
            is_owner=False,
            account=any_account(db),
        )

    def test_a_caregiver_is_not_shown_a_tool_they_lack_the_category_for(
        self, client, owner, db, clock
    ):
        """Filtered out of ``specs``, not merely refused.

        A model that can see a tool will eventually tell the user it tried, which
        is its own small disclosure.
        """
        _, profile_id = owner
        context = self.caregiver_context(db, profile_id, {"medications"})
        names = {spec.name for spec in tools.specs(context)}
        assert "get_active_medications" in names
        assert "get_active_symptoms" not in names
        assert "get_recent_symptom_entries" not in names
        assert "get_upcoming_appointments" not in names

    def test_a_refused_tool_answers_as_if_it_does_not_exist(
        self, client, owner, db, clock
    ):
        """The same answer as an unknown tool, so a reply cannot be read as
        "that tool exists but you are not allowed it"."""
        _, profile_id = owner
        context = self.caregiver_context(db, profile_id, {"medications"})
        outcome = tools.run(context, "get_active_symptoms", {})
        assert outcome.is_error is True
        assert "no tool called" in outcome.content

    def test_a_caregiver_cannot_use_the_one_tool_that_writes(
        self, client, owner, db, clock
    ):
        """Section 64: a caregiver's changes go through a suggestion a person
        approves, so the write tool is the owner's alone -- even for a caregiver
        granted every category."""
        _, profile_id = owner
        context = self.caregiver_context(
            db, profile_id, set(permission_service.CAREGIVER_PERMISSION_KEYS)
        )
        names = {spec.name for spec in tools.specs(context)}
        assert "add_appointment_question" not in names
        outcome = tools.run(
            context, "add_appointment_question", {"text": "Ask about dizziness"}
        )
        assert outcome.is_error is True

    def test_a_tool_that_spans_categories_is_the_owners_alone(
        self, client, owner, db, clock
    ):
        """``get_today_summary`` mentions doses, appointments *and* symptoms.

        A caregiver granted only ``appointments`` must not learn a symptom count
        through a tool that happens to include one (section 18), and the
        permission-filtered caregiver home is the equivalent they do get.
        """
        _, profile_id = owner
        context = self.caregiver_context(
            db, profile_id, set(permission_service.CAREGIVER_PERMISSION_KEYS)
        )
        names = {spec.name for spec in tools.specs(context)}
        assert "get_today_summary" not in names
        assert "get_daily_checkin_summary" not in names

    def test_the_owners_assistant_keeps_every_tool(self, client, owner, db, clock):
        """PRD 8's assistant is the person's own and loses nothing to PRD 9.

        PRD 10 adds the only two tools an owner does *not* get, and they are
        not a loss: ``get_active_safety_alerts`` and
        ``acknowledge_safety_alert`` are a caregiver's view of alerts about
        somebody else (section 97). An owner's own safety history is
        ``get_safety_status``, which they do get.
        """
        _, profile_id = owner
        profile = db.get(Profile, uuid.UUID(profile_id))
        assert profile is not None
        context = tools.ToolContext(
            db=db,
            profile=profile,
            now=NOW,
            local_date=NOW.date(),
            allowed=tools.OWNER_SCOPE,
            is_owner=True,
            account=any_account(db),
        )
        caregiver_only = [tool.name for tool in tools.TOOLS if tool.caregiver_only]
        assert caregiver_only == [
            "get_active_safety_alerts",
            "acknowledge_safety_alert",
        ]
        assert len(tools.specs(context)) == len(tools.TOOLS) - len(caregiver_only)

    def test_a_caregivers_granted_set_drives_the_scope(
        self, client, owner, helper, db, clock
    ):
        """The scope is built from the stored permissions, not from a literal.

        This is the join that section 63 asks for: the relationship's granted
        keys *are* what a caregiver-scoped tool context would carry.
        """
        _, profile_id = owner
        active_caregiver(
            client,
            owner,
            helper,
            permissions={"medications": True, "appointments": True},
        )
        from app.models import CaregiverRelationship

        # Read the caregiver's account off the relationship rather than guessing
        # which of the two accounts is which.
        relationship = db.query(CaregiverRelationship).one()
        assert relationship.caregiver_account_id is not None
        supported = permission_service.supported_profiles(
            db, relationship.caregiver_account_id
        )
        assert len(supported) == 1
        granted = permission_service.granted_keys(supported[0])
        assert granted == frozenset({"medications", "appointments"})

        context = self.caregiver_context(db, profile_id, set(granted))
        names = {spec.name for spec in tools.specs(context)}
        assert names == {
            "get_active_medications",
            "get_recent_medication_history",
            "get_upcoming_appointments",
            "get_appointment_questions",
        }
