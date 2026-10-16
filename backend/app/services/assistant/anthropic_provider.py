"""The Anthropic adapter (PRD 8, sections 10, 55 and 76).

The only file in the backend that imports a model provider's SDK. Everything
above it speaks the vocabulary in ``provider.py``, so swapping this out for
another provider means writing a sibling of this file and changing
``AI_PROVIDER`` -- not touching the assistant, the tools or the guardrails.

Three decisions are worth reading.

**It streams the fetch, and returns one finished reply.** A long answer over a
slow link is the classic way to hit an HTTP timeout, and the SDK's streaming
helper avoids that. The reply still arrives at the caller complete, because
PRD 8's guardrails run *after* the model and a sentence shown to somebody and
then withdrawn is worse than a short wait (section 54 makes streaming to the
app optional for exactly this kind of reason).

**Provider failures never escape as themselves.** Every exception below is
translated into a ``ProviderError`` subclass, and the log line records the
kind and the request id -- never the prompt, never the reply, never the
user's words (sections 55, 58 and 98).

**Thinking is left to the model's own default.** On the pinned default model
omitting the parameter runs adaptive thinking, which is what a request that
has to choose between six tools and stay inside a safety boundary wants; not
sending it explicitly also means a deployment that pins an older model gets a
working assistant rather than a 400.

**Unverified.** No request in this file has ever reached Anthropic from this
repository: there is no API key in the development environment, and the test
suite runs against ``ScriptedProvider``. The shapes are built from the current
SDK and the code type-checks against it, but the round trip is untested.
"""

from __future__ import annotations

import logging
from typing import Any, cast

import anthropic

from app.core.config import Settings
from app.services.assistant.provider import (
    AIModelProvider,
    MalformedReplyError,
    ProviderRateLimitError,
    ProviderReply,
    ProviderRequest,
    ProviderTimeoutError,
    ProviderUnavailableError,
    StopReason,
    ToolCall,
    Turn,
)

logger = logging.getLogger(__name__)

#: Asks the provider to re-route a request its own safety layer declines,
#: rather than returning nothing. Switched off with ``AI_SERVER_SIDE_FALLBACK``
#: for a deployment whose account cannot use it.
FALLBACK_BETA = "server-side-fallback-2026-07-01"

#: One retry, not the SDK's default of two: this request is a person waiting
#: for a chat reply, and three timeouts in a row is a minute and a half of
#: staring at a spinner.
MAX_RETRIES = 1

#: How a provider's stop reason maps onto ours. Anything unlisted is treated
#: as a finished turn, because a reply with text in it is still a reply.
_STOP_REASONS: dict[str, StopReason] = {
    "end_turn": "end_turn",
    "tool_use": "tool_use",
    "max_tokens": "max_tokens",
    "refusal": "refusal",
}


