"""The Privacy & Security hub, and the secrets audit (PRD 13, ss4-10, 16, 52).

Two groups.

``TestSummary`` checks the hub reads the system rather than restating it: the
capability rows are the maps PRD 10, PRD 11 and PRD 12 already own, the counts
come from the database, and the two sentences a person most needs -- that
Privacy Mode is not a hardware switch, and that nothing has been tested on real
hardware -- are present.

``TestSecrets`` is section 16, which asks for a review rather than a feature.
It is written as tests so the review stays true: `.env` ignored, the example
holding placeholders only, no private key in the app, no user token in the
firmware, and no universal device secret.
"""

import pathlib
from datetime import UTC, datetime

import pytest

from app.api.deps import current_time
from app.main import app
from tests.test_devices import ready_account
from tests.test_today import Clock

NOON = datetime(2026, 10, 12, 12, 0, tzinfo=UTC)
REPO = pathlib.Path("..").resolve()


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
def helper(client, make_token) -> dict[str, str]:
    return {"Authorization": f"Bearer {make_token()}"}


def summary(client, headers, profile_id) -> dict:
    response = client.get(
        f"/api/v1/profiles/{profile_id}/privacy/summary", headers=headers
    )
    assert response.status_code == 200, response.json()
    return response.json()


class TestSummary:
    def test_it_is_one_request(self, client, account, clock):
        """Section 4.

        A privacy screen that arrived in pieces would show somebody a
        half-answer about who can see their data while the rest loaded.
        """
        headers, profile_id = account
        body = summary(client, headers, profile_id)
        for key in (
            "privacy_mode",
            "memory_count",
            "conversation_count",
            "caregivers",
            "safety_capabilities",
            "robot_capabilities",
            "external_capabilities",
            "security_statements",
            "data_categories",
        ):
            assert key in body, key

    def test_privacy_mode_is_read_not_set(self, client, account, clock):
        """Section 5: reuse PRD 8's behaviour rather than adding a setting."""
        headers, profile_id = account
        assert summary(client, headers, profile_id)["privacy_mode"] is False

        changed = client.patch(
            f"/api/v1/profiles/{profile_id}/assistant/preferences",
            json={"mode": "privacy"},
            headers=headers,
        )
        assert changed.status_code == 200, changed.json()

        body = summary(client, headers, profile_id)
        assert body["privacy_mode"] is True
        assert body["assistant_mode"] == "privacy"

    def test_it_says_privacy_mode_is_not_a_hardware_switch(self, client, account, clock):
        """Section 5's last line, which is the one that keeps it honest."""
        body = summary(client, *account[::-1][::-1])
        assert "not a hardware switch" in body["privacy_mode_limit"]

    def test_the_microphone_row_says_nura_never_asked(self, client, account, clock):
        """Section 6.

        The strongest truthful sentence available is that no feature in this
        build listens at all -- so the row says what Nura has never asked for
        rather than what it has turned off, which would be a claim about
        hardware nobody queried.
        """
        headers, profile_id = account
        body = summary(client, headers, profile_id)
        assert "does not listen" in body["microphone_note"]
        assert "does not watch" in body["camera_note"]

    def test_the_safety_rows_are_prd_10s_own_map(self, client, account, clock):
        """Section 9: no hard-coded optimistic wording."""
        headers, profile_id = account
        rows = {
            row["key"]: row
            for row in summary(client, headers, profile_id)["safety_capabilities"]
        }
        assert rows["manual_sos"]["state"] == "available"
        # Because no provider exists, not because a screen says so.
        assert rows["push_delivery"]["state"] == "not_configured"
        assert rows["sms_delivery"]["state"] == "not_configured"
        assert rows["robot_detection"]["state"] == "not_connected"

    def test_the_robot_rows_are_all_twelve_even_with_no_robot(
        self, client, account, clock
    ):
        """Section 10, and PRD 11's reason for returning every key.

        A screen that only lists what happens to be reported is a screen that
        silently stops mentioning one. With no robot linked the states are
        honest absences rather than "off".
        """
        headers, profile_id = account
        body = summary(client, headers, profile_id)
        assert body["robot_linked"] is False
        assert len(body["robot_capabilities"]) == 12
        assert body["robot_previews"] == []
        states = {row["state"] for row in body["robot_capabilities"]}
        assert "available" not in states

    def test_the_robot_rows_follow_the_device_once_linked(
        self, client, account, clock, db
    ):
        headers, profile_id = account
        from tests.test_robot_presentations import seed_device

        seed_device(db, client, headers, profile_id=profile_id)

        body = summary(client, headers, profile_id)
        assert body["robot_linked"] is True
        # The preview levels, read from the device's own preferences.
        labels = {label for label, _ in body["robot_previews"]}
        assert "Medication reminders" in labels
        assert "Tasks and routines" in labels

    def test_the_external_rows_are_not_configured(self, client, account, clock):
        """Section 37, from PRD 12's derived map."""
        headers, profile_id = account
        rows = {
            row["key"]: row
            for row in summary(client, headers, profile_id)["external_capabilities"]
        }
        assert set(rows) == {"weather", "news", "external_calendar"}
        for row in rows.values():
            assert row["state"] == "not_configured"
        # PRD 12's three sentences, which differ on purpose: two say "in this
        # build" and the calendar one says what Nura *can* still do. Asserting
        # a shared phrase would force them to be the same sentence, and
        # section 28's point is that the calendar answer is the useful one.
        assert "this build" in rows["weather"]["state_label"]
        assert "this build" in rows["news"]["state_label"]
        assert "not connected" in rows["external_calendar"]["state_label"]

    def test_the_caregiver_rows_are_the_granted_categories(
        self, client, account, helper, clock
    ):
        """Section 8: what each person can see, from the server."""
        headers, profile_id = account
        created = client.post(
            f"/api/v1/profiles/{profile_id}/caregivers/invitations",
            json={
                "invited_name": "Ayesha",
                "role": "family",
                "permissions": {"medications": True, "appointments": True},
            },
            headers=headers,
        )
        assert created.status_code == 201, created.json()
        client.post(
            f"/api/v1/caregiver-invitations/{created.json()['token']}/accept",
            headers=helper,
        )

        rows = summary(client, headers, profile_id)["caregivers"]
        assert len(rows) == 1
        assert rows[0]["name"] == "Ayesha"
        assert sorted(rows[0]["granted"]) == ["appointments", "medications"]

    def test_a_revoked_caregiver_is_not_listed(self, client, account, helper, clock):
        headers, profile_id = account
        created = client.post(
            f"/api/v1/profiles/{profile_id}/caregivers/invitations",
            json={"invited_name": "Ayesha", "role": "family", "permissions": {}},
            headers=headers,
        )
        relationship_id = created.json()["caregiver"]["id"]
        client.post(
            f"/api/v1/caregiver-invitations/{created.json()['token']}/accept",
            headers=helper,
        )
        assert len(summary(client, headers, profile_id)["caregivers"]) == 1

        client.delete(
            f"/api/v1/profiles/{profile_id}/caregivers/{relationship_id}",
            headers=headers,
        )
        assert summary(client, headers, profile_id)["caregivers"] == []

    def test_it_says_nothing_has_been_tested_on_hardware(self, client, account, clock):
        """Section 36, in one sentence rather than on every screen."""
        headers, profile_id = account
        note = summary(client, headers, profile_id)["build_honesty_note"]
        assert "physical phone" in note
        assert "physical robot" in note

    def test_a_caregiver_cannot_read_the_hub(self, client, account, helper, clock):
        """It is an owner surface. Granting every category changes nothing."""
        from app.models.enums import CAREGIVER_PERMISSION_KEYS

        headers, profile_id = account
        created = client.post(
            f"/api/v1/profiles/{profile_id}/caregivers/invitations",
            json={
                "invited_name": "Ayesha",
                "role": "family",
                "permissions": dict.fromkeys(CAREGIVER_PERMISSION_KEYS, True),
            },
            headers=headers,
        )
        client.post(
            f"/api/v1/caregiver-invitations/{created.json()['token']}/accept",
            headers=helper,
        )
        response = client.get(
            f"/api/v1/profiles/{profile_id}/privacy/summary", headers=helper
        )
        assert response.status_code == 404


