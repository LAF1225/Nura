"""Building one export archive (PRD 13, sections 17-20, 43, 48 and 49).

**Synchronous, and that is the decision rather than a shortcut.** Section 20
allows a simple reliable synchronous implementation and section 48 says not to
add a worker that is not needed. An archive here is a few dozen kilobytes of
JSON plus whatever photos and report PDFs the person has, assembled from
queries this backend already runs on every screen. A worker would add a queue,
a state machine, a poll loop and a failure mode to a job that finishes in the
time a request takes -- so the row is ``ready`` or ``failed`` by the time
anybody can read it, and ``requested``/``generating`` stay in the vocabulary
for a build that needs them.

**Deterministic, because section 18 asks for it.** Every table is ordered
explicitly, JSON keys are written in the order ``tables.py`` declares, floats
never appear, and datetimes are ISO-8601 in UTC. The zip is built with fixed
member timestamps, so exporting unchanged data twice produces the same bytes --
which is what makes "did this archive change" a question somebody can answer.

**What goes in it is a list, not a loop**: see ``tables.py``. This module knows
how to *find* rows and how to write them; it does not decide which columns are
safe.
"""

from __future__ import annotations

import io
import json
import logging
import uuid
import zipfile
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.models import DataExport, Profile
from app.models.enums import (
    DATA_CATEGORIES,
    DATA_EXPORT_CATEGORIES,
    DATA_EXPORT_SECTIONS,
)
from app.models.privacy import EXPORT_SCHEMA_VERSION, EXPORT_TTL_HOURS
from app.services.errors import DomainError, NotFoundError
from app.services.privacy import tables as spec_module
from app.services.storage import ObjectStore
from app.services.symptoms import photos as photo_service

logger = logging.getLogger(__name__)

#: How many exports one profile may have waiting at once (section 41's
#: "existing rate limits for sensitive export endpoints", and section 53's
#: repeat-export abuse case).
#:
#: One. An export is a full copy of somebody's record; a screen that can
#: produce them faster than they expire is a way to fill a disk, and there is
#: no reason to hold two copies of the same data. Asking again while one is
#: ready returns a refusal naming the one that exists rather than silently
#: replacing it, so nobody loses a download they were part way through.
MAX_READY_EXPORTS = 1

#: Where archives live under the private media root.
STORAGE_PREFIX = "exports"

#: Every member of the zip gets this timestamp. Zip stores a modification time
#: per entry, so using "now" would make two exports of identical data differ --
#: the opposite of section 18's determinism.
FIXED_MEMBER_TIME = (1980, 1, 1, 0, 0, 0)


class ExportNotFoundError(NotFoundError):
    """No such export, for this profile."""

    code = "data_export_not_found"


class ExportExpiredError(DomainError):
    """The archive existed and its expiry has passed."""

    status_code = 410
    code = "data_export_expired"


class ExportNotReadyError(DomainError):
    """The row is ``failed``, so there is nothing to download."""

    status_code = 409
    code = "data_export_not_ready"


class TooManyExportsError(DomainError):
    """An archive is already waiting for this profile."""

    status_code = 409
    code = "data_export_already_waiting"


@dataclass(frozen=True)
class ArchiveFile:
    """One file inside the archive."""

    path: str
    data: bytes


def _log(action: str, **fields: object) -> None:
    """Ids and counts only (section 12).

    Nothing from inside the archive reaches a log line -- not a title, not a
    note, not a file name a user chose. ``files`` is a count because the names
    under ``files/`` are built from row ids, and a count is the only part worth
    reading in an operational log anyway.
    """
    logger.info("privacy.export %s %s", action, fields)


# --- writing values ---------------------------------------------------------


def _value(value: Any) -> Any:
    """One column, as JSON.

    Explicit rather than relying on a default encoder, because the default for
    an unknown type is to raise in the middle of a half-written archive. Every
    branch here is a type this schema actually stores.
    """
    if value is None or isinstance(value, bool | int | str):
        return value
    if isinstance(value, datetime):
        # Stored as ``timestamptz``; PostgreSQL hands it back in the server's
        # own zone, so normalize rather than exporting whatever the host was
        # set to.
        return value.astimezone(UTC).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, time):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, Decimal):
        # As a string, not a float: a severity or a dose must not acquire
        # binary rounding on its way out of the database.
        return str(value)
    if isinstance(value, list | tuple):
        return [_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _value(item) for key, item in value.items()}
    raise TypeError(f"no export rule for {type(value).__name__}")


def _dumps(payload: Any) -> bytes:
    """Pretty, stable JSON.

    Indented because somebody opens these files by hand, and
    ``sort_keys=False`` because the key order is the one ``tables.py``
    declares -- which reads better than alphabetical and is just as stable.
    """
    text = json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=False)
    return (text + "\n").encode("utf-8")


