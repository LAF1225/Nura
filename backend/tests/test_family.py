"""Family messages, check-ins, emergency contacts and calling.

PRD 9, sections 30-41, 43-47, 65, 68, 72, 74, 76 and 95.

Three groups, and one short one that matters more than its size.

``TestFamilyMessaging`` covers the care thread: that it needs
``communication``, that one caregiver cannot read another's, that a retry is
idempotent, and that read state means only what section 37 says it means.

``TestEmergencyContacts`` covers the chain PRD 10 will escalate through --
created, edited, reordered, renumbered -- and that nothing in PRD 9 walks it.

``TestCalling`` is four tests and the point of all of them is that nothing
happens. Section 38 forbids simulating a successful call; the provider is
unconfigured in every deployment, so the route answers 503 and cannot return
``active``.
"""

import uuid
from datetime import UTC, datetime

import pytest

from app.api.deps import current_time
from app.main import app
from app.services.caregivers import calls as call_service
from tests.test_caregivers import accept, active_caregiver, invite
from tests.test_devices import ready_account
from tests.test_today import Clock

NOW = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)


# --- helpers ----------------------------------------------------------------


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
def helper(client, make_token) -> dict[str, str]:
    return {"Authorization": f"Bearer {make_token()}"}


def threads_url(profile_id: str) -> str:
    return f"/api/v1/profiles/{profile_id}/family/threads"


def contacts_url(profile_id: str) -> str:
    return f"/api/v1/profiles/{profile_id}/emergency-contacts"


