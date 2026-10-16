"""The model boundary (PRD 8, sections 10, 55, 76, 98 and 101).

Section 101 asks for the adapter to be tested against a fake provider,
covering a normal response, streaming, a timeout, a provider failure, a
malformed tool call and a rate limit -- and for no paid model call to be
needed. Every case is here and **nothing in this file reaches the network**.

Two halves.

``TestAnthropicAdapter`` exercises the real ``AnthropicProvider`` with its
HTTP client replaced by a stub that records what it was handed. That proves
what the adapter *builds* and how it reads a reply back: the streaming helper
is used, tool results land in a user turn, a refusal is recognised, a
malformed tool input is rejected. What it cannot prove is that Anthropic
accepts the request -- no key exists in this repository and no request has
ever been sent, which is stated in the adapter's own docstring and in the
documentation.

``TestFailureTranslation`` and ``TestThroughTheService`` cover the rule that
matters more than any of it: section 55 says no raw provider errors, and the
user-facing sentence for every failure kind is one of a fixed set that names
no provider, no model and no status code.
"""

from datetime import UTC, datetime

import anthropic
import httpx2
import pytest

from app.api.deps import current_time
from app.core.config import Settings, get_settings
from app.main import app
from app.services.assistant import prompts
from app.services.assistant.anthropic_provider import FALLBACK_BETA, AnthropicProvider
from app.services.assistant.provider import (
    AIModelProvider,
    MalformedReplyError,
    ProviderNotConfiguredError,
    ProviderRateLimitError,
    ProviderRequest,
    ProviderTimeoutError,
    ProviderUnavailableError,
    ScriptedProvider,
    ScriptedReply,
    ToolCall,
    ToolResult,
    ToolSpec,
    Turn,
    UnconfiguredProvider,
    build_provider,
)
from tests.test_assistant import say, start_conversation
from tests.test_devices import ready_account
from tests.test_today import Clock

#: A Monday at noon. The same moment ``test_assistant`` uses, so a reader
#: comparing the two files is comparing like with like.
NOW = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)


@pytest.fixture
def clock(client) -> Clock:
    """A settable clock, injected in place of the real one.

    Defined here rather than imported: a fixture is resolved by name in the
    module it is used from, and importing one only works by leaving an
    otherwise-unused name in the namespace.
    """
    fake = Clock()
    fake.now = NOW
    app.dependency_overrides[current_time] = lambda: fake.now
    return fake


@pytest.fixture
def account(client, make_token) -> tuple[dict[str, str], str]:
    """A ready account and the profile its conversations belong to."""
    headers = ready_account(client, make_token)
    profile_id = client.get("/api/v1/me", headers=headers).json()["profiles"][0]["id"]
    return headers, profile_id


REQUEST = httpx2.Request("POST", "https://api.example.invalid/v1/messages")
RESPONSE = httpx2.Response(429, request=REQUEST)


# --- stubs ------------------------------------------------------------------


class _Block:
    def __init__(self, **fields: object) -> None:
        self.__dict__.update(fields)


class _Usage:
    input_tokens = 120
    output_tokens = 40


class _Message:
    """Shaped like a provider message, with only the fields we read."""

    def __init__(self, content, stop_reason="end_turn", model="claude-opus-5"):
        self.content = content
        self.stop_reason = stop_reason
        self.model = model
        self.usage = _Usage()
        self.stop_details = None


class _Stream:
    def __init__(self, message, recorder, kwargs):
        self._message = message
        self._recorder = recorder
        self._kwargs = kwargs

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        self._recorder["streamed"] = True
        return self._message


class _Messages:
    def __init__(self, recorder, label):
        self._recorder = recorder
        self._label = label

    def stream(self, **kwargs):
        self._recorder["path"] = self._label
        self._recorder["kwargs"] = kwargs
        if self._recorder.get("raises") is not None:
            raise self._recorder["raises"]
        return _Stream(self._recorder["message"], self._recorder, kwargs)