# --- finding rows -----------------------------------------------------------


def _table(name: str) -> Any:
    return Base.metadata.tables[name]


def _rows(
    db: Session, spec: spec_module.TableSpec, profile: Profile, account_id: uuid.UUID
) -> list[dict[str, Any]]:
    """Every row of one table that belongs to this profile.

    The joins are spelled out per scope rather than inferred. An inferred join
    is the kind of thing that quietly starts matching another profile's rows
    when a column is renamed, and this is the one feature where that would mean
    handing somebody else's record to the wrong person.
    """
    table = _table(spec.table)
    columns = [table.c[name] for name in spec.exported]
    query = select(*columns)

    if spec.scope == "profile":
        query = query.where(table.c.profile_id == profile.id)
    elif spec.scope == "self":
        query = query.where(table.c.id == profile.id)
    elif spec.scope == "account":
        query = query.where(table.c.id == account_id)
    elif spec.scope == "account_settings":
        query = query.where(table.c.user_id == account_id)
    elif spec.scope == "owned_device":
        query = query.where(table.c.owner_profile_id == profile.id)
    elif spec.scope == "via_device":
        devices = _table("devices")
        query = query.where(
            table.c.device_id.in_(
                select(devices.c.id).where(devices.c.owner_profile_id == profile.id)
            )
        )
    elif spec.scope == "via_medication_schedule":
        schedules = _table("medication_schedules")
        query = query.where(
            table.c.schedule_id.in_(
                select(schedules.c.id).where(schedules.c.profile_id == profile.id)
            )
        )
    elif spec.scope == "via_conversation":
        conversations = _table("conversations")
        query = query.where(
            table.c.conversation_id.in_(
                select(conversations.c.id).where(conversations.c.profile_id == profile.id)
            )
        )
    elif spec.scope == "via_relationship":
        relationships = _table("caregiver_relationships")
        query = query.where(
            table.c.relationship_id.in_(
                select(relationships.c.id).where(relationships.c.profile_id == profile.id)
            )
        )
    elif spec.scope == "via_thread":
        threads = _table("family_threads")
        query = query.where(
            table.c.thread_id.in_(
                select(threads.c.id).where(threads.c.profile_id == profile.id)
            )
        )
    else:  # pragma: no cover - ``none`` specs have no exported columns
        raise ValueError(f"unknown export scope {spec.scope!r}")

    query = query.order_by(*(table.c[name] for name in spec.order_by))
    return [
        {name: _value(value) for name, value in zip(spec.exported, row, strict=True)}
        for row in db.execute(query).all()
    ]


# --- media ------------------------------------------------------------------


def _media(
    db: Session, profile: Profile, store: ObjectStore
) -> tuple[list[ArchiveFile], dict[uuid.UUID, str], dict[uuid.UUID, str]]:
    """The photos and report PDFs, plus where each one landed.

    A missing object is skipped rather than failing the export. The row stays
    in the JSON with no ``archive_path``, which says "this existed and its
    bytes could not be read" -- more useful than an export nobody can produce
    because one file went astray years ago.
    """
    files: list[ArchiveFile] = []
    photo_paths: dict[uuid.UUID, str] = {}
    report_paths: dict[uuid.UUID, str] = {}

    photos = _table("symptom_photos")
    rows = db.execute(
        select(photos.c.id, photos.c.storage_key, photos.c.content_type)
        .where(photos.c.profile_id == profile.id)
        .order_by(photos.c.created_at, photos.c.id)
    ).all()
    for photo_id, key, content_type in rows:
        extension = photo_service.EXTENSIONS.get(content_type, ".bin")
        path = f"files/photos/{photo_id}{extension}"
        try:
            files.append(ArchiveFile(path=path, data=store.get(key)))
        except Exception:
            _log("media_missing", kind="photo", id=str(photo_id))
            continue
        photo_paths[photo_id] = path

    reports = _table("appointment_reports")
    rows = db.execute(
        select(reports.c.id, reports.c.file_storage_key)
        .where(
            reports.c.profile_id == profile.id,
            reports.c.file_storage_key.is_not(None),
        )
        .order_by(reports.c.generated_at, reports.c.id)
    ).all()
    for report_id, key in rows:
        path = f"files/reports/{report_id}.pdf"
        try:
            files.append(ArchiveFile(path=path, data=store.get(key)))
        except Exception:
            _log("media_missing", kind="report", id=str(report_id))
            continue
        report_paths[report_id] = path

    return files, photo_paths, report_paths


# --- building ---------------------------------------------------------------


