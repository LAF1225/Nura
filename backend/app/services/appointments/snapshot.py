"""Turning selected records into the finished report (PRD 7, sections 16, 26-31).

This is the one file where recorded facts become sentences. Everything before it
counts rows; everything after it lays out text. So the question "does Nura say
anything it should not?" has exactly one place to be answered, and a test can
read every sentence this module can produce.

**What it may say.** PRD 7 section 16 gives the shape: *"Headache was logged 6
times during the selected period. Severity ranged from 3/10 to 6/10. The latest
entry was marked worsening."* Restatement, with the user's own words quoted and
the counts counted.

**What it may not say.** No diagnosis, no likelihood, no cause, no treatment, no
judgement of adherence, no interpretation of a wellbeing pattern
(sections 3, 18, 20 and 45). There is no code path here that could produce one:
every sentence is a template with values substituted in.

**Uncertainty is carried, not resolved.** A symptom the person was unsure about
appears as something they were unsure about; one they explicitly denied appears
as denied. Neither is dropped and neither is promoted (sections 16 and 47).

**Missing data is stated or omitted, never invented** (section 46). A section
the user asked for with nothing in it reads "Not recorded", which is worth
saying: a doctor learning that no allergies are recorded is different from a
doctor being shown nothing at all.

**The result is frozen.** The dict this builds is stored on the report row, and
the PDF is rendered from it. Editing a symptom entry tomorrow cannot change what
a report generated today says (section 30).
"""

import math
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from app.models.enums import REPORT_SECTIONS
from app.services.appointments import appointments as appointment_service
from app.services.appointments import periods as period_service
from app.services.appointments.preparation import (
    AdherenceReview,
    AllergyItem,
    BaselineReview,
    CheckInReview,
    MedicationReview,
    PreparationData,
    SymptomReview,
)
from app.services.appointments.wording import (
    format_day_short,
    format_moment,
    join_items,
    plural,
)

#: Bumped if the shape of a stored snapshot changes. A renderer reads this
#: first, so an old report keeps rendering after the shape moves on.
SCHEMA_VERSION = 1

REPORT_TITLE = "Nura Health Summary"

#: On every report, always, whatever the user selected. This is the sentence
#: that keeps a summary of records from being read as a clinical opinion
#: (PRD 7, section 45).
DISCLAIMER = (
    "This is a summary of information recorded in the Nura app. "
    "It is not a diagnosis, an assessment or medical advice."
)

#: What each selectable section is called in the report.
SECTION_HEADINGS = {
    "focus": "Reason for this visit",
    "symptoms": "Recent symptoms",
    "medications": "Current medications",
    "adherence": "Medication doses",
    "checkins": "Daily check-ins",
    "background": "Relevant health background",
    "questions": "Questions for the clinician",
}

APPENDIX_HEADINGS = {
    "symptom_timeline": "Appendix A — symptom timeline",
    "adherence_detail": "Appendix B — medication dose detail",
    "skipped_doses": "Appendix C — skipped and missed doses",
    "wellbeing_notes": "Appendix D — daily check-in notes",
    "medical_notes": "Appendix E — medical notes",
}

#: How the user's change-state answer is written out. Their answer, restated --
#: nothing here concludes anything from the numbers (PRD 6, section 41).
CHANGE_STATE_SENTENCE = {
    "improving": "The latest entry was marked improving.",
    "same": "The latest entry was marked unchanged.",
    "worsening": "The latest entry was marked worsening.",
    "unsure": "The latest entry said the change was unclear.",
}

WELLBEING_LABELS = {"good": "Good", "okay": "Okay", "not_great": "Not great"}

CONDITION_STATUS_SUFFIX = {"uncertain": " (recorded as uncertain)"}

ALLERGY_SEVERITY_LABELS = {
    "mild": "mild",
    "moderate": "moderate",
    "severe": "severe",
    "unknown": "severity not recorded",
}

SKIP_REASON_LABELS = {
    "none": "no reason given",
    "feeling_unwell": "feeling unwell",
    "ran_out": "ran out",
    "clinician_advised": "advised by a clinician",
    "too_late": "too late in the day",
    "other": "other",
}

