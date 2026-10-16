"""Appointments, questions, preparation and reports (PRD 7, sections 48-52).

Every route is nested under the profile the records belong to and resolves it
through ``OwnedProfile``, so the authorization chain is the one the health
record, medication and symptom routes already use: *an appointment, a question or
a report is reachable only through a profile the signed-in account owns*, and
anything else is a 404 rather than a 403 (PRD 7, section 51).

Nothing is authorized by object id alone, and the chain is complete at every
depth. A question is fetched by profile *and* appointment *and* id; a report the
same way; and the PDF route re-walks all of it before it serves a byte. There is
no route that takes an id and works out who it belongs to afterwards.

The routes are written out rather than generated. They are repetitive, and that
is the point: this is the surface that decides whether somebody's appointments
and doctor summaries can be read, and being able to read each one in full is
worth more here than brevity.
"""

import logging
import uuid
from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.api.deps import DbSession, Now, OwnedProfile, http_error
from app.models import Appointment, AppointmentQuestion, AppointmentReport, Profile
from app.schemas.appointment import (
    AdherenceReviewRead,
    AllergyItemRead,
    AppointmentComplete,
    AppointmentCreate,
    AppointmentDetailRead,
    AppointmentQuestionCreate,
    AppointmentQuestionRead,
    AppointmentQuestionReorder,
    AppointmentQuestionSaved,
    AppointmentQuestionUpdate,
    AppointmentRead,
    AppointmentSaved,
    AppointmentSummaryRead,
    AppointmentUpdate,
    BaselineReviewRead,
    CheckInNoteRead,
    CheckInReviewRead,
    ClinicianBriefRead,
    ConditionItemRead,
    MedicalNoteItemRead,
    MedicationReviewRead,
    PreparationRead,
    ProcedureItemRead,
    QuestionSuggestionRead,
    ReportDetailRead,
    ReportGenerate,
    ReportPeriodRead,
    ReportRead,
    ReportSaved,
    ReportSelectionInput,
    ReportSelectionRead,
    SkipNoteRead,
    SymptomNoteRead,
    SymptomReviewRead,
    TodayAppointmentRead,
)
from app.services.appointments import appointments as appointment_service
from app.services.appointments import periods as period_service
from app.services.appointments import preparation as preparation_service
from app.services.appointments import questions as question_service
from app.services.appointments import reports as report_service
from app.services.appointments import snapshot as snapshot_service
from app.services.appointments import suggestions as suggestion_service
from app.services.appointments import summary as summary_service
from app.services.appointments.pdf import get_pdf_service
from app.services.appointments.wording import (
    format_clock,
    format_day,
    format_moment,
    relative_day,
    when_label,
)
from app.services.errors import DomainError
from app.services.storage import get_object_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/profiles/{profile_id}/appointments", tags=["appointments"])

NO_CONTENT = status.HTTP_204_NO_CONTENT
CREATED = status.HTTP_201_CREATED


# --- shared plumbing --------------------------------------------------------


def _appointment_read(appointment: Appointment, now: datetime) -> AppointmentRead:
    """One appointment with its display labels rendered (PRD 7, section 42).

    The reference "today" is today *in the appointment's own zone*, so an
    appointment in London reads "Tomorrow" on London's calendar. For the great
    majority of appointments that is the user's calendar too; while travelling it
    is the more useful of the two answers.
    """
    zone = appointment_service.local_zone(appointment)
    local_today = now.astimezone(zone).date()
    appointment_day = appointment.scheduled_at.astimezone(zone).date()

    return AppointmentRead(
        id=appointment.id,
        profile_id=appointment.profile_id,
        title=appointment.title,
        appointment_type=appointment.appointment_type,  # type: ignore[arg-type]
        status=appointment.status,  # type: ignore[arg-type]
        preparation_status=appointment.preparation_status,  # type: ignore[arg-type]
        scheduled_at=appointment.scheduled_at,
        timezone=appointment.timezone,
        local_date=appointment_day,
        day_label=format_day(appointment_day),
        time_label=format_clock(appointment.scheduled_at, zone),
        when_label=when_label(appointment.scheduled_at, zone, local_today),
        relative_day=relative_day(appointment_day, local_today),
        clinician=(
            None
            if appointment.clinician is None
            else ClinicianBriefRead.model_validate(appointment.clinician)
        ),
        location_name=appointment.location_name,
        address=appointment.address,
        phone=appointment.phone,
        notes=appointment.notes,
        visit_notes=appointment.visit_notes,
        follow_up_date=appointment.follow_up_date,
        reminders_enabled=appointment.reminders_enabled,
        cancelled_at=appointment.cancelled_at,
        completed_at=appointment.completed_at,
        question_count=len(appointment.questions),
        report_count=len(appointment.reports),
        created_at=appointment.created_at,
        updated_at=appointment.updated_at,
    )


