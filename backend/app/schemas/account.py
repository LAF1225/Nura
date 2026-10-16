"""Account (`/me`) request/response models (PRD 1, sections 32 and 35)."""

import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.user import REMINDER_TIME_PATTERN
from app.schemas.profile import ProfileRead

Theme = Literal["system", "light", "dark"]

#: Local wall-clock ``HH:MM``. See ``UserSettings`` for why it is not a time.
ReminderTime = Annotated[str, Field(pattern=REMINDER_TIME_PATTERN)]


class SettingsRead(BaseModel):
    """Preferences that belong to the account (PRD 1, sections 22 and 32)."""

    model_config = ConfigDict(from_attributes=True)

    theme: Theme
    language: str
    larger_text: bool
    high_contrast: bool
    reduce_motion: bool
    voice_first_preference: bool
    simplified_interface: bool
    #: Recorded only. Nura does not deliver notifications yet (PRD 3, s38).
    daily_checkin_reminder_enabled: bool
    daily_checkin_reminder_time: str | None
    # --- care notifications (PRD 9, section 48) ---
    # What the primary user wants to hear about from the people helping them.
    # Here rather than behind their own route because this is where per-account
    # preferences already live. None of them gates the in-app pending list:
    # section 48 requires an approval request to stay visible even with push off.
    notify_caregiver_messages: bool
    notify_suggestion_requests: bool
    notify_appointment_suggestions: bool
    notify_routine_suggestions: bool
    # --- safety monitoring (PRD 10, section 6) ---
    # When this person's day ends, for the "until bedtime" monitoring preset.
    # Null until they set one: section 6 says bedtime must come from an
    # explicit setting, and starting monitoring "until bedtime" without one
    # is refused rather than guessed at.
    safety_bedtime: str | None


class SettingsUpdate(BaseModel):
    """PATCH body for `/me`. Only the fields present are changed."""

    theme: Theme | None = None
    #: BCP 47 / ISO 639 style code such as "en" or "ur". Kept as a free string
    #: so adding a language never needs a migration (PRD 1, section 21).
    language: str | None = Field(default=None, min_length=2, max_length=10)
    larger_text: bool | None = None
    high_contrast: bool | None = None
    reduce_motion: bool | None = None
    voice_first_preference: bool | None = None
    simplified_interface: bool | None = None
    daily_checkin_reminder_enabled: bool | None = None
    daily_checkin_reminder_time: ReminderTime | None = None
    notify_caregiver_messages: bool | None = None
    notify_suggestion_requests: bool | None = None
    notify_appointment_suggestions: bool | None = None
    notify_routine_suggestions: bool | None = None
    safety_bedtime: ReminderTime | None = None


class AccountRead(BaseModel):
    """The signed-in account holder.

    Note this is the *account*, not necessarily the person Nura is for -- in
    assisted setup those differ. `profiles` carries the people this account
    set up (PRD 1, section 33).
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str | None
    phone: str | None
    settings: SettingsRead
    profiles: list[ProfileRead] = []
