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
        _get_weight_history_tool(),
        _get_vaccinations_tool(),
        _get_medications_tool(),
        _get_notes_tool(),
        _get_feeding_history_tool(),
        _get_current_diet_tool(),
        _add_medical_record_tool(),
        _get_medical_records_tool(),
        _add_measurement_tool(),
        _get_measurements_tool(),
        _add_vet_visit_tool(),
        _get_vet_visits_tool(),
        _add_mood_log_tool(),
        _get_mood_logs_tool(),
        _add_heat_cycle_tool(),
        _get_heat_cycles_tool(),
    ]


def _add_weight_tool() -> dict:
    """Определение инструмента записи веса."""
    return {
        "type": "function",
        "name": "add_weight",
        "description": (
            "Записать вес питомца в килограммах на указанную дату. "
            "Все параметры обязательные."
        ),
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
        "description": (
            "Записать вакцинацию питомца. "
            "Обязательные параметры - pet_name, vaccine_name, date. "
            "Остальные параметры - опциональные."
        ),
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
                "next_date": {
                    "type": "string",
                    "description": "Дата следующей прививки (YYYY-MM-DD)",
                },
                "vet_name": {
                    "type": "string",
                    "description": "Имя ветеринара",
                },
                "batch_number": {
                    "type": "string",
                    "description": "Номер серии вакцины",
                },
                "notes": {
                    "type": "string",
                    "description": "Заметки",
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
        "description": (
            "Добавить лекарство для питомца. "
            "Обязательные параметры - pet_name, name, start_date. "
            "Остальные параметры - опциональные."
        ),
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
                "frequency": {
                    "type": "string",
                    "description": "Частота приёма (например, «2 раза в день»)",
                },
                "end_date": {
                    "type": "string",
                    "description": "Дата окончания приёма (YYYY-MM-DD)",
                },
                "last_given_date": {
                    "type": "string",
                    "description": "Дата последнего приёма (YYYY-MM-DD)",
                },
                "notes": {
                    "type": "string",
                    "description": "Заметки",
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
        "description": ("Добавить заметку о питомце. Все параметры обязательные."),
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
        "description": (
            "Добавить запись о диете питомца. "
            "Обязательные параметры - pet_name, food_brand, "
            "start_date. Остальные параметры - опциональные."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "pet_name": {
                    "type": "string",
                    "description": "Имя питомца.",
                },
                "food_brand": {
                    "type": "string",
                    "description": "Бренд / название корма",
                },
                "start_date": {
                    "type": "string",
                    "description": "Дата начала рациона (YYYY-MM-DD)",
                },
                "food_type": {
                    "type": "string",
                    "description": "Тип корма (dry, wet, raw, mixed, homemade)",
                },
                "end_date": {
                    "type": "string",
                    "description": "Дата окончания диеты (YYYY-MM-DD)",
                },
                "notes": {
                    "type": "string",
                    "description": "Заметки",
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
        "description": (
            "Записать факт кормления питомца. "
            "Обязательные параметры - pet_name, "
            "food_description, fed_at. "
            "Остальные параметры - опциональные."
        ),
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
                "portion_size": {
                    "type": "string",
                    "description": "Размер порции (например, «200г», «1 стакан»)",
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
        "description": (
            "Получить профиль питомца по имени. Обязательный параметр - pet_name."
        ),
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
            "Частично обновить профиль питомца. "
            "Обязательный параметр - pet_name. "
            "Опциональные поля: breed, birth_date, gender, "
            "is_neutered, origin_story, chip_number."
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
                "origin_story": {
                    "type": "string",
                    "description": "История появления питомца",
                },
                "chip_number": {
                    "type": "string",
                    "description": "Номер микрочипа",
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
        "description": (
            "Создать нового питомца в семье. "
            "Обязательные параметры - name, species. "
            "Остальные параметры - опциональные."
        ),
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
            "Частично обновить экстренный профиль питомца. "
            "Обязательный параметр - pet_name. "
            "Опциональные поля: allergies, chronic_conditions, "
            "vet_contact, blood_type, "
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
        "description": (
            "Получить экстренный профиль питомца. Обязательный параметр - pet_name."
        ),
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


def _get_weight_history_tool() -> dict:
    """Определение инструмента получения истории веса."""
    return {
        "type": "function",
        "name": "get_weight_history",
        "description": (
            "Получить историю веса питомца. "
            "Обязательный параметр - pet_name. "
            "Остальные параметры - опциональные."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "pet_name": {
                    "type": "string",
                    "description": "Имя питомца",
                },
                "limit": {
                    "type": "integer",
                    "description": "Максимальное количество записей",
                },
            },
            "required": ["pet_name"],
        },
    }


def _get_vaccinations_tool() -> dict:
    """Определение инструмента получения вакцинаций."""
    return {
        "type": "function",
        "name": "get_vaccinations",
        "description": (
            "Получить список вакцинаций питомца. Обязательный параметр - pet_name."
        ),
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


def _get_medications_tool() -> dict:
    """Определение инструмента получения лекарств."""
    return {
        "type": "function",
        "name": "get_medications",
        "description": (
            "Получить список лекарств питомца. "
            "Обязательный параметр - pet_name. "
            "Остальные параметры - опциональные."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "pet_name": {
                    "type": "string",
                    "description": "Имя питомца",
                },
                "active_only": {
                    "type": "boolean",
                    "description": "Показать только активные лекарства",
                },
            },
            "required": ["pet_name"],
        },
    }


def _get_notes_tool() -> dict:
    """Определение инструмента получения заметок."""
    return {
        "type": "function",
        "name": "get_notes",
        "description": (
            "Получить заметки о питомце. "
            "Обязательный параметр - pet_name. "
            "Остальные параметры - опциональные."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "pet_name": {
                    "type": "string",
                    "description": "Имя питомца",
                },
                "limit": {
                    "type": "integer",
                    "description": "Максимальное количество заметок",
                },
            },
            "required": ["pet_name"],
        },
    }


def _get_feeding_history_tool() -> dict:
    """Определение инструмента получения истории кормлений."""
    return {
        "type": "function",
        "name": "get_feeding_history",
        "description": (
            "Получить историю кормлений питомца. "
            "Обязательный параметр - pet_name. "
            "Остальные параметры - опциональные."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "pet_name": {
                    "type": "string",
                    "description": "Имя питомца",
                },
                "start_date": {
                    "type": "string",
                    "description": ("Начальная дата периода (YYYY-MM-DD)"),
                },
                "end_date": {
                    "type": "string",
                    "description": ("Конечная дата периода (YYYY-MM-DD)"),
                },
            },
            "required": ["pet_name"],
        },
    }


def _get_current_diet_tool() -> dict:
    """Определение инструмента получения текущей диеты."""
    return {
        "type": "function",
        "name": "get_current_diet",
        "description": (
            "Получить текущую диету питомца. Обязательный параметр - pet_name."
        ),
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


def _add_medical_record_tool() -> dict:
    """Определение инструмента создания медицинской записи."""
    return {
        "type": "function",
        "name": "add_medical_record",
        "description": (
            "Добавить медицинскую запись для питомца "
            "(болезнь, осмотр, операция). "
            "Обязательные параметры - pet_name, record_type, "
            "title, date. "
            "Остальные параметры - опциональные."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "pet_name": {
                    "type": "string",
                    "description": "Имя питомца",
                },
                "record_type": {
                    "type": "string",
                    "description": "Тип записи (illness, checkup, surgery)",
                    "enum": ["illness", "checkup", "surgery"],
                },
                "title": {
                    "type": "string",
                    "description": "Заголовок записи",
                },
                "date": {
                    "type": "string",
                    "description": "Дата события (YYYY-MM-DD)",
                },
                "description": {
                    "type": "string",
                    "description": "Подробное описание",
                },
                "resolved_date": {
                    "type": "string",
                    "description": "Дата разрешения / выздоровления (YYYY-MM-DD)",
                },
                "vet_name": {
                    "type": "string",
                    "description": "Имя ветеринара",
                },
            },
            "required": ["pet_name", "record_type", "title", "date"],
        },
    }


def _get_medical_records_tool() -> dict:
    """Определение инструмента получения медицинских записей."""
    return {
        "type": "function",
        "name": "get_medical_records",
        "description": (
            "Получить медицинские записи питомца. "
            "Обязательный параметр - pet_name. "
            "Остальные параметры - опциональные."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "pet_name": {
                    "type": "string",
                    "description": "Имя питомца",
                },
                "record_type": {
                    "type": "string",
                    "description": "Фильтр по типу записи (illness, checkup, surgery)",
                },
            },
            "required": ["pet_name"],
        },
    }


def _add_measurement_tool() -> dict:
    """Определение инструмента записи физиологического измерения."""
    return {
        "type": "function",
        "name": "add_measurement",
        "description": (
            "Записать физиологическое измерение питомца "
            "(температура, пульс, дыхание). "
            "Все параметры обязательные."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "pet_name": {
                    "type": "string",
                    "description": "Имя питомца",
                },
                "measurement_type": {
                    "type": "string",
                    "description": "Тип измерения (temperature, pulse, respiration)",
                    "enum": ["temperature", "pulse", "respiration"],
                },
                "value": {
                    "type": "number",
                    "description": "Числовое значение измерения",
                },
                "measured_at": {
                    "type": "string",
                    "description": "Дата измерения (YYYY-MM-DD)",
                },
            },
            "required": ["pet_name", "measurement_type", "value", "measured_at"],
        },
    }


def _get_measurements_tool() -> dict:
    """Определение инструмента получения измерений."""
    return {
        "type": "function",
        "name": "get_measurements",
        "description": (
            "Получить физиологические измерения питомца. "
            "Обязательный параметр - pet_name. "
            "Остальные параметры - опциональные."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "pet_name": {
                    "type": "string",
                    "description": "Имя питомца",
                },
                "measurement_type": {
                    "type": "string",
                    "description": (
                        "Фильтр по типу измерения (temperature, pulse, respiration)"
                    ),
                    "enum": ["temperature", "pulse", "respiration"],
                },
                "limit": {
                    "type": "integer",
                    "description": "Максимальное количество записей",
                },
                "start_date": {
                    "type": "string",
                    "description": ("Начальная дата периода (YYYY-MM-DD)"),
                },
                "end_date": {
                    "type": "string",
                    "description": ("Конечная дата периода (YYYY-MM-DD)"),
                },
            },
            "required": ["pet_name"],
        },
    }


def _add_vet_visit_tool() -> dict:
    """Определение инструмента записи визита к ветеринару."""
    return {
        "type": "function",
        "name": "add_vet_visit",
        "description": (
            "Записать визит к ветеринару "
            "(запланированный или состоявшийся). "
            "Обязательные параметры - pet_name, reason, "
            "visit_date. "
            "Остальные параметры - опциональные."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "pet_name": {
                    "type": "string",
                    "description": "Имя питомца",
                },
                "reason": {
                    "type": "string",
                    "description": "Причина визита",
                },
                "visit_date": {
                    "type": "string",
                    "description": "Дата визита (YYYY-MM-DD)",
                },
                "status": {
                    "type": "string",
                    "description": "Статус визита (planned, completed)",
                    "enum": ["planned", "completed"],
                },
                "clinic": {
                    "type": "string",
                    "description": "Название клиники",
                },
                "notes": {
                    "type": "string",
                    "description": "Заметки",
                },
            },
            "required": ["pet_name", "reason", "visit_date"],
        },
    }


