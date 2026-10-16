"""What Nura brings up first (PRD 8, sections 34-36, 66-68 and 95).

Every prompt here is a fact the app already holds: an appointment tomorrow
that has nothing prepared, a check-in not done, a medication running low.
Section 35 is explicit that these must come from existing deterministic data
and that Nura must not invent proactive medical concerns -- so there is no
model call in this file, and nothing here reads a symptom severity or a
diagnosis. The three prompts below are the three the PRD lists, and adding a
fourth would mean finding a fourth fact, not writing a fourth sentence.

**A dismissal sticks** (section 36). Waving away tomorrow's preparation nudge
writes a row against that appointment, so it stops for that appointment and
for nothing else.

**Modes turn it down, not off by halves.** Focus and Sleep suppress the
optional prompts; Privacy suppresses all of them (sections 66-68 and 95).
Medication and appointment *reminders* are untouched by any of this -- they
are notifications the user configured in PRD 5 and PRD 7, they are delivered
by the phone, and section 67 says plainly not to suppress important reminders
without explicit logic.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AssistantPromptDismissal
from app.services import checkins as checkin_service
from app.services.appointments import appointments as appointment_service
from app.services.appointments import summary as appointment_summary
from app.services.medications import summary as medication_summary

#: How many prompts each level allows at once (section 34). Off means none;
#: the rest are a ceiling, not a target -- a quiet day produces none at any
#: level.
MAX_PROMPTS = {"off": 0, "low": 1, "medium": 2, "high": 3}

#: Modes that suppress every optional prompt (sections 68 and 95).
SILENT_MODES = ("privacy",)

#: Modes that keep only the most useful one (sections 66 and 67).
QUIET_MODES = ("focus", "sleep")


@dataclass(frozen=True)
class Prompt:
    """One thing Nura could raise, and what dismissing it would silence."""

    kind: str
    #: Which appointment, which day. Scopes the dismissal (section 36).
    subject_key: str
    text: str
    #: Where the app should go if the user takes it up.
    route: str | None = None
    action_label: str | None = None


def _dismissed(db: Session, profile_id: uuid.UUID) -> set[tuple[str, str]]:
    rows = (
        db.execute(
            select(
                AssistantPromptDismissal.prompt_kind,
                AssistantPromptDismissal.subject_key,
            ).where(AssistantPromptDismissal.profile_id == profile_id)
        )
        .tuples()
        .all()
    )
    return {(kind, subject) for kind, subject in rows}


def dismiss(
    db: Session,
    profile_id: uuid.UUID,
    *,
    kind: str,
    subject_key: str,
    now: datetime,
) -> None:
    """Records that this prompt has been waved away.

    Idempotent: dismissing the same thing twice leaves one row, because the
    unique constraint says so and a second dismissal means the same thing as
    the first.
    """
    existing = db.execute(
        select(AssistantPromptDismissal).where(
            AssistantPromptDismissal.profile_id == profile_id,
            AssistantPromptDismissal.prompt_kind == kind,
            AssistantPromptDismissal.subject_key == subject_key,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return
    db.add(
        AssistantPromptDismissal(
            profile_id=profile_id,
            prompt_kind=kind,
            subject_key=subject_key,
            dismissed_at=now,
        )
    )
    db.commit()


def _candidates(
    db: Session, profile_id: uuid.UUID, local_date: date, now: datetime
) -> list[Prompt]:
    """Every prompt the data currently justifies, most useful first."""
    prompts: list[Prompt] = []

    appointments = appointment_summary.build_summary(db, profile_id, local_date, now)
    for snapshot in appointments.important:
        if snapshot.preparation_complete:
            continue
        appointment = snapshot.appointment
        when = "today" if snapshot.is_today else "tomorrow"
        prompts.append(
            Prompt(
                kind="appointment_preparation",
                subject_key=str(appointment.id),
                text=(
                    f"You have an appointment {when} — {appointment.title}. "
                    "Would you like to prepare for it?"
                ),
                route=f"/appointments/{appointment.id}/prepare",
                action_label="Prepare now",
            )
        )

    if checkin_service.get_checkin(db, profile_id, local_date) is None:
        prompts.append(
            Prompt(
                kind="daily_checkin",
                subject_key=local_date.isoformat(),
                text="You haven't completed today's check-in yet.",
                route="/",
                action_label="Check in",
            )
        )

    low = medication_summary.low_supply(db, profile_id)
    if low:
        # One prompt however many are low: a list of three running out is
        # still one thing to go and do (section 36's "not excessive").
        prompts.append(
            Prompt(
                kind="medication_supply",
                subject_key=local_date.isoformat(),
                text=(
                    "Your medication supply is running low."
                    if len(low) == 1
                    else f"{len(low)} of your medications are running low."
                ),
                route="/medications/supply",
                action_label="Check supply",
            )
        )

    return prompts


def build(
    db: Session,
    profile_id: uuid.UUID,
    *,
    local_date: date,
    now: datetime,
    level: str,
    mode: str = "normal",
    serious: bool = False,
) -> list[Prompt]:
    """The prompts Nura may raise right now.

    Suppressed entirely in a serious moment (section 69): somebody who has
    just described chest pain is not being asked about their check-in.
    """
    if serious or mode in SILENT_MODES:
        return []

    allowed = MAX_PROMPTS.get(level, 0)
    if mode in QUIET_MODES:
        allowed = min(allowed, 1)
    if allowed == 0:
        return []

    dismissed = _dismissed(db, profile_id)
    kept = [
        prompt
        for prompt in _candidates(db, profile_id, local_date, now)
        if (prompt.kind, prompt.subject_key) not in dismissed
    ]
    return kept[:allowed]


def has_upcoming_appointment(db: Session, profile_id: uuid.UUID, now: datetime) -> bool:
    """Whether there is anything to prepare for, for the Nura home screen."""
    return appointment_service.next_upcoming(db, profile_id, now=now) is not None
