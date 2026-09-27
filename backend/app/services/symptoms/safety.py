"""Safety-netting: the only thing in PRD 6 that says anything back.

(PRD 6, sections 40-46, 77, 78 and 81.)

Everything else in the symptom system records what somebody told Nura. This
module is the one place that responds to it, so it is kept small, deterministic
and separate from the code that stores anything -- which is what PRD 6
section 45 asks for, so the wording can be reviewed by somebody clinical
without reading a line of symptom logic.

Three rules hold here and are tested as rules rather than left as habits.

**Nura reports recorded change; it does not diagnose deterioration**
(section 41). Every input is something the user did: they chose "worsening",
their own severity number went up across two entries they both confirmed, or
they explicitly logged a new associated symptom. Nothing is inferred from free
text.

**Uncertainty and negation suppress escalation** (sections 24 and 46). A red
flag that appears in ``uncertain_items`` or ``negated_items`` does not fire.
"I'm not sure if I'm short of breath" is not a report of breathlessness, and
treating it as one would be exactly the false certainty section 24 forbids.

**The urgent rules are built, tested and switched off** (section 44). PRD 6
allows red-flag safety-netting only with a reviewed rule set. Nothing here has
been reviewed by a clinician, so ``symptom_red_flag_rules_enabled`` defaults to
False and the only thing this module ever says in a running deployment is the
generic worsening sentence below. The rules are still written down, still
evaluated in tests, and still one setting away -- which is what "leave the
urgent rule architecture ready but disabled" means.

**No diagnosis, ever** (section 81). There is no disease name, no probability
and no cause anywhere in this file, and a test asserts it.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime

from app.core.config import get_settings
from app.models import SymptomEntry

logger = logging.getLogger(__name__)

# --- reviewed copy -----------------------------------------------------------
#
# Everything a user may be shown lives in this block and nowhere else, so it
# can be reviewed and reworded on its own.

#: Shown when the user has recorded a symptom as worsening (PRD 6, s42 and 77).
#: Non-diagnostic, names no condition, and does not tell anybody what to do --
#: it says what was recorded and leaves the decision with them.
WORSENING_NOTICE = (
    "You have recorded this as worsening. If it keeps getting worse, becomes "
    "severe, or is affecting what you can normally do, consider contacting a "
    "healthcare professional."
)

#: Shown alongside a symptom the user has been tracking for a while. Neutral;
#: it is a prompt to talk to somebody, not a warning.
PERSISTENT_NOTICE = (
    "You have been recording this for a while. It may be worth mentioning at "
    "your next appointment."
)

#: How many days of entries before ``PERSISTENT_NOTICE`` applies.
PERSISTENT_AFTER_DAYS = 14

#: The wording used to check an ambiguous concerning statement before anything
#: is concluded from it (PRD 6, section 46). The app asks this; the backend
#: never sees the phrase that prompted it, only the answer.
CONFIRMATION_PREFIX = "Just to confirm:"

#: What Nura says about a symptom photo, every time one is attached
#: (PRD 6, section 32).
PHOTO_NOTICE = "Nura stores your photos for your own records. It does not look at them."

# --- worsening ---------------------------------------------------------------

#: How many points severity must rise across two entries before it counts as a
#: change rather than noise (PRD 6, sections 40 and 41). Two, because a
#: self-reported scale moves by one on a bad afternoon, and calling that
#: "worsening" would make the signal meaningless.
SEVERITY_INCREASE_THRESHOLD = 2

#: Why an episode is being reported as worsening. Codes, not sentences, so the
#: app words them and this module stays free of user-facing text beyond the
#: reviewed block above.
WORSENING_REASONS = (
    "reported_worsening",
    "severity_increase",
    "new_associated_symptom",
)

# --- red flags (built, tested, disabled) -------------------------------------


@dataclass(frozen=True)
class RedFlagRule:
    """One deterministic rule over what the user explicitly confirmed.

    ``terms`` are canonical phrases. They are the exact strings the guided flow
    writes after the user has confirmed a concerning statement, which is why
    matching is an equality test and not a search for words in a sentence: a
    rule that pattern-matched prose would fire on "I was worried I might faint"
    (PRD 6, section 46).
    """

    code: str
    terms: tuple[str, ...]
    #: Reviewed wording would go here. Still non-diagnostic: it points at
    #: urgent care without naming a cause (PRD 6, sections 42 and 81).
    message: str


#: The categories PRD 6 section 44 lists. **Unreviewed.** They are written down
#: so the shape is real and testable; the messages are a placeholder for
#: clinically reviewed copy and are unreachable while the setting is off.
RED_FLAG_RULES: tuple[RedFlagRule, ...] = (
    RedFlagRule(
        code="severe_breathing_difficulty",
        terms=("severe difficulty breathing", "cannot breathe"),
        message=(
            "You have told Nura you are having severe difficulty breathing. "
            "Please seek urgent medical help now."
        ),
    ),
    RedFlagRule(
        code="loss_of_consciousness",
        terms=("loss of consciousness", "passed out"),
        message=(
            "You have told Nura you lost consciousness. Please seek urgent "
            "medical help now."
        ),
    ),
    RedFlagRule(
        code="new_severe_chest_pain",
        terms=("new severe chest pain", "severe chest pain"),
        message=(
            "You have told Nura you have new severe chest pain. Please seek "
            "urgent medical help now."
        ),
    ),
    RedFlagRule(
        code="uncontrolled_bleeding",
        terms=("uncontrolled bleeding", "heavy bleeding that will not stop"),
        message=(
            "You have told Nura you have bleeding that will not stop. Please "
            "seek urgent medical help now."
        ),
    ),
    RedFlagRule(
        code="new_severe_weakness",
        terms=("new severe weakness", "sudden weakness on one side"),
        message=(
            "You have told Nura you have sudden severe weakness. Please seek "
            "urgent medical help now."
        ),
    ),
)

#: Every canonical phrase any rule matches on. Mirrored in the app so the two
#: cannot drift, with a test on each side asserting they still agree.
RED_FLAG_TERMS: tuple[str, ...] = tuple(
    term for rule in RED_FLAG_RULES for term in rule.terms
)


def rules_enabled() -> bool:
    """Whether the urgent rules are switched on for this deployment.

    False everywhere until the rule set and its wording have been reviewed
    (PRD 6, section 44).
    """
    return get_settings().symptom_red_flag_rules_enabled


# --- assessment --------------------------------------------------------------


@dataclass(frozen=True)
class SafetyAssessment:
    """What Nura may say about an episode, and why.

    ``notice`` is the only field with user-facing text in it, and it is always
    one of the reviewed constants above -- never assembled from the user's own
    words, which is how a "notice" turns into a summary of somebody's symptoms
    on a lock screen.
    """

    #: True only when the user recorded a change, never when Nura guessed one.
    worsening: bool = False
    #: Codes from ``WORSENING_REASONS``, in the order they were found.
    reasons: tuple[str, ...] = ()
    notice: str | None = None
    #: Codes of any red-flag rule that matched. Always empty while the rules
    #: are disabled, which is the shipped state.
    red_flags: tuple[str, ...] = field(default_factory=tuple)
    #: True when a rule matched *and* the rules are enabled. The app shows the
    #: urgent wording only on this, never on ``red_flags`` alone.
    urgent: bool = False


def _normalised(items: list[str] | None) -> set[str]:
    return {item.strip().lower() for item in (items or []) if item.strip()}


def _confirmed_terms(entry: SymptomEntry) -> set[str]:
    """What the user actually said, with anything hedged or denied removed.

    This is the whole of PRD 6 section 46 in four lines: a concerning phrase
    only counts when it is neither uncertain nor negated, so nothing escalates
    off a guess about what somebody meant.
    """
    stated = _normalised(entry.associated_symptoms)
    if entry.main_symptom:
        stated.add(entry.main_symptom.strip().lower())
    return stated - _normalised(entry.uncertain_items) - _normalised(entry.negated_items)


def match_red_flags(entry: SymptomEntry) -> tuple[str, ...]:
    """Rule codes matching what this entry explicitly confirms.

    Evaluated whether or not the rules are enabled, so the layer is exercised
    by the tests and a later review has something real to review. Nothing is
    *shown* unless ``rules_enabled()``.
    """
    confirmed = _confirmed_terms(entry)
    return tuple(
        rule.code
        for rule in RED_FLAG_RULES
        if any(term in confirmed for term in rule.terms)
    )


def red_flag_message(codes: tuple[str, ...]) -> str | None:
    """The reviewed wording for the first matching rule, or None.

    Returns None while the rules are disabled, whatever matched. That is the
    one place the setting is honoured, so there is no path where a caller can
    reach the urgent copy by accident.
    """
    if not codes or not rules_enabled():
        return None
    by_code = {rule.code: rule for rule in RED_FLAG_RULES}
    for code in codes:
        rule = by_code.get(code)
        if rule is not None:
            return rule.message
    return None


def assess(
    latest: SymptomEntry | None,
    previous: SymptomEntry | None = None,
    *,
    first_recorded_at: datetime | None = None,
    now: datetime | None = None,
) -> SafetyAssessment:
    """What, if anything, Nura should say about this episode.

    ``latest`` and ``previous`` are the two most recent entries. Only the
    user's own recorded facts are consulted:

      - they chose "worsening" on the latest entry;
      - their severity rose by ``SEVERITY_INCREASE_THRESHOLD`` or more between
        two entries they each saved deliberately;
      - they added an associated symptom that was not in the previous entry.

    Severity alone is never enough, whatever the number: PRD 6 section 78 rules
    out treating 10/10 as a confirmed emergency, and this function has no
    branch on an absolute severity anywhere.
    """
    if latest is None:
        return SafetyAssessment()

    reasons: list[str] = []

    if latest.change_state == "worsening":
        reasons.append("reported_worsening")

    if previous is not None:
        if (
            latest.severity is not None
            and previous.severity is not None
            and latest.severity - previous.severity >= SEVERITY_INCREASE_THRESHOLD
        ):
            reasons.append("severity_increase")

        added = _normalised(latest.associated_symptoms) - _normalised(
            previous.associated_symptoms
        )
        if added:
            reasons.append("new_associated_symptom")

    red_flags = match_red_flags(latest)
    urgent_message = red_flag_message(red_flags)

    notice: str | None = None
    if urgent_message is not None:
        notice = urgent_message
    elif reasons:
        notice = WORSENING_NOTICE
    elif (
        first_recorded_at is not None
        and now is not None
        and (now - first_recorded_at).days >= PERSISTENT_AFTER_DAYS
    ):
        notice = PERSISTENT_NOTICE

    if notice is not None:
        # The reason is recorded, never the symptom (PRD 6, sections 62, 65).
        logger.info("symptom.safety.notice shown")

    return SafetyAssessment(
        worsening=bool(reasons),
        reasons=tuple(reasons),
        notice=notice,
        red_flags=red_flags,
        urgent=urgent_message is not None,
    )
