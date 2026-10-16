"""What Nura can actually reach (PRD 12, sections 25, 29, 57 and 83).

Section 29 gives the map almost verbatim, and section 29's last line is the
reason it exists: *the model must not improvise capabilities absent from this
map.* So the map is exhaustive over ``DAILY_LIFE_CAPABILITY_KEYS``, it is what
the assistant's system prompt is built from, and it is what the
``external-capabilities`` endpoint returns.

**The four internal keys are ``available`` because they are this system
talking to itself.** Tasks, reminders, alarms and routines are rows in this
database reached by this backend. Nothing outside is involved, which is exactly
why they work -- and why the other three do not.

**The three external keys are derived, never written.** Each one asks
``providers`` whether a provider is both named and implemented. None is, in any
deployment, so all three read ``not_configured``. A capability flag that could
be turned on independently of the capability is how a system comes to tell
somebody it checked the weather, and PRD 10 section 72 already made that
mistake impossible for safety; this is the same shape.

**Alarms are ``available`` with a caveat that is not in the state.** An alarm
can be created, edited, enabled and scheduled -- that is what ``available``
claims, and it is true. Whether the operating system actually wakes anybody is
a different question, it has never been tested, and it is answered by
``wording.ALARM_LIMITATION`` beside the switch rather than by downgrading a
state that would then be wrong about the thing it does describe. Section 11
asks for honest labelling, not for a false ``unavailable``.
"""

import logging
from dataclasses import dataclass

from app.models.enums import (
    DAILY_LIFE_CAPABILITY_KEYS,
    DAILY_LIFE_CAPABILITY_STATES,
    EXTERNAL_CAPABILITY_KEYS,
)
from app.services.productivity import providers, wording

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Capability:
    """One capability, where it stands, and the sentence that explains it."""

    key: str
    state: str
    label: str
    sentence: str

    def __post_init__(self) -> None:
        assert self.key in DAILY_LIFE_CAPABILITY_KEYS, self.key
        assert self.state in DAILY_LIFE_CAPABILITY_STATES, self.state


def capability_map() -> dict[str, str]:
    """Every capability with its current state (section 29).

    Returns all of ``DAILY_LIFE_CAPABILITY_KEYS`` in their fixed order, for the
    reason the caregiver permission map returns all eight categories: a client
    -- or a prompt -- that only sees the keys that happen to be present is one
    that silently stops asking about a key somebody added.
    """
    return {
        # Rows in this database, reached by this backend.
        "tasks": "available",
        "reminders": "available",
        # Available as a *scheduled notification*. See the module docstring and
        # ``wording.ALARM_LIMITATION``.
        "alarms": "available",
        "routines": "available",
        # Somebody outside this system, and nobody is there.
        "weather": ("available" if providers.weather_configured() else "not_configured"),
        "news": "available" if providers.news_configured() else "not_configured",
        "external_calendar": (
            "available" if providers.external_calendar_configured() else "not_configured"
        ),
    }


def capabilities() -> tuple[Capability, ...]:
    """The map as validated rows, in the fixed key order.

    The sentence comes from ``wording.capability_sentence``, which is where
    sections 26, 27 and 28's three exact sentences live -- so the endpoint, the
    assistant and the app's capability rows all say the same thing.
    """
    current = capability_map()
    return tuple(
        Capability(
            key=key,
            state=current[key],
            label=wording.CAPABILITY_LABELS[key],
            sentence=wording.capability_sentence(key=key, state=current[key]),
        )
        for key in DAILY_LIFE_CAPABILITY_KEYS
    )


def is_available(key: str) -> bool:
    """Whether that one capability can be used right now."""
    return capability_map()[key] == "available"


def external_states() -> dict[str, str]:
    """Just the three that need an outside service (section 83's checkpoint)."""
    current = capability_map()
    return {key: current[key] for key in EXTERNAL_CAPABILITY_KEYS}


def unconfigured_sentence(key: str) -> str:
    """What to say when something external is asked for (sections 26-28).

    Used by the assistant's tools, so the model is handed a fact rather than
    left to compose one. A model that composes its own apology for a missing
    integration is a model that will eventually compose an answer instead.
    """
    return wording.capability_sentence(key=key, state=capability_map()[key])
