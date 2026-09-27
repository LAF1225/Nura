"""Symptom episodes, entries and photos (PRD 6, sections 8-11, 31 and 54).

PRD 4 recorded what a person has been *diagnosed* with. This file records what
they are *experiencing*, which is a different thing and deliberately kept in
different tables: a symptom is never converted into a condition, in either
direction (PRD 6, section 6).

The shape follows the one distinction the whole feature rests on
(PRD 6, section 8):

    symptom_episodes          the ongoing problem -- "this headache"
        |
        +-- symptom_entries       one observation about it, at one moment
                |
                +-- symptom_photos    what it looked like, stored privately

Four conventions run through all of them.

**An episode is a bout, not a name.** A headache in March and a headache in
October are two episodes, the second pointing back at the first through
``previous_episode_id`` and carrying the status ``recurring``. That keeps each
bout's own onset and resolution intact instead of merging unrelated events into
one endless episode (PRD 6, section 38).

**Nothing is required except a name.** Severity, site, character, onset,
timing, factors -- every one of them is optional, because somebody describing a
symptom mid-episode often cannot answer half the questions, and a model that
demands answers would either lose the description or invent it (section 11).

**Uncertainty is preserved, not flattened.** "No nausea", "I'm not sure if it
spreads" and "I might have felt dizzy" are kept as what they are, in
``negated_items``, ``uncertain_items`` and ``context_dependent_items``. A
symptom that was explicitly *denied* is information, and turning it into
silence loses it (section 24).

**Nothing here is interpreted.** No symptom is matched to a diagnosis, no
severity is inferred, no photo is analysed, and no cause is attributed to a
medication (sections 32, 81 and 82).
"""

import uuid
from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.enums import (
    SYMPTOM_CHANGE_STATES,
    SYMPTOM_EPISODE_STATUSES,
    SYMPTOM_PHOTO_CONTENT_TYPES,
    SYMPTOM_SOURCES,
    sql_in_list,
)
from app.models.health import year_range_constraint

#: What the user calls the symptom, and where they feel it. Free text at the
#: same length as a condition name, so the two feel like one product.
SYMPTOM_NAME_MAX_LENGTH = 120

#: One descriptive answer -- "behind both eyes", "comes and goes", "walking".
DESCRIPTOR_MAX_LENGTH = 200

#: A note in the user's own words. Long enough for a real description, short
#: enough that it cannot quietly become a medical history document.
SYMPTOM_NOTE_MAX_LENGTH = 2000

#: The severity scale (PRD 6, section 22). Anchored in the app as
#: "0 = no symptom, 10 = worst imaginable", and null wherever a number would be
#: the wrong shape of answer for the symptom.
SEVERITY_MIN, SEVERITY_MAX = 0, 10

#: A client-generated id, sent with a write so a retry cannot create the record
#: twice (PRD 6, section 61). A UUID string, with room to spare.
CLIENT_ID_MAX_LENGTH = 64

#: Where the bytes live, relative to the private media root. Never a URL, and
#: never returned to a client -- a photo is fetched through an authenticated
#: route, not by knowing its key (PRD 6, sections 33 and 63).
STORAGE_KEY_MAX_LENGTH = 200

CONTENT_TYPE_MAX_LENGTH = 60


def _one_precision_constraint(table: str, prefix: str, *suffixes: str) -> CheckConstraint:
    """At most one of the precision columns for ``prefix`` is set.

    Onset is frequently half-known: "about 2015", "on the 3rd", "some time last
    week". Each precision is its own column and only one may be filled, so a
    year never has to be stored as the 1st of January -- the same rule PRD 4
    section 31 set for diagnosis dates.
    """
    parts = " + ".join(
        f"(CASE WHEN {prefix}_{suffix} IS NOT NULL THEN 1 ELSE 0 END)"
        for suffix in suffixes
    )
    return CheckConstraint(f"({parts}) <= 1", name=f"ck_{table}_{prefix}_precision")


def _source_constraint(table: str) -> CheckConstraint:
    return CheckConstraint(
        f"source IN {sql_in_list(SYMPTOM_SOURCES)}", name=f"ck_{table}_source"
    )


def _string_list_column() -> Mapped[list[str]]:
    """A list of short free-text items, stored as JSONB.

    Associated symptoms, aggravating factors and the negated/uncertain lists
    are only ever read and written whole, so a row of JSONB is the right shape
    and a join table would be normalization for its own sake
    (PRD 6, section 9).

    Never null: an empty list means "nothing recorded", and having one
    representation of that rather than two removes a null check from every
    reader. The services always assign a fresh list rather than mutating in
    place, since SQLAlchemy does not track mutation inside a JSONB value.
    """
    return mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )


