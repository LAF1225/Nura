"""Medication scheduling, doses and supply (PRD 5, sections 4, 8, 21 and 50).

PRD 4 recorded *what a medication is*. This file records *when Nura should
remind someone about it*, *what happened at each of those times*, and *how
much of it is left*. Those are deliberately three different things, kept in
three different tables (PRD 5, section 4):

    medications          what it is                 (PRD 4, untouched)
        |
        +-- medication_schedules       when to remind
        |       +-- medication_schedule_times   the times within that pattern
        |
        +-- medication_doses           one concrete moment, and what happened
        |
        +-- medication_supply          how many are left

Four conventions run through all of them.

**A schedule carries its own time zone.** A reminder means a wall-clock time
where the person is -- "eight in the morning" -- not an instant. Storing the
IANA zone with the schedule is what lets the generator keep producing 8am
local across a daylight-saving change, and what stops a trip abroad from
silently doubling a day's doses. See ``docs/architecture/medication-system.md``.

**A dose is a row, not a calculation.** Doses are generated ahead of time as
concrete rows, so "what is due today", "what did I miss", and the local
notification schedule all read the same thing rather than three separate
re-derivations of a recurrence rule (PRD 5, section 22).

**History is never rewritten.** Editing or deleting a schedule touches future
doses only; a dose that has already been recorded keeps its status, its time
and its source forever (PRD 5, sections 36 and 39). That is why
``schedule_id`` clears rather than cascades.

**Nothing here is interpreted.** A skip reason is stored as the person chose
it. No dose is adjusted, doubled, recommended or withheld, and nothing infers
a medical meaning from an adherence figure (PRD 5, sections 3 and 57).
"""

import uuid
from datetime import date, datetime, time

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Time,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.enums import (
    DOSE_SOURCES,
    DOSE_STATUSES,
    SCHEDULE_TYPES,
    SKIP_REASON_CODES,
    sql_in_list,
)
from app.models.health import Medication

#: IANA zone names are well under this ("America/Argentina/ComodRivadavia" is
#: the longest at 32). Room to spare costs nothing.
TIMEZONE_MAX_LENGTH = 64

#: Free text the user typed to explain a skip. Short on purpose: this is a
#: note beside a checkbox, not a place to keep a medical history.
SKIP_REASON_TEXT_MAX_LENGTH = 200

#: Monday is 0, matching ``date.weekday()`` so no translation is ever needed
#: between the database and the generator.
MONDAY, SUNDAY = 0, 6


