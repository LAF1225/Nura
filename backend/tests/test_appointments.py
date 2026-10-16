"""Appointments, questions and preparation (PRD 7, sections 65 and 68).

Every test runs against the real app, the real migrations and a real PostgreSQL
database, with a settable clock injected in place of the real one and private
media pointed at a throwaway directory.

**No hardware is involved anywhere in this file.** PRD 7 section 43 requires
every workflow to run with no robot linked, and it does -- there is nothing here
to disable, because nothing in the appointment or report code paths knows a robot
exists (sections 43 and 74).

Four groups are worth finding on purpose:

``TestAppointments`` covers the rule PRD 7 section 7 is most easily broken:
an appointment whose time has passed is *listed* as past and its status stays
``scheduled`` until the user says what happened. Nothing infers ``missed``.

``TestPreparation`` proves the period rules from section 14 -- including the
fallback when "since my last visit" cannot be answered, and that the fallback is
reported rather than silent.

``TestSuggestions`` checks that the neutral prompts are neutral: they restate
what the user recorded and never explain, connect or predict (section 24).

``TestAuthorization`` walks the whole chain at every depth. An appointment, a
question and a report each belong to a profile, and each is answered with 404
rather than 403 when it does not (section 51).
"""

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest

from app.api.deps import current_time
from app.main import app
from app.services.appointments import periods as period_service
from app.services.appointments import questions as question_service
from tests.test_devices import ready_account
from tests.test_today import Clock

#: A Monday. Chosen so "tomorrow" and "next week" never straddle a month end.
NOW = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)

#: 2 October 2026 at 15:30 Europe/London, which is 14:30 UTC (BST is UTC+1).
#: The offset is the point: PRD 7 section 42 requires the appointment to read
#: 3:30 PM wherever the reader is, and a naive implementation shows 2:30 PM.
LONDON_AFTERNOON = "2026-10-02T14:30:00+00:00"
LONDON = "Europe/London"


# --- helpers ----------------------------------------------------------------


@pytest.fixture
def clock(client) -> Clock:
    """A settable clock, injected in place of the real one.

    Declared here rather than imported from ``test_today``: a fixture is
    resolved by name in the module it is used from, and importing one only works
    by leaving an otherwise-unused name in the namespace.
    """
    fake = Clock()
    fake.now = NOW
    app.dependency_overrides[current_time] = lambda: fake.now
    return fake


@pytest.fixture
def account(client, make_token) -> tuple[dict[str, str], str]:
    """A ready account and the profile its appointments belong to."""
    headers = ready_account(client, make_token)
    profile_id = client.get("/api/v1/me", headers=headers).json()["profiles"][0]["id"]
    return headers, profile_id


def appointments_url(profile_id: str) -> str:
    return f"/api/v1/profiles/{profile_id}/appointments"


def create_appointment(client, headers, profile_id, **body) -> dict:
    """Creates an appointment and returns the stored appointment body."""
    payload = {
        "title": "Cardiology follow-up",
        "scheduled_at": LONDON_AFTERNOON,
        "timezone": LONDON,
        **body,
    }
    response = client.post(appointments_url(profile_id), json=payload, headers=headers)
    assert response.status_code == 201, response.json()
    return response.json()["appointment"]


def add_clinician(client, headers, profile_id, **body) -> dict:
    payload = {"name": "Dr Ahmed Khan", "specialty": "Cardiology", **body}
    response = client.post(
        f"/api/v1/profiles/{profile_id}/clinicians", json=payload, headers=headers
    )
    assert response.status_code == 201, response.json()
    return response.json()


def add_question(client, headers, profile_id, appointment_id, text, **body) -> dict:
    response = client.post(
        f"{appointments_url(profile_id)}/{appointment_id}/questions",
        json={"text": text, **body},
        headers=headers,
    )
    assert response.status_code in (200, 201), response.json()
    return response.json()


def prepare(client, headers, profile_id, appointment_id, **params) -> dict:
    response = client.get(
        f"{appointments_url(profile_id)}/{appointment_id}/prepare",
        params=params,
        headers=headers,
    )
    assert response.status_code == 200, response.json()
    return response.json()


def add_symptom(client, headers, profile_id, **body) -> dict:
    """An episode with a first entry, through the PRD 6 API."""
    payload = {"name": "Headache", **body}
    response = client.post(
        f"/api/v1/profiles/{profile_id}/symptoms", json=payload, headers=headers
    )
    assert response.status_code == 201, response.json()
    return response.json()["episode"]


def add_symptom_entry(client, headers, profile_id, episode_id, **body) -> dict:
    response = client.post(
        f"/api/v1/profiles/{profile_id}/symptoms/{episode_id}/entries",
        json=body,
        headers=headers,
    )
    assert response.status_code in (200, 201), response.json()
    return response.json()["entry"]


def add_medication(client, headers, profile_id, **body) -> dict:
    payload = {"name": "Metformin", "dose": "500", "dose_unit": "mg", **body}
    response = client.post(
        f"/api/v1/profiles/{profile_id}/medications", json=payload, headers=headers
    )
    assert response.status_code == 201, response.json()
    return response.json()


def submit_checkin(client, headers, level, note=None, on_date=None) -> None:
    body: dict = {"wellbeing_level": level}
    if note is not None:
        body["note"] = note
    if on_date is not None:
        body["local_date"] = on_date
    response = client.put("/api/v1/daily-checkins/today", json=body, headers=headers)
    assert response.status_code in (200, 201), response.json()


# --- appointments -----------------------------------------------------------


