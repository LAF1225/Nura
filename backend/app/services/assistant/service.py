"""NuraAssistantService: the one path a message takes (PRD 8, section 9).

    rate limit
        -> deterministic policy on what was said
        -> store the user's message
        -> [emergency phrase? escalate for real, say what it did, no model]
        -> build the prompt: identity, boundary, tone, mode, memory, counts
        -> call the provider
        -> [tool calls? run them, profile-scoped, and go round again]
        -> put the required sentences around the reply
        -> store it with its metadata
        -> notice a durable preference worth offering to remember

Section 9 asks for a dedicated service boundary and says not to call the
model from random screens. This is that boundary: the API layer above it
does authorization and serialisation and nothing else, and no other module
in the backend imports ``provider``.

Three things are worth reading before changing anything here.

**The user's message is stored before the model is called.** If the provider
times out, what they typed is still there, the app can retry with the same
client id, and the retry does not produce a second copy of their question.

**A failure stores nothing from Nura.** Section 56 says no fake assistant
reply, so a provider error produces a failure code and no assistant message
-- the thread reads as a question that has not been answered yet, because
that is what it is.

**Nothing in this file writes to a health record.** The tools that change
anything return a pending action for the user to confirm, and the confirmed
write runs in ``confirm_pending_action`` below, from an explicit request --
not from anything the model said (sections 14, 15 and 53).

**The emergency phrase now does something** (PRD 10, section 14). PRD 8 could
only say that escalation did not exist; PRD 10 built it, so "Nura, emergency"
raises a real safety event, escalates immediately, and the notice reports what
that escalation *did* -- an in-app alert record for each permitted caregiver,
and a line for every channel that is not set up. It still never reaches a
model, and it still never claims anybody was contacted.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field, replace
from datetime import date, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models import Conversation, ConversationMessage, Profile, User
from app.services.assistant import (
    context as context_builder,
)
from app.services.assistant import (
    conversations as conversation_service,
)
from app.services.assistant import limits, memory, policy, preferences, prompts, tools
from app.services.assistant.provider import (
    AIModelProvider,
    ProviderError,
    ProviderRefusedError,
    ProviderReply,
    ProviderRequest,
    ToolResult,
    Turn,
    get_provider,
)
from app.services.productivity import capabilities as daily_life_capabilities
from app.services.robot import presentations as robot_presentations
from app.services.safety import escalation as safety_escalation
from app.services.safety import events as safety_events
from app.services.safety import status as safety_status
from app.services.safety import wording as safety_wording

logger = logging.getLogger(__name__)

#: How many times the model may call tools before Nura answers anyway.
#: Four is generous for the ten read tools here: a question needing five
#: separate lookups is a question that wanted a different screen.
MAX_TOOL_ROUNDS = 4

#: Where a pending write lives until it is confirmed (section 14).
PENDING_KEY = "pending_action"


@dataclass(frozen=True)
class AssistantReply:
    """Everything one exchange produced."""

    conversation: Conversation
    user_message: ConversationMessage
    reply: ConversationMessage | None = None
    #: A stable code from ``prompts.FAILURE_MESSAGES`` when nothing was said.
    failure: str | None = None
    memory_suggestion: memory.MemorySuggestion | None = None
    pending_action: tools.PendingAction | None = None
    #: True when the user described something they have not logged, so the app
    #: can offer the PRD 6 symptom flow rather than Nura discussing it loosely
    #: (section 18).
    suggest_symptom_log: bool = False
    tools_used: tuple[str, ...] = ()

    @property
    def failure_message(self) -> str | None:
        if self.failure is None:
            return None
        return prompts.FAILURE_MESSAGES.get(
            self.failure, prompts.FAILURE_MESSAGES["provider_error"]
        )


@dataclass
class _Exchange:
    """Working state for one call to ``send``."""

    turns: list[Turn] = field(default_factory=list)
    used: list[str] = field(default_factory=list)
    pending: tools.PendingAction | None = None


class NuraAssistantService:
    """Turns a message into a reply, or into an honest failure."""

    def __init__(
        self,
        provider: AIModelProvider | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._provider = provider or get_provider()

    # --- the prompt ---------------------------------------------------------

    def _system_prompt(
        self,
        db: Session,
        profile: Profile,
        *,
        local_date: date,
        now: datetime,
        serious: bool,
        emergency: bool = False,
    ) -> str:
        settings = preferences.get_or_create(db, profile.id)
        remembered = memory.context_lines(
            memory.list_memories(db, profile.id, active_only=True),
            mode=settings.mode,
        )
        block = context_builder.build_block(
            db, profile.id, local_date=local_date, now=now, mode=settings.mode
        )
        return prompts.system_prompt(
            preferred_name=profile.preferred_name,
            traits=preferences.traits(settings),
            verbosity=settings.verbosity,
            mode=settings.mode,
            serious=serious,
            emergency=emergency,
            custom_instructions=settings.custom_instructions,
            memories=remembered,
            context_block=block,
            # PRD 12, section 29. Derived from whether a provider exists, never
            # written by hand, so the prompt cannot claim a capability the
            # deployment does not have.
            capabilities=daily_life_capabilities.capability_map(),
        )

    @staticmethod
    def _history(db: Session, conversation: Conversation) -> list[Turn]:
        """The thread so far, as turns, with the summary standing in for the rest."""
        turns: list[Turn] = []
        if conversation.summary:
            # Carried as a user turn rather than in the system prompt: the
            # system prompt is the same for every message in a thread and is
            # the part worth keeping cacheable, and a summary changes.
            turns.append(
                Turn(
                    role="user",
                    text=(f"Earlier in this conversation:\n{conversation.summary}"),
                )
            )
            turns.append(Turn(role="assistant", text="Understood."))
        for message in conversation_service.recent_for_context(db, conversation):
            turns.append(
                Turn(
                    role="user" if message.role == "user" else "assistant",
                    text=message.content,
                )
            )
        return turns

    # --- the loop -----------------------------------------------------------

    def _run_tools(
        self,
        tool_context: tools.ToolContext,
        reply: ProviderReply,
        exchange: _Exchange,
    ) -> Turn:
        """Runs every tool the model asked for and builds the result turn.

        All of them, and all in one turn: a provider that asked for three
        lookups expects three results in a single user message, and splitting
        them teaches it to stop asking for more than one at a time.
        """
        results: list[ToolResult] = []
        for call in reply.tool_calls:
            outcome = tools.run(tool_context, call.name, call.arguments)
            exchange.used.append(call.name)
            if outcome.pending is not None and exchange.pending is None:
                # One pending write per exchange. A model that proposes two
                # changes at once is asking for a confirmation dialog nobody
                # can answer sensibly.
                exchange.pending = outcome.pending
            results.append(
                ToolResult(
                    call_id=call.id,
                    content=outcome.content,
                    is_error=outcome.is_error,
                )
            )
        return Turn(role="user", tool_results=tuple(results))

    def _converse(
        self,
        tool_context: tools.ToolContext,
        system: str,
        exchange: _Exchange,
    ) -> ProviderReply:
        """Calls the provider, servicing tool calls until it has an answer."""
        specs = tools.specs(tool_context)
        for _ in range(MAX_TOOL_ROUNDS + 1):
            reply = self._provider.complete(
                ProviderRequest(
                    system=system,
                    turns=tuple(exchange.turns),
                    tools=specs,
                    max_output_tokens=self._settings.ai_max_output_tokens,
                )
            )
            if reply.stop_reason != "tool_use" or not reply.tool_calls:
                return reply
            exchange.turns.append(
                Turn(
                    role="assistant",
                    text=reply.text,
                    tool_calls=reply.tool_calls,
                )
            )
            exchange.turns.append(self._run_tools(tool_context, reply, exchange))

        # Out of rounds. Whatever it last said is better than nothing, and
        # the tools it ran have already been recorded.
        logger.info("assistant: stopped after the tool-call limit")
        return reply

    # --- the entry point ----------------------------------------------------

    def send(
        self,
        db: Session,
        profile: Profile,
        conversation: Conversation,
        *,
        user: User,
        text: str,
        now: datetime,
        local_date: date,
        client_message_id: str | None = None,
    ) -> AssistantReply:
        """Records a message and answers it.

        ``user`` is who is asking. PRD 10's safety tools write rows that record
        an actor, and the tool context has no default for it -- so it has to
        come from here, and here it comes from the verified token.
        """
        limits.check(db, profile.id, now, self._settings.assistant_rate_limit_per_hour)

        intent = policy.detect(text)
        # PRD 10, section 43. Emergency mode is a fact about the world rather
        # than about the sentence, so it is read rather than detected.
        intent = replace(
            intent,
            emergency_active=safety_status.in_emergency_mode(db, profile.id),
        )

        existing = (
            conversation_service.find_by_client_id(db, conversation.id, client_message_id)
            if client_message_id
            else None
        )
        if existing is not None:
            # A retry after a failure (section 55). The question is already
            # recorded; answer it rather than recording it twice.
            user_message = existing
        else:
            user_message = conversation_service.append_message(
                db,
                conversation,
                role="user",
                content=text,
                now=now,
                safety_mode=intent.safety_mode,
                client_message_id=client_message_id,
            )
            if conversation.title == conversation_service.DEFAULT_TITLE:
                conversation_service.rename_conversation(
                    db, conversation, conversation_service.title_from(text)
                )

        if intent.emergency_phrase:
            return self._emergency(db, profile, conversation, user_message, user, now)

        if not self._settings.assistant_configured:
            return AssistantReply(
                conversation=conversation,
                user_message=user_message,
                failure="not_configured",
            )

        settings_row = preferences.get_or_create(db, profile.id)
        system = self._system_prompt(
            db,
            profile,
            local_date=local_date,
            now=now,
            serious=intent.serious,
            emergency=intent.emergency_active,
        )
        exchange = _Exchange(turns=self._history(db, conversation))
        # PRD 8's assistant is the person's own, so it runs with the owner's
        # scope. PRD 9 section 63 requires a caregiver-scoped assistant to pass
        # that caregiver's granted set instead; there is no caregiver chat
        # endpoint yet, and ``allowed`` has no default so one cannot be written
        # without choosing.
        tool_context = tools.ToolContext(
            db=db,
            profile=profile,
            now=now,
            local_date=local_date,
            allowed=tools.OWNER_SCOPE,
            is_owner=True,
            account=user,
        )

        started = time.monotonic()
        try:
            reply = self._converse(tool_context, system, exchange)
        except ProviderRefusedError:
            return AssistantReply(
                conversation=conversation,
                user_message=user_message,
                failure="refused",
                tools_used=tuple(exchange.used),
            )
        except ProviderError as error:
            logger.warning("assistant: could not answer (%s)", error.reason)
            return AssistantReply(
                conversation=conversation,
                user_message=user_message,
                failure=error.reason,
                tools_used=tuple(exchange.used),
            )

        if reply.stop_reason == "refusal":
            return AssistantReply(
                conversation=conversation,
                user_message=user_message,
                failure="refused",
                tools_used=tuple(exchange.used),
            )

        answer = policy.enforce(reply.text, intent)
        if not answer:
            # A reply with nothing in it is a failure that happened to
            # return 200. Treated as one rather than stored as silence.
            return AssistantReply(
                conversation=conversation,
                user_message=user_message,
                failure="malformed_reply",
                tools_used=tuple(exchange.used),
            )

        meta: dict[str, Any] = {
            "model": reply.model or self._settings.ai_model,
            "provider": self._provider.name,
            "prompt_version": prompts.PROMPT_VERSION,
            "latency_ms": int((time.monotonic() - started) * 1000),
            "tools": exchange.used,
            "safety_mode": intent.safety_mode,
            "input_tokens": reply.input_tokens,
            "output_tokens": reply.output_tokens,
            "truncated": reply.stop_reason == "max_tokens",
        }
        if exchange.pending is not None:
            meta[PENDING_KEY] = {
                "tool": exchange.pending.tool,
                "arguments": exchange.pending.arguments,
                "summary": exchange.pending.summary,
                "state": "pending",
            }

        stored = conversation_service.append_message(
            db,
            conversation,
            role="assistant",
            content=answer,
            now=now,
            safety_mode=intent.safety_mode,
            source="mobile_text",
            meta=meta,
        )

        if self._settings.assistant_log_model_requests:
            # Shape only, and only when a developer switched it on. No prompt,
            # no reply, no tool arguments (section 58).
            logger.info(
                "assistant: replied in %sms using %s (%s in, %s out)",
                meta["latency_ms"],
                ",".join(exchange.used) or "no tools",
                reply.input_tokens,
                reply.output_tokens,
            )

        self._maybe_summarise(db, conversation, system)

        suggestion = memory.detect_suggestion(text, mode=settings_row.mode)
        if suggestion is not None and memory.already_remembered(
            memory.list_memories(db, profile.id), suggestion
        ):
            suggestion = None

        robot_presentations.show_reply(
            db,
            profile.id,
            text=answer,
            source_id=str(stored.id),
            serious=intent.serious,
            now=now,
        )

        return AssistantReply(
            conversation=conversation,
            user_message=user_message,
            reply=stored,
            memory_suggestion=suggestion,
            pending_action=exchange.pending,
            suggest_symptom_log=intent.new_symptom and not intent.emergency_phrase,
            tools_used=tuple(exchange.used),
        )

    # --- the paths that never reach a model ---------------------------------

    def _emergency(
        self,
        db: Session,
        profile: Profile,
        conversation: Conversation,
        user_message: ConversationMessage,
        user: User,
        now: datetime,
    ) -> AssistantReply:
        """Answers "Nura, emergency" by escalating (PRD 10, section 14).

        The whole of section 14 in one method: the phrase bypasses the normal
        countdown and begins escalation immediately. It is matched
        deterministically in ``policy`` before any provider is reached, so an
        emergency never waits on a model, a rate limit or a network.

        Stored as a ``notice`` rather than as generated text, because that is
        what it is: a product statement assembled from what the escalation
        actually did. No model saw this message, and no sentence in it was
        written by one.

        If creating the event fails -- the only realistic cause is a database
        problem -- the person still gets the standing advice. An emergency is
        the worst possible moment to return an error page.
        """
        lines: list[str] = []
        event = None
        try:
            event = safety_events.create(
                db,
                profile,
                event_type="call_for_help",
                trigger_source="mobile_manual",
                now=now,
                actor_account_id=user.id,
                actor_kind="primary_user",
            )
            db.commit()
            lines = [
                safety_wording.escalation_line(
                    label=attempt.recipient_label,
                    channel=attempt.channel,
                    status=attempt.status,
                )
                for attempt in safety_escalation.attempts_for(db, event.id)
            ]
        except Exception:  # pragma: no cover - defended, not expected
            db.rollback()
            logger.exception("assistant: could not raise an emergency event")

        logger.info("assistant: answered an emergency phrase")
        stored = conversation_service.append_message(
            db,
            conversation,
            role="assistant",
            content=prompts.emergency_notice(lines),
            now=now,
            message_type="notice",
            safety_mode=(
                "emergency_active" if event is not None else "emergency_unconfigured"
            ),
            meta={
                "prompt_version": prompts.PROMPT_VERSION,
                "safety_mode": (
                    "emergency_active" if event is not None else "emergency_unconfigured"
                ),
                "model": None,
                "tools": [],
                "safety_event_id": str(event.id) if event is not None else None,
            },
        )
        return AssistantReply(
            conversation=conversation,
            user_message=user_message,
            reply=stored,
        )

    # --- confirmed writes ---------------------------------------------------

    def confirm_pending_action(
        self,
        db: Session,
        profile: Profile,
        message: ConversationMessage,
        *,
        user: User,
        confirmed: bool,
        now: datetime,
        local_date: date,
    ) -> ConversationMessage | None:
        """Carries out, or cancels, the change Nura offered (section 14).

        The message's own text is never rewritten -- a conversation is a
        record of what was said. What changes is the pending action's state
        in its metadata, and the outcome arrives as a new ``notice`` line, so
        the thread reads as the exchange it was.
        """
        pending = (message.meta or {}).get(PENDING_KEY)
        if not isinstance(pending, dict) or pending.get("state") != "pending":
            return None

        conversation = conversation_service.get_conversation(
            db, profile.id, message.conversation_id
        )

        if not confirmed:
            state = "cancelled"
            outcome = "No problem — nothing was changed."
        else:
            action = tools.PendingAction(
                tool=str(pending.get("tool", "")),
                arguments=dict(pending.get("arguments") or {}),
                summary=str(pending.get("summary", "")),
            )
            tool_context = tools.ToolContext(
                db=db,
                profile=profile,
                now=now,
                local_date=local_date,
                allowed=tools.OWNER_SCOPE,
                is_owner=True,
                account=user,
            )
            outcome = tools.run_pending_action(tool_context, action)
            state = "confirmed"

        # A *new* nested dict, not the loaded one with a field changed.
        # SQLAlchemy compares a JSON column against the value it loaded, so
        # mutating that value in place leaves nothing to compare and the
        # UPDATE is silently never emitted -- which would let Confirm be
        # pressed twice and add the question twice.
        message.meta = {
            **(message.meta or {}),
            PENDING_KEY: {**pending, "state": state},
        }
        db.commit()

        return conversation_service.append_message(
            db,
            conversation,
            role="assistant",
            content=outcome,
            now=now,
            message_type="notice",
            meta={"prompt_version": prompts.PROMPT_VERSION, "model": None, "tools": []},
        )

    # --- keeping a long thread affordable -----------------------------------

    def _maybe_summarise(
        self, db: Session, conversation: Conversation, system: str
    ) -> None:
        """Compacts a thread that has outgrown its replay window (section 79).

        Runs inline, which costs one extra provider call on roughly every
        twenty-fifth message and nothing on the rest. A failure here is
        swallowed: the reply the user is waiting for has already been stored,
        and a thread that stays uncompacted is a cost problem, not a
        correctness one.
        """
        if not conversation_service.needs_summary(conversation):
            return
        transcript = "\n\n".join(
            f"{message.role}: {message.content}"
            for message in conversation_service.recent_for_context(
                db, conversation, limit=conversation_service.SUMMARY_TRIGGER
            )
        )
        if not transcript:
            return
        try:
            reply = self._provider.complete(
                ProviderRequest(
                    system=prompts.SUMMARY_SYSTEM,
                    turns=(Turn(role="user", text=transcript),),
                    max_output_tokens=400,
                )
            )
        except ProviderError as error:
            logger.info("assistant: could not summarise a thread (%s)", error.reason)
            return
        if reply.text:
            conversation_service.store_summary(
                db,
                conversation,
                summary=reply.text,
                through=max(conversation.message_count - 4, 0),
            )


def get_service(provider: AIModelProvider | None = None) -> NuraAssistantService:
    """The service, built per request.

    Cheap to construct -- the expensive part, the provider's HTTP client, is
    cached in ``provider.get_provider`` -- and building it per request means
    a settings change or a swapped provider takes effect without a restart
    of anything but the cache.
    """
    return NuraAssistantService(provider=provider)


def pending_from(message: ConversationMessage) -> tools.PendingAction | None:
    """The unconfirmed write attached to a message, if there is one."""
    pending = (message.meta or {}).get(PENDING_KEY)
    if not isinstance(pending, dict) or pending.get("state") != "pending":
        return None
    return tools.PendingAction(
        tool=str(pending.get("tool", "")),
        arguments=dict(pending.get("arguments") or {}),
        summary=str(pending.get("summary", "")),
    )


def profile_for_conversation(
    db: Session, profile_id: uuid.UUID, conversation_id: uuid.UUID
) -> Conversation:
    """Re-exported so the API layer has one import for the lookup."""
    return conversation_service.get_conversation(db, profile_id, conversation_id)
