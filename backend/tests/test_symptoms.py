"""Symptom episodes, entries, photos and safety-netting (PRD 6, ss86 and 91).

Every test runs against the real app, the real migrations and a real PostgreSQL
database, with a settable clock injected in place of the real one and private
media pointed at a throwaway directory.

**No hardware is involved anywhere in this file, and no speech recognition
exists.** PRD 6's conversational flow is in-app text, and the part of it that
lives on the server is the same entry-writing code the manual form uses -- which
is the point of section 4. The robot is not mentioned because nothing here has
anything to do with it (sections 5, 58 and 84).

Three groups of tests are worth finding on purpose:

``TestAuthorization`` walks the whole chain at every depth. An episode, an
entry and a photo each belong to a profile, and each is answered with 404 rather
than 403 when it does not (section 53).

``TestSafety`` asserts the things PRD 6 forbids as well as the things it asks
for: severity 10 on its own produces nothing (section 78), an uncertain or
denied red flag never fires (sections 24 and 46), and the urgent rules stay off
unless a deployment turns them on (section 44).

``TestPhotos`` proves the privacy chain end to end -- upload, authenticated
read, refusal for somebody else, and deletion that removes the bytes as well as
the row (sections 33, 35 and 63).
"""

import base64
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.api.deps import current_time
from app.main import app
from app.services.storage import InvalidStorageKeyError, get_object_store, validate_key
from app.services.symptoms import photos as photo_service
from app.services.symptoms import safety as safety_service
from tests.test_devices import ready_account
from tests.test_today import Clock

NOW = datetime(2026, 9, 27, 12, 0, tzinfo=UTC)

#: A genuine 1x1 PNG. Used wherever a test should be handling a real image.
PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFAAH/"
    "q842iQAAAABJRU5ErkJggg=="
)

#: JPEG start-of-image, padding, end-of-image. Not a decodable picture, and it
#: does not need to be: nothing in Nura decodes a symptom photo (PRD 6, s32),
#: so what matters is that the header says JPEG and the bytes come back byte for
#: byte.
JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 64 + b"\xff\xd9"

NOT_AN_IMAGE = b"This is a text file pretending to be a photograph."


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
    """A ready account and the profile its symptoms belong to."""
    headers = ready_account(client, make_token)
    profile_id = client.get("/api/v1/me", headers=headers).json()["profiles"][0]["id"]
    return headers, profile_id


def symptoms_url(profile_id: str) -> str:
    return f"/api/v1/profiles/{profile_id}/symptoms"


def create_episode(client, headers, profile_id, **body) -> dict:
    """Creates an episode and returns the stored episode body."""
    payload = {"name": "Headache", **body}
    response = client.post(symptoms_url(profile_id), json=payload, headers=headers)
    assert response.status_code == 201, response.json()
    return response.json()["episode"]


def add_entry(client, headers, profile_id, episode_id, **body) -> dict:
    response = client.post(
        f"{symptoms_url(profile_id)}/{episode_id}/entries", json=body, headers=headers
    )
    assert response.status_code in (200, 201), response.json()
    return response.json()


def upload_photo(
    client,
    headers,
    profile_id,
    episode_id,
    entry_id,
    *,
    data: bytes = PNG_BYTES,
    content_type: str = "image/png",
    filename: str = "photo.png",
    client_photo_id: str | None = None,
):
    files = {"file": (filename, data, content_type)}
    form = {} if client_photo_id is None else {"client_photo_id": client_photo_id}
    return client.post(
        f"{symptoms_url(profile_id)}/{episode_id}/entries/{entry_id}/photos",
        files=files,
        data=form,
        headers=headers,
    )


# --- episodes ---------------------------------------------------------------


