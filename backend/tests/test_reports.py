"""Doctor reports: snapshots, versions, PDFs and privacy (PRD 7, ss65-66).

The report pipeline is four functions in a row -- read the records, build the
text, render the document, store the row -- and this file tests it at each joint.

Five things here are worth reading rather than skimming:

``TestSnapshot`` asserts the wording PRD 7 section 16 allows, sentence by
sentence, and that a section the user unticked is *absent* rather than empty.

``TestImmutability`` is the one that matters most. A report handed to a doctor
must not change because a symptom entry was corrected the following week
(section 30), and a PDF re-rendered from an old row must come out byte for byte
the same document (section 72's determinism criterion).

``TestPdf`` covers section 66's list: a non-empty file, the summary on page 1,
an appendix only when it is enabled, the expected headings present, excluded
sections absent, special characters handled, and a filename that says nothing
medical.

``TestNoDiagnosis`` reads every string a report can contain and fails on a named
likelihood, an attributed cause, a treatment suggestion or a graded adherence
figure (sections 18, 20 and 45).

``TestPrivacy`` proves there is no URL and no storage key in any response, that
an unrelated account gets a 404 for the document, and that deleting a report
takes the file with it and leaves the health records alone (sections 35, 52, 65).
"""

import io
import uuid

import pytest
from pypdf import PdfReader

from app.api.deps import current_time
from app.main import app
from app.models import (
    Allergy,
    AppointmentReport,
    DailyCheckIn,
    MedicalCondition,
    SymptomEntry,
    SymptomEpisode,
)
from app.services.appointments import reports as report_service
from app.services.appointments import snapshot as snapshot_service
from app.services.appointments.pdf import PdfReportService
from app.services.storage import get_object_store
from tests.test_appointments import (
    NOW,
    add_clinician,
    add_medication,
    add_question,
    add_symptom,
    add_symptom_entry,
    appointments_url,
    create_appointment,
    prepare,
    submit_checkin,
)
from tests.test_devices import ready_account
from tests.test_today import Clock

# --- helpers ----------------------------------------------------------------
#
# `account` and `clock` are declared here rather than imported: a fixture is
# resolved by name in the module it is used from, and importing one shadows the
# test parameter of the same name.


@pytest.fixture
def clock(client) -> Clock:
    fake = Clock()
    fake.now = NOW
    app.dependency_overrides[current_time] = lambda: fake.now
    return fake


@pytest.fixture
def account(client, make_token) -> tuple[dict[str, str], str]:
    headers = ready_account(client, make_token)
    profile_id = client.get("/api/v1/me", headers=headers).json()["profiles"][0]["id"]
    return headers, profile_id


def reports_url(profile_id: str, appointment_id: str) -> str:
    return f"{appointments_url(profile_id)}/{appointment_id}/reports"


def generate(client, headers, profile_id, appointment_id, **body) -> dict:
    """Generates a version and returns the saved report body."""
    response = client.post(
        reports_url(profile_id, appointment_id), json=body, headers=headers
    )
    assert response.status_code in (200, 201), response.json()
    return response.json()["report"]


def all_text(report: dict) -> str:
    """Every string in a report's snapshot, joined, for coarse assertions."""
    return "\n".join(snapshot_service.all_text(report["snapshot"]))


def headings(report: dict, group: str = "summary_sections") -> list[str]:
    return [section["heading"] for section in report["snapshot"][group]]


def section(report: dict, key: str, group: str = "summary_sections") -> dict | None:
    for entry in report["snapshot"][group]:
        if entry["key"] == key:
            return entry
    return None


def lines_of(report: dict, key: str, group: str = "summary_sections") -> list[str]:
    found = section(report, key, group)
    if found is None:
        return []
    return [line for item in found["items"] for line in item["lines"]]


def pdf_text(content: bytes) -> list[str]:
    """The text of each page, extracted."""
    reader = PdfReader(io.BytesIO(content))
    return [page.extract_text() or "" for page in reader.pages]


def stored_pdf(db, report_id: str) -> bytes:
    row = db.get(AppointmentReport, uuid.UUID(report_id))
    assert row is not None and row.file_storage_key is not None
    return get_object_store().get(row.file_storage_key)