class MedicationSchedule(Base, TimestampMixin):
    """A repeating pattern of reminders for one medication.

    A medication may have none, one, or several of these (PRD 5, section 4):
    "one at night" and "two in the morning on weekdays" are two schedules for
    the same medication, not one schedule with a special case in it.

    ``is_active`` is the pause switch (PRD 5, section 37). A paused schedule
    generates nothing and reminds about nothing, while keeping every dose it
    has already produced. Nothing infers *why* it was paused.
    """

    __tablename__ = "medication_schedules"
    __table_args__ = (
        CheckConstraint(
            f"schedule_type IN {sql_in_list(SCHEDULE_TYPES)}",
            name="ck_medication_schedules_type",
        ),
        CheckConstraint(
            "end_date IS NULL OR end_date >= start_date",
            name="ck_medication_schedules_date_range",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    #: The person the reminders are for. Carried on the schedule as well as
    #: reachable through the medication, so every query and every
    #: authorization check is "this profile's rows" without a join.
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    medication_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("medications.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    schedule_type: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="daily"
    )
    #: IANA name, e.g. ``Europe/London``. The whole daylight-saving policy
    #: rests on this: the generator resolves a wall-clock time *in this zone*
    #: to an instant, rather than storing an offset that goes stale in spring.
    timezone: Mapped[str] = mapped_column(
        String(TIMEZONE_MAX_LENGTH), nullable=False, server_default="UTC"
    )
    #: Local calendar dates, in the schedule's own zone.
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    #: Null means "no end date", which is the common case for a repeat
    #: prescription (PRD 5, section 11).
    end_date: Mapped[date | None] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(nullable=False, server_default="true")
    #: When the user paused it. Kept only so the app can say "paused since",
    #: never to infer a reason (PRD 5, section 37).
    paused_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    medication: Mapped[Medication] = relationship()
    times: Mapped[list["MedicationScheduleTime"]] = relationship(
        back_populates="schedule",
        cascade="all, delete-orphan",
        order_by="MedicationScheduleTime.time_of_day",
    )


class MedicationScheduleTime(Base, TimestampMixin):
    """One reminder time within a schedule.

    ``weekday`` is null on a daily schedule and set on a ``specific_days``
    one, so "8am and 8pm every day" is two rows and "9am on Mon/Wed/Fri" is
    three -- one shape covering both of PRD 5 section 9's patterns without a
    recurrence grammar to parse.

    ``time_of_day`` is a naive wall-clock time. It is meaningless without the
    parent schedule's ``timezone``, and is never converted at rest.
    """

    __tablename__ = "medication_schedule_times"
    __table_args__ = (
        CheckConstraint(
            f"weekday IS NULL OR (weekday >= {MONDAY} AND weekday <= {SUNDAY})",
            name="ck_medication_schedule_times_weekday",
        ),
        # NULLS NOT DISTINCT so two daily rows at the same time collide rather
        # than quietly producing two reminders a minute apart.
        UniqueConstraint(
            "schedule_id",
            "time_of_day",
            "weekday",
            name="uq_medication_schedule_time",
            postgresql_nulls_not_distinct=True,
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    schedule_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("medication_schedules.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    time_of_day: Mapped[time] = mapped_column(Time(timezone=False), nullable=False)
    #: Null means every day. 0 is Monday (``date.weekday()``).
    weekday: Mapped[int | None] = mapped_column(SmallInteger)

    schedule: Mapped[MedicationSchedule] = relationship(back_populates="times")


class MedicationDose(Base, TimestampMixin):
    """One moment a medication was due, and what happened at it.

    Generated ahead of time by ``app.services.medications.doses`` and then
    owned by the user: Taken, Snooze and Skip all update *this* row rather
    than adding an event beside it. That is what makes a retried request
    harmless -- there is one row per scheduled moment, and re-sending Taken
    finds it already taken (PRD 5, sections 25 and 48).

    ``schedule_id`` clears rather than cascades on purpose. Deleting a
    schedule stops future reminders; it must not erase what somebody already
    recorded about their own medication (PRD 5, section 39).
    """

    __tablename__ = "medication_doses"
    __table_args__ = (
        CheckConstraint(
            f"status IN {sql_in_list(DOSE_STATUSES)}", name="ck_medication_doses_status"
        ),
        CheckConstraint(
            f"source IS NULL OR source IN {sql_in_list(DOSE_SOURCES)}",
            name="ck_medication_doses_source",
        ),
        CheckConstraint(
            f"skip_reason_code IS NULL OR skip_reason_code IN "
            f"{sql_in_list(SKIP_REASON_CODES)}",
            name="ck_medication_doses_skip_reason",
        ),
        CheckConstraint("snooze_count >= 0", name="ck_medication_doses_snooze_count"),
        # One row per scheduled moment per schedule, so a regeneration that
        # races with itself -- or two phones syncing at once -- cannot produce
        # the same 8am twice (PRD 5, sections 12 and 63).
        UniqueConstraint(
            "schedule_id", "scheduled_for", name="uq_medication_dose_occurrence"
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
    medication_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("medications.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    #: Null once the schedule behind it has been deleted. The dose remains.
    schedule_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("medication_schedules.id", ondelete="SET NULL"),
        index=True,
    )
    #: The instant the dose is due, in UTC.
    scheduled_for: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    #: The calendar day it belongs to *where the user is*. Stored rather than
    #: recomputed so "today's medications" and a day's history are one indexed
    #: comparison, and so a dose keeps the day it was scheduled for even if
    #: the schedule's zone is later changed.
    local_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="scheduled"
    )
    #: When the person actually recorded something -- not when the request
    #: arrived, and not when the dose was due (PRD 5, section 25).
    action_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: Set by the server from how the action arrived, never by a client.
    source: Mapped[str | None] = mapped_column(String(20))
    skip_reason_code: Mapped[str | None] = mapped_column(String(20))
    skip_reason_text: Mapped[str | None] = mapped_column(
        String(SKIP_REASON_TEXT_MAX_LENGTH)
    )
    snoozed_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: How many times this dose has been put off. Capped by the service so a
    #: reminder cannot be snoozed indefinitely (PRD 5, section 18).
    snooze_count: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default="0"
    )

    medication: Mapped[Medication] = relationship()
    schedule: Mapped[MedicationSchedule | None] = relationship()


class MedicationSupply(Base, TimestampMixin):
    """How much of a medication is left, as the user believes it to be.

    Opt-in per medication (``tracking_enabled``), because a count nobody keeps
    up to date is worse than no count at all. Decremented only when a dose is
    marked Taken -- never on Snooze, Skip or Missed (PRD 5, section 33) -- and
    always correctable by hand.

    Nura treats this as approximate and says so when it warns (PRD 5,
    section 34). It never orders a refill, never contacts a pharmacy, and
    never tells anyone to change what they take.
    """

    __tablename__ = "medication_supply"
    __table_args__ = (
        CheckConstraint(
            "remaining_doses IS NULL OR remaining_doses >= 0",
            name="ck_medication_supply_remaining",
        ),
        CheckConstraint(
            "refill_threshold_doses IS NULL OR refill_threshold_doses >= 0",
            name="ck_medication_supply_threshold",
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
    #: One supply record per medication, which is what makes
    #: "PATCH the supply for this medication" an unambiguous request.
    medication_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("medications.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    tracking_enabled: Mapped[bool] = mapped_column(nullable=False, server_default="false")
    remaining_doses: Mapped[int | None] = mapped_column(Integer)
    #: Warn at or below this many left. Null means never warn.
    refill_threshold_doses: Mapped[int | None] = mapped_column(Integer)
    last_refill_date: Mapped[date | None] = mapped_column(Date)
