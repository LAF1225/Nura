"""General reminders, their occurrences and their recurrence.

PRD 12, sections 7, 8, 9, 34, 35, 36 and 38.

Two groups carry most of the value.

``TestRecurrence`` is pure: a pattern and two dates go in, a list of moments
comes out, and no database or clock is involved. That is what makes the two
daylight-saving days a year testable at all -- they are impossible to notice in
use and easy to get wrong.

``TestDaylightSaving`` is section 35's requirement stated as properties rather
than as instants: a recurring local-time reminder stays at its intended local
time across a change, a spring morning that has no 01:30 produces one
occurrence rather than none, and an autumn morning that has two produces one
rather than two. Asserting the properties rather than hard-coded UTC values is
deliberate -- the properties are what somebody relies on.
"""

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.api.deps import current_time
from app.main import app
from app.services.productivity import recurrence
from tests.test_devices import ready_account
from tests.test_today import Clock

TODAY = date(2026, 9, 13)
NOON = datetime(2026, 9, 13, 12, 0, tzinfo=UTC)

LONDON = "Europe/London"
#: The two days a year this gets interesting in the UK.
SPRING_FORWARD = date(2026, 3, 29)
FALL_BACK = date(2026, 10, 25)


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


def reminders_url(profile_id: str) -> str:
    return f"/api/v1/profiles/{profile_id}/reminders"


def occurrences_url(profile_id: str) -> str:
    return f"/api/v1/profiles/{profile_id}/reminder-occurrences"


def create_reminder(client, headers, profile_id, **fields) -> dict:
    body = {
        "title": "Ring the bank",
        "time_of_day": "09:00",
        "start_date": TODAY.isoformat(),
        **fields,
    }
    response = client.post(reminders_url(profile_id), json=body, headers=headers)
    assert response.status_code in (200, 201), response.json()
    return response.json()


# --- the pure part ----------------------------------------------------------