class TestAppointments:
    def test_creates_an_appointment_with_only_the_required_fields(
        self, client, account, clock
    ):
        """PRD 7 section 8: keep the optional fields optional."""
        headers, profile_id = account
        appointment = create_appointment(client, headers, profile_id)

        assert appointment["title"] == "Cardiology follow-up"
        assert appointment["status"] == "scheduled"
        assert appointment["preparation_status"] == "not_started"
        assert appointment["clinician"] is None
        assert appointment["location_name"] is None
        assert appointment["question_count"] == 0
        assert appointment["report_count"] == 0
        assert appointment["reminders_enabled"] is True

    def test_shows_the_time_in_the_appointments_own_zone(self, client, account, clock):
        """PRD 7 section 42. 14:30 UTC is 3:30 PM in London, and says so."""
        headers, profile_id = account
        appointment = create_appointment(client, headers, profile_id)

        assert appointment["time_label"] == "3:30 PM"
        assert appointment["day_label"] == "2 October 2026"
        assert appointment["local_date"] == "2026-10-02"
        assert appointment["when_label"] == "2 October 2026 at 3:30 PM"

    def test_names_today_and_tomorrow(self, client, account, clock):
        """The three days a person thinks of by name, and nothing else."""
        headers, profile_id = account
        today = create_appointment(
            client, headers, profile_id, scheduled_at="2026-09-28T16:00:00+00:00"
        )
        tomorrow = create_appointment(
            client, headers, profile_id, scheduled_at="2026-09-29T16:00:00+00:00"
        )
        later = create_appointment(
            client, headers, profile_id, scheduled_at="2026-10-05T16:00:00+00:00"
        )

        assert today["relative_day"] == "Today"
        assert tomorrow["relative_day"] == "Tomorrow"
        assert later["relative_day"] is None
        assert later["when_label"] == "5 October 2026 at 5:00 PM"

    def test_links_a_clinician_from_the_users_own_list(self, client, account, clock):
        headers, profile_id = account
        clinician = add_clinician(client, headers, profile_id)
        appointment = create_appointment(
            client, headers, profile_id, clinician_id=clinician["id"]
        )

        assert appointment["clinician"]["name"] == "Dr Ahmed Khan"
        assert appointment["clinician"]["specialty"] == "Cardiology"

    def test_refuses_a_clinician_that_is_not_this_profiles(
        self, client, account, clock, make_token
    ):
        """Otherwise an appointment could read another account's contact out."""
        headers, profile_id = account
        other_headers = ready_account(client, make_token)
        other_profile = client.get("/api/v1/me", headers=other_headers).json()[
            "profiles"
        ][0]["id"]
        theirs = add_clinician(client, other_headers, other_profile)

        response = client.post(
            appointments_url(profile_id),
            json={
                "title": "Check-up",
                "scheduled_at": LONDON_AFTERNOON,
                "timezone": LONDON,
                "clinician_id": theirs["id"],
            },
            headers=headers,
        )
        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "unknown_clinician"

    def test_refuses_an_unknown_time_zone(self, client, account, clock):
        headers, profile_id = account
        response = client.post(
            appointments_url(profile_id),
            json={
                "title": "Check-up",
                "scheduled_at": LONDON_AFTERNOON,
                "timezone": "Mars/Olympus_Mons",
            },
            headers=headers,
        )
        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "unknown_timezone"

    def test_a_replayed_client_id_does_not_create_a_second_appointment(
        self, client, account, clock
    ):
        """PRD 7 section 53: an offline draft may be retried freely."""
        headers, profile_id = account
        body = {
            "title": "Blood test",
            "scheduled_at": LONDON_AFTERNOON,
            "timezone": LONDON,
            "client_appointment_id": "draft-1",
        }
        first = client.post(appointments_url(profile_id), json=body, headers=headers)
        second = client.post(appointments_url(profile_id), json=body, headers=headers)

        assert first.status_code == 201 and first.json()["created"] is True
        assert second.status_code == 200 and second.json()["created"] is False
        assert second.json()["appointment"]["id"] == first.json()["appointment"]["id"]
        assert len(client.get(appointments_url(profile_id), headers=headers).json()) == 1

    def test_lists_upcoming_past_and_cancelled_separately(self, client, account, clock):
        """PRD 7 section 41."""
        headers, profile_id = account
        ahead = create_appointment(
            client, headers, profile_id, scheduled_at="2026-10-05T10:00:00+00:00"
        )
        behind = create_appointment(
            client, headers, profile_id, scheduled_at="2026-09-01T10:00:00+00:00"
        )
        dropped = create_appointment(
            client, headers, profile_id, scheduled_at="2026-10-09T10:00:00+00:00"
        )
        client.post(
            f"{appointments_url(profile_id)}/{dropped['id']}/cancel", headers=headers
        )

        def ids(scope):
            response = client.get(
                appointments_url(profile_id), params={"scope": scope}, headers=headers
            )
            assert response.status_code == 200
            return [row["id"] for row in response.json()]

        assert ids("upcoming") == [ahead["id"]]
        assert ids("past") == [behind["id"]]
        assert ids("cancelled") == [dropped["id"]]

    def test_a_past_appointment_is_not_marked_missed(self, client, account, clock):
        """PRD 7 section 7. The commonest reason is that nobody opened the app."""
        headers, profile_id = account
        create_appointment(
            client, headers, profile_id, scheduled_at="2026-09-01T10:00:00+00:00"
        )
        clock.advance(days=30)

        rows = client.get(
            appointments_url(profile_id), params={"scope": "past"}, headers=headers
        ).json()
        assert [row["status"] for row in rows] == ["scheduled"]
        assert rows[0]["completed_at"] is None

    def test_edits_the_time_and_the_reminder_preference(self, client, account, clock):
        headers, profile_id = account
        appointment = create_appointment(client, headers, profile_id)

        response = client.patch(
            f"{appointments_url(profile_id)}/{appointment['id']}",
            json={
                "scheduled_at": "2026-10-03T09:00:00+00:00",
                "reminders_enabled": False,
                "location_name": "City Hospital",
            },
            headers=headers,
        )
        assert response.status_code == 200
        updated = response.json()
        assert updated["time_label"] == "10:00 AM"
        assert updated["day_label"] == "3 October 2026"
        assert updated["reminders_enabled"] is False
        assert updated["location_name"] == "City Hospital"

    def test_a_patch_cannot_set_the_status(self, client, account, clock):
        """Status moves by doing something to the appointment, never by PATCH."""
        headers, profile_id = account
        appointment = create_appointment(client, headers, profile_id)

        response = client.patch(
            f"{appointments_url(profile_id)}/{appointment['id']}",
            json={"status": "completed", "completed_at": NOW.isoformat()},
            headers=headers,
        )
        assert response.status_code == 200
        assert response.json()["status"] == "scheduled"
        assert response.json()["completed_at"] is None

    def test_cancelling_keeps_the_row_and_its_timestamp(self, client, account, clock):
        headers, profile_id = account
        appointment = create_appointment(client, headers, profile_id)
        url = f"{appointments_url(profile_id)}/{appointment['id']}/cancel"

        first = client.post(url, headers=headers).json()
        assert first["status"] == "cancelled"
        assert first["cancelled_at"] is not None

        clock.advance(days=1)
        again = client.post(url, headers=headers).json()
        assert again["cancelled_at"] == first["cancelled_at"]

    def test_completing_records_the_notes_and_does_not_blank_them_on_a_retry(
        self, client, account, clock
    ):
        """PRD 7 section 38, kept minimal."""
        headers, profile_id = account
        appointment = create_appointment(client, headers, profile_id)
        url = f"{appointments_url(profile_id)}/{appointment['id']}/complete"

        done = client.post(
            url,
            json={
                "visit_notes": "Continue at lower intensity.",
                "follow_up_date": "2026-12-01",
            },
            headers=headers,
        ).json()
        assert done["status"] == "completed"
        assert done["visit_notes"] == "Continue at lower intensity."
        assert done["follow_up_date"] == "2026-12-01"

        again = client.post(url, json={}, headers=headers).json()
        assert again["visit_notes"] == "Continue at lower intensity."
        assert again["completed_at"] == done["completed_at"]

    def test_reopens_a_cancelled_appointment(self, client, account, clock):
        headers, profile_id = account
        appointment = create_appointment(client, headers, profile_id)
        client.post(
            f"{appointments_url(profile_id)}/{appointment['id']}/cancel",
            headers=headers,
        )

        response = client.post(
            f"{appointments_url(profile_id)}/{appointment['id']}/reopen",
            headers=headers,
        )
        assert response.status_code == 200
        assert response.json()["status"] == "scheduled"

    def test_deletes_an_appointment(self, client, account, clock):
        headers, profile_id = account
        appointment = create_appointment(client, headers, profile_id)

        response = client.delete(
            f"{appointments_url(profile_id)}/{appointment['id']}", headers=headers
        )
        assert response.status_code == 204
        assert client.get(appointments_url(profile_id), headers=headers).json() == []

    def test_summarises_the_three_lists_for_care(self, client, account, clock):
        """PRD 7 section 5."""
        headers, profile_id = account
        create_appointment(
            client, headers, profile_id, scheduled_at="2026-10-05T10:00:00+00:00"
        )
        create_appointment(
            client, headers, profile_id, scheduled_at="2026-09-01T10:00:00+00:00"
        )

        response = client.get(f"{appointments_url(profile_id)}/summary", headers=headers)
        assert response.status_code == 200
        body = response.json()
        assert body["upcoming_count"] == 1
        assert body["past_count"] == 1
        assert body["cancelled_count"] == 0
        assert body["has_appointments"] is True
        assert body["next"]["when_label"] == "5 October 2026 at 11:00 AM"

    def test_an_account_with_no_appointments_gets_an_empty_summary(
        self, client, account, clock
    ):
        """PRD 7 section 9's empty state is a state, not an error."""
        headers, profile_id = account
        body = client.get(
            f"{appointments_url(profile_id)}/summary", headers=headers
        ).json()
        assert body == {
            "profile_id": profile_id,
            "upcoming_count": 0,
            "past_count": 0,
            "cancelled_count": 0,
            "has_appointments": False,
            "next": None,
        }


