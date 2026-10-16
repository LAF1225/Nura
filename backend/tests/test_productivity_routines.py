"""Routines, their steps, their runs and their step completions.

PRD 12, sections 12, 13, 14, 15, 24, 39, 48 and 55.

Two things in here are PRD 12 departing from PRD 5 on purpose, and both have
their own test.

**A run covers a day, not a moment.** A morning routine is a checklist for the
morning, so today's run exists from the start of the day even if its time has
gone, and it stays open until the day is over. A dose does not work that way,
and the difference is deliberate: there was nothing to remind anybody about at
eight, but there is still a glass of water to tick off at nine.

**Missed is decided by the day, not the clock.** A routine is not missed at
half past nine. It is missed when the day is over, and nothing follows from it.
"""

import uuid
from datetime import UTC, date, datetime

import pytest

from app.api.deps import current_time
from app.main import app
from tests.test_devices import ready_account
from tests.test_today import Clock

TODAY = date(2026, 9, 13)
NOON = datetime(2026, 9, 13, 12, 0, tzinfo=UTC)

STEPS = [
    {"title": "Drink water"},
    {"title": "Stretch for 5 minutes"},
    {"title": "Review Today", "optional": True},
]


@pytest.fixture
def clock(client) -> Clock:
    fake = Clock()
    fake.now = NOON
    app.dependency_overrides[current_time] = lambda: fake.now
    return fake


@pytest.fixture
def account(client, make_token) -> tuple[dict[str, str], str]:
    headers = ready_account(client, make_token)
    profile_id = client.get("/api/v1/me", headers=headers).json()["profiles"][0]["id"]
    return headers, profile_id


def routines_url(profile_id: str) -> str:
    return f"/api/v1/profiles/{profile_id}/routines"


def runs_url(profile_id: str) -> str:
    return f"/api/v1/profiles/{profile_id}/routine-runs"


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
    return response.json()


class TestRoutineCrud:
    def test_a_routine_keeps_its_steps_in_order(self, client, account, clock):
        headers, profile_id = account
        routine = create_routine(client, headers, profile_id)["routine"]
        assert [step["title"] for step in routine["steps"]] == [
            "Drink water",
            "Stretch for 5 minutes",
            "Review Today",
        ]
        assert [step["position"] for step in routine["steps"]] == [0, 1, 2]
        assert routine["steps"][2]["optional"] is True
        assert routine["schedule_label"] == "Every day at 7:30 AM"
        assert routine["source"] == "user"
        assert routine["source_label"] == "Added by you"

    def test_a_routine_needs_at_least_one_step(self, client, account, clock):
        """A routine with no steps generates no runs, so an empty one is a
        thing somebody could create and then find does nothing."""
        headers, profile_id = account
        response = client.post(
            routines_url(profile_id),
            json={
                "title": "Empty",
                "time_of_day": "07:30",
                "start_date": TODAY.isoformat(),
                "steps": [],
            },
            headers=headers,
        )
        assert response.status_code == 422

    def test_selected_days_needs_days(self, client, account, clock):
        headers, profile_id = account
        response = client.post(
            routines_url(profile_id),
            json={
                "title": "Weekday routine",
                "time_of_day": "07:30",
                "start_date": TODAY.isoformat(),
                "schedule_type": "selected_days",
                "steps": [{"title": "Stretch"}],
            },
            headers=headers,
        )
        assert response.status_code == 422

    def test_replacing_the_steps_renumbers_them(self, client, account, clock):
        """Section 48. The whole list rather than a diff, which makes Move Up,
        Move Down and drag-and-drop one operation on the server."""
        headers, profile_id = account
        routine_id = create_routine(client, headers, profile_id)["routine"]["id"]
        updated = client.patch(
            f"{routines_url(profile_id)}/{routine_id}",
            json={
                "steps": [
                    {"title": "Stretch for 5 minutes"},
                    {"title": "Drink water"},
                ]
            },
            headers=headers,
        ).json()
        assert [step["title"] for step in updated["steps"]] == [
            "Stretch for 5 minutes",
            "Drink water",
        ]
        assert [step["position"] for step in updated["steps"]] == [0, 1]

    def test_pausing_stops_the_runs_and_keeps_the_routine(self, client, account, clock):
        headers, profile_id = account
        routine_id = create_routine(client, headers, profile_id)["routine"]["id"]
        paused = client.post(
            f"{routines_url(profile_id)}/{routine_id}/pause", headers=headers
        ).json()
        assert paused["status"] == "paused"
        assert paused["today_run"] is None

        resumed = client.post(
            f"{routines_url(profile_id)}/{routine_id}/resume", headers=headers
        ).json()
        assert resumed["status"] == "active"
        assert resumed["today_run"] is not None

    def test_archiving_keeps_the_history(self, client, account, clock):
        """What somebody wants instead of deleting: "I did this every morning
        for a month" is still true afterwards."""
        headers, profile_id = account
        routine = create_routine(client, headers, profile_id)["routine"]
        run_id = routine["today_run"]["id"]
        step_id = routine["steps"][0]["id"]
        client.post(
            f"{runs_url(profile_id)}/{run_id}/steps/{step_id}/complete", headers=headers
        )

        archived = client.post(
            f"{routines_url(profile_id)}/{routine['id']}/archive", headers=headers
        ).json()
        assert archived["status"] == "archived"
        run = client.get(f"{runs_url(profile_id)}/{run_id}", headers=headers).json()
        assert run["completed_steps"] == 1

    def test_deleting_takes_the_runs_with_it(self, client, account, clock):
        headers, profile_id = account
        routine = create_routine(client, headers, profile_id)["routine"]
        run_id = routine["today_run"]["id"]
        client.delete(f"{routines_url(profile_id)}/{routine['id']}", headers=headers)
        assert (
            client.get(f"{runs_url(profile_id)}/{run_id}", headers=headers).status_code
            == 404
        )

    def test_the_same_client_id_twice_is_one_routine(self, client, account, clock):
        headers, profile_id = account
        first = create_routine(client, headers, profile_id, client_routine_id="r1")
        second = create_routine(client, headers, profile_id, client_routine_id="r1")
        assert first["created"] is True
        assert second["created"] is False

    def test_another_account_gets_a_404(self, client, account, make_token, clock):
        headers, profile_id = account
        routine_id = create_routine(client, headers, profile_id)["routine"]["id"]
        stranger = ready_account(client, make_token)
        assert (
            client.get(
                f"{routines_url(profile_id)}/{routine_id}", headers=stranger
            ).status_code
            == 404
        )