class AnthropicProvider(AIModelProvider):
    """Talks to the Anthropic Messages API."""

    name = "anthropic"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._model = settings.ai_model
        self._fallbacks = settings.ai_server_side_fallback
        self._client = anthropic.Anthropic(
            api_key=settings.ai_api_key,
            timeout=settings.ai_timeout_seconds,
            max_retries=MAX_RETRIES,
        )

    # --- building the request ------------------------------------------------

    @staticmethod
    def _blocks(turn: Turn) -> list[dict[str, Any]]:
        """One turn as provider content blocks.

        Empty text is dropped rather than sent: a text block with nothing in
        it is rejected, and an assistant turn that only called tools legitimately
        has none.
        """
        blocks: list[dict[str, Any]] = []
        for result in turn.tool_results:
            block: dict[str, Any] = {
                "type": "tool_result",
                "tool_use_id": result.call_id,
                "content": result.content,
            }
            if result.is_error:
                block["is_error"] = True
            blocks.append(block)
        if turn.text:
            blocks.append({"type": "text", "text": turn.text})
        for call in turn.tool_calls:
            blocks.append(
                {
                    "type": "tool_use",
                    "id": call.id,
                    "name": call.name,
                    "input": call.arguments,
                }
            )
        return blocks

    def _messages(self, request: ProviderRequest) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []
        for turn in request.turns:
            blocks = self._blocks(turn)
            if blocks:
                messages.append({"role": turn.role, "content": blocks})
        return messages

    @staticmethod
    def _tools(request: ProviderRequest) -> list[dict[str, Any]]:
        """Tool definitions, as plain schemas.

        Provider-side strict validation is deliberately *not* asked for. It
        would only save a round trip on a malformed call -- the tool layer
        validates every argument through a pydantic model regardless, which is
        what section 91 requires -- and its exact schema requirements cannot
        be verified from here, where no request has ever reached the provider.
        Trading an untestable hard failure for a rare extra round trip is the
        right way round.
        """
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.parameters,
            }
            for tool in request.tools
        ]

    def _kwargs(self, request: ProviderRequest) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": self._model,
            "max_tokens": request.max_output_tokens,
            "system": request.system,
            "messages": self._messages(request),
        }
        if request.tools:
            kwargs["tools"] = self._tools(request)
            # Never forced: whether a question needs stored data or only an
            # explanation is exactly the judgement the model is here to make.
            kwargs["tool_choice"] = {"type": "auto"}
        if self._settings.ai_effort:
            kwargs["output_config"] = {"effort": self._settings.ai_effort}
        return kwargs

    # --- the call ------------------------------------------------------------

    def complete(self, request: ProviderRequest) -> ProviderReply:
        kwargs = self._kwargs(request)
        # Typed as Any because the beta and non-beta helpers return different
        # message classes with the same shape, and this adapter reads only the
        # fields both have.
        message: Any
        try:
            if self._fallbacks:
                with self._client.beta.messages.stream(
                    betas=[FALLBACK_BETA],
                    fallbacks="default",
                    **kwargs,
                ) as beta_stream:
                    message = beta_stream.get_final_message()
            else:
                with self._client.messages.stream(**kwargs) as plain_stream:
                    message = plain_stream.get_final_message()
        except anthropic.APITimeoutError as error:
            logger.warning("assistant: model request timed out")
            raise ProviderTimeoutError("The model did not answer in time.") from error
        except anthropic.RateLimitError as error:
            logger.warning("assistant: model provider is rate limiting")
            raise ProviderRateLimitError("The model provider is busy.") from error
        except (anthropic.AuthenticationError, anthropic.PermissionDeniedError) as error:
            # A credential problem, which is a deployment fault rather than
            # the caller's. Logged as such; the user is told the same thing
            # as for any other outage (section 55).
            logger.error("assistant: model provider rejected our credentials")
            raise ProviderUnavailableError("The model provider refused us.") from error
        except anthropic.APIStatusError as error:
            logger.warning(
                "assistant: model provider returned %s (request %s)",
                error.status_code,
                getattr(error.response, "headers", {}).get("request-id", "unknown"),
            )
            raise ProviderUnavailableError("The model provider errored.") from error
        except anthropic.APIConnectionError as error:
            logger.warning("assistant: could not reach the model provider")
            raise ProviderUnavailableError(
                "The model provider is unreachable."
            ) from error

        return self._reply(message)

    # --- reading the reply ---------------------------------------------------

    @staticmethod
    def _reply(message: Any) -> ProviderReply:
        """Translates a provider message into a ``ProviderReply``.

        A refusal is returned rather than raised: it arrives as a normal HTTP
        200 with nothing usable in it, and the caller already has one place
        that decides what Nura says when it has no answer.
        """
        text_parts: list[str] = []
        calls: list[ToolCall] = []
        for block in message.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                arguments = block.input
                if not isinstance(arguments, dict):
                    raise MalformedReplyError("A tool call had non-object arguments.")
                calls.append(
                    ToolCall(
                        id=block.id,
                        name=block.name,
                        arguments=cast(dict[str, Any], arguments),
                    )
                )

        stop = _STOP_REASONS.get(message.stop_reason or "end_turn", "end_turn")
        category: str | None = None
        if stop == "refusal":
            details = getattr(message, "stop_details", None)
            category = getattr(details, "category", None)
            logger.info("assistant: the provider declined a request (%s)", category)

        usage = getattr(message, "usage", None)
        return ProviderReply(
            text="\n\n".join(part for part in text_parts if part).strip(),
            stop_reason=stop,
            tool_calls=tuple(calls),
            model=getattr(message, "model", "") or "",
            input_tokens=getattr(usage, "input_tokens", 0) or 0,
            output_tokens=getattr(usage, "output_tokens", 0) or 0,
            refusal_category=category,
        )
