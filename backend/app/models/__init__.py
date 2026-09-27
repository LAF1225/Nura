"""Model package.

Importing every model here means ``Base.metadata`` is fully populated by a
single ``import app.models``, which is what Alembic relies on to autogenerate
migrations.
"""

from app.models.checkin import DailyCheckIn
from app.models.dashboard import DashboardPreference
from app.models.device import DEVICE_TYPE_XIAO_ESP32S3, Device, ProvisioningSession
from app.models.health import (
    Allergy,
    Clinician,
    HealthRecord,
    MedicalCondition,
    MedicalNote,
    Medication,
    Procedure,
)
from app.models.medication import (
    MedicationDose,
    MedicationSchedule,
    MedicationScheduleTime,
    MedicationSupply,
)
from app.models.profile import AccountProfileRole, Profile
from app.models.symptom import SymptomEntry, SymptomEpisode, SymptomPhoto
from app.models.user import User, UserSettings

__all__ = [
    "DEVICE_TYPE_XIAO_ESP32S3",
    "AccountProfileRole",
    "Allergy",
    "Clinician",
    "DailyCheckIn",
    "DashboardPreference",
    "Device",
    "HealthRecord",
    "MedicalCondition",
    "MedicalNote",
    "Medication",
    "MedicationDose",
    "MedicationSchedule",
    "MedicationScheduleTime",
    "MedicationSupply",
    "Procedure",
    "Profile",
    "ProvisioningSession",
    "SymptomEntry",
    "SymptomEpisode",
    "SymptomPhoto",
    "User",
    "UserSettings",
]
