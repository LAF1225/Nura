"""The health record (PRD 4, sections 8-16 and 23).

Six tables, one shape. Everything here belongs to a **profile**, never to the
account that typed it in: in assisted setup the account holder is not the
person the record is about, and getting that wrong once would be very hard to
unpick later (PRD 4, section 8).

Three conventions run through all of them:

**Dates are stored at the precision the user actually has.** "Diagnosed in
2015" is a year, not the 1st of January 2015. Each approximate date is two
columns -- an exact date and a year -- with a constraint making sure only one
is set (PRD 4, section 31).

**Almost everything is optional.** A condition needs a name; a medication needs
a name; a clinician needs a name. Nothing else is required, because a health
profile people fill in gradually is worth more than one they abandon at a
required field they cannot answer (PRD 4, section 3).

**Nothing here is interpreted.** These tables store what a person said about
themselves. No severity is inferred, no interaction is computed, no diagnosis
is suggested (PRD 4, sections 11, 12 and 55).
"""

import uuid
from datetime import date

from sqlalchemy import CheckConstraint, Date, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin
from app.models.enums import (
    ALLERGY_SEVERITIES,
    ALLERGY_TYPES,
    CONDITION_STATUSES,
    MEDICAL_NOTE_CATEGORIES,
    MEDICATION_FORMS,
    RECORD_SOURCES,
    sql_in_list,
)

#: Long enough for a real answer, short enough that a note cannot quietly
#: become a medical history document.
NAME_MAX_LENGTH = 120
SHORT_TEXT_MAX_LENGTH = 200
NOTES_MAX_LENGTH = 2000

#: Nothing earlier than this is a plausible year for a living person's medical
#: history, and nothing later than "now" has happened yet. Checked in the
#: database as well as the API, because a year is the one field where a typo
#: ("205") produces something that looks valid.
EARLIEST_YEAR = 1900


def approximate_date_constraint(table: str, prefix: str) -> CheckConstraint:
    """An exact date or a year, never both (PRD 4, section 31).

    Both columns null is fine: "I don't remember when" is a legitimate answer
    and must not be turned into a made-up date.
    """
    return CheckConstraint(
        f"NOT ({prefix}_date IS NOT NULL AND {prefix}_year IS NOT NULL)",
        name=f"ck_{table}_{prefix}_precision",
    )


def year_range_constraint(column: str, table: str) -> CheckConstraint:
    return CheckConstraint(
        f"{column} IS NULL OR ({column} >= {EARLIEST_YEAR} AND {column} <= 2200)",
        name=f"ck_{table}_{column}_range",
    )


def source_constraint(table: str) -> CheckConstraint:
    return CheckConstraint(
        f"source IN {sql_in_list(RECORD_SOURCES)}", name=f"ck_{table}_source"
    )


class HealthRecord(Base, TimestampMixin):
    """Shared shape for every health record.

    Abstract, so there is no ``health_records`` table -- each record type keeps
    its own columns and its own constraints. What is shared is the part that
    must never vary: the identity, the profile it belongs to, and the cascade
    that removes it with that profile.
    """

    __abstract__ = True

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    #: The person the record is about. Indexed because every query is "this
    #: profile's records" -- there is no route that reads across profiles.
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )


class MedicalCondition(HealthRecord):
    """Something a person has been diagnosed with, or told they might have.

    ``status`` includes ``uncertain`` on purpose: "they think it might be X" is
    a real and common situation, and recording it as ``active`` would state
    more than the person was told (PRD 4, section 9).
    """

    __tablename__ = "medical_conditions"
    __table_args__ = (
        CheckConstraint(
            f"status IN {sql_in_list(CONDITION_STATUSES)}",
            name="ck_medical_conditions_status",
        ),
        source_constraint("medical_conditions"),
        approximate_date_constraint("medical_conditions", "diagnosed"),
        year_range_constraint("diagnosed_year", "medical_conditions"),
    )

    #: As the user wrote it. Never matched against a terminology, never
    #: autocompleted into a diagnosis (PRD 4, section 9).
    name: Mapped[str] = mapped_column(String(NAME_MAX_LENGTH), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="active"
    )
    #: Exactly one of these, or neither. See ``approximate_date_constraint``.
    diagnosed_date: Mapped[date | None] = mapped_column(Date)
    diagnosed_year: Mapped[int | None] = mapped_column(Integer)
    #: Free text, not a foreign key: the clinician who diagnosed something is
    #: often not one the user has added to their own list.
    diagnosing_clinician: Mapped[str | None] = mapped_column(String(NAME_MAX_LENGTH))
    notes: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(20), nullable=False, server_default="user")


