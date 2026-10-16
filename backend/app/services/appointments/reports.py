"""Report versions, private storage and export (PRD 7, sections 29-35 and 52).

The pipeline PRD 7 section 29 asks for, in order:

    preparation.build  ->  snapshot.build  ->  pdf.render  ->  a stored row

Each step is a function of the one before it, and only the last touches the
database or the disk.

**A version is never overwritten.** Regenerating writes a new row with the next
version number; the previous snapshot and the previous file stay exactly as they
were, because somebody may already have emailed it (section 31). Deleting a
version is an explicit act.

**A report is as private as a symptom photo, and stored the same way.** The
bytes go to the private object store under a key the server builds, the key is
never in a response, and the only way to the file is a route that re-checks the
account, the profile, the appointment and the report first (sections 35 and 52).
There is no signed URL.

**Nothing is claimed before it is true.** The row is written only after the PDF
is in storage, and a row that says ``ready`` has a file behind it -- the database
CHECK says so. So the app cannot be offered an export that does not exist
(section 53's "do not pretend generation succeeded").
"""

import logging
import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Appointment, AppointmentReport, Profile
from app.services.appointments import appointments as appointment_service
from app.services.appointments import preparation as preparation_service
from app.services.appointments import snapshot as snapshot_service
from app.services.appointments.pdf import PdfReportService
from app.services.appointments.periods import ReportPeriod
from app.services.appointments.snapshot import ReportSelection
from app.services.errors import DomainError, NotFoundError
from app.services.storage import ObjectNotFoundError, ObjectStore, validate_key

logger = logging.getLogger(__name__)

#: How many versions one appointment may keep. Reached only by somebody
#: regenerating repeatedly, and refused rather than pruned: PRD 7 section 31
#: forbids removing a version the user has not asked to remove.
MAX_REPORTS_PER_APPOINTMENT = 20

#: Where a report's PDF lives, relative to the private media root. Built from
#: ids the server generated -- never from anything a client sent
#: (PRD 7, section 52).
KEY_TEMPLATE = "reports/{profile}/{appointment}/{report}.pdf"


class ReportNotFoundError(NotFoundError):
    """No such report on this appointment, for this profile."""


class ReportNotReadyError(DomainError):
    """The row exists but there is no document behind it."""

    status_code = 409
    code = "report_not_ready"


class TooManyReportsError(DomainError):
    status_code = 409
    code = "too_many_reports"


def _log(action: str) -> None:
    """Never a heading, a count or a section name (PRD 7, section 57)."""
    logger.info("reports: %s", action)


def storage_key_for(
    profile_id: uuid.UUID, appointment_id: uuid.UUID, report_id: uuid.UUID
) -> str:
    """The object key for one report's PDF. Validated before it is used."""
    return validate_key(
        KEY_TEMPLATE.format(
            profile=profile_id.hex, appointment=appointment_id.hex, report=report_id.hex
        )
    )


# --- reading ----------------------------------------------------------------


def list_reports(db: Session, appointment_id: uuid.UUID) -> list[AppointmentReport]:
    """Every version for one appointment, newest first (PRD 7, section 41)."""
    return list(
        db.execute(
            select(AppointmentReport)
            .where(AppointmentReport.appointment_id == appointment_id)
            .order_by(AppointmentReport.version.desc())
        )
        .scalars()
        .all()
    )


def latest_report(db: Session, appointment_id: uuid.UUID) -> AppointmentReport | None:
    """The newest version, which is what "Report v2" on the detail screen is."""
    return db.execute(
        select(AppointmentReport)
        .where(AppointmentReport.appointment_id == appointment_id)
        .order_by(AppointmentReport.version.desc())
        .limit(1)
    ).scalar_one_or_none()


def get_report(
    db: Session,
    profile_id: uuid.UUID,
    appointment_id: uuid.UUID,
    report_id: uuid.UUID,
) -> AppointmentReport:
    """One report, by profile *and* appointment *and* id (PRD 7, section 51)."""
    report = db.execute(
        select(AppointmentReport).where(
            AppointmentReport.id == report_id,
            AppointmentReport.appointment_id == appointment_id,
            AppointmentReport.profile_id == profile_id,
        )
    ).scalar_one_or_none()

    if report is None:
        raise ReportNotFoundError("That report could not be found.")
    return report


def find_by_client_id(
    db: Session, profile_id: uuid.UUID, client_report_id: str
) -> AppointmentReport | None:
    """The version a client already generated with this id, if any.

    What stops a double tap on Generate from producing v2 and v3 of the same
    thing (PRD 7, section 31).
    """
    return db.execute(
        select(AppointmentReport).where(
            AppointmentReport.profile_id == profile_id,
            AppointmentReport.client_report_id == client_report_id,
        )
    ).scalar_one_or_none()