def _sections(
    db: Session,
    profile: Profile,
    account_id: uuid.UUID,
    photo_paths: dict[uuid.UUID, str],
    report_paths: dict[uuid.UUID, str],
) -> list[ArchiveFile]:
    """One JSON file per section, in section order."""
    files: list[ArchiveFile] = []
    for section in DATA_EXPORT_SECTIONS:
        body: dict[str, Any] = {}
        for spec in spec_module.specs_for_section(section):
            rows = _rows(db, spec, profile, account_id)
            if spec.table == "symptom_photos":
                for row in rows:
                    row["archive_path"] = photo_paths.get(uuid.UUID(row["id"]))
            elif spec.table == "appointment_reports":
                for row in rows:
                    row["archive_path"] = report_paths.get(uuid.UUID(row["id"]))
            # ``self``, ``account`` and ``account_settings`` are one row each.
            # An object reads better than a list of one, and a missing row is
            # null rather than an empty list -- the distinction a reader wants.
            if spec.scope in ("self", "account", "account_settings"):
                body[spec.key] = rows[0] if rows else None
            else:
                body[spec.key] = rows
        files.append(ArchiveFile(path=f"{section}.json", data=_dumps(body)))
    return files


def _manifest(
    *,
    profile: Profile,
    generated_at: datetime,
    expires_at: datetime,
    files: list[ArchiveFile],
) -> ArchiveFile:
    """Section 19's manifest, and nothing more than section 19 asks for.

    No account id, no storage key, no provider names, no internal paths: a
    manifest is a description of the archive, and section 19 is explicit that
    it carries no secrets. ``excluded_categories`` is where ``audit`` is
    declared, so somebody reading the file can see what was left out and does
    not have to infer it from an absence.
    """
    excluded = tuple(
        category for category in DATA_CATEGORIES if category not in DATA_EXPORT_CATEGORIES
    )
    payload = {
        "generated_at": generated_at.astimezone(UTC).isoformat(),
        "profile_id": str(profile.id),
        "schema_version": EXPORT_SCHEMA_VERSION,
        "included_categories": list(DATA_EXPORT_CATEGORIES),
        "excluded_categories": [
            {"category": name, "reason": spec_module.exclusion_reason(name)}
            for name in excluded
        ],
        # The manifest counts itself, so "file_count" matches what a reader
        # sees in the archive rather than what the builder happened to loop
        # over.
        "file_count": len(files) + 1,
        "files": [item.path for item in files],
        "expires_at": expires_at.astimezone(UTC).isoformat(),
        "notes": spec_module.MANIFEST_NOTES,
    }
    return ArchiveFile(path="manifest.json", data=_dumps(payload))


