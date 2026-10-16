"""Daily-life cards on the robot (PRD 12, sections 30-33, 64 and 65).

Section 64 lists the simulator coverage this file owes:

    task card
    general reminder
    routine card
    private task preview
    alarm information card
    safety preempts routine
    emergency preempts alarm

and each one is a test below, driven through the real reconciler against real
tasks, real reminder occurrences, real alarms and real routine runs -- not
fixtures standing in for them.

**No physical render is claimed anywhere.** The robot is a database row and a
token; the "screen" is ``services.robot.simulator``, which is the firmware's
dispatch table written in Python. A simulated render is not evidence that
anything was ever drawn on a panel, and section 64 says so outright: *no
physical render claim*.

Two of these are worth reading for the design rather than the coverage.

``TestAdditive`` is section 31. Every daily-life workflow is exercised with the
robot switched off, headless, and absent entirely, and the task, the reminder
and the routine behave identically -- because nothing about them reaches the
robot. The robot reaches them.

``TestPreemption`` is section 64's last two lines, and they are PRD 11's
preemption rule applied to new types rather than a new mechanism: only the
safety band preempts, and it preempts what is on the screen.
"""

import uuid
from datetime import timedelta

import pytest

from app.api.deps import current_time
from app.main import app
from app.services.robot import preferences, presenter, queue
from app.services.robot import simulator as sim
from tests.test_devices import ready_account
from tests.test_robot_presentations import NOW, seed_device, with_display
from tests.test_safety import start_monitoring
from tests.test_today import Clock

#: 4 October 2026 at 19:30 UTC -- a Sunday evening, which is the clock every
#: robot test in this repository starts from.
TODAY = NOW.date()


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
def robot(db, client, clock, owner):
    """A claimed robot with a reported screen, linked to the owner's profile."""
    headers, profile_id = owner
    device, token = seed_device(db, client, headers, profile_id=profile_id)
    with_display(db, device, clock.now)
    return device, token


# --- helpers ----------------------------------------------------------------


def a_task_due_now(client, headers, profile_id, clock, **fields) -> dict:
    """A real task whose card window includes now."""
    body = {
        "title": "Call physiotherapist",
        "due_at": (clock.now + timedelta(minutes=10)).isoformat(),
        "timezone": "UTC",
        **fields,
    }
    response = client.post(
        f"/api/v1/profiles/{profile_id}/tasks", json=body, headers=headers
    )
    assert response.status_code == 201, response.json()
    return response.json()["task"]


def a_reminder_due_now(client, headers, profile_id, clock, **fields) -> dict:
    """A real reminder whose occurrence reads as ``due`` right now.

    Ten minutes ahead, for the reason the medication helper gives: nothing
    backfills, and a reminder reads as due from half an hour before its
    moment.
    """
    moment = clock.now + timedelta(minutes=10)
    body = {
        "title": "Ring the bank",
        "time_of_day": moment.strftime("%H:%M"),
        "start_date": moment.date().isoformat(),
        "timezone": "UTC",
        **fields,
    }
    response = client.post(
        f"/api/v1/profiles/{profile_id}/reminders", json=body, headers=headers
    )
    assert response.status_code == 201, response.json()
    return response.json()["reminder"]


def a_routine_run_today(client, headers, profile_id, clock, **fields) -> dict:
    body = {
        "title": "Morning routine",
        "time_of_day": "07:30",
        "start_date": TODAY.isoformat(),
        "schedule_type": "daily",
        "steps": [
            {"title": "Drink water"},
            {"title": "Stretch for 5 minutes"},
            {"title": "Review Today"},
        ],
        **fields,
    }
    response = client.post(
        f"/api/v1/profiles/{profile_id}/routines", json=body, headers=headers
    )
    assert response.status_code == 201, response.json()
    return response.json()["routine"]


def an_alarm_ringing_now(client, headers, profile_id, clock, **fields) -> dict:
    """An alarm whose moment is five minutes ago, so it is inside the window."""
    moment = clock.now - timedelta(minutes=5)
    body = {
        "label": "Take the bins out",
        "time_of_day": moment.strftime("%H:%M"),
        "recurrence": "one_time",
        "on_date": moment.date().isoformat(),
        "timezone": "UTC",
        **fields,
    }
    response = client.post(
        f"/api/v1/profiles/{profile_id}/alarms", json=body, headers=headers
    )
    assert response.status_code == 201, response.json()
    return response.json()["alarm"]


