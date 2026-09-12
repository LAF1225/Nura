"""Declarative base and shared column mixins."""

from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for every model. Alembic reads metadata from here."""


class TimestampMixin:
    """``created_at`` / ``updated_at``, maintained by the database.

    Using server-side defaults means timestamps are correct even when rows are
    inserted by a migration or by hand in psql, not just through the app.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
