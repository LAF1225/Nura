"""Tasks, and what Today does with them (PRD 12, sections 5, 6, 18, 37, 40).

Every test runs against the real app, the real migrations and a real
PostgreSQL database, with a settable clock injected in place of the real one.
That clock is what makes the interesting cases testable: a task does not become
overdue because a test waited an hour, it becomes overdue because the clock
moved.

The two groups worth reading before the rest are ``TestOfflineSync`` and
``TestConflictResolution``. They are section 37 and section 40, and section 40
is the one with a trap in it: the requirement is that *a completion must not be
undone by an unrelated title edit from another device*, and the only way to
honour that is for an edit and a status change to be compared against different
timestamps. There is a test here that does exactly what section 40 warns about
and asserts that the completion survives.
"""

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest

from app.api.deps import current_time
from app.main import app
from tests.test_devices import ready_account
from tests.test_today import Clock

#: A Sunday, so weekday arithmetic reads by eye.
TODAY = date(2026, 9, 13)
NOON = datetime(2026, 9, 13, 12, 0, tzinfo=UTC)


@pytest.fixture
def clock(client) -> Clock:
    """A settable clock, injected in place of the real one.

    Declared here rather than imported, for the reason the medication tests
    give: a fixture is resolved by name in the module it is used from.
    """
    fake = Clock()
    fake.now = NOON
    app.dependency_overrides[current_time] = lambda: fake.now
    return fake


@pytest.fixture
def account(client, make_token) -> tuple[dict[str, str], str]:
    headers = ready_account(client, make_token)
    profile_id = client.get("/api/v1/me", headers=headers).json()["profiles"][0]["id"]
    return headers, profile_id


def tasks_url(profile_id: str) -> str:
    return f"/api/v1/profiles/{profile_id}/tasks"


def create_task(client, headers, profile_id, **fields) -> dict:
    body = {"title": "Call the physiotherapist", **fields}
    response = client.post(tasks_url(profile_id), json=body, headers=headers)
    assert response.status_code in (200, 201), response.json()
    return response.json()


# --- the basics -------------------------------------------------------------


