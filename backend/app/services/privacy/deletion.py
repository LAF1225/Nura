"""Deleting one profile's data (PRD 13, sections 21-24 and 44).

Section 23 asks for one orchestrated service rather than cascade logic
scattered across routes, and there is a concrete reason this cannot simply be
``DELETE FROM profiles``.

**68 foreign keys cascade, and not one of them can reach a file.** Symptom
photos and report PDFs live in private object storage; the database knows their
keys and nothing else. A delete that let PostgreSQL do the work would leave
every photo and every PDF on disk with no row pointing at it -- unreachable
through the API, and still there. Section 24 tests for exactly that, and
section 56 of PRD 14 lists it as a release blocker. So the order is fixed:

    enumerate -> read the storage keys -> delete the rows -> delete the files

Keys are collected *before* the rows go, because afterwards there is no way to
find them. Files are deleted *after* the transaction commits, because a file
removed for a transaction that then rolled back is the one failure that cannot
be undone.

**Two steps, and the second one is not re-authentication.** Section 21 asks for
a warning, re-authentication "if already supported", explicit confirmation and
a final request. Nura verifies Supabase tokens against a JWKS endpoint and
never sees a password, so there is nothing here to re-authenticate *against* --
section 44 anticipates that and asks for strong explicit confirmation plus a
documented limitation. The limitation is documented in
``docs/architecture/privacy-security-reliability.md`` and said on the screen:
somebody holding an unlocked phone with a live session can delete the data, and
the phrase is what stops it being a mis-tap rather than what stops it being an
intruder.

**One profile, never an account.** An account may hold two profiles -- somebody
using Nura for themselves and for a parent -- and section 22's "preserve
unrelated profiles" is the rule. The account row survives even when its last
profile goes, because an account with no profile is exactly the state a new
sign-up is in, and the alternative is signing somebody out of a session whose
token is still valid for the next hour.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.models import Device, Profile
from app.services.errors import DomainError
from app.services.storage import ObjectStore

logger = logging.getLogger(__name__)

#: What the client must send back, exactly, to confirm (section 44).
#:
#: A fixed phrase the server states rather than something derived from the
#: profile's name. Derived would be guessable *and* awkward to type; the job
#: here is to make a destructive call impossible to arrive at by accident or by
#: a client replaying a request, and an exact literal does that.
CONFIRMATION_PHRASE = "DELETE MY NURA DATA"


class DeletionNotConfirmedError(DomainError):
    """The phrase was missing or did not match."""

    status_code = 422
    code = "deletion_not_confirmed"


@dataclass(frozen=True)
class DeletionInventory:
    """What a delete would remove, counted before anything is removed.

    Section 22 asks for the scope to be documented; this is the same answer
    computed from the database rather than written in prose, so the screen
    cannot describe a scope the code does not have.
    """

    profile_id: uuid.UUID
    profile_name: str
    #: Rows per table, only for tables that have any. Ordered by table name so
    #: two reads of unchanged data agree.
    rows: dict[str, int]
    #: Private files: symptom photos, report PDFs and export archives.
    file_count: int
    #: Caregiver relationships that lose access.
    caregiver_count: int
    #: Robots whose link to this profile goes.
    device_count: int
    #: Other profiles on the same account, which are untouched.
    other_profile_count: int

    @property
    def row_total(self) -> int:
        return sum(self.rows.values())


#: Tables carrying a ``profile_id``, which is how the inventory is counted.
#: Derived from the metadata rather than listed, so a table added by a later
#: PRD is counted the day it exists -- the opposite of the hand-maintained
#: lists this stage is here to fix.
def _profile_tables() -> tuple[str, ...]:
    return tuple(
        sorted(
            name
            for name, table in Base.metadata.tables.items()
            if "profile_id" in table.c
        )
    )


def _storage_keys(db: Session, profile_id: uuid.UUID) -> list[str]:
    """Every private file belonging to this profile.

    Read before the rows are deleted. Three sources, and they are listed here
    rather than discovered, because a column named ``*_key`` is not
    automatically a storage key -- ``dedupe_key`` and ``recipient_key`` are
    not, and a loop over column names would have deleted whatever those
    strings happened to address.
    """
    keys: list[str] = []
    photos = Base.metadata.tables["symptom_photos"]
    keys.extend(
        db.execute(select(photos.c.storage_key).where(photos.c.profile_id == profile_id))
        .scalars()
        .all()
    )
    reports = Base.metadata.tables["appointment_reports"]
    keys.extend(
        db.execute(
            select(reports.c.file_storage_key).where(
                reports.c.profile_id == profile_id,
                reports.c.file_storage_key.is_not(None),
            )
        )
        .scalars()
        .all()
    )
    exports = Base.metadata.tables["data_exports"]
    keys.extend(
        db.execute(
            select(exports.c.file_storage_key).where(
                exports.c.profile_id == profile_id,
                exports.c.file_storage_key.is_not(None),
            )
        )
        .scalars()
        .all()
    )
    return [key for key in keys if key]


def inventory(db: Session, profile: Profile, account_id: uuid.UUID) -> DeletionInventory:
    """What deleting this profile would remove (section 21's warning).

    A read. Nothing here changes anything, so a screen can show it, a person
    can think about it, and the same function can be asserted against after
    the delete to prove the counts reached zero.
    """
    rows: dict[str, int] = {}
    for name in _profile_tables():
        table = Base.metadata.tables[name]
        count = len(
            db.execute(
                select(table.c.profile_id).where(table.c.profile_id == profile.id)
            ).all()
        )
        if count:
            rows[name] = count

    relationships = Base.metadata.tables["caregiver_relationships"]
    caregivers = len(
        db.execute(
            select(relationships.c.id).where(
                relationships.c.profile_id == profile.id,
                relationships.c.status == "active",
            )
        ).all()
    )
    devices = len(
        db.execute(select(Device.id).where(Device.owner_profile_id == profile.id)).all()
    )
    # Profiles on *this account* that survive, not every profile in the
    # database. The number is shown on a destructive confirmation screen, so
    # "your other person is safe" has to mean the caller's other person.
    roles = Base.metadata.tables["account_profile_roles"]
    others = len(
        db.execute(
            select(roles.c.profile_id.distinct()).where(
                roles.c.account_id == account_id,
                roles.c.profile_id != profile.id,
            )
        ).all()
    )

    return DeletionInventory(
        profile_id=profile.id,
        profile_name=profile.preferred_name,
        rows=rows,
        file_count=len(_storage_keys(db, profile.id)),
        caregiver_count=caregivers,
        device_count=devices,
        other_profile_count=others,
    )


@dataclass(frozen=True)
class DeletionResult:
    """What was actually removed (section 23's completion state)."""

    profile_id: uuid.UUID
    rows_deleted: int
    files_deleted: int
    files_missing: int
    caregivers_revoked: int
    devices_unlinked: int
    completed_at: datetime


def delete_profile(
    db: Session,
    profile: Profile,
    account_id: uuid.UUID,
    store: ObjectStore,
    now: datetime,
    *,
    confirmation: str,
) -> DeletionResult:
    """Removes this profile, its data, its files and its access (section 23).

    The confirmation is checked first and compared exactly: a phrase that has
    been lower-cased or trimmed into matching is a phrase that could arrive by
    accident.
    """
    if confirmation != CONFIRMATION_PHRASE:
        raise DeletionNotConfirmedError(
            "Type the confirmation phrase exactly to delete this data."
        )

    before = inventory(db, profile, account_id)
    keys = _storage_keys(db, profile.id)

    # A device is claimed by an *account* and linked to a profile. Deleting the
    # profile must unlink it, not unclaim it: the robot on the shelf still
    # belongs to the person who bought it, and PRD 2's claim is what says so.
    # ``owner_profile_id`` is nullable precisely for the "claimed but set up
    # for nobody" state, which is where these devices land.
    devices = (
        db.execute(select(Device).where(Device.owner_profile_id == profile.id))
        .scalars()
        .all()
    )
    for device in devices:
        device.owner_profile_id = None
        device.setup_completed_at = None

    # The rows. One statement, and the cascade does the rest -- 68 foreign keys
    # reference this row or something that references it, every one of them
    # ``ON DELETE CASCADE``, which is why this service does not enumerate
    # children. What it does enumerate is the files, above, because no cascade
    # reaches those.
    db.execute(delete(Profile).where(Profile.id == profile.id))
    db.commit()

    # Files last. See the module docstring: a committed transaction is what
    # makes deleting bytes safe.
    deleted = missing = 0
    for key in keys:
        try:
            store.delete(key)
            deleted += 1
        except FileNotFoundError:
            missing += 1

    result = DeletionResult(
        profile_id=before.profile_id,
        rows_deleted=before.row_total,
        files_deleted=deleted,
        files_missing=missing,
        caregivers_revoked=before.caregiver_count,
        devices_unlinked=len(devices),
        completed_at=now,
    )
    # Counts and ids only (section 12). Not the name, not a table's contents.
    logger.info(
        "privacy.deletion complete %s",
        {
            "profile": str(result.profile_id),
            "rows": result.rows_deleted,
            "files": result.files_deleted,
            "files_missing": result.files_missing,
            "caregivers": result.caregivers_revoked,
            "devices": result.devices_unlinked,
        },
    )
    return result