def screen_for(db, device, clock, preset: dict[str, str] | None = None):
    """What a person standing in front of the robot would see.

    Runs the real reconciler, hands the next envelope over through the real
    queue, and renders it with the simulator -- which is the firmware's
    dispatch table in Python, and not a panel.
    """
    robot = sim.SimulatedRobot(db=db, device=device)
    robot.connect(clock.now)
    if preset is not None:
        robot.use(dict(preset), clock.now)
    db.commit()
    presenter.refresh(db, device, clock.now)
    db.commit()
    return robot


def cards_of(db, device, presentation_type: str):
    return [
        row
        for row in queue.open_presentations(db, device.id)
        if row.presentation_type == presentation_type
    ]


def set_preference(db, device, clock, **changes):
    row, _ = preferences.resolved_for(db, device, clock.now)
    preferences.update(db, row, changes, clock.now)
    db.commit()


# --- section 64's seven cases -----------------------------------------------


class TestDailyLifeCards:
    def test_a_task_card(self, db, client, clock, owner, robot):
        """Section 33's first example, on the simulated screen."""
        headers, profile_id = owner
        device, _ = robot
        a_task_due_now(client, headers, profile_id, clock)

        presenter.refresh(db, device, clock.now)
        db.commit()
        rows = cards_of(db, device, "task_reminder")
        assert len(rows) == 1
        assert rows[0].payload["title"] == "Task"
        assert rows[0].payload["primary"] == "Call physiotherapist"
        assert rows[0].priority == 54
        # Section 33: no unusable on-robot action buttons until a device
        # reports input, and PRD 11's sentence instead.
        assert rows[0].payload["actions"] == []
        assert rows[0].payload["respond_in_app"] is True

    def test_a_task_with_no_due_date_never_gets_a_card(
        self, db, client, clock, owner, robot
    ):
        """A card appears at a moment, and "pick up the prescription at some
        point" has no moment. It is on the list in the app, where it belongs."""
        headers, profile_id = owner
        device, _ = robot
        client.post(
            f"/api/v1/profiles/{profile_id}/tasks",
            json={"title": "Someday"},
            headers=headers,
        )
        presenter.refresh(db, device, clock.now)
        db.commit()
        assert cards_of(db, device, "task_reminder") == []

    def test_a_general_reminder_card(self, db, client, clock, owner, robot):
        headers, profile_id = owner
        device, _ = robot
        a_reminder_due_now(client, headers, profile_id, clock)

        presenter.refresh(db, device, clock.now)
        db.commit()
        rows = cards_of(db, device, "general_reminder")
        assert len(rows) == 1
        assert rows[0].payload["title"] == "Reminder"
        assert rows[0].payload["primary"] == "Ring the bank"
        assert rows[0].priority == 58

    def test_a_routine_card(self, db, client, clock, owner, robot):
        """Section 33's second example, including its two lines."""
        headers, profile_id = owner
        device, _ = robot
        a_routine_run_today(client, headers, profile_id, clock)

        presenter.refresh(db, device, clock.now)
        db.commit()
        rows = cards_of(db, device, "routine")
        assert len(rows) == 1
        assert rows[0].layout == "STATUS"
        assert rows[0].payload["title"] == "Morning routine"
        assert rows[0].payload["lines"][0] == "0 of 3 complete"
        assert rows[0].payload["lines"][1] == "Next: Drink water"
        assert rows[0].payload["lines"][2] == "Use the Nura app to respond."

    def test_an_alarm_information_card(self, db, client, clock, owner, robot):
        """**Section 65.** The speaker reports ``not_connected``, so the card
        says the alarm will not sound on Nura rather than implying it will.

        The sentence is derived from the capability map, so it disappears on
        its own if a chime capability ever appears.
        """
        headers, profile_id = owner
        device, _ = robot
        an_alarm_ringing_now(client, headers, profile_id, clock)

        presenter.refresh(db, device, clock.now)
        db.commit()
        rows = cards_of(db, device, "alarm")
        assert len(rows) == 1
        assert rows[0].payload["primary"] == "Take the bins out"
        assert "Nura cannot sound this" in rows[0].payload["secondary"]
        assert "chime" not in rows[0].payload
        assert rows[0].priority == 45

    def test_a_private_task_preview(self, db, client, clock, owner, robot):
        """**Section 32.** A task title can be as private as a tablet name.

        "Ring the clinic about the results" on a shelf in a shared room is
        exactly what this exists for, and the redaction happens while the
        payload is built -- so the stored row is already the redacted one and
        the app's history endpoint cannot show more than the robot was sent.
        """
        headers, profile_id = owner
        device, _ = robot
        a_task_due_now(
            client, headers, profile_id, clock, title="Ring the clinic about results"
        )
        set_preference(db, device, clock, daily_life_privacy_level="private")

        presenter.refresh(db, device, clock.now)
        db.commit()
        rows = cards_of(db, device, "task_reminder")
        assert len(rows) == 1
        assert rows[0].payload["primary"] == "Something due"
        assert "clinic" not in str(rows[0].payload)
        assert rows[0].payload["sensitive"] is False

    def test_a_title_only_preview_keeps_the_title_and_drops_the_time(
        self, db, client, clock, owner, robot
    ):
        headers, profile_id = owner
        device, _ = robot
        a_task_due_now(client, headers, profile_id, clock)
        set_preference(db, device, clock, daily_life_privacy_level="name_only")

        presenter.refresh(db, device, clock.now)
        db.commit()
        rows = cards_of(db, device, "task_reminder")
        assert rows[0].payload["primary"] == "Call physiotherapist"
        assert "secondary" not in rows[0].payload

    def test_privacy_mode_suppresses_a_task_card_entirely(
        self, db, client, clock, owner, robot
    ):
        """Privacy Mode is stronger than the preference, not a redaction of it.

        PRD 11 section 33 asks a quiet mode to suppress non-critical activity,
        and a task is non-critical in the way a family message is: it can wait
        until somebody is not asking to be left alone. So the card is not
        queued at all, which is more private than a redacted one -- and the
        task is still in the app, and the phone's own notification is
        unaffected (PRD 12, section 31).
        """
        from app.models import AssistantPreferences

        headers, profile_id = owner
        device, _ = robot
        a_task_due_now(client, headers, profile_id, clock)
        set_preference(db, device, clock, daily_life_privacy_level="full")
        db.add(AssistantPreferences(profile_id=uuid.UUID(profile_id), mode="privacy"))
        db.commit()

        presenter.refresh(db, device, clock.now)
        db.commit()
        assert cards_of(db, device, "task_reminder") == []
        assert (
            client.get(f"/api/v1/profiles/{profile_id}/tasks", headers=headers).json()[
                "open_count"
            ]
            == 1
        )

    def test_privacy_mode_hides_an_alarms_label_rather_than_the_alarm(
        self, db, client, clock, owner, robot
    ):
        """**Where PRD 11's downwards-only override does apply.**

        An alarm is not suppressed by a quiet mode -- that is the whole reason
        it is a separate type -- so Privacy Mode has to do something else with
        it, and what it does is drop the label. The mode is something somebody
        is doing now and the preference is something they set once, so the mode
        wins; and there is no direction in which it can reveal more than the
        preference asked for.
        """
        from app.models import AssistantPreferences

        headers, profile_id = owner
        device, _ = robot
        an_alarm_ringing_now(client, headers, profile_id, clock)
        set_preference(db, device, clock, daily_life_privacy_level="full")
        db.add(AssistantPreferences(profile_id=uuid.UUID(profile_id), mode="privacy"))
        db.commit()

        presenter.refresh(db, device, clock.now)
        db.commit()
        rows = cards_of(db, device, "alarm")
        assert len(rows) == 1
        assert rows[0].payload["primary"] == "Alarm"
        assert "bins" not in str(rows[0].payload)

    def test_a_routine_card_at_name_only_drops_the_step(
        self, db, client, clock, owner, robot
    ):
        """A step title is the part that says what the routine is for."""
        headers, profile_id = owner
        device, _ = robot
        a_routine_run_today(client, headers, profile_id, clock)
        set_preference(db, device, clock, daily_life_privacy_level="name_only")

        presenter.refresh(db, device, clock.now)
        db.commit()
        rows = cards_of(db, device, "routine")
        lines = rows[0].payload["lines"]
        assert lines[0] == "0 of 3 complete"
        assert not any("Drink water" in line for line in lines)