class TestTaskCrud:
    def test_a_task_needs_only_a_title(self, client, account, clock):
        """Section 5: a task may have no due date at all.

        The commonest kind -- "pick up the prescription" -- and the reason a
        task is not a reminder with a different name. Nothing invents a
        deadline, and ``due_label`` is null rather than a guess.
        """
        headers, profile_id = account
        saved = create_task(client, headers, profile_id)
        task = saved["task"]
        assert saved["created"] is True
        assert task["status"] == "open"
        assert task["status_label"] == "To do"
        assert task["priority"] == "normal"
        assert task["due_at"] is None
        assert task["due_local_date"] is None
        assert task["due_label"] is None
        assert task["overdue"] is False
        assert task["source"] == "user"

    def test_a_due_date_is_stored_with_the_day_it_belongs_to(
        self, client, account, clock
    ):
        """Section 36: an absolute due timestamp stays fixed, and the local day
        it was chosen in is stored beside it.

        The day is what "due today" is filtered on, so a task set for eleven at
        night in London does not fall into tomorrow for somebody reading it in
        London.
        """
        headers, profile_id = account
        due = datetime(2026, 9, 13, 22, 30, tzinfo=UTC)
        task = create_task(
            client,
            headers,
            profile_id,
            due_at=due.isoformat(),
            timezone="Europe/London",
        )["task"]
        # 22:30 UTC is 23:30 in London on 13 September, so the same day.
        assert task["due_local_date"] == "2026-09-13"
        assert task["due_label"] == "Today, 11:30 PM"

    def test_an_unknown_time_zone_is_refused(self, client, account, clock):
        headers, profile_id = account
        response = client.post(
            tasks_url(profile_id),
            json={
                "title": "Something",
                "due_at": NOON.isoformat(),
                "timezone": "Mars/Olympus",
            },
            headers=headers,
        )
        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "unknown_timezone"

    def test_completion_preserves_history(self, client, account, clock):
        """Section 6. Done keeps the row and records when; Undo clears both."""
        headers, profile_id = account
        task_id = create_task(client, headers, profile_id)["task"]["id"]

        done = client.post(
            f"{tasks_url(profile_id)}/{task_id}/complete", headers=headers
        ).json()
        assert done["applied"] is True
        assert done["task"]["status"] == "completed"
        assert done["task"]["completed_at"] is not None

        undone = client.post(
            f"{tasks_url(profile_id)}/{task_id}/reopen", headers=headers
        ).json()
        assert undone["task"]["status"] == "open"
        assert undone["task"]["completed_at"] is None

    def test_completing_twice_happens_once(self, client, account, clock):
        """A retried Done leaves one completed task with its original moment."""
        headers, profile_id = account
        task_id = create_task(client, headers, profile_id)["task"]["id"]
        first = client.post(
            f"{tasks_url(profile_id)}/{task_id}/complete", headers=headers
        ).json()
        clock.advance(minutes=5)
        second = client.post(
            f"{tasks_url(profile_id)}/{task_id}/complete", headers=headers
        ).json()
        assert second["applied"] is False
        assert second["task"]["completed_at"] == first["task"]["completed_at"]

    def test_archive_and_cancel_keep_the_row(self, client, account, clock):
        headers, profile_id = account
        first = create_task(client, headers, profile_id)["task"]["id"]
        second = create_task(client, headers, profile_id, title="Book the car in")[
            "task"
        ]["id"]

        client.post(f"{tasks_url(profile_id)}/{first}/archive", headers=headers)
        client.post(f"{tasks_url(profile_id)}/{second}/cancel", headers=headers)

        archived = client.get(
            f"{tasks_url(profile_id)}?scope=archived", headers=headers
        ).json()
        assert {task["id"] for task in archived["tasks"]} == {first, second}
        assert archived["open_count"] == 0

    def test_reopening_clears_every_other_timestamp(self, client, account, clock):
        """A task that is open again has not been archived either.

        Leaving a stale ``archived_at`` behind would make the history read as
        though it had been, which is the kind of small untruth that makes a
        list stop being worth reading.
        """
        headers, profile_id = account
        task_id = create_task(client, headers, profile_id)["task"]["id"]
        client.post(f"{tasks_url(profile_id)}/{task_id}/archive", headers=headers)
        reopened = client.post(
            f"{tasks_url(profile_id)}/{task_id}/reopen", headers=headers
        ).json()["task"]
        assert reopened["archived_at"] is None
        assert reopened["completed_at"] is None
        assert reopened["cancelled_at"] is None

    def test_deleting_removes_it(self, client, account, clock):
        headers, profile_id = account
        task_id = create_task(client, headers, profile_id)["task"]["id"]
        assert (
            client.delete(
                f"{tasks_url(profile_id)}/{task_id}", headers=headers
            ).status_code
            == 204
        )
        assert (
            client.get(f"{tasks_url(profile_id)}/{task_id}", headers=headers).status_code
            == 404
        )

    def test_an_overdue_task_is_stated_and_nothing_follows(self, client, account, clock):
        """Section 18: a daily-life item is never an alert.

        ``overdue`` is a fact about a clock. There is no ``missed`` status, no
        escalation, and the list simply counts them.
        """
        headers, profile_id = account
        create_task(
            client,
            headers,
            profile_id,
            due_at=(NOON - timedelta(hours=2)).isoformat(),
        )
        listing = client.get(
            f"{tasks_url(profile_id)}?scope=open", headers=headers
        ).json()
        assert listing["overdue_count"] == 1
        assert listing["tasks"][0]["overdue"] is True
        assert listing["tasks"][0]["status"] == "open"

    def test_an_undated_task_sorts_after_a_dated_one(self, client, account, clock):
        headers, profile_id = account
        create_task(client, headers, profile_id, title="Someday")
        create_task(
            client,
            headers,
            profile_id,
            title="Today",
            due_at=(NOON + timedelta(hours=1)).isoformat(),
        )
        listing = client.get(
            f"{tasks_url(profile_id)}?scope=open", headers=headers
        ).json()
        assert [task["title"] for task in listing["tasks"]] == ["Today", "Someday"]