def _get_vet_visits_tool() -> dict:
    """Определение инструмента получения визитов к ветеринару."""
    return {
        "type": "function",
        "name": "get_vet_visits",
        "description": (
            "Получить список визитов к ветеринару. "
            "Обязательный параметр - pet_name. "
            "Остальные параметры - опциональные."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "pet_name": {
                    "type": "string",
                    "description": "Имя питомца",
                },
                "status": {
                    "type": "string",
                    "description": "Фильтр по статусу (planned, completed)",
                    "enum": ["planned", "completed"],
                },
            },
            "required": ["pet_name"],
        },
    }


def _add_mood_log_tool() -> dict:
    """Определение инструмента записи наблюдения за состоянием."""
    return {
        "type": "function",
        "name": "add_mood_log",
        "description": (
            "Записать наблюдение за состоянием питомца "
            "(настроение и аппетит). "
            "Обязательные параметры - pet_name, mood, "
            "appetite, log_date. "
            "Остальные параметры - опциональные."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "pet_name": {
                    "type": "string",
                    "description": "Имя питомца",
                },
                "mood": {
                    "type": "string",
                    "description": "Настроение (excellent, good, normal, poor)",
                    "enum": ["excellent", "good", "normal", "poor"],
                },
                "appetite": {
                    "type": "string",
                    "description": "Аппетит (good, reduced, none)",
                    "enum": ["good", "reduced", "none"],
                },
                "log_date": {
                    "type": "string",
                    "description": "Дата наблюдения (YYYY-MM-DD)",
                },
                "notes": {
                    "type": "string",
                    "description": "Заметки",
                },
            },
            "required": ["pet_name", "mood", "appetite", "log_date"],
        },
    }


