"""Exporting one profile's data (PRD 13, sections 17-20, 43 and 49).

Three groups matter more than the rest.

``TestTableSpec`` is the one that keeps the feature honest after this PRD.
Section 18 requires an archive free of secrets and section 49 asks for a test
that proves it, and the proof is not "no secret appeared in this archive" --
that is true of any archive built from today's schema. It is that *every column
of every table has been classified*, checked against the live metadata. A
column a later PRD adds is unclassified, and unclassified fails.

``TestArchive`` opens the zip and reads it, rather than trusting what the
builder says it wrote.

``TestAuthorization`` is the cross-boundary half: another owner, a caregiver
with every permission, and an id from the wrong profile all get 404.
"""

import io
import json
import uuid
import zipfile
from datetime import UTC, datetime, timedelta

import pytest

from app.api.deps import current_time
from app.db.base import Base
from app.main import app
from app.models.privacy import EXPORT_SCHEMA_VERSION, EXPORT_TTL_HOURS
from app.services.privacy import tables as spec_module
from tests.test_devices import ready_account
from tests.test_today import Clock

NOON = datetime(2026, 10, 12, 12, 0, tzinfo=UTC)


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


@pytest.fixture
def other_account(client, make_token) -> tuple[dict[str, str], str]:
    """A second owner, for the cross-profile assertions."""
    headers = ready_account(client, make_token)
    profile_id = client.get("/api/v1/me", headers=headers).json()["profiles"][0]["id"]
    return headers, profile_id


def privacy_url(profile_id: str, path: str = "") -> str:
    return f"/api/v1/profiles/{profile_id}/privacy{path}"


def request_export(client, headers, profile_id) -> dict:
    response = client.post(privacy_url(profile_id, "/export"), headers=headers)
    assert response.status_code == 201, response.json()
    return response.json()


def download(client, headers, profile_id, export_id) -> bytes:
    response = client.get(
        privacy_url(profile_id, f"/export/{export_id}/content"), headers=headers
    )
    assert response.status_code == 200, response.text
    return response.content


