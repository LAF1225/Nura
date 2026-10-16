"""Deleting one profile's data (PRD 13, sections 21-24 and 44).

Section 24 names seven things to verify and ``TestDeletion`` is those seven.
The one worth reading first is ``test_private_files_are_gone``: 68 foreign keys
cascade from a profile and not one of them can reach a file, so a delete that
let the database do all the work would leave every symptom photo and report PDF
on disk with no row pointing at it. PRD 14 section 56 lists that as a release
blocker, and this is the test that would catch it.

``TestConfirmation`` is section 21's "do not make this a one-tap destructive
action", checked by trying to do it in one tap.
"""

import uuid
from datetime import UTC, datetime

import pytest

from app.api.deps import current_time
from app.main import app
from app.services.privacy import deletion as deletion_service
from tests.test_devices import ready_account
from tests.test_today import Clock

NOON = datetime(2026, 10, 12, 12, 0, tzinfo=UTC)
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c63000100000500010d0a2db40000000049454e44ae"
    "426082"
)


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
    headers = ready_account(client, make_token)
    profile_id = client.get("/api/v1/me", headers=headers).json()["profiles"][0]["id"]
    return headers, profile_id


@pytest.fixture
def helper(client, make_token) -> dict[str, str]:
    """A third account, with no profile of its own, to be a caregiver."""
    return {"Authorization": f"Bearer {make_token()}"}


def privacy_url(profile_id: str, path: str = "") -> str:
    return f"/api/v1/profiles/{profile_id}/privacy{path}"


def confirm(client, headers, profile_id, **overrides) -> object:
    body = {
        "confirmation_phrase": deletion_service.CONFIRMATION_PHRASE,
        "acknowledged": True,
        **overrides,
    }
    return client.post(
        privacy_url(profile_id, "/delete-confirm"), json=body, headers=headers
    )


def fill(client, headers, profile_id) -> dict[str, str]:
    """Something in every category, so a delete has work to do."""
    ids: dict[str, str] = {}
    client.post(
        f"/api/v1/profiles/{profile_id}/conditions",
        json={"name": "Hypertension", "status": "active"},
        headers=headers,
    )
    client.post(
        f"/api/v1/profiles/{profile_id}/tasks",
        json={"title": "Call the physiotherapist"},
        headers=headers,
    )
    client.put(
        "/api/v1/daily-checkins/today",
        json={"wellbeing_level": "okay"},
        headers=headers,
    )
    episode = client.post(
        f"/api/v1/profiles/{profile_id}/symptoms",
        json={"name": "Headache", "first_entry": {"severity": 4}},
        headers=headers,
    )
    assert episode.status_code == 201, episode.json()
    ids["episode"] = episode.json()["episode"]["id"]
    ids["entry"] = episode.json()["episode"]["latest_entry"]["id"]
    photo = client.post(
        f"/api/v1/profiles/{profile_id}/symptoms/{ids['episode']}"
        f"/entries/{ids['entry']}/photos",
        files={"file": ("rash.png", PNG, "image/png")},
        headers=headers,
    )
    assert photo.status_code == 201, photo.text
    ids["photo"] = photo.json()["id"]
    return ids


def storage_keys(db, profile_id: str) -> list[str]:
    return deletion_service._storage_keys(db, uuid.UUID(profile_id))


