"""Appointments, the questions for them, and the reports made from them.

PRD 7, sections 6, 22, 30 and 42.

Three tables, and the relationship between them is the whole feature:

    appointments                  a visit, entered by hand
        |
        +-- appointment_questions     what the person wants to ask
        |
        +-- appointment_reports       a frozen summary to hand over

Four conventions run through them.

**An appointment is entered, never synced.** There is no calendar integration
in PRD 7 and no field that implies one: no external id, no sync token, no
provider (section 4). Everything here was typed by somebody.

**A report is a snapshot, not a query.** ``snapshot`` holds the finished text
of the report as it read at the moment it was generated. Nothing in it is
recomputed on a later read, so editing a symptom entry next week cannot change
what a PDF handed to a doctor last week says (section 30). Regeneration makes a
*new version*; the old one is left exactly as it was (section 31).

**The user decides what is in it.** ``selection`` records what they chose to
include, per section and per symptom episode. There is no rule anywhere that
adds a section because it looked important, because deciding that is a clinical
judgement Nura does not make (sections 3, 15 and 25).

**Nothing here interprets anything.** No diagnosis, no probable cause, no
treatment suggestion, no claim that a medication caused a symptom (section 45).
The tables have nowhere to put such a thing, which is the most reliable way of
not having one.
"""

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.enums import (
    APPOINTMENT_PREPARATION_STATUSES,
    APPOINTMENT_STATUSES,
    APPOINTMENT_TYPES,
    REPORT_PERIOD_PRESETS,
    REPORT_STATUSES,
    sql_in_list,
)
from app.models.health import NAME_MAX_LENGTH, SHORT_TEXT_MAX_LENGTH, Clinician
from app.models.medication import TIMEZONE_MAX_LENGTH
from app.models.symptom import CLIENT_ID_MAX_LENGTH, STORAGE_KEY_MAX_LENGTH

#: "Cardiology follow-up". Same length as a condition or a symptom name, so the
#: three feel like one product.
APPOINTMENT_TITLE_MAX_LENGTH = NAME_MAX_LENGTH

#: A question in the user's own words (PRD 7, section 23). Long enough for a
#: real question with its context, short enough that the list stays a list.
QUESTION_MAX_LENGTH = 500

#: What the clinician said, as the user wrote it down afterwards
#: (PRD 7, section 39). Their record of the answer, never verified clinical data.
ANSWER_NOTE_MAX_LENGTH = 1000

#: A phone number as typed. Never parsed, never dialled -- PRD 7 has no calling
#: (section 70).
PHONE_MAX_LENGTH = 40


