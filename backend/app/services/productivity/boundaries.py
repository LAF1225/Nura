"""The one thing a daily-life tool must refuse to be (PRD 12, section 23).

Section 23 names the risk exactly: *generic daily-life tools must not become a
bypass around medical safeguards.* The example is the dangerous one --

    Remind me to double my medication tomorrow.

-- and the point is that it is not an attack. It is an ordinary sentence
somebody might well say, and a reminder app that writes it down without comment
has quietly become a place where a dose change gets recorded as a decision.

**What Nura cannot do is already structural.** There is no tool, anywhere, that
changes a medication, a schedule or a dose. PRD 8 section 15 ruled it out and
PRD 12 does not add one, so nothing here is holding back a capability. What
this module does is narrower and still worth doing: it recognises the phrasing,
so the note gets written *and* the person is told where dose changes come from.
Section 23's own answer, in section 23's own words, is
``wording.MEDICATION_CHANGE_BOUNDARY``.

**It is deliberately conservative.** A dose-change verb *and* a medication noun
have to both be present, because "remind me to pick up my medication" is an
ordinary errand and treating it as a medical event would make Nura tiresome in
a way that teaches people to phrase things to avoid it. Matching is on words,
not substrings, so "doubles" does not match inside "troubleshoot".

**Nothing is blocked.** This returns a flag. The caller writes the note either
way, because refusing to write down something the person asked for would leave
them with nothing -- and a reminder to talk to the pharmacist is a perfectly
good thing to have written down.
"""

import re
from collections.abc import Iterable

#: Verbs and phrases that describe changing what somebody takes.
_CHANGE_WORDS = frozenset(
    {
        "double",
        "doubling",
        "triple",
        "increase",
        "increasing",
        "decrease",
        "decreasing",
        "reduce",
        "reducing",
        "halve",
        "extra",
        "more",
        "less",
        "skip",
        "skipping",
        "stop",
        "stopping",
        "quit",
        "quitting",
        "change",
        "changing",
        "switch",
        "switching",
    }
)

#: ``up`` and ``down`` are deliberately **not** here. "Double up" already
#: matches on ``double``, and "pick up my medication" is an errand -- treating
#: it as a medical event is exactly the tiresome false positive this module's
#: docstring warns about, and the kind that teaches people to phrase things to
#: avoid it.

#: Nouns that mean "the thing somebody takes".
_MEDICATION_WORDS = frozenset(
    {
        "dose",
        "doses",
        "dosage",
        "medication",
        "medications",
        "medicine",
        "medicines",
        "med",
        "meds",
        "tablet",
        "tablets",
        "pill",
        "pills",
        "capsule",
        "capsules",
        "insulin",
        "injection",
        "injections",
        "inhaler",
        "prescription",
    }
)

_WORD = re.compile(r"[a-z]+")


def mentions_medication_change(
    *parts: str | None, medication_names: Iterable[str] = ()
) -> bool:
    """Whether this text reads as changing what somebody takes (section 23).

    Takes several strings -- a title and a note, say -- because the phrasing
    may be split across them and checking only the title would be a gap
    somebody finds by accident.

    ``medication_names`` is what makes it work on real sentences. "Double my
    metformin tomorrow" has a change word and no medication *noun* in it, and
    no fixed list could ever hold every drug name -- so the caller passes the
    names on this person's own record, and a name they are actually taking
    counts as a medication word. Somebody else's drug name does not, which is
    both more accurate and the privacy-respecting direction.
    """
    words = set()
    for part in parts:
        if part:
            words.update(_WORD.findall(part.lower()))
    if not words & _CHANGE_WORDS:
        return False
    if words & _MEDICATION_WORDS:
        return True
    own = {
        token
        for name in medication_names
        for token in _WORD.findall(name.lower())
        if len(token) > 3
    }
    return bool(words & own)


#: Words that would make a routine a clinical prescription if Nura chose it
#: (section 24). Used only to decide whether to *add a sentence*: a person may
#: absolutely create a physiotherapy routine their clinician gave them, and
#: nothing here stops them.
_CLINICAL_WORDS = frozenset(
    {
        "physiotherapy",
        "physio",
        "rehab",
        "rehabilitation",
        "therapy",
        "treatment",
        "prescribed",
        "prescription",
        "exercises",
    }
)


def mentions_clinical_routine(*parts: str | None) -> bool:
    """Whether a routine reads as clinical (section 24).

    The caller uses this to attach ``wording.CLINICAL_ROUTINE_BOUNDARY`` to the
    result it hands the model, so the reply says plainly that Nura is writing
    down what the person decided rather than deciding it. It does not refuse,
    and it must not: "evening stretch, as my physio showed me" is exactly the
    routine section 15 says somebody may enter.
    """
    words = set()
    for part in parts:
        if part:
            words.update(_WORD.findall(part.lower()))
    return bool(words & _CLINICAL_WORDS)