def _get_mood_logs_tool() -> dict:
    """Определение инструмента получения наблюдений за состоянием."""
    return {
        "type": "function",
        "name": "get_mood_logs",
        "description": (
            "Получить записи наблюдений за состоянием питомца. "
            "Обязательный параметр - pet_name. "
            "Остальные параметры - опциональные."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "pet_name": {
                    "type": "string",
                    "description": "Имя питомца",
                },
                "limit": {
                    "type": "integer",
                    "description": "Максимальное количество записей",
                },
            },
            "required": ["pet_name"],
        },
    }


def _add_heat_cycle_tool() -> dict:
    """Определение инструмента записи цикла течки."""
    return {
        "type": "function",
        "name": "add_heat_cycle",
        "description": (
            "Записать цикл течки питомца. "
            "Обязательные параметры - pet_name, start_date. "
            "Остальные параметры - опциональные."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "pet_name": {
                    "type": "string",
                    "description": "Имя питомца",
                },
                "start_date": {
                    "type": "string",
                    "description": "Дата начала цикла (YYYY-MM-DD)",
                },
                "end_date": {
                    "type": "string",
                    "description": "Дата окончания цикла (YYYY-MM-DD)",
                },
                "notes": {
                    "type": "string",
                    "description": "Заметки",
                },
            },
            "required": ["pet_name", "start_date"],
        },
    }


def _get_heat_cycles_tool() -> dict:
    """Определение инструмента получения циклов течки."""
    return {
        "type": "function",
        "name": "get_heat_cycles",
        "description": (
            "Получить записи о циклах течки питомца. Обязательный параметр - pet_name."
        ),
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