def _report_read(report: AppointmentReport) -> ReportRead:
    """One version's metadata. No storage key and no URL (PRD 7, section 52)."""
    return ReportRead(
        id=report.id,
        appointment_id=report.appointment_id,
        version=report.version,
        status=report.status,  # type: ignore[arg-type]
        period_start=report.period_start,
        period_end=report.period_end,
        period_preset=report.period_preset,  # type: ignore[arg-type]
        period_label=str(report.snapshot.get("period", {}).get("label", "")),
        include_appendix=report.include_appendix,
        generated_at=report.generated_at,
        generated_label=format_moment(
            report.generated_at, appointment_service.local_zone(report.appointment)
        ),
        byte_size=report.byte_size,
        page_count=report.page_count,
        file_name=report_service.file_name(report),
        selection=ReportSelectionRead.model_validate(report.selection),
    )


def _report_detail(report: AppointmentReport) -> ReportDetailRead:
    return ReportDetailRead(**_report_read(report).model_dump(), snapshot=report.snapshot)


def _appointment_detail(appointment: Appointment, now: datetime) -> AppointmentDetailRead:
    base = _appointment_read(appointment, now)
    return AppointmentDetailRead(
        **base.model_dump(),
        questions=[
            AppointmentQuestionRead.model_validate(question)
            for question in appointment.questions
        ],
        reports=[_report_read(report) for report in appointment.reports],
    )


def _fetch_appointment(
    db: DbSession, profile: Profile, appointment_id: uuid.UUID
) -> Appointment:
    try:
        return appointment_service.get_appointment(db, profile.id, appointment_id)
    except DomainError as error:
        raise http_error(error) from error


def _fetch_question(
    db: DbSession,
    profile: Profile,
    appointment_id: uuid.UUID,
    question_id: uuid.UUID,
) -> AppointmentQuestion:
    try:
        return question_service.get_question(db, profile.id, appointment_id, question_id)
    except DomainError as error:
        raise http_error(error) from error


def _fetch_report(
    db: DbSession,
    profile: Profile,
    appointment_id: uuid.UUID,
    report_id: uuid.UUID,
) -> AppointmentReport:
    try:
        return report_service.get_report(db, profile.id, appointment_id, report_id)
    except DomainError as error:
        raise http_error(error) from error


def _selection(sent: ReportSelectionInput) -> snapshot_service.ReportSelection:
    """A request's selection, with unsent sections left at their defaults.

    Merging rather than replacing means a client that only wants to turn one
    section off sends one field, and a section added by a later build appears
    without every old client having to know about it.
    """
    include = snapshot_service.default_include()
    include.update(sent.include)
    return snapshot_service.ReportSelection(
        include=include,
        symptom_episode_ids=list(sent.symptom_episode_ids),
        symptom_note_entry_ids=list(sent.symptom_note_entry_ids),
        medication_ids=(
            None if sent.medication_ids is None else list(sent.medication_ids)
        ),
        checkin_note_dates=list(sent.checkin_note_dates),
        medical_note_ids=list(sent.medical_note_ids),
        focus=sent.focus,
        include_appendix=sent.include_appendix,
        include_skip_reason_notes=sent.include_skip_reason_notes,
    )


def _resolve_period(
    db: DbSession,
    appointment: Appointment,
    now: datetime,
    preset: str,
    start: date | None,
    end: date | None,
) -> period_service.ReportPeriod:
    zone = appointment_service.local_zone(appointment)
    try:
        return period_service.resolve(
            db,
            appointment,
            preset=preset,
            today=now.astimezone(zone).date(),
            start=start,
            end=end,
        )
    except DomainError as error:
        raise http_error(error) from error


