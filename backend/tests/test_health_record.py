"""The health record (PRD 4, sections 50 and 58).

Two things every test here is really about:

**It belongs to the right person.** Health records hang off a profile, and a
profile is reachable only through the signed-in account's own link. Half of
this file is one account trying to reach another's records and being told the
same thing it would be told about an id that never existed.

**Nothing needs a robot.** Not one test in this file touches a device, a
heartbeat or a radio (PRD 4, section 49).
"""

import uuid

import pytest

from tests.test_devices import ready_account

# Every record type, with the payload that creates one and the field to check
# it came back. Parametrising the CRUD tests over this is what keeps the six
# resources genuinely equivalent rather than only intended to be.
RESOURCES = [
    ("conditions", {"name": "Asthma"}, "name", "Asthma"),
    ("medications", {"name": "Salbutamol"}, "name", "Salbutamol"),
    ("allergies", {"allergen": "Penicillin"}, "allergen", "Penicillin"),
    ("clinicians", {"name": "Dr Okafor"}, "name", "Dr Okafor"),
    ("procedures", {"name": "Appendectomy"}, "name", "Appendectomy"),
    (
        "medical_notes",
        {"title": "Mobility", "body": "Uses a stick outdoors."},
        "title",
        "Mobility",
    ),
]

#: The API path for a section key. Only this one differs from the key.
PATHS = {"medical_notes": "medical-notes"}


def path_for(section: str) -> str:
    return PATHS.get(section, section)


@pytest.fixture
def account(client, make_token) -> tuple[dict[str, str], str]:
    """A ready account, and the id of the profile its health records belong to."""
    headers = ready_account(client, make_token)
    profile_id = client.get("/api/v1/me", headers=headers).json()["profiles"][0]["id"]
    return headers, profile_id


def records_url(profile_id: str, section: str) -> str:
    return f"/api/v1/profiles/{profile_id}/{path_for(section)}"


# --- create, read, update, delete -------------------------------------------


@pytest.mark.parametrize(("section", "payload", "field", "value"), RESOURCES)
def test_a_record_can_be_created_read_updated_and_deleted(
    client, account, section, payload, field, value
):
    headers, profile_id = account
    url = records_url(profile_id, section)

    created = client.post(url, json=payload, headers=headers)
    assert created.status_code == 201, created.json()
    record = created.json()
    assert record[field] == value
    assert record["profile_id"] == profile_id

    listed = client.get(url, headers=headers)
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [record["id"]]

    changed = client.patch(
        f"{url}/{record['id']}", json={field: "Changed"}, headers=headers
    )
    assert changed.status_code == 200
    assert changed.json()[field] == "Changed"
    # The other fields are untouched by a PATCH that did not name them.
    assert changed.json()["id"] == record["id"]

    removed = client.delete(f"{url}/{record['id']}", headers=headers)
    assert removed.status_code == 204
    assert client.get(url, headers=headers).json() == []


@pytest.mark.parametrize(("section", "payload", "field", "value"), RESOURCES)
def test_a_record_needs_a_name(client, account, section, payload, field, value):
    headers, profile_id = account
    blank = {**payload, field: "   "}
    response = client.post(records_url(profile_id, section), json=blank, headers=headers)
    assert response.status_code == 422


@pytest.mark.parametrize(("section", "payload", "field", "value"), RESOURCES)
def test_a_missing_record_is_not_found(client, account, section, payload, field, value):
    headers, profile_id = account
    url = f"{records_url(profile_id, section)}/{uuid.uuid4()}"
    assert client.patch(url, json={}, headers=headers).status_code == 404
    assert client.delete(url, headers=headers).status_code == 404


# --- authorization ----------------------------------------------------------