#: Said when a section was asked for and there is nothing in it (s46).
NOT_RECORDED = "Not recorded."

#: Roughly how many lines of 10pt text fit on one A4 page under the header.
#: Used only to decide when to tighten the summary; it never changes the font
#: size, because PRD 7 section 26 rules that out.
ONE_PAGE_LINE_BUDGET = 44

#: Characters per line at 10pt Helvetica across the usable width. Approximate on
#: purpose -- it is a budget, not a layout engine.
CHARS_PER_LINE = 95


# --- what the user chose ----------------------------------------------------


def default_include() -> dict[str, bool]:
    """Every section on except medical notes (PRD 7, section 25).

    Notes are off because they are long-form and often about something else
    entirely; the rest are the things a doctor asks for at the start of a visit.
    """
    return {key: key != "medical_notes" for key in REPORT_SECTIONS}


@dataclass(frozen=True)
class ReportSelection:
    """Exactly what the user asked to be in the report (PRD 7, sections 25, 50).

    Symptoms are chosen individually rather than by a single switch, because
    PRD 7 section 15 forbids Nura deciding which symptom matters more -- and one
    switch would be Nura deciding.

    ``medication_ids`` of None means "the active ones", which is the default the
    review screen shows. An explicit empty list means the user unticked them
    all, and is honoured.
    """

    include: dict[str, bool] = field(default_factory=default_include)
    symptom_episode_ids: list[uuid.UUID] = field(default_factory=list)
    #: Which free-text symptom notes to quote (PRD 7, section 16).
    symptom_note_entry_ids: list[uuid.UUID] = field(default_factory=list)
    medication_ids: list[uuid.UUID] | None = None
    #: Which wellbeing notes to quote (PRD 7, section 20).
    checkin_note_dates: list[date] = field(default_factory=list)
    #: Which medical notes to attach (PRD 7, section 27).
    medical_note_ids: list[uuid.UUID] = field(default_factory=list)
    #: The user's own words for why they are going (PRD 7, section 26).
    focus: str | None = None
    include_appendix: bool = False
    #: Free-text skip reasons. Off unless asked for (PRD 7, section 19).
    include_skip_reason_notes: bool = False

    def selected(self, key: str) -> bool:
        return bool(self.include.get(key, False))

    def as_dict(self) -> dict[str, Any]:
        """JSON for the ``selection`` column, and for the app to restore from."""
        return {
            "include": dict(self.include),
            "symptom_episode_ids": [str(value) for value in self.symptom_episode_ids],
            "symptom_note_entry_ids": [
                str(value) for value in self.symptom_note_entry_ids
            ],
            "medication_ids": (
                None
                if self.medication_ids is None
                else [str(value) for value in self.medication_ids]
            ),
            "checkin_note_dates": [
                value.isoformat() for value in self.checkin_note_dates
            ],
            "medical_note_ids": [str(value) for value in self.medical_note_ids],
            "focus": self.focus,
            "include_appendix": self.include_appendix,
            "include_skip_reason_notes": self.include_skip_reason_notes,
        }


# --- building blocks --------------------------------------------------------


def _item(title: str | None, lines: list[str]) -> dict[str, Any]:
    return {"title": title, "lines": [line for line in lines if line]}