class _Client:
    """Stands in for ``anthropic.Anthropic``. Records, never connects."""

    def __init__(self, recorder):
        self.messages = _Messages(recorder, "plain")
        self.beta = _Block(messages=_Messages(recorder, "beta"))


def adapter(*, fallbacks: bool = True, message=None, raises=None):
    """A real ``AnthropicProvider`` with a recording client in place of HTTP."""
    settings = Settings(
        database_url=get_settings().database_url,
        ai_provider="anthropic",
        ai_api_key="test-key-not-real",
        ai_model="claude-opus-5",
        ai_effort="low",
        ai_server_side_fallback=fallbacks,
    )
    provider = AnthropicProvider(settings)
    recorder: dict = {
        "message": message or _Message([_Block(type="text", text="Hello.")]),
        "raises": raises,
    }
    provider._client = _Client(recorder)  # type: ignore[assignment]
    return provider, recorder


def a_request(**overrides) -> ProviderRequest:
    defaults = {
        "system": "You are Nura.",
        "turns": (Turn(role="user", text="Hello"),),
        "tools": (),
        "max_output_tokens": 500,
    }
    return ProviderRequest(**{**defaults, **overrides})


# --- choosing a provider ----------------------------------------------------


class TestProviderSelection:
    def test_nothing_configured_means_nothing_pretends(self):
        """Section 76: no key, no assistant, and a clear answer either way."""
        settings = Settings(database_url=get_settings().database_url)
        provider = build_provider(settings)
        assert isinstance(provider, UnconfiguredProvider)
        assert settings.assistant_configured is False
        with pytest.raises(ProviderNotConfiguredError):
            provider.complete(a_request())

    def test_anthropic_without_a_key_is_not_configured(self):
        settings = Settings(
            database_url=get_settings().database_url, ai_provider="anthropic"
        )
        assert settings.assistant_configured is False
        assert isinstance(build_provider(settings), UnconfiguredProvider)

    def test_anthropic_with_a_key_builds_the_adapter(self):
        settings = Settings(
            database_url=get_settings().database_url,
            ai_provider="anthropic",
            ai_api_key="test-key-not-real",
        )
        assert settings.assistant_configured is True
        assert isinstance(build_provider(settings), AnthropicProvider)

    def test_the_scripted_provider_is_refused_in_production(self):
        """Section 104: no production fixture controls.

        A canned-reply assistant in production would be a Nura that says the
        same thing to everybody and means none of it.
        """
        settings = Settings(
            database_url=get_settings().database_url,
            ai_provider="scripted",
            app_env="production",
        )
        with pytest.raises(ProviderNotConfiguredError):
            build_provider(settings)

    def test_the_scripted_provider_is_allowed_in_development(self):
        settings = Settings(
            database_url=get_settings().database_url,
            ai_provider="scripted",
            app_env="development",
        )
        assert isinstance(build_provider(settings), ScriptedProvider)

    def test_the_abstraction_is_one_method(self):
        """Section 10: a provider is swappable because there is little to swap."""
        assert AIModelProvider.complete.__isabstractmethod__ is True
        overridable = [
            name
            for name in dir(AIModelProvider)
            if not name.startswith("_") and callable(getattr(AIModelProvider, name))
        ]
        assert overridable == ["complete"]


# --- the adapter ------------------------------------------------------------


