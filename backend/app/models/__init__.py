"""Model package.

Importing every model here means ``Base.metadata`` is fully populated by a
single ``import app.models``, which is what Alembic relies on to autogenerate
migrations.
"""

from app.models.checkin import DailyCheckIn
from app.models.dashboard import DashboardPreference
from app.models.device import DEVICE_TYPE_XIAO_ESP32S3, Device, ProvisioningSession
from app.models.profile import AccountProfileRole, Profile
from app.models.user import User, UserSettings

__all__ = [
    "DEVICE_TYPE_XIAO_ESP32S3",
    "AccountProfileRole",
    "DailyCheckIn",
    "DashboardPreference",
    "Device",
    "Profile",
    "ProvisioningSession",
    "User",
    "UserSettings",
]
