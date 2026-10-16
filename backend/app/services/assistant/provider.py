"""The boundary between Nura and whatever model answers for it.

PRD 8, sections 10, 55 and 101.

Everything above this file speaks in the vocabulary defined here -- turns,
tool calls, tool results, a reply -- and nothing above it imports a provider
SDK or knows a provider's wire format. That is the whole point of section 10:
the model behind Nura should be a deployment decision, not an architectural
one.

The shapes are deliberately smaller than any provider's API. A ``Turn`` is a
role plus text plus whichever tool calls or results belong to it; a
``ProviderReply`` is text, the tools the model wants to run, and why it
stopped. Features no Nura workflow uses -- images in conversation, citations,
server-side tools, prefill -- have no representation here, because a shape
nothing fills is a shape the next provider has to emulate for no reason.

**Errors are translated, never passed through** (sections 55 and 98). Every
failure below this line becomes one of the ``ProviderError`` subclasses, and
the caller turns that into one of the few sentences Nura is allowed to say. A
provider stack trace, a model name in an error, a rate-limit body: none of
them reach a user, and none of them reach a log with conversation text
attached.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Literal

from app.core.config import Settings, get_settings

#: What a reply's ``stop_reason`` can be, once translated out of a provider's
#: own vocabulary. ``refusal`` means the provider's own safety layer declined
#: -- distinct from Nura's guardrails, which never reach the provider at all.
StopReason = Literal["end_turn", "tool_use", "max_tokens", "refusal"]

#: Who is speaking in a turn sent *to* the provider.
TurnRole = Literal["user", "assistant"]


@dataclass(frozen=True)
class ToolCall:
    """A tool the model asked to run, with the arguments it proposed.

    ``arguments`` is whatever the model produced and is **not** trusted: it is
    validated against the tool's schema before anything runs (section 91).
    """

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ToolResult:
    """What running a tool produced, on its way back to the model."""

    call_id: str
    content: str
    is_error: bool = False


@dataclass(frozen=True)
class Turn:
    """One exchange in the transcript sent to the provider.

    A user turn carries either text or tool results; an assistant turn carries
    text and any tool calls. Keeping both on one shape means the conversation
    sent to a provider is a flat list, which is what every provider wants.
    """

    role: TurnRole
    text: str = ""
    tool_calls: tuple[ToolCall, ...] = ()
    tool_results: tuple[ToolResult, ...] = ()


@dataclass(frozen=True)
class ToolSpec:
    """A tool offered to the model.

    ``parameters`` is a JSON Schema object. Nura's tools all declare
    ``additionalProperties: false`` and list their required fields, so a
    provider that supports strict validation can reject a malformed call
    before it is ever returned -- and the tool layer validates again anyway,
    because "the provider checked" is not an authorization model.
    """

    name: str
    description: str
    parameters: dict[str, Any]


@dataclass(frozen=True)
class ProviderRequest:
    """One call to the model."""

    system: str
    turns: tuple[Turn, ...]
    tools: tuple[ToolSpec, ...] = ()
    max_output_tokens: int = 1024


@dataclass(frozen=True)
class ProviderReply:
    """What came back.

    ``text`` is the visible answer. ``tool_calls`` is non-empty only when
    ``stop_reason`` is ``tool_use``. Token counts are recorded so cost can be
    watched (section 77); they are numbers, and carry no conversation content.
    """

    text: str
    stop_reason: StopReason = "end_turn"
    tool_calls: tuple[ToolCall, ...] = ()
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    #: Set when the provider's own safety layer declined, for the log line.
    #: Never shown to a user.
    refusal_category: str | None = None


# --- failures ---------------------------------------------------------------


class ProviderError(Exception):
    """Something went wrong below the abstraction.

    Carries a ``reason`` short enough to log as a single stable token. The
    message is for developers; what a user sees is chosen by the caller from
    the fixed set in ``copy.py``.
    """

    reason = "provider_error"


class ProviderNotConfiguredError(ProviderError):
    """No provider is set up on this deployment (PRD 8, section 76)."""

    reason = "not_configured"


class ProviderUnavailableError(ProviderError):
    """The provider could not be reached, or refused the request outright."""

    reason = "unavailable"


class ProviderTimeoutError(ProviderError):
    """The provider took longer than ``AI_TIMEOUT_SECONDS``."""

    reason = "timeout"


class ProviderRateLimitError(ProviderError):
    """The provider is rate-limiting this deployment."""

    reason = "rate_limited"


class ProviderRefusedError(ProviderError):
    """The provider's own safety layer declined to answer."""

    reason = "refused"


class MalformedReplyError(ProviderError):
    """The reply did not have a shape this code can use."""

    reason = "malformed_reply"


# --- the abstraction --------------------------------------------------------