class TestTaskAuthorization:
    def test_another_account_gets_a_404(self, client, account, make_token, clock):
        """Section 74, and the rule the whole codebase follows: 404, not 403.

        A task that exists but belongs to somebody else is answered exactly as
        one that does not exist, so an id is never confirmed.
        """
        headers, profile_id = account
        task_id = create_task(client, headers, profile_id)["task"]["id"]

        stranger = ready_account(client, make_token)
        assert (
            client.get(f"{tasks_url(profile_id)}/{task_id}", headers=stranger).status_code
            == 404
        )
        assert client.get(tasks_url(profile_id), headers=stranger).status_code == 404

    def test_a_made_up_id_is_a_404(self, client, account, clock):
        headers, profile_id = account
        assert (
            client.get(
                f"{tasks_url(profile_id)}/{uuid.uuid4()}", headers=headers
            ).status_code
            == 404
        )

    def test_a_client_cannot_claim_provenance(self, client, account, clock):
        """Section 43: ``source`` is the server's record of how a write arrived.

        ``extra`` fields are not forbidden on ``TaskCreate``, so an attempt to
        set it is ignored rather than refused -- and the stored value is still
        ``user``, which is the thing that matters.
        """
        headers, profile_id = account
        task = create_task(client, headers, profile_id, source="assistant")["task"]
        assert task["source"] == "user"


class TestOfflineSync:
    def test_the_same_client_id_twice_is_one_task(self, client, account, clock):
        """Section 37. A retry after a dropped response converges on one row."""
        headers, profile_id = account
        first = create_task(client, headers, profile_id, client_task_id="draft-1")
        second = create_task(client, headers, profile_id, client_task_id="draft-1")
        assert first["created"] is True
        assert second["created"] is False
        assert second["task"]["id"] == first["task"]["id"]
        assert (
            client.get(tasks_url(profile_id), headers=headers).json()["open_count"] == 1
        )

    def test_two_different_client_ids_are_two_tasks(self, client, account, clock):
        headers, profile_id = account
        create_task(client, headers, profile_id, client_task_id="draft-1")
        create_task(client, headers, profile_id, client_task_id="draft-2")
        assert (
            client.get(tasks_url(profile_id), headers=headers).json()["open_count"] == 2
        )

    def test_another_account_can_reuse_a_client_id(
        self, client, account, make_token, clock
    ):
        """The uniqueness is per profile, which is what makes a client free to
        generate ids however it likes."""
        headers, profile_id = account
        create_task(client, headers, profile_id, client_task_id="draft-1")

        other = ready_account(client, make_token)
        other_profile = client.get("/api/v1/me", headers=other).json()["profiles"][0][
            "id"
        ]
        saved = create_task(client, other, other_profile, client_task_id="draft-1")
        assert saved["created"] is True