class SymptomEpisode(Base, TimestampMixin):
    """One bout of one symptom, as the person experiences it.

    Not a diagnosis and never promoted to one (PRD 6, section 6). ``name`` is
    whatever they called it -- "headache", "knee pain", "feeling wobbly" -- and
    nothing matches it against a terminology.

    ``status`` moves only when the user says so. In particular nothing infers
    ``resolved`` from silence: a symptom nobody has updated for a month is
    still active, because the alternative is Nura deciding somebody got better
    (section 10).
    """

    __tablename__ = "symptom_episodes"
    __table_args__ = (
        CheckConstraint(
            f"status IN {sql_in_list(SYMPTOM_EPISODE_STATUSES)}",
            name="ck_symptom_episodes_status",
        ),
        # Resolved means somebody said so, and when. The reverse is not forced:
        # an episode may carry the timestamp of an earlier resolution after it
        # has been reopened.
        CheckConstraint(
            "status <> 'resolved' OR resolved_at IS NOT NULL",
            name="ck_symptom_episodes_resolved_at",
        ),
        _one_precision_constraint(
            "symptom_episodes", "first_noticed", "at", "date", "year"
        ),
        year_range_constraint("first_noticed_year", "symptom_episodes"),
        _source_constraint("symptom_episodes"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    #: The person the symptom belongs to, never the account that typed it in.
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    #: As the user wrote it. Free text, never mapped to a diagnosis
    #: (PRD 6, section 13).
    name: Mapped[str] = mapped_column(String(SYMPTOM_NAME_MAX_LENGTH), nullable=False)
    #: Where it is, in their words -- "left knee", "behind both eyes". No body
    #: map is required in PRD 6 (section 14).
    body_site: Mapped[str | None] = mapped_column(String(SYMPTOM_NAME_MAX_LENGTH))
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="active", index=True
    )
    #: Exactly one of these three, or none. See ``_one_precision_constraint``.
    first_noticed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_noticed_date: Mapped[date | None] = mapped_column(Date)
    first_noticed_year: Mapped[int | None] = mapped_column(Integer)
    #: The user's own wording for when it began -- "this morning", "after
    #: exercise", "suddenly". Kept alongside the structured time rather than
    #: instead of it, because "suddenly, three days ago" is two facts and
    #: PRD 6 section 74 asks for both.
    first_noticed_text: Mapped[str | None] = mapped_column(String(DESCRIPTOR_MAX_LENGTH))
    #: Set when the user marks the episode resolved. History is kept; the
    #: episode is never deleted (PRD 6, section 37).
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: The earlier bout this one follows, for a symptom that came back
    #: (PRD 6, section 38). Clears rather than cascades: deleting an old
    #: episode must not take the current one with it.
    previous_episode_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("symptom_episodes.id", ondelete="SET NULL"),
        index=True,
    )
    source: Mapped[str] = mapped_column(
        String(24), nullable=False, server_default="manual_app"
    )

    entries: Mapped[list["SymptomEntry"]] = relationship(
        back_populates="episode",
        cascade="all, delete-orphan",
        order_by="SymptomEntry.recorded_at.desc()",
    )


