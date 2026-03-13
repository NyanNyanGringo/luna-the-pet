"""
Re-export всех моделей для Alembic autodiscovery и удобного импорта.

Все модели регистрируются в Base.metadata при импорте этого пакета.
"""

from backend.app.db.models.audit import ChangeLog
from backend.app.db.models.family import (
    ConversationState,
    OAuthCredential,
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
from backend.app.db.models.workspace import (
    Workspace,
    WorkspaceMember,
    WorkspaceSettings,
)

__all__ = [
    "ChangeLog",
    "ConversationState",
    "DietRecord",
    "EmergencyProfile",
    "FeedingEntry",
    "MedicalRecord",
    "Medication",
    "Note",
    "OAuthCredential",
    "Pet",
    "Vaccination",
    "WeightRecord",
    "Workspace",
    "WorkspaceMember",
    "WorkspaceSettings",
]