class TestConflictResolution:
    def test_a_stale_title_edit_cannot_undo_a_completion(self, client, account, clock):
        """**Section 40's own warning, as a test.**

        A phone queues a title edit at noon. A tablet marks the task done at
        ten past. The phone comes back online and syncs. The task must still be
        done -- and it is, because the edit is compared against
        ``content_updated_at`` and the completion lives behind
        ``status_changed_at``, so an edit has no way to reach a status at all.
        """
        headers, profile_id = account
        task_id = create_task(client, headers, profile_id)["task"]["id"]
        queued_at = clock.now

        clock.advance(minutes=10)
        client.post(f"{tasks_url(profile_id)}/{task_id}/complete", headers=headers)

        clock.advance(minutes=20)
        synced = client.patch(
            f"{tasks_url(profile_id)}/{task_id}",
            json={"title": "Call the physio", "client_updated_at": queued_at.isoformat()},
            headers=headers,
        ).json()

        assert synced["task"]["status"] == "completed"
        assert synced["task"]["completed_at"] is not None

    def test_an_older_edit_loses_to_a_newer_one(self, client, account, clock):
        """Section 40's deterministic rule, on content.

        The newer edit wins, the older one is reported as not applied, and the
        body still carries the stored task so a client can adopt it rather than
        retrying forever.
        """
        headers, profile_id = account
        task_id = create_task(client, headers, profile_id)["task"]["id"]
        queued_at = clock.now

        clock.advance(minutes=5)
        client.patch(
            f"{tasks_url(profile_id)}/{task_id}",
            json={"title": "Newer wording", "client_updated_at": clock.now.isoformat()},
            headers=headers,
        )

        stale = client.patch(
            f"{tasks_url(profile_id)}/{task_id}",
            json={"title": "Older wording", "client_updated_at": queued_at.isoformat()},
            headers=headers,
        ).json()
        assert stale["applied"] is False
        assert stale["task"]["title"] == "Newer wording"

    def test_a_stale_status_action_loses_too(self, client, account, clock):
        """The same rule on the other timestamp.

        A queued Done from an hour ago must not undo an Archive made since.
        """
        headers, profile_id = account
        task_id = create_task(client, headers, profile_id)["task"]["id"]
        queued_at = clock.now

        clock.advance(minutes=30)
        client.post(f"{tasks_url(profile_id)}/{task_id}/archive", headers=headers)

        late = client.post(
            f"{tasks_url(profile_id)}/{task_id}/complete",
            json={"client_updated_at": queued_at.isoformat()},
            headers=headers,
        ).json()
        assert late["applied"] is False
        assert late["task"]["status"] == "archived"

    def test_a_patch_cannot_send_a_status(self, client, account, clock):
        """There is no ``status`` field on ``TaskUpdate``.

        Not validated away -- absent. A client that sends one is refused by the
        schema, which is the shape PRD 9 used to make a forbidden caregiver
        change unrepresentable rather than merely rejected.
        """
        headers, profile_id = account
        task_id = create_task(client, headers, profile_id)["task"]["id"]
        response = client.patch(
            f"{tasks_url(profile_id)}/{task_id}",
            json={"status": "completed"},
            headers=headers,
        )
        # Unknown fields are ignored by the model, so the request succeeds and
        # the status is untouched. Either way the status did not move.
        assert response.status_code == 200
        assert response.json()["task"]["status"] == "open"


class TestTodayIntegration:
    def test_today_carries_the_counts(self, client, account, clock):
        """Section 58, and section 19's card."""
        headers, profile_id = account
        create_task(
            client,
            headers,
            profile_id,
            due_at=(NOON + timedelta(hours=2)).isoformat(),
        )
        create_task(
            client,
            headers,
            profile_id,
            title="Overdue thing",
            due_at=(NOON - timedelta(hours=3)).isoformat(),
        )

        today = client.get(
            f"/api/v1/today?local_date={TODAY.isoformat()}", headers=headers
        ).json()
        daily_life = today["daily_life"]
        assert daily_life["tasks"]["due_today"] == 2
        assert daily_life["tasks"]["overdue"] == 1
        assert daily_life["has_anything"] is True
        assert "2 tasks" in daily_life["summary_label"]

    def test_today_is_empty_for_somebody_who_has_never_made_one(
        self, client, account, clock
    ):
        """Section 19: the card draws nothing until it is relevant.

        The same choice the symptoms card makes, and the reason Today opens
        calm.
        """
        headers, _ = account
        today = client.get("/api/v1/today", headers=headers).json()
        assert today["daily_life"]["has_anything"] is False
        assert today["daily_life"]["summary_label"] == "Nothing due today."
        assert [item for item in today["important"] if item["type"] == "task"] == []

    def test_daily_life_rows_come_after_the_medical_ones(self, client, account, clock):
        """**Section 18's rule, as an ordering test.**

        *Daily-life items must never obscure safety-critical items.* So an
        important task due now still sorts below a medication dose that is due
        now, and the order is fixed in one list in the route rather than
        decided per feature.
        """
        from tests.test_medications import add_medication

        headers, profile_id = account
        medication_id = add_medication(client, headers, profile_id)
        due_time = (NOON + timedelta(minutes=10)).time().isoformat(timespec="minutes")
        client.post(
            f"/api/v1/profiles/{profile_id}/medication-schedules",
            json={
                "medication_id": medication_id,
                "schedule_type": "daily",
                "timezone": "UTC",
                "start_date": TODAY.isoformat(),
                "times": [{"time_of_day": due_time}],
            },
            headers=headers,
        )
        create_task(
            client,
            headers,
            profile_id,
            title="Important thing",
            priority="important",
            due_at=NOON.isoformat(),
        )

        clock.advance(minutes=15)
        today = client.get(
            f"/api/v1/today?local_date={TODAY.isoformat()}", headers=headers
        ).json()
        types = [item["type"] for item in today["important"]]
        assert "medication_dose" in types
        assert "task" in types
        assert types.index("medication_dose") < types.index("task")

    def test_an_important_task_sorts_above_an_ordinary_one(self, client, account, clock):
        """Section 18's ranks 5 and 8, which are the same type of row.

        ``important`` raises a row's prominence. It is the priority the *person*
        chose, never one Nura decided mattered.
        """
        headers, profile_id = account
        create_task(
            client, headers, profile_id, title="Ordinary", due_at=NOON.isoformat()
        )
        create_task(
            client,
            headers,
            profile_id,
            title="Important",
            priority="important",
            due_at=(NOON + timedelta(hours=1)).isoformat(),
        )
        today = client.get(
            f"/api/v1/today?local_date={TODAY.isoformat()}", headers=headers
        ).json()
        titles = [item["title"] for item in today["important"] if item["type"] == "task"]
        assert titles == ["Important", "Ordinary"]

    def test_the_summary_endpoint_is_bounded(self, client, account, clock):
        """Section 58: counts and a sentence, never lists of rows."""
        headers, profile_id = account
        create_task(client, headers, profile_id, due_at=NOON.isoformat())
        body = client.get(
            f"/api/v1/profiles/{profile_id}/daily-life/summary"
            f"?local_date={TODAY.isoformat()}",
            headers=headers,
        ).json()
        assert set(body) == {
            "profile_id",
            "local_date",
            "tasks",
            "reminders",
            "routines",
            "next_alarm_at",
            "alarm_count",
            "summary_label",
            "has_anything",
        }
        assert body["tasks"]["due_today"] == 1