@pytest.fixture
def rich_account(client, account, clock):
    """An account with something in every section a report can carry.

    Built through the public API so the records are the genuine article: a
    symptom with entries and a note, a medication with a schedule, a recorded
    dose, a check-in with a note, a condition, an allergy and a blood type.
    """
    headers, profile_id = account
    clinician = add_clinician(client, headers, profile_id)
    appointment = create_appointment(
        client, headers, profile_id, clinician_id=clinician["id"]
    )

    headache = add_symptom(
        client,
        headers,
        profile_id,
        first_entry={
            "recorded_at": "2026-09-20T09:00:00+00:00",
            "severity": 3,
            "free_text_note": "worse in the mornings",
            "exacerbating_factors": ["walking"],
            "relieving_factors": ["rest"],
            "associated_symptoms": ["nausea"],
            "uncertain_items": ["dizziness"],
            "negated_items": ["fever"],
        },
    )
    add_symptom_entry(
        client,
        headers,
        profile_id,
        headache["id"],
        recorded_at="2026-09-25T09:00:00+00:00",
        severity=6,
        change_state="worsening",
    )
    dizziness = add_symptom(
        client,
        headers,
        profile_id,
        name="Dizziness",
        first_entry={"recorded_at": "2026-09-26T09:00:00+00:00", "severity": 3},
    )

    medication = add_medication(client, headers, profile_id)
    client.post(
        f"/api/v1/profiles/{profile_id}/medication-schedules",
        json={
            "medication_id": medication["id"],
            "schedule_type": "daily",
            "timezone": "UTC",
            "start_date": "2026-09-28",
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
        json={"reason_code": "ran_out", "reason_text": "pharmacy was shut"},
        headers=headers,
    )

    submit_checkin(client, headers, "not_great", note="tired all day")
    client.post(
        f"/api/v1/profiles/{profile_id}/conditions",
        json={"name": "Asthma", "status": "active", "diagnosed_year": 2015},
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
    client.patch(
        f"/api/v1/profiles/{profile_id}/health-setup",
        json={"blood_type": "O+"},
        headers=headers,
    )
    add_question(
        client,
        headers,
        profile_id,
        appointment["id"],
        "Could this medication be contributing to my fatigue?",
    )

    return {
        "headers": headers,
        "profile_id": profile_id,
        "appointment_id": appointment["id"],
        "headache_id": headache["id"],
        "dizziness_id": dizziness["id"],
        "medication_id": medication["id"],
    }


def default_selection(client, world) -> dict:
    """The selection the app starts from: every section, every symptom."""
    body = prepare(client, world["headers"], world["profile_id"], world["appointment_id"])
    return body["default_selection"]


# --- the snapshot -----------------------------------------------------------


class TestSnapshot:
    def test_generates_a_first_version_with_everything_selected(
        self, client, rich_account
    ):
        world = rich_account
        report = generate(
            client,
            world["headers"],
            world["profile_id"],
            world["appointment_id"],
            selection=default_selection(client, world),
        )

        assert report["version"] == 1
        assert report["status"] == "ready"
        assert report["page_count"] >= 1
        assert report["byte_size"] > 0
        assert report["snapshot"]["title"] == "Nura Health Summary"
        assert headings(report) == [
            "Recent symptoms",
            "Current medications",
            "Medication doses",
            "Daily check-ins",
            "Relevant health background",
            "Questions for the clinician",
        ]

    def test_summarises_a_symptom_in_the_wording_prd_7_allows(self, client, rich_account):
        """PRD 7 section 16's own example, in Nura's voice."""
        world = rich_account
        report = generate(
            client,
            world["headers"],
            world["profile_id"],
            world["appointment_id"],
            selection=default_selection(client, world),
        )

        lines = lines_of(report, "symptoms")
        assert "Logged 2 times during this period." in lines
        assert "Severity ranged from 3/10 to 6/10." in lines
        assert "The latest entry was marked worsening." in lines
        assert "Also reported: nausea." in lines
        assert "Worse with: walking." in lines
        assert "Better with: rest." in lines

    def test_carries_uncertainty_and_denial_into_the_report(self, client, rich_account):
        """PRD 7 section 47: nothing is rewritten as definite."""
        world = rich_account
        report = generate(
            client,
            world["headers"],
            world["profile_id"],
            world["appointment_id"],
            selection=default_selection(client, world),
        )

        lines = lines_of(report, "symptoms")
        assert "Unsure about: dizziness." in lines
        assert "Said were not present: fever." in lines

    def test_only_the_selected_sections_appear(self, client, rich_account):
        """PRD 7 section 25: only selected information should appear."""
        world = rich_account
        selection = default_selection(client, world)
        selection["include"]["allergies"] = False
        selection["include"]["questions"] = False
        selection["include"]["daily_checkins"] = False

        report = generate(
            client,
            world["headers"],
            world["profile_id"],
            world["appointment_id"],
            selection=selection,
        )

        assert "Questions for the clinician" not in headings(report)
        assert "Daily check-ins" not in headings(report)
        assert "Penicillin" not in all_text(report)
        assert "tired all day" not in all_text(report)

    def test_an_unselected_symptom_is_absent(self, client, rich_account):
        """PRD 7 section 15: Nura does not choose which symptom matters."""
        world = rich_account
        selection = default_selection(client, world)
        selection["symptom_episode_ids"] = [world["headache_id"]]

        report = generate(
            client,
            world["headers"],
            world["profile_id"],
            world["appointment_id"],
            selection=selection,
        )

        text = all_text(report)
        assert "Headache" in text
        assert "Dizziness" not in text

    def test_a_selected_section_with_nothing_in_it_says_not_recorded(
        self, client, account, clock
    ):
        """PRD 7 section 46: state it or omit it, never invent it."""
        headers, profile_id = account
        appointment = create_appointment(client, headers, profile_id)

        report = generate(
            client,
            headers,
            profile_id,
            appointment["id"],
            selection={"include": {"allergies": True, "conditions": True}},
        )

        background = section(report, "background")
        assert background is not None
        titles = {item["title"]: item["lines"] for item in background["items"]}
        assert titles["Allergies"] == ["Not recorded."]
        assert titles["Conditions"] == ["Not recorded."]

    def test_a_question_is_reproduced_word_for_word(self, client, rich_account):
        """PRD 7 section 23: preserve the user's wording."""
        world = rich_account
        report = generate(
            client,
            world["headers"],
            world["profile_id"],
            world["appointment_id"],
            selection=default_selection(client, world),
        )

        assert lines_of(report, "questions") == [
            "Could this medication be contributing to my fatigue?"
        ]

    def test_adherence_is_counted_and_never_graded(self, client, rich_account):
        """PRD 7 sections 18 and 19: prefer counts, and no percentage here."""
        world = rich_account
        report = generate(
            client,
            world["headers"],
            world["profile_id"],
            world["appointment_id"],
            selection=default_selection(client, world),
        )

        lines = lines_of(report, "adherence")
        assert "0 of 1 scheduled doses were marked as taken." in lines
        assert "1 dose skipped." in lines
        assert not any("%" in line for line in lines)

    def test_the_wellbeing_counts_are_counts(self, client, rich_account):
        """PRD 7 section 20: three counts, no interpretation."""
        world = rich_account
        report = generate(
            client,
            world["headers"],
            world["profile_id"],
            world["appointment_id"],
            selection=default_selection(client, world),
        )

        lines = lines_of(report, "checkins")
        assert "Not great: 1 day." in lines
        assert any(line.startswith("Recorded on 1 of ") for line in lines)

    def test_a_skipped_doses_own_words_are_only_included_on_request(
        self, client, rich_account
    ):
        """PRD 7 section 19: not automatically."""
        world = rich_account
        selection = default_selection(client, world)
        selection["include_appendix"] = True

        without = generate(
            client,
            world["headers"],
            world["profile_id"],
            world["appointment_id"],
            selection=selection,
            client_report_id="without-notes",
        )
        assert "ran out" in all_text(without)
        assert "pharmacy was shut" not in all_text(without)

        selection["include_skip_reason_notes"] = True
        with_notes = generate(
            client,
            world["headers"],
            world["profile_id"],
            world["appointment_id"],
            selection=selection,
            client_report_id="with-notes",
        )
        assert "pharmacy was shut" in all_text(with_notes)

    def test_a_note_is_only_quoted_when_it_was_chosen(self, client, rich_account):
        """PRD 7 section 16: "selected notes"."""
        world = rich_account
        body = prepare(
            client, world["headers"], world["profile_id"], world["appointment_id"]
        )
        headache = next(
            row for row in body["symptoms"] if row["episode_id"] == world["headache_id"]
        )
        note_id = headache["notes"][0]["entry_id"]

        selection = body["default_selection"]
        quiet = generate(
            client,
            world["headers"],
            world["profile_id"],
            world["appointment_id"],
            selection=selection,
            client_report_id="quiet",
        )
        assert "worse in the mornings" not in all_text(quiet)

        selection["symptom_note_entry_ids"] = [note_id]
        quoted = generate(
            client,
            world["headers"],
            world["profile_id"],
            world["appointment_id"],
            selection=selection,
            client_report_id="quoted",
        )
        assert "worse in the mornings" in all_text(quoted)

    def test_the_users_reason_for_the_visit_is_reproduced(self, client, rich_account):
        world = rich_account
        selection = default_selection(client, world)
        selection["focus"] = "Headaches since starting the new tablet"

        report = generate(
            client,
            world["headers"],
            world["profile_id"],
            world["appointment_id"],
            selection=selection,
        )
        assert lines_of(report, "focus") == ["Headaches since starting the new tablet"]

    def test_the_period_and_its_story_are_on_the_report(self, client, rich_account):
        """PRD 7 section 14: show the selected range clearly."""
        world = rich_account
        report = generate(
            client,
            world["headers"],
            world["profile_id"],
            world["appointment_id"],
            selection=default_selection(client, world),
        )

        header_lines = report["snapshot"]["header"]["lines"]
        assert any(line.startswith("Report period: ") for line in header_lines)
        assert report["snapshot"]["period"]["preset"] == "30_days"
        assert report["snapshot"]["period"]["requested_preset"] == "since_last_visit"
        assert report["snapshot"]["period"]["note"] is not None

    def test_the_appendix_is_only_built_when_it_is_enabled(self, client, rich_account):
        """PRD 7 section 27's locked behaviour."""
        world = rich_account
        selection = default_selection(client, world)

        off = generate(
            client,
            world["headers"],
            world["profile_id"],
            world["appointment_id"],
            selection=selection,
            client_report_id="off",
        )
        assert off["snapshot"]["appendix_sections"] == []
        assert off["include_appendix"] is False

        selection["include_appendix"] = True
        on = generate(
            client,
            world["headers"],
            world["profile_id"],
            world["appointment_id"],
            selection=selection,
            client_report_id="on",
        )
        assert on["include_appendix"] is True
        assert "Appendix A — symptom timeline" in headings(on, "appendix_sections")
        assert "Appendix B — medication dose detail" in headings(on, "appendix_sections")

    def test_the_percentage_lives_in_the_appendix_with_its_period(
        self, client, rich_account
    ):
        """PRD 7 section 18: if a percentage is displayed, define the period."""
        world = rich_account
        selection = default_selection(client, world)
        selection["include_appendix"] = True

        report = generate(
            client,
            world["headers"],
            world["profile_id"],
            world["appointment_id"],
            selection=selection,
        )

        lines = lines_of(report, "adherence_detail", "appendix_sections")
        assert any(line.startswith("Period: ") for line in lines)
        assert any("% of doses in this period" in line for line in lines)

    def test_a_long_selection_tightens_the_summary_rather_than_shrinking_it(
        self, client, account, clock
    ):
        """PRD 7 section 26, in the order it gives: summarise, then appendix."""
        headers, profile_id = account
        appointment = create_appointment(client, headers, profile_id)
        episode_ids = []
        for index in range(8):
            episode = add_symptom(
                client,
                headers,
                profile_id,
                name=f"Symptom {index}",
                first_entry={
                    "recorded_at": "2026-09-25T09:00:00+00:00",
                    "severity": 5,
                    "change_state": "worsening",
                    "associated_symptoms": ["nausea", "light sensitivity"],
                    "exacerbating_factors": ["walking", "bright light"],
                    "relieving_factors": ["rest", "a dark room"],
                },
            )
            episode_ids.append(episode["id"])

        report = generate(
            client,
            headers,
            profile_id,
            appointment["id"],
            selection={"symptom_episode_ids": episode_ids, "include_appendix": True},
        )

        assert report["snapshot"]["summary_condensed"] is True
        lines = lines_of(report, "symptoms")
        # The detail moved to the appendix; the counted facts stayed.
        assert not any(line.startswith("Worse with:") for line in lines)
        assert any(line.startswith("Logged ") for line in lines)
        assert "Fuller detail follows in the appendix." in all_text(report)

    def test_a_short_report_is_not_condensed(self, client, rich_account):
        world = rich_account
        report = generate(
            client,
            world["headers"],
            world["profile_id"],
            world["appointment_id"],
            selection=default_selection(client, world),
        )
        assert report["snapshot"]["summary_condensed"] is False


# --- immutability and versions ----------------------------------------------


class TestImmutability:
    def test_a_later_edit_does_not_change_a_generated_report(
        self, client, rich_account, db
    ):
        """PRD 7 section 30, the reason a snapshot exists at all."""
        world = rich_account
        selection = default_selection(client, world)
        selection["symptom_episode_ids"] = [world["headache_id"]]
        report = generate(
            client,
            world["headers"],
            world["profile_id"],
            world["appointment_id"],
            selection=selection,
        )
        before = all_text(report)
        assert "Severity ranged from 3/10 to 6/10." in before

        entries = client.get(
            f"/api/v1/profiles/{world['profile_id']}/symptoms/"
            f"{world['headache_id']}/entries",
            headers=world["headers"],
        ).json()
        client.patch(
            f"/api/v1/profiles/{world['profile_id']}/symptoms/"
            f"{world['headache_id']}/entries/{entries[0]['id']}",
            json={"severity": 10},
            headers=world["headers"],
        )

        again = client.get(
            f"{reports_url(world['profile_id'], world['appointment_id'])}/{report['id']}",
            headers=world["headers"],
        ).json()
        assert all_text(again) == before

    def test_the_stored_pdf_is_a_function_of_the_stored_snapshot(
        self, client, rich_account, db
    ):
        """PRD 7 section 72's determinism criterion, at the byte level.

        Re-rendering an old row produces the file that was already exported, not
        a new one that merely says the same thing.
        """
        world = rich_account
        report = generate(
            client,
            world["headers"],
            world["profile_id"],
            world["appointment_id"],
            selection=default_selection(client, world),
        )

        row = db.get(AppointmentReport, uuid.UUID(report["id"]))
        assert row is not None
        service = PdfReportService(None)
        first = service.render(row.snapshot)
        second = service.render(row.snapshot)

        assert first.content == second.content
        assert first.content == stored_pdf(db, report["id"])

    def test_regenerating_makes_a_new_version_and_leaves_the_old_one_alone(
        self, client, rich_account
    ):
        """PRD 7 section 31: never silently overwrite an exported version."""
        world = rich_account
        selection = default_selection(client, world)
        first = generate(
            client,
            world["headers"],
            world["profile_id"],
            world["appointment_id"],
            selection=selection,
            client_report_id="v1",
        )

        selection["include"]["questions"] = False
        second = generate(
            client,
            world["headers"],
            world["profile_id"],
            world["appointment_id"],
            selection=selection,
            client_report_id="v2",
        )

        assert first["version"] == 1
        assert second["version"] == 2
        assert "Questions for the clinician" in headings(first)
        assert "Questions for the clinician" not in headings(second)

        listed = client.get(
            reports_url(world["profile_id"], world["appointment_id"]),
            headers=world["headers"],
        ).json()
        assert [row["version"] for row in listed] == [2, 1]

    def test_a_version_number_never_sits_between_two_others(self, client, rich_account):
        """Deleting v1 while v2 exists gives v3, not a second v1.

        Deleting the *newest* version does free its number. That is deliberate:
        the user removed that document on purpose, and every version is shown
        with the time it was generated -- which is what PRD 7 section 31's own
        example metadata does.
        """
        world = rich_account
        selection = default_selection(client, world)
        first = generate(
            client,
            world["headers"],
            world["profile_id"],
            world["appointment_id"],
            selection=selection,
            client_report_id="a",
        )
        generate(
            client,
            world["headers"],
            world["profile_id"],
            world["appointment_id"],
            selection=selection,
            client_report_id="b",
        )
        client.delete(
            f"{reports_url(world['profile_id'], world['appointment_id'])}/{first['id']}",
            headers=world["headers"],
        )

        third = generate(
            client,
            world["headers"],
            world["profile_id"],
            world["appointment_id"],
            selection=selection,
            client_report_id="c",
        )
        assert third["version"] == 3
        listed = client.get(
            reports_url(world["profile_id"], world["appointment_id"]),
            headers=world["headers"],
        ).json()
        assert [row["version"] for row in listed] == [3, 2]

    def test_a_replayed_client_id_does_not_make_a_second_version(
        self, client, rich_account
    ):
        """A double tap on Generate produces one version."""
        world = rich_account
        body = {
            "selection": default_selection(client, world),
            "client_report_id": "generate-once",
        }
        url = reports_url(world["profile_id"], world["appointment_id"])

        first = client.post(url, json=body, headers=world["headers"])
        second = client.post(url, json=body, headers=world["headers"])

        assert first.status_code == 201 and first.json()["created"] is True
        assert second.status_code == 200 and second.json()["created"] is False
        assert len(client.get(url, headers=world["headers"]).json()) == 1

    def test_too_many_versions_is_refused_rather_than_pruned(
        self, client, account, clock
    ):
        """PRD 7 section 31 forbids removing a version nobody asked to remove."""
        headers, profile_id = account
        appointment = create_appointment(client, headers, profile_id)
        url = reports_url(profile_id, appointment["id"])
        for index in range(report_service.MAX_REPORTS_PER_APPOINTMENT):
            response = client.post(
                url, json={"client_report_id": f"r{index}"}, headers=headers
            )
            assert response.status_code == 201, response.json()

        response = client.post(url, json={"client_report_id": "extra"}, headers=headers)
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "too_many_reports"

    def test_generating_marks_the_appointment_prepared(self, client, rich_account):
        """PRD 7 section 6: the status follows what exists."""
        world = rich_account
        generate(
            client,
            world["headers"],
            world["profile_id"],
            world["appointment_id"],
            selection=default_selection(client, world),
        )

        detail = client.get(
            f"{appointments_url(world['profile_id'])}/{world['appointment_id']}",
            headers=world["headers"],
        ).json()
        assert detail["preparation_status"] == "complete"
        assert detail["report_count"] == 1


# --- the document -----------------------------------------------------------


class TestPdf:
    def test_the_pdf_is_a_real_non_empty_document(self, client, rich_account):
        world = rich_account
        report = generate(
            client,
            world["headers"],
            world["profile_id"],
            world["appointment_id"],
            selection=default_selection(client, world),
        )

        response = client.get(
            f"{reports_url(world['profile_id'], world['appointment_id'])}"
            f"/{report['id']}/pdf",
            headers=world["headers"],
        )
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"
        assert response.content.startswith(b"%PDF-")
        assert len(response.content) > 500

    def test_the_summary_starts_on_page_one(self, client, rich_account):
        """PRD 7 section 66."""
        world = rich_account
        report = generate(
            client,
            world["headers"],
            world["profile_id"],
            world["appointment_id"],
            selection=default_selection(client, world),
        )
        response = client.get(
            f"{reports_url(world['profile_id'], world['appointment_id'])}"
            f"/{report['id']}/pdf",
            headers=world["headers"],
        )

        pages = pdf_text(response.content)
        assert report["page_count"] == 1
        assert "Nura Health Summary" in pages[0]
        assert "Recent symptoms" in pages[0]

    def test_the_expected_headings_are_in_the_document(self, client, rich_account):
        world = rich_account
        report = generate(
            client,
            world["headers"],
            world["profile_id"],
            world["appointment_id"],
            selection=default_selection(client, world),
        )
        text = "\n".join(
            pdf_text(
                client.get(
                    f"{reports_url(world['profile_id'], world['appointment_id'])}"
                    f"/{report['id']}/pdf",
                    headers=world["headers"],
                ).content
            )
        )

        for heading in (
            "Recent symptoms",
            "Current medications",
            "Medication doses",
            "Daily check-ins",
            "Relevant health background",
            "Questions for the clinician",
        ):
            assert heading in text

    def test_the_appendix_begins_on_its_own_page(self, client, rich_account):
        """PRD 7 section 66: the appendix appears only when enabled."""
        world = rich_account
        selection = default_selection(client, world)
        selection["include_appendix"] = True

        report = generate(
            client,
            world["headers"],
            world["profile_id"],
            world["appointment_id"],
            selection=selection,
        )
        pages = pdf_text(
            client.get(
                f"{reports_url(world['profile_id'], world['appointment_id'])}"
                f"/{report['id']}/pdf",
                headers=world["headers"],
            ).content
        )

        assert report["page_count"] == 2
        assert "Appendix A" not in pages[0]
        assert "Appendix A" in pages[1]

    def test_an_excluded_section_is_not_in_the_document(self, client, rich_account):
        world = rich_account
        selection = default_selection(client, world)
        selection["include"]["questions"] = False
        selection["symptom_episode_ids"] = [world["headache_id"]]

        report = generate(
            client,
            world["headers"],
            world["profile_id"],
            world["appointment_id"],
            selection=selection,
        )
        text = "\n".join(
            pdf_text(
                client.get(
                    f"{reports_url(world['profile_id'], world['appointment_id'])}"
                    f"/{report['id']}/pdf",
                    headers=world["headers"],
                ).content
            )
        )

        assert "Questions for the clinician" not in text
        assert "Dizziness" not in text
        assert "Headache" in text

    def test_special_characters_survive_the_standard_fonts(self, client, account, clock):
        """PRD 7 section 66.

        With no Unicode font configured the document is typeset in Helvetica,
        which covers Latin-1. Accents come through; typographic punctuation is
        folded to its ASCII equivalent; a script the font cannot draw is marked
        rather than silently dropped -- and none of it stops a report being made.
        """
        headers, profile_id = account
        appointment = create_appointment(client, headers, profile_id)
        episode = add_symptom(
            client,
            headers,
            profile_id,
            name="Café headache",
            first_entry={
                "recorded_at": "2026-09-25T09:00:00+00:00",
                "free_text_note": "worse after café — 中文 — naïve",
            },
        )
        body = prepare(client, headers, profile_id, appointment["id"])
        note_id = body["symptoms"][0]["notes"][0]["entry_id"]

        report = generate(
            client,
            headers,
            profile_id,
            appointment["id"],
            selection={
                "symptom_episode_ids": [episode["id"]],
                "symptom_note_entry_ids": [note_id],
            },
        )
        text = "\n".join(
            pdf_text(
                client.get(
                    f"{reports_url(profile_id, appointment['id'])}/{report['id']}/pdf",
                    headers=headers,
                ).content
            )
        )

        assert "Café headache" in text
        assert "naïve" in text
        # The em dashes became hyphens and the unsupported script a marker.
        assert "中文" not in text
        assert "?" in text

    def test_the_filename_says_nothing_medical(self, client, rich_account):
        """PRD 7 section 33."""
        world = rich_account
        report = generate(
            client,
            world["headers"],
            world["profile_id"],
            world["appointment_id"],
            selection=default_selection(client, world),
        )

        assert report["file_name"] == "Nura_Health_Summary_2026-09-28.pdf"
        response = client.get(
            f"{reports_url(world['profile_id'], world['appointment_id'])}"
            f"/{report['id']}/pdf",
            headers=world["headers"],
        )
        assert (
            response.headers["content-disposition"]
            == 'attachment; filename="Nura_Health_Summary_2026-09-28.pdf"'
        )
        for word in ("headache", "symptom", "cardiology", "dizziness", "metformin"):
            assert word not in report["file_name"].lower()

    def test_the_document_is_never_cached_by_anything_in_between(
        self, client, rich_account
    ):
        world = rich_account
        report = generate(
            client,
            world["headers"],
            world["profile_id"],
            world["appointment_id"],
            selection=default_selection(client, world),
        )
        response = client.get(
            f"{reports_url(world['profile_id'], world['appointment_id'])}"
            f"/{report['id']}/pdf",
            headers=world["headers"],
        )
        assert response.headers["cache-control"] == "private, no-store"

    def test_a_report_with_nothing_in_it_is_still_a_valid_document(
        self, client, account, clock
    ):
        """An appointment added before anything was recorded (s46, s69)."""
        headers, profile_id = account
        appointment = create_appointment(client, headers, profile_id)

        report = generate(client, headers, profile_id, appointment["id"])
        assert report["page_count"] == 1
        pages = pdf_text(
            client.get(
                f"{reports_url(profile_id, appointment['id'])}/{report['id']}/pdf",
                headers=headers,
            ).content
        )
        assert "Nura Health Summary" in pages[0]


# --- no diagnosis -----------------------------------------------------------


class TestNoDiagnosis:
    #: Everything PRD 7 sections 3, 18, 20 and 45 rule out. Checked against
    #: every string a report can contain, so a sentence added later cannot
    #: quietly introduce one.
    FORBIDDEN = (
        "likely diagnosis",
        "probable",
        "probably",
        "ai impression",
        "impression:",
        "suggests that",
        "consistent with",
        "caused by",
        "is causing",
        "due to the",
        "side effect of",
        "you should take",
        "you should stop",
        "we recommend",
        "recommended dose",
        "poor adherence",
        "good adherence",
        "non-compliant",
        "noncompliant",
        "at risk of",
        "deteriorating",
        "you have a",
        "you may have",
    )

    def test_no_report_contains_a_diagnosis_or_a_recommendation(
        self, client, rich_account
    ):
        world = rich_account
        selection = default_selection(client, world)
        selection["include_appendix"] = True
        selection["include_skip_reason_notes"] = True
        selection["focus"] = "Headaches since starting the new tablet"
        body = prepare(
            client, world["headers"], world["profile_id"], world["appointment_id"]
        )
        selection["symptom_note_entry_ids"] = [
            note["entry_id"] for row in body["symptoms"] for note in row["notes"]
        ]
        selection["checkin_note_dates"] = [
            note["checkin_date"] for note in body["daily_checkins"]["notes"]
        ]

        report = generate(
            client,
            world["headers"],
            world["profile_id"],
            world["appointment_id"],
            selection=selection,
        )

        text = all_text(report).lower()
        for phrase in self.FORBIDDEN:
            assert phrase not in text, phrase

    def test_every_report_carries_the_disclaimer(self, client, rich_account):
        """PRD 7 section 45, on every page of every report."""
        world = rich_account
        report = generate(
            client,
            world["headers"],
            world["profile_id"],
            world["appointment_id"],
            selection=default_selection(client, world),
        )

        assert snapshot_service.DISCLAIMER in report["snapshot"]["footer_lines"]
        pages = pdf_text(
            client.get(
                f"{reports_url(world['profile_id'], world['appointment_id'])}"
                f"/{report['id']}/pdf",
                headers=world["headers"],
            ).content
        )
        assert all("not a diagnosis" in page for page in pages)

    def test_the_user_keeps_their_own_uncertain_wording(self, client, account, clock):
        """PRD 7 section 47's own example, quoted rather than resolved."""
        headers, profile_id = account
        appointment = create_appointment(client, headers, profile_id)
        note = (
            "I’m not sure whether the dizziness started before or after the medication."
        )
        episode = add_symptom(
            client,
            headers,
            profile_id,
            name="Dizziness",
            first_entry={
                "recorded_at": "2026-09-25T09:00:00+00:00",
                "free_text_note": note,
            },
        )
        body = prepare(client, headers, profile_id, appointment["id"])
        note_id = body["symptoms"][0]["notes"][0]["entry_id"]

        report = generate(
            client,
            headers,
            profile_id,
            appointment["id"],
            selection={
                "symptom_episode_ids": [episode["id"]],
                "symptom_note_entry_ids": [note_id],
            },
        )
        assert note in all_text(report)


# --- privacy ----------------------------------------------------------------


class TestPrivacy:
    def test_no_response_carries_a_storage_key_or_a_url(self, client, rich_account):
        """PRD 7 sections 35 and 52: no public URL, and no guessable one."""
        world = rich_account
        report = generate(
            client,
            world["headers"],
            world["profile_id"],
            world["appointment_id"],
            selection=default_selection(client, world),
        )

        for blob in (
            report,
            client.get(
                reports_url(world["profile_id"], world["appointment_id"]),
                headers=world["headers"],
            ).json(),
            client.get(
                f"{appointments_url(world['profile_id'])}/{world['appointment_id']}",
                headers=world["headers"],
            ).json(),
        ):
            text = str(blob)
            assert "file_storage_key" not in text
            assert "reports/" not in text
            assert "http" not in text

    def test_another_account_cannot_read_the_document(
        self, client, rich_account, make_token
    ):
        world = rich_account
        report = generate(
            client,
            world["headers"],
            world["profile_id"],
            world["appointment_id"],
            selection=default_selection(client, world),
        )
        other = ready_account(client, make_token)
        base = (
            f"{reports_url(world['profile_id'], world['appointment_id'])}/{report['id']}"
        )

        assert client.get(base, headers=other).status_code == 404
        assert client.get(f"{base}/pdf", headers=other).status_code == 404
        assert client.delete(base, headers=other).status_code == 404
        assert client.get(f"{base}/pdf").status_code == 401

    def test_a_report_id_from_another_appointment_is_not_found(
        self, client, rich_account
    ):
        """Authorization is never by object id alone (PRD 7, section 51)."""
        world = rich_account
        report = generate(
            client,
            world["headers"],
            world["profile_id"],
            world["appointment_id"],
            selection=default_selection(client, world),
        )
        other = create_appointment(client, world["headers"], world["profile_id"])

        response = client.get(
            f"{reports_url(world['profile_id'], other['id'])}/{report['id']}",
            headers=world["headers"],
        )
        assert response.status_code == 404

    def test_deleting_a_version_removes_the_file_and_keeps_the_records(
        self, client, rich_account, db
    ):
        """PRD 7 section 65: report deletion leaves health records intact."""
        world = rich_account
        report = generate(
            client,
            world["headers"],
            world["profile_id"],
            world["appointment_id"],
            selection=default_selection(client, world),
        )
        row = db.get(AppointmentReport, uuid.UUID(report["id"]))
        assert row is not None
        key = row.file_storage_key
        assert key is not None
        assert get_object_store().get(key)

        response = client.delete(
            f"{reports_url(world['profile_id'], world['appointment_id'])}/{report['id']}",
            headers=world["headers"],
        )
        assert response.status_code == 204

        with pytest.raises(FileNotFoundError):
            get_object_store().get(key)

        profile_id = uuid.UUID(world["profile_id"])
        assert db.query(SymptomEpisode).filter_by(profile_id=profile_id).count() == 2
        assert db.query(SymptomEntry).filter_by(profile_id=profile_id).count() == 3
        assert db.query(MedicalCondition).filter_by(profile_id=profile_id).count() == 1
        assert db.query(Allergy).filter_by(profile_id=profile_id).count() == 1
        assert db.query(DailyCheckIn).filter_by(profile_id=profile_id).count() == 1

    def test_deleting_the_appointment_removes_its_documents_too(
        self, client, rich_account, db
    ):
        """A database cascade cannot reach into storage (PRD 7, section 35)."""
        world = rich_account
        report = generate(
            client,
            world["headers"],
            world["profile_id"],
            world["appointment_id"],
            selection=default_selection(client, world),
        )
        row = db.get(AppointmentReport, uuid.UUID(report["id"]))
        assert row is not None and row.file_storage_key is not None
        key = row.file_storage_key

        response = client.delete(
            f"{appointments_url(world['profile_id'])}/{world['appointment_id']}",
            headers=world["headers"],
        )
        assert response.status_code == 204

        with pytest.raises(FileNotFoundError):
            get_object_store().get(key)
        assert (
            db.query(AppointmentReport).filter_by(id=uuid.UUID(report["id"])).count() == 0
        )

    def test_a_storage_key_is_built_from_server_ids_only(self):
        """Nothing a client sends reaches the filesystem (PRD 7, section 52)."""
        profile_id = uuid.uuid4()
        appointment_id = uuid.uuid4()
        report_id = uuid.uuid4()
        key = report_service.storage_key_for(profile_id, appointment_id, report_id)

        assert key == (
            f"reports/{profile_id.hex}/{appointment_id.hex}/{report_id.hex}.pdf"
        )
        assert ".." not in key
        assert not key.startswith("/")
