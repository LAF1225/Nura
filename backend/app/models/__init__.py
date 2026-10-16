"""Model package.

Importing every model here means ``Base.metadata`` is fully populated by a
single ``import app.models``, which is what Alembic relies on to autogenerate
migrations.
"""

from app.models.appointment import (
    Appointment,
    AppointmentQuestion,
    AppointmentReport,
)
from app.models.assistant import (
    AssistantMemory,
    AssistantPreferences,
    AssistantPromptDismissal,
    Conversation,
    ConversationMessage,
)
from app.models.caregiver import (
    CaregiverAuditEvent,
    CaregiverPermission,
    CaregiverRelationship,
    CaregiverSuggestion,
    EmergencyContact,
    FamilyMessage,
    FamilyThread,
)
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
from app.models.privacy import DataExport
from app.models.productivity import (
    Alarm,
    GeneralReminder,
    GeneralReminderOccurrence,
    Routine,
    RoutineRun,
    RoutineStep,
    RoutineStepCompletion,
    Task,
)
from app.models.profile import AccountProfileRole, Profile
from app.models.robot import (
    DeviceCapability,
    DevicePresentation,
    DevicePresentationPreferences,
)
from app.models.safety import (
    SafetyAlert,
    SafetyAuditEvent,
    SafetyEscalationAttempt,
    SafetyEvent,
    SafetyMonitoringSession,
)
from app.models.symptom import SymptomEntry, SymptomEpisode, SymptomPhoto
from app.models.user import User, UserSettings

__all__ = [
    "DEVICE_TYPE_XIAO_ESP32S3",
    "AccountProfileRole",
    "Alarm",
    "Allergy",
    "Appointment",
    "AppointmentQuestion",
    "AppointmentReport",
    "AssistantMemory",
    "AssistantPreferences",
    "AssistantPromptDismissal",
    "CaregiverAuditEvent",
    "CaregiverPermission",
    "CaregiverRelationship",
    "CaregiverSuggestion",
    "Clinician",
    "Conversation",
    "ConversationMessage",
    "DailyCheckIn",
    "DataExport",
    "DashboardPreference",
    "Device",
    "DeviceCapability",
    "DevicePresentation",
    "DevicePresentationPreferences",
    "EmergencyContact",
    "FamilyMessage",
    "FamilyThread",
    "GeneralReminder",
    "GeneralReminderOccurrence",
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
    "Routine",
    "RoutineRun",
    "RoutineStep",
    "RoutineStepCompletion",
    "SafetyAlert",
    "SafetyAuditEvent",
    "SafetyEscalationAttempt",
    "SafetyEvent",
    "SafetyMonitoringSession",
    "SymptomEntry",
    "SymptomEpisode",
    "SymptomPhoto",
    "Task",
    "User",
    "UserSettings",
]