def build_archive(
    db: Session,
    profile: Profile,
    account_id: uuid.UUID,
    store: ObjectStore,
    now: datetime,
) -> tuple[bytes, int]:
    """The whole zip, in memory, and how many files are in it.

    In memory because of the size: a few dozen kilobytes of JSON plus a handful
    of photos. If a deployment ever holds enough media for that to matter, this
    is the one function that changes -- which is why the caller receives bytes
    rather than a path.
    """
    media, photo_paths, report_paths = _media(db, profile, store)
    sections = _sections(db, profile, account_id, photo_paths, report_paths)
    expires_at = now + timedelta(hours=EXPORT_TTL_HOURS)
    contents = [*sections, *media]
    manifest = _manifest(
        profile=profile, generated_at=now, expires_at=expires_at, files=contents
    )

    buffer = io.BytesIO()
    # No compression of the member order and no timestamps from the clock: see
    # the module docstring on determinism.
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for item in [manifest, *contents]:
            info = zipfile.ZipInfo(item.path, date_time=FIXED_MEMBER_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            # 0o600: the archive is private, and a reader that restores
            # permissions should not widen them.
            info.external_attr = 0o600 << 16
            archive.writestr(info, item.data)
    return buffer.getvalue(), len(contents) + 1


def storage_key(export_id: uuid.UUID) -> str:
    """Where one archive lives. Built here, never supplied by a client."""
    return f"{STORAGE_PREFIX}/{export_id}.zip"


def create_export(
    db: Session,
    profile: Profile,
    account_id: uuid.UUID,
    store: ObjectStore,
    now: datetime,
) -> DataExport:
    """Builds an archive and records it (sections 18 and 43).

    A failure is stored rather than raised: section 20 has a ``failed`` state,
    and a person who asked for their data deserves to be told it did not work
    rather than receiving a 500 with nothing to look at. The exception is
    re-raised only for the refusals above, which are about the request rather
    than about the build.
    """
    waiting = ready_exports(db, profile.id, now)
    if len(waiting) >= MAX_READY_EXPORTS:
        raise TooManyExportsError(
            "An export is already waiting. Download or delete it first."
        )

    export = DataExport(
        profile_id=profile.id,
        status="failed",
        requested_at=now,
        file_count=0,
        schema_version=EXPORT_SCHEMA_VERSION,
        categories={
            "included": list(DATA_EXPORT_CATEGORIES),
            "excluded": [
                name for name in DATA_CATEGORIES if name not in DATA_EXPORT_CATEGORIES
            ],
        },
    )
    db.add(export)
    db.flush()

    try:
        data, file_count = build_archive(db, profile, account_id, store, now)
    except Exception as error:
        # The sentence is generic on purpose: section 12 forbids payload
        # contents anywhere persisted, and a serializer's message can quote a
        # value. The detail goes to the log as a type name.
        export.failure_reason = "Nura could not finish building this export."
        logger.warning(
            "privacy.export build failed: %s", type(error).__name__, exc_info=False
        )
        db.commit()
        db.refresh(export)
        return export

    key = storage_key(export.id)
    store.put(key, data)
    export.status = "ready"
    export.generated_at = now
    export.expires_at = now + timedelta(hours=EXPORT_TTL_HOURS)
    export.file_storage_key = key
    export.byte_size = len(data)
    export.file_count = file_count
    db.commit()
    db.refresh(export)
    _log("create", id=str(export.id), files=file_count, bytes=len(data))
    return export


# --- reading ----------------------------------------------------------------


def is_expired(export: DataExport, now: datetime) -> bool:
    """Whether this archive has outlived its expiry.

    Derived, and compared on every read path -- PRD 11's rule for a presentation
    applied to a file. The maintenance script flips the status and deletes the
    bytes, and nothing depends on it having run.
    """
    return export.expires_at is not None and export.expires_at <= now


def get_export(db: Session, profile_id: uuid.UUID, export_id: uuid.UUID) -> DataExport:
    """One export of one profile, or 404.

    Scoped by profile in the query rather than checked afterwards, so an id
    from somebody else's account is *not found* rather than *forbidden*
    (PRD 1, section 54).
    """
    export = db.execute(
        select(DataExport).where(
            DataExport.id == export_id, DataExport.profile_id == profile_id
        )
    ).scalar_one_or_none()
    if export is None:
        raise ExportNotFoundError("No such export.")
    return export


def list_exports(db: Session, profile_id: uuid.UUID) -> list[DataExport]:
    return list(
        db.execute(
            select(DataExport)
            .where(DataExport.profile_id == profile_id)
            .order_by(DataExport.requested_at.desc())
        )
        .scalars()
        .all()
    )


def ready_exports(db: Session, profile_id: uuid.UUID, now: datetime) -> list[DataExport]:
    """Exports that could still be downloaded right now."""
    return [
        export
        for export in list_exports(db, profile_id)
        if export.status == "ready" and not is_expired(export, now)
    ]


def read_archive(
    db: Session, export: DataExport, store: ObjectStore, now: datetime
) -> bytes:
    """The bytes, or a refusal.

    Expiry is checked here as well as in the route, because this is the
    function that touches the file: a later caller that forgets the check
    cannot serve an expired archive.
    """
    if export.status == "failed":
        raise ExportNotReadyError("That export did not finish.")
    if export.status == "expired" or is_expired(export, now):
        raise ExportExpiredError("That export has expired. Ask for a new one.")
    if export.file_storage_key is None:  # pragma: no cover - constraint forbids it
        raise ExportNotReadyError("That export did not finish.")
    return store.get(export.file_storage_key)


def delete_export(db: Session, export: DataExport, store: ObjectStore) -> None:
    """Removes the row and the bytes (section 43).

    Bytes first: a row deleted with the file still on disk is an archive
    nothing points at, which is the one outcome a privacy feature must not
    produce.
    """
    if export.file_storage_key is not None:
        # Already gone is fine: the sweep below, or a previous attempt. The row
        # going is still the right end state.
        with suppress(FileNotFoundError):
            store.delete(export.file_storage_key)
    _log("delete", id=str(export.id))
    db.delete(export)
    db.commit()


def expire_overdue(
    db: Session, store: ObjectStore, now: datetime, *, dry_run: bool = False
) -> int:
    """Marks expired archives and deletes their bytes (sections 25 and 26).

    Called by ``scripts/privacy_maintenance.py``. Nothing depends on it: the
    read path refuses an expired archive on its own, so this keeps storage
    tidy rather than keeping the rule.
    """
    overdue = [
        export
        for export in db.execute(select(DataExport).where(DataExport.status == "ready"))
        .scalars()
        .all()
        if is_expired(export, now)
    ]
    if dry_run:
        return len(overdue)
    for export in overdue:
        if export.file_storage_key is not None:
            with suppress(FileNotFoundError):
                store.delete(export.file_storage_key)
        export.status = "expired"
        export.file_storage_key = None
        export.byte_size = None
    if overdue:
        db.commit()
        _log("expire", count=len(overdue))
    return len(overdue)