def _period_read(period: period_service.ReportPeriod) -> ReportPeriodRead:
    return ReportPeriodRead(
        start=period.start,
        end=period.end,
        label=period.label,
        preset=period.preset,  # type: ignore[arg-type]
        requested_preset=period.requested_preset,  # type: ignore[arg-type]
        note=period_service.describe_fallback(period),
        since_label=period_service.describe_since_last_visit(period),
        days=period.days,
    )


def _today_appointment(
    snapshot: summary_service.AppointmentSnapshot, now: datetime
) -> TodayAppointmentRead:
    appointment = snapshot.appointment
    zone = appointment_service.local_zone(appointment)
    clinician = appointment.clinician
    return TodayAppointmentRead(
        appointment_id=appointment.id,
        title=appointment.title,
        appointment_type=appointment.appointment_type,  # type: ignore[arg-type]
        scheduled_at=appointment.scheduled_at,
        timezone=appointment.timezone,
        when_label=when_label(
            appointment.scheduled_at, zone, now.astimezone(zone).date()
        ),
        relative_day=relative_day(snapshot.local_date, now.astimezone(zone).date()),
        clinician_name=None if clinician is None else clinician.name,
        clinician_specialty=None if clinician is None else clinician.specialty,
        location_name=appointment.location_name,
        preparation_status=appointment.preparation_status,  # type: ignore[arg-type]
        question_count=snapshot.question_count,
        report_count=snapshot.report_count,
    )


# --- summary ----------------------------------------------------------------
#
# Declared before `/{appointment_id}` so "summary" is matched as a literal
# rather than failing to parse as a UUID. FastAPI matches in declaration order.


@router.get("/summary", response_model=AppointmentSummaryRead)
def read_appointment_summary(
    profile: OwnedProfile, db: DbSession, now: Now
) -> AppointmentSummaryRead:
    """Counts for the Care tab (PRD 7, section 5)."""
    zone_today = now.date()
    summary = summary_service.build_summary(db, profile.id, zone_today, now)
    past = appointment_service.list_appointments(db, profile.id, scope="past", now=now)
    cancelled = appointment_service.list_appointments(
        db, profile.id, scope="cancelled", now=now
    )

    return AppointmentSummaryRead(
        profile_id=profile.id,
        upcoming_count=summary.upcoming_count,
        past_count=len(past),
        cancelled_count=len(cancelled),
        has_appointments=summary.has_appointments,
        next=(
            None
            if summary.next_appointment is None
            else _today_appointment(summary.next_appointment, now)
        ),
    )


# --- appointments -----------------------------------------------------------

ScopeFilter = Annotated[
    str | None,
    Query(
        pattern="^(upcoming|past|cancelled)$",
        description="Which list to return. Omitted returns everything.",
    ),
]


@router.get("", response_model=list[AppointmentRead])
def list_appointments(
    profile: OwnedProfile,
    db: DbSession,
    now: Now,
    scope: ScopeFilter = None,
) -> list[AppointmentRead]:
    """This profile's appointments (PRD 7, section 41).

    ``upcoming`` is soonest first; ``past`` and ``cancelled`` read backwards.
    """
    rows = appointment_service.list_appointments(db, profile.id, scope=scope, now=now)
    return [_appointment_read(appointment, now) for appointment in rows]


@router.post("", response_model=AppointmentSaved, status_code=CREATED)
def create_appointment(
    payload: AppointmentCreate,
    profile: OwnedProfile,
    db: DbSession,
    now: Now,
    response: Response,
) -> AppointmentSaved:
    """Adds an appointment by hand (PRD 7, sections 4 and 8).

    **Idempotent through ``client_appointment_id``.** A retry after a failed
    request returns the stored appointment with ``created: false`` and a 200, so
    an offline draft cannot become two appointments (PRD 7, section 53).
    """
    if payload.client_appointment_id is not None:
        existing = appointment_service.find_by_client_id(
            db, profile.id, payload.client_appointment_id
        )
        if existing is not None:
            response.status_code = status.HTTP_200_OK
            return AppointmentSaved(
                appointment=_appointment_detail(existing, now), created=False
            )

    try:
        appointment = appointment_service.create_appointment(
            db,
            profile.id,
            appointment_service.AppointmentInput(
                title=payload.title,
                scheduled_at=payload.scheduled_at,
                timezone=payload.timezone,
                appointment_type=payload.appointment_type,
                clinician_id=payload.clinician_id,
                location_name=payload.location_name,
                address=payload.address,
                phone=payload.phone,
                notes=payload.notes,
                reminders_enabled=payload.reminders_enabled,
                client_appointment_id=payload.client_appointment_id,
            ),
        )
    except DomainError as error:
        raise http_error(error) from error

    return AppointmentSaved(
        appointment=_appointment_detail(appointment, now), created=True
    )


