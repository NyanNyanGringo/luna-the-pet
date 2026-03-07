"""
Re-export всех моделей для Alembic autodiscovery и удобного импорта.

Все модели регистрируются в Base.metadata при импорте этого пакета.
"""

from backend.app.db.models.audit import ChangeLog
from backend.app.db.models.family import (
    Family,
    FamilyInvite,
    FamilyMember,
    FamilySettings,
    OAuthCredential,
    family_pet,
)
from backend.app.db.models.pet import Pet

__all__ = [
    "ChangeLog",
    "Family",
    "FamilyInvite",
    "FamilyMember",
    "FamilySettings",
    "OAuthCredential",
    "Pet",
    "family_pet",
]