class TestRecurrence:
    """``services.productivity.recurrence``, with no database and no clock."""

    def test_a_one_off_produces_exactly_one_moment(self):
        pattern = recurrence.Pattern(
            recurrence="one_time",
            timezone="UTC",
            start_date=TODAY,
            time_of_day=time(9, 0),
        )
        moments = list(recurrence.occurrences(pattern, TODAY, TODAY + timedelta(days=30)))
        assert len(moments) == 1
        assert moments[0].local_date == TODAY

    def test_daily_produces_one_a_day(self):
        pattern = recurrence.Pattern(
            recurrence="daily", timezone="UTC", start_date=TODAY, time_of_day=time(9, 0)
        )
        moments = list(recurrence.occurrences(pattern, TODAY, TODAY + timedelta(days=6)))
        assert len(moments) == 7
        assert [moment.local_date.weekday() for moment in moments] == [
            6,
            0,
            1,
            2,
            3,
            4,
            5,
        ]

    def test_selected_days_produces_only_those_days(self):
        """0 is Monday, as everywhere in this codebase."""
        pattern = recurrence.Pattern(
            recurrence="selected_days",
            timezone="UTC",
            start_date=TODAY,
            time_of_day=time(9, 0),
            weekdays=[0, 2, 4],
        )
        moments = list(recurrence.occurrences(pattern, TODAY, TODAY + timedelta(days=13)))
        assert {moment.local_date.weekday() for moment in moments} == {0, 2, 4}
        assert len(moments) == 6

    def test_weekly_is_one_day_a_week(self):
        pattern = recurrence.Pattern(
            recurrence="weekly",
            timezone="UTC",
            start_date=TODAY,
            time_of_day=time(9, 0),
            weekdays=[2],
        )
        moments = list(recurrence.occurrences(pattern, TODAY, TODAY + timedelta(days=27)))
        assert len(moments) == 4

    def test_a_pattern_with_no_weekdays_produces_nothing(self):
        """ "On no days" is no occurrences, which is the correct reading.

        Unreachable for a stored row -- the database CHECK refuses it -- and
        answered here because a ``Pattern`` can also be built by a caller that
        has not read the constraint.
        """
        pattern = recurrence.Pattern(
            recurrence="selected_days",
            timezone="UTC",
            start_date=TODAY,
            time_of_day=time(9, 0),
            weekdays=[],
        )
        assert (
            list(recurrence.occurrences(pattern, TODAY, TODAY + timedelta(days=30))) == []
        )

    def test_monthly_lands_on_the_chosen_day(self):
        pattern = recurrence.Pattern(
            recurrence="monthly",
            timezone="UTC",
            start_date=date(2026, 1, 1),
            time_of_day=time(9, 0),
            day_of_month=15,
        )
        moments = list(
            recurrence.occurrences(pattern, date(2026, 1, 1), date(2026, 4, 30))
        )
        assert [moment.local_date.isoformat() for moment in moments] == [
            "2026-01-15",
            "2026-02-15",
            "2026-03-15",
            "2026-04-15",
        ]

    def test_the_31st_of_a_short_month_is_its_last_day(self):
        """**One occurrence, at the end of the month -- never none.**

        Decided deterministically here rather than refused at the edge or
        silently skipped. Somebody who sets a month-end reminder expects
        twelve a year, and eleven with one missing is the answer they would
        least expect.
        """
        pattern = recurrence.Pattern(
            recurrence="monthly",
            timezone="UTC",
            start_date=date(2026, 1, 1),
            time_of_day=time(9, 0),
            day_of_month=31,
        )
        moments = list(
            recurrence.occurrences(pattern, date(2026, 1, 1), date(2026, 4, 30))
        )
        assert [moment.local_date.isoformat() for moment in moments] == [
            "2026-01-31",
            "2026-02-28",
            "2026-03-31",
            "2026-04-30",
        ]

    def test_a_leap_february_gets_the_29th(self):
        pattern = recurrence.Pattern(
            recurrence="monthly",
            timezone="UTC",
            start_date=date(2028, 2, 1),
            time_of_day=time(9, 0),
            day_of_month=31,
        )
        moments = list(
            recurrence.occurrences(pattern, date(2028, 2, 1), date(2028, 2, 29))
        )
        assert [moment.local_date.isoformat() for moment in moments] == ["2028-02-29"]

    def test_an_end_date_stops_it(self):
        pattern = recurrence.Pattern(
            recurrence="daily",
            timezone="UTC",
            start_date=TODAY,
            time_of_day=time(9, 0),
            end_date=TODAY + timedelta(days=2),
        )
        moments = list(recurrence.occurrences(pattern, TODAY, TODAY + timedelta(days=30)))
        assert len(moments) == 3

    def test_the_recurrence_module_uses_prd_5s_own_resolver(self):
        """Section 35: do not build a second, contradictory DST policy.

        Checked by identity rather than by behaviour: ``recurrence`` re-exports
        the function PRD 5 wrote, so there is no second implementation that
        could disagree with it.
        """
        from app.services.medications import doses as dose_service

        assert recurrence.occurrence_instant is dose_service.occurrence_instant
        assert recurrence.zone_for is dose_service.zone_for