@router.get("/{appointment_id}", response_model=AppointmentDetailRead)
def read_appointment(
    appointment_id: uuid.UUID, profile: OwnedProfile, db: DbSession, now: Now
) -> AppointmentDetailRead:
    """One appointment, its questions and its report versions (s11)."""
    return _appointment_detail(_fetch_appointment(db, profile, appointment_id), now)


@router.patch("/{appointment_id}", response_model=AppointmentDetailRead)
def update_appointment(
    appointment_id: uuid.UUID,
    payload: AppointmentUpdate,
    profile: OwnedProfile,
    db: DbSession,
    now: Now,
) -> AppointmentDetailRead:
    """Edits an appointment.

    Changing the time is what the app watches for: it reschedules the local
    reminders from the stored appointment afterwards, so the two cannot drift
    apart (PRD 7, section 54).
    """
    appointment = _fetch_appointment(db, profile, appointment_id)
    try:
        updated = appointment_service.update_appointment(
            db, appointment, payload.model_dump(exclude_unset=True)
        )
    except DomainError as error:
        raise http_error(error) from error
    return _appointment_detail(updated, now)


@router.delete("/{appointment_id}", status_code=NO_CONTENT)
def delete_appointment(
    appointment_id: uuid.UUID, profile: OwnedProfile, db: DbSession
) -> None:
    """Removes an appointment, its questions and its reports.

    For one entered by mistake. Cancelling is what somebody wants for an
    appointment that is not happening, and the app says which is which before
    asking. The stored PDFs go first: a database cascade cannot reach into
    storage (PRD 7, section 35).
    """
    appointment = _fetch_appointment(db, profile, appointment_id)
    report_service.purge_objects(
        get_object_store(), report_service.list_reports(db, appointment.id)
    )
    appointment_service.delete_appointment(db, appointment)


@router.post("/{appointment_id}/cancel", response_model=AppointmentDetailRead)
def cancel_appointment(
    appointment_id: uuid.UUID, profile: OwnedProfile, db: DbSession, now: Now
) -> AppointmentDetailRead:
    """Marks an appointment cancelled, keeping it and everything on it.

    Idempotent, and it keeps the original ``cancelled_at`` rather than pushing
    the timestamp forward on a retry.
    """
    appointment = appointment_service.cancel_appointment(
        db, _fetch_appointment(db, profile, appointment_id), now
    )
    return _appointment_detail(appointment, now)


@router.post("/{appointment_id}/complete", response_model=AppointmentDetailRead)
def complete_appointment(
    appointment_id: uuid.UUID,
    payload: AppointmentComplete,
    profile: OwnedProfile,
    db: DbSession,
    now: Now,
) -> AppointmentDetailRead:
    """Marks an appointment attended, with the optional notes from s38.

    Only the user does this. Nothing concludes from a passing timestamp that
    somebody attended, or did not (PRD 7, section 7).
    """
    appointment = appointment_service.complete_appointment(
        db,
        _fetch_appointment(db, profile, appointment_id),
        now,
        visit_notes=payload.visit_notes,
        follow_up_date=payload.follow_up_date,
    )
    return _appointment_detail(appointment, now)


@router.post("/{appointment_id}/reopen", response_model=AppointmentDetailRead)
def reopen_appointment(
    appointment_id: uuid.UUID, profile: OwnedProfile, db: DbSession, now: Now
) -> AppointmentDetailRead:
    """Puts a cancelled or completed appointment back to scheduled."""
    appointment = appointment_service.reopen_appointment(
        db, _fetch_appointment(db, profile, appointment_id)
    )
    return _appointment_detail(appointment, now)


# --- questions --------------------------------------------------------------


@router.get("/{appointment_id}/questions", response_model=list[AppointmentQuestionRead])
def list_questions(
    appointment_id: uuid.UUID, profile: OwnedProfile, db: DbSession
) -> list[AppointmentQuestionRead]:
    """This appointment's questions, in the user's order (PRD 7, section 23)."""
    appointment = _fetch_appointment(db, profile, appointment_id)
    return [
        AppointmentQuestionRead.model_validate(question)
        for question in question_service.list_questions(db, appointment.id)
    ]


