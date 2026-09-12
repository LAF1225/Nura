"""Profile request/response models (PRD 1, sections 18-21)."""

import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import AGE_RANGES, PROFILE_ROLES

AgeRange = Literal[
    "under_18", "18_29", "30_44", "45_59", "60_74", "75_plus", "prefer_not_to_say"
]
ProfileRole = Literal["self", "setup_helper"]

# Guards against the Literal types above drifting from the database CHECK
# constraints, which are generated from these same tuples.
assert set(AGE_RANGES) == set(AgeRange.__args__)  # type: ignore[attr-defined]
assert set(PROFILE_ROLES) == set(ProfileRole.__args__)  # type: ignore[attr-defined]

#: Preferred name is the one genuinely required field (PRD 1, section 19).
PreferredName = Annotated[str, Field(min_length=1, max_length=64)]


class ProfileBase(BaseModel):
    age_range: AgeRange | None = None
    country_region: str | None = Field(default=None, min_length=2, max_length=2)
    pronouns: str | None = Field(default=None, max_length=32)

    @field_validator("country_region")
    @classmethod
    def _uppercase_region(cls, value: str | None) -> str | None:
        """Stores ISO 3166-1 alpha-2 consistently, so "gb" and "GB" match."""
        return value.upper() if value else value


class ProfileCreate(ProfileBase):
    preferred_name: PreferredName
    #: How the signed-in account relates to this person. Defaults to `self`;
    #: assisted setup passes `setup_helper` when creating the other person's
    #: profile (PRD 1, section 28).
    role: ProfileRole = "self"


class ProfileUpdate(ProfileBase):
    """Every field optional -- a PATCH only changes what it names."""

    preferred_name: PreferredName | None = None


class ProfileRead(ProfileBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    preferred_name: str
    avatar_url: str | None = None
    #: The signed-in account's relationship to this profile. Populated by the
    #: endpoint from the join row, not stored on the profile itself.
    role: ProfileRole | None = None


def profile_to_read(profile: object, role: str | None) -> ProfileRead:
    """Combines a Profile row with the caller's role for it.

    ``role`` lives on the join table rather than the profile, so it has to be
    supplied alongside rather than read off the model.
    """
    read = ProfileRead.model_validate(profile)
    return read.model_copy(update={"role": role})