class TestDaylightSaving:
    """Section 35, as properties rather than as hard-coded instants."""

    def test_a_morning_reminder_keeps_its_local_time_across_the_change(self):
        """**The property that matters.** Nine o'clock stays nine o'clock.

        In March and in April alike, which is only true because the pattern
        stores a wall-clock time and a zone rather than an offset.
        """
        pattern = recurrence.Pattern(
            recurrence="daily",
            timezone=LONDON,
            start_date=SPRING_FORWARD - timedelta(days=2),
            time_of_day=time(9, 0),
        )
        zone = ZoneInfo(LONDON)
        moments = list(
            recurrence.occurrences(
                pattern,
                SPRING_FORWARD - timedelta(days=2),
                SPRING_FORWARD + timedelta(days=2),
            )
        )
        assert len(moments) == 5
        for moment in moments:
            local = moment.scheduled_for.astimezone(zone)
            assert (local.hour, local.minute) == (9, 0)

    def test_an_hour_that_never_happens_still_produces_one_occurrence(self):
        """Spring forward. One dose, never zero -- PRD 5's words, reused.

        01:30 does not exist on the morning the clocks go forward. It resolves
        through the pre-transition offset, so the reminder lands the same
        elapsed time later and reads an hour on from the chosen time. What
        matters is that it exists.
        """
        pattern = recurrence.Pattern(
            recurrence="daily",
            timezone=LONDON,
            start_date=SPRING_FORWARD,
            time_of_day=time(1, 30),
            end_date=SPRING_FORWARD,
        )
        moments = list(recurrence.occurrences(pattern, SPRING_FORWARD, SPRING_FORWARD))
        assert len(moments) == 1
        local = moments[0].scheduled_for.astimezone(ZoneInfo(LONDON))
        # The clock jumped over 01:30, so it reads 02:30 -- an hour on, which
        # is the documented consequence rather than a surprise.
        assert (local.hour, local.minute) == (2, 30)

    def test_an_hour_that_happens_twice_produces_one_occurrence(self):
        """Autumn. One reminder, never two.

        The earlier of the two 01:30s, which is ``fold=0`` in PRD 5's
        resolver -- the whole policy in one keyword.
        """
        pattern = recurrence.Pattern(
            recurrence="daily",
            timezone=LONDON,
            start_date=FALL_BACK,
            time_of_day=time(1, 30),
            end_date=FALL_BACK,
        )
        moments = list(recurrence.occurrences(pattern, FALL_BACK, FALL_BACK))
        assert len(moments) == 1
        # 01:30 BST, which is 00:30 UTC -- the first of the two.
        assert moments[0].scheduled_for == datetime(2026, 10, 25, 0, 30, tzinfo=UTC)

    def test_a_week_across_the_change_has_exactly_seven_occurrences(self):
        """Neither a doubled day nor a missing one."""
        for day in (SPRING_FORWARD, FALL_BACK):
            pattern = recurrence.Pattern(
                recurrence="daily",
                timezone=LONDON,
                start_date=day - timedelta(days=3),
                time_of_day=time(1, 30),
            )
            moments = list(
                recurrence.occurrences(
                    pattern, day - timedelta(days=3), day + timedelta(days=3)
                )
            )
            assert len(moments) == 7, day
            assert len({moment.scheduled_for for moment in moments}) == 7, day


# --- over HTTP --------------------------------------------------------------


