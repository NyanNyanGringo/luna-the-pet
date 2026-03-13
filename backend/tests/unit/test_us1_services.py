"""Workspace-centric тесты pet_service (US1 runtime слой)."""

from __future__ import annotations

from datetime import date

from backend.app.db.models.pet import Pet
from backend.app.db.models.workspace import Workspace
from backend.app.services.pet_service import (
    create_pet,
    get_pet_by_name,
    get_workspace_pets,
    resolve_pet_from_text,
    update_pet,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def _create_workspace(session: AsyncSession) -> Workspace:
    """Создаёт workspace для тестов pet_service."""
    workspace = Workspace(
        telegram_chat_id=-1001234567890,
        title="Service Test Workspace",
    )
    session.add(workspace)
    await session.flush()
    return workspace


class TestPetServiceWorkspaceFlow:
    """Минимальный контракт pet_service после перехода на workspace."""

    async def test_create_pet_persists_workspace_id(
        self,
        db_session: AsyncSession,
    ) -> None:
        """create_pet сохраняет питомца с переданным workspace_id."""
        workspace = await _create_workspace(db_session)
        pet = await create_pet(
            session=db_session,
            workspace_id=workspace.id,
            name="Луна",
            species="dog",
            actor_id=12345,
        )

        assert pet.workspace_id == workspace.id
        persisted_pet = await db_session.scalar(select(Pet).where(Pet.id == pet.id))
        assert persisted_pet is not None
        assert persisted_pet.workspace_id == workspace.id

    async def test_get_workspace_pets_returns_only_active(
        self,
        db_session: AsyncSession,
    ) -> None:
        """get_workspace_pets возвращает только активных питомцев workspace."""
        workspace = await _create_workspace(db_session)
        active_pet = await create_pet(
            session=db_session,
            workspace_id=workspace.id,
            name="Бобик",
            species="dog",
            actor_id=1,
        )
        inactive_pet = await create_pet(
            session=db_session,
            workspace_id=workspace.id,
            name="Шарик",
            species="dog",
            actor_id=1,
        )
        inactive_pet.is_active = False
        await db_session.flush()

        pets = await get_workspace_pets(db_session, workspace.id)
        pet_names = {pet.name for pet in pets}
        assert active_pet.name in pet_names
        assert inactive_pet.name not in pet_names

    async def test_get_pet_by_name_is_case_insensitive(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Поиск по имени в workspace не чувствителен к регистру."""
        workspace = await _create_workspace(db_session)
        await create_pet(
            session=db_session,
            workspace_id=workspace.id,
            name="Луна",
            species="dog",
            actor_id=1,
        )

        pet = await get_pet_by_name(db_session, workspace.id, "луНА")
        assert pet is not None
        assert pet.name == "Луна"

    async def test_resolve_pet_from_text_uses_workspace_scope(
        self,
        db_session: AsyncSession,
    ) -> None:
        """resolve_pet_from_text ищет питомца только внутри заданного workspace."""
        workspace = await _create_workspace(db_session)
        await create_pet(
            session=db_session,
            workspace_id=workspace.id,
            name="Луна",
            species="dog",
            actor_id=1,
        )

        resolved_pet = await resolve_pet_from_text(
            session=db_session,
            workspace_id=workspace.id,
            text="Сегодня кормили Луну и гуляли.",
        )
        assert resolved_pet is not None
        assert resolved_pet.name == "Луна"

    async def test_update_pet_changes_only_allowed_fields(
        self,
        db_session: AsyncSession,
    ) -> None:
        """update_pet меняет доменные поля и сохраняет результат."""
        workspace = await _create_workspace(db_session)
        pet = await create_pet(
            session=db_session,
            workspace_id=workspace.id,
            name="Рекс",
            species="dog",
            actor_id=1,
        )

        updated_pet = await update_pet(
            session=db_session,
            pet_id=pet.id,
            actor_id=1,
            breed="husky",
            birth_date=date(2022, 1, 1),
        )
        assert updated_pet.breed == "husky"
        assert updated_pet.birth_date == date(2022, 1, 1)