# --- questions --------------------------------------------------------------


class TestQuestions:
    def test_keeps_the_users_wording_and_their_order(self, client, account, clock):
        """PRD 7 section 23: preserve the user's wording."""
        headers, profile_id = account
        appointment = create_appointment(client, headers, profile_id)
        text = "Could this medication be contributing to my fatigue?"

        add_question(client, headers, profile_id, appointment["id"], text)
        add_question(
            client, headers, profile_id, appointment["id"], "Do I need any tests?"
        )

        rows = client.get(
            f"{appointments_url(profile_id)}/{appointment['id']}/questions",
            headers=headers,
        ).json()
        assert [row["text"] for row in rows] == [text, "Do I need any tests?"]
        assert [row["position"] for row in rows] == [0, 1]

    def test_a_replayed_client_id_does_not_add_a_second_question(
        self, client, account, clock
    ):
        headers, profile_id = account
        appointment = create_appointment(client, headers, profile_id)
        body = {"text": "Should I continue physiotherapy?", "client_question_id": "q-1"}
        url = f"{appointments_url(profile_id)}/{appointment['id']}/questions"

        first = client.post(url, json=body, headers=headers)
        second = client.post(url, json=body, headers=headers)

        assert first.status_code == 201 and first.json()["created"] is True
        assert second.status_code == 200 and second.json()["created"] is False
        assert len(client.get(url, headers=headers).json()) == 1

    def test_records_the_answer_the_user_was_given(self, client, account, clock):
        """PRD 7 section 39. Their record, not verified clinical data."""
        headers, profile_id = account
        appointment = create_appointment(client, headers, profile_id)
        question = add_question(
            client, headers, profile_id, appointment["id"], "Continue physio?"
        )["question"]

        response = client.patch(
            f"{appointments_url(profile_id)}/{appointment['id']}"
            f"/questions/{question['id']}",
            json={
                "is_answered": True,
                "answer_note": "Doctor said continue at lower intensity.",
            },
            headers=headers,
        )
        assert response.status_code == 200
        assert response.json()["is_answered"] is True
        assert (
            response.json()["answer_note"] == "Doctor said continue at lower intensity."
        )

    def test_deleting_closes_the_gap_in_the_order(self, client, account, clock):
        headers, profile_id = account
        appointment = create_appointment(client, headers, profile_id)
        url = f"{appointments_url(profile_id)}/{appointment['id']}/questions"
        created = [
            add_question(client, headers, profile_id, appointment["id"], f"Q{index}")[
                "question"
            ]
            for index in range(3)
        ]

        client.delete(f"{url}/{created[1]['id']}", headers=headers)

        rows = client.get(url, headers=headers).json()
        assert [row["text"] for row in rows] == ["Q0", "Q2"]
        assert [row["position"] for row in rows] == [0, 1]

    def test_reorders_to_the_list_the_client_is_showing(self, client, account, clock):
        headers, profile_id = account
        appointment = create_appointment(client, headers, profile_id)
        created = [
            add_question(client, headers, profile_id, appointment["id"], f"Q{index}")[
                "question"
            ]
            for index in range(3)
        ]

        response = client.put(
            f"{appointments_url(profile_id)}/{appointment['id']}/questions/order",
            json={"question_ids": [created[2]["id"], created[0]["id"]]},
            headers=headers,
        )
        assert response.status_code == 200
        assert [row["text"] for row in response.json()] == ["Q2", "Q0", "Q1"]

    def test_refuses_more_questions_than_a_consultation_can_hold(
        self, client, account, clock
    ):
        headers, profile_id = account
        appointment = create_appointment(client, headers, profile_id)
        url = f"{appointments_url(profile_id)}/{appointment['id']}/questions"
        for index in range(question_service.MAX_QUESTIONS):
            client.post(url, json={"text": f"Q{index}"}, headers=headers)

        response = client.post(url, json={"text": "one more"}, headers=headers)
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "too_many_questions"

    def test_preparation_status_follows_what_actually_exists(
        self, client, account, clock
    ):
        """PRD 7 section 6. The column is a cache of a derivation, never a claim."""
        headers, profile_id = account
        appointment = create_appointment(client, headers, profile_id)
        detail_url = f"{appointments_url(profile_id)}/{appointment['id']}"

        assert (
            client.get(detail_url, headers=headers).json()["preparation_status"]
            == "not_started"
        )

        question = add_question(
            client, headers, profile_id, appointment["id"], "Anything to worry about?"
        )["question"]
        assert (
            client.get(detail_url, headers=headers).json()["preparation_status"]
            == "in_progress"
        )

        client.delete(f"{detail_url}/questions/{question['id']}", headers=headers)
        assert (
            client.get(detail_url, headers=headers).json()["preparation_status"]
            == "not_started"
        )