@pytest.mark.parametrize(("section", "payload", "field", "value"), RESOURCES)
def test_another_account_cannot_reach_these_records(
    client, make_token, account, section, payload, field, value
):
    """PRD 4, section 25, and the acceptance criterion in section 58."""
    headers, profile_id = account
    url = records_url(profile_id, section)
    record_id = client.post(url, json=payload, headers=headers).json()["id"]

    stranger = ready_account(client, make_token)

    # 404 everywhere, not 403: the endpoint never confirms the id exists.
    assert client.get(url, headers=stranger).status_code == 404
    assert client.post(url, json=payload, headers=stranger).status_code == 404
    assert (
        client.patch(f"{url}/{record_id}", json={}, headers=stranger).status_code == 404
    )
    assert client.delete(f"{url}/{record_id}", headers=stranger).status_code == 404

    # And the owner's record is still there, untouched.
    assert len(client.get(url, headers=headers).json()) == 1


def test_health_records_need_authentication(client, account):
    _, profile_id = account
    assert client.get(records_url(profile_id, "conditions")).status_code == 401
    assert client.get(f"/api/v1/profiles/{profile_id}/health-summary").status_code == 401


def test_a_profile_that_does_not_exist_is_not_found(client, account):
    headers, _ = account
    url = records_url(str(uuid.uuid4()), "conditions")
    assert client.get(url, headers=headers).status_code == 404


# --- conditions -------------------------------------------------------------


def test_a_condition_can_record_a_year_instead_of_a_date(client, account):
    """PRD 4, section 31: "diagnosed in 2015" is a year, and stays one."""
    headers, profile_id = account
    url = records_url(profile_id, "conditions")

    created = client.post(
        url, json={"name": "Asthma", "diagnosed_year": 2015}, headers=headers
    )
    assert created.status_code == 201
    assert created.json()["diagnosed_year"] == 2015
    # Never turned into a made-up 1 January.
    assert created.json()["diagnosed_date"] is None


def test_a_condition_cannot_have_both_a_date_and_a_year(client, account):
    headers, profile_id = account
    response = client.post(
        records_url(profile_id, "conditions"),
        json={"name": "Asthma", "diagnosed_year": 2015, "diagnosed_date": "2015-06-01"},
        headers=headers,
    )
    assert response.status_code == 422


def test_an_implausible_year_is_refused(client, account):
    headers, profile_id = account
    response = client.post(
        records_url(profile_id, "conditions"),
        json={"name": "Asthma", "diagnosed_year": 205},
        headers=headers,
    )
    assert response.status_code == 422


def test_a_condition_status_must_be_one_of_the_four(client, account):
    headers, profile_id = account
    url = records_url(profile_id, "conditions")
    assert (
        client.post(
            url, json={"name": "Asthma", "status": "uncertain"}, headers=headers
        ).status_code
        == 201
    )
    assert (
        client.post(
            url, json={"name": "Asthma", "status": "probably"}, headers=headers
        ).status_code
        == 422
    )


# --- medications ------------------------------------------------------------


def test_medications_can_be_filtered_by_whether_they_are_current(client, account):
    headers, profile_id = account
    url = records_url(profile_id, "medications")

    client.post(url, json={"name": "Salbutamol"}, headers=headers)
    client.post(url, json={"name": "Amoxicillin", "is_active": False}, headers=headers)

    assert len(client.get(url, headers=headers).json()) == 2
    active = client.get(f"{url}?active=true", headers=headers).json()
    assert [item["name"] for item in active] == ["Salbutamol"]
    past = client.get(f"{url}?active=false", headers=headers).json()
    assert [item["name"] for item in past] == ["Amoxicillin"]


def test_a_medication_can_be_marked_inactive_without_being_deleted(client, account):
    """PRD 4, section 58: mark inactive is its own step, kept for history."""
    headers, profile_id = account
    url = records_url(profile_id, "medications")
    record_id = client.post(url, json={"name": "Amoxicillin"}, headers=headers).json()[
        "id"
    ]

    stopped = client.patch(
        f"{url}/{record_id}", json={"is_active": False}, headers=headers
    )
    assert stopped.status_code == 200
    assert stopped.json()["is_active"] is False
    assert len(client.get(url, headers=headers).json()) == 1


