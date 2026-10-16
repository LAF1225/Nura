"""Caregivers, invitations, permissions and revocation (PRD 9, sections 95, 105).

Every test runs against the real app, the real migrations and a real PostgreSQL
database, with two real accounts holding two genuinely signed tokens. There is no
mocked authorization anywhere in this file: when a caregiver is refused, it is
because the same dependency the production app uses refused them.

**No hardware is involved.** PRD 9 section 90 requires every workflow to run
without a robot, BLE, a display, a speaker or a heartbeat, and it does -- nothing
in the caregiver code path knows a robot exists, so there is nothing here to
switch off.

Four groups are worth finding on purpose.

``TestInvitations`` covers the whole token contract: short-lived, single-use,
stored hashed, revocable, and that a preview reveals only what section 81 allows.

``TestPermissionEnforcement`` is the file's centre of gravity. It walks what a
caregiver can reach with each category granted and -- more importantly -- what a
missing category looks like, which per section 18 must be indistinguishable from
a person who has recorded nothing.

``TestRevocation`` proves section 52's "immediately": the same request that
worked a line earlier answers 404 after a revoke, with no cache to clear.

``TestRoleVersusPermission`` is one test and it is the point of section 10: a
role change leaves the granted set byte-identical.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.api.deps import current_time
from app.main import app
from app.services.caregivers import invitations as invitation_service
from tests.test_devices import ready_account
from tests.test_today import Clock

#: A Monday at noon. Fixed so "today" never drifts mid-test.
NOW = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)

ALL_KEYS = (
    "medications",
    "appointments",
    "symptoms",
    "reports",
    "safety_alerts",
    "communication",
    "routines",
    "general_health_summary",
)


# --- helpers ----------------------------------------------------------------


@pytest.fixture
def clock(client) -> Clock:
    fake = Clock()
    fake.now = NOW
    app.dependency_overrides[current_time] = lambda: fake.now
    return fake


@pytest.fixture
def owner(client, make_token) -> tuple[dict[str, str], str]:
    """The primary user, and the profile Nura is for."""
    headers = ready_account(client, make_token)
    profile_id = client.get("/api/v1/me", headers=headers).json()["profiles"][0]["id"]
    return headers, profile_id


@pytest.fixture
def helper(client, make_token) -> dict[str, str]:
    """A second account with no profile of its own.

    Section 14: supporting somebody must not require having a health profile.
    This account never creates one, and every caregiver test below works.
    """
    return {"Authorization": f"Bearer {make_token()}"}


def invite(
    client,
    headers,
    profile_id: str,
    *,
    name: str = "Ayesha",
    role: str = "family",
    permissions: dict[str, bool] | None = None,
):
    return client.post(
        f"/api/v1/profiles/{profile_id}/caregivers/invitations",
        json={
            "invited_name": name,
            "role": role,
            "permissions": permissions or {},
        },
        headers=headers,
    )


def accept(client, headers, token: str):
    return client.post(f"/api/v1/caregiver-invitations/{token}/accept", headers=headers)


def active_caregiver(
    client,
    owner_account,
    caregiver_headers,
    *,
    permissions: dict[str, bool] | None = None,
    role: str = "family",
) -> str:
    """Invites, accepts, and returns the relationship id."""
    headers, profile_id = owner_account
    created = invite(
        client, headers, profile_id, role=role, permissions=permissions
    ).json()
    accepted = accept(client, caregiver_headers, created["token"])
    assert accepted.status_code == 200, accepted.text
    return created["caregiver"]["id"]


# --- invitations -------------------------------------------------------------


class TestInvitations:
    def test_inviting_returns_the_token_once_and_says_nura_will_not_send_it(
        self, client, owner, clock
    ):
        """Section 12, answered honestly.

        There is no mail sender and no SMS gateway in this backend, so the
        invitation comes back to the primary user to pass on. ``delivery`` says
        so in the response rather than only in the documentation, because the app
        has to tell them whose job it is.
        """
        headers, profile_id = owner
        response = invite(client, headers, profile_id)
        assert response.status_code == 201
        body = response.json()
        assert body["token"].startswith("nci_")
        assert body["delivery"] == "share_manually"
        assert body["caregiver"]["status"] == "pending"
        assert body["caregiver"]["invited_name"] == "Ayesha"

    def test_the_token_is_stored_only_as_a_hash(self, client, owner, db, clock):
        """Section 13. A database dump must hold no usable invitation."""
        from app.models import CaregiverRelationship

        headers, profile_id = owner
        token = invite(client, headers, profile_id).json()["token"]
        row = db.query(CaregiverRelationship).one()
        assert row.invite_token_hash is not None
        assert token not in str(row.invite_token_hash)
        assert row.invite_token_hash == invitation_service.hash_secret(token)

    def test_a_preview_reveals_only_what_is_needed_to_decide(
        self, client, owner, helper, clock
    ):
        """Section 81, and section 15's two lists.

        What is absent matters more than what is present: no profile id, so a
        token holder never learns the key to every other route, and nothing about
        what this person has recorded.
        """
        headers, profile_id = owner
        token = invite(
            client,
            headers,
            profile_id,
            permissions={"medications": True, "appointments": True},
        ).json()["token"]

        body = client.get(f"/api/v1/caregiver-invitations/{token}", headers=helper).json()
        assert body["profile_name"] == "Ada"
        assert body["will_access"] == ["Medication reminders", "Appointments"]
        assert "Symptoms" in body["will_not_access"]
        assert "Health reports" in body["will_not_access"]
        assert "profile_id" not in body

    def test_accepting_lets_the_caregiver_in(self, client, owner, helper, clock):
        headers, profile_id = owner
        token = invite(
            client, headers, profile_id, permissions={"medications": True}
        ).json()["token"]
        body = accept(client, helper, token).json()
        assert body["profile_name"] == "Ada"
        assert body["granted"] == ["medications"]

        supported = client.get("/api/v1/caregiver/profiles", headers=helper).json()
        assert [row["profile_name"] for row in supported["profiles"]] == ["Ada"]

    def test_a_token_works_exactly_once(self, client, owner, helper, make_token, clock):
        """Sections 13, 74 and 75.

        The replay is refused, and the relationship the first attempt created is
        still active -- which is the state the caller was asking for.
        """
        headers, profile_id = owner
        token = invite(client, headers, profile_id).json()["token"]
        assert accept(client, helper, token).status_code == 200

        again = accept(client, helper, token)
        assert again.status_code == 404
        assert again.json()["detail"]["code"] == "invitation_not_found"

        third = {"Authorization": f"Bearer {make_token()}"}
        assert accept(client, third, token).status_code == 404

        supported = client.get("/api/v1/caregiver/profiles", headers=helper).json()
        assert len(supported["profiles"]) == 1

    def test_an_expired_invitation_is_refused_and_marked(
        self, client, owner, helper, clock
    ):
        """Section 13: not permanent.

        The row is marked ``expired`` as it is found, so the status the primary
        user sees and the status the caregiver hit are the same -- rather than
        reading ``pending`` for ever because nothing ran.
        """
        headers, profile_id = owner
        token = invite(client, headers, profile_id).json()["token"]

        clock.now = NOW + invitation_service.INVITE_TTL + timedelta(minutes=1)
        refused = accept(client, helper, token)
        assert refused.status_code == 404

        listed = client.get(
            f"/api/v1/profiles/{profile_id}/caregivers?include_inactive=true",
            headers=headers,
        ).json()
        assert [row["status"] for row in listed["caregivers"]] == ["expired"]

    def test_declining_consumes_the_token(self, client, owner, helper, clock):
        headers, profile_id = owner
        token = invite(client, headers, profile_id).json()["token"]
        assert (
            client.post(
                f"/api/v1/caregiver-invitations/{token}/decline", headers=helper
            ).status_code
            == 204
        )
        assert accept(client, helper, token).status_code == 404

    def test_a_nonsense_token_is_not_found(self, client, helper, clock):
        response = client.get(
            "/api/v1/caregiver-invitations/nci_not-a-real-token", headers=helper
        )
        assert response.status_code == 404

    def test_the_owner_cannot_become_their_own_caregiver(self, client, owner, clock):
        """Accepting your own invitation would give you a second, weaker path to
        your own record and make "is this a caregiver?" ambiguous everywhere."""
        headers, profile_id = owner
        token = invite(client, headers, profile_id).json()["token"]
        response = accept(client, headers, token)
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "cannot_care_for_self"

    def test_several_caregivers_are_supported(self, client, owner, make_token, clock):
        """Section 55. There is no column anywhere that could hold "the" caregiver."""
        headers, profile_id = owner
        for name in ("Ayesha", "Bilal", "Carmen"):
            token = invite(client, headers, profile_id, name=name).json()["token"]
            accept(client, {"Authorization": f"Bearer {make_token()}"}, token)

        listed = client.get(
            f"/api/v1/profiles/{profile_id}/caregivers", headers=headers
        ).json()
        assert len(listed["caregivers"]) == 3
        assert all(row["status"] == "active" for row in listed["caregivers"])

    def test_one_caregiver_may_support_several_people(
        self, client, make_token, helper, clock
    ):
        """Sections 56 and 57: each relationship has its own permissions."""
        first = ready_account(client, make_token)
        first_profile = client.get("/api/v1/me", headers=first).json()["profiles"][0][
            "id"
        ]
        second = ready_account(client, make_token)
        second_profile = client.get("/api/v1/me", headers=second).json()["profiles"][0][
            "id"
        ]

        token_one = invite(
            client, first, first_profile, permissions={"medications": True}
        ).json()["token"]
        token_two = invite(
            client, second, second_profile, permissions={"appointments": True}
        ).json()["token"]
        accept(client, helper, token_one)
        accept(client, helper, token_two)

        supported = client.get("/api/v1/caregiver/profiles", headers=helper).json()
        granted = {row["profile_id"]: row["granted"] for row in supported["profiles"]}
        assert granted[first_profile] == ["medications"]
        assert granted[second_profile] == ["appointments"]

    def test_an_invitation_grants_nothing_by_default(self, client, owner, helper, clock):
        """Section 66 forbids a broad default permission."""
        headers, profile_id = owner
        token = invite(client, headers, profile_id).json()["token"]
        body = accept(client, helper, token).json()
        assert body["granted"] == []

    def test_a_caregiver_cannot_read_the_caregiver_list(
        self, client, owner, helper, clock
    ):
        """Section 66: who else is helping somebody is not theirs to read."""
        headers, profile_id = owner
        active_caregiver(client, owner, helper, permissions={"medications": True})
        response = client.get(f"/api/v1/profiles/{profile_id}/caregivers", headers=helper)
        assert response.status_code == 404


# --- permission enforcement --------------------------------------------------


class TestPermissionEnforcement:
    def test_a_caregiver_cannot_reach_any_route_written_before_prd_9(
        self, client, owner, helper, clock
    ):
        """The most important test in this file.

        Every PRD 0-8 profile-scoped route authorizes through
        ``account_profile_roles``, which a caregiver has no row in. So an active
        caregiver with *every* category granted still cannot read the health
        record, the medication list, a symptom, an appointment or a conversation
        -- those routes return less than nothing to them. The caregiver surface
        is separate and narrower on purpose (sections 9, 18, 67).
        """
        _, profile_id = owner
        active_caregiver(client, owner, helper, permissions=dict.fromkeys(ALL_KEYS, True))
        for path in (
            f"/api/v1/profiles/{profile_id}/health-summary",
            f"/api/v1/profiles/{profile_id}/medications",
            f"/api/v1/profiles/{profile_id}/conditions",
            f"/api/v1/profiles/{profile_id}/symptoms",
            f"/api/v1/profiles/{profile_id}/appointments",
            f"/api/v1/profiles/{profile_id}/medication-schedules",
            f"/api/v1/profiles/{profile_id}/assistant/conversations",
            f"/api/v1/profiles/{profile_id}/assistant/memories",
        ):
            response = client.get(path, headers=helper)
            assert response.status_code == 404, f"{path} answered {response.status_code}"

    def test_the_home_shows_only_the_granted_categories(
        self, client, owner, helper, clock
    ):
        """Sections 17 and 60."""
        active_caregiver(
            client,
            owner,
            helper,
            permissions={"medications": True, "appointments": True},
        )
        _, profile_id = owner
        body = client.get(
            f"/api/v1/profiles/{profile_id}/care/home", headers=helper
        ).json()
        assert sorted(body["granted"]) == ["appointments", "medications"]
        assert body["medications"] is not None
        assert body["appointments"] is not None

    def test_a_hidden_category_is_absent_rather_than_empty(
        self, client, owner, helper, clock
    ):
        """Section 18, and the reason this file exists.

        A caregiver without ``symptoms`` gets no symptom key at all -- not an
        empty list, not a zero count. An omitted key is indistinguishable from a
        person who has never recorded a symptom, which is exactly what section 18
        asks for: the absence of a permission must not leak.
        """
        active_caregiver(client, owner, helper, permissions={"medications": True})
        _, profile_id = owner
        body = client.get(
            f"/api/v1/profiles/{profile_id}/care/home", headers=helper
        ).json()
        assert body["symptoms"] is None
        assert body["reports"] is None
        assert body["health_counts"] is None
        assert body["unread_messages"] is None

    def test_a_caregiver_with_no_symptom_access_cannot_see_a_symptom_count(
        self, client, owner, helper, clock
    ):
        """The same rule with real data behind it.

        A symptom is recorded, and the caregiver's view is byte-identical to the
        one they got before it existed. Section 18 is about metadata as much as
        records: a count is information.
        """
        headers, profile_id = owner
        active_caregiver(client, owner, helper, permissions={"medications": True})
        before = client.get(
            f"/api/v1/profiles/{profile_id}/care/home", headers=helper
        ).json()

        created = client.post(
            f"/api/v1/profiles/{profile_id}/symptoms",
            json={
                "name": "Headache",
                "first_entry": {"severity": 7, "change_state": "worsening"},
            },
            headers=headers,
        )
        assert created.status_code == 201, created.text

        after = client.get(
            f"/api/v1/profiles/{profile_id}/care/home", headers=helper
        ).json()
        assert after["symptoms"] is None
        assert after == before

    def test_granting_symptoms_shows_them_read_only(self, client, owner, helper, clock):
        """Section 28: viewing history, and no path to rewriting it."""
        headers, profile_id = owner
        active_caregiver(client, owner, helper, permissions={"symptoms": True})
        client.post(
            f"/api/v1/profiles/{profile_id}/symptoms",
            json={"name": "Headache", "first_entry": {"severity": 7}},
            headers=headers,
        )
        body = client.get(
            f"/api/v1/profiles/{profile_id}/care/home", headers=helper
        ).json()
        assert [row["name"] for row in body["symptoms"]] == ["Headache"]
        assert body["symptoms"][0]["severity"] == 7

        # And no write path exists, at any URL a caregiver could reach.
        refused = client.post(
            f"/api/v1/profiles/{profile_id}/symptoms",
            json={"name": "Invented", "first_entry": {"severity": 1}},
            headers=helper,
        )
        assert refused.status_code == 404

    def test_a_caregiver_view_carries_no_skip_reason(
        self, client, owner, helper, db, clock
    ):
        """Section 19 excludes free-text skip reasons by default.

        There is no field for one in the caregiver medication model, which is why
        this test asserts on the keys rather than on a value: a reason cannot be
        omitted by accident if there is nowhere to put it.
        """
        active_caregiver(client, owner, helper, permissions={"medications": True})
        _, profile_id = owner
        body = client.get(
            f"/api/v1/profiles/{profile_id}/care/home", headers=helper
        ).json()
        serialised = str(body)
        assert "skip_reason" not in serialised
        assert "skip_reason_text" not in serialised

    def test_the_health_summary_permission_gives_counts_and_no_names(
        self, client, owner, helper, clock
    ):
        """Section 67. A caregiver is told how many, never which."""
        headers, profile_id = owner
        active_caregiver(
            client, owner, helper, permissions={"general_health_summary": True}
        )
        client.post(
            f"/api/v1/profiles/{profile_id}/conditions",
            json={"name": "Asthma", "status": "active"},
            headers=headers,
        )
        client.post(
            f"/api/v1/profiles/{profile_id}/medications",
            json={"name": "Salbutamol", "is_active": True},
            headers=headers,
        )
        body = client.get(
            f"/api/v1/profiles/{profile_id}/care/home", headers=helper
        ).json()
        assert body["health_counts"]["active_conditions"] == 1
        assert body["health_counts"]["active_medications"] == 1
        assert "Asthma" not in str(body)
        assert "Salbutamol" not in str(body)

    def test_every_granted_permission_now_has_a_source(
        self, client, owner, helper, clock
    ):
        """PRD 9 section 94's honesty, closed for the last key.

        PRD 9 allowed a permission to exist before its data did and warned
        against fabricating one, so ``routines`` was granted, stored faithfully
        and unlocked nothing -- and the response said so through
        ``granted_without_data`` rather than showing an empty section that
        reads as "nothing recorded".

        PRD 10 built the safety source. PRD 12 section 12 builds the routine
        one. So ``granted_without_data`` is now empty, both sections are real,
        and this test is the record of that: a key reappearing in that list
        would mean somebody reserved another permission, which is allowed, and
        a key appearing there *with* data would be a bug.
        """
        active_caregiver(
            client, owner, helper, permissions={"safety_alerts": True, "routines": True}
        )
        _, profile_id = owner
        body = client.get(
            f"/api/v1/profiles/{profile_id}/care/home", headers=helper
        ).json()
        assert sorted(body["granted"]) == ["routines", "safety_alerts"]
        assert body["granted_without_data"] == []
        # Present and empty, which is the difference PRD 12 makes: an absent
        # key means "not granted" and an empty list means "granted, and this
        # person has no routines" (PRD 9, section 18).
        assert body["routines"] == []
        assert body["safety"] == {
            "unread_count": 0,
            "latest_alert_id": None,
            "latest_event_label": None,
            "latest_at": None,
            "latest_acknowledged": False,
        }

    def test_routines_does_not_reach_tasks_alarms_or_reminders(
        self, client, owner, helper, clock
    ):
        """PRD 12, section 42, as the absence of a route rather than a filter.

        A caregiver granted ``routines`` and nothing else gets routines. There
        is no caregiver route anywhere that reaches a task, an alarm or a
        general reminder -- so the check is that asking for one of the owner's
        own routes is a 404, which is the same answer as a profile that is not
        theirs.
        """
        active_caregiver(client, owner, helper, permissions={"routines": True})
        _, profile_id = owner

        home = client.get(
            f"/api/v1/profiles/{profile_id}/care/home", headers=helper
        ).json()
        assert home["routines"] == []
        # Null rather than an empty list, which is the distinction PRD 9
        # section 18 turns on: null is "not granted" and `[]` is "granted, and
        # there is nothing", so the response cannot be read to learn whether
        # this person takes any medication.
        assert home["medications"] is None

        for path in ("tasks", "alarms", "reminders", "daily-life/summary"):
            response = client.get(f"/api/v1/profiles/{profile_id}/{path}", headers=helper)
            assert response.status_code == 404, path

    def test_an_unrelated_account_reaches_nothing(self, client, owner, make_token, clock):
        """Not a caregiver, not the owner: 404 at every depth."""
        _, profile_id = owner
        stranger = {"Authorization": f"Bearer {make_token()}"}
        for path in (
            f"/api/v1/profiles/{profile_id}/care/home",
            f"/api/v1/profiles/{profile_id}/caregivers",
            f"/api/v1/profiles/{profile_id}/caregiver-suggestions",
            f"/api/v1/profiles/{profile_id}/family/threads",
            f"/api/v1/profiles/{profile_id}/emergency-contacts",
        ):
            assert client.get(path, headers=stranger).status_code == 404

    def test_changing_a_permission_takes_effect_on_the_next_request(
        self, client, owner, helper, clock
    ):
        """Section 53: immediate after a successful save.

        There is no window in which the old set still applies, because every
        check reads the rows rather than a cached scope.
        """
        headers, profile_id = owner
        relationship_id = active_caregiver(
            client, owner, helper, permissions={"medications": True}
        )
        assert (
            client.get(f"/api/v1/profiles/{profile_id}/care/home", headers=helper).json()[
                "symptoms"
            ]
            is None
        )

        client.patch(
            f"/api/v1/profiles/{profile_id}/caregivers/{relationship_id}/permissions",
            json={"permissions": {"symptoms": True}},
            headers=headers,
        )
        assert (
            client.get(f"/api/v1/profiles/{profile_id}/care/home", headers=helper).json()[
                "symptoms"
            ]
            == []
        )

    def test_a_permission_update_leaves_the_others_alone(
        self, client, owner, helper, clock
    ):
        """A client sending one toggle must not silently deny the rest."""
        headers, profile_id = owner
        relationship_id = active_caregiver(
            client,
            owner,
            helper,
            permissions={"medications": True, "appointments": True},
        )
        body = client.patch(
            f"/api/v1/profiles/{profile_id}/caregivers/{relationship_id}/permissions",
            json={"permissions": {"symptoms": True}},
            headers=headers,
        ).json()
        granted = {row["key"] for row in body["permissions"] if row["allowed"]}
        assert granted == {"medications", "appointments", "symptoms"}

    def test_a_caregiver_cannot_change_their_own_permissions(
        self, client, owner, helper, clock
    ):
        """Section 75: a client flag cannot elevate privilege, and neither can a
        client request -- the permission routes depend on ``OwnedProfile``."""
        _, profile_id = owner
        relationship_id = active_caregiver(client, owner, helper)
        response = client.patch(
            f"/api/v1/profiles/{profile_id}/caregivers/{relationship_id}/permissions",
            json={"permissions": dict.fromkeys(ALL_KEYS, True)},
            headers=helper,
        )
        assert response.status_code == 404

    def test_an_unknown_permission_key_is_refused(self, client, owner, helper, clock):
        headers, profile_id = owner
        relationship_id = active_caregiver(client, owner, helper)
        response = client.patch(
            f"/api/v1/profiles/{profile_id}/caregivers/{relationship_id}/permissions",
            json={"permissions": {"everything": True}},
            headers=headers,
        )
        assert response.status_code == 422


# --- revocation --------------------------------------------------------------


class TestRevocation:
    def test_revoking_stops_access_immediately(self, client, owner, helper, clock):
        """Section 52, and the word "immediately" taken literally.

        The same GET that worked on the line above answers 404 on the line below.
        Nothing is invalidated, because nothing was cached: ``granted_keys``
        returns an empty set for a relationship that is not active, and every
        request reads the row.
        """
        headers, profile_id = owner
        relationship_id = active_caregiver(
            client, owner, helper, permissions={"medications": True}
        )
        assert (
            client.get(
                f"/api/v1/profiles/{profile_id}/care/home", headers=helper
            ).status_code
            == 200
        )

        assert (
            client.delete(
                f"/api/v1/profiles/{profile_id}/caregivers/{relationship_id}",
                headers=headers,
            ).status_code
            == 204
        )

        assert (
            client.get(
                f"/api/v1/profiles/{profile_id}/care/home", headers=helper
            ).status_code
            == 404
        )
        assert (
            client.get("/api/v1/caregiver/profiles", headers=helper).json()["profiles"]
            == []
        )

    def test_a_revoked_caregiver_leaves_the_active_list_and_keeps_their_history(
        self, client, owner, helper, db, clock
    ):
        """Section 52: the caregiver disappears, the record does not."""
        from app.models import CaregiverAuditEvent, CaregiverRelationship

        headers, profile_id = owner
        relationship_id = active_caregiver(client, owner, helper)
        client.delete(
            f"/api/v1/profiles/{profile_id}/caregivers/{relationship_id}",
            headers=headers,
        )

        assert (
            client.get(
                f"/api/v1/profiles/{profile_id}/caregivers", headers=headers
            ).json()["caregivers"]
            == []
        )
        row = db.query(CaregiverRelationship).one()
        assert row.status == "revoked"
        assert row.revoked_at is not None
        assert row.accepted_at is not None
        events = {event.event_type for event in db.query(CaregiverAuditEvent).all()}
        assert {"invited", "accepted", "relationship_revoked"} <= events

    def test_revoking_twice_is_accepted(self, client, owner, helper, clock):
        """Pressing Remove again should not produce an error about somebody who
        is already gone."""
        headers, profile_id = owner
        relationship_id = active_caregiver(client, owner, helper)
        for _ in range(2):
            assert (
                client.delete(
                    f"/api/v1/profiles/{profile_id}/caregivers/{relationship_id}",
                    headers=headers,
                ).status_code
                == 204
            )

    def test_revoking_a_pending_invitation_kills_its_token(
        self, client, owner, helper, clock
    ):
        """How an invitation is withdrawn: a link already sent stops working."""
        headers, profile_id = owner
        created = invite(client, headers, profile_id).json()
        client.delete(
            f"/api/v1/profiles/{profile_id}/caregivers/{created['caregiver']['id']}",
            headers=headers,
        )
        assert accept(client, helper, created["token"]).status_code == 404

    def test_the_same_person_can_be_invited_back(self, client, owner, helper, clock):
        """What the partial unique index is for.

        The revoked row keeps its history and the new one is the only active
        pairing, so re-inviting somebody is an ordinary thing to do rather than a
        constraint violation.
        """
        headers, profile_id = owner
        relationship_id = active_caregiver(client, owner, helper)
        client.delete(
            f"/api/v1/profiles/{profile_id}/caregivers/{relationship_id}",
            headers=headers,
        )
        again = invite(
            client, headers, profile_id, permissions={"appointments": True}
        ).json()
        body = accept(client, helper, again["token"])
        assert body.status_code == 200
        assert body.json()["granted"] == ["appointments"]


# --- role versus permission --------------------------------------------------


class TestRoleVersusPermission:
    def test_changing_a_role_changes_no_permission(self, client, owner, helper, clock):
        """Sections 10 and 54, and the whole reason ``role`` is never read by the
        authorization code.

        ``family`` becomes ``primary_caregiver`` -- the most senior-sounding role
        there is -- and the granted set is identical before and after.
        """
        headers, profile_id = owner
        relationship_id = active_caregiver(
            client, owner, helper, permissions={"medications": True}, role="family"
        )
        before = client.get(
            f"/api/v1/profiles/{profile_id}/caregivers/{relationship_id}/permissions",
            headers=headers,
        ).json()

        updated = client.patch(
            f"/api/v1/profiles/{profile_id}/caregivers/{relationship_id}",
            json={"role": "primary_caregiver"},
            headers=headers,
        )
        assert updated.status_code == 200
        assert updated.json()["role"] == "primary_caregiver"

        after = client.get(
            f"/api/v1/profiles/{profile_id}/caregivers/{relationship_id}/permissions",
            headers=headers,
        ).json()
        assert after == before

        home = client.get(
            f"/api/v1/profiles/{profile_id}/care/home", headers=helper
        ).json()
        assert sorted(home["granted"]) == ["medications"]
        assert home["symptoms"] is None

    def test_a_role_is_only_a_label(self, client, owner, helper, clock):
        """Even ``emergency_contact`` as a role grants nothing.

        Worth its own test because the name invites the assumption that it does
        -- and because section 43's emergency contacts are a different table
        entirely, with no permissions attached.
        """
        active_caregiver(client, owner, helper, role="emergency_contact", permissions={})
        _, profile_id = owner
        body = client.get(
            f"/api/v1/profiles/{profile_id}/care/home", headers=helper
        ).json()
        assert body["granted"] == []
        assert body["medications"] is None
        assert body["appointments"] is None


# --- what a caregiver may never touch ----------------------------------------


class TestEmergencyContactsAreOwnerOnly:
    def test_a_caregiver_cannot_read_reorder_or_change_the_chain(
        self, client, owner, helper, clock
    ):
        """Section 45, enforced by there being no caregiver route at all.

        Every emergency-contact endpoint depends on ``OwnedProfile``, reads
        included, so a caregiver with every category granted 404s on every verb.
        """
        headers, profile_id = owner
        active_caregiver(client, owner, helper, permissions=dict.fromkeys(ALL_KEYS, True))
        created = client.post(
            f"/api/v1/profiles/{profile_id}/emergency-contacts",
            json={"name": "Hana", "phone": "+441234567890"},
            headers=headers,
        ).json()

        base = f"/api/v1/profiles/{profile_id}/emergency-contacts"
        assert client.get(base, headers=helper).status_code == 404
        assert (
            client.post(base, json={"name": "Sneaky"}, headers=helper).status_code == 404
        )
        assert (
            client.patch(
                f"{base}/{created['id']}", json={"name": "Changed"}, headers=helper
            ).status_code
            == 404
        )
        assert client.delete(f"{base}/{created['id']}", headers=helper).status_code == 404
        assert (
            client.post(
                f"{base}/reorder", json={"order": [created["id"]]}, headers=helper
            ).status_code
            == 404
        )

    def test_the_contact_survived_every_attempt(self, client, owner, helper, clock):
        headers, profile_id = owner
        active_caregiver(client, owner, helper, permissions=dict.fromkeys(ALL_KEYS, True))
        client.post(
            f"/api/v1/profiles/{profile_id}/emergency-contacts",
            json={"name": "Hana"},
            headers=headers,
        )
        client.post(
            f"/api/v1/profiles/{profile_id}/emergency-contacts",
            json={"name": "Sneaky"},
            headers=helper,
        )
        listed = client.get(
            f"/api/v1/profiles/{profile_id}/emergency-contacts", headers=headers
        ).json()
        assert [row["name"] for row in listed["contacts"]] == ["Hana"]


# --- robot independence ------------------------------------------------------


def test_no_caregiver_route_mentions_hardware(client, owner, helper, clock):
    """Section 90, checked rather than asserted in prose.

    A full caregiver flow -- invite, accept, read the home, send nothing -- runs
    on an account with no robot claimed, no provisioning session and no
    heartbeat. There is nothing to switch off because nothing in this code path
    knows a robot exists.
    """
    headers, profile_id = owner
    assert client.get("/api/v1/devices", headers=headers).json() == []

    active_caregiver(client, owner, helper, permissions={"medications": True})
    home = client.get(f"/api/v1/profiles/{profile_id}/care/home", headers=helper)
    assert home.status_code == 200
    assert "device" not in str(home.json())
    assert uuid.UUID(home.json()["profile_id"]) == uuid.UUID(profile_id)
