"""Symptom photos: stored privately, never looked at (PRD 6, sections 31-35, 63).

The boundary this file has to hold is PRD 6 section 32's, and it is worth
stating in the plainest possible terms: **nothing in Nura analyses a symptom
photo.** No rash is classified, no wound is assessed, no infection is
identified, no model is run over the bytes. A photo is something a person keeps
for themselves and shows a clinician. This module writes it down, hands it back
to the person who owns it, and deletes it when asked.

Everything else here follows from photos being the most sensitive thing the
product stores.

**The declared type is not believed.** An upload is sniffed from its first
bytes, and a mismatch is refused rather than stored under a wrong type. This is
not a security boundary on its own -- nothing renders these images
server-side -- but it stops a file that is not an image at all from being
handed back to a phone with an image content type.

**A key is never returned to a client.** ``storage_key`` stays inside the
backend. A photo is fetched through a route that resolves the profile, the
episode and the entry first, so the only way to somebody's photo is to be them
(PRD 6, section 63).

**Deleting means deleting.** ``delete_photo`` removes the object *and* the row,
and the row only goes once the object has gone -- so a failure cannot leave a
database with no picture behind it pointing at a file nobody can reach
(PRD 6, section 35).
"""

import logging
import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Profile, SymptomEntry, SymptomPhoto
from app.services.errors import DomainError, NotFoundError
from app.services.storage import ObjectNotFoundError, ObjectStore

logger = logging.getLogger(__name__)

#: Where the bytes go, under the private media root. Two levels so a profile's
#: photos sit together, which makes a manual deletion during development
#: obvious rather than a hunt through one flat directory.
KEY_TEMPLATE = "symptom-photos/{profile_id}/{photo_id}{extension}"

#: Extension per accepted type. Only used to make a stored file recognisable;
#: nothing reads the extension back.
EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/heic": ".heic",
    "image/heif": ".heif",
}

#: The ``ftyp`` brands an HEIC/HEIF file may declare. Apple's camera writes
#: ``heic``; the others appear on images produced by other tools.
HEIF_BRANDS = frozenset(
    {
        b"heic",
        b"heix",
        b"hevc",
        b"hevx",
        b"heim",
        b"heis",
        b"hevm",
        b"hevs",
        b"mif1",
        b"msf1",
    }
)


class PhotoNotFoundError(NotFoundError):
    """No such photo on this entry, for this profile."""

    code = "symptom_photo_not_found"


class PhotoTooLargeError(DomainError):
    """Bigger than ``max_photo_bytes`` (PRD 6, section 34)."""

    status_code = 413
    code = "photo_too_large"


class UnsupportedPhotoTypeError(DomainError):
    """Not a JPEG, PNG or HEIC/HEIF, or not what it claimed to be."""

    status_code = 415
    code = "photo_type_unsupported"


class TooManyPhotosError(DomainError):
    """This entry already has as many photos as one entry may carry."""

    status_code = 409
    code = "photo_limit_reached"


def _log(action: str) -> None:
    """``symptom.photo.upload success`` -- never a key, never a path.

    PRD 6 section 62 forbids photo paths and URLs in logs as firmly as it
    forbids symptom names.
    """
    logger.info("symptom.photo.%s success", action)


def sniff_content_type(data: bytes) -> str | None:
    """The image type these bytes actually are, or None.

    Deliberately narrow: three formats, recognised from their headers. Guessing
    from a filename would be trusting the client, which is the thing this exists
    not to do.
    """
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if len(data) >= 12 and data[4:8] == b"ftyp" and data[8:12] in HEIF_BRANDS:
        # HEIC and HEIF are the same container with different brands. The whole
        # family is stored as ``image/heic``: the distinction matters to a
        # decoder, and nothing here decodes anything.
        return "image/heic"
    return None


def storage_key_for(profile_id: uuid.UUID, photo_id: uuid.UUID, content_type: str) -> str:
    """The key for one photo. Built from server-generated ids only."""
    return KEY_TEMPLATE.format(
        profile_id=profile_id,
        photo_id=photo_id,
        extension=EXTENSIONS.get(content_type, ".bin"),
    )


# --- reading ----------------------------------------------------------------


def list_photos(db: Session, entry_id: uuid.UUID) -> list[SymptomPhoto]:
    return list(
        db.execute(
            select(SymptomPhoto)
            .where(SymptomPhoto.symptom_entry_id == entry_id)
            .order_by(SymptomPhoto.created_at.asc())
        )
        .scalars()
        .all()
    )