def members(data: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def fill_profile(client, headers, profile_id, clock) -> None:
    """A little of everything, so the archive has something in each section."""
    client.post(
        f"/api/v1/profiles/{profile_id}/conditions",
        json={"name": "Hypertension", "status": "active"},
        headers=headers,
    )
    client.post(
        f"/api/v1/profiles/{profile_id}/medications",
        json={"name": "Ramipril", "dose": "5", "dose_unit": "mg"},
        headers=headers,
    )
    client.post(
        f"/api/v1/profiles/{profile_id}/tasks",
        json={"title": "Call the physiotherapist"},
        headers=headers,
    )
    client.put(
        "/api/v1/daily-checkins/today",
        json={"wellbeing_level": "okay", "note": "A bit tired."},
        headers=headers,
    )


class TestTableSpec:
    """Section 49's "secrets excluded", proved structurally."""

    def test_every_table_is_classified(self):
        """No table in the schema is unaccounted for.

        A table a later PRD adds has no spec and is not in
        ``UNEXPORTED_TABLES``, so this fails -- which is the point. The
        alternative is an export that silently stops covering a feature.
        """
        known = {spec.table for spec in spec_module.SPECS} | set(
            spec_module.UNEXPORTED_TABLES
        )
        assert set(Base.metadata.tables) == known

    def test_every_column_is_classified(self):
        """And no column, either.

        For each table: exported plus excluded is exactly the column set.
        A new column is on neither side, and this test names it.
        """
        for spec in spec_module.SPECS:
            columns = {c.name for c in Base.metadata.tables[spec.table].columns}
            classified = set(spec.exported) | set(spec.excluded)
            assert classified == columns, spec.table

    def test_no_column_is_both_exported_and_excluded(self):
        for spec in spec_module.SPECS:
            assert not (set(spec.exported) & set(spec.excluded)), spec.table

    def test_no_secret_is_on_the_exported_side(self):
        """Section 18, as a property of the spec rather than of one archive.

        Every column whose name says it holds a token, a secret, a hash or a
        storage key must be excluded. ``sound_key``, ``card_key``,
        ``permission_key`` and the rest are keys in the dictionary sense, so
        the check is on the four words that mean a credential or a file path.
        """
        for spec in spec_module.SPECS:
            for name in spec.exported:
                assert "token" not in name, f"{spec.table}.{name}"
                assert "secret" not in name, f"{spec.table}.{name}"
                assert "_hash" not in name, f"{spec.table}.{name}"
                assert "storage_key" not in name, f"{spec.table}.{name}"

    def test_the_known_secrets_are_all_excluded(self):
        """The list, named, so removing one from a spec fails here."""
        excluded = spec_module.excluded_columns()
        for name in (
            "invite_token_hash",
            "bootstrap_secret_hash",
            "device_token_hash",
            "token_hash",
            "storage_key",
            "file_storage_key",
            "attachment_key",
            "auth_provider_id",
        ):
            assert name in excluded, name

    def test_audit_tables_are_excluded_with_a_reason(self):
        """Section 19: an omission is stated, not inferred."""
        for table in spec_module.AUDIT_TABLES:
            assert table in spec_module.UNEXPORTED_TABLES
            assert spec_module.UNEXPORTED_TABLES[table].strip()

    def test_other_accounts_identifiers_stay_out(self):
        """An archive belongs to one person.

        A caregiver is somebody with their own account; what goes in is the
        name this user typed, not the caregiver's primary key.
        """
        relationships = spec_module.spec_for("caregiver_relationships")
        assert "caregiver_account_id" in relationships.excluded
        assert "invited_by_account_id" in relationships.excluded
        assert "invited_name" in relationships.exported

        messages = spec_module.spec_for("family_messages")
        assert "sender_account_id" in messages.excluded
        assert "sender_side" in messages.exported


class TestArchive:
    """What is actually in the zip."""

    def test_the_archive_has_a_manifest_and_every_section(self, client, account, clock):
        headers, profile_id = account
        fill_profile(client, headers, profile_id, clock)
        export = request_export(client, headers, profile_id)
        files = members(download(client, headers, profile_id, export["id"]))

        assert "manifest.json" in files
        for section in (
            "profile",
            "health",
            "medications",
            "symptoms",
            "appointments",
            "assistant",
            "caregivers",
            "safety",
            "daily-life",
            "devices",
        ):
            assert f"{section}.json" in files

    def test_the_manifest_says_what_was_left_out(self, client, account, clock):
        """Section 19, including the reason."""
        headers, profile_id = account
        export = request_export(client, headers, profile_id)
        files = members(download(client, headers, profile_id, export["id"]))
        manifest = json.loads(files["manifest.json"])

        assert manifest["profile_id"] == profile_id
        assert manifest["schema_version"] == EXPORT_SCHEMA_VERSION
        assert "audit" not in manifest["included_categories"]
        excluded = {
            row["category"]: row["reason"] for row in manifest["excluded_categories"]
        }
        assert "audit" in excluded
        assert excluded["audit"].strip()
        # The count includes the manifest itself.
        assert manifest["file_count"] == len(files)

    def test_the_manifest_carries_no_secrets(self, client, account, clock):
        """Section 19: "do not include internal secrets".

        Checked on the *keys*, not by scanning the text. The notes in the
        manifest say in plain English that no tokens or device secrets are
        included, so a substring search for "token" finds the sentence that
        promises there is none -- which is why this walks the structure
        instead.
        """
        headers, profile_id = account
        export = request_export(client, headers, profile_id)
        files = members(download(client, headers, profile_id, export["id"]))
        manifest = json.loads(files["manifest.json"])

        def keys(value, path="") -> list[str]:
            if isinstance(value, dict):
                out = []
                for key, item in value.items():
                    out.append(f"{path}.{key}")
                    out.extend(keys(item, f"{path}.{key}"))
                return out
            if isinstance(value, list):
                return [name for item in value for name in keys(item, path)]
            return []

        for name in keys(manifest):
            lowered = name.lower()
            for word in ("token", "secret", "hash", "storage_key", "password"):
                assert word not in lowered, name

        # And the only free text in it is the notes and the exclusion reasons,
        # both of which come from the wording module rather than from a row.
        assert set(manifest) == {
            "generated_at",
            "profile_id",
            "schema_version",
            "included_categories",
            "excluded_categories",
            "file_count",
            "files",
            "expires_at",
            "notes",
        }

    def test_what_the_user_recorded_is_in_it(self, client, account, clock):
        """An export that omitted the data would pass every test above."""
        headers, profile_id = account
        fill_profile(client, headers, profile_id, clock)
        export = request_export(client, headers, profile_id)
        files = members(download(client, headers, profile_id, export["id"]))

        health = json.loads(files["health.json"])
        assert [row["name"] for row in health["conditions"]] == ["Hypertension"]

        medications = json.loads(files["medications.json"])
        assert [row["name"] for row in medications["medications"]] == ["Ramipril"]

        daily_life = json.loads(files["daily-life.json"])
        assert [row["title"] for row in daily_life["tasks"]] == [
            "Call the physiotherapist"
        ]

        profile = json.loads(files["profile.json"])
        assert profile["profile"]["id"] == profile_id
        assert [row["note"] for row in profile["daily_check_ins"]] == ["A bit tired."]

    def test_the_account_row_has_no_provider_subject(self, client, account, clock):
        headers, profile_id = account
        export = request_export(client, headers, profile_id)
        files = members(download(client, headers, profile_id, export["id"]))
        account_row = json.loads(files["profile.json"])["account"]
        assert "auth_provider_id" not in account_row
        assert "id" in account_row

    def test_two_exports_of_unchanged_data_are_byte_identical(
        self, client, account, clock
    ):
        """Section 18: deterministic.

        The second export is requested after deleting the first, because one
        archive at a time is the limit. Nothing about the profile changes in
        between, so the bytes must match -- which is what makes "has my data
        changed" answerable by comparing two archives.
        """
        headers, profile_id = account
        fill_profile(client, headers, profile_id, clock)

        first = request_export(client, headers, profile_id)
        first_bytes = download(client, headers, profile_id, first["id"])
        client.delete(privacy_url(profile_id, f"/export/{first['id']}"), headers=headers)

        clock.now = NOON + timedelta(minutes=5)
        second = request_export(client, headers, profile_id)
        second_bytes = download(client, headers, profile_id, second["id"])

        # The manifest holds a generation time, so compare everything else.
        first_files = members(first_bytes)
        second_files = members(second_bytes)
        del first_files["manifest.json"], second_files["manifest.json"]
        assert first_files == second_files

    def test_a_photo_and_its_row_point_at_each_other(self, client, account, clock):
        """Media is in ``files/`` and the row says where (section 17)."""
        headers, profile_id = account
        episode = client.post(
            f"/api/v1/profiles/{profile_id}/symptoms",
            json={"name": "Headache"},
            headers=headers,
        )
        assert episode.status_code == 201, episode.json()
        episode_id = episode.json()["episode"]["id"]

        entry = client.post(
            f"/api/v1/profiles/{profile_id}/symptoms/{episode_id}/entries",
            json={"main_symptom": "Headache", "severity": 4},
            headers=headers,
        )
        assert entry.status_code in (200, 201), entry.json()
        entry_id = entry.json()["entry"]["id"]

        upload = client.post(
            f"/api/v1/profiles/{profile_id}/symptoms/{episode_id}"
            f"/entries/{entry_id}/photos",
            files={"file": ("rash.png", _png(), "image/png")},
            headers=headers,
        )
        assert upload.status_code in (200, 201), upload.text

        export = request_export(client, headers, profile_id)
        files = members(download(client, headers, profile_id, export["id"]))
        photos = json.loads(files["symptoms.json"])["photos"]
        assert len(photos) == 1
        path = photos[0]["archive_path"]
        assert path.startswith("files/photos/")
        assert path in files
        assert files[path] == _png()
        # And the internal key is not in the row.
        assert "storage_key" not in photos[0]


def _png() -> bytes:
    """The smallest valid PNG, so the upload passes type sniffing."""
    return bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
        "890000000a49444154789c63000100000500010d0a2db40000000049454e44ae"
        "426082"
    )