def _section(key: str, heading: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    return {"key": key, "heading": heading, "items": items}


def _estimate_lines(sections: list[dict[str, Any]]) -> int:
    """Roughly how many rendered lines these sections need.

    Each heading costs two (itself and the space around it); each item's title
    costs one; each body line costs as many as it wraps to.
    """
    total = 0
    for section in sections:
        total += 2
        for item in section["items"]:
            if item["title"]:
                total += 1
            for line in item["lines"]:
                total += max(1, math.ceil(len(line) / CHARS_PER_LINE))
    return total


# --- the header -------------------------------------------------------------


def _header(data: PreparationData) -> dict[str, Any]:
    """Who, when, where and over what period (PRD 7, section 26)."""
    appointment = data.appointment
    zone = appointment_service.local_zone(appointment)
    lines = [f"Report period: {data.period.label}"]

    since = period_service.describe_since_last_visit(data.period)
    if since:
        lines.append(since)

    lines.append(
        f"Appointment: {appointment.title} — "
        f"{format_moment(appointment.scheduled_at, zone)} ({appointment.timezone})"
    )

    clinician = appointment.clinician
    if clinician is not None:
        detail = f", {clinician.specialty}" if clinician.specialty else ""
        lines.append(f"Clinician: {clinician.name}{detail}")

    place = appointment.location_name or appointment.address
    if place:
        lines.append(f"Location: {place}")

    return {
        "patient": data.profile.preferred_name,
        "lines": lines,
        # Repeated here so a renderer does not have to reach into `period`. The
        # reason for the visit is deliberately *not* here: it has its own
        # section, and one value in two places invites the two to disagree.
        "period_label": data.period.label,
    }


# --- symptoms ---------------------------------------------------------------


def _severity_sentence(review: SymptomReview) -> str | None:
    """The range, or the single reading, or nothing.

    "Severity ranged from 3/10 to 6/10" needs two different numbers to be true.
    One reading says so; no readings say nothing at all, because a symptom
    without a number is not a symptom with a severity of zero
    (PRD 6, section 22).
    """
    low, high = review.severity_min, review.severity_max
    if low is None or high is None:
        return None
    if low == high:
        return f"Severity recorded as {high}/10."
    return f"Severity ranged from {low}/10 to {high}/10."


def _symptom_item(
    review: SymptomReview,
    *,
    note_entry_ids: set[uuid.UUID],
    detailed: bool,
) -> dict[str, Any]:
    """One symptom, in the wording PRD 7 section 16 allows."""
    title = review.name if not review.body_site else f"{review.name} ({review.body_site})"
    lines: list[str] = []

    if review.entry_count == 0:
        # An ongoing symptom with nothing in the window. Said plainly, because
        # silence here would read as "it stopped".
        lines.append("Still ongoing. No entries during this period.")
    else:
        logged = plural(review.entry_count, "time")
        lines.append(f"Logged {logged} during this period.")

    severity = _severity_sentence(review)
    if severity:
        lines.append(severity)

    if review.latest_change_state:
        lines.append(CHANGE_STATE_SENTENCE[review.latest_change_state])

    if review.first_noticed_label:
        lines.append(f"First noticed: {review.first_noticed_label}.")

    if not detailed:
        return _item(title, lines)

    if review.associated_symptoms:
        lines.append(f"Also reported: {join_items(review.associated_symptoms)}.")
    if review.exacerbating_factors:
        lines.append(f"Worse with: {join_items(review.exacerbating_factors)}.")
    if review.relieving_factors:
        lines.append(f"Better with: {join_items(review.relieving_factors)}.")
    if review.context_dependent_items:
        lines.append(
            f"Reported only in certain situations: "
            f"{join_items(review.context_dependent_items)}."
        )
    # Both of these preserve what the person actually said (PRD 7, section 47).
    if review.uncertain_items:
        lines.append(f"Unsure about: {join_items(review.uncertain_items)}.")
    if review.negated_items:
        lines.append(f"Said were not present: {join_items(review.negated_items)}.")

    for note in review.notes:
        if note.entry_id in note_entry_ids:
            lines.append(
                f"Their words ({format_day_short(note.recorded_at.date())}): "
                f"“{note.text}”"
            )

    return _item(title, lines)


def _symptom_section(
    data: PreparationData, selection: ReportSelection, *, detailed: bool
) -> dict[str, Any] | None:
    chosen = set(selection.symptom_episode_ids)
    if not chosen:
        return None

    note_ids = set(selection.symptom_note_entry_ids)
    items = [
        _symptom_item(review, note_entry_ids=note_ids, detailed=detailed)
        for review in data.symptoms
        if review.episode_id in chosen
    ]
    if not items:
        return None
    return _section("symptoms", SECTION_HEADINGS["symptoms"], items)


# --- medications ------------------------------------------------------------


def _selected_medications(
    data: PreparationData, selection: ReportSelection
) -> list[MedicationReview]:
    if selection.medication_ids is None:
        return list(data.medications)
    chosen = set(selection.medication_ids)
    return [review for review in data.medications if review.medication_id in chosen]


def _medication_section(
    data: PreparationData, selection: ReportSelection
) -> dict[str, Any] | None:
    if not selection.selected("medications"):
        return None

    items = [
        _item(
            review.display_name,
            [review.frequency or "How often is not recorded."]
            + ([f"For: {review.reason}"] if review.reason else []),
        )
        for review in _selected_medications(data, selection)
    ]
    return _section(
        "medications",
        SECTION_HEADINGS["medications"],
        items or [_item(None, [NOT_RECORDED])],
    )


# --- adherence --------------------------------------------------------------


def _adherence_lines(adherence: AdherenceReview) -> list[str]:
    """Counts, never a grade (PRD 7, sections 18 and 19).

    The denominator is stated in the same sentence as the numerator, so the
    figure cannot be read out of context. No percentage in the summary: PRD 7
    section 18 prefers counts, and the appendix carries the percentage with its
    period attached.
    """
    if adherence.total == 0:
        return ["No doses were scheduled during this period."]

    lines = [
        f"{adherence.taken} of {adherence.total} scheduled doses were marked as taken."
    ]
    if adherence.skipped:
        lines.append(f"{plural(adherence.skipped, 'dose')} skipped.")
    if adherence.missed:
        lines.append(
            f"{plural(adherence.missed, 'dose')} not marked as taken or skipped."
        )
    return lines


def _adherence_section(
    data: PreparationData, selection: ReportSelection
) -> dict[str, Any] | None:
    adherence = data.adherence
    if not selection.selected("adherence") or adherence is None:
        return None
    return _section(
        "adherence",
        SECTION_HEADINGS["adherence"],
        [_item(None, _adherence_lines(adherence))],
    )


# --- health background ------------------------------------------------------


def _condition_line(name: str, status: str, diagnosed: str | None) -> str:
    suffix = CONDITION_STATUS_SUFFIX.get(status, "")
    when = f", diagnosed {diagnosed}" if diagnosed else ""
    return f"{name}{when}{suffix}"


def _background_section(
    data: PreparationData, selection: ReportSelection, *, detailed: bool
) -> dict[str, Any] | None:
    """Conditions, allergies, procedures and blood type (PRD 7, section 21).

    One item per group rather than per record, because this is the compact part
    of a one-page summary. ``detailed`` False collapses each group onto a single
    line, which is the last thing tried before letting the summary run on
    (section 26).
    """
    baseline = data.baseline
    if baseline is None:
        return None

    items: list[dict[str, Any]] = []

    if selection.selected("conditions"):
        lines = [
            _condition_line(item.name, item.status, item.diagnosed_label)
            for item in baseline.conditions
        ]
        items.append(_group("Conditions", lines, detailed=detailed))

    if selection.selected("allergies"):
        lines = [_allergy_line(item) for item in baseline.allergies]
        items.append(_group("Allergies", lines, detailed=detailed))

    if selection.selected("procedures"):
        lines = [
            f"{item.name}{f' — {item.performed_label}' if item.performed_label else ''}"
            for item in baseline.procedures
        ]
        items.append(_group("Recent procedures", lines, detailed=detailed))

    if selection.selected("blood_type"):
        items.append(_item("Blood type", [_blood_type_line(baseline)]))

    if not items:
        return None
    return _section("background", SECTION_HEADINGS["background"], items)


def _checkin_section(
    data: PreparationData, selection: ReportSelection
) -> dict[str, Any] | None:
    review = data.checkins
    if not selection.selected("daily_checkins") or review is None:
        return None
    return _section(
        "checkins",
        SECTION_HEADINGS["checkins"],
        [_item(None, _checkin_lines(review, selection))],
    )


def _group(title: str, lines: list[str], *, detailed: bool) -> dict[str, Any]:
    """A titled group of short lines, collapsed to one line when condensing."""
    if not lines:
        return _item(title, [NOT_RECORDED])
    if detailed:
        return _item(title, lines)
    return _item(title, [join_items(lines)])


def _allergy_line(item: AllergyItem) -> str:
    severity = ALLERGY_SEVERITY_LABELS.get(item.severity, item.severity)
    reaction = f" — {item.reaction}" if item.reaction else ""
    return f"{item.allergen}{reaction} ({severity})"


def _blood_type_line(baseline: BaselineReview) -> str:
    """Blood type, with the two answers that are not a group handled honestly."""
    value = baseline.blood_type
    if value is None or value == "prefer_not_to_say":
        return NOT_RECORDED
    if value == "unknown":
        return "Not known."
    return value


def _checkin_lines(review: CheckInReview, selection: ReportSelection) -> list[str]:
    """Three counts, and any notes the user picked (PRD 7, section 20).

    No interpretation of the pattern. "Not great: 4 days" is a count of what
    somebody tapped, and PRD 7 section 20 rules out reading anything into it.
    """
    if review.total == 0:
        return ["No check-ins recorded during this period."]

    counts = ", ".join(
        f"{WELLBEING_LABELS[level]}: {plural(count, 'day')}"
        for level, count in (
            ("good", review.good),
            ("okay", review.okay),
            ("not_great", review.not_great),
        )
        if count
    )
    lines = [
        f"Recorded on {review.total} of {plural(review.days_in_period, 'day')}.",
        counts + ".",
    ]

    chosen = set(selection.checkin_note_dates)
    for note in review.notes:
        if note.checkin_date in chosen:
            lines.append(
                f"{format_day_short(note.checkin_date)} "
                f"({WELLBEING_LABELS[note.wellbeing_level].lower()}): “{note.note}”"
            )
    return lines


# --- questions --------------------------------------------------------------


def _question_section(
    data: PreparationData, selection: ReportSelection
) -> dict[str, Any] | None:
    """The user's questions, verbatim and in their order (PRD 7, section 23)."""
    if not selection.selected("questions"):
        return None
    if not data.questions:
        return None
    return _section(
        "questions",
        SECTION_HEADINGS["questions"],
        [_item(None, [question.text]) for question in data.questions],
    )


def _focus_section(selection: ReportSelection) -> dict[str, Any] | None:
    focus = (selection.focus or "").strip()
    if not focus:
        return None
    return _section("focus", SECTION_HEADINGS["focus"], [_item(None, [focus])])


# --- the appendix -----------------------------------------------------------


def _timeline_section(
    data: PreparationData, selection: ReportSelection
) -> dict[str, Any] | None:
    """Every entry for the selected symptoms, oldest first (PRD 7, section 27)."""
    chosen = set(selection.symptom_episode_ids)
    items: list[dict[str, Any]] = []

    for review in data.symptoms:
        lines: list[str]
        if review.episode_id not in chosen:
            continue
        if not review.entry_count and not review.notes:
            continue
        lines = []
        if review.first_noticed_label:
            lines.append(f"First noticed: {review.first_noticed_label}.")
        lines.extend(_timeline_lines(review))
        if lines:
            items.append(_item(review.name, lines))

    if not items:
        return None
    return _section("symptom_timeline", APPENDIX_HEADINGS["symptom_timeline"], items)


def _timeline_lines(review: SymptomReview) -> list[str]:
    """One line per entry: when, how bad, how it changed, what they wrote.

    Built from the review's notes and counts rather than from a second query, so
    the appendix cannot disagree with the summary above it.
    """
    lines: list[str] = []
    if review.entry_count:
        first = review.first_entry_at
        latest = review.latest_entry_at
        if first and latest and first.date() != latest.date():
            lines.append(
                f"{plural(review.entry_count, 'entry', 'entries')} between "
                f"{format_day_short(first.date())} and "
                f"{format_day_short(latest.date())}."
            )
        elif latest:
            lines.append(
                f"{plural(review.entry_count, 'entry', 'entries')} on "
                f"{format_day_short(latest.date())}."
            )
    for note in review.notes:
        lines.append(f"{format_day_short(note.recorded_at.date())}: “{note.text}”")
    return lines


def _adherence_detail_section(
    data: PreparationData, selection: ReportSelection
) -> dict[str, Any] | None:
    adherence = data.adherence
    if not selection.selected("adherence") or adherence is None:
        return None
    if adherence.total == 0:
        return None

    lines = [
        f"Period: {data.period.label}.",
        f"Scheduled: {adherence.total}. Marked taken: {adherence.taken}. "
        f"Skipped: {adherence.skipped}. Not marked: {adherence.missed}.",
    ]
    if adherence.percent is not None:
        # The one place a percentage appears, with its period named in the line
        # above it, exactly as PRD 7 section 18 requires.
        lines.append(f"{adherence.percent}% of doses in this period were marked taken.")
    return _section(
        "adherence_detail", APPENDIX_HEADINGS["adherence_detail"], [_item(None, lines)]
    )


def _skipped_section(
    data: PreparationData, selection: ReportSelection
) -> dict[str, Any] | None:
    """Skipped doses, with the user's own words only if they asked (s19)."""
    adherence = data.adherence
    if not selection.selected("adherence") or adherence is None:
        return None
    if not adherence.skip_notes:
        return None

    items: list[dict[str, Any]] = []
    for note in adherence.skip_notes:
        reason = SKIP_REASON_LABELS.get(
            note.reason_code or "none", note.reason_code or "none"
        )
        line = f"{format_day_short(note.local_date)} — {note.medication_name}: {reason}"
        if selection.include_skip_reason_notes and note.reason_text:
            line += f" — “{note.reason_text}”"
        items.append(_item(None, [line]))

    return _section("skipped_doses", APPENDIX_HEADINGS["skipped_doses"], items)


def _wellbeing_notes_section(
    data: PreparationData, selection: ReportSelection
) -> dict[str, Any] | None:
    review = data.checkins
    if not selection.selected("daily_checkins") or review is None:
        return None
    chosen = set(selection.checkin_note_dates)
    items = [
        _item(
            None,
            [
                f"{format_day_short(note.checkin_date)} "
                f"({WELLBEING_LABELS[note.wellbeing_level].lower()}): “{note.note}”"
            ],
        )
        for note in review.notes
        if note.checkin_date in chosen
    ]
    if not items:
        return None
    return _section("wellbeing_notes", APPENDIX_HEADINGS["wellbeing_notes"], items)


def _medical_notes_section(
    data: PreparationData, selection: ReportSelection
) -> dict[str, Any] | None:
    """Medical notes the user picked out, verbatim (PRD 7, section 27)."""
    if not selection.selected("medical_notes"):
        return None
    chosen = set(selection.medical_note_ids)
    items = [
        _item(note.title, [note.body])
        for note in data.medical_notes
        if note.note_id in chosen
    ]
    if not items:
        return None
    return _section("medical_notes", APPENDIX_HEADINGS["medical_notes"], items)


# --- assembly ---------------------------------------------------------------


def _summary_sections(
    data: PreparationData,
    selection: ReportSelection,
    *,
    detailed_symptoms: bool,
    detailed_background: bool,
) -> list[dict[str, Any]]:
    """The one-page summary, in PRD 7 section 26's recommended order."""
    candidates = [
        _focus_section(selection),
        _symptom_section(data, selection, detailed=detailed_symptoms),
        _medication_section(data, selection),
        _adherence_section(data, selection),
        _checkin_section(data, selection),
        _background_section(data, selection, detailed=detailed_background),
        _question_section(data, selection),
    ]
    return [section for section in candidates if section is not None]


def _appendix_sections(
    data: PreparationData, selection: ReportSelection
) -> list[dict[str, Any]]:
    candidates = [
        _timeline_section(data, selection),
        _adherence_detail_section(data, selection),
        _skipped_section(data, selection),
        _wellbeing_notes_section(data, selection),
        _medical_notes_section(data, selection),
    ]
    return [section for section in candidates if section is not None]


def _footer_lines(data: PreparationData, generated_at: datetime) -> list[str]:
    zone = appointment_service.local_zone(data.appointment)
    return [
        DISCLAIMER,
        f"Prepared from records entered by {data.profile.preferred_name} in Nura.",
        f"Generated {format_moment(generated_at, zone)}.",
    ]


def build(
    data: PreparationData, selection: ReportSelection, *, generated_at: datetime
) -> dict[str, Any]:
    """The finished report, as a plain dict ready to be stored and rendered.

    Aims for one page, and PRD 7 section 26's three instructions are applied in
    the order it gives them: summarise more tightly first, then let the detail be
    what the appendix is for, and never shrink the text. So when the selected
    content is too long, the symptom detail lines drop out of the summary (they
    are in the appendix), then the background groups collapse onto single lines
    -- and if it is *still* too long, the summary runs onto a second page at full
    size, which is the honest outcome for somebody who chose a lot of content.

    Every branch is a function of ``data`` and ``selection`` alone, so the same
    inputs always produce the same report (section 72's determinism criterion).
    """
    sections = _summary_sections(
        data, selection, detailed_symptoms=True, detailed_background=True
    )
    condensed = False

    if _estimate_lines(sections) > ONE_PAGE_LINE_BUDGET:
        sections = _summary_sections(
            data, selection, detailed_symptoms=False, detailed_background=True
        )
        condensed = True
    if _estimate_lines(sections) > ONE_PAGE_LINE_BUDGET:
        sections = _summary_sections(
            data, selection, detailed_symptoms=False, detailed_background=False
        )
        condensed = True

    appendix = _appendix_sections(data, selection) if selection.include_appendix else []

    if condensed and selection.include_appendix and appendix:
        sections.append(
            _section(
                "condensed_note",
                "",
                [_item(None, ["Fuller detail follows in the appendix."])],
            )
        )

    period = data.period
    return {
        "schema_version": SCHEMA_VERSION,
        "title": REPORT_TITLE,
        "generated_at": generated_at.isoformat(),
        "header": _header(data),
        "period": {
            "start": period.start.isoformat(),
            "end": period.end.isoformat(),
            "label": period.label,
            "preset": period.preset,
            "requested_preset": period.requested_preset,
            "fallback_reason": period.fallback_reason,
            "note": period_service.describe_fallback(period),
        },
        "summary_sections": sections,
        "appendix_sections": appendix,
        "include_appendix": selection.include_appendix,
        "summary_condensed": condensed,
        "footer_lines": _footer_lines(data, generated_at),
        "counts": {
            "symptoms": len(selection.symptom_episode_ids),
            "medications": len(_selected_medications(data, selection)),
            "questions": len(data.questions) if selection.selected("questions") else 0,
            "appendix_sections": len(appendix),
        },
    }


def all_text(snapshot: dict[str, Any]) -> list[str]:
    """Every string a report can show, for auditing.

    Used by the tests that assert no report can contain a diagnosis, a
    likelihood or a treatment suggestion (PRD 7, section 45). Having one
    function that returns the whole text means such a test cannot miss a section
    somebody adds later.
    """
    lines: list[str] = [str(snapshot.get("title", ""))]
    header = snapshot.get("header", {})
    lines.append(str(header.get("patient", "")))
    lines.extend(str(line) for line in header.get("lines", []))
    period_note = snapshot.get("period", {}).get("note")
    if period_note:
        lines.append(str(period_note))

    for group in ("summary_sections", "appendix_sections"):
        for section in snapshot.get(group, []):
            lines.append(str(section.get("heading", "")))
            for item in section.get("items", []):
                if item.get("title"):
                    lines.append(str(item["title"]))
                lines.extend(str(line) for line in item.get("lines", []))

    lines.extend(str(line) for line in snapshot.get("footer_lines", []))
    return [line for line in lines if line]


def file_name(generated_on: date) -> str:
    """ "Nura_Health_Summary_2026-10-02.pdf" (PRD 7, section 33).

    Deliberately says nothing medical. A filename shows up in a share sheet, a
    downloads list, a file manager and a notification, none of which the user
    chose to put it in -- so it carries a date and nothing else.
    """
    return f"Nura_Health_Summary_{generated_on.isoformat()}.pdf"