def test_a_medication_keeps_its_frequency_as_written(client, account):
    headers, profile_id = account
    created = client.post(
        records_url(profile_id, "medications"),
        json={"name": "Salbutamol", "frequency_text": "two puffs when needed"},
        headers=headers,
    )
    assert created.json()["frequency_text"] == "two puffs when needed"


def test_an_unknown_medication_form_is_refused(client, account):
    headers, profile_id = account
    response = client.post(
        records_url(profile_id, "medications"),
        json={"name": "Salbutamol", "form": "potion"},
        headers=headers,
    )
    assert response.status_code == 422


# --- allergies --------------------------------------------------------------


def test_allergy_severity_is_whatever_the_user_chose(client, account):
    """PRD 4, section 12: never inferred from the reaction text."""
    headers, profile_id = account
    created = client.post(
        records_url(profile_id, "allergies"),
        json={
            "allergen": "Penicillin",
            "allergy_type": "medication",
            "reaction": "Severe rash and swelling",
            "severity": "mild",
        },
        headers=headers,
    )
    # The word "severe" in the reaction does not promote the severity.
    assert created.json()["severity"] == "mild"


def test_an_allergy_defaults_to_an_unknown_severity(client, account):
    headers, profile_id = account
    created = client.post(
        records_url(profile_id, "allergies"),
        json={"allergen": "Pollen"},
        headers=headers,
    )
    assert created.json()["severity"] == "unknown"
    assert created.json()["allergy_type"] == "other"


# --- provenance -------------------------------------------------------------


def test_a_record_cannot_claim_a_provenance_it_does_not_have(client, account):
    """PRD 4, section 32: the server sets `source`, not the client."""
    headers, profile_id = account
    created = client.post(
        records_url(profile_id, "conditions"),
        json={"name": "Asthma", "source": "clinician_import"},
        headers=headers,
    )
    assert created.status_code == 201
    assert created.json()["source"] == "user"


# --- setup and blood type ---------------------------------------------------


def setup_url(profile_id: str) -> str:
    return f"/api/v1/profiles/{profile_id}/health-setup"


def test_health_setup_starts_at_not_started(client, account):
    headers, profile_id = account
    body = client.get(setup_url(profile_id), headers=headers).json()
    assert body == {
        "profile_id": profile_id,
        "status": "not_started",
        "step": None,
        "blood_type": None,
    }


def test_adding_any_record_marks_setup_as_under_way(client, account):
    """PRD 4, section 18: starting is something you do, not something you declare."""
    headers, profile_id = account
    client.post(
        records_url(profile_id, "conditions"), json={"name": "Asthma"}, headers=headers
    )
    assert client.get(setup_url(profile_id), headers=headers).json()["status"] == (
        "in_progress"
    )


def test_setup_progress_persists_and_can_be_resumed(client, account):
    headers, profile_id = account

    saved = client.patch(
        setup_url(profile_id),
        json={"status": "in_progress", "step": "allergies"},
        headers=headers,
    )
    assert saved.status_code == 200
    assert saved.json()["step"] == "allergies"

    # Read back on a later launch.
    assert client.get(setup_url(profile_id), headers=headers).json()["step"] == (
        "allergies"
    )

    # A PATCH that does not mention the step leaves it alone...
    client.patch(setup_url(profile_id), json={"status": "in_progress"}, headers=headers)
    assert client.get(setup_url(profile_id), headers=headers).json()["step"] == (
        "allergies"
    )

    # ...while an explicit null clears it.
    cleared = client.patch(setup_url(profile_id), json={"step": None}, headers=headers)
    assert cleared.json()["step"] is None


def test_setup_can_be_marked_complete_with_sections_still_empty(client, account):
    """PRD 4, section 17: "I have nothing to add" is a legitimate answer."""
    headers, profile_id = account
    done = client.patch(
        setup_url(profile_id), json={"status": "complete"}, headers=headers
    )
    assert done.status_code == 200
    assert done.json()["status"] == "complete"