class TestBulkConversationDelete:
    """Section 7, and the thing it must not take with it."""

    def test_it_removes_conversations_and_nothing_else(
        self, client, account, clock, scripted
    ):
        from app.services.assistant.provider import ScriptedReply

        headers, profile_id = account
        client.post(
            f"/api/v1/profiles/{profile_id}/conditions",
            json={"name": "Hypertension", "status": "active"},
            headers=headers,
        )
        client.post(
            f"/api/v1/profiles/{profile_id}/assistant/memories",
            json={"category": "preferences", "content": "Call me by my middle name"},
            headers=headers,
        )
        scripted.queue(ScriptedReply(text="Noted."))
        conversation = client.post(
            f"/api/v1/profiles/{profile_id}/assistant/conversations",
            json={},
            headers=headers,
        )
        conversation_id = conversation.json()["id"]
        client.post(
            f"/api/v1/profiles/{profile_id}/assistant/conversations"
            f"/{conversation_id}/messages",
            json={"content": "Hello"},
            headers=headers,
        )

        response = client.post(
            f"/api/v1/profiles/{profile_id}/privacy/conversations/delete-all",
            headers=headers,
        )
        assert response.status_code == 200, response.json()
        assert response.json()["deleted"] == 1
        # And the response says what stayed, because this is the one place
        # somebody might fear they deleted more than they did.
        assert "health record" in response.json()["note"]

        assert (
            client.get(
                f"/api/v1/profiles/{profile_id}/assistant/conversations",
                headers=headers,
            ).json()["conversations"]
            == []
        )
        # The memory and the medical record are untouched (section 7).
        memories = client.get(
            f"/api/v1/profiles/{profile_id}/assistant/memories", headers=headers
        ).json()
        assert len(memories["memories"]) == 1
        conditions = client.get(
            f"/api/v1/profiles/{profile_id}/conditions", headers=headers
        ).json()
        assert len(conditions) == 1

    def test_it_is_fine_with_nothing_to_delete(self, client, account, clock):
        headers, profile_id = account
        response = client.post(
            f"/api/v1/profiles/{profile_id}/privacy/conversations/delete-all",
            headers=headers,
        )
        assert response.status_code == 200
        assert response.json()["deleted"] == 0