# --- preparation ------------------------------------------------------------


class TestPreparation:
    def test_defaults_to_since_the_last_visit_and_says_when_it_cannot(
        self, client, account, clock
    ):
        """PRD 7 section 14's fallback, reported rather than silent."""
        headers, profile_id = account
        appointment = create_appointment(client, headers, profile_id)

        body = prepare(client, headers, profile_id, appointment["id"])
        period = body["period"]

        assert period["requested_preset"] == "since_last_visit"
        assert period["preset"] == "30_days"
        assert period["note"] is not None
        assert "clinician" in period["note"]
        assert period["days"] == 30
        assert period["end"] == "2026-09-28"
        assert period["start"] == "2026-08-30"

    def test_runs_from_the_previous_visit_with_the_same_clinician(
        self, client, account, clock
    ):
        headers, profile_id = account
        clinician = add_clinician(client, headers, profile_id)
        create_appointment(
            client,
            headers,
            profile_id,
            scheduled_at="2026-09-01T09:00:00+00:00",
            clinician_id=clinician["id"],
        )
        appointment = create_appointment(
            client, headers, profile_id, clinician_id=clinician["id"]
        )

        period = prepare(client, headers, profile_id, appointment["id"])["period"]
        assert period["preset"] == "since_last_visit"
        assert period["start"] == "2026-09-01"
        assert period["note"] is None
        assert period["since_label"] == "Since your appointment on 1 September 2026"

    def test_falls_back_when_the_clinician_has_no_earlier_appointment(
        self, client, account, clock
    ):
        headers, profile_id = account
        clinician = add_clinician(client, headers, profile_id)
        appointment = create_appointment(
            client, headers, profile_id, clinician_id=clinician["id"]
        )

        period = prepare(client, headers, profile_id, appointment["id"])["period"]
        assert period["preset"] == "30_days"
        assert "no earlier appointment" in period["note"]

    def test_offers_the_fixed_windows(self, client, account, clock):
        headers, profile_id = account
        appointment = create_appointment(client, headers, profile_id)

        for preset, days in (("7_days", 7), ("30_days", 30), ("90_days", 90)):
            period = prepare(
                client, headers, profile_id, appointment["id"], preset=preset
            )["period"]
            assert period["preset"] == preset
            assert period["days"] == days

    def test_a_period_ends_on_the_appointment_day_or_today(self, client, account, clock):
        """Preparing for Friday on Monday covers up to Monday."""
        headers, profile_id = account
        past = create_appointment(
            client, headers, profile_id, scheduled_at="2026-09-10T09:00:00+00:00"
        )

        period = prepare(client, headers, profile_id, past["id"], preset="7_days")[
            "period"
        ]
        assert period["end"] == "2026-09-10"
        assert period["start"] == "2026-09-04"

    def test_a_custom_period_is_validated_and_never_runs_into_the_future(
        self, client, account, clock
    ):
        headers, profile_id = account
        appointment = create_appointment(client, headers, profile_id)
        url = f"{appointments_url(profile_id)}/{appointment['id']}/prepare"

        backwards = client.get(
            url,
            params={
                "preset": "custom",
                "period_start": "2026-09-20",
                "period_end": "2026-09-01",
            },
            headers=headers,
        )
        assert backwards.status_code == 422
        assert backwards.json()["detail"]["code"] == "invalid_report_period"

        missing = client.get(url, params={"preset": "custom"}, headers=headers)
        assert missing.status_code == 422

        clamped = client.get(
            url,
            params={
                "preset": "custom",
                "period_start": "2026-09-01",
                "period_end": "2026-12-31",
            },
            headers=headers,
        )
        assert clamped.status_code == 200
        assert clamped.json()["period"]["end"] == "2026-09-28"
        assert clamped.json()["period"]["label"] == "1 to 28 September 2026"

    def test_a_period_longer_than_two_years_is_refused(self, client, account, clock):
        headers, profile_id = account
        appointment = create_appointment(client, headers, profile_id)
        too_long = timedelta(days=period_service.MAX_PERIOD_DAYS + 5)
        far_back = (NOW.date() - too_long).isoformat()

        response = client.get(
            f"{appointments_url(profile_id)}/{appointment['id']}/prepare",
            params={
                "preset": "custom",
                "period_start": far_back,
                "period_end": NOW.date().isoformat(),
            },
            headers=headers,
        )
        assert response.status_code == 422

    def test_counts_symptom_entries_inside_the_period_only(self, client, account, clock):
        """PRD 7 section 16: summarise structured data, counted."""
        headers, profile_id = account
        appointment = create_appointment(client, headers, profile_id)
        episode = add_symptom(
            client,
            headers,
            profile_id,
            first_entry={
                "recorded_at": "2026-09-20T09:00:00+00:00",
                "severity": 3,
                "free_text_note": "worse in the mornings",
            },
        )
        add_symptom_entry(
            client,
            headers,
            profile_id,
            episode["id"],
            recorded_at="2026-09-25T09:00:00+00:00",
            severity=6,
            change_state="worsening",
        )
        # Well outside a 7-day window, so it must not be counted there.
        add_symptom_entry(
            client,
            headers,
            profile_id,
            episode["id"],
            recorded_at="2026-08-01T09:00:00+00:00",
            severity=9,
        )

        body = prepare(client, headers, profile_id, appointment["id"], preset="30_days")
        review = body["symptoms"][0]
        assert review["entry_count"] == 2
        assert review["severity_min"] == 3
        assert review["severity_max"] == 6
        assert review["latest_severity"] == 6
        assert review["latest_change_state"] == "worsening"
        assert [note["text"] for note in review["notes"]] == ["worse in the mornings"]

    def test_an_ongoing_symptom_with_nothing_recent_still_appears(
        self, client, account, clock
    ):
        """Silence must not read as "it stopped"."""
        headers, profile_id = account
        appointment = create_appointment(client, headers, profile_id)
        add_symptom(
            client,
            headers,
            profile_id,
            name="Knee pain",
            first_entry={"recorded_at": "2026-05-01T09:00:00+00:00", "severity": 4},
        )

        body = prepare(client, headers, profile_id, appointment["id"], preset="7_days")
        review = body["symptoms"][0]
        assert review["name"] == "Knee pain"
        assert review["entry_count"] == 0
        assert review["is_ongoing"] is True

    def test_a_resolved_symptom_outside_the_period_is_left_out(
        self, client, account, clock
    ):
        headers, profile_id = account
        appointment = create_appointment(client, headers, profile_id)
        episode = add_symptom(
            client,
            headers,
            profile_id,
            name="Sore throat",
            first_entry={"recorded_at": "2026-05-01T09:00:00+00:00"},
        )
        client.post(
            f"/api/v1/profiles/{profile_id}/symptoms/{episode['id']}/resolve",
            headers=headers,
        )

        body = prepare(client, headers, profile_id, appointment["id"], preset="7_days")
        assert body["symptoms"] == []

    def test_carries_uncertainty_and_denial_through(self, client, account, clock):
        """PRD 7 section 47: preserve uncertainty."""
        headers, profile_id = account
        appointment = create_appointment(client, headers, profile_id)
        add_symptom(
            client,
            headers,
            profile_id,
            first_entry={
                "recorded_at": "2026-09-25T09:00:00+00:00",
                "negated_items": ["fever"],
                "uncertain_items": ["dizziness"],
                "context_dependent_items": ["only when standing"],
            },
        )

        review = prepare(client, headers, profile_id, appointment["id"])["symptoms"][0]
        assert review["negated_items"] == ["fever"]
        assert review["uncertain_items"] == ["dizziness"]
        assert review["context_dependent_items"] == ["only when standing"]

    def test_lists_active_medications_with_how_often_they_are_taken(
        self, client, account, clock
    ):
        """PRD 7 section 17, using the PRD 5 schedule where there is one."""
        headers, profile_id = account
        appointment = create_appointment(client, headers, profile_id)
        medication = add_medication(client, headers, profile_id)
        add_medication(client, headers, profile_id, name="Old tablet", is_active=False)
        client.post(
            f"/api/v1/profiles/{profile_id}/medication-schedules",
            json={
                "medication_id": medication["id"],
                "schedule_type": "daily",
                "timezone": LONDON,
                "start_date": "2026-09-01",
                "times": [{"time_of_day": "08:00"}, {"time_of_day": "20:00"}],
            },
            headers=headers,
        )

        body = prepare(client, headers, profile_id, appointment["id"])
        assert [row["display_name"] for row in body["medications"]] == [
            "Metformin 500 mg"
        ]
        assert body["medications"][0]["frequency"] == "Twice daily"

    def test_falls_back_to_the_records_own_frequency_text(self, client, account, clock):
        headers, profile_id = account
        appointment = create_appointment(client, headers, profile_id)
        add_medication(
            client,
            headers,
            profile_id,
            name="Inhaler",
            dose=None,
            dose_unit=None,
            frequency_text="two puffs when needed",
        )

        body = prepare(client, headers, profile_id, appointment["id"])
        inhaler = next(row for row in body["medications"] if row["name"] == "Inhaler")
        assert inhaler["frequency"] == "two puffs when needed"
        assert inhaler["display_name"] == "Inhaler"

    def test_adherence_matches_the_medication_history(self, client, account, clock):
        """PRD 7 section 18: the same figures the medication screens show."""
        headers, profile_id = account
        appointment = create_appointment(client, headers, profile_id)
        medication = add_medication(client, headers, profile_id)
        client.post(
            f"/api/v1/profiles/{profile_id}/medication-schedules",
            json={
                "medication_id": medication["id"],
                "schedule_type": "daily",
                "timezone": "UTC",
                "start_date": "2026-09-28",
                # Later today: dose generation never invents a moment that has
                # already passed (PRD 5, section 22).
                "times": [{"time_of_day": "20:00"}],
            },
            headers=headers,
        )
        doses = client.get(
            f"/api/v1/profiles/{profile_id}/medication-doses",
            params={"from_date": "2026-09-28", "to_date": "2026-09-28"},
            headers=headers,
        ).json()
        client.post(
            f"/api/v1/profiles/{profile_id}/medication-doses/{doses[0]['id']}/taken",
            json={},
            headers=headers,
        )

        body = prepare(client, headers, profile_id, appointment["id"])
        adherence = body["adherence"]
        assert adherence["taken"] == 1
        assert adherence["total"] == 1
        assert adherence["percent"] == 100

        history = client.get(
            f"/api/v1/profiles/{profile_id}/medication-adherence",
            params={"from_date": adherence["from_date"], "to_date": adherence["to_date"]},
            headers=headers,
        ).json()
        assert history["taken"] == adherence["taken"]
        assert history["total"] == adherence["total"]

    def test_counts_the_daily_checkins(self, client, account, clock):
        """PRD 7 section 20: three counts, and no interpretation."""
        headers, profile_id = account
        appointment = create_appointment(client, headers, profile_id)
        submit_checkin(client, headers, "not_great", note="tired all day")

        body = prepare(client, headers, profile_id, appointment["id"])
        checkins = body["daily_checkins"]
        assert checkins["not_great"] == 1
        assert checkins["good"] == 0
        assert checkins["total"] == 1
        assert [note["note"] for note in checkins["notes"]] == ["tired all day"]

    def test_reads_the_health_background(self, client, account, clock):
        """PRD 7 section 21, with an uncertain condition labelled as one."""
        headers, profile_id = account
        appointment = create_appointment(client, headers, profile_id)
        client.post(
            f"/api/v1/profiles/{profile_id}/conditions",
            json={"name": "Asthma", "status": "active", "diagnosed_year": 2015},
            headers=headers,
        )
        client.post(
            f"/api/v1/profiles/{profile_id}/conditions",
            json={"name": "Coeliac disease", "status": "uncertain"},
            headers=headers,
        )
        client.post(
            f"/api/v1/profiles/{profile_id}/conditions",
            json={"name": "Chickenpox", "status": "resolved"},
            headers=headers,
        )
        client.post(
            f"/api/v1/profiles/{profile_id}/allergies",
            json={
                "allergen": "Penicillin",
                "allergy_type": "medication",
                "reaction": "rash",
                "severity": "moderate",
            },
            headers=headers,
        )
        client.post(
            f"/api/v1/profiles/{profile_id}/procedures",
            json={"name": "Appendectomy", "performed_year": 2019},
            headers=headers,
        )
        client.patch(
            f"/api/v1/profiles/{profile_id}/health-setup",
            json={"blood_type": "O+"},
            headers=headers,
        )

        baseline = prepare(client, headers, profile_id, appointment["id"])["baseline"]
        assert [row["name"] for row in baseline["conditions"]] == [
            "Asthma",
            "Coeliac disease",
        ]
        assert baseline["conditions"][0]["diagnosed_label"] == "2015"
        assert baseline["conditions"][1]["status"] == "uncertain"
        assert baseline["allergies"][0]["allergen"] == "Penicillin"
        assert baseline["procedures"][0]["performed_label"] == "2019"
        assert baseline["blood_type"] == "O+"

    def test_offers_medical_notes_without_choosing_any(self, client, account, clock):
        """PRD 7 section 27: offered, never chosen."""
        headers, profile_id = account
        appointment = create_appointment(client, headers, profile_id)
        client.post(
            f"/api/v1/profiles/{profile_id}/medical-notes",
            json={"title": "Hospital parking", "body": "Use the west entrance."},
            headers=headers,
        )

        body = prepare(client, headers, profile_id, appointment["id"])
        assert [note["title"] for note in body["medical_notes"]] == ["Hospital parking"]
        assert body["default_selection"]["include"]["medical_notes"] is False
        assert body["default_selection"]["medical_note_ids"] == []

    def test_an_account_with_nothing_recorded_says_so(self, client, account, clock):
        """PRD 7 section 46: a real state, not an error."""
        headers, profile_id = account
        appointment = create_appointment(client, headers, profile_id)

        body = prepare(client, headers, profile_id, appointment["id"])
        assert body["has_health_data"] is False
        assert body["symptoms"] == []
        assert body["medications"] == []
        assert body["adherence"]["total"] == 0

    def test_the_default_selection_ticks_every_symptom(self, client, account, clock):
        """PRD 7 section 25: the narrowing is the user's, so nothing starts off."""
        headers, profile_id = account
        appointment = create_appointment(client, headers, profile_id)
        first = add_symptom(
            client,
            headers,
            profile_id,
            first_entry={"recorded_at": "2026-09-25T09:00:00+00:00"},
        )
        second = add_symptom(
            client,
            headers,
            profile_id,
            name="Dizziness",
            first_entry={"recorded_at": "2026-09-26T09:00:00+00:00"},
        )

        body = prepare(client, headers, profile_id, appointment["id"])
        chosen = set(body["default_selection"]["symptom_episode_ids"])
        assert chosen == {first["id"], second["id"]}
        assert body["default_selection"]["include_appendix"] is False

    def test_preparing_changes_nothing(self, client, account, clock):
        """Reads only. Section 13's flow may be reopened as often as the user likes."""
        headers, profile_id = account
        appointment = create_appointment(client, headers, profile_id)
        before = client.get(
            f"{appointments_url(profile_id)}/{appointment['id']}", headers=headers
        ).json()

        prepare(client, headers, profile_id, appointment["id"])
        prepare(client, headers, profile_id, appointment["id"], preset="7_days")

        after = client.get(
            f"{appointments_url(profile_id)}/{appointment['id']}", headers=headers
        ).json()
        assert after["preparation_status"] == "not_started"
        assert after["updated_at"] == before["updated_at"]