def test_an_unknown_setup_step_is_refused(client, account):
    headers, profile_id = account
    response = client.patch(
        setup_url(profile_id), json={"step": "horoscope"}, headers=headers
    )
    assert response.status_code == 422


def test_blood_type_can_be_saved_and_changed(client, account):
    headers, profile_id = account

    saved = client.patch(
        setup_url(profile_id), json={"blood_type": "O+"}, headers=headers
    )
    assert saved.json()["blood_type"] == "O+"
    # Answering starts the health profile.
    assert saved.json()["status"] == "in_progress"

    changed = client.patch(
        setup_url(profile_id), json={"blood_type": "AB-"}, headers=headers
    )
    assert changed.json()["blood_type"] == "AB-"

    # "I'd rather not say" is an answer, and is stored as one.
    private = client.patch(
        setup_url(profile_id), json={"blood_type": "prefer_not_to_say"}, headers=headers
    )
    assert private.json()["blood_type"] == "prefer_not_to_say"


def test_an_invented_blood_type_is_refused(client, account):
    headers, profile_id = account
    response = client.patch(
        setup_url(profile_id), json={"blood_type": "Q+"}, headers=headers
    )
    assert response.status_code == 422


def test_blood_type_is_not_exposed_by_the_account_endpoint(client, account):
    """It is medical data; `/me` is not a medical endpoint."""
    headers, profile_id = account
    client.patch(setup_url(profile_id), json={"blood_type": "O+"}, headers=headers)

    profile = client.get("/api/v1/me", headers=headers).json()["profiles"][0]
    assert "blood_type" not in profile


def test_another_account_cannot_read_or_change_health_setup(client, make_token, account):
    headers, profile_id = account
    client.patch(setup_url(profile_id), json={"blood_type": "O+"}, headers=headers)

    stranger = ready_account(client, make_token)
    assert client.get(setup_url(profile_id), headers=stranger).status_code == 404
    assert (
        client.patch(
            setup_url(profile_id), json={"blood_type": "A+"}, headers=stranger
        ).status_code
        == 404
    )
    assert client.get(setup_url(profile_id), headers=headers).json()["blood_type"] == (
        "O+"
    )


# --- the summary ------------------------------------------------------------


def summary_url(profile_id: str) -> str:
    return f"/api/v1/profiles/{profile_id}/health-summary"


def test_an_empty_health_profile_summarises_as_zero(client, account):
    headers, profile_id = account
    body = client.get(summary_url(profile_id), headers=headers).json()

    assert body["percent"] == 0
    assert body["completed_sections"] == 0
    assert body["total_sections"] == 7
    assert body["active_conditions"] == 0
    assert body["active_medications"] == 0
    assert [section["key"] for section in body["sections"]] == [
        "conditions",
        "medications",
        "allergies",
        "clinicians",
        "procedures",
        "blood_type",
        "medical_notes",
    ]
    assert all(section["count"] == 0 for section in body["sections"])


def test_the_summary_counts_what_is_there(client, account):
    headers, profile_id = account

    client.post(
        records_url(profile_id, "conditions"), json={"name": "Asthma"}, headers=headers
    )
    client.post(
        records_url(profile_id, "conditions"),
        json={"name": "Old sprain", "status": "resolved"},
        headers=headers,
    )
    client.post(
        records_url(profile_id, "medications"),
        json={"name": "Salbutamol"},
        headers=headers,
    )
    client.post(
        records_url(profile_id, "medications"),
        json={"name": "Amoxicillin", "is_active": False},
        headers=headers,
    )
    client.post(
        records_url(profile_id, "allergies"),
        json={"allergen": "Penicillin"},
        headers=headers,
    )

    body = client.get(summary_url(profile_id), headers=headers).json()
    counts = {section["key"]: section["count"] for section in body["sections"]}
    assert counts["conditions"] == 2
    assert counts["medications"] == 2
    assert counts["allergies"] == 1
    assert counts["clinicians"] == 0

    # "What do you have" and "what are you dealing with now" are different
    # questions, and the summary answers both (PRD 4, section 22).
    assert body["active_conditions"] == 1
    assert body["active_medications"] == 1