class TestEpisodes:
    def test_a_manual_log_stores_the_whole_structured_description(
        self, client, account, clock
    ):
        """PRD 6 sections 11, 12 and 25: every field the flow asks about."""
        headers, profile_id = account
        episode = create_episode(
            client,
            headers,
            profile_id,
            name="Headache",
            body_site="behind both eyes",
            first_noticed_date="2026-09-26",
            first_noticed_text="this morning",
            first_entry={
                "main_symptom": "headache",
                "site": "behind both eyes",
                "onset_text": "suddenly",
                "onset_date": "2026-09-26",
                "character": "throbbing",
                "radiation": "stays in one place",
                "timing": "worse in the morning",
                "severity": 5,
                "change_state": "worsening",
                "associated_symptoms": ["nausea", "light sensitivity"],
                "exacerbating_factors": ["bright light"],
                "relieving_factors": ["lying down"],
                "free_text_note": "Started after a poor night's sleep.",
            },
        )

        assert episode["name"] == "Headache"
        assert episode["body_site"] == "behind both eyes"
        assert episode["status"] == "active"
        assert episode["first_noticed_date"] == "2026-09-26"
        assert episode["first_noticed_text"] == "this morning"
        assert episode["entry_count"] == 1

        entry = episode["latest_entry"]
        assert entry["severity"] == 5
        assert entry["character"] == "throbbing"
        assert entry["radiation"] == "stays in one place"
        assert entry["timing"] == "worse in the morning"
        assert entry["change_state"] == "worsening"
        assert entry["associated_symptoms"] == ["nausea", "light sensitivity"]
        assert entry["exacerbating_factors"] == ["bright light"]
        assert entry["relieving_factors"] == ["lying down"]
        # Both pieces of onset information survive: the wording and the day
        # (PRD 6, section 74).
        assert entry["onset_text"] == "suddenly"
        assert entry["onset_date"] == "2026-09-26"

    def test_a_name_on_its_own_is_a_valid_record(self, client, account, clock):
        """PRD 6 sections 11 and 91: incomplete descriptions must be savable."""
        headers, profile_id = account
        episode = create_episode(client, headers, profile_id, name="Feeling wobbly")

        assert episode["latest_entry"] is None
        assert episode["entry_count"] == 0
        assert episode["body_site"] is None
        assert episode["safety"]["worsening"] is False
        assert episode["safety"]["notice"] is None

    def test_an_entry_may_leave_every_optional_field_out(self, client, account, clock):
        headers, profile_id = account
        episode = create_episode(
            client, headers, profile_id, name="Nausea", first_entry={"severity": 3}
        )
        entry = episode["latest_entry"]

        # Radiation is meaningless for nausea and simply stays null, rather
        # than the flow insisting on an answer (PRD 6, section 12).
        assert entry["radiation"] is None
        assert entry["character"] is None
        assert entry["associated_symptoms"] == []

    def test_severity_outside_the_scale_is_refused(self, client, account, clock):
        headers, profile_id = account
        response = client.post(
            symptoms_url(profile_id),
            json={"name": "Headache", "first_entry": {"severity": 11}},
            headers=headers,
        )
        assert response.status_code == 422

    def test_two_onset_precisions_are_refused(self, client, account, clock):
        """PRD 6 section 15: a year stays a year, never a made-up date."""
        headers, profile_id = account
        response = client.post(
            symptoms_url(profile_id),
            json={
                "name": "Knee pain",
                "first_noticed_date": "2026-09-01",
                "first_noticed_year": 2026,
            },
            headers=headers,
        )
        assert response.status_code == 422

    def test_a_year_only_onset_is_kept_as_a_year(self, client, account, clock):
        headers, profile_id = account
        episode = create_episode(
            client, headers, profile_id, name="Knee pain", first_noticed_year=2019
        )
        assert episode["first_noticed_year"] == 2019
        assert episode["first_noticed_date"] is None
        assert episode["first_noticed_at"] is None

    def test_the_list_filters_by_active_status_and_name(self, client, account, clock):
        headers, profile_id = account
        headache = create_episode(client, headers, profile_id, name="Headache")
        knee = create_episode(client, headers, profile_id, name="Knee pain")
        client.post(f"{symptoms_url(profile_id)}/{knee['id']}/resolve", headers=headers)

        active = client.get(
            symptoms_url(profile_id), params={"active": True}, headers=headers
        ).json()
        assert [entry["id"] for entry in active] == [headache["id"]]

        resolved = client.get(
            symptoms_url(profile_id), params={"status": "resolved"}, headers=headers
        ).json()
        assert [entry["id"] for entry in resolved] == [knee["id"]]

        by_name = client.get(
            symptoms_url(profile_id), params={"name": "knee"}, headers=headers
        ).json()
        assert [entry["id"] for entry in by_name] == [knee["id"]]

    def test_an_unknown_status_filter_is_refused(self, client, account, clock):
        headers, profile_id = account
        response = client.get(
            symptoms_url(profile_id),
            params={"status": "probably_migraine"},
            headers=headers,
        )
        assert response.status_code == 422

    def test_the_episode_name_and_site_can_be_corrected(self, client, account, clock):
        headers, profile_id = account
        episode = create_episode(client, headers, profile_id, name="Headache")

        response = client.patch(
            f"{symptoms_url(profile_id)}/{episode['id']}",
            json={"name": "Pressure behind my eyes", "body_site": "forehead"},
            headers=headers,
        )
        assert response.status_code == 200
        assert response.json()["name"] == "Pressure behind my eyes"
        assert response.json()["body_site"] == "forehead"

    def test_deleting_an_episode_takes_its_entries_with_it(self, client, account, clock):
        headers, profile_id = account
        episode = create_episode(client, headers, profile_id, first_entry={"severity": 4})

        assert (
            client.delete(
                f"{symptoms_url(profile_id)}/{episode['id']}", headers=headers
            ).status_code
            == 204
        )
        assert (
            client.get(
                f"{symptoms_url(profile_id)}/{episode['id']}", headers=headers
            ).status_code
            == 404
        )


class TestResolutionAndRecurrence:
    def test_resolving_keeps_the_history_and_leaves_the_active_list(
        self, client, account, clock
    ):
        """PRD 6 sections 37 and 91."""
        headers, profile_id = account
        episode = create_episode(client, headers, profile_id, first_entry={"severity": 6})

        response = client.post(
            f"{symptoms_url(profile_id)}/{episode['id']}/resolve", headers=headers
        )
        assert response.status_code == 200
        resolved = response.json()
        assert resolved["status"] == "resolved"
        assert resolved["resolved_at"] is not None
        # Nothing was deleted.
        assert len(resolved["entries"]) == 1
        assert resolved["entries"][0]["severity"] == 6

        active = client.get(
            symptoms_url(profile_id), params={"active": True}, headers=headers
        ).json()
        assert active == []

    def test_resolving_twice_keeps_the_first_timestamp(self, client, account, clock):
        headers, profile_id = account
        episode = create_episode(client, headers, profile_id)
        url = f"{symptoms_url(profile_id)}/{episode['id']}/resolve"

        first = client.post(url, headers=headers).json()["resolved_at"]
        clock.advance(hours=3)
        second = client.post(url, headers=headers).json()["resolved_at"]

        assert first == second

    def test_a_recurrence_is_a_new_linked_episode(self, client, account, clock):
        """PRD 6 section 38: the documented model, and nothing merged."""
        headers, profile_id = account
        first = create_episode(
            client, headers, profile_id, name="Headache", first_entry={"severity": 3}
        )
        client.post(f"{symptoms_url(profile_id)}/{first['id']}/resolve", headers=headers)

        clock.advance(days=40)
        response = client.post(
            f"{symptoms_url(profile_id)}/{first['id']}/recur",
            json={
                "first_noticed_text": "last night",
                "first_entry": {"severity": 5, "change_state": "same"},
            },
            headers=headers,
        )
        assert response.status_code == 201, response.json()
        recurrence = response.json()["episode"]

        assert recurrence["id"] != first["id"]
        assert recurrence["name"] == "Headache"
        assert recurrence["status"] == "recurring"
        assert recurrence["previous_episode_id"] == first["id"]
        assert recurrence["first_noticed_text"] == "last night"
        assert recurrence["entry_count"] == 1

        # The earlier bout is untouched: still resolved, still one entry.
        earlier = client.get(
            f"{symptoms_url(profile_id)}/{first['id']}", headers=headers
        ).json()
        assert earlier["status"] == "resolved"
        assert earlier["entry_count"] == 1
        assert earlier["entries"][0]["severity"] == 3

    def test_a_recurring_episode_counts_as_active(self, client, account, clock):
        headers, profile_id = account
        first = create_episode(client, headers, profile_id)
        client.post(f"{symptoms_url(profile_id)}/{first['id']}/resolve", headers=headers)
        recurrence = client.post(
            f"{symptoms_url(profile_id)}/{first['id']}/recur", json={}, headers=headers
        ).json()["episode"]

        active = client.get(
            symptoms_url(profile_id), params={"active": True}, headers=headers
        ).json()
        assert [entry["id"] for entry in active] == [recurrence["id"]]

    def test_a_recurrence_of_an_ongoing_symptom_is_refused(self, client, account, clock):
        """An ongoing symptom wants a follow-up, not a second live episode."""
        headers, profile_id = account
        episode = create_episode(client, headers, profile_id)

        response = client.post(
            f"{symptoms_url(profile_id)}/{episode['id']}/recur",
            json={},
            headers=headers,
        )
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "symptom_episode_not_resolved"

    def test_adding_an_update_does_not_reopen_a_resolved_episode(
        self, client, account, clock
    ):
        """PRD 6 section 10: nothing infers a status change."""
        headers, profile_id = account
        episode = create_episode(client, headers, profile_id)
        client.post(
            f"{symptoms_url(profile_id)}/{episode['id']}/resolve", headers=headers
        )

        add_entry(client, headers, profile_id, episode["id"], severity=2)
        after = client.get(
            f"{symptoms_url(profile_id)}/{episode['id']}", headers=headers
        ).json()
        assert after["status"] == "resolved"