@router.post(
    "/{appointment_id}/questions",
    response_model=AppointmentQuestionSaved,
    status_code=CREATED,
)
def create_question(
    appointment_id: uuid.UUID,
    payload: AppointmentQuestionCreate,
    profile: OwnedProfile,
    db: DbSession,
    response: Response,
) -> AppointmentQuestionSaved:
    """Adds a question, stored exactly as written (PRD 7, section 23).

    **Idempotent through ``client_question_id``**, so a question added offline
    lands once however many times the queue retries (section 53).
    """
    appointment = _fetch_appointment(db, profile, appointment_id)
    try:
        question, created = question_service.create_question(
            db,
            appointment,
            text=payload.text,
            client_question_id=payload.client_question_id,
        )
    except DomainError as error:
        raise http_error(error) from error

    if not created:
        response.status_code = status.HTTP_200_OK
    appointment_service.refresh_preparation_status(db, appointment)
    return AppointmentQuestionSaved(
        question=AppointmentQuestionRead.model_validate(question), created=created
    )


@router.put(
    "/{appointment_id}/questions/order", response_model=list[AppointmentQuestionRead]
)
def reorder_questions(
    appointment_id: uuid.UUID,
    payload: AppointmentQuestionReorder,
    profile: OwnedProfile,
    db: DbSession,
) -> list[AppointmentQuestionRead]:
    """Puts the questions in the order the client is displaying them."""
    appointment = _fetch_appointment(db, profile, appointment_id)
    rows = question_service.reorder_questions(db, appointment, payload.question_ids)
    return [AppointmentQuestionRead.model_validate(question) for question in rows]


@router.patch(
    "/{appointment_id}/questions/{question_id}",
    response_model=AppointmentQuestionRead,
)
def update_question(
    appointment_id: uuid.UUID,
    question_id: uuid.UUID,
    payload: AppointmentQuestionUpdate,
    profile: OwnedProfile,
    db: DbSession,
) -> AppointmentQuestionRead:
    """Edits a question, or records the answer the user was given (s39).

    An answer note is the user's record of what they were told. It is stored as
    theirs and is never treated as verified clinical data.
    """
    _fetch_appointment(db, profile, appointment_id)
    question = _fetch_question(db, profile, appointment_id, question_id)
    updated = question_service.update_question(
        db, question, payload.model_dump(exclude_unset=True)
    )
    return AppointmentQuestionRead.model_validate(updated)


@router.delete("/{appointment_id}/questions/{question_id}", status_code=NO_CONTENT)
def delete_question(
    appointment_id: uuid.UUID,
    question_id: uuid.UUID,
    profile: OwnedProfile,
    db: DbSession,
) -> None:
    """Removes a question and closes the gap in the order it left."""
    appointment = _fetch_appointment(db, profile, appointment_id)
    question = _fetch_question(db, profile, appointment_id, question_id)
    question_service.delete_question(db, question)
    appointment_service.refresh_preparation_status(db, appointment)


# --- preparation ------------------------------------------------------------

PresetQuery = Annotated[
    str,
    Query(
        pattern="^(since_last_visit|7_days|30_days|90_days|custom)$",
        description="Which period to summarise.",
    ),
]
DateQuery = Annotated[date | None, Query(description="Only used with the custom period.")]


