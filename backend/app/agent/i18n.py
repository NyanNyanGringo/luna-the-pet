"""
Локализованные шаблоны сообщений для AI-агента.

Поддерживает русский (ru) и английский (en) языки.
Шаблоны используют str.format() для подстановки параметров.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Шаблоны сообщений по языкам
_MESSAGES: dict[str, dict[str, str]] = {
    "ru": {
        "weight_saved": "Вес {weight} кг записан для {pet_name}.",
        "vaccination_saved": "Вакцинация '{vaccine_name}' записана на {date}.",
        "medication_saved": "Лекарство '{name}' добавлено с {start_date}.",
        "note_saved": "Заметка сохранена: {preview}",
        "diet_saved": "Диета '{food_brand}' записана с {start_date}.",
        "feeding_saved": "Кормление записано: {food_description}",
        "pet_created": "Питомец {pet_name} создан.",
        "pet_profile": "Имя: {name}, Вид: {species}{breed_part}{birth_date_part}",
        "pet_profile_breed_part": ", Порода: {breed}",
        "pet_profile_birth_date_part": ", Дата рождения: {birth_date}",
        "pet_updated": "Профиль питомца '{pet_name}' обновлён.",
        "emergency_profile_updated": "Экстренный профиль питомца обновлён.",
        "emergency_profile_empty": "Экстренный профиль пуст",
        "emergency_profile_allergies": "Аллергии: {value}",
        "emergency_profile_chronic_conditions": "Хронические заболевания: {value}",
        "emergency_profile_vet_contact": "Ветеринар: {value}",
        "emergency_profile_blood_type": "Группа крови: {value}",
        "emergency_profile_rabies_vaccination_date": "Прививка от бешенства: {value}",
        "emergency_profile_latest_weight_snapshot": "Последний вес: {value}",
        "unknown_tool": "Неизвестная команда. Попробуйте ещё раз.",
        "unknown_command": "Неизвестная команда. Попробуйте ещё раз.",
        "error_occurred": "Произошла ошибка: {error}.",
    },
    "en": {
        "weight_saved": "Weight {weight} kg saved for {pet_name}.",
        "vaccination_saved": "Vaccination '{vaccine_name}' recorded on {date}.",
        "medication_saved": "Medication '{name}' added from {start_date}.",
        "note_saved": "Note saved: {preview}",
        "diet_saved": "Diet '{food_brand}' saved from {start_date}.",
        "feeding_saved": "Feeding logged: {food_description}",
        "pet_created": "Pet {pet_name} created.",
        "pet_profile": "Name: {name}, Species: {species}{breed_part}{birth_date_part}",
        "pet_profile_breed_part": ", Breed: {breed}",
        "pet_profile_birth_date_part": ", Birth date: {birth_date}",
        "pet_updated": "Pet profile '{pet_name}' updated.",
        "emergency_profile_updated": "Emergency profile updated.",
        "emergency_profile_empty": "Emergency profile is empty",
        "emergency_profile_allergies": "Allergies: {value}",
        "emergency_profile_chronic_conditions": "Chronic conditions: {value}",
        "emergency_profile_vet_contact": "Veterinarian: {value}",
        "emergency_profile_blood_type": "Blood type: {value}",
        "emergency_profile_rabies_vaccination_date": "Rabies vaccination: {value}",
        "emergency_profile_latest_weight_snapshot": "Latest weight: {value}",
        "unknown_tool": "Unknown command. Please try again.",
        "unknown_command": "Unknown command. Please try again.",
        "error_occurred": "An error occurred: {error}.",
    },
}


def get_message(
    key: str,
    language: str = "ru",
    **kwargs: object,
) -> str:
    """Возвращает локализованное сообщение по ключу с подстановкой параметров.

    Аргументы:
        key: ключ сообщения (например, "weight_saved")
        language: код языка ("ru" или "en"), по умолчанию "ru"
        **kwargs: параметры для подстановки в шаблон

    Возвращает:
        str: сформированное сообщение или сам ключ, если он не найден
    """
    language_messages = _MESSAGES.get(language, _MESSAGES["ru"])
    template = language_messages.get(key)

    if template is None:
        return key

    return _format_template(template, kwargs)


def _format_template(
    template: str,
    params: dict[str, object],
) -> str:
    """Подставляет параметры в шаблон, игнорируя отсутствующие ключи.

    Аргументы:
        template: строка-шаблон с плейсхолдерами {param}
        params: словарь параметров для подстановки

    Возвращает:
        str: шаблон с подставленными значениями
    """
    try:
        return template.format(**params)
    except KeyError:
        # Если не все параметры переданы, возвращаем шаблон как есть
        return template