class TestEntries:
    def test_a_follow_up_carries_only_what_changed(self, client, account, clock):
        """PRD 6 sections 47 and 91: no re-entering the original description."""
        headers, profile_id = account
        episode = create_episode(
            client,
            headers,
            profile_id,
            first_entry={
                "severity": 4,
                "character": "throbbing",
                "site": "behind both eyes",
            },
        )

        clock.advance(days=1)
        saved = add_entry(
            client,
            headers,
            profile_id,
            episode["id"],
            severity=6,
            change_state="worsening",
            associated_symptoms=["nausea"],
        )

        assert saved["created"] is True
        assert saved["entry"]["severity"] == 6
        assert saved["entry"]["change_state"] == "worsening"
        # Nothing was copied forward, and nothing was demanded.
        assert saved["entry"]["character"] is None

        detail = client.get(
            f"{symptoms_url(profile_id)}/{episode['id']}", headers=headers
        ).json()
        assert detail["entry_count"] == 2
        # Newest first, and the original description is still there.
        assert [entry["severity"] for entry in detail["entries"]] == [6, 4]
        assert detail["entries"][1]["character"] == "throbbing"

    def test_the_same_client_entry_id_never_creates_two_entries(
        self, client, account, clock
    ):
        """PRD 6 section 61: an offline retry is safe."""
        headers, profile_id = account
        episode = create_episode(client, headers, profile_id)
        url = f"{symptoms_url(profile_id)}/{episode['id']}/entries"
        body = {"severity": 5, "client_entry_id": "entry-abcdef12"}

        first = client.post(url, json=body, headers=headers)
        second = client.post(url, json=body, headers=headers)

        assert first.status_code == 201
        assert first.json()["created"] is True
        assert second.status_code == 200
        assert second.json()["created"] is False
        assert second.json()["entry"]["id"] == first.json()["entry"]["id"]

        detail = client.get(
            f"{symptoms_url(profile_id)}/{episode['id']}", headers=headers
        ).json()
        assert detail["entry_count"] == 1

    def test_a_replay_does_not_overwrite_the_stored_entry(self, client, account, clock):
        """A retry is not an edit. The stored answer stands."""
        headers, profile_id = account
        episode = create_episode(client, headers, profile_id)
        url = f"{symptoms_url(profile_id)}/{episode['id']}/entries"

        client.post(
            url,
            json={"severity": 5, "client_entry_id": "entry-abcdef12"},
            headers=headers,
        )
        replay = client.post(
            url,
            json={"severity": 9, "client_entry_id": "entry-abcdef12"},
            headers=headers,
        )
        assert replay.json()["entry"]["severity"] == 5

    def test_creating_an_episode_twice_with_one_client_id_makes_one_episode(
        self, client, account, clock
    ):
        """The episode create is idempotent through its first entry's id."""
        headers, profile_id = account
        body = {
            "name": "Headache",
            "first_entry": {"severity": 4, "client_entry_id": "entry-99887766"},
        }

        first = client.post(symptoms_url(profile_id), json=body, headers=headers)
        second = client.post(symptoms_url(profile_id), json=body, headers=headers)

        assert first.status_code == 201
        assert second.status_code == 200
        assert second.json()["created"] is False
        assert second.json()["episode"]["id"] == first.json()["episode"]["id"]
        assert len(client.get(symptoms_url(profile_id), headers=headers).json()) == 1

    def test_an_entry_can_be_corrected(self, client, account, clock):
        """PRD 6 sections 30 and 67."""
        headers, profile_id = account
        episode = create_episode(client, headers, profile_id, first_entry={"severity": 8})
        entry_id = episode["latest_entry"]["id"]

        response = client.patch(
            f"{symptoms_url(profile_id)}/{episode['id']}/entries/{entry_id}",
            json={"severity": 5, "associated_symptoms": ["nausea"]},
            headers=headers,
        )
        assert response.status_code == 200
        assert response.json()["entry"]["severity"] == 5
        assert response.json()["entry"]["associated_symptoms"] == ["nausea"]

    def test_negation_and_uncertainty_survive_the_round_trip(
        self, client, account, clock
    ):
        """PRD 6 section 24: no flattening into false certainty."""
        headers, profile_id = account
        episode = create_episode(
            client,
            headers,
            profile_id,
            first_entry={
                "associated_symptoms": ["nausea"],
                "negated_items": ["vomiting"],
                "uncertain_items": ["dizziness"],
                "context_dependent_items": ["only when I stand up"],
            },
        )
        entry = episode["latest_entry"]

        assert entry["associated_symptoms"] == ["nausea"]
        assert entry["negated_items"] == ["vomiting"]
        assert entry["uncertain_items"] == ["dizziness"]
        assert entry["context_dependent_items"] == ["only when I stand up"]

    def test_duplicate_list_items_are_collapsed_keeping_the_first_spelling(
        self, client, account, clock
    ):
        headers, profile_id = account
        episode = create_episode(
            client,
            headers,
            profile_id,
            first_entry={"associated_symptoms": ["Nausea", "nausea", "  ", "fever"]},
        )
        assert episode["latest_entry"]["associated_symptoms"] == ["Nausea", "fever"]

    def test_the_guided_flow_is_recorded_as_its_own_source(self, client, account, clock):
        """PRD 6 section 57: both production sources, stored as given."""
        headers, profile_id = account
        episode = create_episode(
            client,
            headers,
            profile_id,
            source="guided_app",
            first_entry={"severity": 5, "source": "guided_app"},
        )
        assert episode["source"] == "guided_app"
        assert episode["latest_entry"]["source"] == "guided_app"

    def test_a_client_cannot_claim_a_reserved_source(self, client, account, clock):
        """A request cannot pretend to be a robot or a caregiver (s57)."""
        headers, profile_id = account
        response = client.post(
            symptoms_url(profile_id),
            json={"name": "Headache", "source": "robot_voice_future"},
            headers=headers,
        )
        assert response.status_code == 422

    def test_recorded_at_defaults_to_now_and_can_be_backdated(
        self, client, account, clock
    ):
        """An entry saved offline is about when it was made (s59)."""
        headers, profile_id = account
        episode = create_episode(client, headers, profile_id)
        earlier = (NOW - timedelta(hours=5)).isoformat()

        saved = add_entry(
            client, headers, profile_id, episode["id"], severity=4, recorded_at=earlier
        )
        stored = datetime.fromisoformat(saved["entry"]["recorded_at"])
        assert stored == NOW - timedelta(hours=5)

    def test_an_entry_can_be_deleted(self, client, account, clock):
        headers, profile_id = account
        episode = create_episode(client, headers, profile_id, first_entry={"severity": 4})
        entry_id = episode["latest_entry"]["id"]

        assert (
            client.delete(
                f"{symptoms_url(profile_id)}/{episode['id']}/entries/{entry_id}",
                headers=headers,
            ).status_code
            == 204
        )
        detail = client.get(
            f"{symptoms_url(profile_id)}/{episode['id']}", headers=headers
        ).json()
        assert detail["entry_count"] == 0