# --- suggestions ------------------------------------------------------------


class TestSuggestions:
    def test_offers_a_prompt_about_a_symptom_the_user_called_worsening(
        self, client, account, clock
    ):
        """PRD 7 section 24, restating the user's own answer."""
        headers, profile_id = account
        appointment = create_appointment(client, headers, profile_id)
        add_symptom(
            client,
            headers,
            profile_id,
            first_entry={
                "recorded_at": "2026-09-25T09:00:00+00:00",
                "change_state": "worsening",
            },
        )

        offers = prepare(client, headers, profile_id, appointment["id"])["suggestions"]
        assert any(offer["reason"] == "symptom_worsening" for offer in offers)
        worsening = next(
            offer for offer in offers if offer["reason"] == "symptom_worsening"
        )
        assert worsening["prompt"] == (
            "Would you like to ask about your worsening headache?"
        )

    def test_always_offers_the_one_generic_prompt(self, client, account, clock):
        headers, profile_id = account
        appointment = create_appointment(client, headers, profile_id)

        offers = prepare(client, headers, profile_id, appointment["id"])["suggestions"]
        assert [offer["key"] for offer in offers] == ["follow_up_tests"]
        assert offers[0]["question_text"] == "Do I need any follow-up tests?"

    def test_a_suggestion_the_user_accepted_is_not_offered_again(
        self, client, account, clock
    ):
        """They become ordinary questions, indistinguishable from typed ones."""
        headers, profile_id = account
        appointment = create_appointment(client, headers, profile_id)
        add_question(
            client,
            headers,
            profile_id,
            appointment["id"],
            "Do I need any follow-up tests?",
        )

        offers = prepare(client, headers, profile_id, appointment["id"])["suggestions"]
        assert offers == []

    def test_no_suggestion_explains_connects_or_predicts(self, client, account, clock):
        """PRD 7 sections 3 and 45. A prompt restates; it never hypothesises."""
        headers, profile_id = account
        appointment = create_appointment(client, headers, profile_id)
        medication = add_medication(client, headers, profile_id)
        client.post(
            f"/api/v1/profiles/{profile_id}/medication-schedules",
            json={
                "medication_id": medication["id"],
                "schedule_type": "daily",
                "timezone": "UTC",
                "start_date": "2026-09-28",
                # Later today: dose generation never invents a moment that has
                # already passed (PRD 5, section 22).
                "times": [{"time_of_day": "20:00"}],
            },
            headers=headers,
        )
        doses = client.get(
            f"/api/v1/profiles/{profile_id}/medication-doses",
            params={"from_date": "2026-09-28", "to_date": "2026-09-28"},
            headers=headers,
        ).json()
        client.post(
            f"/api/v1/profiles/{profile_id}/medication-doses/{doses[0]['id']}/skip",
            json={"reason_code": "ran_out"},
            headers=headers,
        )
        add_symptom(
            client,
            headers,
            profile_id,
            first_entry={
                "recorded_at": "2026-09-25T09:00:00+00:00",
                "change_state": "worsening",
            },
        )

        offers = prepare(client, headers, profile_id, appointment["id"])["suggestions"]
        assert any(offer["reason"] == "doses_unrecorded" for offer in offers)

        forbidden = (
            "caus",
            "because",
            "due to",
            "likely",
            "probably",
            "may be",
            "side effect",
            "diagnos",
            "you should stop",
            "you should take",
        )
        for offer in offers:
            text = f"{offer['prompt']} {offer['question_text']}".lower()
            for phrase in forbidden:
                assert phrase not in text, (phrase, text)


