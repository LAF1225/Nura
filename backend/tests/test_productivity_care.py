"""The caregiver side of routines (PRD 12, sections 16, 17, 42, 43 and 56).

PRD 9 reserved the ``routines`` permission and deliberately left it empty, with
a test asserting that it unlocked nothing. PRD 12 builds the source, so this
file is the other half of that story: what a caregiver with ``routines`` can
now see, what they can propose, and -- the part worth being sure about -- what
the permission still does not reach.

``TestIsolation`` is section 42, and it is checked as *absence*: there is no
caregiver route anywhere that reaches a task, an alarm or a general reminder,
and no caregiver suggestion action that could create one. A test walks the
whole suggestion registry to say so.
"""

from datetime import UTC, date, datetime

import pytest

from app.api.deps import current_time
from app.main import app
from tests.test_caregivers import active_caregiver
from tests.test_devices import ready_account
from tests.test_today import Clock

#: A Monday at noon, matching the caregiver tests this file borrows from.
NOW = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)
TODAY = date(2026, 9, 28)

STEPS = [{"title": "Drink water"}, {"title": "Stretch for 5 minutes"}]


@pytest.fixture
def clock(client) -> Clock:
    """Declared locally, per this repository's fixture convention."""
    fake = Clock()
    fake.now = NOW
    app.dependency_overrides[current_time] = lambda: fake.now
    return fake


@pytest.fixture
def owner(client, make_token) -> tuple[dict[str, str], str]:
    """The primary user, and the profile Nura is for.

    Declared here rather than imported, per this repository's convention.
    """
    headers = ready_account(client, make_token)
    profile_id = client.get("/api/v1/me", headers=headers).json()["profiles"][0]["id"]
    return headers, profile_id


@pytest.fixture
def helper(client, make_token) -> dict[str, str]:
    """A second account with no profile of its own (PRD 9, section 14)."""
    return {"Authorization": f"Bearer {make_token()}"}


def routines_url(profile_id: str) -> str:
    return f"/api/v1/profiles/{profile_id}/routines"


def suggestions_url(profile_id: str) -> str:
    return f"/api/v1/profiles/{profile_id}/caregiver-suggestions"


def create_routine(client, headers, profile_id, **fields) -> dict:
    body = {
        "title": "Morning routine",
        "time_of_day": "07:30",
        "start_date": TODAY.isoformat(),
        "schedule_type": "daily",
        "steps": [dict(step) for step in STEPS],
        **fields,
    }
    response = client.post(routines_url(profile_id), json=body, headers=headers)
    assert response.status_code in (200, 201), response.json()
    return response.json()["routine"]


class TestCaregiverReads:
    def test_a_caregiver_with_routines_sees_them(self, client, owner, helper, clock):
        """Section 16's first bullet, and section 56's route."""
        headers, profile_id = owner
        create_routine(client, headers, profile_id)
        active_caregiver(client, owner, helper, permissions={"routines": True})

        body = client.get(
            f"/api/v1/profiles/{profile_id}/care/routines", headers=helper
        ).json()
        assert len(body["routines"]) == 1
        row = body["routines"][0]
        assert row["title"] == "Morning routine"
        assert row["schedule_label"] == "Every day at 7:30 AM"
        assert row["step_count"] == 2
        assert row["paused"] is False
        assert row["today_status"] == "scheduled"
        assert row["today_progress_label"] == "0 of 2 complete"
        # Section 42, said on the caregiver's own screen.
        assert "stay private" in body["scope_note"]

    def test_a_caregiver_without_routines_is_refused(self, client, owner, helper, clock):
        """404, not 403 -- the same answer as a profile that is not theirs, so
        the absence of a permission reveals nothing (PRD 9, section 18)."""
        headers, profile_id = owner
        create_routine(client, headers, profile_id)
        active_caregiver(client, owner, helper, permissions={"medications": True})
        assert (
            client.get(
                f"/api/v1/profiles/{profile_id}/care/routines", headers=helper
            ).status_code
            == 404
        )

    def test_the_owner_cannot_use_the_caregiver_route(self, client, owner, clock):
        """Section 56: *do not use owner authorization dependency.*

        The owner has their own, richer route for all of this, and refusing
        here keeps "whose view is this" a question with one answer.
        """
        headers, profile_id = owner
        assert (
            client.get(
                f"/api/v1/profiles/{profile_id}/care/routines", headers=headers
            ).status_code
            == 404
        )

    def test_an_unrelated_account_reaches_nothing(self, client, owner, make_token, clock):
        headers, profile_id = owner
        create_routine(client, headers, profile_id)
        stranger = ready_account(client, make_token)
        assert (
            client.get(
                f"/api/v1/profiles/{profile_id}/care/routines", headers=stranger
            ).status_code
            == 404
        )

    def test_a_revoked_caregiver_loses_it_immediately(self, client, owner, helper, clock):
        """PRD 9 section 52, applied to the new category."""
        headers, profile_id = owner
        create_routine(client, headers, profile_id)
        relationship_id = active_caregiver(
            client, owner, helper, permissions={"routines": True}
        )
        assert (
            client.get(
                f"/api/v1/profiles/{profile_id}/care/routines", headers=helper
            ).status_code
            == 200
        )

        client.delete(
            f"/api/v1/profiles/{profile_id}/caregivers/{relationship_id}",
            headers=headers,
        )
        assert (
            client.get(
                f"/api/v1/profiles/{profile_id}/care/routines", headers=helper
            ).status_code
            == 404
        )

    def test_an_archived_routine_is_not_shown(self, client, owner, helper, clock):
        headers, profile_id = owner
        routine = create_routine(client, headers, profile_id)
        client.post(
            f"{routines_url(profile_id)}/{routine['id']}/archive", headers=headers
        )
        active_caregiver(client, owner, helper, permissions={"routines": True})
        body = client.get(
            f"/api/v1/profiles/{profile_id}/care/routines", headers=helper
        ).json()
        assert body["routines"] == []

    def test_the_caregiver_view_is_narrower_than_the_owners(
        self, client, owner, helper, clock
    ):
        """PRD 9 section 67, applied again: a caregiver endpoint returns only
        what the permission needs.

        No step titles, no provenance, no completion rows -- a tick-by-tick log
        of somebody's morning is the surveillance experience PRD 9 section 2
        rules out.
        """
        headers, profile_id = owner
        create_routine(client, headers, profile_id)
        active_caregiver(client, owner, helper, permissions={"routines": True})
        row = client.get(
            f"/api/v1/profiles/{profile_id}/care/routines", headers=helper
        ).json()["routines"][0]
        assert set(row) == {
            "routine_id",
            "title",
            "schedule_label",
            "step_count",
            "paused",
            "today_status",
            "today_done",
            "today_total",
            "today_progress_label",
        }