class TestSecrets:
    """Section 16's review, written as tests so it stays true."""

    def test_env_files_are_ignored_except_the_example(self):
        ignore = (REPO / ".gitignore").read_text(encoding="utf-8")
        assert ".env" in ignore
        assert ".env.*" in ignore
        assert "!.env.example" in ignore

    def test_the_example_holds_placeholders_only(self):
        """Every assignment is empty or an obvious local placeholder.

        A real key committed to the template is the single easiest way for a
        secret to reach a repository, and it would look exactly like the lines
        around it.
        """
        text = (REPO / ".env.example").read_text(encoding="utf-8")
        suspicious = []
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            _, _, value = stripped.partition("=")
            value = value.strip().strip("'\"")
            if not value:
                continue
            # What a placeholder may look like: a local URL, a local database
            # name, a development flag, a short word.
            local = (
                value.startswith(("http://localhost", "postgresql+psycopg://nura:"))
                or value in {"development", "true", "false", "scripted", "local"}
                or "change_me" in value
                or "example" in value
                or len(value) < 24
            )
            if not local:
                suspicious.append(stripped)
        assert suspicious == [], suspicious

    def test_the_app_carries_no_private_provider_key(self):
        """Only ``EXPO_PUBLIC_*`` reaches the bundle, and only public values.

        The app reads configuration in exactly one place, which is what makes
        this checkable at all.
        """
        config = (REPO / "mobile/src/constants/config.ts").read_text(encoding="utf-8")
        for line in config.splitlines():
            stripped = line.strip()
            # Comments explain the rule; code has to follow it.
            if stripped.startswith(("//", "*", "/*")):
                continue
            if "process.env" not in stripped:
                continue
            assert "EXPO_PUBLIC_" in stripped, stripped
        # And the model provider's key is never one of them.
        assert "AI_API_KEY" not in config
        assert "SUPABASE_SERVICE" not in config

    def test_no_source_file_outside_config_reads_the_environment(self):
        """PRD 0's rule, and the reason the check above is sufficient.

        Comments are skipped. Several files explain *why* they do not read the
        environment, and a check that counted those would push people into
        deleting the explanation to make it pass.
        """
        offenders = []
        for path in (REPO / "mobile/src").rglob("*.ts"):
            if path.name == "config.ts":
                continue
            for line in path.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if stripped.startswith(("//", "*", "/*")):
                    continue
                if "process.env" in stripped:
                    offenders.append(f"{path.as_posix()}: {stripped}")
        assert offenders == []

    def test_the_firmware_holds_no_user_access_token(self):
        """A robot authenticates as itself, never as the person.

        PRD 5 section 94 and PRD 11 section 69: the device has its own token,
        the profile comes from the device record, and nothing on the board is
        ever the user's own credential.
        """
        firmware = REPO / "firmware/xiao_esp32s3/src"
        for path in firmware.rglob("*.*"):
            text = path.read_text(encoding="utf-8", errors="ignore")
            assert "access_token" not in text, path.as_posix()
            assert "refresh_token" not in text, path.as_posix()

    def test_the_bootstrap_secret_is_generated_rather_than_compiled_in(self):
        """Section 16's last line.

        A bootstrap credential shared by every board would mean one leak
        compromised all of them. PRD 2 generates one per device on first boot
        and stores it in NVS; the backend keeps only a hash.

        Checked by what the firmware *does* rather than by scanning strings: a
        string scan reads ``request["bootstrap_secret"] = …`` as a finding,
        because the literal there is the JSON field name. What matters is that
        the value comes from a function call into the identity module, and
        that no constant anywhere declares one.
        """
        firmware = REPO / "firmware/xiao_esp32s3/src"
        sources = list(firmware.rglob("*.cpp")) + list(firmware.rglob("*.h"))

        # It is produced at runtime, per device.
        uses = [
            path.as_posix()
            for path in sources
            if "bootstrapSecret()" in path.read_text(encoding="utf-8", errors="ignore")
        ]
        assert uses, "the firmware should read its bootstrap secret from identity"

        # And nothing declares one as a constant.
        for path in sources:
            for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
                stripped = line.strip()
                if stripped.startswith(("//", "*", "/*")):
                    continue
                lowered = stripped.lower()
                declares = stripped.startswith(("#define", "constexpr", "static const"))
                if declares and ("secret" in lowered or "password" in lowered):
                    # A length limit rather than a ban, because the honest
                    # matches are short: ``KEY_PASSWORD = "pass"`` is the NVS
                    # key the Wi-Fi password is *stored under*, and an NVS key
                    # cannot exceed fifteen characters. No credential worth
                    # having is that short.
                    quoted = stripped.split('"')
                    value = quoted[1] if len(quoted) >= 3 else ""
                    assert len(value) < 16, f"{path.as_posix()}: {stripped}"