# --- photos -----------------------------------------------------------------


class TestPhotos:
    def test_a_photo_can_be_attached_and_read_back(self, client, account, clock):
        """PRD 6 sections 31 and 63, end to end."""
        headers, profile_id = account
        episode = create_episode(client, headers, profile_id, first_entry={"severity": 4})
        entry_id = episode["latest_entry"]["id"]

        upload = upload_photo(
            client, headers, profile_id, episode["id"], entry_id, data=PNG_BYTES
        )
        assert upload.status_code == 201, upload.text
        body = upload.json()
        assert body["content_type"] == "image/png"
        assert body["byte_size"] == len(PNG_BYTES)
        # Where the bytes live is never in the response (PRD 6, section 63).
        assert "storage_key" not in body

        content = client.get(
            f"{symptoms_url(profile_id)}/{episode['id']}/entries/{entry_id}"
            f"/photos/{body['id']}/content",
            headers=headers,
        )
        assert content.status_code == 200
        assert content.content == PNG_BYTES
        assert content.headers["content-type"] == "image/png"
        assert content.headers["cache-control"] == "private, no-store"

    def test_an_attached_photo_appears_on_the_entry(self, client, account, clock):
        headers, profile_id = account
        episode = create_episode(client, headers, profile_id, first_entry={"severity": 4})
        entry_id = episode["latest_entry"]["id"]
        upload_photo(client, headers, profile_id, episode["id"], entry_id)

        detail = client.get(
            f"{symptoms_url(profile_id)}/{episode['id']}", headers=headers
        ).json()
        assert len(detail["entries"][0]["photos"]) == 1

    def test_a_jpeg_is_accepted(self, client, account, clock):
        headers, profile_id = account
        episode = create_episode(client, headers, profile_id, first_entry={"severity": 4})
        response = upload_photo(
            client,
            headers,
            profile_id,
            episode["id"],
            episode["latest_entry"]["id"],
            data=JPEG_BYTES,
            content_type="image/jpeg",
            filename="photo.jpg",
        )
        assert response.status_code == 201
        assert response.json()["content_type"] == "image/jpeg"

    def test_something_that_is_not_an_image_is_refused(self, client, account, clock):
        headers, profile_id = account
        episode = create_episode(client, headers, profile_id, first_entry={"severity": 4})
        response = upload_photo(
            client,
            headers,
            profile_id,
            episode["id"],
            episode["latest_entry"]["id"],
            data=NOT_AN_IMAGE,
            content_type="image/png",
        )
        assert response.status_code == 415
        assert response.json()["detail"]["code"] == "photo_type_unsupported"

    def test_a_mislabelled_image_is_refused(self, client, account, clock):
        """The bytes decide the type, not the client (PRD 6, section 34)."""
        headers, profile_id = account
        episode = create_episode(client, headers, profile_id, first_entry={"severity": 4})
        response = upload_photo(
            client,
            headers,
            profile_id,
            episode["id"],
            episode["latest_entry"]["id"],
            data=PNG_BYTES,
            content_type="image/jpeg",
        )
        assert response.status_code == 415

    def test_a_photo_over_the_size_limit_is_refused(
        self, client, account, clock, monkeypatch
    ):
        headers, profile_id = account
        from app.core.config import get_settings

        monkeypatch.setattr(get_settings(), "max_photo_bytes", 64)
        episode = create_episode(client, headers, profile_id, first_entry={"severity": 4})
        response = upload_photo(
            client,
            headers,
            profile_id,
            episode["id"],
            episode["latest_entry"]["id"],
            data=PNG_BYTES + b"\x00" * 200,
        )
        assert response.status_code == 413
        assert response.json()["detail"]["code"] == "photo_too_large"

    def test_one_entry_cannot_hold_unlimited_photos(
        self, client, account, clock, monkeypatch
    ):
        headers, profile_id = account
        from app.core.config import get_settings

        monkeypatch.setattr(get_settings(), "max_photos_per_entry", 1)
        episode = create_episode(client, headers, profile_id, first_entry={"severity": 4})
        entry_id = episode["latest_entry"]["id"]

        assert (
            upload_photo(client, headers, profile_id, episode["id"], entry_id).status_code
            == 201
        )
        second = upload_photo(client, headers, profile_id, episode["id"], entry_id)
        assert second.status_code == 409
        assert second.json()["detail"]["code"] == "photo_limit_reached"

    def test_the_same_client_photo_id_uploads_once(self, client, account, clock):
        """PRD 6 section 61, for photos as well as entries."""
        headers, profile_id = account
        episode = create_episode(client, headers, profile_id, first_entry={"severity": 4})
        entry_id = episode["latest_entry"]["id"]

        first = upload_photo(
            client,
            headers,
            profile_id,
            episode["id"],
            entry_id,
            client_photo_id="photo-11223344",
        )
        second = upload_photo(
            client,
            headers,
            profile_id,
            episode["id"],
            entry_id,
            client_photo_id="photo-11223344",
        )
        assert first.status_code == 201
        assert second.status_code == 200
        assert second.json()["id"] == first.json()["id"]

        detail = client.get(
            f"{symptoms_url(profile_id)}/{episode['id']}", headers=headers
        ).json()
        assert len(detail["entries"][0]["photos"]) == 1

    def test_deleting_a_photo_removes_the_bytes_as_well_as_the_row(
        self, client, account, clock, db
    ):
        """PRD 6 section 35."""
        headers, profile_id = account
        episode = create_episode(client, headers, profile_id, first_entry={"severity": 4})
        entry_id = episode["latest_entry"]["id"]
        photo_id = upload_photo(
            client, headers, profile_id, episode["id"], entry_id
        ).json()["id"]

        stored_key = photo_service.get_photo(
            db, uuid.UUID(profile_id), uuid.UUID(entry_id), uuid.UUID(photo_id)
        ).storage_key
        store = get_object_store()
        assert store.get(stored_key) == PNG_BYTES

        base = (
            f"{symptoms_url(profile_id)}/{episode['id']}/entries/{entry_id}"
            f"/photos/{photo_id}"
        )
        assert client.delete(base, headers=headers).status_code == 204

        with pytest.raises(FileNotFoundError):
            store.get(stored_key)
        assert client.get(f"{base}/content", headers=headers).status_code == 404

    def test_deleting_an_entry_removes_its_stored_photos(
        self, client, account, clock, db
    ):
        headers, profile_id = account
        episode = create_episode(client, headers, profile_id, first_entry={"severity": 4})
        entry_id = episode["latest_entry"]["id"]
        photo_id = upload_photo(
            client, headers, profile_id, episode["id"], entry_id
        ).json()["id"]
        stored_key = photo_service.get_photo(
            db, uuid.UUID(profile_id), uuid.UUID(entry_id), uuid.UUID(photo_id)
        ).storage_key

        client.delete(
            f"{symptoms_url(profile_id)}/{episode['id']}/entries/{entry_id}",
            headers=headers,
        )
        with pytest.raises(FileNotFoundError):
            get_object_store().get(stored_key)

    def test_deleting_an_episode_removes_stored_photos_under_it(
        self, client, account, clock, db
    ):
        headers, profile_id = account
        episode = create_episode(client, headers, profile_id, first_entry={"severity": 4})
        entry_id = episode["latest_entry"]["id"]
        photo_id = upload_photo(
            client, headers, profile_id, episode["id"], entry_id
        ).json()["id"]
        stored_key = photo_service.get_photo(
            db, uuid.UUID(profile_id), uuid.UUID(entry_id), uuid.UUID(photo_id)
        ).storage_key

        client.delete(f"{symptoms_url(profile_id)}/{episode['id']}", headers=headers)
        with pytest.raises(FileNotFoundError):
            get_object_store().get(stored_key)

    def test_the_sniffer_recognises_the_three_accepted_formats(self):
        assert photo_service.sniff_content_type(PNG_BYTES) == "image/png"
        assert photo_service.sniff_content_type(JPEG_BYTES) == "image/jpeg"
        heic = b"\x00\x00\x00\x18ftypheic" + b"\x00" * 16
        assert photo_service.sniff_content_type(heic) == "image/heic"
        assert photo_service.sniff_content_type(NOT_AN_IMAGE) is None

    def test_a_storage_key_cannot_climb_out_of_the_media_root(self):
        """Keys are server-generated; this is what keeps that true."""
        for bad in ("../../etc/passwd", "/etc/passwd", "a/../../b", "sym\\ptom"):
            with pytest.raises(InvalidStorageKeyError):
                validate_key(bad)
        assert validate_key("symptom-photos/abc/def.png")


