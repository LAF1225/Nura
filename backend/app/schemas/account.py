"""Account (`/me`) request/response models (PRD 1, sections 32 and 35)."""

import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.profile import ProfileRead

Theme = Literal["system", "light", "dark"]


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