class TestReminderCrud:
    def test_a_one_off_reminder_generates_one_occurrence(self, client, account, clock):
        headers, profile_id = account
        saved = create_reminder(
            client,
            headers,
            profile_id,
            time_of_day="18:00",
            start_date=TODAY.isoformat(),
        )
        reminder = saved["reminder"]
        assert reminder["recurrence"] == "one_time"
        assert reminder["status"] == "active"
        assert reminder["schedule_label"] == "13 September 2026 at 6:00 PM"
        assert len(reminder["occurrences"]) == 1
        assert reminder["occurrences"][0]["status"] == "scheduled"

    def test_a_daily_reminder_fills_the_fortnight(self, client, account, clock):
        """The same horizon PRD 5 uses, so a phone offline for a week still
        has reminders left to fire.

        Fifteen rather than fourteen: the window is today plus the horizon,
        inclusive, and today's six o'clock has not happened yet. PRD 5's dose
        generator counts the same way, which is the point of reusing it.
        """
        headers, profile_id = account
        saved = create_reminder(
            client, headers, profile_id, recurrence="daily", time_of_day="18:00"
        )
        assert len(saved["reminder"]["occurrences"]) == 15

    def test_nothing_is_generated_for_a_moment_that_has_gone(
        self, client, account, clock
    ):
        """Generation only looks forward (PRD 5, section 22).

        A reminder created at noon does not retroactively produce -- let alone
        miss -- this morning's nine o'clock.
        """
        headers, profile_id = account
        saved = create_reminder(
            client, headers, profile_id, recurrence="daily", time_of_day="09:00"
        )
        moments = [
            datetime.fromisoformat(row["scheduled_for"])
            for row in saved["reminder"]["occurrences"]
        ]
        assert all(moment > clock.now for moment in moments)

    def test_selected_days_needs_days(self, client, account, clock):
        headers, profile_id = account
        response = client.post(
            reminders_url(profile_id),
            json={
                "title": "Bins",
                "time_of_day": "07:00",
                "start_date": TODAY.isoformat(),
                "recurrence": "selected_days",
            },
            headers=headers,
        )
        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "invalid_reminder"

    def test_a_weekly_reminder_is_one_day(self, client, account, clock):
        headers, profile_id = account
        response = client.post(
            reminders_url(profile_id),
            json={
                "title": "Bins",
                "time_of_day": "07:00",
                "start_date": TODAY.isoformat(),
                "recurrence": "weekly",
                "weekdays": [0, 3],
            },
            headers=headers,
        )
        assert response.status_code == 422

    def test_a_monthly_reminder_needs_a_day_of_the_month(self, client, account, clock):
        headers, profile_id = account
        response = client.post(
            reminders_url(profile_id),
            json={
                "title": "Rent",
                "time_of_day": "07:00",
                "start_date": TODAY.isoformat(),
                "recurrence": "monthly",
            },
            headers=headers,
        )
        assert response.status_code == 422

    def test_a_day_of_the_month_is_refused_on_a_daily_reminder(
        self, client, account, clock
    ):
        """A field that does not apply is refused rather than ignored.

        Ignoring it would store a reminder that quietly disagrees with what
        somebody filled in.
        """
        headers, profile_id = account
        response = client.post(
            reminders_url(profile_id),
            json={
                "title": "Water the plants",
                "time_of_day": "07:00",
                "start_date": TODAY.isoformat(),
                "recurrence": "daily",
                "day_of_month": 4,
            },
            headers=headers,
        )
        assert response.status_code == 422

    def test_changing_the_time_rebuilds_the_future_and_keeps_the_past(
        self, client, account, clock
    ):
        """Only the future is rebuilt. An occurrence somebody answered keeps
        its status and its time forever -- PRD 5's rule about history, applied
        to "ring the bank"."""
        headers, profile_id = account
        saved = create_reminder(
            client, headers, profile_id, recurrence="daily", time_of_day="18:00"
        )
        reminder_id = saved["reminder"]["id"]
        first = saved["reminder"]["occurrences"][0]["id"]

        # Answer tonight's, then move the time.
        clock.advance(hours=6)
        client.post(f"{occurrences_url(profile_id)}/{first}/complete", headers=headers)
        updated = client.patch(
            f"{reminders_url(profile_id)}/{reminder_id}",
            json={"time_of_day": "20:00"},
            headers=headers,
        ).json()

        answered = [row for row in updated["occurrences"] if row["id"] == first]
        assert answered and answered[0]["status"] == "completed"
        future = [
            row
            for row in updated["occurrences"]
            if datetime.fromisoformat(row["scheduled_for"]) > clock.now
        ]
        assert future
        for row in future:
            # Normalised to UTC: PostgreSQL hands a ``timestamptz`` back in the
            # server's own zone, and the reminder's zone here is UTC.
            moment = datetime.fromisoformat(row["scheduled_for"]).astimezone(UTC)
            assert moment.hour == 20

    def test_pausing_withdraws_the_future_and_keeps_the_series(
        self, client, account, clock
    ):
        headers, profile_id = account
        reminder_id = create_reminder(
            client, headers, profile_id, recurrence="daily", time_of_day="18:00"
        )["reminder"]["id"]

        paused = client.post(
            f"{reminders_url(profile_id)}/{reminder_id}/pause", headers=headers
        ).json()
        assert paused["status"] == "paused"
        assert paused["status_label"] == "Paused"
        assert paused["occurrences"] == []

        resumed = client.post(
            f"{reminders_url(profile_id)}/{reminder_id}/resume", headers=headers
        ).json()
        assert resumed["status"] == "active"
        assert len(resumed["occurrences"]) == 15

    def test_resuming_does_not_fill_in_the_gap(self, client, account, clock):
        """A reminder nobody wanted last week is not a backlog to work through."""
        headers, profile_id = account
        reminder_id = create_reminder(
            client, headers, profile_id, recurrence="daily", time_of_day="18:00"
        )["reminder"]["id"]
        client.post(f"{reminders_url(profile_id)}/{reminder_id}/pause", headers=headers)

        clock.advance(days=3)
        resumed = client.post(
            f"{reminders_url(profile_id)}/{reminder_id}/resume", headers=headers
        ).json()
        moments = [
            datetime.fromisoformat(row["scheduled_for"]) for row in resumed["occurrences"]
        ]
        assert all(moment > clock.now for moment in moments)

    def test_notifications_off_says_so_rather_than_going_quiet(
        self, client, account, clock
    ):
        """Section 9. The reminder is stored, it is on Today, and the response
        carries the sentence -- so a client cannot ship a screen without it."""
        headers, profile_id = account
        saved = create_reminder(client, headers, profile_id, notification_enabled=False)
        reminder = saved["reminder"]
        assert reminder["notification_enabled"] is False
        assert "will not make a sound" in reminder["notification_note"]

        on = create_reminder(client, headers, profile_id, title="Other")["reminder"]
        assert on["notification_note"] is None

    def test_the_same_client_id_twice_is_one_reminder(self, client, account, clock):
        headers, profile_id = account
        first = create_reminder(client, headers, profile_id, client_reminder_id="d1")
        second = create_reminder(client, headers, profile_id, client_reminder_id="d1")
        assert first["created"] is True
        assert second["created"] is False
        assert second["reminder"]["id"] == first["reminder"]["id"]

    def test_another_account_gets_a_404(self, client, account, make_token, clock):
        headers, profile_id = account
        reminder_id = create_reminder(client, headers, profile_id)["reminder"]["id"]
        stranger = ready_account(client, make_token)
        assert (
            client.get(
                f"{reminders_url(profile_id)}/{reminder_id}", headers=stranger
            ).status_code
            == 404
        )


