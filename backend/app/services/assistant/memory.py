"""What Nura remembers, and how it comes to remember it.

PRD 8, sections 40-48, 93 and 94.

Memory here is a short list of durable *preferences*, not a second copy of
anybody's health record. Section 40 draws that line and section 45 restates
it: a condition, a medication, a symptom belongs in the tables built for it,
where it is dated, editable, exportable and covered by the health-record
authorization -- not paraphrased into a sentence Nura repeats back.

**Nothing is saved without being agreed to.** Section 46 asks Nura to
*propose* a memory and let the user press Remember. ``detect_suggestion``
below finds the durable preference; nothing in this module writes a row as a
side effect of a conversation. The write happens when the app posts the
confirmed memory, exactly as it would for one typed on the memory screen.

**Detection is deterministic, and deliberately narrow.** Section 42 says not
to save every casual statement, and the cheapest way to honour that is to
recognise only the handful of shapes that are unambiguously durable
preferences -- the ones section 93 lists. Asking a second model call "was
that a preference?" would cost a request per message and answer "sometimes
yes" on things like "I'm tired today", which is precisely the statement
section 42 warns about. What this misses, the memory screen catches: a user
can always add one themselves.
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AssistantMemory
from app.services.assistant import policy
from app.services.errors import DomainError, NotFoundError

logger = logging.getLogger(__name__)

#: How many memories one profile may keep. A list somebody can read in one
#: screen is a list they can actually manage (section 43); past that, "what
#: does Nura know about me" stops having an answer anybody checks.
MAX_MEMORIES = 50

#: Categories whose content is about the person's life rather than about how
#: Nura should talk. Held back in Privacy mode, where section 95 asks for
#: non-essential memory use to be avoided -- "call me Baba" still applies,
#: because it is how to address them and not a fact about them.
PERSONAL_CATEGORIES = ("routine", "personal_context")


class MemoryNotFoundError(NotFoundError):
    """No such memory for this profile."""


class TooManyMemoriesError(DomainError):
    """The memory list is full."""

    code = "too_many_memories"


@dataclass(frozen=True)
class MemorySuggestion:
    """A durable preference Nura noticed, for the user to accept or decline."""

    category: str
    content: str


def _normalise(text: str) -> str:
    """Collapses whitespace so a memory is one tidy line."""
    return " ".join(text.split())


# --- reading ----------------------------------------------------------------


def list_memories(
    db: Session, profile_id: uuid.UUID, *, active_only: bool = False
) -> list[AssistantMemory]:
    """This profile's memories, newest first."""
    query = select(AssistantMemory).where(AssistantMemory.profile_id == profile_id)
    if active_only:
        query = query.where(AssistantMemory.is_active.is_(True))
    return list(
        db.execute(query.order_by(AssistantMemory.created_at.desc())).scalars().all()
    )


def get_memory(
    db: Session, profile_id: uuid.UUID, memory_id: uuid.UUID
) -> AssistantMemory:
    """One memory, by profile *and* id together.

    Never by id alone, for the reason every other lookup in this codebase is
    written this way: someone else's memory must be indistinguishable from one
    that does not exist.
    """
    memory = db.execute(
        select(AssistantMemory).where(
            AssistantMemory.id == memory_id,
            AssistantMemory.profile_id == profile_id,
        )
    ).scalar_one_or_none()
    if memory is None:
        raise MemoryNotFoundError("That memory could not be found.")
    return memory


def context_lines(memories: list[AssistantMemory], *, mode: str) -> list[str]:
    """The memories that reach the model for one reply (sections 47 and 95).

    An inactive memory is absent here, which is the whole of what turning one
    off means. In Privacy mode the personal categories are held back too.
    """
    lines = []
    for memory in memories:
        if not memory.is_active:
            continue
        if mode == "privacy" and memory.category in PERSONAL_CATEGORIES:
            continue
        lines.append(memory.content)
    return lines


# --- writing ----------------------------------------------------------------


def create_memory(
    db: Session,
    profile_id: uuid.UUID,
    *,
    category: str,
    content: str,
    source: str,
    now: datetime,
) -> AssistantMemory:
    """Saves one agreed memory.

    ``confirmed_at`` is set for both sources: typing one on the memory screen
    is agreeing to it just as much as pressing Remember is, and one column
    that means "a person said yes to this" beats a rule about which source
    implies what.
    """
    cleaned = _normalise(content)
    # Held to the same standard as a custom instruction: a memory is text that
    # reaches the prompt, so it cannot be a way in through the side door
    # (sections 26 and 50).
    policy.check_instruction(cleaned)

    if len(list_memories(db, profile_id)) >= MAX_MEMORIES:
        raise TooManyMemoriesError(
            "Nura is already remembering as much as it can. Remove something first."
        )

    memory = AssistantMemory(
        profile_id=profile_id,
        category=category,
        content=cleaned,
        source=source,
        is_active=True,
        confirmed_at=now,
    )
    db.add(memory)
    db.commit()
    db.refresh(memory)
    # Category and source only. The content is the user's own words.
    logger.info("assistant: remembered something (%s, %s)", category, source)
    return memory