# --- authorization ----------------------------------------------------------


class TestAuthorization:
    @pytest.fixture
    def other_account(self, client, make_token) -> dict[str, str]:
        return ready_account(client, make_token)

    def test_another_account_cannot_reach_an_appointment(
        self, client, account, clock, other_account
    ):
        """PRD 7 section 51: 404, never 403 -- an id is never confirmed."""
        headers, profile_id = account
        appointment = create_appointment(client, headers, profile_id)
        url = f"{appointments_url(profile_id)}/{appointment['id']}"

        assert client.get(url, headers=other_account).status_code == 404
        assert (
            client.patch(url, json={"title": "theirs"}, headers=other_account).status_code
            == 404
        )
        assert client.delete(url, headers=other_account).status_code == 404
        assert client.post(f"{url}/cancel", headers=other_account).status_code == 404
        assert (
            client.post(f"{url}/complete", json={}, headers=other_account).status_code
            == 404
        )
        assert client.get(f"{url}/prepare", headers=other_account).status_code == 404
        assert client.get(f"{url}/questions", headers=other_account).status_code == 404
        assert client.get(f"{url}/reports", headers=other_account).status_code == 404

    def test_another_account_cannot_reach_a_question(
        self, client, account, clock, other_account
    ):
        headers, profile_id = account
        appointment = create_appointment(client, headers, profile_id)
        question = add_question(client, headers, profile_id, appointment["id"], "Mine")[
            "question"
        ]
        url = (
            f"{appointments_url(profile_id)}/{appointment['id']}"
            f"/questions/{question['id']}"
        )

        assert (
            client.patch(url, json={"text": "theirs"}, headers=other_account).status_code
            == 404
        )
        assert client.delete(url, headers=other_account).status_code == 404

    def test_an_appointment_id_from_another_profile_is_not_found(
        self, client, account, clock, other_account
    ):
        """Their appointment under our profile path is a 404 too."""
        headers, profile_id = account
        other_profile = client.get("/api/v1/me", headers=other_account).json()[
            "profiles"
        ][0]["id"]
        theirs = create_appointment(client, other_account, other_profile)

        response = client.get(
            f"{appointments_url(profile_id)}/{theirs['id']}", headers=headers
        )
        assert response.status_code == 404

    def test_an_unknown_appointment_is_not_found(self, client, account, clock):
        headers, profile_id = account
        response = client.get(
            f"{appointments_url(profile_id)}/{uuid.uuid4()}", headers=headers
        )
        assert response.status_code == 404
        assert response.json()["detail"]["code"] == "not_found"

    def test_signed_out_requests_are_refused(self, client, account, clock):
        _, profile_id = account
        assert client.get(appointments_url(profile_id)).status_code == 401
        assert (
            client.post(appointments_url(profile_id), json={"title": "x"}).status_code
            == 401
        )


