"""
Re-export всех моделей для Alembic autodiscovery и удобного импорта.

Все модели регистрируются в Base.metadata при импорте этого пакета.
"""

from backend.app.db.models.audit import ChangeLog
from backend.app.db.models.family import (
    ConversationState,
    Family,
    FamilyInvite,
    FamilyMember,
    FamilySettings,
    OAuthCredential,
    family_pet,
)
from backend.app.db.models.health import (
    EmergencyProfile,
    MedicalRecord,
    Medication,
    Note,
    Vaccination,
    WeightRecord,
)
from backend.app.db.models.nutrition import DietRecord, FeedingEntry
from backend.app.db.models.pet import Pet

__all__ = [
    "ChangeLog",
    "ConversationState",
    "DietRecord",
    "EmergencyProfile",
    "Family",
    "FamilyInvite",
    "FamilyMember",
    "FamilySettings",
    "FeedingEntry",
    "MedicalRecord",
    "Medication",
    "Note",
    "OAuthCredential",
    "Pet",
    "Vaccination",
    "WeightRecord",
    "family_pet",
]