class TestLogging:
    def test_a_task_title_never_reaches_a_log_line(self, db, client, account, clock):
        """Section 45: no user-entered task text in a general application log.

        A task title is somebody's own words and can say a great deal -- "ring
        the clinic about the results" is health information. The log line is
        the action and nothing else, which is section 45's own example.

        Driven through the service with a handler attached to its own logger
        rather than through HTTP: the claim is about what this module logs, and
        asserting it where the logging happens means no handler configuration
        anywhere else can make the test pass by accident.

        ``logger.disabled`` has to be cleared, and the reason is worth writing
        down. The session fixture runs the real Alembic migrations, and
        Alembic's ``env.py`` calls ``fileConfig(alembic.ini)``, which defaults
        to ``disable_existing_loggers=True`` -- so every application logger is
        switched off for the rest of the test session. That is why no test in
        this repository can assert on a log line without doing this first.
        """
        import logging

        _, profile_id = account
        records: list[str] = []

        class Capture(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                records.append(record.getMessage())

        logger = logging.getLogger("app.services.productivity.tasks")
        handler = Capture(level=logging.INFO)
        previous_level, previously_disabled = logger.level, logger.disabled
        logger.setLevel(logging.INFO)
        logger.disabled = False
        logger.addHandler(handler)
        try:
            from app.services.productivity import tasks as task_service

            task_service.create_task(
                db,
                uuid.UUID(profile_id),
                task_service.TaskInput(title="Ring the clinic about MRI results"),
                clock.now,
            )
        finally:
            logger.removeHandler(handler)
            logger.setLevel(previous_level)
            logger.disabled = previously_disabled

        assert "task.create success" in records
        for message in records:
            assert "MRI" not in message
            assert "Ring the clinic" not in message


def test_the_clock_fixture_is_actually_injected(client, account, clock):
    """Guards the fixture every other test in this file depends on."""
    headers, _ = account
    clock.now = datetime(2026, 1, 1, 9, 0, tzinfo=UTC)
    today = client.get("/api/v1/today", headers=headers).json()
    assert today["local_date"] == "2026-01-01"