# --- Today and the card registry --------------------------------------------


class TestTodayIntegration:
    def test_today_carries_the_next_appointment(self, client, account, clock):
        """PRD 7 section 9, arriving with the day rather than as a second request."""
        headers, profile_id = account
        clinician = add_clinician(client, headers, profile_id)
        create_appointment(
            client,
            headers,
            profile_id,
            scheduled_at="2026-09-29T14:30:00+00:00",
            clinician_id=clinician["id"],
        )

        body = client.get("/api/v1/today", headers=headers).json()
        appointments = body["appointments"]
        assert appointments["upcoming_count"] == 1
        assert appointments["has_appointments"] is True
        assert appointments["next"]["clinician_name"] == "Dr Ahmed Khan"
        assert appointments["next"]["clinician_specialty"] == "Cardiology"
        assert appointments["next"]["relative_day"] == "Tomorrow"
        assert appointments["next"]["when_label"] == "Tomorrow at 3:30 PM"

    def test_today_reports_no_appointments_without_hiding_the_card(
        self, client, account, clock
    ):
        """Unlike medications and symptoms, this card has its own empty state."""
        headers, _ = account
        body = client.get("/api/v1/today", headers=headers).json()

        assert body["appointments"] == {
            "next": None,
            "upcoming_count": 0,
            "has_appointments": False,
        }
        card = next(row for row in body["cards"] if row["key"] == "appointments")
        assert card["available"] is True
        assert card["visible"] is True

    def test_todays_unprepared_appointment_is_in_important_today(
        self, client, account, clock
    ):
        """PRD 7 section 10 -- and not as an emergency."""
        headers, profile_id = account
        appointment = create_appointment(
            client, headers, profile_id, scheduled_at="2026-09-28T16:00:00+00:00"
        )

        body = client.get("/api/v1/today", headers=headers).json()
        rows = [row for row in body["important"] if row["type"] == "appointment"]
        assert len(rows) == 1
        assert rows[0]["id"] == f"appointment:{appointment['id']}"
        assert rows[0]["priority"] == "important"
        assert rows[0]["subtitle"] == "Today at 5:00 PM · Not prepared yet"
        assert rows[0]["action_route"] == f"/appointments/{appointment['id']}"

    def test_tomorrows_appointment_is_present_but_not_raised(
        self, client, account, clock
    ):
        headers, profile_id = account
        create_appointment(
            client, headers, profile_id, scheduled_at="2026-09-29T16:00:00+00:00"
        )

        body = client.get("/api/v1/today", headers=headers).json()
        rows = [row for row in body["important"] if row["type"] == "appointment"]
        assert [row["priority"] for row in rows] == ["normal"]

    def test_an_appointment_next_week_is_not_in_important_today(
        self, client, account, clock
    ):
        headers, profile_id = account
        create_appointment(
            client, headers, profile_id, scheduled_at="2026-10-06T16:00:00+00:00"
        )

        body = client.get("/api/v1/today", headers=headers).json()
        assert [row for row in body["important"] if row["type"] == "appointment"] == []

    def test_no_appointment_row_is_ever_worded_as_an_emergency(
        self, client, account, clock
    ):
        """PRD 7 section 10 says so outright."""
        headers, profile_id = account
        create_appointment(
            client, headers, profile_id, scheduled_at="2026-09-28T16:00:00+00:00"
        )

        body = client.get("/api/v1/today", headers=headers).json()
        rows = [row for row in body["important"] if row["type"] == "appointment"]
        words = " ".join(
            f"{row['title']} {row.get('subtitle') or ''}" for row in rows
        ).lower()
        for phrase in ("urgent", "emergency", "immediately", "warning", "alert", "!"):
            assert phrase not in words

    def test_an_account_with_no_profile_still_gets_today(self, client, make_token):
        """PRD 7 section 43's "no robot, no data" case, at the earliest state."""
        headers = {"Authorization": f"Bearer {make_token()}"}
        body = client.get("/api/v1/today", headers=headers).json()
        assert body["appointments"] is None


