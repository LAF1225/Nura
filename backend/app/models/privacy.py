"""One table: an export somebody asked for (PRD 13, sections 17-20 and 47).

PRD 13 adds almost no schema, and the reason is section 47's instruction read
against what the two features actually need.

**An export needs a row, because it has a file and an expiry.** The archive
lives in private storage like a report PDF does, and something has to say where
it is, when it stops being downloadable and what went into it -- so the
manifest's own claims can be checked against the row that produced them.

**Deletion needs no row at all.** Section 47 makes ``deletion_requests``
conditional on deletion being asynchronous, and it is not: the whole operation
is one transaction plus a file sweep, finished before the response is written.
A table recording that somebody asked to be deleted, kept after they were
deleted, would be the one piece of their data that outlived the request -- which
is a strange thing to build into a deletion feature. The confirmation step is a
second request carrying a phrase the first one handed out, not a stored token.

**Expiry is applied on read, as PRD 11 does it.** ``expires_at`` is a column
and the download route refuses a row whose expiry has passed, whatever the
``status`` says. The maintenance script then flips the row to ``expired`` and
deletes the bytes. Both agree because the route never trusts the status alone,
which is what stops a worker that has not run from turning into a file served
past its expiry.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.enums import DATA_EXPORT_STATUSES, sql_in_list
from app.models.profile import Profile
from app.models.symptom import STORAGE_KEY_MAX_LENGTH

#: Bumped when the archive's shape changes, and written into the manifest
#: (section 19). A reader that understands version 1 can say so rather than
#: guessing at a file it does not recognise.
EXPORT_SCHEMA_VERSION = 1

#: How long a finished archive stays downloadable (section 18: temporary).
#:
#: Long enough to notice the export finished and fetch it, short enough that a
#: forgotten archive is not sitting in storage a month later. Section 25's
#: retention document states the same number, from this constant.
EXPORT_TTL_HOURS = 24

#: Why an export failed, in a sentence safe to show somebody. Not a traceback:
#: section 12 forbids payload contents in anything persisted, and a stack trace
#: from a serializer is the one place a record's value could end up.
FAILURE_REASON_MAX_LENGTH = 200


class DataExport(Base, TimestampMixin):
    """One archive of one profile's data.

    Owned by a profile and cascading with it, like everything else PRD 4
    onwards added. That cascade matters more here than usual: deleting a
    profile must not leave an export of it behind, and the file sweep in
    ``services.privacy.deletion`` is what removes the bytes the cascade cannot
    reach.
    """

    __tablename__ = "data_exports"
    __table_args__ = (
        CheckConstraint(
            f"status IN {sql_in_list(DATA_EXPORT_STATUSES)}",
            name="ck_data_exports_status",
        ),
        # A row that says it is ready has a file and an expiry behind it. The
        # same shape as ``ck_appointment_reports_ready_file``, and for the same
        # reason: an offer to download something the storage layer cannot find
        # is worse than an honest failure.
        CheckConstraint(
            "status <> 'ready' OR "
            "(file_storage_key IS NOT NULL AND expires_at IS NOT NULL)",
            name="ck_data_exports_ready_file",
        ),
        # And a row that failed has no file. Written as its own constraint
        # rather than folded into the one above, so the message a developer
        # gets names which half is wrong.
        CheckConstraint(
            "status <> 'failed' OR file_storage_key IS NULL",
            name="ck_data_exports_failed_no_file",
        ),
        CheckConstraint(
            "byte_size IS NULL OR byte_size > 0", name="ck_data_exports_byte_size"
        ),
        CheckConstraint("file_count >= 0", name="ck_data_exports_file_count"),
        CheckConstraint("schema_version >= 1", name="ck_data_exports_schema_version"),
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
    status: Mapped[str] = mapped_column(String(12), nullable=False)
    #: When the person asked. Distinct from ``created_at`` only in meaning, and
    #: worth its own column because section 19 puts a generation time in the
    #: manifest and a reader should be able to check it against the row.
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: Null for a failed export, which has nothing to expire.
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: Where the zip lives, relative to the private media root. Never a URL and
    #: never returned to a client -- the archive is read through an
    #: authenticated route, exactly as a report PDF and a symptom photo are
    #: (sections 18 and 27).
    file_storage_key: Mapped[str | None] = mapped_column(
        String(STORAGE_KEY_MAX_LENGTH), unique=True
    )
    byte_size: Mapped[int | None] = mapped_column(Integer)
    #: Files inside the archive, including the manifest (section 19).
    file_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    schema_version: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=str(EXPORT_SCHEMA_VERSION)
    )
    #: What went in and what did not, as the manifest states it (section 19).
    #: Stored so the row can answer "what was in that archive" after the bytes
    #: have expired -- which is the question somebody asks when they are
    #: deciding whether to export again.
    categories: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    failure_reason: Mapped[str | None] = mapped_column(String(FAILURE_REASON_MAX_LENGTH))

    profile: Mapped[Profile] = relationship()
