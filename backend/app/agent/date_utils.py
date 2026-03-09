"""Утилиты runtime-парсинга дат для agent/tool path US1."""

from __future__ import annotations

import datetime
import logging
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

_RELATIVE_DATE_OFFSETS: dict[str, int] = {
    "сегодня": 0,
    "завтра": 1,
    "вчера": -1,
    "today": 0,
    "tomorrow": 1,
    "yesterday": -1,
}


class InvalidRuntimeDateError(ValueError):
    """Ошибка парсинга runtime-значения даты для tool/date field."""


def current_date_in_timezone(timezone: str) -> datetime.date:
    """Возвращает текущую календарную дату в указанной IANA-таймзоне."""
    timezone_info = _resolve_timezone(timezone)
    return datetime.datetime.now(tz=timezone_info).date()


def normalize_relative_date(
    text: str,
    timezone: str,
    family_today: datetime.date | None = None,
) -> datetime.date | None:
    """Преобразует текстовое описание относительной даты в datetime.date.

    Поддерживаются ключевые слова:
    - ru: сегодня, вчера, завтра
    - en: today, yesterday, tomorrow

    Аргументы:
        text: текст с описанием даты
        timezone: IANA-таймзона (например, "UTC", "Europe/Moscow")

    Возвращает:
        datetime.date | None: дата или None, если текст не распознан
    """
    normalized_text = text.strip().lower()
    offset_days = _RELATIVE_DATE_OFFSETS.get(normalized_text)
    if offset_days is None:
        return None

    base_date = family_today or current_date_in_timezone(timezone)
    return base_date + datetime.timedelta(days=offset_days)


def parse_runtime_date(
    value: str,
    timezone: str,
    field_name: str,
    family_today: datetime.date | None = None,
) -> datetime.date:
    """Парсит runtime-дату для date-полей tool path.

    Поддерживает ISO `YYYY-MM-DD` и относительные ключевые слова ru/en.

    Ошибки:
        InvalidRuntimeDateError: при невалидном формате входной даты.
    """
    cleaned_value = value.strip()
    if cleaned_value == "":
        raise InvalidRuntimeDateError(
            f"Некорректная дата для поля '{field_name}': пустое значение."
        )

    relative_date = normalize_relative_date(
        text=cleaned_value,
        timezone=timezone,
        family_today=family_today,
    )
    if relative_date is not None:
        return relative_date

    try:
        return datetime.date.fromisoformat(cleaned_value)
    except ValueError as parsing_error:
        raise InvalidRuntimeDateError(
            f"Некорректная дата для поля '{field_name}': '{value}'. "
            "Ожидается ISO YYYY-MM-DD или today/сегодня."
        ) from parsing_error


def _resolve_timezone(timezone: str) -> ZoneInfo:
    """Возвращает ZoneInfo; при ошибке использует UTC и пишет warning."""
    try:
        return ZoneInfo(timezone)
    except Exception:
        logger.warning("Некорректная таймзона '%s', fallback на UTC", timezone)
        return ZoneInfo("UTC")
