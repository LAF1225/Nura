"""Private object storage for user media (PRD 6, sections 33, 34 and 63).

Symptom photos are the first thing Nura stores that is not a row in a table,
and they are about as sensitive as anything the product will ever hold. Three
decisions follow from that.

**There is no public URL, and no signed one either.** PRD 6 section 33 allows
either authenticated access or a signed expiring URL; this uses the first.
A signed URL is a bearer token in a query string -- it lands in logs, in
screenshots and in share sheets, and it stays valid until it expires no matter
who ends up holding it. An authenticated route re-checks the profile on every
single byte served, which is a stronger guarantee for a small amount of extra
work (section 63).

**A key is never client-supplied.** Keys are built here from ids the server
generated, and ``validate_key`` refuses anything that could climb out of the
media root. A store that accepts a caller's path is one ``../`` away from
serving the rest of the disk.

**The backend is the only reader.** ``LocalObjectStore`` writes under a
directory that is not served statically by anything, so the only way to the
bytes is through the authenticated route.

The interface is deliberately three methods. Swapping in S3, Supabase Storage
or any other private bucket later means one new class and one line in
``get_object_store`` -- no route, service or test changes.
"""

import logging
import re
import shutil
from functools import lru_cache
from pathlib import Path
from typing import Protocol

from app.core.config import get_settings

logger = logging.getLogger(__name__)

#: Object keys are built by this module, so the alphabet can be narrow: a
#: forward-slash separated path of hex, dashes and a single dot for the
#: extension. Anything else -- a backslash, a ``..``, an absolute path, a null
#: byte -- is refused before it reaches the filesystem.
KEY_PATTERN = re.compile(r"^[a-z0-9][a-z0-9/_.-]{0,198}[a-z0-9]$")


class InvalidStorageKeyError(ValueError):
    """The key is not one this module could have produced."""


class ObjectNotFoundError(FileNotFoundError):
    """The row says there should be bytes here and there are not.

    Distinguished from a missing row on purpose: a database record with no
    object behind it is a deployment problem, not a caller's mistake, and the
    route turns it into a 404 only after logging that they disagree.
    """


def validate_key(key: str) -> str:
    """Returns ``key`` if it is safe, or raises.

    Belt and braces: every caller in this codebase passes a key this module
    built, and this is what makes that still true after somebody adds a caller
    that does not.
    """
    if ".." in key or key.startswith("/") or not KEY_PATTERN.match(key):
        raise InvalidStorageKeyError("Not a valid storage key.")
    return key


class ObjectStore(Protocol):
    """Somewhere private to put bytes."""

    def put(self, key: str, data: bytes) -> None: ...

    def get(self, key: str) -> bytes: ...

    def delete(self, key: str) -> None: ...


class LocalObjectStore:
    """Files under a private directory on the machine running the backend.

    Right for development and for a single-host deployment, and enough to prove
    the whole privacy chain end to end: the route authorizes, the store hands
    back bytes, and nothing about the file is reachable any other way.

    A multi-host deployment wants a shared bucket instead, which is what the
    ``ObjectStore`` protocol is for.
    """

    def __init__(self, root: Path) -> None:
        self.root = root

    def _path(self, key: str) -> Path:
        path = (self.root / validate_key(key)).resolve()
        # Even with a validated key, confirm the resolved path is inside the
        # root. A symlink in the tree is the case the regex cannot see.
        if not path.is_relative_to(self.root.resolve()):
            raise InvalidStorageKeyError("Not a valid storage key.")
        return path

    def put(self, key: str, data: bytes) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Write beside the target and move into place, so a failed or
        # interrupted write never leaves a half-file that reads as a photo.
        staging = path.with_suffix(f"{path.suffix}.part")
        staging.write_bytes(data)
        staging.replace(path)

    def get(self, key: str) -> bytes:
        path = self._path(key)
        try:
            return path.read_bytes()
        except FileNotFoundError as error:
            raise ObjectNotFoundError(key) from error

    def delete(self, key: str) -> None:
        """Removes the object. Missing is success: deletion is idempotent."""
        self._path(key).unlink(missing_ok=True)


@lru_cache
def get_object_store() -> ObjectStore:
    """The store this deployment uses, built once per process."""
    root = get_settings().media_root_path
    root.mkdir(parents=True, exist_ok=True)
    logger.info("storage: private media root is configured")
    return LocalObjectStore(root)


def clear_media_root() -> None:
    """Empties the private media root. Development and tests only.

    Guarded by ``is_development`` in the one script that calls it, so a
    production deployment cannot lose somebody's photos to a stray import.
    """
    root = get_settings().media_root_path
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)