class TestReconciliation:
    def test_a_completed_task_loses_its_card(self, db, client, clock, owner, robot):
        """Section 31 and PRD 11's reconciliation in one: nothing notified the
        robot, the task was simply asked again."""
        headers, profile_id = owner
        device, _ = robot
        task = a_task_due_now(client, headers, profile_id, clock)
        presenter.refresh(db, device, clock.now)
        db.commit()
        assert cards_of(db, device, "task_reminder")

        client.post(
            f"/api/v1/profiles/{profile_id}/tasks/{task['id']}/complete", headers=headers
        )
        presenter.refresh(db, device, clock.now)
        db.commit()
        assert cards_of(db, device, "task_reminder") == []

    def test_an_answered_reminder_loses_its_card(self, db, client, clock, owner, robot):
        headers, profile_id = owner
        device, _ = robot
        reminder = a_reminder_due_now(client, headers, profile_id, clock)
        occurrence_id = reminder["occurrences"][0]["id"]
        presenter.refresh(db, device, clock.now)
        db.commit()
        assert cards_of(db, device, "general_reminder")

        client.post(
            f"/api/v1/profiles/{profile_id}/reminder-occurrences/{occurrence_id}/complete",
            headers=headers,
        )
        presenter.refresh(db, device, clock.now)
        db.commit()
        assert cards_of(db, device, "general_reminder") == []

    def test_ticking_a_step_rebuilds_the_routine_card(
        self, db, client, clock, owner, robot
    ):
        """The card *is* the count, so a card saying "1 of 3" after the second
        step was ticked would be worse than no card."""
        headers, profile_id = owner
        device, _ = robot
        routine = a_routine_run_today(client, headers, profile_id, clock)
        run_id = routine["today_run"]["id"]
        step_id = routine["steps"][0]["id"]
        presenter.refresh(db, device, clock.now)
        db.commit()

        client.post(
            f"/api/v1/profiles/{profile_id}/routine-runs/{run_id}"
            f"/steps/{step_id}/complete",
            headers=headers,
        )
        presenter.refresh(db, device, clock.now)
        db.commit()
        rows = cards_of(db, device, "routine")
        assert len(rows) == 1
        assert rows[0].payload["lines"][0] == "1 of 3 complete"
        assert rows[0].payload["lines"][1] == "Next: Stretch for 5 minutes"

    def test_a_completed_run_loses_its_card(self, db, client, clock, owner, robot):
        headers, profile_id = owner
        device, _ = robot
        routine = a_routine_run_today(client, headers, profile_id, clock)
        presenter.refresh(db, device, clock.now)
        db.commit()
        client.post(
            f"/api/v1/profiles/{profile_id}/routine-runs"
            f"/{routine['today_run']['id']}/complete",
            headers=headers,
        )
        presenter.refresh(db, device, clock.now)
        db.commit()
        assert cards_of(db, device, "routine") == []

    def test_an_alarm_card_goes_when_its_minute_has_gone(
        self, db, client, clock, owner, robot
    ):
        """Ten minutes. After that it is not an alarm any more, and a card
        still saying the time at half past would be worse than no card."""
        headers, profile_id = owner
        device, _ = robot
        an_alarm_ringing_now(client, headers, profile_id, clock)
        presenter.refresh(db, device, clock.now)
        db.commit()
        assert cards_of(db, device, "alarm")

        clock.advance(minutes=20)
        presenter.refresh(db, device, clock.now)
        db.commit()
        assert cards_of(db, device, "alarm") == []

    def test_a_privacy_change_rebuilds_a_card_already_on_the_shelf(
        self, db, client, clock, owner, robot
    ):
        """PRD 11's manual walk-through paid for this one.

        Switching to a private preview has to change the card that is already
        there, or somebody who has just asked for less keeps looking at the
        same words.
        """
        headers, profile_id = owner
        device, _ = robot
        a_task_due_now(client, headers, profile_id, clock, title="Ring the clinic")
        presenter.refresh(db, device, clock.now)
        db.commit()
        assert cards_of(db, device, "task_reminder")[0].payload["primary"] == (
            "Ring the clinic"
        )

        set_preference(db, device, clock, daily_life_privacy_level="private")
        presenter.refresh(db, device, clock.now)
        db.commit()
        rows = cards_of(db, device, "task_reminder")
        assert len(rows) == 1
        assert rows[0].payload["primary"] == "Something due"

    def test_a_level_configured_away_from_can_be_configured_back_to(
        self, db, client, clock, owner, robot
    ):
        """The second half of the same lesson: full to private to full must
        leave a card, not nothing."""
        headers, profile_id = owner
        device, _ = robot
        a_task_due_now(client, headers, profile_id, clock)
        for level in ("full", "private", "full"):
            set_preference(db, device, clock, daily_life_privacy_level=level)
            presenter.refresh(db, device, clock.now)
            db.commit()
        rows = cards_of(db, device, "task_reminder")
        assert len(rows) == 1
        assert rows[0].payload["primary"] == "Call physiotherapist"


