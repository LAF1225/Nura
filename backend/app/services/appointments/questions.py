"""Questions for the clinician (PRD 7, sections 22, 23, 39 and 48).

The whole job of this module is to keep somebody's own words intact and in the
order they put them in. Nothing rewrites a question, merges two that look
similar, or reorders by importance -- deciding which question matters most is
exactly the judgement PRD 7 section 3 says Nura does not make.

**Idempotent by client id.** A question added offline carries its own id, so a
queue may retry it as often as it likes and the list still has one
(PRD 7, section 53).

**Positions stay a clean sequence.** Deleting the second of four leaves 0, 1, 2
rather than 0, 2, 3, so a client can always send the list it is displaying and
have the order it sees be the order stored.
"""

import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Appointment, AppointmentQuestion
from app.services.errors import DomainError, NotFoundError

logger = logging.getLogger(__name__)

#: How many questions one appointment may carry. A consultation is minutes
#: long; a list past this is a different feature.
MAX_QUESTIONS = 30

#: Fields a client may change on an existing question.
EDITABLE_FIELDS = frozenset({"text", "is_answered", "answer_note"})


class QuestionNotFoundError(NotFoundError):
    """No such question on this appointment, for this profile."""


class TooManyQuestionsError(DomainError):
    status_code = 409
    code = "too_many_questions"


def _log(action: str) -> None:
    """Never the question text: it is health information (PRD 7, section 57)."""
    logger.info("appointments: %s", action)


def list_questions(db: Session, appointment_id: uuid.UUID) -> list[AppointmentQuestion]:
    """This appointment's questions, in the user's order."""
    return list(
        db.execute(
            select(AppointmentQuestion)
            .where(AppointmentQuestion.appointment_id == appointment_id)
            .order_by(AppointmentQuestion.position, AppointmentQuestion.created_at)
        )
        .scalars()
        .all()
    )


def get_question(
    db: Session,
    profile_id: uuid.UUID,
    appointment_id: uuid.UUID,
    question_id: uuid.UUID,
) -> AppointmentQuestion:
    """One question, by profile *and* appointment *and* id (PRD 7, section 51)."""
    question = db.execute(
        select(AppointmentQuestion).where(
            AppointmentQuestion.id == question_id,
            AppointmentQuestion.appointment_id == appointment_id,
            AppointmentQuestion.profile_id == profile_id,
        )
    ).scalar_one_or_none()

    if question is None:
        raise QuestionNotFoundError("That question could not be found.")
    return question


def find_by_client_id(
    db: Session, profile_id: uuid.UUID, client_question_id: str
) -> AppointmentQuestion | None:
    """The question a client already added with this id, if any (s53)."""
    return db.execute(
        select(AppointmentQuestion).where(
            AppointmentQuestion.profile_id == profile_id,
            AppointmentQuestion.client_question_id == client_question_id,
        )
    ).scalar_one_or_none()


def _next_position(db: Session, appointment_id: uuid.UUID) -> int:
    return len(list_questions(db, appointment_id))


def create_question(
    db: Session,
    appointment: Appointment,
    *,
    text: str,
    client_question_id: str | None = None,
) -> tuple[AppointmentQuestion, bool]:
    """Adds a question. Returns it, and whether this call created it.

    A replay of a known ``client_question_id`` returns the stored question with
    ``created=False`` rather than adding a second copy of it
    (PRD 7, section 53).
    """
    if client_question_id is not None:
        existing = find_by_client_id(db, appointment.profile_id, client_question_id)
        if existing is not None:
            return existing, False

    if _next_position(db, appointment.id) >= MAX_QUESTIONS:
        raise TooManyQuestionsError("There are too many questions on this appointment.")

    question = AppointmentQuestion(
        profile_id=appointment.profile_id,
        appointment_id=appointment.id,
        text=text,
        position=_next_position(db, appointment.id),
        client_question_id=client_question_id,
    )
    db.add(question)
    db.commit()
    db.refresh(question)
    _log("added a question")
    return question, True


def update_question(
    db: Session, question: AppointmentQuestion, fields: dict[str, Any]
) -> AppointmentQuestion:
    """Edits a question, or records the answer the user was given (s39)."""
    for key, value in fields.items():
        if key in EDITABLE_FIELDS:
            setattr(question, key, value)

    db.commit()
    db.refresh(question)
    _log("updated a question")
    return question


def _renumber(db: Session, appointment_id: uuid.UUID) -> None:
    """Rewrites positions as 0..n-1 in current order. Caller commits."""
    for index, question in enumerate(list_questions(db, appointment_id)):
        if question.position != index:
            question.position = index


def delete_question(db: Session, question: AppointmentQuestion) -> None:
    """Removes a question and closes the gap it left."""
    appointment_id = question.appointment_id
    db.delete(question)
    db.flush()
    _renumber(db, appointment_id)
    db.commit()
    _log("deleted a question")


def reorder_questions(
    db: Session, appointment: Appointment, order: list[uuid.UUID]
) -> list[AppointmentQuestion]:
    """Puts the questions in the order given.

    The client sends the list it is displaying, and position is taken from that
    order rather than from numbers the client has to keep consistent -- the same
    decision the Today card layout makes, for the same reason
    (PRD 3, section 20).

    Ids that are not on this appointment are ignored rather than refused, and
    anything left out keeps its relative order at the end. A reorder is a
    cosmetic action; failing it because a question was deleted on another device
    would be worse than accepting what is left.
    """
    questions = list_questions(db, appointment.id)
    by_id = {question.id: question for question in questions}

    ordered = [by_id[question_id] for question_id in order if question_id in by_id]
    ordered += [question for question in questions if question not in ordered]

    for index, question in enumerate(ordered):
        question.position = index
    db.commit()
    _log("reordered questions")
    return list_questions(db, appointment.id)