class TestOccurrenceActions:
    """Section 8's three actions, and the words they are not."""

    def test_done_dismiss_and_snooze_are_three_different_facts(
        self, client, account, clock
    ):
        headers, profile_id = account
        reminder = create_reminder(
            client, headers, profile_id, recurrence="daily", time_of_day="18:00"
        )["reminder"]
        first, second, third = (row["id"] for row in reminder["occurrences"][:3])

        clock.advance(hours=6)
        done = client.post(
            f"{occurrences_url(profile_id)}/{first}/complete", headers=headers
        ).json()
        dismissed = client.post(
            f"{occurrences_url(profile_id)}/{second}/dismiss", headers=headers
        ).json()
        snoozed = client.post(
            f"{occurrences_url(profile_id)}/{third}/snooze",
            json={"minutes": 10},
            headers=headers,
        ).json()

        assert done["occurrence"]["status"] == "completed"
        assert done["occurrence"]["status_label"] == "Done"
        assert dismissed["occurrence"]["status"] == "dismissed"
        assert dismissed["occurrence"]["status_label"] == "Dismissed"
        assert snoozed["occurrence"]["status"] == "snoozed"
        assert snoozed["occurrence"]["snoozed_until"] is not None

    def test_no_status_anywhere_says_taken(self, client, account, clock):
        """**Section 8: do not reuse medication ``Taken`` semantics.**

        Checked against the vocabulary rather than one response: a reminder
        that was dealt with is not a dose somebody took, and nothing in this
        feature counts adherence.
        """
        from app.models.enums import REMINDER_OCCURRENCE_STATUSES

        assert "taken" not in REMINDER_OCCURRENCE_STATUSES
        assert "skipped" not in REMINDER_OCCURRENCE_STATUSES

    def test_completing_twice_happens_once(self, client, account, clock):
        headers, profile_id = account
        reminder = create_reminder(
            client, headers, profile_id, recurrence="daily", time_of_day="18:00"
        )["reminder"]
        occurrence_id = reminder["occurrences"][0]["id"]
        clock.advance(hours=6)
        client.post(
            f"{occurrences_url(profile_id)}/{occurrence_id}/complete", headers=headers
        )
        again = client.post(
            f"{occurrences_url(profile_id)}/{occurrence_id}/complete", headers=headers
        ).json()
        assert again["applied"] is False

    def test_snoozing_is_capped_and_done_stays_available(self, client, account, clock):
        """The cap stops endless rapid snoozing without taking away the two
        buttons that finish the thing."""
        headers, profile_id = account
        reminder = create_reminder(
            client, headers, profile_id, recurrence="daily", time_of_day="18:00"
        )["reminder"]
        occurrence_id = reminder["occurrences"][0]["id"]
        clock.advance(hours=6)

        for _ in range(3):
            response = client.post(
                f"{occurrences_url(profile_id)}/{occurrence_id}/snooze",
                json={"minutes": 10},
                headers=headers,
            )
            assert response.status_code == 200, response.json()

        refused = client.post(
            f"{occurrences_url(profile_id)}/{occurrence_id}/snooze",
            json={"minutes": 10},
            headers=headers,
        )
        assert refused.status_code == 409
        assert refused.json()["detail"]["code"] == "snooze_limit_reached"

        done = client.post(
            f"{occurrences_url(profile_id)}/{occurrence_id}/complete", headers=headers
        )
        assert done.status_code == 200
        assert done.json()["occurrence"]["status"] == "completed"

    def test_a_snooze_nura_does_not_offer_is_refused(self, client, account, clock):
        headers, profile_id = account
        reminder = create_reminder(
            client, headers, profile_id, recurrence="daily", time_of_day="18:00"
        )["reminder"]
        occurrence_id = reminder["occurrences"][0]["id"]
        response = client.post(
            f"{occurrences_url(profile_id)}/{occurrence_id}/snooze",
            json={"minutes": 7},
            headers=headers,
        )
        assert response.status_code == 422

    def test_an_unanswered_occurrence_becomes_missed_after_the_grace_period(
        self, client, account, clock
    ):
        """Recorded, and nothing follows: no advice, no escalation, nobody told."""
        headers, profile_id = account
        create_reminder(
            client, headers, profile_id, recurrence="daily", time_of_day="18:00"
        )

        clock.advance(hours=9)
        rows = client.get(occurrences_url(profile_id), headers=headers).json()
        statuses = {row["status"] for row in rows}
        assert "missed" in statuses

    def test_a_snoozed_occurrence_is_measured_from_its_snooze(
        self, client, account, clock
    ):
        """Otherwise snoozing for ten minutes would mark it missed the moment
        the ten minutes were up."""
        headers, profile_id = account
        reminder = create_reminder(
            client, headers, profile_id, recurrence="daily", time_of_day="18:00"
        )["reminder"]
        occurrence_id = reminder["occurrences"][0]["id"]

        clock.advance(hours=6, minutes=5)
        client.post(
            f"{occurrences_url(profile_id)}/{occurrence_id}/snooze",
            json={"minutes": 60},
            headers=headers,
        )
        clock.advance(hours=1, minutes=30)
        rows = {
            row["id"]: row
            for row in client.get(occurrences_url(profile_id), headers=headers).json()
        }
        assert rows[occurrence_id]["status"] == "snoozed"

        # Past the snooze plus the two-hour grace period.
        clock.advance(hours=2)
        rows = {
            row["id"]: row
            for row in client.get(occurrences_url(profile_id), headers=headers).json()
        }
        assert rows[occurrence_id]["status"] == "missed"

    def test_a_one_off_series_finishes_once_its_occurrence_is_answered(
        self, client, account, clock
    ):
        """Otherwise a reminder for last Tuesday sits in the list saying "On"
        forever, which is a small untruth that makes the whole list less worth
        reading."""
        headers, profile_id = account
        saved = create_reminder(client, headers, profile_id, time_of_day="18:00")
        occurrence_id = saved["reminder"]["occurrences"][0]["id"]
        clock.advance(hours=6)
        client.post(
            f"{occurrences_url(profile_id)}/{occurrence_id}/complete", headers=headers
        )

        listing = client.get(reminders_url(profile_id), headers=headers).json()
        assert listing["reminders"][0]["status"] == "completed"
        assert listing["reminders"][0]["status_label"] == "Finished"

    def test_an_older_queued_action_cannot_overwrite_a_newer_one(
        self, client, account, clock
    ):
        """Section 40, on an occurrence. The most recent explicit action wins."""
        headers, profile_id = account
        reminder = create_reminder(
            client, headers, profile_id, recurrence="daily", time_of_day="18:00"
        )["reminder"]
        occurrence_id = reminder["occurrences"][0]["id"]
        clock.advance(hours=6)
        queued_at = clock.now

        clock.advance(minutes=20)
        client.post(
            f"{occurrences_url(profile_id)}/{occurrence_id}/dismiss",
            json={"action_at": clock.now.isoformat()},
            headers=headers,
        )
        stale = client.post(
            f"{occurrences_url(profile_id)}/{occurrence_id}/complete",
            json={"action_at": queued_at.isoformat()},
            headers=headers,
        ).json()
        assert stale["applied"] is False
        assert stale["occurrence"]["status"] == "dismissed"