# --- authorization ----------------------------------------------------------


class TestAuthorization:
    """PRD 6 section 53: the whole chain, at every depth, 404 not 403."""

    @pytest.fixture
    def other(self, client, make_token) -> tuple[dict[str, str], str]:
        headers = ready_account(client, make_token)
        profile_id = client.get("/api/v1/me", headers=headers).json()["profiles"][0]["id"]
        return headers, profile_id

    def test_another_account_cannot_read_an_episode(self, client, account, other, clock):
        headers, profile_id = account
        episode = create_episode(client, headers, profile_id)
        other_headers, _ = other

        response = client.get(
            f"{symptoms_url(profile_id)}/{episode['id']}", headers=other_headers
        )
        # 404 on the profile, which is where the chain stops first.
        assert response.status_code == 404

    def test_an_episode_id_from_another_account_is_not_found(
        self, client, account, other, clock
    ):
        headers, profile_id = account
        episode = create_episode(client, headers, profile_id)
        other_headers, other_profile_id = other

        response = client.get(
            f"{symptoms_url(other_profile_id)}/{episode['id']}", headers=other_headers
        )
        assert response.status_code == 404
        assert response.json()["detail"]["code"] == "symptom_episode_not_found"

    def test_another_account_cannot_add_an_entry(self, client, account, other, clock):
        headers, profile_id = account
        episode = create_episode(client, headers, profile_id)
        other_headers, other_profile_id = other

        response = client.post(
            f"{symptoms_url(other_profile_id)}/{episode['id']}/entries",
            json={"severity": 9},
            headers=other_headers,
        )
        assert response.status_code == 404

    def test_an_entry_id_from_another_episode_is_not_found(self, client, account, clock):
        """Even within one profile, the chain has to hold."""
        headers, profile_id = account
        first = create_episode(
            client, headers, profile_id, name="Headache", first_entry={"severity": 4}
        )
        second = create_episode(client, headers, profile_id, name="Knee pain")
        entry_id = first["latest_entry"]["id"]

        response = client.patch(
            f"{symptoms_url(profile_id)}/{second['id']}/entries/{entry_id}",
            json={"severity": 1},
            headers=headers,
        )
        assert response.status_code == 404
        assert response.json()["detail"]["code"] == "symptom_entry_not_found"

    def test_another_account_cannot_read_a_photo(self, client, account, other, clock):
        """PRD 6 section 63: an unrelated account never reaches an image."""
        headers, profile_id = account
        episode = create_episode(client, headers, profile_id, first_entry={"severity": 4})
        entry_id = episode["latest_entry"]["id"]
        photo_id = upload_photo(
            client, headers, profile_id, episode["id"], entry_id
        ).json()["id"]
        other_headers, other_profile_id = other

        for path_profile, request_headers in (
            (profile_id, other_headers),
            (other_profile_id, other_headers),
        ):
            response = client.get(
                f"{symptoms_url(path_profile)}/{episode['id']}/entries/{entry_id}"
                f"/photos/{photo_id}/content",
                headers=request_headers,
            )
            assert response.status_code == 404
            assert b"PNG" not in response.content

    def test_a_signed_out_request_is_rejected(self, client, account, clock):
        headers, profile_id = account
        episode = create_episode(client, headers, profile_id)

        assert client.get(symptoms_url(profile_id)).status_code == 401
        assert (
            client.get(f"{symptoms_url(profile_id)}/{episode['id']}").status_code == 401
        )

    def test_a_photo_id_from_another_entry_is_not_found(self, client, account, clock):
        headers, profile_id = account
        episode = create_episode(client, headers, profile_id, first_entry={"severity": 4})
        entry_id = episode["latest_entry"]["id"]
        photo_id = upload_photo(
            client, headers, profile_id, episode["id"], entry_id
        ).json()["id"]

        other_entry = add_entry(client, headers, profile_id, episode["id"], severity=5)[
            "entry"
        ]["id"]
        response = client.get(
            f"{symptoms_url(profile_id)}/{episode['id']}/entries/{other_entry}"
            f"/photos/{photo_id}/content",
            headers=headers,
        )
        assert response.status_code == 404