class TestAnthropicAdapter:
    def test_a_normal_response_comes_back_translated(self):
        """Section 101: normal response."""
        provider, recorder = adapter()
        reply = provider.complete(a_request())
        assert reply.text == "Hello."
        assert reply.stop_reason == "end_turn"
        assert reply.model == "claude-opus-5"
        assert (reply.input_tokens, reply.output_tokens) == (120, 40)

    def test_it_streams_the_fetch(self):
        """Section 101: streaming.

        A long answer over a slow link is the classic way to hit an HTTP
        timeout. The reply still arrives complete -- guardrails run after the
        model, so nothing is shown and then withdrawn (section 54).
        """
        provider, recorder = adapter()
        provider.complete(a_request())
        assert recorder["streamed"] is True

    def test_the_fallback_beta_is_sent_when_it_is_switched_on(self):
        provider, recorder = adapter(fallbacks=True)
        provider.complete(a_request())
        assert recorder["path"] == "beta"
        assert recorder["kwargs"]["betas"] == [FALLBACK_BETA]
        assert recorder["kwargs"]["fallbacks"] == "default"

    def test_switching_the_fallback_off_uses_the_plain_endpoint(self):
        """Harmless to turn off, for an account not enrolled in the beta."""
        provider, recorder = adapter(fallbacks=False)
        provider.complete(a_request())
        assert recorder["path"] == "plain"
        assert "betas" not in recorder["kwargs"]

    def test_the_request_carries_the_system_prompt_and_the_effort(self):
        provider, recorder = adapter()
        provider.complete(a_request(system="You are Nura."))
        kwargs = recorder["kwargs"]
        assert kwargs["system"] == "You are Nura."
        assert kwargs["model"] == "claude-opus-5"
        assert kwargs["max_tokens"] == 500
        assert kwargs["output_config"] == {"effort": "low"}

    def test_tools_are_offered_but_never_forced(self):
        """Whether a question needs stored data is the model's judgement."""
        provider, recorder = adapter()
        spec = ToolSpec(
            name="get_today_summary",
            description="Today.",
            parameters={"type": "object", "properties": {}},
        )
        provider.complete(a_request(tools=(spec,)))
        kwargs = recorder["kwargs"]
        assert kwargs["tool_choice"] == {"type": "auto"}
        assert kwargs["tools"][0]["name"] == "get_today_summary"

    def test_turns_become_content_blocks_in_the_right_roles(self):
        provider, recorder = adapter()
        provider.complete(
            a_request(
                turns=(
                    Turn(role="user", text="What's on today?"),
                    Turn(
                        role="assistant",
                        tool_calls=(
                            ToolCall(id="t1", name="get_today_summary", arguments={}),
                        ),
                    ),
                    Turn(
                        role="user",
                        tool_results=(ToolResult(call_id="t1", content="Nothing due."),),
                    ),
                )
            )
        )
        messages = recorder["kwargs"]["messages"]
        assert [message["role"] for message in messages] == [
            "user",
            "assistant",
            "user",
        ]
        assert messages[1]["content"][0]["type"] == "tool_use"
        assert messages[2]["content"][0] == {
            "type": "tool_result",
            "tool_use_id": "t1",
            "content": "Nothing due.",
        }

    def test_an_empty_text_block_is_not_sent(self):
        """A text block with nothing in it is rejected by the API."""
        provider, recorder = adapter()
        provider.complete(
            a_request(
                turns=(
                    Turn(role="user", text="Hi"),
                    Turn(
                        role="assistant",
                        text="",
                        tool_calls=(ToolCall(id="t1", name="x", arguments={}),),
                    ),
                )
            )
        )
        blocks = recorder["kwargs"]["messages"][1]["content"]
        assert all(block["type"] != "text" for block in blocks)

    def test_a_failed_tool_result_is_marked(self):
        provider, recorder = adapter()
        provider.complete(
            a_request(
                turns=(
                    Turn(
                        role="user",
                        tool_results=(
                            ToolResult(call_id="t1", content="No.", is_error=True),
                        ),
                    ),
                )
            )
        )
        assert recorder["kwargs"]["messages"][0]["content"][0]["is_error"] is True

    def test_tool_calls_are_read_back(self):
        provider, _ = adapter(
            message=_Message(
                [
                    _Block(type="text", text="Let me check."),
                    _Block(
                        type="tool_use",
                        id="t1",
                        name="get_today_summary",
                        input={"foo": "bar"},
                    ),
                ],
                stop_reason="tool_use",
            )
        )
        reply = provider.complete(a_request())
        assert reply.stop_reason == "tool_use"
        assert reply.tool_calls[0].name == "get_today_summary"
        assert reply.tool_calls[0].arguments == {"foo": "bar"}

    def test_a_malformed_tool_call_is_refused(self):
        """Section 101: malformed tool call.

        Non-object arguments cannot be validated against a schema, so they
        are rejected at the boundary rather than handed on as a dict-ish
        thing that fails somewhere less obvious.
        """
        provider, _ = adapter(
            message=_Message(
                [_Block(type="tool_use", id="t1", name="x", input="not an object")],
                stop_reason="tool_use",
            )
        )
        with pytest.raises(MalformedReplyError):
            provider.complete(a_request())

    def test_a_refusal_is_reported_rather_than_raised(self):
        """It arrives as a 200 with nothing usable in it."""
        message = _Message([], stop_reason="refusal")
        message.stop_details = _Block(category="cyber")
        provider, _ = adapter(message=message)

        reply = provider.complete(a_request())
        assert reply.stop_reason == "refusal"
        assert reply.refusal_category == "cyber"
        assert reply.text == ""

    def test_an_unknown_stop_reason_is_treated_as_a_finished_turn(self):
        """A reply with text in it is still a reply."""
        provider, _ = adapter(
            message=_Message(
                [_Block(type="text", text="Done.")], stop_reason="something_new"
            )
        )
        assert provider.complete(a_request()).stop_reason == "end_turn"

    @pytest.mark.parametrize(
        ("raised", "expected"),
        [
            (anthropic.APITimeoutError(request=REQUEST), ProviderTimeoutError),
            (
                anthropic.RateLimitError("slow down", response=RESPONSE, body=None),
                ProviderRateLimitError,
            ),
            (
                anthropic.AuthenticationError(
                    "bad key", response=httpx2.Response(401, request=REQUEST), body=None
                ),
                ProviderUnavailableError,
            ),
            (
                anthropic.APIStatusError(
                    "boom", response=httpx2.Response(500, request=REQUEST), body=None
                ),
                ProviderUnavailableError,
            ),
            (anthropic.APIConnectionError(request=REQUEST), ProviderUnavailableError),
        ],
    )
    def test_every_provider_exception_is_translated(self, raised, expected):
        """Section 101: timeout, provider failure, rate limit.

        And section 55: nothing below the abstraction escapes as itself.
        """
        provider, _ = adapter(raises=raised)
        with pytest.raises(expected):
            provider.complete(a_request())


