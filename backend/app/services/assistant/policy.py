"""The guardrails that do not depend on the model (PRD 8, sections 37-39, 69, 73-75).

Section 74 is the instruction this file exists for: *prefer deterministic
flags where possible; do not rely entirely on model judgement.* Everything
here runs on the user's own words, before and after the model, and behaves
identically whichever provider is configured -- which is also what makes the
section 72 guardrail tests mean anything, since a test that only proves a
scripted reply came back proves nothing about safety.

Three things happen here.

**An emergency phrase never reaches the model at all.** Section 39 says PRD 8
may recognise "Nura, emergency" and must route it to a clear not-yet-configured
path without pretending escalation exists. A model cannot be relied on to say
that every time, so it is not asked to: the phrase short-circuits to a fixed
notice.

**Serious mode is decided from the text, not inferred by the model.** Section
38 lists the triggers and warns against treating every health question as an
emergency, so the patterns below are deliberately high-precision and low-recall:
they fire on the clear cases and let the prompt handle the rest.

**The section 73 sentences are put in front of the reply.** Not requested of
the model and hoped for -- placed there. A diagnosis request gets the
diagnosis sentence; a dose-change request gets the medication sentence; and
if the model already said it, it is not said twice.

What this file deliberately does **not** do is scrub the model's own words. A
filter that catches most ways of saying "you have migraine" would let the rest
through while making everyone believe none got through, and the honest
position is that the prompt and the boundary above are what keep Nura from
diagnosing -- not a regular expression applied afterwards.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.services.assistant.prompts import (
    DIAGNOSIS_PREAMBLE,
    MEDICATION_GUIDANCE,
    MEDICATION_PREAMBLE,
)
from app.services.errors import DomainError

#: Section 39's phrase, allowing for how people actually type it.
EMERGENCY_PHRASES = (
    "nura emergency",
    "nura, emergency",
    "nura help emergency",
)

#: Words that mean somebody may be describing a medical emergency right now.
#: Short, unambiguous and physical; nothing here is a symptom Nura tracks.
URGENT_PHRASES = (
    "can't breathe",
    "cant breathe",
    "cannot breathe",
    "struggling to breathe",
    "chest pain",
    "crushing pain in my chest",
    "unconscious",
    "unresponsive",
    "overdose",
    "overdosed",
    "bleeding heavily",
    "severe bleeding",
    "having a stroke",
    "having a heart attack",
)

#: Said by somebody who may be in danger from themselves. Handled separately
#: from other distress because the reply owes them something specific.
SELF_HARM_PHRASES = (
    "kill myself",
    "killing myself",
    "end my life",
    "want to die",
    "suicidal",
    "suicide",
    "harm myself",
    "hurt myself",
)

#: Plain distress (section 38, "explicit distress statement"). Turns humour
#: off and shortens the reply; nothing more.
DISTRESS_PHRASES = (
    "i'm scared",
    "im scared",
    "i am scared",
    "i'm frightened",
    "im frightened",
    "i'm terrified",
    "im terrified",
    "i can't cope",
    "i cant cope",
    "i'm really worried",
    "im really worried",
    "i'm panicking",
    "im panicking",
)

#: Asking Nura what is wrong with them (sections 16 and 73). High-precision on
#: purpose: "do I have" alone would match "do I have any appointments".
DIAGNOSIS_PHRASES = (
    "diagnose me",
    "can you diagnose",
    "what's wrong with me",
    "whats wrong with me",
    "what is wrong with me",
    "what do i have",
    "what have i got",
    "what's causing",
    "whats causing",
    "what is causing",
    "what could be causing",
    "do you think i have",
    "do i have cancer",
    "could this be cancer",
    "could it be cancer",
    "is this cancer",
    "what condition do i have",
    "tell me what i have",
)

#: Asking Nura to change how a medication is taken (sections 19 and 73).
MEDICATION_CHANGE_PHRASES = (
    "should i stop taking",
    "should i stop my",
    "can i stop taking",
    "stop taking my",
    "should i double",
    "can i double",
    "double my dose",
    "double the dose",
    "take two instead",
    "take a double",
    "should i take extra",
    "take an extra dose",
    "increase my dose",
    "reduce my dose",
    "lower my dose",
    "change my dose",
    "up my dose",
    "should i skip my",
    "can i skip my",
    "should i take more",
    "safe to take together",
    "safe to take with",
    "interact with",
    "any interactions",
    "interaction between",
)

#: "Is this dangerous?" -- a safety-relevant question, per section 38.
SAFETY_QUESTION_PHRASES = (
    "is this dangerous",
    "is it dangerous",
    "is this serious",
    "is it serious",
    "is this harmful",
    "am i going to die",
    "will i be okay",
    "will i be ok",
    "is this an emergency",
    "should i go to hospital",
    "should i go to a&e",
    "should i call an ambulance",
)

#: Somebody mentioning something they have not recorded (section 18). Only a
#: hint: the consequence is an optional "Log symptom" button, so a false
#: positive costs a button nobody presses.
NEW_SYMPTOM_PATTERN = re.compile(
    r"\bi(?:'ve| ?ve| have)? ?(?:been )?(?:feeling|having|getting|had)\b"
    r"|\bi keep (?:getting|having|feeling)\b"
    r"|\bi feel\b",
    re.IGNORECASE,
)

#: What Nura adds for itself when somebody describes an emergency. It does not
#: call anyone -- section 75 -- and says so by pointing outward.
URGENT_CARE_LINE = (
    "This sounds like it could need urgent care. Please contact your local "
    "emergency services or an urgent care service now -- Nura cannot contact "
    "anyone for you."
)

#: Deliberately not a specific number: Nura does not know which country
#: somebody is in, and a wrong crisis line is worse than none.
CRISIS_LINE = (
    "If you are thinking about harming yourself, please reach out to your "
    "local emergency services or a crisis line right now. Nura cannot "
    "contact anyone for you, and you deserve to talk to someone who can help."
)

# --- what a message is asking for -------------------------------------------


@dataclass(frozen=True)
class Intent:
    """What the deterministic checks found in one user message."""

    emergency_phrase: bool = False
    urgent_language: bool = False
    self_harm: bool = False
    distress: bool = False
    diagnosis_request: bool = False
    medication_change: bool = False
    safety_question: bool = False
    new_symptom: bool = False
    #: Not from the text. Set by the service from the safety layer when an
    #: escalation is in flight (PRD 10, section 43), because emergency mode is
    #: a fact about the world rather than about the sentence.
    emergency_active: bool = False

    @property
    def serious(self) -> bool:
        """Whether this moment gets serious mode (sections 37 and 38).

        Note what is absent: "mentions a symptom" and "asks a health
        question". Section 38 says not to treat every health question as an
        emergency, and an assistant that drops its warmth the moment somebody
        says the word "headache" is doing exactly that.
        """
        return (
            self.emergency_active
            or self.urgent_language
            or self.self_harm
            or self.distress
            or self.diagnosis_request
            or self.medication_change
            or self.safety_question
        )

    @property
    def safety_mode(self) -> str:
        """The value recorded on the message (sections 37, 39 and 80).

        ``emergency_active`` comes first, and it is PRD 10's addition: a reply
        given while an escalation is actually in flight is a different kind of
        moment from one where somebody typed the phrase. PRD 8 had only the
        second, because there was no escalation for the first to be about.
        """
        if self.emergency_active:
            return "emergency_active"
        if self.emergency_phrase:
            return "emergency_unconfigured"
        return "serious" if self.serious else "normal"


def _contains_any(haystack: str, needles: tuple[str, ...]) -> bool:
    return any(needle in haystack for needle in needles)


def detect(text: str) -> Intent:
    """Reads one user message and reports what it triggers.

    Case-insensitive and punctuation-tolerant only as far as lowercasing goes.
    Nothing here is clever, and that is the point: it can be read, listed in a
    test, and argued about.
    """
    lowered = text.lower()
    return Intent(
        emergency_phrase=_contains_any(lowered, EMERGENCY_PHRASES),
        urgent_language=_contains_any(lowered, URGENT_PHRASES),
        self_harm=_contains_any(lowered, SELF_HARM_PHRASES),
        distress=_contains_any(lowered, DISTRESS_PHRASES),
        diagnosis_request=_contains_any(lowered, DIAGNOSIS_PHRASES),
        medication_change=_contains_any(lowered, MEDICATION_CHANGE_PHRASES),
        safety_question=_contains_any(lowered, SAFETY_QUESTION_PHRASES),
        new_symptom=bool(NEW_SYMPTOM_PATTERN.search(lowered)),
    )


def enforce(reply: str, intent: Intent) -> str:
    """Puts the required sentences around a reply (section 73).

    A floor, not a filter. It adds what must be said and never removes or
    rewrites what the model said -- see this module's docstring for why there
    is no scrubbing step.

    Anything already present is not repeated, so a model that got it right
    produces the same text it would have produced on its own.
    """
    body = reply.strip()
    lowered = body.lower()

    before: list[str] = []
    if intent.diagnosis_request and DIAGNOSIS_PREAMBLE.lower() not in lowered:
        before.append(DIAGNOSIS_PREAMBLE)
    if intent.medication_change and MEDICATION_PREAMBLE.lower() not in lowered:
        before.append(MEDICATION_PREAMBLE)

    after: list[str] = []
    if intent.medication_change and MEDICATION_GUIDANCE.lower() not in lowered:
        after.append(MEDICATION_GUIDANCE)
    if intent.urgent_language and URGENT_CARE_LINE not in body:
        after.append(URGENT_CARE_LINE)
    if intent.self_harm and CRISIS_LINE not in body:
        after.append(CRISIS_LINE)

    return "\n\n".join(part for part in [*before, body, *after] if part)


# --- what a user may tell Nura about itself ---------------------------------


class UnsafeInstructionError(DomainError):
    """A custom instruction or memory tried to move the boundary it sits in."""

    status_code = 400
    code = "unsafe_instruction"


#: Attempts to switch the medical boundary off (section 26).
_DISABLE_SAFETY = (
    "ignore your safety",
    "ignore safety",
    "no safety",
    "disable safety",
    "without safety",
    "no disclaimers",
    "no disclaimer",
    "skip the disclaimer",
    "don't warn me",
    "dont warn me",
    "stop telling me to see",
    "never tell me to see a doctor",
    "you are a doctor",
    "you're a doctor",
    "act as a doctor",
    "act as my doctor",
    "pretend to be a doctor",
    "you are my doctor",
    "diagnose me",
    "give me a diagnosis",
    "prescribe",
    "tell me what medication to take",
)

#: Attempts to read the instructions themselves (section 26).
_REVEAL_PROMPT = (
    "system prompt",
    "your instructions",
    "your system message",
    "reveal your prompt",
    "print your prompt",
    "repeat your prompt",
    "show me your prompt",
    "initial prompt",
)

#: Attempts to step outside this profile (sections 26 and 105).
_BYPASS = (
    "ignore previous instructions",
    "ignore all previous",
    "disregard previous",
    "disregard all previous",
    "developer mode",
    "jailbreak",
    "other users",
    "another user",
    "other profiles",
    "another profile",
    "other patients",
    "everyone's data",
    "all accounts",
    "admin access",
)

#: Which family a rejected instruction belongs to, for a log line that says
#: what happened without quoting what was typed (section 58).
_CHECKS = (
    ("disable_safety", _DISABLE_SAFETY),
    ("reveal_prompt", _REVEAL_PROMPT),
    ("bypass", _BYPASS),
)


def instruction_risk(text: str) -> str | None:
    """Names the rule a piece of user-authored instruction breaks, or None."""
    lowered = text.lower()
    for label, phrases in _CHECKS:
        if _contains_any(lowered, phrases):
            return label
    return None


def check_instruction(text: str) -> None:
    """Refuses an instruction that tries to disable, reveal or escape.

    Section 26 allows rejecting *or* safely ignoring these. Rejecting is the
    better of the two: somebody who types "act as my doctor" and is quietly
    ignored will believe it worked, and will read the next answer as a
    doctor's. They are told instead.

    This is not the only defence. Anything that gets past these phrases is
    still rendered inside the untrusted fence in ``prompts.py``, with the
    precedence rules restated after it.
    """
    risk = instruction_risk(text)
    if risk is None:
        return
    raise UnsafeInstructionError(
        "Nura can't follow that instruction. It can't be asked to diagnose, "
        "to drop safety information, to reveal how it is set up, or to reach "
        "anyone else's information."
    )
