"""Logging setup (PRD 0, section 21).

A thin wrapper over the standard library rather than a new abstraction: modules
call ``logging.getLogger(__name__)`` as usual and get debug/info/warning/error.

Never log passwords, authentication tokens, medical records or private
conversations.
"""

import logging


def configure_logging(*, development: bool) -> None:
    """Configures root logging once, at application startup."""
    logging.basicConfig(
        level=logging.DEBUG if development else logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )
