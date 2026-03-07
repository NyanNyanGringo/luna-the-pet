"""
Базовый класс SQLAlchemy DeclarativeBase для всех моделей проекта.

Определяет MetaData с naming conventions для автогенерации имён
constraints и индексов. Все модели наследуются от Base.

Дополнительно регистрирует event listener, который применяет
column defaults на Python-уровне при создании экземпляров моделей
(без этого mapped_column(default=...) работает только при INSERT).
"""

from typing import Any

from sqlalchemy import MetaData, event
from sqlalchemy.orm import DeclarativeBase

# Соглашения именования для constraints и индексов.
# Alembic использует эти шаблоны при автогенерации миграций.
NAMING_CONVENTION: dict[str, str] = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Базовый класс для всех SQLAlchemy-моделей проекта.

    Содержит MetaData с naming conventions для единообразного именования
    constraints (PK, FK, UQ, CK) и индексов (IX) во всех таблицах.

    При создании экземпляров моделей скалярные column defaults
    автоматически применяются на Python-уровне (event 'init').
    """

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


@event.listens_for(Base, "init", propagate=True)
def _apply_column_defaults(
    target: Base,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> None:
    """Применяет скалярные column defaults при создании экземпляра модели.

    SQLAlchemy mapped_column(default=...) устанавливает значение только при INSERT.
    Этот listener дублирует скалярные defaults на Python-уровне, чтобы атрибуты
    были доступны сразу после вызова конструктора (до flush/commit).

    Аргументы:
        target: создаваемый экземпляр модели
        args: позиционные аргументы конструктора
        kwargs: именованные аргументы конструктора

    Побочные эффекты:
        Устанавливает атрибуты экземпляра для полей с скалярными defaults,
        если они не были явно переданы в конструктор.
    """
    for attribute in target.__mapper__.column_attrs:
        column = attribute.columns[0]
        attribute_name = attribute.key

        # Пропускаем атрибуты, явно переданные в конструктор
        if attribute_name in kwargs:
            continue

        # Применяем только скалярные defaults (не callable, не SQL-выражения)
        if column.default is not None and column.default.is_scalar:
            setattr(target, attribute_name, column.default.arg)