class TestPreemption:
    def test_safety_preempts_a_routine(self, db, client, clock, owner, robot):
        """**Section 64's sixth case**, and PRD 11's rule rather than a new one:
        only the safety band preempts, and it preempts what is on the screen.
        """
        headers, profile_id = owner
        device, _ = robot
        a_routine_run_today(client, headers, profile_id, clock)
        presenter.refresh(db, device, clock.now)
        db.commit()

        # Put the routine card on the screen.
        row = queue.next_for_device(db, device, clock.now)
        db.commit()
        while row is not None and row.presentation_type != "routine":
            queue.acknowledge(db, row, "render_completed", clock.now)
            db.commit()
            row = queue.next_for_device(db, device, clock.now)
            db.commit()
        assert row is not None and row.presentation_type == "routine"
        queue.acknowledge(db, row, "render_started", clock.now)
        db.commit()
        assert row.status == "displayed"

        start_monitoring(client, headers, profile_id)
        presenter.refresh(db, device, clock.now)
        db.commit()
        db.refresh(row)
        assert row.status == "cancelled"
        assert row.cancel_reason == "preempted"

    def test_an_emergency_preempts_an_alarm(self, db, client, clock, owner, robot):
        """**Section 64's seventh case.** An alarm outranks an appointment and
        is still nowhere near the safety band."""

        headers, profile_id = owner
        device, _ = robot
        an_alarm_ringing_now(client, headers, profile_id, clock)
        presenter.refresh(db, device, clock.now)
        db.commit()

        row = queue.next_for_device(db, device, clock.now)
        db.commit()
        while row is not None and row.presentation_type != "alarm":
            queue.acknowledge(db, row, "render_completed", clock.now)
            db.commit()
            row = queue.next_for_device(db, device, clock.now)
            db.commit()
        assert row is not None and row.presentation_type == "alarm"
        queue.acknowledge(db, row, "render_started", clock.now)
        db.commit()

        client.post(
            f"/api/v1/profiles/{profile_id}/safety/sos",
            json={"trigger_source": "mobile_manual"},
            headers=headers,
        )
        presenter.refresh(db, device, clock.now)
        db.commit()
        db.refresh(row)
        assert row.status == "cancelled"
        assert row.cancel_reason == "preempted"

    def test_an_alarm_does_not_preempt_a_routine(self, db, client, clock, owner, robot):
        """Only safety preempts. A card with a better rank waits its turn,
        which is PRD 11 section 17's "may" decided once."""
        headers, profile_id = owner
        device, _ = robot
        a_routine_run_today(client, headers, profile_id, clock)
        presenter.refresh(db, device, clock.now)
        db.commit()

        row = queue.next_for_device(db, device, clock.now)
        db.commit()
        while row is not None and row.presentation_type != "routine":
            queue.acknowledge(db, row, "render_completed", clock.now)
            db.commit()
            row = queue.next_for_device(db, device, clock.now)
            db.commit()
        queue.acknowledge(db, row, "render_started", clock.now)
        db.commit()

        an_alarm_ringing_now(client, headers, profile_id, clock)
        presenter.refresh(db, device, clock.now)
        db.commit()
        db.refresh(row)
        assert row.status == "displayed"

    def test_the_priority_order_is_section_18s(self):
        """The ranks, read off the table rather than inferred from behaviour."""
        from app.models.enums import ROBOT_PRESENTATION_PRIORITIES

        ranks = dict(ROBOT_PRESENTATION_PRIORITIES)
        assert ranks["medication_reminder"] < ranks["alarm"]
        assert ranks["alarm"] < ranks["appointment_reminder"]
        assert ranks["appointment_reminder"] < ranks["task_reminder"]
        assert ranks["task_reminder"] < ranks["routine"]
        assert ranks["routine"] < ranks["general_reminder"]
        assert ranks["general_reminder"] < ranks["family_message"]
        # And every one of them is well below the safety band.
        from app.models.enums import ROBOT_SAFETY_PRIORITY_CEILING

        for name in ("alarm", "task_reminder", "routine", "general_reminder"):
            assert ranks[name] > ROBOT_SAFETY_PRIORITY_CEILING