class TestRoutineSuggestions:
    def test_a_caregiver_can_propose_a_routine_and_the_user_approves_it(
        self, client, owner, helper, clock
    ):
        """Sections 16, 17 and 43.

        Approval goes through the ordinary routine service, so the routine that
        appears has runs, steps and a schedule exactly as one the person
        created -- and it carries ``caregiver_suggestion`` for as long as it
        exists.
        """
        headers, profile_id = owner
        active_caregiver(client, owner, helper, permissions={"routines": True})

        created = client.post(
            suggestions_url(profile_id),
            json={
                "action_type": "add_routine",
                "payload": {
                    "title": "Evening stretch",
                    "time_of_day": "19:30",
                    "timezone": "Europe/London",
                    "start_date": TODAY.isoformat(),
                    "schedule_type": "daily",
                    "steps": [{"title": "Stretch"}, {"title": "Sit quietly"}],
                },
            },
            headers=helper,
        )
        assert created.status_code == 201, created.json()
        suggestion = created.json()
        assert suggestion["category"] == "routines"
        assert suggestion["action_label"] == "Suggest a routine"
        assert suggestion["diff"]["subject"] == "Evening stretch"
        assert "Stretch" in suggestion["diff"]["proposed"]

        approved = client.post(
            f"{suggestions_url(profile_id)}/{suggestion['id']}/approve", headers=headers
        )
        assert approved.status_code == 200, approved.json()
        assert approved.json()["status"] == "approved"

        routines = client.get(routines_url(profile_id), headers=headers).json()
        assert len(routines["routines"]) == 1
        routine = routines["routines"][0]
        assert routine["title"] == "Evening stretch"
        assert routine["source"] == "caregiver_suggestion"
        assert routine["source_label"] == "From a care request you approved"
        assert [step["title"] for step in routine["steps"]] == ["Stretch", "Sit quietly"]

    def test_a_routine_suggestion_must_have_steps(self, client, owner, helper, clock):
        """A routine with no steps generates no runs, so proposing one would be
        proposing something the person could approve and find does nothing."""
        headers, profile_id = owner
        active_caregiver(client, owner, helper, permissions={"routines": True})
        response = client.post(
            suggestions_url(profile_id),
            json={
                "action_type": "add_routine",
                "payload": {
                    "title": "Nothing",
                    "time_of_day": "19:30",
                    "timezone": "UTC",
                    "start_date": TODAY.isoformat(),
                    "steps": [],
                },
            },
            headers=helper,
        )
        assert response.status_code == 422

    def test_a_caregiver_can_propose_a_new_time(self, client, owner, helper, clock):
        headers, profile_id = owner
        routine = create_routine(client, headers, profile_id)
        active_caregiver(client, owner, helper, permissions={"routines": True})

        suggestion = client.post(
            suggestions_url(profile_id),
            json={
                "action_type": "change_routine_time",
                "target_resource_id": routine["id"],
                "payload": {"time_of_day": "08:15"},
            },
            headers=helper,
        ).json()
        assert suggestion["diff"]["current"] == "Every day at 7:30 AM"
        assert suggestion["diff"]["proposed"] == "Every day at 8:15 AM"

        client.post(
            f"{suggestions_url(profile_id)}/{suggestion['id']}/approve", headers=headers
        )
        updated = client.get(
            f"{routines_url(profile_id)}/{routine['id']}", headers=headers
        ).json()
        assert updated["schedule_label"] == "Every day at 8:15 AM"

    def test_a_caregiver_can_propose_pausing_one(self, client, owner, helper, clock):
        headers, profile_id = owner
        routine = create_routine(client, headers, profile_id)
        active_caregiver(client, owner, helper, permissions={"routines": True})

        suggestion = client.post(
            suggestions_url(profile_id),
            json={
                "action_type": "pause_routine",
                "target_resource_id": routine["id"],
                "payload": {},
            },
            headers=helper,
        ).json()
        assert suggestion["diff"]["proposed"] == "Routine paused"

        client.post(
            f"{suggestions_url(profile_id)}/{suggestion['id']}/approve", headers=headers
        )
        updated = client.get(
            f"{routines_url(profile_id)}/{routine['id']}", headers=headers
        ).json()
        assert updated["status"] == "paused"

    def test_a_caregiver_without_routines_cannot_propose_one(
        self, client, owner, helper, clock
    ):
        """The permission is checked when the suggestion is created and again
        at approval (PRD 9, section 24)."""
        headers, profile_id = owner
        active_caregiver(client, owner, helper, permissions={"medications": True})
        response = client.post(
            suggestions_url(profile_id),
            json={
                "action_type": "add_routine",
                "payload": {
                    "title": "Evening stretch",
                    "time_of_day": "19:30",
                    "timezone": "UTC",
                    "start_date": TODAY.isoformat(),
                    "steps": [{"title": "Stretch"}],
                },
            },
            headers=helper,
        )
        assert response.status_code == 404

    def test_a_permission_withdrawn_after_proposing_cannot_be_approved(
        self, client, owner, helper, clock
    ):
        """PRD 9 section 24 step 1: not "was it allowed when they asked" but
        "is it allowed now"."""
        headers, profile_id = owner
        relationship_id = active_caregiver(
            client, owner, helper, permissions={"routines": True}
        )
        suggestion = client.post(
            suggestions_url(profile_id),
            json={
                "action_type": "add_routine",
                "payload": {
                    "title": "Evening stretch",
                    "time_of_day": "19:30",
                    "timezone": "UTC",
                    "start_date": TODAY.isoformat(),
                    "steps": [{"title": "Stretch"}],
                },
            },
            headers=helper,
        ).json()

        client.patch(
            f"/api/v1/profiles/{profile_id}/caregivers/{relationship_id}/permissions",
            json={"permissions": {"routines": False}},
            headers=headers,
        )
        refused = client.post(
            f"{suggestions_url(profile_id)}/{suggestion['id']}/approve", headers=headers
        )
        assert refused.status_code == 409
        assert (
            client.get(routines_url(profile_id), headers=headers).json()["routines"] == []
        )

    def test_declining_leaves_no_routine(self, client, owner, helper, clock):
        headers, profile_id = owner
        active_caregiver(client, owner, helper, permissions={"routines": True})
        suggestion = client.post(
            suggestions_url(profile_id),
            json={
                "action_type": "add_routine",
                "payload": {
                    "title": "Evening stretch",
                    "time_of_day": "19:30",
                    "timezone": "UTC",
                    "start_date": TODAY.isoformat(),
                    "steps": [{"title": "Stretch"}],
                },
            },
            headers=helper,
        ).json()
        client.post(
            f"{suggestions_url(profile_id)}/{suggestion['id']}/decline",
            json={"note": "Not for me"},
            headers=headers,
        )
        assert (
            client.get(routines_url(profile_id), headers=headers).json()["routines"] == []
        )

    def test_approving_twice_creates_one_routine(self, client, owner, helper, clock):
        """PRD 9 section 74. A retried Approve returns the same suggestion."""
        headers, profile_id = owner
        active_caregiver(client, owner, helper, permissions={"routines": True})
        suggestion = client.post(
            suggestions_url(profile_id),
            json={
                "action_type": "add_routine",
                "payload": {
                    "title": "Evening stretch",
                    "time_of_day": "19:30",
                    "timezone": "UTC",
                    "start_date": TODAY.isoformat(),
                    "steps": [{"title": "Stretch"}],
                },
            },
            headers=helper,
        ).json()
        url = f"{suggestions_url(profile_id)}/{suggestion['id']}/approve"
        client.post(url, headers=headers)
        client.post(url, headers=headers)
        assert (
            len(client.get(routines_url(profile_id), headers=headers).json()["routines"])
            == 1
        )

    def test_a_routine_that_was_deleted_cannot_be_changed(
        self, client, owner, helper, clock
    ):
        headers, profile_id = owner
        routine = create_routine(client, headers, profile_id)
        active_caregiver(client, owner, helper, permissions={"routines": True})
        suggestion = client.post(
            suggestions_url(profile_id),
            json={
                "action_type": "change_routine_time",
                "target_resource_id": routine["id"],
                "payload": {"time_of_day": "08:15"},
            },
            headers=helper,
        ).json()
        client.delete(f"{routines_url(profile_id)}/{routine['id']}", headers=headers)

        refused = client.post(
            f"{suggestions_url(profile_id)}/{suggestion['id']}/approve", headers=headers
        )
        assert refused.status_code == 409
        assert refused.json()["detail"]["code"] == "suggestion_target_missing"

    def test_a_routine_suggestion_shows_on_today(self, client, owner, helper, clock):
        """PRD 9 section 87: a pending care request is visible on Today."""
        headers, profile_id = owner
        active_caregiver(client, owner, helper, permissions={"routines": True})
        client.post(
            suggestions_url(profile_id),
            json={
                "action_type": "add_routine",
                "payload": {
                    "title": "Evening stretch",
                    "time_of_day": "19:30",
                    "timezone": "UTC",
                    "start_date": TODAY.isoformat(),
                    "steps": [{"title": "Stretch"}],
                },
            },
            headers=helper,
        )
        summary = client.get(
            f"/api/v1/profiles/{profile_id}/care-summary", headers=headers
        ).json()
        assert summary["pending_suggestion_count"] == 1