class Appointment(Base, TimestampMixin):
    """One visit, as the person recorded it (PRD 7, sections 6-8).

    ``scheduled_at`` is the instant; ``timezone`` is the zone it was arranged
    in. Both are kept for the reason PRD 5 keeps them on a medication schedule:
    an appointment at 3:30 PM in London is still at 3:30 PM in London after the
    clocks change and after the user flies to Karachi, and an instant alone
    cannot say that (PRD 7, section 42).

    ``clinician_id`` is optional and stays optional. Plenty of appointments are
    "the hospital" or "blood test", and requiring a clinician record first would
    put a form in front of somebody trying to note down a date.
    """

    __tablename__ = "appointments"
    __table_args__ = (
        CheckConstraint(
            f"status IN {sql_in_list(APPOINTMENT_STATUSES)}",
            name="ck_appointments_status",
        ),
        CheckConstraint(
            f"appointment_type IN {sql_in_list(APPOINTMENT_TYPES)}",
            name="ck_appointments_type",
        ),
        CheckConstraint(
            f"preparation_status IN {sql_in_list(APPOINTMENT_PREPARATION_STATUSES)}",
            name="ck_appointments_preparation_status",
        ),
        # Cancelled and completed both mean "somebody said so, then". The
        # reverse is not forced: a cancelled appointment that is rescheduled
        # back to `scheduled` may keep the timestamp of the earlier decision.
        CheckConstraint(
            "status <> 'cancelled' OR cancelled_at IS NOT NULL",
            name="ck_appointments_cancelled_at",
        ),
        CheckConstraint(
            "status <> 'completed' OR completed_at IS NOT NULL",
            name="ck_appointments_completed_at",
        ),
        # The idempotency key (PRD 7, section 53). Scoped to the profile, and
        # NULLS DISTINCT by default so any number of rows may leave it unset.
        UniqueConstraint(
            "profile_id", "client_appointment_id", name="uq_appointment_client_id"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    #: The person the appointment is for, never the account that typed it in.
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    #: The clinician from the user's own list, if they picked one. Clears rather
    #: than cascades: deleting a doctor from the list must not delete the
    #: appointments that mention them, or the history goes with it.
    clinician_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("clinicians.id", ondelete="SET NULL"),
        index=True,
    )
    #: As the user wrote it -- "Cardiology follow-up", "Blood test".
    title: Mapped[str] = mapped_column(
        String(APPOINTMENT_TITLE_MAX_LENGTH), nullable=False
    )
    appointment_type: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="other"
    )
    scheduled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    #: An IANA name such as ``Europe/London``. Required for the same reason a
    #: medication schedule's is (PRD 5, section 12; PRD 7, section 42).
    timezone: Mapped[str] = mapped_column(String(TIMEZONE_MAX_LENGTH), nullable=False)
    location_name: Mapped[str | None] = mapped_column(String(NAME_MAX_LENGTH))
    address: Mapped[str | None] = mapped_column(String(SHORT_TEXT_MAX_LENGTH))
    phone: Mapped[str | None] = mapped_column(String(PHONE_MAX_LENGTH))
    #: Anything the user wants to remember beforehand. Never parsed, and never
    #: put in a report unless they choose to include it.
    notes: Mapped[str | None] = mapped_column(Text)
    #: What happened, written afterwards (PRD 7, section 38). Deliberately a
    #: separate column from ``notes``: "bring the previous scan" and "the doctor
    #: said continue at lower intensity" are not the same note.
    visit_notes: Mapped[str | None] = mapped_column(Text)
    #: A date the user was given for a next visit. Just a date -- nothing books
    #: anything, and adding the follow-up opens the ordinary form
    #: (PRD 7, section 40).
    follow_up_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(
        String(12), nullable=False, server_default="scheduled", index=True
    )
    #: A cache of a derivation, written only by the server. See
    #: ``services.appointments.appointments.preparation_state``: it is worked
    #: out from what exists -- questions, and a generated report -- so it cannot
    #: claim preparation that did not happen (PRD 7, sections 6 and 10).
    preparation_status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="not_started"
    )
    #: Whether the app should raise the two local reminders (PRD 7, section 36).
    #: Stored on the appointment so the choice survives reinstalling the app,
    #: and so changing the time can reschedule from one source of truth
    #: (section 54).
    reminders_enabled: Mapped[bool] = mapped_column(nullable=False, server_default="true")
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: The client's own id, so an appointment created from an offline draft
    #: cannot be created twice by a retry (PRD 7, section 53).
    client_appointment_id: Mapped[str | None] = mapped_column(
        String(CLIENT_ID_MAX_LENGTH)
    )

    clinician: Mapped[Clinician | None] = relationship()
    questions: Mapped[list["AppointmentQuestion"]] = relationship(
        back_populates="appointment",
        cascade="all, delete-orphan",
        order_by="AppointmentQuestion.position",
    )
    reports: Mapped[list["AppointmentReport"]] = relationship(
        back_populates="appointment",
        cascade="all, delete-orphan",
        order_by="AppointmentReport.version.desc()",
    )


