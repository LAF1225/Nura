"""How Nura is asked to sound (PRD 8, sections 22-34, 62-64 and 88).

One row per profile, created the first time anybody reads it, so no screen
ever has to render "you have not set Nura up yet".

**A preset sets the dials and then stops mattering.** Choosing Gentle writes
five values; nudging one afterwards leaves the other four alone. What is
stored is always the five values, which is why ``personality_preset`` is
recorded too -- not as the source of truth, but so the screen can show which
button was last pressed and mark it as departed from once a dial moves.

**Nothing here can reach the medical boundary.** Section 24 is explicit that
personality must never weaken safety behaviour, and the way that is
guaranteed is structural rather than careful: the values below are rendered
into ``prompts.TRAIT_RULES`` and ``VERBOSITY_RULES``, neither of which has any
text about health in it, and serious mode discards the tone block entirely
(section 69).
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AssistantPreferences
from app.models.enums import PERSONALITY_TRAITS
from app.services.assistant import policy

logger = logging.getLogger(__name__)

#: The preset a profile starts on. The column defaults in
#: ``models/assistant.py`` are this preset's values, so ``matches_preset``
#: is true before anybody has touched the screen.
DEFAULT_PRESET = "gentle"

#: What each preset sets the dials to (PRD 8, sections 22 and 62).
#:
#: Humour is never ``high`` in any of them. A preset is a one-tap choice made
#: before somebody knows how Nura behaves, and a health companion that arrives
#: cracking jokes is the wrong first impression; anybody who wants more can
#: move the dial themselves.
PRESETS: dict[str, dict[str, str]] = {
    "gentle": {
        "warmth": "high",
        "humour": "low",
        "talkativeness": "medium",
        "proactivity": "low",
        "reminder_firmness": "low",
        "verbosity": "balanced",
    },
    "friendly": {
        "warmth": "high",
        "humour": "medium",
        "talkativeness": "high",
        "proactivity": "medium",
        "reminder_firmness": "medium",
        "verbosity": "balanced",
    },
    "focused": {
        "warmth": "low",
        "humour": "low",
        "talkativeness": "low",
        "proactivity": "low",
        "reminder_firmness": "high",
        "verbosity": "concise",
    },
    "professional": {
        "warmth": "medium",
        "humour": "low",
        "talkativeness": "low",
        "proactivity": "medium",
        "reminder_firmness": "high",
        "verbosity": "balanced",
    },
}

#: The fields a client may change. ``personality_preset`` is here too: picking
#: a preset is a change like any other, and applying its dials is what
#: ``update`` does with it.
EDITABLE_FIELDS = (
    "personality_preset",
    *PERSONALITY_TRAITS,
    "verbosity",
    "voice_id",
    "speaking_speed",
    "assistant_language",
    "custom_instructions",
    "mode",
)


def get_or_create(db: Session, profile_id: uuid.UUID) -> AssistantPreferences:
    """This profile's settings, with the defaults written on first read."""
    existing = db.execute(
        select(AssistantPreferences).where(AssistantPreferences.profile_id == profile_id)
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    preferences = AssistantPreferences(profile_id=profile_id)
    db.add(preferences)
    db.commit()
    db.refresh(preferences)
    return preferences


def apply_preset(preferences: AssistantPreferences, preset: str) -> None:
    """Writes a preset's five dials and its verbosity onto the row."""
    values = PRESETS.get(preset)
    if values is None:
        return
    preferences.personality_preset = preset
    for field, value in values.items():
        setattr(preferences, field, value)


def update(
    db: Session,
    preferences: AssistantPreferences,
    changes: dict[str, object],
) -> AssistantPreferences:
    """Applies a partial change.

    A preset in the same request is applied *first*, so a client that sends
    "Focused, but warmth high" gets Focused's other four dials and the warmth
    it asked for -- rather than the preset overwriting the explicit value a
    moment after it was set.

    Custom instructions are checked before they are stored (section 26). A
    refused instruction raises rather than being silently dropped: somebody
    who types "act as my doctor" and hears nothing will read the next answer
    as a doctor's.
    """
    preset = changes.get("personality_preset")
    if isinstance(preset, str):
        apply_preset(preferences, preset)

    for field, value in changes.items():
        if field == "personality_preset" or field not in EDITABLE_FIELDS:
            continue
        if field == "custom_instructions" and isinstance(value, str):
            cleaned = value.strip()
            if cleaned:
                policy.check_instruction(cleaned)
            setattr(preferences, field, cleaned or None)
            continue
        setattr(preferences, field, value)

    db.commit()
    db.refresh(preferences)
    # Names the fields, never their contents: a custom instruction is the
    # user's own words (section 58).
    logger.info("assistant: updated preferences (%s)", ", ".join(sorted(changes)))
    return preferences


def traits(preferences: AssistantPreferences) -> dict[str, str]:
    """The five dials as a plain mapping, for the prompt builder."""
    return {trait: getattr(preferences, trait) for trait in PERSONALITY_TRAITS}


def matches_preset(preferences: AssistantPreferences) -> bool:
    """Whether the dials still say what the stored preset says.

    Lets the screen show "Gentle" as chosen but adjusted, rather than
    claiming a preset the settings have drifted away from.
    """
    values = PRESETS.get(preferences.personality_preset)
    if values is None:
        return False
    return all(getattr(preferences, field) == value for field, value in values.items())