@router.get("/{appointment_id}/prepare", response_model=PreparationRead)
def prepare_appointment(
    appointment_id: uuid.UUID,
    profile: OwnedProfile,
    db: DbSession,
    now: Now,
    preset: PresetQuery = "since_last_visit",
    period_start: DateQuery = None,
    period_end: DateQuery = None,
) -> PreparationRead:
    """Everything the preparation flow reads, in one request (s13, s49).

    Reads only: preparing for an appointment changes nothing about the records
    being prepared, and this route may be called again every time the user moves
    the period.

    Nothing in the response is ranked or interpreted, and the default selection
    it returns is "everything, every symptom" -- the narrowing is the user's
    (sections 15 and 25).
    """
    appointment = _fetch_appointment(db, profile, appointment_id)
    period = _resolve_period(db, appointment, now, preset, period_start, period_end)
    data = preparation_service.build(db, profile, appointment, period)
    offers = suggestion_service.suggest(data)

    return PreparationRead(
        appointment=_appointment_read(appointment, now),
        period=_period_read(period),
        symptoms=[_symptom_review_read(review) for review in data.symptoms],
        medications=[
            MedicationReviewRead(
                medication_id=review.medication_id,
                name=review.name,
                display_name=review.display_name,
                dose=review.dose,
                dose_unit=review.dose_unit,
                frequency=review.frequency,
                reason=review.reason,
                is_active=review.is_active,
            )
            for review in data.medications
        ],
        adherence=(
            None
            if data.adherence is None
            else AdherenceReviewRead(
                from_date=data.adherence.from_date,
                to_date=data.adherence.to_date,
                taken=data.adherence.taken,
                skipped=data.adherence.skipped,
                missed=data.adherence.missed,
                total=data.adherence.total,
                percent=data.adherence.percent,
                skip_notes=[
                    SkipNoteRead(
                        dose_id=note.dose_id,
                        local_date=note.local_date,
                        medication_name=note.medication_name,
                        reason_code=note.reason_code,
                        reason_text=note.reason_text,
                    )
                    for note in data.adherence.skip_notes
                ],
            )
        ),
        daily_checkins=(
            None
            if data.checkins is None
            else CheckInReviewRead(
                good=data.checkins.good,
                okay=data.checkins.okay,
                not_great=data.checkins.not_great,
                total=data.checkins.total,
                days_in_period=data.checkins.days_in_period,
                notes=[
                    CheckInNoteRead(
                        checkin_date=note.checkin_date,
                        wellbeing_level=note.wellbeing_level,  # type: ignore[arg-type]
                        note=note.note,
                    )
                    for note in data.checkins.notes
                ],
            )
        ),
        baseline=(
            None
            if data.baseline is None
            else BaselineReviewRead(
                conditions=[
                    ConditionItemRead(
                        condition_id=item.condition_id,
                        name=item.name,
                        status=item.status,
                        diagnosed_label=item.diagnosed_label,
                    )
                    for item in data.baseline.conditions
                ],
                allergies=[
                    AllergyItemRead(
                        allergy_id=item.allergy_id,
                        allergen=item.allergen,
                        reaction=item.reaction,
                        severity=item.severity,
                    )
                    for item in data.baseline.allergies
                ],
                procedures=[
                    ProcedureItemRead(
                        procedure_id=item.procedure_id,
                        name=item.name,
                        performed_label=item.performed_label,
                    )
                    for item in data.baseline.procedures
                ],
                blood_type=data.baseline.blood_type,
            )
        ),
        medical_notes=[
            MedicalNoteItemRead(
                note_id=note.note_id,
                title=note.title,
                body=note.body,
                category=note.category,
            )
            for note in data.medical_notes
        ],
        questions=[
            AppointmentQuestionRead.model_validate(question)
            for question in data.questions
        ],
        suggestions=[
            QuestionSuggestionRead(
                key=offer.key,
                prompt=offer.prompt,
                question_text=offer.question_text,
                reason=offer.reason,
            )
            for offer in offers
        ],
        has_health_data=data.has_any_health_data,
        default_selection=ReportSelectionRead(
            include=snapshot_service.default_include(),
            symptom_episode_ids=[review.episode_id for review in data.symptoms],
            include_appendix=False,
        ),
    )


def _symptom_review_read(
    review: preparation_service.SymptomReview,
) -> SymptomReviewRead:
    return SymptomReviewRead(
        episode_id=review.episode_id,
        name=review.name,
        body_site=review.body_site,
        status=review.status,
        is_ongoing=review.is_ongoing,
        entry_count=review.entry_count,
        first_noticed_label=review.first_noticed_label,
        latest_severity=review.latest_severity,
        severity_min=review.severity_min,
        severity_max=review.severity_max,
        latest_change_state=review.latest_change_state,  # type: ignore[arg-type]
        associated_symptoms=review.associated_symptoms,
        exacerbating_factors=review.exacerbating_factors,
        relieving_factors=review.relieving_factors,
        negated_items=review.negated_items,
        uncertain_items=review.uncertain_items,
        context_dependent_items=review.context_dependent_items,
        notes=[
            SymptomNoteRead(
                entry_id=note.entry_id, recorded_at=note.recorded_at, text=note.text
            )
            for note in review.notes
        ],
        photo_count=review.photo_count,
    )