class TestIsolation:
    def test_there_is_no_action_that_touches_a_task_an_alarm_or_a_reminder(self):
        """**Section 42, as the absence of an action type.**

        A caregiver cannot reach into somebody's task list, and the way that is
        guaranteed is not validation -- it is that the registry has no entry
        that could carry the request, so a request for one fails schema
        validation before any code runs.
        """
        from app.services.caregivers import suggestions

        for name, action in suggestions.ACTIONS.items():
            assert action.category in ("medications", "appointments", "routines"), name
            fields = set(action.payload_model.model_fields)
            assert "task_title" not in fields, name
            assert "alarm_label" not in fields, name
        assert not any(
            word in name
            for name in suggestions.ACTIONS
            for word in ("task", "alarm", "reminder_title")
        )

    def test_the_routines_permission_reaches_no_other_route(
        self, client, owner, helper, clock
    ):
        """Walked rather than reasoned about: every owner-side daily-life route
        answers 404 for a caregiver, whatever they were granted."""
        headers, profile_id = owner
        create_routine(client, headers, profile_id)
        active_caregiver(client, owner, helper, permissions={"routines": True})

        for path in (
            "tasks",
            "alarms",
            "reminders",
            "reminder-occurrences",
            "routines",
            "routine-runs/today",
            "daily-life/summary",
        ):
            response = client.get(f"/api/v1/profiles/{profile_id}/{path}", headers=helper)
            assert response.status_code == 404, path

    def test_a_caregiver_cannot_write_a_routine_directly(
        self, client, owner, helper, clock
    ):
        """PRD 9 section 21: a caregiver never changes anything.

        Not refused by a check -- there is no caregiver route that writes a
        routine. The owner's own route answers 404 because the caregiver does
        not own the profile.
        """
        headers, profile_id = owner
        active_caregiver(client, owner, helper, permissions={"routines": True})
        response = client.post(
            routines_url(profile_id),
            json={
                "title": "Mine now",
                "time_of_day": "06:00",
                "start_date": TODAY.isoformat(),
                "steps": [{"title": "Up"}],
            },
            headers=helper,
        )
        assert response.status_code == 404
        assert (
            client.get(routines_url(profile_id), headers=headers).json()["routines"] == []
        )

    def test_the_permission_list_describes_what_it_shares_now(self, client, clock):
        """The description stopped saying "nothing yet", because it no longer
        is -- and it says where the edge is (section 42)."""
        response = client.get("/api/v1/caregiver-permissions")
        rows = {row["key"]: row for row in response.json()}
        assert "Nothing yet" not in rows["routines"]["description"]
        assert "stay private" in rows["routines"]["description"]
        assert rows["routines"]["has_data"] is True