class Medication(HealthRecord):
    """A medication record -- and in PRD 4, only a record.

    No schedule, no reminder, no adherence, no refill. Those turn a record into
    an instruction, which is PRD 5's job and needs its own care (PRD 4,
    sections 10 and 11).

    ``frequency_text`` is free text for the same reason: "two puffs when
    needed" and "one at night" do not fit a structured schedule, and forcing
    them into one would either lose meaning or invent it.
    """

    __tablename__ = "medications"
    __table_args__ = (
        CheckConstraint(
            f"form IS NULL OR form IN {sql_in_list(MEDICATION_FORMS)}",
            name="ck_medications_form",
        ),
        source_constraint("medications"),
    )

    name: Mapped[str] = mapped_column(String(NAME_MAX_LENGTH), nullable=False)
    #: Kept as text with a separate unit, so "half a tablet" survives.
    dose: Mapped[str | None] = mapped_column(String(50))
    dose_unit: Mapped[str | None] = mapped_column(String(30))
    form: Mapped[str | None] = mapped_column(String(20))
    frequency_text: Mapped[str | None] = mapped_column(String(SHORT_TEXT_MAX_LENGTH))
    instructions: Mapped[str | None] = mapped_column(String(SHORT_TEXT_MAX_LENGTH))
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    prescribing_clinician: Mapped[str | None] = mapped_column(String(NAME_MAX_LENGTH))
    #: What it is for, in the user's words.
    reason: Mapped[str | None] = mapped_column(String(SHORT_TEXT_MAX_LENGTH))
    #: Something they are taking now, as opposed to a past medication kept for
    #: history. Set by the user, never inferred from ``end_date``.
    is_active: Mapped[bool] = mapped_column(nullable=False, server_default="true")
    notes: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(20), nullable=False, server_default="user")


class Allergy(HealthRecord):
    """Something that causes a reaction, as the person described it.

    ``severity`` is whatever they chose, including ``unknown``. Nura does not
    work severity out from the reaction text, and does not escalate on the
    word "severe" (PRD 4, section 12).
    """

    __tablename__ = "allergies"
    __table_args__ = (
        CheckConstraint(
            f"allergy_type IN {sql_in_list(ALLERGY_TYPES)}",
            name="ck_allergies_allergy_type",
        ),
        CheckConstraint(
            f"severity IN {sql_in_list(ALLERGY_SEVERITIES)}",
            name="ck_allergies_severity",
        ),
        source_constraint("allergies"),
    )

    allergen: Mapped[str] = mapped_column(String(NAME_MAX_LENGTH), nullable=False)
    allergy_type: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="other"
    )
    #: What happens, in their words -- "rash", "swelling", "upset stomach".
    reaction: Mapped[str | None] = mapped_column(String(SHORT_TEXT_MAX_LENGTH))
    severity: Mapped[str] = mapped_column(
        String(12), nullable=False, server_default="unknown"
    )
    notes: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(20), nullable=False, server_default="user")


class Clinician(HealthRecord):
    """A doctor, nurse or other clinician the person sees.

    The user's own list, typed by them. No provider directory is consulted and
    none is planned here (PRD 4, section 13); only ``name`` is required,
    because "my GP" with nothing else is still worth keeping.
    """

    __tablename__ = "clinicians"

    name: Mapped[str] = mapped_column(String(NAME_MAX_LENGTH), nullable=False)
    specialty: Mapped[str | None] = mapped_column(String(NAME_MAX_LENGTH))
    clinic_name: Mapped[str | None] = mapped_column(String(NAME_MAX_LENGTH))
    phone: Mapped[str | None] = mapped_column(String(40))
    email: Mapped[str | None] = mapped_column(String(320))
    address: Mapped[str | None] = mapped_column(String(SHORT_TEXT_MAX_LENGTH))
    notes: Mapped[str | None] = mapped_column(Text)


class Procedure(HealthRecord):
    """A surgery or procedure someone has had.

    Dates here are frequently approximate -- an operation "about 2009" is a
    normal answer -- so the same date/year pair is used as for conditions.
    """

    __tablename__ = "procedures"
    __table_args__ = (
        approximate_date_constraint("procedures", "performed"),
        year_range_constraint("performed_year", "procedures"),
    )

    name: Mapped[str] = mapped_column(String(NAME_MAX_LENGTH), nullable=False)
    #: Named ``performed_*`` rather than ``date``/``year``: "date" alone is
    #: ambiguous once a row also has created_at and updated_at.
    performed_date: Mapped[date | None] = mapped_column(Date)
    performed_year: Mapped[int | None] = mapped_column(Integer)
    hospital: Mapped[str | None] = mapped_column(String(NAME_MAX_LENGTH))
    clinician: Mapped[str | None] = mapped_column(String(NAME_MAX_LENGTH))
    outcome_notes: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)


class MedicalNote(HealthRecord):
    """Something important that does not fit any of the other shapes.

    Deliberately a note and nothing more. It is never parsed into conditions,
    and symptoms must not be kept here -- they get their own model in PRD 6
    (PRD 4, sections 16 and 41).
    """

    __tablename__ = "medical_notes"
    __table_args__ = (
        CheckConstraint(
            f"category IN {sql_in_list(MEDICAL_NOTE_CATEGORIES)}",
            name="ck_medical_notes_category",
        ),
    )

    title: Mapped[str] = mapped_column(String(NAME_MAX_LENGTH), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="general"
    )