class TestInventory:
    """Section 21's warning, and section 22's documented scope."""

    def test_the_request_step_changes_nothing(self, client, account, clock):
        headers, profile_id = account
        fill(client, headers, profile_id)

        first = client.post(privacy_url(profile_id, "/delete-request"), headers=headers)
        assert first.status_code == 200
        body = first.json()
        assert body["row_total"] > 0

        # Everything it counted is still there.
        again = client.post(privacy_url(profile_id, "/delete-request"), headers=headers)
        assert again.json()["row_total"] == body["row_total"]
        assert (
            client.get(
                f"/api/v1/profiles/{profile_id}/conditions", headers=headers
            ).status_code
            == 200
        )

    def test_it_counts_the_files_as_well_as_the_rows(self, client, account, clock):
        headers, profile_id = account
        fill(client, headers, profile_id)
        body = client.post(
            privacy_url(profile_id, "/delete-request"), headers=headers
        ).json()
        assert body["file_count"] == 1

    def test_it_hands_back_the_phrase_the_next_step_needs(self, client, account, clock):
        """Section 44, without a stored token.

        The phrase is what the second request must carry, and it is handed out
        here rather than being something a client invents.
        """
        headers, profile_id = account
        body = client.post(
            privacy_url(profile_id, "/delete-request"), headers=headers
        ).json()
        assert body["confirmation_phrase"] == deletion_service.CONFIRMATION_PHRASE
        assert body["confirm_prompt"].strip()

    def test_it_says_what_is_kept(self, client, account, clock):
        """Section 22, in the response rather than only in a document."""
        headers, profile_id = account
        body = client.post(
            privacy_url(profile_id, "/delete-request"), headers=headers
        ).json()
        assert "sign-in stays" in body["keeps"]
        assert "cannot be undone" in body["warning"]

    def test_it_names_the_re_authentication_limitation(self, client, account, clock):
        """Section 44: if re-auth is not supported, document the limitation.

        Documented on the screen as well as in the architecture notes, because
        this is the moment somebody would want to know.
        """
        headers, profile_id = account
        body = client.post(
            privacy_url(profile_id, "/delete-request"), headers=headers
        ).json()
        assert "never receives" in body["reauth_limitation"]

    def test_it_counts_only_this_accounts_other_profiles(
        self, client, account, other_account, clock
    ):
        """Another account's profile is not "your other profile".

        The number appears on a destructive confirmation screen, so it has to
        mean the caller's other person rather than every profile in the
        database.
        """
        headers, profile_id = account
        body = client.post(
            privacy_url(profile_id, "/delete-request"), headers=headers
        ).json()
        assert body["other_profile_count"] == 0


class TestConfirmation:
    """Section 21: not a one-tap destructive action."""

    def test_the_wrong_phrase_is_refused(self, client, account, clock):
        headers, profile_id = account
        response = confirm(
            client, headers, profile_id, confirmation_phrase="delete my nura data"
        )
        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "deletion_not_confirmed"
        # And nothing happened.
        assert (
            client.get(f"/api/v1/profiles/{profile_id}", headers=headers).status_code
            == 200
        )

    def test_an_unacknowledged_request_is_refused(self, client, account, clock):
        headers, profile_id = account
        response = confirm(client, headers, profile_id, acknowledged=False)
        assert response.status_code == 422
        assert (
            client.get(f"/api/v1/profiles/{profile_id}", headers=headers).status_code
            == 200
        )

    def test_an_empty_body_is_refused(self, client, account, clock):
        """Neither field has a default, so a bare retry cannot delete."""
        headers, profile_id = account
        response = client.post(
            privacy_url(profile_id, "/delete-confirm"), json={}, headers=headers
        )
        assert response.status_code == 422
        assert (
            client.get(f"/api/v1/profiles/{profile_id}", headers=headers).status_code
            == 200
        )