class SymptomEntry(Base, TimestampMixin):
    """One observation about an episode, at one moment (PRD 6, sections 8, 11).

    The first entry is the description; every later one is a follow-up, which
    is why a follow-up needs only what has changed and never re-asks for the
    original description (PRD 6, section 47).

    The structured fields are the ones a person is asked for when describing a
    symptom to a clinician (section 12). They are all optional and several are
    irrelevant to most symptoms -- radiation means nothing for nausea -- so the
    flows skip what does not apply rather than forcing an answer (section 12).
    """

    __tablename__ = "symptom_entries"
    __table_args__ = (
        CheckConstraint(
            f"severity IS NULL OR (severity >= {SEVERITY_MIN} "
            f"AND severity <= {SEVERITY_MAX})",
            name="ck_symptom_entries_severity",
        ),
        CheckConstraint(
            f"change_state IS NULL OR change_state IN "
            f"{sql_in_list(SYMPTOM_CHANGE_STATES)}",
            name="ck_symptom_entries_change_state",
        ),
        _one_precision_constraint("symptom_entries", "onset", "at", "date"),
        _source_constraint("symptom_entries"),
        # The idempotency key (PRD 6, section 61). Scoped to the profile so two
        # people's clients cannot collide, and NULLS DISTINCT (the default) so
        # any number of rows may leave it unset.
        UniqueConstraint(
            "profile_id", "client_entry_id", name="uq_symptom_entry_client_id"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    #: Carried on the entry as well as reachable through the episode, so every
    #: query and every authorization check is "this profile's rows".
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    symptom_episode_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("symptom_episodes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    #: When the observation is about -- which is not when the request arrived.
    #: An entry saved offline may be hours old by the time it syncs
    #: (PRD 6, section 59).
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )

    #: What the person said this time. Usually the episode's name, but kept per
    #: entry because wording drifts -- "headache" one day, "pressure behind my
    #: eyes" the next -- and the drift is itself worth keeping.
    main_symptom: Mapped[str | None] = mapped_column(String(SYMPTOM_NAME_MAX_LENGTH))
    site: Mapped[str | None] = mapped_column(String(DESCRIPTOR_MAX_LENGTH))
    #: Their wording for how it started. Structured time goes in the two
    #: columns below; this keeps "suddenly" or "after exercise".
    onset_text: Mapped[str | None] = mapped_column(String(DESCRIPTOR_MAX_LENGTH))
    onset_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    onset_date: Mapped[date | None] = mapped_column(Date)
    #: "sharp", "dull", "burning". Never read diagnostically (section 16).
    character: Mapped[str | None] = mapped_column(String(DESCRIPTOR_MAX_LENGTH))
    #: Mostly relevant to pain. "stays in one place", "spreads to my back".
    radiation: Mapped[str | None] = mapped_column(String(DESCRIPTOR_MAX_LENGTH))
    #: Other things happening with it. Not diagnoses (section 18).
    associated_symptoms: Mapped[list[str]] = _string_list_column()
    #: "constant", "comes and goes", "worse at night".
    timing: Mapped[str | None] = mapped_column(String(DESCRIPTOR_MAX_LENGTH))
    #: What makes it worse and what makes it better, as *reported*. Nura never
    #: suggests what ought to help (PRD 6, sections 20 and 21).
    exacerbating_factors: Mapped[list[str]] = _string_list_column()
    relieving_factors: Mapped[list[str]] = _string_list_column()
    #: 0-10, or null where a number is the wrong shape of answer (section 22).
    severity: Mapped[int | None] = mapped_column(SmallInteger)
    #: Improving / same / worsening / unsure, as the user chose it. Never
    #: inferred from the numbers (PRD 6, sections 23 and 41).
    change_state: Mapped[str | None] = mapped_column(String(12), index=True)
    free_text_note: Mapped[str | None] = mapped_column(Text)

    #: Things explicitly denied ("no nausea"), things the user was unsure about
    #: ("I might have felt dizzy"), and things true only in a context ("only
    #: when I stand up"). Kept so a summary cannot claim more certainty than
    #: the person expressed (PRD 6, section 24).
    negated_items: Mapped[list[str]] = _string_list_column()
    uncertain_items: Mapped[list[str]] = _string_list_column()
    context_dependent_items: Mapped[list[str]] = _string_list_column()

    #: Set by the server from which flow the request came, never trusted from
    #: a client that claims it (PRD 6, section 57).
    source: Mapped[str] = mapped_column(
        String(24), nullable=False, server_default="manual_app"
    )
    #: The client's own id for this entry. Sending it again returns the
    #: existing row rather than creating a second one, which is what makes an
    #: offline retry safe (PRD 6, section 61).
    client_entry_id: Mapped[str | None] = mapped_column(String(CLIENT_ID_MAX_LENGTH))

    episode: Mapped[SymptomEpisode] = relationship(back_populates="entries")
    photos: Mapped[list["SymptomPhoto"]] = relationship(
        back_populates="entry",
        cascade="all, delete-orphan",
        order_by="SymptomPhoto.created_at",
    )


class SymptomPhoto(Base, TimestampMixin):
    """A photo the user attached to an entry (PRD 6, sections 31-35).

    The row is metadata only. The bytes live in private object storage under
    ``storage_key``, which is never returned to a client: a photo is read
    through an authenticated route that checks the profile first, so knowing an
    id -- or guessing a key -- gets nobody anything (PRD 6, section 63).

    **Nothing looks at the image.** No classification, no wound assessment, no
    rash identification, no medical computer vision of any kind
    (PRD 6, section 32).
    """

    __tablename__ = "symptom_photos"
    __table_args__ = (
        CheckConstraint(
            f"content_type IN {sql_in_list(SYMPTOM_PHOTO_CONTENT_TYPES)}",
            name="ck_symptom_photos_content_type",
        ),
        CheckConstraint("byte_size > 0", name="ck_symptom_photos_byte_size"),
        UniqueConstraint(
            "symptom_entry_id", "client_photo_id", name="uq_symptom_photo_client_id"
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
    symptom_entry_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("symptom_entries.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    #: Opaque, generated by the server. Unique so two rows can never end up
    #: sharing -- and therefore both deleting -- the same stored object.
    storage_key: Mapped[str] = mapped_column(
        String(STORAGE_KEY_MAX_LENGTH), nullable=False, unique=True
    )
    content_type: Mapped[str] = mapped_column(
        String(CONTENT_TYPE_MAX_LENGTH), nullable=False
    )
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    #: The client's own id, so a retried upload replaces nothing and adds
    #: nothing (PRD 6, section 61).
    client_photo_id: Mapped[str | None] = mapped_column(String(CLIENT_ID_MAX_LENGTH))

    entry: Mapped[SymptomEntry] = relationship(back_populates="photos")