class TestQuietModes:
    def test_sleep_mode_silences_a_task_but_not_an_alarm(
        self, db, client, clock, owner, robot
    ):
        """**The reason ``alarm`` is a separate type.**

        Section 4 defines an alarm as a time-critical alert whose purpose is to
        get attention at a specific time. An alarm that Sleep mode silenced
        would be an alarm that does not work, since the hour it is for is
        exactly the hour the robot would be asleep. A task is not that, and
        the phone's own notification is unaffected either way.
        """
        from app.models import AssistantPreferences

        headers, profile_id = owner
        device, _ = robot
        a_task_due_now(client, headers, profile_id, clock)
        an_alarm_ringing_now(client, headers, profile_id, clock)
        db.add(AssistantPreferences(profile_id=uuid.UUID(profile_id), mode="sleep"))
        db.commit()

        presenter.refresh(db, device, clock.now)
        db.commit()
        assert cards_of(db, device, "task_reminder") == []
        assert len(cards_of(db, device, "alarm")) == 1


class TestAdditive:
    def test_turning_the_cards_off_withdraws_them_and_changes_nothing_else(
        self, db, client, clock, owner, robot
    ):
        """**Section 31 as a switch.** The task, the reminder and the routine
        are untouched; only the cards go."""
        headers, profile_id = owner
        device, _ = robot
        task = a_task_due_now(client, headers, profile_id, clock)
        a_routine_run_today(client, headers, profile_id, clock)
        presenter.refresh(db, device, clock.now)
        db.commit()
        assert cards_of(db, device, "task_reminder")

        set_preference(db, device, clock, daily_life_display_enabled=False)
        presenter.refresh(db, device, clock.now)
        db.commit()
        assert cards_of(db, device, "task_reminder") == []
        assert cards_of(db, device, "routine") == []

        stored = client.get(
            f"/api/v1/profiles/{profile_id}/tasks/{task['id']}", headers=headers
        ).json()
        assert stored["status"] == "open"
        assert (
            client.get(f"/api/v1/profiles/{profile_id}/routines", headers=headers).json()[
                "active_count"
            ]
            == 1
        )

    def test_a_headless_robot_records_not_supported_rather_than_failing(
        self, db, client, clock, owner
    ):
        """PRD 11 section 123, for a daily-life card. A robot with no screen
        has not failed to show a task."""
        headers, profile_id = owner
        device, _ = seed_device(db, client, headers, profile_id=profile_id)
        robot = sim.SimulatedRobot(db=db, device=device)
        robot.connect(clock.now)
        robot.use(dict(sim.HEADLESS), clock.now)
        db.commit()

        a_task_due_now(client, headers, profile_id, clock)
        presenter.refresh(db, device, clock.now)
        db.commit()

        history = queue.history(db, device.id, limit=30)
        unsupported = [
            row
            for row in history
            if row.presentation_type == "task_reminder" and row.status == "not_supported"
        ]
        assert unsupported
        assert unsupported[0].failure_code == "no_display"

    def test_every_daily_life_workflow_works_with_no_robot_at_all(
        self, db, client, clock, owner
    ):
        """**Section 80's hardware-independence checkpoint**, answered by
        exercising the lot against an account with no device row.

        Create, complete, snooze, tick a step, pause, resume: not one of them
        touches the robot, because nothing about a daily-life item does.
        """
        headers, profile_id = owner
        assert client.get("/api/v1/devices", headers=headers).json() == []

        task = a_task_due_now(client, headers, profile_id, clock)
        assert (
            client.post(
                f"/api/v1/profiles/{profile_id}/tasks/{task['id']}/complete",
                headers=headers,
            ).status_code
            == 200
        )

        reminder = a_reminder_due_now(client, headers, profile_id, clock)
        occurrence_id = reminder["occurrences"][0]["id"]
        assert (
            client.post(
                f"/api/v1/profiles/{profile_id}/reminder-occurrences"
                f"/{occurrence_id}/snooze",
                json={"minutes": 10},
                headers=headers,
            ).status_code
            == 200
        )

        routine = a_routine_run_today(client, headers, profile_id, clock)
        run_id = routine["today_run"]["id"]
        step_id = routine["steps"][0]["id"]
        assert (
            client.post(
                f"/api/v1/profiles/{profile_id}/routine-runs/{run_id}"
                f"/steps/{step_id}/complete",
                headers=headers,
            ).status_code
            == 200
        )
        assert (
            client.post(
                f"/api/v1/profiles/{profile_id}/routines/{routine['id']}/pause",
                headers=headers,
            ).status_code
            == 200
        )

        an_alarm_ringing_now(client, headers, profile_id, clock)
        assert (
            client.get(f"/api/v1/profiles/{profile_id}/alarms", headers=headers).json()[
                "enabled_count"
            ]
            == 1
        )

    def test_no_productivity_service_imports_the_robot(self):
        """Section 31, structurally. ``test_robot_builders`` walks every file
        under ``app/services`` and asserts the only exception is the
        assistant; this names the PRD 12 package explicitly so a later change
        to that test cannot quietly let one through.
        """
        import pathlib

        for path in pathlib.Path("app/services/productivity").rglob("*.py"):
            for line in path.read_text(encoding="utf-8").splitlines():
                statement = line.strip()
                if statement.startswith(("from ", "import ")):
                    assert "app.services.robot" not in statement, path