# --- reports ----------------------------------------------------------------


@router.get("/{appointment_id}/reports", response_model=list[ReportRead])
def list_reports(
    appointment_id: uuid.UUID, profile: OwnedProfile, db: DbSession
) -> list[ReportRead]:
    """Every version for this appointment, newest first (PRD 7, section 41)."""
    appointment = _fetch_appointment(db, profile, appointment_id)
    return [
        _report_read(report) for report in report_service.list_reports(db, appointment.id)
    ]


@router.post("/{appointment_id}/reports", response_model=ReportSaved, status_code=CREATED)
def generate_report(
    appointment_id: uuid.UUID,
    payload: ReportGenerate,
    profile: OwnedProfile,
    db: DbSession,
    now: Now,
    response: Response,
) -> ReportSaved:
    """Generates one version from the user's selection (PRD 7, ss29-31).

    Deterministic all the way down: the content is built from the selection and
    the records as they are now, frozen into the row, and the PDF is rendered
    from that frozen copy. Editing a record afterwards cannot change this
    version, and regenerating makes a *new* one rather than overwriting it
    (sections 30 and 31).

    **Idempotent through ``client_report_id``**, so a double tap on Generate
    produces one version rather than two.
    """
    appointment = _fetch_appointment(db, profile, appointment_id)
    period = _resolve_period(
        db,
        appointment,
        now,
        payload.period_preset,
        payload.period_start,
        payload.period_end,
    )

    try:
        report, created = report_service.generate(
            db,
            get_object_store(),
            get_pdf_service(),
            profile,
            appointment,
            selection=_selection(payload.selection),
            period=period,
            now=now,
            client_report_id=payload.client_report_id,
        )
    except DomainError as error:
        raise http_error(error) from error

    if not created:
        response.status_code = status.HTTP_200_OK
    return ReportSaved(report=_report_detail(report), created=created)


@router.get("/{appointment_id}/reports/{report_id}", response_model=ReportDetailRead)
def read_report(
    appointment_id: uuid.UUID,
    report_id: uuid.UUID,
    profile: OwnedProfile,
    db: DbSession,
) -> ReportDetailRead:
    """One version, with the frozen content the preview renders (s32)."""
    _fetch_appointment(db, profile, appointment_id)
    return _report_detail(_fetch_report(db, profile, appointment_id, report_id))


@router.get(
    "/{appointment_id}/reports/{report_id}/pdf",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}, "description": "The document."}},
)
def read_report_pdf(
    appointment_id: uuid.UUID,
    report_id: uuid.UUID,
    profile: OwnedProfile,
    db: DbSession,
) -> Response:
    """The document itself, for the person it belongs to (PRD 7, section 52).

    The whole chain is re-checked on every request for every byte: the account
    owns the profile, the appointment belongs to the profile, and the report
    belongs to the appointment. There is no signed URL and no public path -- an
    unrelated account gets the same 404 as a report that was never there.

    ``no-store`` because a cached copy of somebody's doctor summary in a shared
    proxy is exactly the thing this route exists to prevent.
    """
    _fetch_appointment(db, profile, appointment_id)
    report = _fetch_report(db, profile, appointment_id, report_id)

    try:
        content = report_service.read_pdf(get_object_store(), report)
    except DomainError as error:
        raise http_error(error) from error

    return Response(
        content=content,
        media_type="application/pdf",
        headers={
            "Cache-Control": "private, no-store",
            # The filename carries a date and nothing medical (s33).
            "Content-Disposition": (
                f'attachment; filename="{report_service.file_name(report)}"'
            ),
            "Content-Length": str(len(content)),
        },
    )


@router.delete("/{appointment_id}/reports/{report_id}", status_code=NO_CONTENT)
def delete_report(
    appointment_id: uuid.UUID,
    report_id: uuid.UUID,
    profile: OwnedProfile,
    db: DbSession,
) -> None:
    """Removes one version -- the document as well as the row.

    Health records are untouched: a report is a copy of what was recorded, and
    deleting the copy never meant deleting the original (PRD 7, section 65).
    """
    _fetch_appointment(db, profile, appointment_id)
    report = _fetch_report(db, profile, appointment_id, report_id)
    report_service.delete_report(db, get_object_store(), report)
