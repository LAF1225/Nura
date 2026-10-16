"""The tool layer (PRD 8, sections 13, 14, 52, 90, 91 and 100).

Section 100 asks for four things per tool -- schema validation, authorization,
correct output, and no unintended write -- and this file is organised around
them.

The authorization group is the one worth reading. Section 90 says the model
must never choose a profile id. That is tested twice over: once by asserting
that **no tool has an argument that names a person**, which is what actually
makes it impossible, and once by giving a tool another profile's appointment
id and watching it come back as not found.

Tools are called directly rather than through a model here. There is no
provider in this file at all: the point is what the functions do when handed
arguments, and putting a model in the middle would only make the failures
harder to read.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.api.deps import current_time
from app.main import app
from app.models import AccountProfileRole, Profile, User
from app.services.assistant import tools
from tests.test_assistant import assistant_url
from tests.test_devices import ready_account
from tests.test_today import Clock

#: A Monday at noon UTC.
NOW = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)

#: 2 October 2026, 15:30 in London.
SOON = "2026-10-02T14:30:00+00:00"


# --- helpers ----------------------------------------------------------------


@pytest.fixture
def clock(client) -> Clock:
    """A settable clock, injected in place of the real one."""
    fake = Clock()
    fake.now = NOW
    app.dependency_overrides[current_time] = lambda: fake.now
    return fake


@pytest.fixture
def account(client, make_token) -> tuple[dict[str, str], str]:
    headers = ready_account(client, make_token)
    profile_id = client.get("/api/v1/me", headers=headers).json()["profiles"][0]["id"]
    return headers, profile_id


def account_for(db, profile_id: str) -> User:
    """The account that owns a profile.

    PRD 10 gave ``ToolContext`` a required ``account``: the safety tools write
    rows that record who acted, and a context that could not say would have to
    guess. Tests resolve it the same way the API does -- through the join
    table, never from an id in a body.
    """
    row = (
        db.query(AccountProfileRole)
        .filter(AccountProfileRole.profile_id == uuid.UUID(profile_id))
        .first()
    )
    assert row is not None
    user = db.get(User, row.account_id)
    assert user is not None
    return user


def context_for(db, profile_id: str) -> tools.ToolContext:
    profile = db.get(Profile, uuid.UUID(profile_id))
    assert profile is not None
    return tools.ToolContext(
        db=db,
        profile=profile,
        now=NOW,
        local_date=NOW.date(),
        allowed=tools.OWNER_SCOPE,
        is_owner=True,
        account=account_for(db, profile_id),
    )


def run(db, whose: str, name: str, **arguments) -> tools.ToolOutcome:
    """Runs one tool directly. ``whose`` is deliberately not called
    ``profile_id`` -- a test needs to be able to pass ``profile_id`` as a
    tool *argument* to prove that doing so is refused."""
    return tools.run(context_for(db, whose), name, arguments)


def add_medication(client, headers, profile_id, **body) -> dict:
    payload = {"name": "Salbutamol", "dose": "100", "dose_unit": "mcg", **body}
    response = client.post(
        f"/api/v1/profiles/{profile_id}/medications", json=payload, headers=headers
    )
    assert response.status_code == 201, response.json()
    return response.json()


def add_appointment(client, headers, profile_id, **body) -> dict:
    payload = {
        "title": "Cardiology follow-up",
        "scheduled_at": SOON,
        "timezone": "Europe/London",
        **body,
    }
    response = client.post(
        f"/api/v1/profiles/{profile_id}/appointments", json=payload, headers=headers
    )
    assert response.status_code == 201, response.json()
    return response.json()["appointment"]


def add_symptom(client, headers, profile_id, **first_entry) -> dict:
    payload = {"name": "Headache", "first_entry": first_entry or None}
    response = client.post(
        f"/api/v1/profiles/{profile_id}/symptoms", json=payload, headers=headers
    )
    assert response.status_code == 201, response.json()
    return response.json()["episode"]


def read_appointment(client, headers, profile_id, appointment_id) -> dict:
    response = client.get(
        f"/api/v1/profiles/{profile_id}/appointments/{appointment_id}",
        headers=headers,
    )
    assert response.status_code == 200, response.json()
    return response.json()


# --- the read tools ---------------------------------------------------------


class TestReadTools:
    def test_every_suggested_tool_exists(self):
        """PRD 8 lists ten, PRD 10 adds nine, PRD 12 adds thirteen.

        Written out rather than counted, because the thing worth protecting is
        not how many there are but that no thirty-third tool appeared without
        somebody choosing it.

        PRD 12's thirteen are sections 21's own list. What is *not* in it is
        the point of section 42: there is no tool a caregiver could use to
        reach a task, an alarm or a general reminder, and no tool anywhere that
        reads the weather, the news or a calendar -- those three are
        ``not_configured`` and section 29 says the model must not improvise
        them.
        """
        assert set(tools.BY_NAME) == {
            # PRD 8
            "get_today_summary",
            "get_health_summary",
            "get_active_medications",
            "get_recent_medication_history",
            "get_active_symptoms",
            "get_recent_symptom_entries",
            "get_upcoming_appointments",
            "get_appointment_questions",
            "get_daily_checkin_summary",
            "add_appointment_question",
            # PRD 10
            "get_safety_status",
            "get_active_safety_event",
            "get_escalation_status",
            "start_safety_monitoring",
            "stop_safety_monitoring",
            "manual_sos",
            "respond_to_safety_check",
            "get_active_safety_alerts",
            "acknowledge_safety_alert",
            # PRD 12
            "get_tasks",
            "get_today_tasks",
            "get_reminders",
            "get_alarms",
            "get_routines",
            "get_today_routine_runs",
            "create_task",
            "complete_task",
            "create_reminder",
            "create_alarm",
            "update_task",
            "create_routine",
            "pause_routine",
        }

    def test_every_write_tool_is_one_somebody_asked_for(self):
        """PRD 8 sections 13 and 15, PRD 10 sections 56 and 57, PRD 12 s21-24.

        PRD 8 had exactly one write. PRD 10 added five and PRD 12 adds seven,
        and the list is written out here so adding another is a decision rather
        than an accident -- especially since one of them can start an
        escalation.

        **None of PRD 12's seven can change anything medical.** Section 23's
        risk is that a generic daily-life tool becomes a way round the medical
        safeguards; the way that is prevented is the absence below. There is no
        tool that edits a medication, a schedule, a dose or a health record,
        and a request to "remind me to double my dose" reaches ``create_task``,
        which writes a note and returns the sentence about clinicians.

        **No tool anywhere takes an event type.** That is PRD 10 section 57
        enforced by absence: a model cannot turn a speculative reading of
        something somebody typed into a ``possible_seizure_like_activity``,
        because there is nowhere in any argument model to put one.
        """
        writers = [tool.name for tool in tools.TOOLS if tool.writes]
        assert writers == [
            "start_safety_monitoring",
            "stop_safety_monitoring",
            "manual_sos",
            "respond_to_safety_check",
            "acknowledge_safety_alert",
            "add_appointment_question",
            # PRD 12, section 22. The first four execute; the last three
            # propose. ``TestDailyLifeTools`` checks which is which.
            "create_task",
            "complete_task",
            "create_reminder",
            "create_alarm",
            "update_task",
            "create_routine",
            "pause_routine",
        ]
        for tool in tools.TOOLS:
            fields = set(tool.args_model.model_fields)
            assert "event_type" not in fields, tool.name
            assert "trigger_source" not in fields, tool.name

    def test_only_acknowledging_an_alert_is_a_caregiver_write(self):
        """PRD 9 section 64 and PRD 10 sections 84, 97 and 125.

        A caregiver's changes go through a suggestion the person approves, and
        PRD 10 opens exactly one exception: recording that they are checking
        on somebody. It resolves nothing and reaches nobody, which is why it
        is allowed to be the exception -- and why the exception is a flag on
        one tool rather than a relaxed rule.
        """
        exceptions = [tool.name for tool in tools.TOOLS if tool.caregiver_writable]
        assert exceptions == ["acknowledge_safety_alert"]

    def test_active_medications_reports_the_schedule(self, client, account, db):
        headers, profile_id = account
        medication = add_medication(client, headers, profile_id)
        client.post(
            f"/api/v1/profiles/{profile_id}/medication-schedules",
            json={
                "medication_id": medication["id"],
                "schedule_type": "daily",
                "timezone": "Europe/London",
                "start_date": "2026-09-01",
                "times": [{"time_of_day": "08:00"}, {"time_of_day": "20:00"}],
            },
            headers=headers,
        )

        outcome = run(db, profile_id, "get_active_medications")
        assert "Salbutamol" in outcome.content
        assert "100 mcg" in outcome.content
        assert "Twice daily" in outcome.content
        assert "08:00" in outcome.content

    def test_an_empty_record_reads_as_empty(self, client, account, db):
        """Section 81: do not imply access to data that is not there."""
        headers, profile_id = account
        for name in (
            "get_active_medications",
            "get_active_symptoms",
            "get_upcoming_appointments",
        ):
            assert tools.NOTHING_RECORDED in run(db, profile_id, name).content

    def test_active_symptoms_reports_what_was_recorded(self, client, account, db):
        headers, profile_id = account
        add_symptom(client, headers, profile_id, severity=6, change_state="worsening")

        outcome = run(db, profile_id, "get_active_symptoms")
        assert "Headache" in outcome.content
        assert "severity 6 of 10" in outcome.content
        assert "recorded as worsening" in outcome.content

    def test_upcoming_appointments_use_the_appointments_own_time_zone(
        self, client, account, db
    ):
        """The same 3:30 PM the appointment screens show (PRD 7, section 42)."""
        headers, profile_id = account
        add_appointment(client, headers, profile_id)

        outcome = run(db, profile_id, "get_upcoming_appointments")
        assert "Cardiology follow-up" in outcome.content
        assert "3:30 PM" in outcome.content

    def test_medication_history_is_counts_with_no_verdict(self, client, account, db):
        """Section 19 allows adherence counts; PRD 5 forbids grading them."""
        headers, profile_id = account
        outcome = run(db, profile_id, "get_recent_medication_history", days=7)
        assert "none were scheduled" in outcome.content
        for word in ("good", "poor", "excellent", "bad", "%"):
            assert word not in outcome.content.lower()

    def test_checkin_summary_counts_and_names_the_latest(
        self, client, account, db, clock
    ):
        """``clock`` is not optional here.

        The check-in route refuses a ``local_date`` more than a day from the
        server's own now, and this file's ``NOW`` is a fixed Monday. Without the
        injected clock the test passes for two days after it is written and then
        starts failing for a reason that has nothing to do with what it checks.
        """
        headers, profile_id = account
        client.put(
            "/api/v1/daily-checkins/today",
            json={
                "profile_id": profile_id,
                "local_date": NOW.date().isoformat(),
                "wellbeing_level": "okay",
            },
            headers=headers,
        )
        outcome = run(db, profile_id, "get_daily_checkin_summary")
        assert "1 completed" in outcome.content
        assert "okay" in outcome.content

    def test_today_summary_pulls_the_pieces_together(self, client, account, db):
        headers, profile_id = account
        add_appointment(client, headers, profile_id)
        add_symptom(client, headers, profile_id, severity=4)

        outcome = run(db, profile_id, "get_today_summary")
        assert "Cardiology follow-up" in outcome.content
        assert "1 active symptom" in outcome.content
        assert "check-in has not been done" in outcome.content

    def test_output_is_bounded(self, client, account, db):
        """Section 77: bounded tool output.

        Twenty appointments, ten rows back. A tool that can return everything
        is a tool that can empty a budget in one conversation.
        """
        headers, profile_id = account
        for index in range(20):
            add_appointment(
                client,
                headers,
                profile_id,
                title=f"Visit {index}",
                scheduled_at=(
                    datetime(2026, 10, 2, 14, 30, tzinfo=UTC) + timedelta(days=index)
                ).isoformat(),
            )
        outcome = run(db, profile_id, "get_upcoming_appointments")
        assert len(outcome.content.splitlines()) <= tools.MAX_ROWS + 1
        assert len(outcome.content) <= tools.MAX_TOOL_OUTPUT_CHARS


# --- validation -------------------------------------------------------------


class TestToolValidation:
    def test_an_unknown_tool_is_an_error_result_not_a_crash(self, account, db):
        """A model asking for a tool that does not exist can be told so."""
        _, profile_id = account
        outcome = run(db, profile_id, "delete_everything")
        assert outcome.is_error is True
        assert "no tool called" in outcome.content

    def test_arguments_that_do_not_fit_are_refused(self, account, db):
        """Section 91: validate all model-generated tool arguments."""
        _, profile_id = account
        outcome = run(db, profile_id, "get_recent_symptom_entries", days="lots")
        assert outcome.is_error is True
        assert "did not match its schema" in outcome.content

    def test_out_of_range_arguments_are_refused(self, account, db):
        _, profile_id = account
        outcome = run(db, profile_id, "get_recent_symptom_entries", days=5000)
        assert outcome.is_error is True

    def test_an_unexpected_argument_is_refused(self, account, db):
        """Extra fields are refused, not ignored -- ``extra="forbid"``.

        An argument nobody validated is the one somebody eventually reads.
        """
        _, profile_id = account
        outcome = run(db, profile_id, "get_today_summary", profile_id="anything")
        assert outcome.is_error is True

    def test_every_schema_forbids_extra_properties(self):
        # Every tool, not just the ones a given scope may use: the guarantee is
        # about the schemas themselves, so scoping the scan would weaken it.
        for tool in tools.TOOLS:
            assert tool.spec().parameters["additionalProperties"] is False


# --- authorization ----------------------------------------------------------


class TestToolAuthorization:
    def test_no_tool_has_an_argument_that_names_a_person(self):
        """Section 90, enforced by absence rather than by validation.

        The model cannot choose a profile because there is nowhere to put
        one. This is the assertion that keeps it that way.
        """
        for tool in tools.TOOLS:
            for name in tool.spec().parameters.get("properties", {}):
                assert "profile" not in name
                assert "account" not in name
                assert "user" not in name

    def test_a_tool_reads_only_the_profile_it_was_given(
        self, client, make_token, account, db
    ):
        headers, profile_id = account
        add_medication(client, headers, profile_id, name="Salbutamol")

        other_headers = ready_account(client, make_token)
        other_profile = client.get("/api/v1/me", headers=other_headers).json()[
            "profiles"
        ][0]["id"]
        add_medication(client, other_headers, other_profile, name="Atorvastatin")

        mine = run(db, profile_id, "get_active_medications").content
        theirs = run(db, other_profile, "get_active_medications").content
        assert "Salbutamol" in mine and "Atorvastatin" not in mine
        assert "Atorvastatin" in theirs and "Salbutamol" not in theirs

    def test_another_profiles_appointment_id_is_not_found(
        self, client, make_token, account, db
    ):
        """A real id, belonging to somebody else. Same answer as a made-up one."""
        headers, profile_id = account
        other_headers = ready_account(client, make_token)
        other_profile = client.get("/api/v1/me", headers=other_headers).json()[
            "profiles"
        ][0]["id"]
        theirs = add_appointment(client, other_headers, other_profile)

        outcome = run(
            db,
            profile_id,
            "get_appointment_questions",
            appointment_id=theirs["id"],
        )
        assert "no upcoming appointment" in outcome.content

    def test_a_nonsense_appointment_id_does_not_raise(self, account, db):
        _, profile_id = account
        outcome = run(
            db, profile_id, "get_appointment_questions", appointment_id="not-a-uuid"
        )
        assert "no upcoming appointment" in outcome.content


# --- the one write ----------------------------------------------------------


class TestWriteConfirmation:
    def test_read_tools_write_nothing(self, client, account, db):
        """Section 100: verify no unintended write."""
        headers, profile_id = account
        appointment = add_appointment(client, headers, profile_id)
        before = read_appointment(client, headers, profile_id, appointment["id"])

        for name in (
            "get_today_summary",
            "get_health_summary",
            "get_active_medications",
            "get_active_symptoms",
            "get_upcoming_appointments",
            "get_appointment_questions",
            "get_daily_checkin_summary",
        ):
            run(db, profile_id, name)

        after = read_appointment(client, headers, profile_id, appointment["id"])
        assert after["updated_at"] == before["updated_at"]
        assert after["questions"] == before["questions"]

    def test_adding_a_question_only_proposes_it(self, client, account, db):
        """Section 14: do not silently change health data."""
        headers, profile_id = account
        appointment = add_appointment(client, headers, profile_id)

        outcome = run(
            db, profile_id, "add_appointment_question", text="Ask about dizziness"
        )
        assert outcome.pending is not None
        assert outcome.pending.summary == (
            'Add "Ask about dizziness" to your questions for Cardiology follow-up?'
        )

        stored = read_appointment(client, headers, profile_id, appointment["id"])
        assert stored["questions"] == []

    def test_proposing_with_no_appointment_says_so(self, client, account, db):
        headers, profile_id = account
        outcome = run(
            db, profile_id, "add_appointment_question", text="Ask about dizziness"
        )
        assert outcome.is_error is True
        assert outcome.pending is None

    def test_a_confirmed_write_happens_through_the_api(
        self, client, account, clock, scripted
    ):
        """Sections 14 and 53, end to end.

        The model proposes; the reply comes back with a pending action; the
        user presses Confirm; only then does the question exist.
        """
        from app.services.assistant.provider import ScriptedReply, ToolCall
        from tests.test_assistant import say, start_conversation

        headers, profile_id = account
        appointment = add_appointment(client, headers, profile_id)
        scripted.queue(
            ScriptedReply(
                stop_reason="tool_use",
                tool_calls=(
                    ToolCall(
                        id="t1",
                        name="add_appointment_question",
                        arguments={"text": "Ask about dizziness"},
                    ),
                ),
            ),
            ScriptedReply(text="I've asked you to confirm that."),
        )
        conversation = start_conversation(client, headers, profile_id)
        result = say(
            client,
            headers,
            profile_id,
            conversation["id"],
            "Add ask about dizziness to my doctor questions.",
        )

        pending = result["reply"]["pending_action"]
        assert pending["state"] == "pending"
        assert pending["tool"] == "add_appointment_question"
        assert (
            read_appointment(client, headers, profile_id, appointment["id"])["questions"]
            == []
        )

        confirmed = client.post(
            f"{assistant_url(profile_id)}/conversations/{conversation['id']}"
            f"/messages/{result['reply']['id']}/confirm",
            json={"confirmed": True},
            headers=headers,
        )
        assert confirmed.status_code == 200
        body = confirmed.json()
        assert body["message"]["pending_action"]["state"] == "confirmed"
        assert "Added" in body["outcome"]["content"]
        assert body["outcome"]["message_type"] == "notice"

        questions = read_appointment(client, headers, profile_id, appointment["id"])[
            "questions"
        ]
        assert [question["text"] for question in questions] == ["Ask about dizziness"]

    def test_cancelling_changes_nothing(self, client, account, clock, scripted):
        from app.services.assistant.provider import ScriptedReply, ToolCall
        from tests.test_assistant import say, start_conversation

        headers, profile_id = account
        appointment = add_appointment(client, headers, profile_id)
        scripted.queue(
            ScriptedReply(
                stop_reason="tool_use",
                tool_calls=(
                    ToolCall(
                        id="t1",
                        name="add_appointment_question",
                        arguments={"text": "Ask about dizziness"},
                    ),
                ),
            ),
            ScriptedReply(text="Shall I add that?"),
        )
        conversation = start_conversation(client, headers, profile_id)
        result = say(client, headers, profile_id, conversation["id"], "Add a question")

        cancelled = client.post(
            f"{assistant_url(profile_id)}/conversations/{conversation['id']}"
            f"/messages/{result['reply']['id']}/confirm",
            json={"confirmed": False},
            headers=headers,
        )
        assert cancelled.status_code == 200
        assert cancelled.json()["message"]["pending_action"]["state"] == "cancelled"
        assert (
            read_appointment(client, headers, profile_id, appointment["id"])["questions"]
            == []
        )

    def test_confirming_twice_adds_one_question(self, client, account, clock, scripted):
        """The state moves off ``pending``, so the second press does nothing."""
        from app.services.assistant.provider import ScriptedReply, ToolCall
        from tests.test_assistant import say, start_conversation

        headers, profile_id = account
        appointment = add_appointment(client, headers, profile_id)
        scripted.queue(
            ScriptedReply(
                stop_reason="tool_use",
                tool_calls=(
                    ToolCall(
                        id="t1",
                        name="add_appointment_question",
                        arguments={"text": "Ask about dizziness"},
                    ),
                ),
            ),
            ScriptedReply(text="Shall I add that?"),
        )
        conversation = start_conversation(client, headers, profile_id)
        result = say(client, headers, profile_id, conversation["id"], "Add a question")
        url = (
            f"{assistant_url(profile_id)}/conversations/{conversation['id']}"
            f"/messages/{result['reply']['id']}/confirm"
        )

        client.post(url, json={"confirmed": True}, headers=headers)
        second = client.post(url, json={"confirmed": True}, headers=headers)
        assert second.json()["outcome"] is None

        questions = read_appointment(client, headers, profile_id, appointment["id"])[
            "questions"
        ]
        assert len(questions) == 1

    def test_another_account_cannot_confirm_someone_elses_action(
        self, client, make_token, account, clock, scripted
    ):
        from app.services.assistant.provider import ScriptedReply, ToolCall
        from tests.test_assistant import say, start_conversation

        headers, profile_id = account
        add_appointment(client, headers, profile_id)
        scripted.queue(
            ScriptedReply(
                stop_reason="tool_use",
                tool_calls=(
                    ToolCall(
                        id="t1",
                        name="add_appointment_question",
                        arguments={"text": "Ask about dizziness"},
                    ),
                ),
            ),
            ScriptedReply(text="Shall I add that?"),
        )
        conversation = start_conversation(client, headers, profile_id)
        result = say(client, headers, profile_id, conversation["id"], "Add a question")

        other = ready_account(client, make_token)
        response = client.post(
            f"{assistant_url(profile_id)}/conversations/{conversation['id']}"
            f"/messages/{result['reply']['id']}/confirm",
            json={"confirmed": True},
            headers=other,
        )
        assert response.status_code == 404