class TestLifecycle:
    def test_one_export_at_a_time(self, client, account, clock):
        """Section 53's repeat-export abuse case.

        The refusal names the one that exists rather than replacing it, so
        nobody loses a download part way through.
        """
        headers, profile_id = account
        request_export(client, headers, profile_id)
        second = client.post(privacy_url(profile_id, "/export"), headers=headers)
        assert second.status_code == 409
        assert second.json()["detail"]["code"] == "data_export_already_waiting"

    def test_an_expired_export_cannot_be_downloaded(self, client, account, clock):
        """Section 18: temporary, and enforced on read.

        The clock moves past the expiry and nothing else happens -- no
        maintenance run, no status change. The download is still refused,
        which is what makes the expiry a rule rather than a job.
        """
        headers, profile_id = account
        export = request_export(client, headers, profile_id)
        clock.now = NOON + timedelta(hours=EXPORT_TTL_HOURS, minutes=1)

        response = client.get(
            privacy_url(profile_id, f"/export/{export['id']}/content"), headers=headers
        )
        assert response.status_code == 410
        assert response.json()["detail"]["code"] == "data_export_expired"

    def test_an_expired_export_reads_as_expired(self, client, account, clock):
        headers, profile_id = account
        export = request_export(client, headers, profile_id)
        clock.now = NOON + timedelta(hours=EXPORT_TTL_HOURS, minutes=1)

        body = client.get(
            privacy_url(profile_id, f"/export/{export['id']}"), headers=headers
        ).json()
        assert body["status"] == "expired"
        assert body["downloadable"] is False

    def test_the_sweep_removes_the_bytes(self, client, account, clock, db):
        """Section 26, and nothing depends on it.

        The read path already refuses an expired archive; this is what stops
        the file sitting in storage. Run it and the row keeps its history with
        no key behind it.
        """
        from app.services.privacy import export as export_service
        from app.services.storage import get_object_store

        headers, profile_id = account
        export = request_export(client, headers, profile_id)
        later = NOON + timedelta(hours=EXPORT_TTL_HOURS, minutes=1)

        swept = export_service.expire_overdue(db, get_object_store(), later)
        assert swept == 1

        row = export_service.get_export(
            db, uuid.UUID(profile_id), uuid.UUID(export["id"])
        )
        assert row.status == "expired"
        assert row.file_storage_key is None

    def test_deleting_an_export_removes_the_file(self, client, account, clock, db):
        from app.services.privacy import export as export_service
        from app.services.storage import get_object_store

        headers, profile_id = account
        export = request_export(client, headers, profile_id)
        key = export_service.get_export(
            db, uuid.UUID(profile_id), uuid.UUID(export["id"])
        ).file_storage_key
        assert key is not None

        response = client.delete(
            privacy_url(profile_id, f"/export/{export['id']}"), headers=headers
        )
        assert response.status_code == 204

        with pytest.raises(FileNotFoundError):
            get_object_store().get(key)

    def test_a_second_export_is_allowed_once_the_first_is_gone(
        self, client, account, clock
    ):
        headers, profile_id = account
        first = request_export(client, headers, profile_id)
        client.delete(privacy_url(profile_id, f"/export/{first['id']}"), headers=headers)
        request_export(client, headers, profile_id)

    def test_the_list_describes_the_archive_before_it_is_asked_for(
        self, client, account, clock
    ):
        """Section 17: somebody should know what they are requesting."""
        headers, profile_id = account
        body = client.get(privacy_url(profile_id, "/export"), headers=headers).json()
        assert body["exports"] == []
        assert "no passwords" in body["secrets_note"].lower()
        assert len(body["sections"]) == 10