class TestRunGeneration:
    def test_todays_run_exists_even_though_its_time_has_gone(
        self, client, account, clock
    ):
        """**The departure from PRD 5's generator, and the reason for it.**

        It is noon; the routine is for half past seven. The run exists, because
        a routine is a checklist for a day and somebody should be able to tick
        off the water they drank at half past seven.
        """
        headers, profile_id = account
        routine = create_routine(client, headers, profile_id)["routine"]
        run = routine["today_run"]
        assert run is not None
        assert run["local_date"] == TODAY.isoformat()
        assert run["status"] == "scheduled"
        assert datetime.fromisoformat(run["scheduled_for"]) < clock.now

    def test_a_fortnight_of_runs_is_generated(self, client, account, clock):
        headers, profile_id = account
        create_routine(client, headers, profile_id)
        runs = client.get(f"{runs_url(profile_id)}/today", headers=headers).json()
        assert len(runs["runs"]) == 1  # today's, which is what the endpoint is for

    def test_a_selected_days_routine_only_runs_on_those_days(
        self, client, account, clock
    ):
        """13 September 2026 is a Sunday, so a weekday routine has no run."""
        headers, profile_id = account
        routine = create_routine(
            client,
            headers,
            profile_id,
            schedule_type="selected_days",
            weekdays=[0, 1, 2, 3, 4],
        )["routine"]
        assert routine["today_run"] is None

        clock.advance(days=1)  # Monday
        refreshed = client.get(
            f"{routines_url(profile_id)}/{routine['id']}", headers=headers
        ).json()
        assert refreshed["today_run"] is not None

    def test_a_run_whose_day_has_gone_is_missed(self, client, account, clock):
        """By the day rather than by the clock, which is the honest reading of
        a checklist. Nothing follows from it."""
        headers, profile_id = account
        routine = create_routine(client, headers, profile_id)["routine"]
        run_id = routine["today_run"]["id"]

        clock.advance(days=1)
        client.get(f"{routines_url(profile_id)}", headers=headers)
        run = client.get(f"{runs_url(profile_id)}/{run_id}", headers=headers).json()
        assert run["status"] == "missed"
        assert run["status_label"] == "Not done"

    def test_a_run_is_not_missed_later_the_same_day(self, client, account, clock):
        headers, profile_id = account
        routine = create_routine(client, headers, profile_id)["routine"]
        run_id = routine["today_run"]["id"]

        clock.advance(hours=11)
        client.get(f"{routines_url(profile_id)}", headers=headers)
        run = client.get(f"{runs_url(profile_id)}/{run_id}", headers=headers).json()
        assert run["status"] == "scheduled"

    def test_changing_the_time_rebuilds_the_untouched_runs(self, client, account, clock):
        headers, profile_id = account
        routine_id = create_routine(client, headers, profile_id)["routine"]["id"]
        updated = client.patch(
            f"{routines_url(profile_id)}/{routine_id}",
            json={"time_of_day": "08:15"},
            headers=headers,
        ).json()
        assert updated["schedule_label"] == "Every day at 8:15 AM"
        moment = datetime.fromisoformat(updated["today_run"]["scheduled_for"])
        assert moment.astimezone(UTC).hour == 8

    def test_a_started_run_is_cancelled_rather_than_deleted(
        self, db, client, account, clock
    ):
        """Deleting a run somebody had begun would erase something they did."""
        from app.models import RoutineRun

        headers, profile_id = account
        routine = create_routine(client, headers, profile_id)["routine"]
        run_id = routine["today_run"]["id"]
        step_id = routine["steps"][0]["id"]
        client.post(
            f"{runs_url(profile_id)}/{run_id}/steps/{step_id}/complete", headers=headers
        )
        client.patch(
            f"{routines_url(profile_id)}/{routine['id']}",
            json={"time_of_day": "09:00"},
            headers=headers,
        )
        row = db.get(RoutineRun, uuid.UUID(run_id))
        db.refresh(row)
        assert row is not None
        assert row.status == "cancelled"