# --- safety-netting ---------------------------------------------------------


class TestSafety:
    def test_explicit_worsening_shows_the_generic_notice(self, client, account, clock):
        """PRD 6 sections 42 and 77."""
        headers, profile_id = account
        episode = create_episode(
            client,
            headers,
            profile_id,
            first_entry={"severity": 5, "change_state": "worsening"},
        )

        safety = episode["safety"]
        assert safety["worsening"] is True
        assert safety["reasons"] == ["reported_worsening"]
        assert safety["notice"] == safety_service.WORSENING_NOTICE
        assert safety["urgent"] is False

    def test_improving_shows_nothing(self, client, account, clock):
        headers, profile_id = account
        episode = create_episode(
            client,
            headers,
            profile_id,
            first_entry={"severity": 5, "change_state": "improving"},
        )
        assert episode["safety"]["worsening"] is False
        assert episode["safety"]["notice"] is None

    def test_a_confirmed_severity_increase_counts_as_recorded_change(
        self, client, account, clock
    ):
        """PRD 6 section 41's second allowed input."""
        headers, profile_id = account
        episode = create_episode(client, headers, profile_id, first_entry={"severity": 3})
        clock.advance(days=1)
        saved = add_entry(client, headers, profile_id, episode["id"], severity=6)

        assert saved["safety"]["worsening"] is True
        assert "severity_increase" in saved["safety"]["reasons"]

    def test_a_one_point_severity_change_is_not_worsening(self, client, account, clock):
        """A self-reported scale moves by one on a bad afternoon."""
        headers, profile_id = account
        episode = create_episode(client, headers, profile_id, first_entry={"severity": 3})
        clock.advance(days=1)
        saved = add_entry(client, headers, profile_id, episode["id"], severity=4)
        assert saved["safety"]["worsening"] is False

    def test_a_new_associated_symptom_counts_as_recorded_change(
        self, client, account, clock
    ):
        """PRD 6 section 41's third allowed input."""
        headers, profile_id = account
        episode = create_episode(
            client,
            headers,
            profile_id,
            first_entry={"severity": 4, "associated_symptoms": ["nausea"]},
        )
        clock.advance(days=1)
        saved = add_entry(
            client,
            headers,
            profile_id,
            episode["id"],
            severity=4,
            associated_symptoms=["nausea", "fever"],
        )
        assert "new_associated_symptom" in saved["safety"]["reasons"]

    def test_severity_ten_on_its_own_is_not_an_emergency(self, client, account, clock):
        """PRD 6 section 78, stated as a test so it cannot quietly change."""
        headers, profile_id = account
        episode = create_episode(
            client, headers, profile_id, first_entry={"severity": 10}
        )

        assert episode["safety"]["worsening"] is False
        assert episode["safety"]["urgent"] is False
        assert episode["safety"]["notice"] is None

    def test_a_long_running_symptom_gets_a_neutral_prompt(self, client, account, clock):
        headers, profile_id = account
        episode = create_episode(client, headers, profile_id, first_entry={"severity": 4})
        clock.advance(days=safety_service.PERSISTENT_AFTER_DAYS + 1)

        detail = client.get(
            f"{symptoms_url(profile_id)}/{episode['id']}", headers=headers
        ).json()
        assert detail["safety"]["notice"] == safety_service.PERSISTENT_NOTICE
        assert detail["safety"]["worsening"] is False

    def test_the_urgent_rules_are_switched_off_by_default(self, client, account, clock):
        """PRD 6 section 44: unreviewed rules ship inert."""
        headers, profile_id = account
        episode = create_episode(
            client,
            headers,
            profile_id,
            name="Chest pain",
            first_entry={
                "main_symptom": "severe chest pain",
                "severity": 9,
                "change_state": "worsening",
            },
        )

        assert safety_service.rules_enabled() is False
        assert episode["safety"]["urgent"] is False
        # The generic worsening sentence, and nothing stronger.
        assert episode["safety"]["notice"] == safety_service.WORSENING_NOTICE

    def test_a_confirmed_red_flag_fires_when_a_deployment_enables_the_rules(
        self, client, account, clock, monkeypatch
    ):
        """The architecture works; it is the wording that is unreviewed."""
        from app.core.config import get_settings

        monkeypatch.setattr(get_settings(), "symptom_red_flag_rules_enabled", True)
        headers, profile_id = account
        episode = create_episode(
            client,
            headers,
            profile_id,
            name="Chest pain",
            first_entry={"main_symptom": "severe chest pain", "severity": 9},
        )

        assert episode["safety"]["urgent"] is True
        assert episode["safety"]["notice"] is not None
        assert "urgent medical help" in episode["safety"]["notice"]

    def test_an_uncertain_red_flag_never_fires(self, client, account, clock, monkeypatch):
        """PRD 6 section 46: no escalation from a hedged statement."""
        from app.core.config import get_settings

        monkeypatch.setattr(get_settings(), "symptom_red_flag_rules_enabled", True)
        headers, profile_id = account
        episode = create_episode(
            client,
            headers,
            profile_id,
            name="Chest discomfort",
            first_entry={
                "associated_symptoms": ["severe chest pain"],
                "uncertain_items": ["severe chest pain"],
            },
        )
        assert episode["safety"]["urgent"] is False
        assert episode["safety"]["notice"] is None

    def test_a_denied_red_flag_never_fires(self, client, account, clock, monkeypatch):
        """PRD 6 section 24: "no chest pain" is not a report of chest pain."""
        from app.core.config import get_settings

        monkeypatch.setattr(get_settings(), "symptom_red_flag_rules_enabled", True)
        headers, profile_id = account
        episode = create_episode(
            client,
            headers,
            profile_id,
            name="Indigestion",
            first_entry={
                "associated_symptoms": ["severe chest pain"],
                "negated_items": ["severe chest pain"],
            },
        )
        assert episode["safety"]["urgent"] is False

    def test_no_safety_wording_contains_a_diagnosis(self):
        """PRD 6 section 81, asserted rather than trusted.

        Every sentence Nura may show about a symptom is in one module, so this
        can check all of them at once. The list is of things a user must never
        read from Nura about their own symptoms -- a named condition, a
        likelihood, an attribution of cause, or an instruction about medication.

        Note what is *not* forbidden: "you have recorded this as worsening" is
        allowed and is the reviewed wording, because it states what the user did
        rather than what is wrong with them. The forbidden phrases are the ones
        that would turn a statement of fact into a guess about a cause.
        """
        forbidden = (
            "migraine",
            "appendicitis",
            "pneumonia",
            "infection",
            "diagnos",
            "probably",
            "likely",
            "could be",
            "sounds like",
            "you have a",
            "you have an",
            "you may have",
            "stop taking",
            "caused by",
        )
        wording = [
            safety_service.WORSENING_NOTICE,
            safety_service.PERSISTENT_NOTICE,
            safety_service.PHOTO_NOTICE,
            *(rule.message for rule in safety_service.RED_FLAG_RULES),
        ]
        for sentence in wording:
            lowered = sentence.lower()
            for word in forbidden:
                assert word not in lowered, f"{word!r} appears in {sentence!r}"

    def test_every_red_flag_term_belongs_to_a_rule(self):
        """The shared vocabulary and the rules cannot drift apart."""
        from_rules = {
            term for rule in safety_service.RED_FLAG_RULES for term in rule.terms
        }
        assert set(safety_service.RED_FLAG_TERMS) == from_rules


