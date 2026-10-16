"""Sensitive payloads stay out of the logs (PRD 13, sections 12 and 52).

Section 12 names eleven classes of content that must never reach a log line,
and section 265 asks for targeted regression tests rather than a static-
analysis framework. This is the targeted version: one capture handler on the
root ``app`` logger, one write per domain driven through the real HTTP routes,
and one assertion that none of the distinctive strings came out the other side.

**Driven through HTTP on purpose.** An earlier version of this check (PRD 12's,
for a task title) attaches a handler to one service's own logger, which proves
what that module logs. This one is the complement: it attaches to ``app`` and
exercises a whole request, so it also covers whatever a route, a dependency, a
schema validator or an exception handler might log on the way past.

**``logger.disabled`` has to be cleared first**, and the reason is worth
repeating here because it defeats every attempt to test logging in this
repository. The session fixture runs the real Alembic migrations, and Alembic's
``env.py`` calls ``fileConfig(alembic.ini)``, which defaults to
``disable_existing_loggers=True`` -- so every application logger is switched off
for the rest of the test session.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import pytest

from app.api.deps import current_time
from app.main import app
from tests.test_devices import ready_account
from tests.test_today import Clock

NOON = datetime(2026, 10, 12, 12, 0, tzinfo=UTC)

#: Strings written into the data below, each one distinctive enough that a
#: match cannot be a coincidence. If any of these appears in a log record, a
#: payload leaked.
#:
#: Section 12's eleven classes, in its own order, with the one that carries
#: each.
SECRETS = {
    "medical record": "Hypertensive nephropathy",
    "symptom": "Throbbing behind the left eye",
    "medication": "Amlodipine besylate",
    "conversation": "I have been dizzy since Tuesday",
    "memory": "Prefers to be called by their middle name",
    "caregiver message": "Did the pharmacy call you back",
    "safety event text": "Slipped on the landing carpet",
    "task": "Ring the clinic about the MRI results",
    "reminder": "Collect the repeat prescription",
    "report content": "Appointment preparation notes",
    "phone number": "07700900123",
}


class Capture(logging.Handler):
    """Collects formatted messages from the whole ``app`` logger tree."""

    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.messages.append(record.getMessage())
        except Exception:  # pragma: no cover - a broken format is itself a bug
            self.messages.append(repr(record.msg))


@pytest.fixture
def captured() -> Capture:
    """Everything logged under ``app`` while a test runs.

    Set at ``DEBUG`` deliberately: section 52 is about release configuration
    not enabling verbose logs with sensitive content, and the way to be sure of
    that is to capture the most verbose level and assert the content is absent
    even there.

    **Every ``app.*`` logger has to be re-enabled, not just ``app``.**
    ``disable_existing_loggers=True`` sets ``disabled`` on each logger object
    that already exists, individually -- it is not inherited, so clearing it on
    the parent leaves ``app.services.privacy.export`` silent. Getting this
    wrong is the dangerous kind of wrong: a capture handler on a disabled
    logger records nothing, and every "this content is absent" assertion then
    passes while proving nothing at all. That is why
    ``TestTheCaptureItself`` asserts a real application logger reaches the
    handler, and why the two PRD 13 tests below also assert that *something*
    was logged.
    """
    manager = logging.Logger.manager
    names = ["app"] + [
        name
        for name in manager.loggerDict
        if name.startswith("app.")
        and isinstance(manager.loggerDict[name], logging.Logger)
    ]
    restore: list[tuple[logging.Logger, int, bool]] = []
    handler = Capture()
    for name in names:
        logger = logging.getLogger(name)
        restore.append((logger, logger.level, logger.disabled))
        logger.setLevel(logging.DEBUG)
        logger.disabled = False

    root = logging.getLogger("app")
    root.addHandler(handler)
    try:
        yield handler
    finally:
        root.removeHandler(handler)
        for logger, level, disabled in restore:
            logger.setLevel(level)
            logger.disabled = disabled


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


def assert_absent(captured: Capture, *values: str) -> None:
    """None of these strings is in any captured record."""
    joined = "\n".join(captured.messages)
    for value in values:
        assert value not in joined, f"{value!r} reached a log line"


class TestSensitiveLogging:
    """Section 12, one class of content at a time."""

    def test_a_medical_record_is_not_logged(self, client, account, clock, captured):
        headers, profile_id = account
        response = client.post(
            f"/api/v1/profiles/{profile_id}/conditions",
            json={
                "name": SECRETS["medical record"],
                "status": "active",
                "notes": "Diagnosed after the second admission.",
            },
            headers=headers,
        )
        assert response.status_code == 201, response.json()
        assert_absent(
            captured,
            SECRETS["medical record"],
            "Diagnosed after the second admission.",
        )

    def test_a_medication_is_not_logged(self, client, account, clock, captured):
        headers, profile_id = account
        response = client.post(
            f"/api/v1/profiles/{profile_id}/medications",
            json={
                "name": SECRETS["medication"],
                "dose": "5",
                "dose_unit": "mg",
                "reason": "Blood pressure",
            },
            headers=headers,
        )
        assert response.status_code == 201, response.json()
        assert_absent(captured, SECRETS["medication"], "Blood pressure")

    def test_a_symptom_is_not_logged(self, client, account, clock, captured):
        headers, profile_id = account
        response = client.post(
            f"/api/v1/profiles/{profile_id}/symptoms",
            json={
                "name": "Headache",
                "first_entry": {
                    "severity": 7,
                    "character": SECRETS["symptom"],
                    "free_text_note": "Worse when I stand up quickly.",
                },
            },
            headers=headers,
        )
        assert response.status_code == 201, response.json()
        assert_absent(captured, SECRETS["symptom"], "Worse when I stand up quickly.")

    def test_a_task_and_a_reminder_are_not_logged(self, client, account, clock, captured):
        headers, profile_id = account
        client.post(
            f"/api/v1/profiles/{profile_id}/tasks",
            json={"title": SECRETS["task"], "notes": "Ask for the written report."},
            headers=headers,
        )
        client.post(
            f"/api/v1/profiles/{profile_id}/reminders",
            json={
                "title": SECRETS["reminder"],
                "time_of_day": "09:00",
                "start_date": "2026-10-12",
            },
            headers=headers,
        )
        assert_absent(
            captured,
            SECRETS["task"],
            SECRETS["reminder"],
            "Ask for the written report.",
        )

    def test_an_assistant_memory_is_not_logged(self, client, account, clock, captured):
        headers, profile_id = account
        response = client.post(
            f"/api/v1/profiles/{profile_id}/assistant/memories",
            json={"category": "preferences", "content": SECRETS["memory"]},
            headers=headers,
        )
        assert response.status_code in (200, 201), response.json()
        assert_absent(captured, SECRETS["memory"])

    def test_a_conversation_is_not_logged(
        self, client, account, clock, captured, scripted
    ):
        """Including what Nura said back.

        PRD 8 section 58 already forbids this at every level; section 12
        restates it, and this is the regression test both point at.
        """
        from app.services.assistant.provider import ScriptedReply

        headers, profile_id = account
        scripted.queue(ScriptedReply(text="I can note that down for you."))
        conversation = client.post(
            f"/api/v1/profiles/{profile_id}/assistant/conversations",
            json={},
            headers=headers,
        )
        assert conversation.status_code == 201, conversation.json()
        conversation_id = conversation.json()["id"]
        response = client.post(
            f"/api/v1/profiles/{profile_id}/assistant/conversations"
            f"/{conversation_id}/messages",
            json={"content": SECRETS["conversation"]},
            headers=headers,
        )
        assert response.status_code in (200, 201), response.json()
        assert_absent(captured, SECRETS["conversation"], "I can note that down for you.")

    def test_a_caregiver_message_and_a_phone_number_are_not_logged(
        self, client, account, clock, captured, make_token
    ):
        headers, profile_id = account
        helper = {"Authorization": f"Bearer {make_token()}"}

        contact = client.post(
            f"/api/v1/profiles/{profile_id}/emergency-contacts",
            json={
                "name": "Ayesha",
                "phone": SECRETS["phone number"],
                "relationship_label": "Daughter",
            },
            headers=headers,
        )
        assert contact.status_code == 201, contact.json()

        invitation = client.post(
            f"/api/v1/profiles/{profile_id}/caregivers/invitations",
            json={
                "invited_name": "Ayesha",
                "role": "family",
                # ``communication`` is what opens a thread (PRD 9, s31).
                "permissions": {"medications": True, "communication": True},
            },
            headers=headers,
        )
        assert invitation.status_code == 201, invitation.json()
        client.post(
            f"/api/v1/caregiver-invitations/{invitation.json()['token']}/accept",
            headers=helper,
        )
        relationship_id = invitation.json()["caregiver"]["id"]

        thread = client.post(
            f"/api/v1/profiles/{profile_id}/family/threads",
            json={"relationship_id": relationship_id},
            headers=headers,
        )
        assert thread.status_code in (200, 201), thread.json()
        message = client.post(
            f"/api/v1/profiles/{profile_id}/family/threads"
            f"/{thread.json()['id']}/messages",
            json={"message_type": "text", "text": SECRETS["caregiver message"]},
            headers=headers,
        )
        assert message.status_code in (200, 201), message.json()

        assert_absent(captured, SECRETS["caregiver message"], SECRETS["phone number"])

    def test_an_invitation_token_is_not_logged(self, client, account, clock, captured):
        """Not in section 12's list, and it belongs there.

        An invitation token grants caregiver access to somebody's medical
        record. PRD 9 stores it hashed for that reason, and a token in a log
        line would undo the hashing.
        """
        headers, profile_id = account
        invitation = client.post(
            f"/api/v1/profiles/{profile_id}/caregivers/invitations",
            json={"invited_name": "Ayesha", "role": "family", "permissions": {}},
            headers=headers,
        )
        token = invitation.json()["token"]
        client.get(f"/api/v1/caregiver-invitations/{token}", headers=headers)
        assert_absent(captured, token)

    def test_a_safety_event_response_is_not_logged(
        self, client, account, clock, captured
    ):
        headers, profile_id = account
        client.post(
            f"/api/v1/profiles/{profile_id}/emergency-contacts",
            json={"name": "Ayesha", "phone": "07700900999"},
            headers=headers,
        )
        sos = client.post(
            f"/api/v1/profiles/{profile_id}/safety/sos", json={}, headers=headers
        )
        assert sos.status_code in (200, 201), sos.json()
        event_id = sos.json()["id"]
        client.post(
            f"/api/v1/profiles/{profile_id}/safety/events/{event_id}/false-alarm",
            json={"reason": "other", "note": SECRETS["safety event text"]},
            headers=headers,
        )
        assert_absent(captured, SECRETS["safety event text"])

    def test_an_export_logs_counts_rather_than_contents(
        self, client, account, clock, captured
    ):
        """PRD 13's own feature held to PRD 13's own rule.

        An export reads every row this profile has. If anything in the build
        logged what it serialized, this is where it would show.
        """
        headers, profile_id = account
        client.post(
            f"/api/v1/profiles/{profile_id}/conditions",
            json={"name": SECRETS["medical record"], "status": "active"},
            headers=headers,
        )
        captured.messages.clear()

        response = client.post(
            f"/api/v1/profiles/{profile_id}/privacy/export", headers=headers
        )
        assert response.status_code == 201, response.json()

        assert_absent(captured, SECRETS["medical record"])
        # And it did log something, so the absence above is not vacuous.
        assert any("privacy.export" in message for message in captured.messages)

    def test_a_deletion_logs_counts_rather_than_a_name(
        self, client, account, clock, captured
    ):
        headers, profile_id = account
        client.patch(
            f"/api/v1/profiles/{profile_id}",
            json={"preferred_name": "Zubeida"},
            headers=headers,
        )
        captured.messages.clear()

        from app.services.privacy import deletion as deletion_service

        response = client.post(
            f"/api/v1/profiles/{profile_id}/privacy/delete-confirm",
            json={
                "confirmation_phrase": deletion_service.CONFIRMATION_PHRASE,
                "acknowledged": True,
            },
            headers=headers,
        )
        assert response.status_code == 200, response.json()

        assert_absent(captured, "Zubeida")
        assert any("privacy.deletion" in message for message in captured.messages)


class TestTheCaptureItself:
    """A guard on the fixture, so the assertions above cannot pass vacuously."""

    def test_the_handler_sees_application_logs(self, client, account, clock, captured):
        """If this fails, every test above is asserting nothing.

        Which is exactly what happened before ``logger.disabled`` was cleared:
        Alembic's ``fileConfig`` switches off every application logger for the
        session, and a capture handler on a disabled logger records silence.
        """
        logging.getLogger("app.tests").info("a deliberate line")
        assert "a deliberate line" in captured.messages
