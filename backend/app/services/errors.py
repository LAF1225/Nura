"""The one shape a refused request takes.

A service raises a ``DomainError`` when a rule says no. It carries the HTTP
status the refusal deserves and a stable ``code`` that clients branch on, so
the rule and its consequence are written down in the same place -- and the
HTTP layer needs no ``if`` per rule to turn it into a response.

Messages here are safe to show a user, but the app and the firmware use their
own wording; they read ``code``, never the sentence.
"""


class DomainError(Exception):
    """A rule refused the request."""

    status_code = 400
    code = "error"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class NotFoundError(DomainError):
    """The resource does not exist, or does not belong to the caller.

    Deliberately the same answer for both: a 403 would confirm that an id
    exists, which is how someone enumerates other people's records
    (PRD 1, section 54).
    """

    status_code = 404
    code = "not_found"