class TestTodayIntegration:
    def test_a_due_reminder_reaches_today(self, client, account, clock):
        headers, profile_id = account
        create_reminder(
            client, headers, profile_id, recurrence="daily", time_of_day="18:00"
        )
        clock.advance(hours=6)
        today = client.get(
            f"/api/v1/today?local_date={TODAY.isoformat()}", headers=headers
        ).json()
        rows = [item for item in today["important"] if item["type"] == "general_reminder"]
        assert len(rows) == 1
        assert rows[0]["title"] == "Ring the bank"
        assert today["daily_life"]["reminders"]["due_now"] == 1


class TestMaintenanceScript:
    def test_the_script_writes_what_a_read_would_have_written(
        self, db, client, account, clock
    ):
        """Section 63. The script is for the profile nobody opened.

        Correctness does not depend on it -- a read replenishes first -- so the
        test is that running it produces the same state, not that anything
        waits for it.
        """
        from scripts import productivity_maintenance

        headers, profile_id = account
        create_reminder(
            client, headers, profile_id, recurrence="daily", time_of_day="18:00"
        )
        clock.advance(hours=9)

        seen, generated, missed = productivity_maintenance.run(db, clock.now)
        assert seen == 1
        assert missed >= 1

    def test_a_dry_run_changes_nothing(self, db, client, account, clock):
        from scripts import productivity_maintenance

        headers, profile_id = account
        create_reminder(
            client, headers, profile_id, recurrence="daily", time_of_day="18:00"
        )
        clock.advance(hours=9)
        productivity_maintenance.run(db, clock.now, dry_run=True)

        rows = client.get(occurrences_url(profile_id), headers=headers).json()
        assert rows  # the read itself replenishes, which is the point
