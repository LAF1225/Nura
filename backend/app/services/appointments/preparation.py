"""Reading the records back for review (PRD 7, sections 13, 15-21 and 49).

What Prepare for Appointment shows the user before they choose anything. Every
figure here is counted from rows they entered; nothing is interpreted, ranked,
weighted or explained.

Four boundaries, each of which would be easy to cross by accident:

**No symptom is more important than another.** The list is ordered by when it
was last written about, because that is a fact about the data. It is not ordered
by severity, not filtered to the "significant" ones, and carries no flag saying
which to include -- PRD 7 section 15 puts that decision with the user, and an
ordering by severity would quietly make it for them.

**Adherence is counts first.** ``13 of 14 doses marked taken`` is what the
report prefers; the percentage is available and is never labelled good or bad
(sections 18 and 19).

**A skipped dose's own words are not included unless asked for.** The counts
come out automatically; ``skip_reason_notes`` is what somebody wrote, and that
is theirs to offer (section 19).

**Uncertainty survives.** A symptom's ``uncertain_items`` and ``negated_items``
are carried through rather than dropped, so a review cannot read as more
definite than the person was (sections 16 and 47).
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    Allergy,
    Appointment,
    AppointmentQuestion,
    DailyCheckIn,
    MedicalCondition,
    MedicalNote,
    Medication,
    MedicationDose,
    MedicationSchedule,
    Procedure,
    Profile,
    SymptomEntry,
    SymptomEpisode,
)
from app.models.enums import SYMPTOM_ACTIVE_STATUSES
from app.services.appointments import questions as question_service
from app.services.appointments.periods import ReportPeriod
from app.services.appointments.wording import format_day, join_items
from app.services.medications import adherence as adherence_service

logger = logging.getLogger(__name__)

#: How many recent procedures the baseline section offers (PRD 7, section 21).
#: "Recent" has to mean something countable; three is enough to be useful and
#: few enough to stay compact.
RECENT_PROCEDURES = 3

#: How many wellbeing notes the review offers for selection. A month of notes is
#: a diary, and a doctor summary is not the place for one.
MAX_CHECKIN_NOTES = 30

#: Statuses counted as a current condition (PRD 7, section 21). ``uncertain`` is
#: included and *labelled* uncertain rather than dropped: "they think it might
#: be X" is worth a doctor knowing, and stating it as active would overstate it
#: (PRD 4, section 9; PRD 7, section 47).
CURRENT_CONDITION_STATUSES = ("active", "uncertain")


# --- what a review is made of -----------------------------------------------


@dataclass(frozen=True)
class SymptomNote:
    """One thing the person wrote about a symptom, offered for inclusion."""

    entry_id: uuid.UUID
    recorded_at: datetime
    text: str


@dataclass(frozen=True)
class SymptomReview:
    """One symptom episode over the period, counted (PRD 7, sections 15, 16)."""

    episode_id: uuid.UUID
    name: str
    body_site: str | None
    status: str
    #: Entries inside the period. Zero for an ongoing symptom nobody has
    #: written about lately, which is stated rather than hidden.
    entry_count: int
    #: When the episode began, in whatever precision was recorded.
    first_noticed_label: str | None
    first_entry_at: datetime | None
    latest_entry_at: datetime | None
    latest_severity: int | None
    severity_min: int | None
    severity_max: int | None
    latest_change_state: str | None
    associated_symptoms: list[str] = field(default_factory=list)
    exacerbating_factors: list[str] = field(default_factory=list)
    relieving_factors: list[str] = field(default_factory=list)
    negated_items: list[str] = field(default_factory=list)
    uncertain_items: list[str] = field(default_factory=list)
    context_dependent_items: list[str] = field(default_factory=list)
    notes: list[SymptomNote] = field(default_factory=list)
    #: Counted, never included. PRD 7 section 28 leaves photos out of the
    #: report; the count is here so the app can say they exist.
    photo_count: int = 0
    #: True while the episode is active or recurring.
    is_ongoing: bool = False


@dataclass(frozen=True)
class MedicationReview:
    """One medication, and how often it is taken (PRD 7, section 17)."""

    medication_id: uuid.UUID
    name: str
    dose: str | None
    dose_unit: str | None
    #: "Twice daily", from the PRD 5 schedule when there is one, otherwise the
    #: free text on the record. None when neither was ever filled in.
    frequency: str | None
    reason: str | None
    is_active: bool

    @property
    def display_name(self) -> str:
        """ "Metformin 500 mg" -- the line a doctor reads (PRD 7, section 17)."""
        if not self.dose:
            return self.name
        unit = f" {self.dose_unit}" if self.dose_unit else ""
        return f"{self.name} {self.dose}{unit}"


@dataclass(frozen=True)
class SkipNote:
    """A dose the person skipped, and what they said about it."""

    dose_id: uuid.UUID
    local_date: date
    medication_name: str
    reason_code: str | None
    reason_text: str | None


@dataclass(frozen=True)
class AdherenceReview:
    """Counts over the period (PRD 7, sections 18 and 19)."""

    from_date: date
    to_date: date
    taken: int
    skipped: int
    missed: int
    total: int
    #: Available, never graded. See ``adherence.calculate``.
    percent: int | None
    #: Free-text skip reasons, offered for explicit inclusion only (s19).
    skip_notes: list[SkipNote] = field(default_factory=list)


@dataclass(frozen=True)
class CheckInNote:
    checkin_date: date
    wellbeing_level: str
    note: str


@dataclass(frozen=True)
class CheckInReview:
    """Wellbeing counts over the period (PRD 7, section 20)."""

    good: int
    okay: int
    not_great: int
    total: int
    days_in_period: int
    notes: list[CheckInNote] = field(default_factory=list)


@dataclass(frozen=True)
class ConditionItem:
    condition_id: uuid.UUID
    name: str
    status: str
    diagnosed_label: str | None


@dataclass(frozen=True)
class AllergyItem:
    allergy_id: uuid.UUID
    allergen: str
    reaction: str | None
    severity: str


@dataclass(frozen=True)
class ProcedureItem:
    procedure_id: uuid.UUID
    name: str
    performed_label: str | None


@dataclass(frozen=True)
class MedicalNoteItem:
    """One medical note, offered for the appendix (PRD 7, section 27)."""

    note_id: uuid.UUID
    title: str
    body: str
    category: str


@dataclass(frozen=True)
class BaselineReview:
    """The compact health background (PRD 7, section 21)."""

    conditions: list[ConditionItem] = field(default_factory=list)
    allergies: list[AllergyItem] = field(default_factory=list)
    procedures: list[ProcedureItem] = field(default_factory=list)
    blood_type: str | None = None


@dataclass(frozen=True)
class PreparationData:
    """Everything the preparation screens read (PRD 7, section 49)."""

    appointment: Appointment
    profile: Profile
    period: ReportPeriod
    symptoms: list[SymptomReview] = field(default_factory=list)
    medications: list[MedicationReview] = field(default_factory=list)
    adherence: AdherenceReview | None = None
    checkins: CheckInReview | None = None
    baseline: BaselineReview | None = None
    #: Offered for the appendix, chosen one by one (PRD 7, section 27).
    medical_notes: list[MedicalNoteItem] = field(default_factory=list)
    questions: list[AppointmentQuestion] = field(default_factory=list)

    @property
    def has_any_health_data(self) -> bool:
        """False for an appointment with nothing to review.

        A real state, not an error: somebody may add an appointment before they
        have recorded anything at all, and the screen says so rather than
        showing empty sections (PRD 7, sections 46 and 69).
        """
        return bool(
            self.symptoms
            or self.medications
            or (self.adherence is not None and self.adherence.total > 0)
            or (self.checkins is not None and self.checkins.total > 0)
            or (
                self.baseline is not None
                and (
                    self.baseline.conditions
                    or self.baseline.allergies
                    or self.baseline.procedures
                    or self.baseline.blood_type
                )
            )
        )


# --- symptoms ---------------------------------------------------------------


def _first_noticed_label(episode: SymptomEpisode) -> str | None:
    """The onset in whatever precision was recorded, or the user's own words.

    PRD 4 and PRD 6 both keep three precisions rather than forcing a date, and a
    report has to respect that: "about 2015" must not become "1 January 2015".
    """
    if episode.first_noticed_at is not None:
        return format_day(episode.first_noticed_at.date())
    if episode.first_noticed_date is not None:
        return format_day(episode.first_noticed_date)
    if episode.first_noticed_year is not None:
        return str(episode.first_noticed_year)
    return episode.first_noticed_text


def _merge(values: list[list[str]]) -> list[str]:
    """Every distinct item across a set of entries, first sighting first.

    Case-insensitive on the comparison and original on the output, so "Nausea"
    and "nausea" are one item and it reads the way the person wrote it.
    """
    seen: set[str] = set()
    merged: list[str] = []
    for group in values:
        for item in group:
            key = item.strip().casefold()
            if key and key not in seen:
                seen.add(key)
                merged.append(item.strip())
    return merged


def _symptom_notes(entries: list[SymptomEntry]) -> list[SymptomNote]:
    """The notes among these entries, in order. Empty notes are not notes."""
    notes: list[SymptomNote] = []
    for entry in entries:
        text = entry.free_text_note
        if text:
            notes.append(
                SymptomNote(entry_id=entry.id, recorded_at=entry.recorded_at, text=text)
            )
    return notes


def _symptom_review(
    episode: SymptomEpisode, entries: list[SymptomEntry]
) -> SymptomReview:
    """One episode, summarised from the entries inside the period.

    ``entries`` arrives oldest first. Severity range is taken only from entries
    that recorded a number: an episode where two of six entries gave a severity
    ranged over those two, and saying otherwise would invent data.
    """
    severities = [entry.severity for entry in entries if entry.severity is not None]
    latest = entries[-1] if entries else None
    # The latest recorded change state, which may not be on the newest entry:
    # a follow-up that only added a note leaves the previous answer standing.
    change_state = next(
        (entry.change_state for entry in reversed(entries) if entry.change_state),
        None,
    )

    return SymptomReview(
        episode_id=episode.id,
        name=episode.name,
        body_site=episode.body_site,
        status=episode.status,
        entry_count=len(entries),
        first_noticed_label=_first_noticed_label(episode),
        first_entry_at=entries[0].recorded_at if entries else None,
        latest_entry_at=latest.recorded_at if latest else None,
        latest_severity=latest.severity if latest else None,
        severity_min=min(severities) if severities else None,
        severity_max=max(severities) if severities else None,
        latest_change_state=change_state,
        associated_symptoms=_merge([entry.associated_symptoms for entry in entries]),
        exacerbating_factors=_merge([entry.exacerbating_factors for entry in entries]),
        relieving_factors=_merge([entry.relieving_factors for entry in entries]),
        negated_items=_merge([entry.negated_items for entry in entries]),
        uncertain_items=_merge([entry.uncertain_items for entry in entries]),
        context_dependent_items=_merge(
            [entry.context_dependent_items for entry in entries]
        ),
        notes=_symptom_notes(entries),
        photo_count=sum(len(entry.photos) for entry in entries),
        is_ongoing=episode.status in SYMPTOM_ACTIVE_STATUSES,
    )


def symptom_reviews(
    db: Session, profile_id: uuid.UUID, period: ReportPeriod
) -> list[SymptomReview]:
    """Symptoms worth reviewing before this appointment.

    An episode is here if it was written about during the period, or if it is
    still going on. The second half matters: an ongoing symptom nobody has
    updated for six weeks is exactly the thing a person forgets to mention, and
    leaving it out because the period is 30 days would help them forget it.
    Such an episode reports ``entry_count`` 0, and the report says as much
    rather than implying it was quiet.
    """
    episodes = (
        db.execute(
            select(SymptomEpisode)
            .where(SymptomEpisode.profile_id == profile_id)
            .options(
                selectinload(SymptomEpisode.entries).selectinload(SymptomEntry.photos)
            )
        )
        .scalars()
        .all()
    )

    reviews: list[SymptomReview] = []
    for episode in episodes:
        # `episode.entries` is newest-first from the relationship; the summary
        # reads better built oldest-first.
        in_period = sorted(
            (
                entry
                for entry in episode.entries
                if period.start <= entry.recorded_at.date() <= period.end
            ),
            key=lambda entry: entry.recorded_at,
        )
        ongoing = episode.status in SYMPTOM_ACTIVE_STATUSES
        if not in_period and not ongoing:
            continue
        reviews.append(_symptom_review(episode, in_period))

    # Most recently written about first, then anything ongoing with nothing in
    # the period, alphabetically so the order is stable between generations.
    reviews.sort(
        key=lambda review: (
            review.latest_entry_at is None,
            -(review.latest_entry_at.timestamp() if review.latest_entry_at else 0),
            review.name.casefold(),
        )
    )
    return reviews


# --- medications ------------------------------------------------------------


def _times_phrase(count: int) -> str:
    if count <= 1:
        return "Once"
    if count == 2:
        return "Twice"
    return f"{count} times"


WEEKDAY_NAMES = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)


def schedule_frequency(schedules: list[MedicationSchedule]) -> str | None:
    """ "Twice daily", or "Twice on Monday and Thursday", from PRD 5 schedules.

    Built from the schedule rather than from free text wherever there is one,
    because the schedule is what the reminders actually follow -- so the report
    and the phone agree. Paused and ended schedules are ignored by the caller.

    Returns None when there is no schedule, which is when the caller falls back
    to the medication record's own ``frequency_text``.
    """
    if not schedules:
        return None

    daily = [s for s in schedules if s.schedule_type == "daily"]
    if daily:
        return f"{_times_phrase(sum(len(s.times) for s in daily))} daily"

    weekdays = sorted(
        {
            time_row.weekday
            for schedule in schedules
            for time_row in schedule.times
            if time_row.weekday is not None
        }
    )
    per_day = max(
        (
            len([t for t in schedule.times if t.weekday == weekday])
            for schedule in schedules
            for weekday in weekdays
        ),
        default=1,
    )
    if not weekdays:
        return f"{_times_phrase(sum(len(s.times) for s in schedules))} weekly"
    names = join_items([WEEKDAY_NAMES[weekday] for weekday in weekdays])
    return f"{_times_phrase(per_day)} on {names}"


def medication_reviews(
    db: Session, profile_id: uuid.UUID, *, include_inactive: bool = False
) -> list[MedicationReview]:
    """The medications the user is taking (PRD 7, section 17).

    Active only by default. An inactive medication is history, and a report that
    listed it beside a current one would be misleading in the worst possible
    place (section 17).
    """
    query = select(Medication).where(Medication.profile_id == profile_id)
    if not include_inactive:
        query = query.where(Medication.is_active.is_(True))

    medications = db.execute(query.order_by(Medication.name)).scalars().all()

    schedules = (
        db.execute(
            select(MedicationSchedule)
            .where(
                MedicationSchedule.profile_id == profile_id,
                MedicationSchedule.is_active.is_(True),
            )
            .options(selectinload(MedicationSchedule.times))
        )
        .scalars()
        .all()
    )
    by_medication: dict[uuid.UUID, list[MedicationSchedule]] = {}
    for schedule in schedules:
        by_medication.setdefault(schedule.medication_id, []).append(schedule)

    return [
        MedicationReview(
            medication_id=medication.id,
            name=medication.name,
            dose=medication.dose,
            dose_unit=medication.dose_unit,
            frequency=(
                schedule_frequency(by_medication.get(medication.id, []))
                or medication.frequency_text
            ),
            reason=medication.reason,
            is_active=medication.is_active,
        )
        for medication in medications
    ]


# --- adherence --------------------------------------------------------------


def adherence_review(
    db: Session, profile_id: uuid.UUID, period: ReportPeriod
) -> AdherenceReview:
    """Dose counts over the period, plus the skip notes, ready to be offered.

    The counts come from PRD 5's one adherence definition, so the report and the
    medication history screen can never show different figures
    (PRD 7, section 18).
    """
    figures = adherence_service.calculate(
        db, profile_id, from_date=period.start, to_date=period.end
    )

    skipped = (
        db.execute(
            select(MedicationDose)
            .where(
                MedicationDose.profile_id == profile_id,
                MedicationDose.local_date >= period.start,
                MedicationDose.local_date <= period.end,
                MedicationDose.status == "skipped",
            )
            .order_by(MedicationDose.local_date)
            .options(selectinload(MedicationDose.medication))
        )
        .scalars()
        .all()
    )

    return AdherenceReview(
        from_date=figures.from_date,
        to_date=figures.to_date,
        taken=figures.taken,
        skipped=figures.skipped,
        missed=figures.missed,
        total=figures.total,
        percent=figures.percent,
        skip_notes=[
            SkipNote(
                dose_id=dose.id,
                local_date=dose.local_date,
                medication_name=dose.medication.name,
                reason_code=dose.skip_reason_code,
                reason_text=dose.skip_reason_text,
            )
            for dose in skipped
        ],
    )


# --- check-ins --------------------------------------------------------------


def _checkin_notes(rows: list[DailyCheckIn]) -> list[CheckInNote]:
    notes: list[CheckInNote] = []
    for row in rows:
        note = row.note
        if note:
            notes.append(
                CheckInNote(
                    checkin_date=row.checkin_date,
                    wellbeing_level=row.wellbeing_level,
                    note=note,
                )
            )
        if len(notes) == MAX_CHECKIN_NOTES:
            break
    return notes


def checkin_review(
    db: Session, profile_id: uuid.UUID, period: ReportPeriod
) -> CheckInReview:
    """Wellbeing counts over the period (PRD 7, section 20).

    Three counts and the notes. Not a mood trend, not a graph, and not an
    interpretation -- the same restraint PRD 3 section 12 put on the check-in
    itself.
    """
    rows = list(
        db.execute(
            select(DailyCheckIn)
            .where(
                DailyCheckIn.profile_id == profile_id,
                DailyCheckIn.checkin_date >= period.start,
                DailyCheckIn.checkin_date <= period.end,
            )
            .order_by(DailyCheckIn.checkin_date)
        )
        .scalars()
        .all()
    )

    counts = {"good": 0, "okay": 0, "not_great": 0}
    for row in rows:
        if row.wellbeing_level in counts:
            counts[row.wellbeing_level] += 1

    return CheckInReview(
        good=counts["good"],
        okay=counts["okay"],
        not_great=counts["not_great"],
        total=len(rows),
        days_in_period=period.days,
        notes=_checkin_notes(rows),
    )


# --- baseline ---------------------------------------------------------------


def _diagnosed_label(condition: MedicalCondition) -> str | None:
    if condition.diagnosed_date is not None:
        return format_day(condition.diagnosed_date)
    if condition.diagnosed_year is not None:
        return str(condition.diagnosed_year)
    return None


def _performed_label(procedure: Procedure) -> str | None:
    if procedure.performed_date is not None:
        return format_day(procedure.performed_date)
    if procedure.performed_year is not None:
        return str(procedure.performed_year)
    return None


def baseline_review(db: Session, profile: Profile) -> BaselineReview:
    """Conditions, allergies, recent procedures and blood type (s21).

    "Recent procedures" is the most recent few by the date recorded, which is
    the only definition that does not need Nura to decide which operation
    mattered. Ones with no date at all come last, in the order they were added.
    """
    conditions = (
        db.execute(
            select(MedicalCondition)
            .where(
                MedicalCondition.profile_id == profile.id,
                MedicalCondition.status.in_(CURRENT_CONDITION_STATUSES),
            )
            .order_by(MedicalCondition.name)
        )
        .scalars()
        .all()
    )
    allergies = (
        db.execute(
            select(Allergy)
            .where(Allergy.profile_id == profile.id)
            .order_by(Allergy.allergen)
        )
        .scalars()
        .all()
    )
    procedures = (
        db.execute(
            select(Procedure)
            .where(Procedure.profile_id == profile.id)
            .order_by(
                Procedure.performed_date.desc().nulls_last(),
                Procedure.performed_year.desc().nulls_last(),
                Procedure.created_at.desc(),
            )
            .limit(RECENT_PROCEDURES)
        )
        .scalars()
        .all()
    )

    return BaselineReview(
        conditions=[
            ConditionItem(
                condition_id=condition.id,
                name=condition.name,
                status=condition.status,
                diagnosed_label=_diagnosed_label(condition),
            )
            for condition in conditions
        ],
        allergies=[
            AllergyItem(
                allergy_id=allergy.id,
                allergen=allergy.allergen,
                reaction=allergy.reaction,
                severity=allergy.severity,
            )
            for allergy in allergies
        ],
        procedures=[
            ProcedureItem(
                procedure_id=procedure.id,
                name=procedure.name,
                performed_label=_performed_label(procedure),
            )
            for procedure in procedures
        ],
        blood_type=profile.blood_type,
    )


def medical_note_items(db: Session, profile_id: uuid.UUID) -> list[MedicalNoteItem]:
    """The profile's medical notes, for the user to pick from (s27).

    Offered, never chosen: a note may be about anything from a hospital parking
    code to a care instruction, and Nura has no way to tell which belongs in a
    doctor summary.
    """
    rows = (
        db.execute(
            select(MedicalNote)
            .where(MedicalNote.profile_id == profile_id)
            .order_by(MedicalNote.created_at.desc())
        )
        .scalars()
        .all()
    )
    return [
        MedicalNoteItem(
            note_id=row.id, title=row.title, body=row.body, category=row.category
        )
        for row in rows
    ]


# --- the whole review -------------------------------------------------------


def build(
    db: Session,
    profile: Profile,
    appointment: Appointment,
    period: ReportPeriod,
) -> PreparationData:
    """Assembles everything the preparation flow reads.

    One call, for the same reason Today is one call: the flow shows symptoms,
    medications, adherence, check-ins and questions on consecutive steps, and
    five requests would mean five chances to be half-loaded
    (PRD 3, section 16).

    Reads only. Preparing for an appointment changes nothing about the records
    being prepared.
    """
    logger.info("appointments: assembled a preparation review")
    return PreparationData(
        appointment=appointment,
        profile=profile,
        period=period,
        symptoms=symptom_reviews(db, profile.id, period),
        medications=medication_reviews(db, profile.id),
        adherence=adherence_review(db, profile.id, period),
        checkins=checkin_review(db, profile.id, period),
        baseline=baseline_review(db, profile),
        medical_notes=medical_note_items(db, profile.id),
        questions=question_service.list_questions(db, appointment.id),
    )