def test_completeness_is_deterministic_and_equal_weight(client, account):
    """PRD 4, section 7: seven sections, each worth the same."""
    headers, profile_id = account

    assert client.get(summary_url(profile_id), headers=headers).json()["percent"] == 0

    client.post(
        records_url(profile_id, "conditions"), json={"name": "Asthma"}, headers=headers
    )
    first = client.get(summary_url(profile_id), headers=headers).json()
    assert first["completed_sections"] == 1
    assert first["percent"] == 14  # 1/7, rounded down -- never flattered

    # A second record in the *same* section does not move it.
    client.post(
        records_url(profile_id, "conditions"), json={"name": "Eczema"}, headers=headers
    )
    assert client.get(summary_url(profile_id), headers=headers).json()["percent"] == 14

    # A different section does.
    client.patch(setup_url(profile_id), json={"blood_type": "O+"}, headers=headers)
    second = client.get(summary_url(profile_id), headers=headers).json()
    assert second["completed_sections"] == 2
    assert second["percent"] == 28

    # And the same request twice gives the same answer.
    assert client.get(summary_url(profile_id), headers=headers).json() == second


def test_a_fully_filled_profile_reaches_a_hundred(client, account):
    headers, profile_id = account
    for section, payload, _field, _value in RESOURCES:
        client.post(records_url(profile_id, section), json=payload, headers=headers)
    client.patch(setup_url(profile_id), json={"blood_type": "O+"}, headers=headers)

    body = client.get(summary_url(profile_id), headers=headers).json()
    assert body["completed_sections"] == 7
    assert body["percent"] == 100


def test_the_summary_says_when_a_section_last_changed(client, account):
    headers, profile_id = account
    client.post(
        records_url(profile_id, "medical_notes"),
        json={"title": "Mobility", "body": "Uses a stick outdoors."},
        headers=headers,
    )
    body = client.get(summary_url(profile_id), headers=headers).json()
    notes = next(s for s in body["sections"] if s["key"] == "medical_notes")
    assert notes["updated_at"] is not None
    assert notes["complete"] is True


def test_the_summary_carries_no_medical_content(client, account):
    """PRD 4, sections 33 and 47: counts only, never names."""
    headers, profile_id = account
    client.post(
        records_url(profile_id, "conditions"),
        json={"name": "Hypertension"},
        headers=headers,
    )
    client.post(
        records_url(profile_id, "medications"),
        json={"name": "Amlodipine"},
        headers=headers,
    )
    client.post(
        records_url(profile_id, "allergies"),
        json={"allergen": "Penicillin"},
        headers=headers,
    )

    raw = client.get(summary_url(profile_id), headers=headers).text
    for value in ("Hypertension", "Amlodipine", "Penicillin"):
        assert value not in raw


def test_another_account_cannot_read_the_summary(client, make_token, account):
    _, profile_id = account
    stranger = ready_account(client, make_token)
    assert client.get(summary_url(profile_id), headers=stranger).status_code == 404


# --- assisted setup ---------------------------------------------------------


def test_records_belong_to_the_person_being_helped_not_the_helper(client, make_token):
    """PRD 4, section 8, in the case it exists for."""
    headers = ready_account(client, make_token, setup_mode="assisted")
    profiles = client.get("/api/v1/me", headers=headers).json()["profiles"]
    assert [profile["role"] for profile in profiles] == ["setup_helper"]

    profile_id = profiles[0]["id"]
    created = client.post(
        records_url(profile_id, "conditions"), json={"name": "Asthma"}, headers=headers
    )
    assert created.status_code == 201
    assert created.json()["profile_id"] == profile_id