def next_version(db: Session, appointment_id: uuid.UUID) -> int:
    """One more than the highest version currently stored.

    Taken from the highest rather than the count, so deleting v1 while v2 exists
    and regenerating gives v3 -- a version number never sits between two others.

    Deleting the *newest* version does free its number, and that is deliberate:
    the user removed that document on purpose, and the app always shows the
    generated time beside the version, which is what PRD 7 section 31's own
    example metadata does. What never happens is the thing section 31 actually
    forbids -- a regeneration overwriting a version that is still there.
    """
    highest = db.execute(
        select(AppointmentReport.version)
        .where(AppointmentReport.appointment_id == appointment_id)
        .order_by(AppointmentReport.version.desc())
        .limit(1)
    ).scalar_one_or_none()
    return (highest or 0) + 1


def file_name(report: AppointmentReport) -> str:
    """ "Nura_Health_Summary_2026-10-02.pdf" (PRD 7, section 33)."""
    return snapshot_service.file_name(report.generated_at.date())


def read_pdf(store: ObjectStore, report: AppointmentReport) -> bytes:
    """The document itself, for the person it belongs to.

    Refuses rather than 500s when the row and the storage disagree, which is a
    deployment problem and is logged as one.
    """
    if report.status != "ready" or report.file_storage_key is None:
        raise ReportNotReadyError("That report has no document yet.")
    try:
        return store.get(report.file_storage_key)
    except ObjectNotFoundError as error:
        logger.error("reports: a report row has no stored document")
        raise ReportNotReadyError("That report could not be read.") from error


# --- generating -------------------------------------------------------------


def generate(
    db: Session,
    store: ObjectStore,
    pdf_service: PdfReportService,
    profile: Profile,
    appointment: Appointment,
    *,
    selection: ReportSelection,
    period: ReportPeriod,
    now: datetime,
    client_report_id: str | None = None,
) -> tuple[AppointmentReport, bool]:
    """Builds, renders and stores one version. Returns it, and whether it is new.

    The order is deliberate: the document is written to storage *before* the row
    that claims it exists, so a failure part-way leaves an unreferenced file
    rather than a report the app offers and cannot open. If the row then fails to
    commit, the file is removed again.
    """
    if client_report_id is not None:
        existing = find_by_client_id(db, profile.id, client_report_id)
        if existing is not None:
            return existing, False

    if len(list_reports(db, appointment.id)) >= MAX_REPORTS_PER_APPOINTMENT:
        raise TooManyReportsError("This appointment has too many report versions.")

    data = preparation_service.build(db, profile, appointment, period)
    content = snapshot_service.build(data, selection, generated_at=now)
    rendered = pdf_service.render(content)

    report_id = uuid.uuid4()
    key = storage_key_for(profile.id, appointment.id, report_id)
    store.put(key, rendered.content)

    report = AppointmentReport(
        id=report_id,
        profile_id=profile.id,
        appointment_id=appointment.id,
        version=next_version(db, appointment.id),
        period_start=period.start,
        period_end=period.end,
        period_preset=period.preset,
        include_appendix=selection.include_appendix,
        selection=selection.as_dict(),
        snapshot=content,
        generated_at=now,
        file_storage_key=key,
        byte_size=rendered.byte_size,
        page_count=rendered.page_count,
        status="ready",
        client_report_id=client_report_id,
    )
    db.add(report)
    try:
        db.commit()
    except Exception:
        db.rollback()
        store.delete(key)
        raise

    db.refresh(report)
    appointment_service.refresh_preparation_status(db, appointment)
    _log("generated a report version")
    return report, True


def delete_report(db: Session, store: ObjectStore, report: AppointmentReport) -> None:
    """Removes one version -- the stored document as well as the row.

    The file goes first: a row with no file is recoverable, while a file with no
    row is invisible and stays on disk forever (PRD 7, section 35).

    Health records are untouched. A report is a copy of what was recorded, and
    deleting the copy has never meant deleting the original
    (section 65's "report deletion leaves health records intact").
    """
    appointment_id = report.appointment_id
    if report.file_storage_key is not None:
        store.delete(report.file_storage_key)
    db.delete(report)
    db.commit()

    appointment = db.get(Appointment, appointment_id)
    if appointment is not None:
        appointment_service.refresh_preparation_status(db, appointment)
    _log("deleted a report version")


def purge_objects(store: ObjectStore, reports: list[AppointmentReport]) -> None:
    """Removes the stored documents for these rows.

    Called before deleting an appointment: a database cascade takes the rows and
    cannot reach the files, so without this a deleted appointment would leave its
    PDFs on disk (PRD 7, section 35).
    """
    for report in reports:
        if report.file_storage_key is not None:
            store.delete(report.file_storage_key)
