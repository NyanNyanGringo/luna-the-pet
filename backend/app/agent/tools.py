"""
Определения инструментов (tools) для OpenAI function calling.

Возвращает JSON-схемы всех доступных инструментов AI-агента.
Формат соответствует OpenAI Responses API.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def get_tool_definitions() -> list[dict]:
    """Возвращает список определений инструментов для OpenAI function calling.

    Каждый инструмент описан в формате OpenAI:
    {"type": "function", "name": ..., "description": ..., "parameters": {...}}

    Возвращает:
        list[dict]: список JSON-схем инструментов
    """
    return [
        _add_weight_tool(),
        _add_vaccination_tool(),
        _add_medication_tool(),
        _add_note_tool(),
        _add_diet_tool(),
        _add_feeding_tool(),
        _get_pet_profile_tool(),
        _update_pet_tool(),
        _create_pet_tool(),
        _update_emergency_profile_tool(),
        _get_emergency_profile_tool(),
    ]


def _add_weight_tool() -> dict:
    """Определение инструмента записи веса."""
    return {
        "type": "function",
        "name": "add_weight",
        "description": "Записать вес питомца в килограммах на указанную дату.",
        "parameters": {
            "type": "object",
            "properties": {
                "pet_name": {
                    "type": "string",
                    "description": "Имя питомца",
                },
                "weight_kg": {
                    "type": "number",
                    "description": "Вес в килограммах",
                },
                "measured_at": {
                    "type": "string",
                    "description": "Дата измерения (YYYY-MM-DD)",
                },
            },
            "required": ["pet_name", "weight_kg", "measured_at"],
        },
    }


def _add_vaccination_tool() -> dict:
    """Определение инструмента записи вакцинации."""
    return {
        "type": "function",
        "name": "add_vaccination",
        "description": "Записать вакцинацию питомца.",
        "parameters": {
            "type": "object",
            "properties": {
                "pet_name": {
                    "type": "string",
                    "description": "Имя питомца",
                },
                "vaccine_name": {
                    "type": "string",
                    "description": "Название вакцины",
                },
                "date": {
                    "type": "string",
                    "description": "Дата вакцинации (YYYY-MM-DD)",
                },
            },
            "required": ["pet_name", "vaccine_name", "date"],
        },
    }


def _add_medication_tool() -> dict:
    """Определение инструмента записи лекарства."""
    return {
        "type": "function",
        "name": "add_medication",
        "description": "Добавить лекарство для питомца.",
        "parameters": {
            "type": "object",
            "properties": {
                "pet_name": {
                    "type": "string",
                    "description": "Имя питомца",
                },
                "name": {
                    "type": "string",
                    "description": "Название препарата",
                },
                "start_date": {
                    "type": "string",
                    "description": "Дата начала приёма (YYYY-MM-DD)",
                },
                "dosage": {
                    "type": "string",
                    "description": "Дозировка",
                },
            },
            "required": ["pet_name", "name", "start_date"],
        },
    }


def _add_note_tool() -> dict:
    """Определение инструмента записи заметки."""
    return {
        "type": "function",
        "name": "add_note",
        "description": "Добавить заметку о питомце.",
        "parameters": {
            "type": "object",
            "properties": {
                "pet_name": {
                    "type": "string",
                    "description": "Имя питомца",
                },
                "content": {
                    "type": "string",
                    "description": "Текст заметки",
                },
            },
            "required": ["pet_name", "content"],
        },
    }


def _add_diet_tool() -> dict:
    """Определение инструмента записи диеты."""
    return {
        "type": "function",
        "name": "add_diet",
        "description": "Добавить запись о диете питомца.",
        "parameters": {
            "type": "object",
            "properties": {
                "pet_name": {
                    "type": "string",
                    "description": "Имя питомца",
                },
                "food_brand": {
                    "type": "string",
                    "description": "Бренд / название корма",
                },
                "start_date": {
                    "type": "string",
                    "description": "Дата начала рациона (YYYY-MM-DD)",
                },
            },
            "required": ["pet_name", "food_brand", "start_date"],
        },
    }


def _add_feeding_tool() -> dict:
    """Определение инструмента записи кормления."""
    return {
        "type": "function",
        "name": "add_feeding",
        "description": "Записать факт кормления питомца.",
        "parameters": {
            "type": "object",
            "properties": {
                "pet_name": {
                    "type": "string",
                    "description": "Имя питомца",
                },
                "food_description": {
                    "type": "string",
                    "description": "Описание еды",
                },
                "fed_at": {
                    "type": "string",
                    "description": (
                        "Дата и время кормления в строгом ISO 8601 с часовым "
                        "смещением (например, 2026-03-08T12:30:00+03:00). "
                        "Naive datetime без offset запрещён."
                    ),
                    "pattern": (
                        "^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}"
                        "(?::\\d{2}(?:\\.\\d{1,6})?)?(?:Z|[+-]\\d{2}:\\d{2})$"
                    ),
                },
            },
            "required": ["pet_name", "food_description", "fed_at"],
            "additionalProperties": False,
        },
    }


def _get_pet_profile_tool() -> dict:
    """Определение инструмента получения профиля питомца."""
    return {
        "type": "function",
        "name": "get_pet_profile",
        "description": "Получить профиль питомца по имени.",
        "parameters": {
            "type": "object",
            "properties": {
                "pet_name": {
                    "type": "string",
                    "description": "Имя питомца",
                },
            },
            "required": ["pet_name"],
        },
    }


def _update_pet_tool() -> dict:
    """Определение инструмента обновления профиля питомца."""
    return {
        "type": "function",
        "name": "update_pet",
        "description": (
            "Частично обновить профиль питомца. Разрешены только поля: "
            "breed, birth_date, gender, is_neutered."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "pet_name": {
                    "type": "string",
                    "description": "Имя питомца",
                },
                "breed": {
                    "type": "string",
                    "description": "Порода",
                },
                "birth_date": {
                    "type": "string",
                    "description": "Дата рождения (YYYY-MM-DD)",
                },
                "gender": {
                    "type": "string",
                    "description": "Пол питомца",
                },
                "is_neutered": {
                    "type": "boolean",
                    "description": "Кастрирован/стерилизован",
                },
            },
            "required": ["pet_name"],
            "additionalProperties": False,
        },
    }


def _create_pet_tool() -> dict:
    """Определение инструмента создания нового питомца."""
    return {
        "type": "function",
        "name": "create_pet",
        "description": "Создать нового питомца в семье.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Имя питомца",
                },
                "species": {
                    "type": "string",
                    "description": "Вид животного (dog, cat, other)",
                },
                "breed": {
                    "type": "string",
                    "description": "Порода",
                },
            },
            "required": ["name", "species"],
        },
    }


def _update_emergency_profile_tool() -> dict:
    """Определение инструмента обновления экстренного профиля."""
    return {
        "type": "function",
        "name": "update_emergency_profile",
        "description": (
            "Частично обновить экстренный профиль питомца. Разрешены поля: "
            "allergies, chronic_conditions, vet_contact, blood_type, "
            "rabies_vaccination_date, latest_weight_snapshot."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "pet_name": {
                    "type": "string",
                    "description": "Имя питомца",
                },
                "allergies": {
                    "type": "string",
                    "description": "Аллергии питомца",
                },
                "chronic_conditions": {
                    "type": "string",
                    "description": "Хронические заболевания",
                },
                "vet_contact": {
                    "type": "string",
                    "description": "Контакт ветеринара",
                },
                "blood_type": {
                    "type": "string",
                    "description": "Группа крови (например, DEA 1.1+)",
                },
                "rabies_vaccination_date": {
                    "type": "string",
                    "description": "Дата прививки от бешенства (YYYY-MM-DD)",
                },
                "latest_weight_snapshot": {
                    "type": "number",
                    "description": "Последний известный вес в килограммах",
                },
            },
            "required": ["pet_name"],
            "additionalProperties": False,
        },
    }


def _get_emergency_profile_tool() -> dict:
    """Определение инструмента получения экстренного профиля."""
    return {
        "type": "function",
        "name": "get_emergency_profile",
        "description": "Получить экстренный профиль питомца.",
        "parameters": {
            "type": "object",
            "properties": {
                "pet_name": {
                    "type": "string",
                    "description": "Имя питомца",
                },
            },
            "required": ["pet_name"],
        },
    }