class TestCardRegistry:
    def test_the_appointments_card_can_be_shown_and_hidden(self, client, account):
        """It is a real card from PRD 7, so the user may turn it off."""
        headers, _ = account
        response = client.put(
            "/api/v1/dashboard-preferences",
            json={
                "cards": [
                    {"card_key": "appointments", "visible": False},
                    {"card_key": "daily_checkin", "visible": True},
                ]
            },
            headers=headers,
        )
        assert response.status_code == 200
        card = next(
            row for row in response.json()["cards"] if row["key"] == "appointments"
        )
        assert card["available"] is True
        assert card["visible"] is False


class TestPeriodWording:
    """``periods.resolve`` decides dates; these check how they read."""

    def test_a_range_drops_what_it_repeats(self):
        from app.services.appointments.wording import format_range

        assert format_range(date(2026, 9, 1), date(2026, 9, 28)) == (
            "1 to 28 September 2026"
        )
        assert format_range(date(2026, 9, 1), date(2026, 10, 2)) == (
            "1 September to 2 October 2026"
        )
        assert format_range(date(2025, 12, 28), date(2026, 1, 2)) == (
            "28 December 2025 to 2 January 2026"
        )
        assert format_range(date(2026, 9, 1), date(2026, 9, 1)) == "1 September 2026"

    def test_a_count_is_never_pluralised_wrongly(self):
        from app.services.appointments.wording import plural

        assert plural(1, "time") == "1 time"
        assert plural(6, "time") == "6 times"
        assert plural(1, "entry", "entries") == "1 entry"
        assert plural(2, "entry", "entries") == "2 entries"

    def test_a_list_reads_as_a_sentence(self):
        from app.services.appointments.wording import join_items

        assert join_items(["rest"]) == "rest"
        assert join_items(["rest", "walking"]) == "rest and walking"
        assert join_items(["rest", "walking", "heat"]) == "rest, walking and heat"
        assert join_items([" ", ""]) == ""