class TestStepCompletion:
    def test_ticking_a_step_starts_the_run_and_moves_the_progress(
        self, client, account, clock
    ):
        headers, profile_id = account
        routine = create_routine(client, headers, profile_id)["routine"]
        run_id = routine["today_run"]["id"]
        first, second, _ = (step["id"] for step in routine["steps"])

        run = client.post(
            f"{runs_url(profile_id)}/{run_id}/steps/{first}/complete", headers=headers
        ).json()
        assert run["status"] == "in_progress"
        assert run["completed_steps"] == 1
        assert run["progress_label"] == "1 of 3 complete. Next: Stretch for 5 minutes"
        assert run["next_step_id"] == second

    def test_ticking_the_same_step_twice_is_one_row(self, client, account, clock):
        """Section 39: an offline queue that retries cannot invent progress."""
        headers, profile_id = account
        routine = create_routine(client, headers, profile_id)["routine"]
        run_id = routine["today_run"]["id"]
        step_id = routine["steps"][0]["id"]
        url = f"{runs_url(profile_id)}/{run_id}/steps/{step_id}/complete"

        client.post(url, json={"client_completion_id": "c1"}, headers=headers)
        run = client.post(
            url, json={"client_completion_id": "c1"}, headers=headers
        ).json()
        assert run["completed_steps"] == 1
        assert len(run["completions"]) == 1

    def test_a_step_can_be_skipped(self, client, account, clock):
        """ "I skipped the stretch" is a different fact from "I have not got to
        it yet", and nothing interprets either."""
        headers, profile_id = account
        routine = create_routine(client, headers, profile_id)["routine"]
        run_id = routine["today_run"]["id"]
        step_id = routine["steps"][1]["id"]
        run = client.post(
            f"{runs_url(profile_id)}/{run_id}/steps/{step_id}/complete",
            json={"state": "skipped"},
            headers=headers,
        ).json()
        assert run["skipped_steps"] == 1
        assert run["completed_steps"] == 0
        assert run["completions"][0]["state_label"] == "Skipped"

    def test_a_step_can_be_un_ticked(self, client, account, clock):
        """A checklist needs Undo as much as a task does."""
        headers, profile_id = account
        routine = create_routine(client, headers, profile_id)["routine"]
        run_id = routine["today_run"]["id"]
        step_id = routine["steps"][0]["id"]
        url = f"{runs_url(profile_id)}/{run_id}/steps/{step_id}/complete"
        client.post(url, headers=headers)
        run = client.delete(url, headers=headers).json()
        assert run["completed_steps"] == 0
        assert run["next_step_id"] == step_id

    def test_a_whole_run_can_be_completed_with_steps_untouched(
        self, client, account, clock
    ):
        """Somebody who did their routine without opening the app should be
        able to say so in one tap. Insisting on three taps first would teach
        people to lie to the app."""
        headers, profile_id = account
        routine = create_routine(client, headers, profile_id)["routine"]
        run_id = routine["today_run"]["id"]
        result = client.post(
            f"{runs_url(profile_id)}/{run_id}/complete", headers=headers
        ).json()
        assert result["applied"] is True
        assert result["run"]["status"] == "completed"
        assert result["run"]["completed_steps"] == 0

    def test_completing_a_run_twice_happens_once(self, client, account, clock):
        headers, profile_id = account
        routine = create_routine(client, headers, profile_id)["routine"]
        run_id = routine["today_run"]["id"]
        client.post(f"{runs_url(profile_id)}/{run_id}/complete", headers=headers)
        again = client.post(
            f"{runs_url(profile_id)}/{run_id}/complete", headers=headers
        ).json()
        assert again["applied"] is False

    def test_skipping_a_run_is_not_missing_it(self, client, account, clock):
        """Skipping is something a person decided; missing is what the end of a
        day concluded. Keeping them apart is the difference between a record
        and a judgement."""
        headers, profile_id = account
        routine = create_routine(client, headers, profile_id)["routine"]
        run_id = routine["today_run"]["id"]
        result = client.post(
            f"{runs_url(profile_id)}/{run_id}/skip", headers=headers
        ).json()
        assert result["run"]["status"] == "skipped"
        assert result["run"]["status_label"] == "Skipped"

    def test_a_recorded_run_refuses_further_steps(self, client, account, clock):
        headers, profile_id = account
        routine = create_routine(client, headers, profile_id)["routine"]
        run_id = routine["today_run"]["id"]
        step_id = routine["steps"][0]["id"]
        client.post(f"{runs_url(profile_id)}/{run_id}/complete", headers=headers)
        response = client.post(
            f"{runs_url(profile_id)}/{run_id}/steps/{step_id}/complete", headers=headers
        )
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "routine_run_not_actionable"

    def test_a_step_from_another_routine_is_a_404(self, client, account, clock):
        """The authorization chain is complete at every depth."""
        headers, profile_id = account
        first = create_routine(client, headers, profile_id)["routine"]
        second = create_routine(
            client, headers, profile_id, title="Evening", client_routine_id="r2"
        )["routine"]
        run_id = first["today_run"]["id"]
        foreign_step = second["steps"][0]["id"]
        response = client.post(
            f"{runs_url(profile_id)}/{run_id}/steps/{foreign_step}/complete",
            headers=headers,
        )
        assert response.status_code == 404

    def test_optional_steps_do_not_block_a_complete_run(self, db, client, account, clock):
        """Section 14. A routine ending in "if you feel up to it" must not be
        permanently unfinished."""
        from app.services.productivity import routines as routine_service

        headers, profile_id = account
        routine = create_routine(client, headers, profile_id)["routine"]
        run_id = routine["today_run"]["id"]
        for step in routine["steps"][:2]:
            client.post(
                f"{runs_url(profile_id)}/{run_id}/steps/{step['id']}/complete",
                headers=headers,
            )
        run = routine_service.get_run(db, uuid.UUID(profile_id), uuid.UUID(run_id))
        progress = routine_service.progress(run)
        assert progress.all_required_done is True
        assert progress.next_step is not None  # the optional one is still offered