class TestSimulatorRendering:
    def test_the_simulator_draws_a_task_card(self, db, client, clock, owner, robot):
        """The firmware's dispatch table, in Python.

        **A simulated render is not a physical one.** Section 64 says it
        outright: no physical render claim. Nothing in this project has drawn a
        frame on a panel.
        """
        headers, profile_id = owner
        device, _ = robot
        a_task_due_now(client, headers, profile_id, clock)
        robot_sim = screen_for(db, device, clock)

        screens = robot_sim.drain(clock.now)
        db.commit()
        layouts_seen = {screen.layout for screen in screens}
        types_seen = {screen.presentation_type for screen in screens}
        assert "task_reminder" in types_seen
        assert "REMINDER" in layouts_seen
        task_screen = next(
            screen for screen in screens if screen.presentation_type == "task_reminder"
        )
        assert "Call physiotherapist" in task_screen.lines
        assert "Use the Nura app to respond." in task_screen.lines
        # Nothing was spoken: no capability report has ever included a speaker.
        assert task_screen.spoken == ()

    def test_the_simulator_draws_a_routine_card(self, db, client, clock, owner, robot):
        headers, profile_id = owner
        device, _ = robot
        a_routine_run_today(client, headers, profile_id, clock)
        robot_sim = screen_for(db, device, clock)

        screens = robot_sim.drain(clock.now)
        db.commit()
        routine_screen = next(
            screen for screen in screens if screen.presentation_type == "routine"
        )
        assert routine_screen.layout == "STATUS"
        assert "0 of 3 complete" in routine_screen.lines
        assert "Next: Drink water" in routine_screen.lines

    def test_nothing_is_displayed_without_an_acknowledgement(
        self, db, client, clock, owner, robot
    ):
        """PRD 11 section 14, which PRD 12 does not get to weaken.

        Every daily-life card in this file that reached ``displayed`` got there
        through a simulated device acknowledgement. There is no path by which
        the backend handing a card over marks it shown.
        """
        headers, profile_id = owner
        device, _ = robot
        a_task_due_now(client, headers, profile_id, clock)
        presenter.refresh(db, device, clock.now)
        db.commit()

        row = queue.next_for_device(db, device, clock.now)
        db.commit()
        assert row is not None
        assert row.status == "sent"
        assert row.displayed_at is None