class AIModelProvider(ABC):
    """What Nura needs from a model.

    One method. Streaming is a property of how a provider fetches a reply --
    the Anthropic adapter streams, because that is what keeps a long answer
    from hitting an HTTP timeout -- and not a second thing callers choose
    between. PRD 8 section 54 makes streaming to the *app* optional, and it is
    deliberately not implemented: a partial answer that is then withdrawn by a
    guardrail is worse than a short wait, and every reply here passes through
    a guardrail.
    """

    #: Stable identifier for logs and message metadata.
    name: str = "provider"

    @abstractmethod
    def complete(self, request: ProviderRequest) -> ProviderReply:
        """Sends one request and returns one reply, or raises ``ProviderError``."""


class UnconfiguredProvider(AIModelProvider):
    """Stands in when no provider is set up.

    Every call fails the same way, immediately, so a deployment without an
    ``AI_API_KEY`` gets a clear answer instead of a hang or a fabricated
    reply. PRD 8 section 55 says no raw provider errors; this is the case
    where there is no provider to get one from.
    """

    name = "unconfigured"

    def complete(self, request: ProviderRequest) -> ProviderReply:
        raise ProviderNotConfiguredError(
            "No AI provider is configured. Set AI_PROVIDER and AI_API_KEY."
        )


@dataclass
class ScriptedReply:
    """One canned reply, for tests and development fixtures."""

    text: str = ""
    tool_calls: tuple[ToolCall, ...] = ()
    stop_reason: StopReason = "end_turn"
    #: Raised instead of returning, when a test wants a failure.
    error: ProviderError | None = None


class ScriptedProvider(AIModelProvider):
    """Replays prepared replies in order (PRD 8, sections 101 and 104).

    Exists so the assistant can be tested end to end -- guardrails, tools,
    memory suggestions, error handling -- without a paid model call, which
    section 101 asks for directly, and so the development fixtures in section
    104 can include a timeout and a provider error without anybody unplugging
    a network cable.

    It records the requests it received, so a test can assert what was *sent*:
    that is how "the context builder did not include unrelated medical notes"
    and "the custom instruction was fenced as untrusted data" are checked.

    Selecting it needs ``AI_PROVIDER=scripted``, and ``get_provider`` refuses
    that outside development -- PRD 8 section 104 rules out production fixture
    controls.
    """

    name = "scripted"

    def __init__(self, replies: list[ScriptedReply] | None = None) -> None:
        self.replies: list[ScriptedReply] = list(replies or [])
        self.requests: list[ProviderRequest] = []

    def queue(self, *replies: ScriptedReply) -> None:
        self.replies.extend(replies)

    def complete(self, request: ProviderRequest) -> ProviderReply:
        self.requests.append(request)
        if not self.replies:
            # Better than an index error, and better than inventing text: a
            # test that ran one more turn than it scripted should say so.
            raise MalformedReplyError("The scripted provider has no reply left.")
        reply = self.replies.pop(0)
        if reply.error is not None:
            raise reply.error
        return ProviderReply(
            text=reply.text,
            stop_reason=reply.stop_reason,
            tool_calls=reply.tool_calls,
            model="scripted",
            input_tokens=0,
            output_tokens=0,
        )


@dataclass
class _ProviderHolder:
    """Lets tests swap the provider without reaching into the cache."""

    provider: AIModelProvider | None = field(default=None)


_override = _ProviderHolder()


def set_provider(provider: AIModelProvider | None) -> None:
    """Replaces the process-wide provider. Used by tests and fixtures only."""
    _override.provider = provider
    get_provider.cache_clear()


def build_provider(settings: Settings) -> AIModelProvider:
    """Chooses a provider from configuration (PRD 8, sections 10 and 76)."""
    if settings.ai_provider == "anthropic":
        if not settings.ai_api_key:
            return UnconfiguredProvider()
        # Imported here rather than at module scope so the backend runs, and
        # its tests pass, on a deployment that has no provider configured and
        # therefore no provider SDK installed.
        from app.services.assistant.anthropic_provider import AnthropicProvider

        return AnthropicProvider(settings)
    if settings.ai_provider == "scripted":
        if not settings.is_development:
            # A canned-reply assistant in production would be a Nura that
            # says the same thing to everybody and means none of it.
            raise ProviderNotConfiguredError(
                "AI_PROVIDER=scripted is for development only."
            )
        return ScriptedProvider()
    return UnconfiguredProvider()


@lru_cache
def get_provider() -> AIModelProvider:
    """The provider for this process, built once.

    Cached because the Anthropic adapter holds an HTTP client with its own
    connection pool; rebuilding it per request would open a new connection
    per message.
    """
    if _override.provider is not None:
        return _override.provider
    return build_provider(get_settings())