def open_thread(client, headers, profile_id: str, relationship_id: str) -> str:
    response = client.post(
        threads_url(profile_id),
        json={"relationship_id": relationship_id},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def send(client, headers, profile_id: str, thread_id: str, **body):
    return client.post(
        f"{threads_url(profile_id)}/{thread_id}/messages", json=body, headers=headers
    )


# --- family messaging --------------------------------------------------------


class TestFamilyMessaging:
    def test_both_sides_can_talk(self, client, owner, helper, clock):
        """Section 31, and the whole of what section 32 allows: two people and a
        list of lines."""
        headers, profile_id = owner
        relationship_id = active_caregiver(
            client, owner, helper, permissions={"communication": True}
        )
        thread_id = open_thread(client, headers, profile_id, relationship_id)

        assert (
            send(client, headers, profile_id, thread_id, text="Morning!").status_code
            == 201
        )
        assert (
            send(
                client, helper, profile_id, thread_id, text="How did you sleep?"
            ).status_code
            == 201
        )

        body = client.get(
            f"{threads_url(profile_id)}/{thread_id}/messages", headers=headers
        ).json()
        assert [m["text"] for m in body["messages"]] == ["Morning!", "How did you sleep?"]
        assert [m["side"] for m in body["messages"]] == ["primary_user", "caregiver"]

    def test_messaging_needs_the_communication_permission(
        self, client, owner, helper, clock
    ):
        """A caregiver with medications but not communication cannot read or send."""
        headers, profile_id = owner
        relationship_id = active_caregiver(
            client, owner, helper, permissions={"communication": True}
        )
        thread_id = open_thread(client, headers, profile_id, relationship_id)
        send(client, headers, profile_id, thread_id, text="Hello?")

        # Communication is then withdrawn. The thread and its message stay; both
        # sides stop being able to reach them, which is the same rule revocation
        # follows -- access ends, the record does not.
        client.patch(
            f"/api/v1/profiles/{profile_id}/caregivers/{relationship_id}/permissions",
            json={"permissions": {"communication": False}},
            headers=headers,
        )

        assert client.get(threads_url(profile_id), headers=helper).status_code == 404
        assert (
            client.get(
                f"{threads_url(profile_id)}/{thread_id}/messages", headers=helper
            ).status_code
            == 404
        )
        assert (
            send(client, helper, profile_id, thread_id, text="Let me in").status_code
            == 404
        )

    def test_one_caregiver_cannot_read_anothers_thread(
        self, client, owner, helper, make_token, clock
    ):
        """Section 66, made structural by one thread per relationship.

        There is no query in the messaging service that could return caregiver
        B's messages to caregiver A: a thread id resolves through one
        relationship, and the relationship resolves through one account.
        """
        headers, profile_id = owner
        first_relationship = active_caregiver(
            client, owner, helper, permissions={"communication": True}
        )
        second = {"Authorization": f"Bearer {make_token()}"}
        token = invite(
            client,
            headers,
            profile_id,
            name="Bilal",
            permissions={"communication": True},
        ).json()["token"]
        accept(client, second, token)

        first_thread = open_thread(client, headers, profile_id, first_relationship)
        send(client, helper, profile_id, first_thread, text="Private to Ayesha")

        assert (
            client.get(
                f"{threads_url(first_thread and profile_id)}/{first_thread}/messages",
                headers=second,
            ).status_code
            == 404
        )
        listed = client.get(threads_url(profile_id), headers=second).json()
        assert "Private to Ayesha" not in str(listed)

    def test_the_owner_sees_every_thread_and_a_caregiver_sees_one(
        self, client, owner, helper, make_token, clock
    ):
        headers, profile_id = owner
        first = active_caregiver(
            client, owner, helper, permissions={"communication": True}
        )
        second_headers = {"Authorization": f"Bearer {make_token()}"}
        token = invite(
            client,
            headers,
            profile_id,
            name="Bilal",
            permissions={"communication": True},
        ).json()["token"]
        second = accept(client, second_headers, token).json()["relationship_id"]

        open_thread(client, headers, profile_id, first)
        open_thread(client, headers, profile_id, second)

        owner_threads = client.get(threads_url(profile_id), headers=headers).json()
        caregiver_threads = client.get(threads_url(profile_id), headers=helper).json()
        assert len(owner_threads["threads"]) == 2
        assert len(caregiver_threads["threads"]) == 1

    def test_opening_a_thread_twice_returns_the_same_one(
        self, client, owner, helper, clock
    ):
        """One per pairing, so this is idempotent rather than a second thread."""
        headers, profile_id = owner
        relationship_id = active_caregiver(
            client, owner, helper, permissions={"communication": True}
        )
        first = open_thread(client, headers, profile_id, relationship_id)
        second = open_thread(client, headers, profile_id, relationship_id)
        assert first == second

    def test_a_retried_send_does_not_duplicate(self, client, owner, helper, clock):
        """Sections 72 and 74.

        The app keeps one ``client_message_id`` across attempts, so a send that
        timed out *after* the server stored it comes back as the message that is
        already there -- which is what lets the app retire its optimistic row
        instead of showing the message twice.
        """
        headers, profile_id = owner
        relationship_id = active_caregiver(
            client, owner, helper, permissions={"communication": True}
        )
        thread_id = open_thread(client, headers, profile_id, relationship_id)

        first = send(
            client,
            headers,
            profile_id,
            thread_id,
            text="Are you up?",
            client_message_id="draft-1",
        ).json()
        second = send(
            client,
            headers,
            profile_id,
            thread_id,
            text="Are you up?",
            client_message_id="draft-1",
        ).json()
        assert first["id"] == second["id"]

        body = client.get(
            f"{threads_url(profile_id)}/{thread_id}/messages", headers=headers
        ).json()
        assert len(body["messages"]) == 1
        assert body["messages"][0]["client_message_id"] == "draft-1"

    def test_a_check_in_is_stored_as_a_code_and_rendered_from_it(
        self, client, owner, helper, clock
    ):
        """Sections 34, 35 and 36, and the PRD 7 lesson about prose.

        The row keeps ``im_okay``; one module turns it into a sentence. So a
        check-in can never carry free text the sender did not mean to put in a
        care thread, and the wording can be fixed later without rewriting rows.
        """
        headers, profile_id = owner
        relationship_id = active_caregiver(
            client, owner, helper, permissions={"communication": True}
        )
        thread_id = open_thread(client, headers, profile_id, relationship_id)

        sent = send(
            client,
            headers,
            profile_id,
            thread_id,
            message_type="check_in",
            check_in_code="im_okay",
        )
        assert sent.status_code == 201
        assert sent.json()["check_in_code"] == "im_okay"
        assert sent.json()["text"] == "I’m okay."

    def test_each_side_has_its_own_check_ins(self, client, owner, helper, clock):
        """Sections 35 and 36 list different things, because they are different
        gestures: the person says how they are, the caregiver asks."""
        headers, profile_id = owner
        relationship_id = active_caregiver(
            client, owner, helper, permissions={"communication": True}
        )
        thread_id = open_thread(client, headers, profile_id, relationship_id)

        # The caregiver asks; that is theirs.
        assert (
            send(
                client,
                helper,
                profile_id,
                thread_id,
                message_type="check_in",
                check_in_code="how_are_you",
            ).status_code
            == 201
        )
        # "I'm okay" from a caregiver is an answer to a question nobody asked.
        refused = send(
            client,
            helper,
            profile_id,
            thread_id,
            message_type="check_in",
            check_in_code="im_okay",
        )
        assert refused.status_code == 422
        # And the reverse.
        assert (
            send(
                client,
                headers,
                profile_id,
                thread_id,
                message_type="check_in",
                check_in_code="how_are_you",
            ).status_code
            == 422
        )

    def test_nothing_infers_urgency_from_a_check_in(self, client, owner, helper, clock):
        """Section 35 forbids inferring emergency severity, and section 102 any
        autonomous caregiver escalation.

        "I need help with something" is stored as a message and produces nothing
        else: no suggestion, no alert, no audit event, no change to the care
        summary beyond an unread count.
        """
        headers, profile_id = owner
        relationship_id = active_caregiver(
            client, owner, helper, permissions={"communication": True}
        )
        thread_id = open_thread(client, headers, profile_id, relationship_id)
        send(
            client,
            headers,
            profile_id,
            thread_id,
            message_type="check_in",
            check_in_code="need_help",
        )

        summary = client.get(
            f"/api/v1/profiles/{profile_id}/care-summary", headers=headers
        ).json()
        assert summary["pending_suggestion_count"] == 0
        home = client.get(
            f"/api/v1/profiles/{profile_id}/care/home", headers=helper
        ).json()
        assert home["unread_messages"] == 1
        assert home["pending_suggestions"] == 0

    def test_a_photo_message_cannot_be_sent(self, client, owner, helper, clock):
        """Section 33 makes attachments optional and this one is not built.

        Refused by the schema's Literal rather than half-accepted, so there is no
        state in which a message claims an attachment that does not exist.
        """
        headers, profile_id = owner
        relationship_id = active_caregiver(
            client, owner, helper, permissions={"communication": True}
        )
        thread_id = open_thread(client, headers, profile_id, relationship_id)
        refused = send(
            client,
            headers,
            profile_id,
            thread_id,
            message_type="photo",
            text="look at this",
        )
        assert refused.status_code == 422

    def test_an_empty_message_is_refused(self, client, owner, helper, clock):
        headers, profile_id = owner
        relationship_id = active_caregiver(
            client, owner, helper, permissions={"communication": True}
        )
        thread_id = open_thread(client, headers, profile_id, relationship_id)
        assert send(client, headers, profile_id, thread_id, text="   ").status_code == 422

    def test_read_state_is_the_other_sides_messages_only(
        self, client, owner, helper, clock
    ):
        """Section 37: sent and read, and no stronger promise.

        A reader opening their own thread does not mark their own messages read,
        which would make the sender's indicator mean nothing.
        """
        headers, profile_id = owner
        relationship_id = active_caregiver(
            client, owner, helper, permissions={"communication": True}
        )
        thread_id = open_thread(client, headers, profile_id, relationship_id)
        send(client, headers, profile_id, thread_id, text="Did you eat?")

        # The owner re-reading their own message does not mark it read.
        own = client.get(
            f"{threads_url(profile_id)}/{thread_id}/messages", headers=headers
        ).json()
        assert own["messages"][0]["read_at"] is None
        assert own["thread"]["unread"] == 0

        # The caregiver opening it does.
        caregiver_view = client.get(
            f"{threads_url(profile_id)}/{thread_id}/messages", headers=helper
        ).json()
        assert caregiver_view["messages"][0]["read_at"] is not None

        back = client.get(
            f"{threads_url(profile_id)}/{thread_id}/messages", headers=headers
        ).json()
        assert back["messages"][0]["read_at"] is not None

    def test_an_unread_count_is_waiting_for_the_other_side(
        self, client, owner, helper, clock
    ):
        headers, profile_id = owner
        relationship_id = active_caregiver(
            client, owner, helper, permissions={"communication": True}
        )
        thread_id = open_thread(client, headers, profile_id, relationship_id)
        send(client, helper, profile_id, thread_id, text="Thinking of you")
        send(client, helper, profile_id, thread_id, text="Call when you can")

        threads = client.get(threads_url(profile_id), headers=headers).json()
        assert threads["threads"][0]["unread"] == 2
        assert threads["threads"][0]["last_message"]["text"] == "Call when you can"

    def test_revoking_stops_messaging_and_keeps_the_conversation(
        self, client, owner, helper, db, clock
    ):
        """Section 52, applied to a thread.

        Access ends; the record of a conversation that really happened does not.
        Deleting somebody's messages because their access ended would be
        destroying history, not revoking a permission.
        """
        from app.models import FamilyMessage

        headers, profile_id = owner
        relationship_id = active_caregiver(
            client, owner, helper, permissions={"communication": True}
        )
        thread_id = open_thread(client, headers, profile_id, relationship_id)
        send(client, helper, profile_id, thread_id, text="Hope today is kinder")

        client.delete(
            f"/api/v1/profiles/{profile_id}/caregivers/{relationship_id}",
            headers=headers,
        )

        assert (
            client.get(
                f"{threads_url(profile_id)}/{thread_id}/messages", headers=helper
            ).status_code
            == 404
        )
        assert db.query(FamilyMessage).count() == 1

    def test_an_unrelated_account_cannot_read_a_thread(
        self, client, owner, helper, make_token, clock
    ):
        headers, profile_id = owner
        relationship_id = active_caregiver(
            client, owner, helper, permissions={"communication": True}
        )
        thread_id = open_thread(client, headers, profile_id, relationship_id)
        stranger = {"Authorization": f"Bearer {make_token()}"}
        assert (
            client.get(
                f"{threads_url(profile_id)}/{thread_id}/messages", headers=stranger
            ).status_code
            == 404
        )

    def test_no_assistant_tool_can_read_a_family_message(self):
        """Section 65: no AI summary or analysis of private family messages.

        Checked by absence across the whole tool layer -- no tool names a thread,
        a message or a check-in, so there is nothing to opt out of.
        """
        from app.services.assistant import tools

        for tool in tools.TOOLS:
            assert "message" not in tool.name
            assert "thread" not in tool.name
            assert "family" not in tool.name
            assert "check_in" not in tool.name
            for argument in tool.spec().parameters.get("properties", {}):
                assert "thread" not in argument
                assert "message" not in argument


# --- emergency contacts ------------------------------------------------------


class TestEmergencyContacts:
    def test_contacts_are_created_in_order(self, client, owner, clock):
        """Section 44: the chain is ordered, and added at the end.

        At the end rather than anywhere clever: somebody adding their neighbour
        fourth meant fourth, and a service with an opinion about who matters most
        is not what section 45 asks for.
        """
        headers, profile_id = owner
        for name in ("Spouse", "Child", "Neighbour"):
            response = client.post(
                contacts_url(profile_id),
                json={"name": name, "relationship_label": name},
                headers=headers,
            )
            assert response.status_code == 201, response.text

        listed = client.get(contacts_url(profile_id), headers=headers).json()
        assert [row["name"] for row in listed["contacts"]] == [
            "Spouse",
            "Child",
            "Neighbour",
        ]
        assert [row["priority"] for row in listed["contacts"]] == [1, 2, 3]

    def test_reordering_renumbers_the_chain(self, client, owner, clock):
        """Sections 44, 45 and 89.

        The client sends the list it is displaying and priority is taken from
        that, rather than from numbers the client has to keep consistent.
        """
        headers, profile_id = owner
        ids = [
            client.post(
                contacts_url(profile_id), json={"name": name}, headers=headers
            ).json()["id"]
            for name in ("Spouse", "Child", "Neighbour")
        ]

        reordered = client.post(
            f"{contacts_url(profile_id)}/reorder",
            json={"order": [ids[2], ids[0], ids[1]]},
            headers=headers,
        )
        assert reordered.status_code == 200
        assert [row["name"] for row in reordered.json()["contacts"]] == [
            "Neighbour",
            "Spouse",
            "Child",
        ]
        assert [row["priority"] for row in reordered.json()["contacts"]] == [1, 2, 3]

    def test_a_partial_order_keeps_the_rest(self, client, owner, clock):
        """Leniency worth stating once: a reorder that refused to save because one
        contact was deleted on another device would leave the old order in place,
        which is the opposite of what somebody reordering wanted."""
        headers, profile_id = owner
        ids = [
            client.post(
                contacts_url(profile_id), json={"name": name}, headers=headers
            ).json()["id"]
            for name in ("Spouse", "Child", "Neighbour")
        ]
        body = client.post(
            f"{contacts_url(profile_id)}/reorder",
            json={"order": [ids[1], str(uuid.uuid4())]},
            headers=headers,
        ).json()
        assert [row["name"] for row in body["contacts"]] == [
            "Child",
            "Spouse",
            "Neighbour",
        ]

    def test_deleting_closes_the_gap(self, client, owner, clock):
        headers, profile_id = owner
        ids = [
            client.post(
                contacts_url(profile_id), json={"name": name}, headers=headers
            ).json()["id"]
            for name in ("Spouse", "Child", "Neighbour")
        ]
        assert (
            client.delete(
                f"{contacts_url(profile_id)}/{ids[0]}", headers=headers
            ).status_code
            == 204
        )
        listed = client.get(contacts_url(profile_id), headers=headers).json()
        assert [row["priority"] for row in listed["contacts"]] == [1, 2]
        assert [row["name"] for row in listed["contacts"]] == ["Child", "Neighbour"]

    def test_deactivating_keeps_the_contact(self, client, owner, clock):
        """Section 45 asks for activate/deactivate as well as remove.

        A deactivated contact nobody can see again is a deleted one with extra
        steps, so it stays in the list.
        """
        headers, profile_id = owner
        contact_id = client.post(
            contacts_url(profile_id), json={"name": "Spouse"}, headers=headers
        ).json()["id"]
        updated = client.patch(
            f"{contacts_url(profile_id)}/{contact_id}",
            json={"is_active": False},
            headers=headers,
        )
        assert updated.status_code == 200
        assert updated.json()["is_active"] is False
        listed = client.get(contacts_url(profile_id), headers=headers).json()
        assert len(listed["contacts"]) == 1

    def test_an_account_cannot_be_attached_from_a_request(self, client, owner, clock):
        """Section 75: account ids are never trusted from a client.

        ``has_account`` is derived from a link the caregiver invitation flow makes,
        and the create schema has no field for one -- so a request naming somebody
        else's account id is refused outright.
        """
        headers, profile_id = owner
        refused = client.post(
            contacts_url(profile_id),
            json={"name": "Spouse", "account_id": str(uuid.uuid4())},
            headers=headers,
        )
        assert refused.status_code == 422

    def test_priority_cannot_be_set_directly(self, client, owner, clock):
        """Contiguity is the server's to keep, so there is no priority field on
        the create or the patch -- the chain is reordered as a whole."""
        headers, profile_id = owner
        assert (
            client.post(
                contacts_url(profile_id),
                json={"name": "Spouse", "priority": 1},
                headers=headers,
            ).status_code
            == 422
        )
        contact_id = client.post(
            contacts_url(profile_id), json={"name": "Spouse"}, headers=headers
        ).json()["id"]
        assert (
            client.patch(
                f"{contacts_url(profile_id)}/{contact_id}",
                json={"priority": 5},
                headers=headers,
            ).status_code
            == 422
        )

    def test_another_account_cannot_reach_the_chain(
        self, client, owner, make_token, clock
    ):
        headers, profile_id = owner
        contact_id = client.post(
            contacts_url(profile_id), json={"name": "Spouse"}, headers=headers
        ).json()["id"]
        stranger = {"Authorization": f"Bearer {make_token()}"}
        assert client.get(contacts_url(profile_id), headers=stranger).status_code == 404
        assert (
            client.delete(
                f"{contacts_url(profile_id)}/{contact_id}", headers=stranger
            ).status_code
            == 404
        )

    def test_nothing_in_prd_9_contacts_anybody(self, client, owner, clock):
        """Section 47, checked rather than asserted in prose.

        The chain is built and ordered. Nothing sends, rings, notifies or
        escalates: no code path in the caregiver package reads ``priority`` to
        decide who to reach, and a contact marked first is simply a row that says
        so. Escalation is PRD 10's.
        """
        import inspect

        from app.services.caregivers import contacts as contact_service

        # Checked on the module's own surface rather than by scanning its prose:
        # no function here does anything but read and write rows, and it imports
        # nothing that could reach a phone or an inbox.
        public = {
            name
            for name, _ in inspect.getmembers(contact_service, inspect.isfunction)
            if not name.startswith("_")
            and inspect.getmodule(getattr(contact_service, name)) is contact_service
        }
        assert public == {
            "list_contacts",
            "get_contact",
            "create_contact",
            "update_contact",
            "delete_contact",
            "reorder",
        }
        imported = {
            name for name, value in inspect.getmembers(contact_service, inspect.ismodule)
        }
        for sender in ("smtplib", "httpx", "requests", "twilio", "urllib"):
            assert sender not in imported

        headers, profile_id = owner
        client.post(
            contacts_url(profile_id),
            json={"name": "Spouse", "phone": "+441234567890"},
            headers=headers,
        )
        # Creating one produces a contact and nothing else.
        summary = client.get(
            f"/api/v1/profiles/{profile_id}/care-summary", headers=headers
        ).json()
        assert summary["emergency_contact_count"] == 1


# --- calling -----------------------------------------------------------------


class TestCalling:
    def test_calling_is_refused_rather_than_simulated(self, client, owner, helper, clock):
        """Section 38, and the sentence in it that matters: do not simulate
        successful calls.

        Every method of ``UnconfiguredCallProvider`` raises, so this route cannot
        return ``ringing``, ``connecting`` or ``active``. The app shows a sentence
        saying calling is not set up, not a call screen.
        """
        headers, profile_id = owner
        relationship_id = active_caregiver(
            client, owner, helper, permissions={"communication": True}
        )
        response = client.post(
            f"/api/v1/profiles/{profile_id}/family/calls",
            json={"relationship_id": relationship_id},
            headers=headers,
        )
        assert response.status_code == 503
        assert response.json()["detail"]["code"] == "calling_not_configured"

    def test_a_call_still_needs_the_permission(self, client, owner, helper, clock):
        """Authorized exactly like a message, so wiring a provider later does not
        also have to get the authorization right."""
        headers, profile_id = owner
        relationship_id = active_caregiver(
            client, owner, helper, permissions={"medications": True}
        )
        # The owner's own scope holds every category, so what refuses this is the
        # *pairing*: this caregiver was never granted ``communication``, and a
        # call into a relationship that cannot exchange messages is a call to
        # somebody who has not agreed to be called.
        assert (
            client.post(
                f"/api/v1/profiles/{profile_id}/family/calls",
                json={"relationship_id": relationship_id},
                headers=headers,
            ).status_code
            == 404
        )
        # And from the caregiver's side it is their own missing category.
        assert (
            client.post(
                f"/api/v1/profiles/{profile_id}/family/calls",
                json={"relationship_id": relationship_id},
                headers=helper,
            ).status_code
            == 404
        )

    def test_the_home_says_calling_is_unavailable(self, client, owner, helper, clock):
        """So the app can leave the control out rather than showing one that
        always fails -- while the server stays authoritative either way
        (section 62)."""
        active_caregiver(client, owner, helper, permissions={"communication": True})
        _, profile_id = owner
        body = client.get(
            f"/api/v1/profiles/{profile_id}/care/home", headers=helper
        ).json()
        assert body["calling_available"] is False

    def test_the_provider_interface_mentions_no_vendor(self):
        """Section 39: do not hard-wire the app to one vendor.

        Five methods, which is section 39's own list, and no vendor concept in any
        signature -- no room, no SDP, no ICE server, no token format. A session's
        ``credential`` is opaque and short-lived by contract (section 76), and
        there is no table for calls because nothing has ever happened that would
        need recording.
        """
        import inspect

        from app.models import __all__ as model_names

        abstract = {
            name
            for name, value in inspect.getmembers(
                call_service.AudioCallProvider, inspect.isfunction
            )
            if getattr(value, "__isabstractmethod__", False)
        }
        assert abstract == {"start", "accept", "decline", "end", "state"}

        # Checked on the signatures rather than on the prose: every parameter is
        # a Nura concept, so a provider that needs a room, a channel or an SDP
        # offer builds one from the relationship id and keeps it to itself.
        parameters: set[str] = set()
        for name in abstract:
            signature = inspect.signature(getattr(call_service.AudioCallProvider, name))
            parameters |= set(signature.parameters) - {"self"}
        assert parameters == {
            "relationship_id",
            "caller_account_id",
            "call_id",
            "account_id",
        }

        # And nothing stores a call, because none has ever happened.
        assert not any("Call" in name for name in model_names)

    def test_an_unconfigured_provider_is_what_every_deployment_has(self):
        assert isinstance(
            call_service.get_provider(), call_service.UnconfiguredCallProvider
        )
        assert call_service.calling_available() is False


# --- notification preferences ------------------------------------------------


def test_a_caregiver_sets_their_own_notification_preferences(
    client, owner, helper, clock
):
    """Section 48, per supported person.

    Somebody supporting two parents may want everything about one and only
    messages about the other, which is why these live on the relationship.
    ``safety_alerts`` defaults off and nothing will fire it until PRD 10
    (sections 48 and 94).
    """
    _, profile_id = owner
    active_caregiver(client, owner, helper, permissions={"communication": True})

    supported = client.get("/api/v1/caregiver/profiles", headers=helper).json()
    assert supported["profiles"][0]["notifications"] == {
        "messages": True,
        "appointment_updates": True,
        "suggestion_outcomes": True,
        "safety_alerts": False,
    }

    updated = client.patch(
        f"/api/v1/profiles/{profile_id}/care/notifications",
        json={"notifications": {"messages": False, "safety_alerts": True}},
        headers=helper,
    )
    assert updated.status_code == 200
    assert updated.json()["notifications"]["messages"] is False
    assert updated.json()["notifications"]["safety_alerts"] is True


def test_the_primary_user_sets_their_care_notifications_on_me(client, owner, clock):
    """Section 48's other half, where per-account preferences already live.

    None of them gates the in-app list: section 48 requires an approval request
    to stay visible even when push is off.
    """
    headers, _ = owner
    settings = client.get("/api/v1/me", headers=headers).json()["settings"]
    assert settings["notify_suggestion_requests"] is True

    updated = client.patch(
        "/api/v1/me", json={"notify_suggestion_requests": False}, headers=headers
    )
    assert updated.status_code == 200
    assert updated.json()["settings"]["notify_suggestion_requests"] is False


def test_an_approval_request_stays_visible_with_every_notification_off(
    client, owner, helper, clock
):
    """Section 48, stated as a test because it is easy to get wrong.

    Every care notification is switched off, and the pending suggestion is still
    in the list and still counted. Notification preferences decide whether a
    *notification* is scheduled; they gate nothing in the app.
    """
    from tests.test_care_suggestions import propose, suggestions_url
    from tests.test_medications import add_medication, make_schedule

    headers, profile_id = owner
    client.patch(
        "/api/v1/me",
        json={
            "notify_caregiver_messages": False,
            "notify_suggestion_requests": False,
            "notify_appointment_suggestions": False,
            "notify_routine_suggestions": False,
        },
        headers=headers,
    )
    active_caregiver(client, owner, helper, permissions={"medications": True})
    medication_id = add_medication(client, headers, profile_id)
    schedule = make_schedule(client, headers, profile_id, medication_id).json()
    propose(
        client,
        helper,
        profile_id,
        action_type="pause_medication_reminder",
        target_resource_id=schedule["id"],
    )

    listed = client.get(suggestions_url(profile_id), headers=headers).json()
    assert listed["pending_count"] == 1
    summary = client.get(
        f"/api/v1/profiles/{profile_id}/care-summary", headers=headers
    ).json()
    assert summary["pending_suggestion_count"] == 1