# --- summary, Today and Health ----------------------------------------------


class TestSummary:
    def test_the_summary_counts_and_says_nothing_else(self, client, account, clock):
        """PRD 6 section 51: no diagnosis, no risk score."""
        headers, profile_id = account
        create_episode(
            client,
            headers,
            profile_id,
            name="Headache",
            first_entry={"severity": 5, "change_state": "worsening"},
        )
        create_episode(
            client, headers, profile_id, name="Knee pain", first_entry={"severity": 3}
        )

        body = client.get(f"{symptoms_url(profile_id)}/summary", headers=headers).json()
        assert body["active_count"] == 2
        assert body["worsening_count"] == 1
        assert body["recent_updates_count"] == 2
        assert body["has_episodes"] is True
        assert set(body) == {
            "profile_id",
            "active_count",
            "worsening_count",
            "recent_updates_count",
            "has_episodes",
        }

    def test_the_summary_is_empty_and_honest_for_a_new_profile(
        self, client, account, clock
    ):
        headers, profile_id = account
        body = client.get(f"{symptoms_url(profile_id)}/summary", headers=headers).json()
        assert body["active_count"] == 0
        assert body["has_episodes"] is False

    def test_updates_count_episodes_not_entries(self, client, account, clock):
        """PRD 6 section 48: five check-ins on one headache is one symptom."""
        headers, profile_id = account
        episode = create_episode(client, headers, profile_id, first_entry={"severity": 4})
        for _ in range(4):
            clock.advance(hours=3)
            add_entry(client, headers, profile_id, episode["id"], severity=4)

        body = client.get(f"{symptoms_url(profile_id)}/summary", headers=headers).json()
        assert body["recent_updates_count"] == 1

    def test_a_resolved_episode_leaves_the_active_count(self, client, account, clock):
        headers, profile_id = account
        episode = create_episode(client, headers, profile_id)
        client.post(
            f"{symptoms_url(profile_id)}/{episode['id']}/resolve", headers=headers
        )

        body = client.get(f"{symptoms_url(profile_id)}/summary", headers=headers).json()
        assert body["active_count"] == 0
        # But the person has used the feature, so Today may still draw a card.
        assert body["has_episodes"] is True


