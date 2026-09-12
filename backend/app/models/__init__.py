"""Model package.

Importing every model here means ``Base.metadata`` is fully populated by a
single ``import app.models``, which is what Alembic relies on to autogenerate
migrations.
"""

from app.models.device import DEVICE_TYPE_XIAO_ESP32S3, Device
from app.models.user import User, UserSettings

__all__ = ["DEVICE_TYPE_XIAO_ESP32S3", "Device", "User", "UserSettings"]