def get_photo(
    db: Session, profile_id: uuid.UUID, entry_id: uuid.UUID, photo_id: uuid.UUID
) -> SymptomPhoto:
    """One photo, on this entry, of this profile's -- or a 404.

    All three are part of the lookup. There is no path that finds a photo by id
    and works out who owns it afterwards (PRD 6, section 53).
    """
    photo = db.execute(
        select(SymptomPhoto).where(
            SymptomPhoto.id == photo_id,
            SymptomPhoto.symptom_entry_id == entry_id,
            SymptomPhoto.profile_id == profile_id,
        )
    ).scalar_one_or_none()
    if photo is None:
        raise PhotoNotFoundError("Not found.")
    return photo


def read_photo(store: ObjectStore, photo: SymptomPhoto) -> bytes:
    """The bytes behind a row the caller has already been authorized for."""
    try:
        return store.get(photo.storage_key)
    except ObjectNotFoundError:
        # The row and the storage disagree. Worth a warning -- it means
        # something removed a file without removing its row -- but the caller
        # gets the same 404 as a photo that never existed.
        logger.warning("symptom.photo.read missing object")
        raise PhotoNotFoundError("Not found.") from None


# --- writing ----------------------------------------------------------------


def attach_photo(
    db: Session,
    store: ObjectStore,
    profile: Profile,
    entry: SymptomEntry,
    data: bytes,
    *,
    declared_type: str | None = None,
    client_photo_id: str | None = None,
    now: datetime | None = None,
) -> tuple[SymptomPhoto, bool]:
    """Stores a photo against an entry. Returns it and whether it is new.

    False for a replay of a ``client_photo_id`` already attached, which is what
    makes a retried upload from a queue safe -- the same guarantee entries get,
    for the same reason (PRD 6, section 61).

    The object is written before the row is committed. If the write fails there
    is no row; if the commit fails there is an orphaned object, which costs disk
    and reveals nothing. The other order would produce a row pointing at
    nothing, which is a photo the user can see listed and never open.
    """
    settings = get_settings()

    if client_photo_id:
        existing = db.execute(
            select(SymptomPhoto).where(
                SymptomPhoto.symptom_entry_id == entry.id,
                SymptomPhoto.client_photo_id == client_photo_id,
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing, False

    if not data:
        raise UnsupportedPhotoTypeError("That file is empty.")
    if len(data) > settings.max_photo_bytes:
        raise PhotoTooLargeError("That photo is too large to upload.")

    actual = sniff_content_type(data)
    if actual is None:
        raise UnsupportedPhotoTypeError("Nura can attach JPEG, PNG and HEIC photos.")
    if declared_type is not None:
        declared = declared_type.split(";")[0].strip().lower()
        heif_family = {"image/heic", "image/heif"}
        # Either HEIF label is accepted for either brand; everything else has
        # to match what the bytes actually say.
        agrees = declared == actual or (declared in heif_family and actual in heif_family)
        if not agrees:
            raise UnsupportedPhotoTypeError("That file is not the type it claims to be.")

    if len(list_photos(db, entry.id)) >= settings.max_photos_per_entry:
        raise TooManyPhotosError(
            f"An update can have up to {settings.max_photos_per_entry} photos."
        )

    photo_id = uuid.uuid4()
    key = storage_key_for(profile.id, photo_id, actual)
    store.put(key, data)

    photo = SymptomPhoto(
        id=photo_id,
        profile_id=profile.id,
        symptom_entry_id=entry.id,
        storage_key=key,
        content_type=actual,
        byte_size=len(data),
        client_photo_id=client_photo_id,
    )
    db.add(photo)
    if now is not None:
        entry.episode.updated_at = now
    db.commit()
    db.refresh(photo)
    _log("upload")
    return photo, True


def delete_photo(db: Session, store: ObjectStore, photo: SymptomPhoto) -> None:
    """Removes the stored object and then the row (PRD 6, section 35)."""
    store.delete(photo.storage_key)
    db.delete(photo)
    db.commit()
    _log("delete")


def purge_objects(store: ObjectStore, photos: list[SymptomPhoto]) -> None:
    """Removes stored objects for rows a cascade is about to delete.

    Called before deleting an entry or an episode. The database cascade removes
    the rows; nothing in the database can reach into storage, so this has to
    happen explicitly or the bytes would outlive the record pointing at them.
    """
    for photo in photos:
        store.delete(photo.storage_key)
    if photos:
        _log("purge")


def photos_for_episode(db: Session, episode_id: uuid.UUID) -> list[SymptomPhoto]:
    """Every photo under an episode, through its entries."""
    return list(
        db.execute(
            select(SymptomPhoto)
            .join(SymptomEntry, SymptomEntry.id == SymptomPhoto.symptom_entry_id)
            .where(SymptomEntry.symptom_episode_id == episode_id)
        )
        .scalars()
        .all()
    )
