"""Expired export archives, swept (PRD 13, sections 25, 26 and 48).

**Nothing depends on this running.** Section 48 says not to add a worker that
is not needed, and the rule this script enforces is already enforced without
it: ``export.read_archive`` compares the expiry on every read, so an archive
past its expiry cannot be downloaded whether or not anybody has swept it. What
the sweep does is delete the bytes and mark the row, so a forgotten archive is
not sitting in private storage a month later.

That makes it the same kind of job as ``robot_maintenance.py`` and the opposite
of ``safety_maintenance.py``, which is load-bearing: PRD 10's escalation
deadlines only fire if something runs. Worth stating plainly, because "we have
a maintenance script" means two very different things in this repository.

Usage, from the ``backend`` directory with the virtualenv active::

    python -m scripts.privacy_maintenance
    python -m scripts.privacy_maintenance --dry-run

A dry run counts what would go and touches nothing, which is the version worth
running first on anything that deletes files.
"""

import argparse
from datetime import UTC, datetime

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.models import DataExport
from app.services.privacy import export as export_service
from app.services.storage import get_object_store


def open_session() -> Session:
    settings = get_settings()
    engine = create_engine(settings.database_url, future=True)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Delete expired data-export archives and mark their rows."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="count what would be removed, and change nothing",
    )
    args = parser.parse_args()

    now = datetime.now(UTC)
    db = open_session()
    try:
        store = get_object_store()
        ready = len(
            db.execute(select(DataExport.id).where(DataExport.status == "ready")).all()
        )
        count = export_service.expire_overdue(db, store, now, dry_run=args.dry_run)
        verb = "would expire" if args.dry_run else "expired"
        print(f"{verb} {count} of {ready} ready export(s)")
        if count == 0:
            # Said explicitly, because "nothing happened" is the expected
            # result most of the time and silence reads like a failure.
            print("nothing to do -- no archive has passed its expiry")
    finally:
        db.close()


if __name__ == "__main__":
    main()