def update_memory(
    db: Session,
    memory: AssistantMemory,
    *,
    content: str | None = None,
    category: str | None = None,
    is_active: bool | None = None,
) -> AssistantMemory:
    """Edits one memory (section 43)."""
    if content is not None:
        cleaned = _normalise(content)
        policy.check_instruction(cleaned)
        memory.content = cleaned
    if category is not None:
        memory.category = category
    if is_active is not None:
        memory.is_active = is_active
    db.commit()
    db.refresh(memory)
    logger.info("assistant: edited a memory")
    return memory


def delete_memory(db: Session, memory: AssistantMemory) -> None:
    """Forgets one thing, and nothing else (section 47).

    Worth saying plainly because the PRD says it plainly: removing "call me
    Baba" removes a row from this table. It does not touch the profile, the
    name on it, or any health record -- there is no cascade from here to
    anywhere, by design.
    """
    db.delete(memory)
    db.commit()
    logger.info("assistant: forgot a memory")


# --- noticing a durable preference ------------------------------------------

#: Each entry is a pattern, the category it belongs to, and how the memory
#: reads once saved. Written as sentences about the future, because that is
#: what a memory has to be useful for: "Prefers short answers" tells the next
#: conversation something; "said they prefer short answers on Tuesday" does
#: not.
_RULES: tuple[tuple[re.Pattern[str], str, str], ...] = (
    (
        re.compile(r"\bcall me ([A-Za-z][\w'’\- ]{0,40}?)\s*[.!]?$", re.IGNORECASE),
        "communication",
        "Prefers to be called {0}.",
    ),
    (
        re.compile(
            r"\b(?:please )?(?:don'?t|do not|never) (?:make )?joke",
            re.IGNORECASE,
        ),
        "communication",
        "Does not want jokes.",
    ),
    (
        re.compile(r"\b(?:don'?t|do not|never) use (?:overly )?cheerful", re.IGNORECASE),
        "communication",
        "Does not want cheerful language.",
    ),
    (
        re.compile(
            r"\bkeep (?:my )?morning(?:s| conversations| replies| answers)?"
            r"[\w ]{0,20}\bshort\b",
            re.IGNORECASE,
        ),
        "routine",
        "Morning responses should be concise.",
    ),
    (
        re.compile(
            r"\bi (?:prefer|like|want)[\w ]{0,15}\b(?:short|brief|concise)\b"
            r"[\w ]{0,15}\b(?:answers|replies|responses)\b",
            re.IGNORECASE,
        ),
        "communication",
        "Prefers short answers.",
    ),
    (
        re.compile(
            r"\bi (?:prefer|like|want)[\w ]{0,15}\b(?:detailed|thorough|long)\b"
            r"[\w ]{0,15}\b(?:answers|replies|responses|explanations)\b",
            re.IGNORECASE,
        ),
        "communication",
        "Prefers detailed explanations.",
    ),
    (
        re.compile(
            r"\bexplain (?:medical )?(?:words|terms|things)[\w ]{0,10}\bsimpl",
            re.IGNORECASE,
        ),
        "communication",
        "Wants medical words explained simply.",
    ),
)


def detect_suggestion(text: str, *, mode: str = "normal") -> MemorySuggestion | None:
    """Finds a durable preference worth offering to remember (sections 42, 93).

    Returns at most one: being asked two questions after one message is worse
    than missing the second preference, which the user can add by hand.

    Silent in Privacy mode -- section 95 says not to suggest new memories
    there -- and silent on anything that would fail the instruction check,
    since a "preference" that tries to switch off the medical boundary is not
    a preference.
    """
    if mode == "privacy":
        return None

    for pattern, category, template in _RULES:
        match = pattern.search(text)
        if match is None:
            continue
        groups = [_normalise(group) for group in match.groups() if group]
        content = template.format(*groups) if groups else template
        if policy.instruction_risk(content) is not None:
            return None
        return MemorySuggestion(category=category, content=content)
    return None


def already_remembered(
    memories: list[AssistantMemory], suggestion: MemorySuggestion
) -> bool:
    """Whether this is something Nura has been told already.

    Compared on the settled sentence rather than on what the user typed, so
    "call me Baba" said twice in different words does not produce two rows.
    """
    target = suggestion.content.casefold()
    return any(memory.content.casefold() == target for memory in memories)