class TestAuthorization:
    """Section 51's export half of the cross-boundary suite."""

    def test_another_owner_cannot_read_this_export(
        self, client, account, other_account, clock
    ):
        headers, profile_id = account
        export = request_export(client, headers, profile_id)
        intruder, _ = other_account

        for path in (
            f"/export/{export['id']}",
            f"/export/{export['id']}/content",
            "/export",
            "/summary",
        ):
            response = client.get(privacy_url(profile_id, path), headers=intruder)
            assert response.status_code == 404, path

    def test_an_export_id_from_another_profile_is_not_found(
        self, client, account, other_account, clock
    ):
        """Not forbidden -- not found. PRD 1, section 54."""
        headers, profile_id = account
        other_headers, other_profile_id = other_account
        theirs = request_export(client, other_headers, other_profile_id)

        response = client.get(
            privacy_url(profile_id, f"/export/{theirs['id']}"), headers=headers
        )
        assert response.status_code == 404

    def test_an_export_holds_only_the_requested_profile(
        self, client, account, other_account, clock
    ):
        """The claim the archive makes about itself, checked.

        Both profiles record something distinctive, and the archive must hold
        exactly one of them.
        """
        headers, profile_id = account
        other_headers, other_profile_id = other_account
        client.post(
            f"/api/v1/profiles/{profile_id}/tasks",
            json={"title": "Mine alone"},
            headers=headers,
        )
        client.post(
            f"/api/v1/profiles/{other_profile_id}/tasks",
            json={"title": "Theirs alone"},
            headers=other_headers,
        )

        export = request_export(client, headers, profile_id)
        raw = download(client, headers, profile_id, export["id"])
        text = b"".join(members(raw).values()).decode()
        assert "Mine alone" in text
        assert "Theirs alone" not in text

    def test_no_export_route_answers_without_a_token(self, client, account, clock):
        _, profile_id = account
        assert client.get(privacy_url(profile_id, "/export")).status_code == 401
        assert client.post(privacy_url(profile_id, "/export")).status_code == 401