class AppointmentQuestion(Base, TimestampMixin):
    """Something the person wants to ask, in their words (PRD 7, sections 22-23).

    ``text`` is stored exactly as typed. Nothing rewrites it into a better
    question, expands an abbreviation, or corrects the grammar: it is going to
    be read out in a consulting room by the person who wrote it, and their
    phrasing is the point (section 23).

    ``position`` is the order they put them in. Suggested questions
    (section 24) reach this table only after the user has accepted one, and are
    indistinguishable from their own once they have -- because at that point
    they *are* theirs.
    """

    __tablename__ = "appointment_questions"
    __table_args__ = (
        CheckConstraint("position >= 0", name="ck_appointment_questions_position"),
        UniqueConstraint(
            "profile_id", "client_question_id", name="uq_appointment_question_client_id"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    #: Carried here as well as reachable through the appointment, so every query
    #: and every authorization check is "this profile's rows".
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    appointment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("appointments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    text: Mapped[str] = mapped_column(String(QUESTION_MAX_LENGTH), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    #: Ticked off after the visit. Nothing infers it from an answer note being
    #: present, because somebody may note context without getting an answer.
    is_answered: Mapped[bool] = mapped_column(nullable=False, server_default="false")
    #: The user's record of what they were told (PRD 7, section 39). Their
    #: words, not verified clinical data, and never treated as such.
    answer_note: Mapped[str | None] = mapped_column(String(ANSWER_NOTE_MAX_LENGTH))
    #: The client's own id, so a question added offline lands once
    #: (PRD 7, section 53).
    client_question_id: Mapped[str | None] = mapped_column(String(CLIENT_ID_MAX_LENGTH))

    appointment: Mapped[Appointment] = relationship(back_populates="questions")


class AppointmentReport(Base, TimestampMixin):
    """A frozen summary of selected records, and the PDF made from it.

    PRD 7, sections 29-31.

    ``snapshot`` is the report's content: the finished headings and sentences,
    as they read when the user pressed Generate. That is the strongest form of
    what section 30 asks for -- a report handed to a doctor does not change
    because a symptom entry was corrected afterwards, and re-rendering the PDF
    from an old row produces the same document it always did.

    ``selection`` is what the user chose, kept beside the result so a
    regeneration can start from their last answers rather than from defaults.

    ``version`` counts up per appointment and is never reused. Regenerating
    writes a new row; the previous one keeps its snapshot and its stored file,
    because somebody may already have sent it (section 31).
    """

    __tablename__ = "appointment_reports"
    __table_args__ = (
        CheckConstraint(
            f"status IN {sql_in_list(REPORT_STATUSES)}",
            name="ck_appointment_reports_status",
        ),
        CheckConstraint(
            f"period_preset IN {sql_in_list(REPORT_PERIOD_PRESETS)}",
            name="ck_appointment_reports_period_preset",
        ),
        CheckConstraint("version >= 1", name="ck_appointment_reports_version"),
        CheckConstraint(
            "period_end >= period_start", name="ck_appointment_reports_period"
        ),
        # A row that says it is ready has a file behind it. Without this, a
        # failed PDF write could leave something the app offers to export and
        # the storage layer cannot find.
        CheckConstraint(
            "status <> 'ready' OR file_storage_key IS NOT NULL",
            name="ck_appointment_reports_ready_file",
        ),
        CheckConstraint(
            "byte_size IS NULL OR byte_size > 0",
            name="ck_appointment_reports_byte_size",
        ),
        UniqueConstraint(
            "appointment_id", "version", name="uq_appointment_report_version"
        ),
        UniqueConstraint(
            "profile_id", "client_report_id", name="uq_appointment_report_client_id"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    appointment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("appointments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    #: 1, 2, 3... per appointment. "Report v2" in the app (section 31).
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    #: PRD 7 section 30 calls these ``report_period_start`` and
    #: ``report_period_end``; the table is already ``appointment_reports``, so
    #: the prefix would only repeat itself.
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    #: How the period was arrived at, so the report can say why it covers what
    #: it covers -- and so "since my last visit" quietly becoming 30 days is
    #: recorded rather than invisible (PRD 7, section 14).
    period_preset: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="custom"
    )
    include_appendix: Mapped[bool] = mapped_column(nullable=False, server_default="false")
    #: What the user chose to include. PRD 7 section 30 calls it
    #: ``selection_json``.
    selection: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    #: The finished report. See the class docstring.
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    #: Where the PDF lives, relative to the private media root. Never a URL and
    #: never returned to a client: the file is read through an authenticated
    #: route, exactly as a symptom photo is (PRD 7, sections 35 and 52).
    file_storage_key: Mapped[str | None] = mapped_column(
        String(STORAGE_KEY_MAX_LENGTH), unique=True
    )
    byte_size: Mapped[int | None] = mapped_column(Integer)
    #: Pages in the generated PDF. Recorded so "the summary is one page" is a
    #: fact about the file rather than an aspiration (PRD 7, section 26).
    page_count: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(
        String(12), nullable=False, server_default="ready"
    )
    #: The client's own id, so a double tap on Generate makes one version
    #: rather than two (PRD 7, section 31).
    client_report_id: Mapped[str | None] = mapped_column(String(CLIENT_ID_MAX_LENGTH))

    appointment: Mapped[Appointment] = relationship(back_populates="reports")