class TestDeletion:
    """Section 24's seven checks."""

    def test_the_profile_and_its_rows_are_gone(self, client, account, clock):
        headers, profile_id = account
        fill(client, headers, profile_id)

        response = confirm(client, headers, profile_id)
        assert response.status_code == 200, response.json()
        assert response.json()["rows_deleted"] > 0

        for path in (
            f"/api/v1/profiles/{profile_id}",
            f"/api/v1/profiles/{profile_id}/conditions",
            f"/api/v1/profiles/{profile_id}/tasks",
            f"/api/v1/profiles/{profile_id}/health-summary",
        ):
            assert client.get(path, headers=headers).status_code == 404, path

    def test_private_files_are_gone(self, client, account, clock, db):
        """The one no cascade could do.

        A photo lives in object storage; the database holds its key and
        nothing else. Reading the keys before the rows go is the whole reason
        ``ProfileDeletionService`` exists, and this is what proves it ran.
        """
        from app.services.storage import get_object_store

        headers, profile_id = account
        fill(client, headers, profile_id)
        keys = storage_keys(db, profile_id)
        assert keys, "the fixture should have stored a photo"
        store = get_object_store()
        for key in keys:
            assert store.get(key)

        body = confirm(client, headers, profile_id).json()
        assert body["files_deleted"] == len(keys)
        assert body["files_missing"] == 0

        for key in keys:
            with pytest.raises(FileNotFoundError):
                store.get(key)

    def test_an_export_archive_goes_with_it(self, client, account, clock, db):
        """Including the one artefact PRD 13 itself adds.

        An export is a complete copy of the record being deleted. Leaving it
        behind would make the delete worse than useless.
        """
        from app.services.storage import get_object_store

        headers, profile_id = account
        export = client.post(privacy_url(profile_id, "/export"), headers=headers)
        assert export.status_code == 201, export.json()
        keys = storage_keys(db, profile_id)
        assert len(keys) == 1

        confirm(client, headers, profile_id)
        with pytest.raises(FileNotFoundError):
            get_object_store().get(keys[0])

    def test_caregiver_access_is_gone(self, client, account, helper, clock):
        """Section 24: caregiver access removed.

        The relationship cascades with the profile, so the caregiver's own
        route stops answering -- not because the permission changed, but
        because there is nothing to resolve a scope against.
        """
        headers, profile_id = account
        invitation = client.post(
            f"/api/v1/profiles/{profile_id}/caregivers/invitations",
            json={"invited_name": "Ayesha", "role": "family", "permissions": {}},
            headers=headers,
        )
        assert invitation.status_code == 201, invitation.json()
        token = invitation.json()["token"]
        accept = client.post(
            f"/api/v1/caregiver-invitations/{token}/accept", headers=helper
        )
        assert accept.status_code == 200, accept.json()

        assert (
            client.get("/api/v1/caregiver/profiles", headers=helper).json()["profiles"][
                0
            ]["profile_id"]
            == profile_id
        )

        confirm(client, headers, profile_id)

        assert (
            client.get("/api/v1/caregiver/profiles", headers=helper).json()["profiles"]
            == []
        )
        assert (
            client.get(
                f"/api/v1/profiles/{profile_id}/care/home", headers=helper
            ).status_code
            == 404
        )

    def test_a_device_is_unlinked_and_still_claimed(self, client, account, clock, db):
        """Section 22's "device ownership linkage where applicable".

        Unlinked, not unclaimed. The robot on the shelf still belongs to the
        person who bought it; what goes is which profile it was set up for.
        ``owner_profile_id`` is nullable for exactly this state.
        """
        from tests.test_robot_presentations import seed_device

        headers, profile_id = account
        seed_device(db, client, headers, profile_id=profile_id)

        body = confirm(client, headers, profile_id).json()
        assert body["devices_unlinked"] == 1

        from sqlalchemy import select

        from app.models import Device

        device = db.execute(select(Device)).scalars().one()
        assert device.owner_profile_id is None
        assert device.claimed_by_account_id is not None
        assert device.setup_completed_at is None

    def test_the_assistant_stops_answering(self, client, account, clock):
        """Section 24: assistant access fails."""
        headers, profile_id = account
        assert (
            client.get(
                f"/api/v1/profiles/{profile_id}/assistant/conversations",
                headers=headers,
            ).status_code
            == 200
        )
        confirm(client, headers, profile_id)
        assert (
            client.get(
                f"/api/v1/profiles/{profile_id}/assistant/conversations",
                headers=headers,
            ).status_code
            == 404
        )

    def test_an_old_download_link_stops_working(self, client, account, clock):
        """Section 24: old links fail.

        There are no signed links in Nura -- a photo and an export are served
        through authenticated routes -- so "the link expires" is really "the
        route stops authorizing". Which is stronger, and this is it.
        """
        headers, profile_id = account
        ids = fill(client, headers, profile_id)
        path = (
            f"/api/v1/profiles/{profile_id}/symptoms/{ids['episode']}"
            f"/entries/{ids['entry']}/photos/{ids['photo']}/content"
        )
        assert client.get(path, headers=headers).status_code == 200

        confirm(client, headers, profile_id)
        assert client.get(path, headers=headers).status_code == 404

    def test_an_unrelated_profile_is_untouched(
        self, client, account, other_account, clock
    ):
        """Section 22's rule, and section 55's acceptance criterion."""
        headers, profile_id = account
        other_headers, other_profile_id = other_account
        fill(client, headers, profile_id)
        fill(client, other_headers, other_profile_id)

        confirm(client, headers, profile_id)

        assert (
            client.get(
                f"/api/v1/profiles/{other_profile_id}", headers=other_headers
            ).status_code
            == 200
        )
        conditions = client.get(
            f"/api/v1/profiles/{other_profile_id}/conditions", headers=other_headers
        )
        assert conditions.status_code == 200
        assert len(conditions.json()) == 1

    def test_the_account_survives_its_last_profile(self, client, account, clock):
        """Section 22: the sign-in is not deleted with the data.

        An account with no profile is where every new sign-up starts, and
        signing somebody out of a session whose token is valid for another hour
        is not something a delete should do.
        """
        headers, profile_id = account
        confirm(client, headers, profile_id)
        me = client.get("/api/v1/me", headers=headers)
        assert me.status_code == 200
        assert me.json()["profiles"] == []

    def test_deleting_twice_is_a_404(self, client, account, clock):
        """The second attempt has nothing to address."""
        headers, profile_id = account
        assert confirm(client, headers, profile_id).status_code == 200
        assert confirm(client, headers, profile_id).status_code == 404