class TestTodayIntegration:
    def test_today_carries_the_symptom_block(self, client, account, clock):
        """PRD 6 section 52."""
        headers, profile_id = account
        create_episode(
            client,
            headers,
            profile_id,
            name="Headache",
            first_entry={"severity": 5, "change_state": "worsening"},
        )

        today = client.get("/api/v1/today", headers=headers).json()
        symptoms = today["symptoms"]
        assert symptoms["active_count"] == 1
        assert symptoms["worsening_count"] == 1
        assert symptoms["has_episodes"] is True
        assert symptoms["most_recent"]["name"] == "Headache"
        assert symptoms["most_recent"]["severity"] == 5
        assert symptoms["most_recent"]["change_state"] == "worsening"

    def test_today_says_nothing_for_someone_with_no_symptoms(
        self, client, account, clock
    ):
        headers, _ = account
        today = client.get("/api/v1/today", headers=headers).json()

        assert today["symptoms"]["has_episodes"] is False
        assert today["symptoms"]["most_recent"] is None
        assert today["important"] == []

    def test_a_worsening_symptom_reaches_important_today_without_being_urgent(
        self, client, account, clock
    ):
        """PRD 6 section 40: never labelled urgent without a reviewed rule."""
        headers, profile_id = account
        create_episode(
            client,
            headers,
            profile_id,
            name="Headache",
            first_entry={"severity": 6, "change_state": "worsening"},
        )

        items = client.get("/api/v1/today", headers=headers).json()["important"]
        assert len(items) == 1
        assert items[0]["type"] == "symptom_episode"
        assert items[0]["title"] == "Headache — 6/10"
        assert items[0]["priority"] == "normal"
        assert items[0]["action_route"].startswith("/symptoms/")

    def test_a_stable_symptom_stays_out_of_important_today(self, client, account, clock):
        headers, profile_id = account
        create_episode(
            client,
            headers,
            profile_id,
            first_entry={"severity": 4, "change_state": "same"},
        )
        assert client.get("/api/v1/today", headers=headers).json()["important"] == []

    def test_the_symptoms_card_is_available_and_on_by_default(
        self, client, account, clock
    ):
        headers, _ = account
        cards = {
            card["key"]: card
            for card in client.get("/api/v1/today", headers=headers).json()["cards"]
        }
        assert cards["symptoms"]["available"] is True
        assert cards["symptoms"]["visible"] is True

    def test_the_symptoms_card_can_be_hidden(self, client, account, clock):
        headers, _ = account
        response = client.put(
            "/api/v1/dashboard-preferences",
            json={
                "cards": [
                    {"card_key": "daily_checkin", "visible": True},
                    {"card_key": "symptoms", "visible": False},
                ]
            },
            headers=headers,
        )
        assert response.status_code == 200
        cards = {card["key"]: card for card in response.json()["cards"]}
        assert cards["symptoms"]["visible"] is False


class TestHealthIntegration:
    def test_the_health_summary_counts_symptoms_separately(self, client, account, clock):
        """PRD 6 section 48: never mixed with diagnosed conditions."""
        headers, profile_id = account
        client.post(
            f"/api/v1/profiles/{profile_id}/conditions",
            json={"name": "Asthma", "status": "active"},
            headers=headers,
        )
        create_episode(
            client, headers, profile_id, name="Headache", first_entry={"severity": 5}
        )

        summary = client.get(
            f"/api/v1/profiles/{profile_id}/health-summary", headers=headers
        ).json()
        assert summary["active_conditions"] == 1
        assert summary["active_symptoms"] == 1
        assert summary["symptom_updates_this_week"] == 1

    def test_symptoms_are_not_part_of_the_completeness_figure(
        self, client, account, clock
    ):
        """Having no symptoms logged is a good state, not an incomplete one."""
        headers, profile_id = account
        before = client.get(
            f"/api/v1/profiles/{profile_id}/health-summary", headers=headers
        ).json()

        create_episode(client, headers, profile_id, first_entry={"severity": 5})

        after = client.get(
            f"/api/v1/profiles/{profile_id}/health-summary", headers=headers
        ).json()
        assert after["percent"] == before["percent"]
        assert after["total_sections"] == before["total_sections"] == 7
        assert [section["key"] for section in after["sections"]] == [
            section["key"] for section in before["sections"]
        ]
        assert "symptoms" not in [section["key"] for section in after["sections"]]
