"""
Re-export всех моделей для Alembic autodiscovery и удобного импорта.

Все модели регистрируются в Base.metadata при импорте этого пакета.
"""

from backend.app.db.models.audit import ChangeLog
from backend.app.db.models.documents import Document
from backend.app.db.models.family import ConversationState
from backend.app.db.models.health import (
    EmergencyProfile,
    HeatCycle,
    Measurement,
    MedicalRecord,
    Medication,
    MoodLog,
    Note,
    Vaccination,
    VetVisit,
    WeightRecord,
)
from backend.app.db.models.nutrition import DietRecord, FeedingEntry
from backend.app.db.models.pet import Pet
from backend.app.db.models.workspace import (
    Workspace,
    WorkspaceMember,
    WorkspaceSettings,
)

__all__ = [
    "ChangeLog",
    "ConversationState",
    "DietRecord",
    "Document",
    "EmergencyProfile",
    "FeedingEntry",
    "HeatCycle",
    "Measurement",
    "MedicalRecord",
    "Medication",
    "MoodLog",
    "Note",
    "Pet",
    "Vaccination",
    "VetVisit",
    "WeightRecord",
    "Workspace",
    "WorkspaceMember",
    "WorkspaceSettings",
]