class TestAuthorization:
    """Section 51's deletion half."""

    def test_another_owner_cannot_delete_this_profile(
        self, client, account, other_account, clock
    ):
        headers, profile_id = account
        intruder, _ = other_account

        assert (
            client.post(
                privacy_url(profile_id, "/delete-request"), headers=intruder
            ).status_code
            == 404
        )
        assert confirm(client, intruder, profile_id).status_code == 404
        # Still there.
        assert (
            client.get(f"/api/v1/profiles/{profile_id}", headers=headers).status_code
            == 200
        )

    def test_a_caregiver_with_every_permission_cannot_delete(
        self, client, account, helper, clock
    ):
        """The most important assertion in this file.

        A caregiver is granted every category there is and still cannot reach
        either deletion route, because both depend on ``OwnedProfile`` and a
        caregiver has no row in ``account_profile_roles``. There is no
        permission that could grant this and no code path that checks for one.
        """
        from app.models.enums import CAREGIVER_PERMISSION_KEYS

        headers, profile_id = account
        invitation = client.post(
            f"/api/v1/profiles/{profile_id}/caregivers/invitations",
            json={"invited_name": "Ayesha", "role": "family", "permissions": {}},
            headers=headers,
        )
        token = invitation.json()["token"]
        relationship_id = invitation.json()["caregiver"]["id"]
        client.post(f"/api/v1/caregiver-invitations/{token}/accept", headers=helper)
        client.patch(
            f"/api/v1/profiles/{profile_id}/caregivers/{relationship_id}/permissions",
            json={"permissions": dict.fromkeys(CAREGIVER_PERMISSION_KEYS, True)},
            headers=headers,
        )

        assert (
            client.post(
                privacy_url(profile_id, "/delete-request"), headers=helper
            ).status_code
            == 404
        )
        assert confirm(client, helper, profile_id).status_code == 404
        assert (
            client.get(f"/api/v1/profiles/{profile_id}", headers=headers).status_code
            == 200
        )

    def test_neither_route_answers_without_a_token(self, client, account, clock):
        _, profile_id = account
        assert client.post(privacy_url(profile_id, "/delete-request")).status_code == 401
        assert (
            client.post(
                privacy_url(profile_id, "/delete-confirm"),
                json={"confirmation_phrase": "x", "acknowledged": True},
            ).status_code
            == 401
        )