class TestTodayIntegration:
    def test_an_open_run_reaches_today(self, client, account, clock):
        headers, profile_id = account
        create_routine(client, headers, profile_id)
        today = client.get(
            f"/api/v1/today?local_date={TODAY.isoformat()}", headers=headers
        ).json()
        rows = [item for item in today["important"] if item["type"] == "routine_run"]
        assert len(rows) == 1
        assert rows[0]["title"] == "Morning routine"
        assert rows[0]["subtitle"] == "0 of 3 complete. Next: Drink water"
        assert today["daily_life"]["routines"]["due_today"] == 1

    def test_a_completed_run_leaves_today(self, client, account, clock):
        headers, profile_id = account
        routine = create_routine(client, headers, profile_id)["routine"]
        client.post(
            f"{runs_url(profile_id)}/{routine['today_run']['id']}/complete",
            headers=headers,
        )
        today = client.get(
            f"/api/v1/today?local_date={TODAY.isoformat()}", headers=headers
        ).json()
        assert [
            item for item in today["important"] if item["type"] == "routine_run"
        ] == []
        assert today["daily_life"]["routines"]["completed_today"] == 1


class TestClinicalBoundary:
    def test_nothing_creates_a_routine_from_health_data(self):
        """**Sections 15 and 24, as the absence of a code path.**

        A person may create a health-related routine, or enter one a clinician
        gave them, and Nura may remind them of it. Nura never decides from a
        symptom, a diagnosis or a model's inference that somebody should have
        one -- so no module that owns health data imports the routine service,
        and the routine service imports nothing that owns health data beyond
        PRD 5's time-zone resolver.
        """
        import pathlib

        health_owners = (
            "app/services/symptoms",
            "app/services/health.py",
            "app/services/appointments",
        )
        for name in health_owners:
            path = pathlib.Path(name)
            files = [path] if path.is_file() else list(path.rglob("*.py"))
            for file in files:
                text = file.read_text(encoding="utf-8")
                assert "productivity" not in text, file

    def test_the_routine_service_reads_no_health_record(self):
        """The other direction: a routine is built from what somebody typed."""
        import pathlib

        source = pathlib.Path("app/services/productivity/routines.py").read_text(
            encoding="utf-8"
        )
        for forbidden in ("SymptomEpisode", "MedicalCondition", "HealthRecord"):
            assert forbidden not in source