# --- what the user is told --------------------------------------------------


class TestFailureTranslation:
    def test_every_failure_kind_has_a_sentence(self):
        for error in (
            ProviderNotConfiguredError,
            ProviderTimeoutError,
            ProviderRateLimitError,
            ProviderUnavailableError,
            MalformedReplyError,
        ):
            assert error.reason in prompts.FAILURE_MESSAGES

    def test_no_failure_sentence_names_a_provider_or_a_status(self):
        """Section 98: no provider or model stack traces."""
        for message in prompts.FAILURE_MESSAGES.values():
            lowered = message.lower()
            for leak in (
                "anthropic",
                "claude",
                "openai",
                "http",
                "500",
                "429",
                "token",
                "api key",
                "traceback",
                "exception",
            ):
                assert leak not in lowered


# --- through the whole service ----------------------------------------------


class TestThroughTheService:
    def test_a_timeout_reaches_the_user_as_one_sentence(
        self, client, account, clock, scripted
    ):
        headers, profile_id = account
        scripted.queue(ScriptedReply(error=ProviderTimeoutError("slow")))
        conversation = start_conversation(client, headers, profile_id)
        result = say(client, headers, profile_id, conversation["id"], "Hello")
        assert result["failure_message"] == prompts.FAILURE_MESSAGES["timeout"]

    def test_a_rate_limited_provider_is_not_the_users_fault(
        self, client, account, clock, scripted
    ):
        """Distinct from Nura's own per-profile limit, which is a 429."""
        headers, profile_id = account
        scripted.queue(ScriptedReply(error=ProviderRateLimitError("busy")))
        conversation = start_conversation(client, headers, profile_id)
        result = say(client, headers, profile_id, conversation["id"], "Hello")
        assert result["failure"] == "rate_limited"
        assert "busy" in result["failure_message"]

    def test_a_provider_refusal_is_answered_plainly(
        self, client, account, clock, scripted
    ):
        headers, profile_id = account
        scripted.queue(ScriptedReply(text="", stop_reason="refusal"))
        conversation = start_conversation(client, headers, profile_id)
        result = say(client, headers, profile_id, conversation["id"], "Hello")
        assert result["failure"] == "refused"
        assert result["reply"] is None

    def test_an_empty_reply_counts_as_a_failure(self, client, account, clock, scripted):
        """A 200 with nothing in it is a failure that happened to succeed."""
        headers, profile_id = account
        scripted.queue(ScriptedReply(text="   "))
        conversation = start_conversation(client, headers, profile_id)
        result = say(client, headers, profile_id, conversation["id"], "Hello")
        assert result["failure"] == "malformed_reply"

    def test_a_tool_call_for_a_tool_that_does_not_exist_recovers(
        self, client, account, clock, scripted
    ):
        """Section 101: malformed tool call, seen from the service.

        The model is told the tool does not exist and answers anyway, rather
        than the request failing.
        """
        headers, profile_id = account
        scripted.queue(
            ScriptedReply(
                stop_reason="tool_use",
                tool_calls=(ToolCall(id="t1", name="delete_everything", arguments={}),),
            ),
            ScriptedReply(text="Sorry, I can't do that."),
        )
        conversation = start_conversation(client, headers, profile_id)
        result = say(client, headers, profile_id, conversation["id"], "Delete my data")

        assert result["reply"]["content"] == "Sorry, I can't do that."
        tool_turn = scripted.requests[-1].turns[-1]
        assert tool_turn.tool_results[0].is_error is True

    def test_a_model_that_only_calls_tools_is_stopped(
        self, client, account, clock, scripted
    ):
        """The loop has a ceiling, and the last thing said is kept."""
        from app.services.assistant.service import MAX_TOOL_ROUNDS

        headers, profile_id = account
        for _ in range(MAX_TOOL_ROUNDS + 1):
            scripted.queue(
                ScriptedReply(
                    text="Still looking.",
                    stop_reason="tool_use",
                    tool_calls=(
                        ToolCall(id="t", name="get_today_summary", arguments={}),
                    ),
                )
            )
        conversation = start_conversation(client, headers, profile_id)
        result = say(client, headers, profile_id, conversation["id"], "Loop please")

        assert result["reply"]["content"] == "Still looking."
        assert len(scripted.requests) == MAX_TOOL_ROUNDS + 1

    def test_the_model_and_prompt_version_are_recorded(
        self, client, account, clock, scripted
    ):
        """Section 80's metadata -- and nothing beyond it."""
        headers, profile_id = account
        scripted.queue(ScriptedReply(text="Hello."))
        conversation = start_conversation(client, headers, profile_id)
        result = say(client, headers, profile_id, conversation["id"], "Hi")

        meta = result["reply"]["meta"]
        assert meta["model"] == "scripted"
        assert meta["prompt_version"] == prompts.PROMPT_VERSION
        assert meta["latency_ms"] >= 0
        assert set(meta) == {
            "model",
            "latency_ms",
            "tools",
            "safety_mode",
            "prompt_version",
            "truncated",
        }

    def test_no_prompt_or_chain_of_thought_is_ever_returned(
        self, client, account, clock, scripted
    ):
        """Section 80: do not store hidden chain-of-thought -- or return it."""
        headers, profile_id = account
        scripted.queue(ScriptedReply(text="Hello."))
        conversation = start_conversation(client, headers, profile_id)
        result = say(client, headers, profile_id, conversation["id"], "Hi")

        body = str(result)
        assert "Health Information Assistant" not in body
        assert "USER-PROVIDED" not in body

    def test_a_truncated_reply_says_so(self, client, account, clock, scripted):
        headers, profile_id = account
        scripted.queue(ScriptedReply(text="It began", stop_reason="max_tokens"))
        conversation = start_conversation(client, headers, profile_id)
        result = say(client, headers, profile_id, conversation["id"], "Tell me a saga")
        assert result["reply"]["meta"]["truncated"] is True
