"""Neutral question prompts (PRD 7, section 24).

Deterministic rules over the review the user is already looking at. **There is
no model behind this**, and PRD 7 section 24 says so outright: these are `if`
statements with wording written once and reviewed, not generated sentences.

Three rules govern what may be suggested, and they are what makes a prompt safe:

**A suggestion points at something the user recorded, and says nothing about
it.** "Would you like to ask about your worsening headaches?" restates their own
answer. What it must never do is explain, connect or predict -- no "could your
medication be causing this?", because that is a clinical hypothesis and Nura
does not have those (sections 3 and 45).

**Nothing is added until the user says so.** These are offers. Accepting one
writes an ordinary question in the ordinary table, and from then on it is
indistinguishable from one they typed -- because it is theirs
(section 24).

**A suggestion is never a nudge about behaviour.** The medication prompt is
about the *schedule*, offered whenever any dose went unrecorded, and it is
phrased as a question for the clinician rather than a comment on adherence
(section 18's refusal to grade it).
"""

from dataclasses import dataclass

from app.services.appointments.preparation import PreparationData

#: How many to offer. The screen is a list of the user's own questions with a
#: few offers underneath; more than this and the offers become the screen.
MAX_SUGGESTIONS = 4


@dataclass(frozen=True)
class QuestionSuggestion:
    """One offer, and the question it would add."""

    #: Stable across calls, so a client can remember which were dismissed.
    key: str
    #: What Nura asks the user -- "Would you like to ask about ...?"
    prompt: str
    #: What is added if they accept, phrased as they would ask it.
    question_text: str
    #: Why it was offered, for the app to group by. Never shown as a reason.
    reason: str


def _normalise(text: str) -> str:
    """For comparing a suggestion against what the user has already asked."""
    return " ".join(text.lower().split())


def suggest(data: PreparationData) -> list[QuestionSuggestion]:
    """Offers for this appointment, in the order they should be shown.

    Ordered by how specific they are: a symptom the person recorded as getting
    worse first, then a new symptom, then the medication schedule, then the one
    generic prompt. Anything already on their list is dropped, so accepting a
    suggestion makes it disappear rather than offering it twice.
    """
    suggestions: list[QuestionSuggestion] = []

    worsening = [
        review
        for review in data.symptoms
        if review.latest_change_state == "worsening" and review.entry_count > 0
    ]
    for review in worsening:
        name = review.name.strip()
        suggestions.append(
            QuestionSuggestion(
                key=f"worsening:{review.episode_id}",
                prompt=f"Would you like to ask about your worsening {name.lower()}?",
                question_text=(
                    f"My {name.lower()} has been getting worse — what should I do?"
                ),
                reason="symptom_worsening",
            )
        )

    # A symptom whose first entry in the period is also the start of the
    # episode: something that began since the last visit, which is the thing
    # people most often mean to mention and most often forget.
    started = [
        review
        for review in data.symptoms
        if review.entry_count > 0
        and review.first_entry_at is not None
        and review.first_entry_at.date() >= data.period.start
        and review.latest_change_state != "worsening"
    ]
    for review in started:
        name = review.name.strip()
        suggestions.append(
            QuestionSuggestion(
                key=f"new:{review.episode_id}",
                prompt=f"Would you like to ask about your new {name.lower()}?",
                question_text=f"I’ve started getting {name.lower()} — what could I do?",
                reason="symptom_new",
            )
        )

    adherence = data.adherence
    if adherence is not None and (adherence.skipped > 0 or adherence.missed > 0):
        suggestions.append(
            QuestionSuggestion(
                key="medication_schedule",
                prompt="Would you like to ask about your medication schedule?",
                question_text="Is my current medication schedule still right for me?",
                reason="doses_unrecorded",
            )
        )

    # Offered to everybody, because it is the question people wish they had
    # asked and it assumes nothing about their records.
    suggestions.append(
        QuestionSuggestion(
            key="follow_up_tests",
            prompt="Would you like to ask whether you need any follow-up tests?",
            question_text="Do I need any follow-up tests?",
            reason="generic",
        )
    )

    asked = {_normalise(question.text) for question in data.questions}
    unique = [
        suggestion
        for suggestion in suggestions
        if _normalise(suggestion.question_text) not in asked
    ]
    return unique[:MAX_SUGGESTIONS]
