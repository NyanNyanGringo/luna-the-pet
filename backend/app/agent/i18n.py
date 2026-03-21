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
        "no_weight_records": "Записей о весе не найдено.",
        "no_vaccinations": "Записей о вакцинациях не найдено.",
        "no_medications": "Записей о лекарствах не найдено.",
        "medications_section_active": "Активные лекарства:",
        "medications_section_completed": "Завершённые лекарства:",
        "medications_section_empty": "  (нет записей)",
        "no_notes": "Заметок не найдено.",
        "no_feeding_entries": "Записей о кормлениях не найдено.",
        "no_current_diet": "Текущая диета не задана.",
        "medical_record_saved": (
            "Медицинская запись '{title}' ({record_type}) сохранена на {date}."
        ),
        "no_medical_records": "Медицинских записей не найдено.",
        "measurement_saved": "Измерение {measurement_type}: {value} {unit} записано.",
        "no_measurements": "Записей измерений не найдено.",
        "vet_visit_saved": "Визит к ветеринару '{reason}' записан на {visit_date}.",
        "no_vet_visits": "Записей о визитах к ветеринару не найдено.",
        "mood_log_saved": (
            "Наблюдение записано: настроение — {mood}, аппетит — {appetite}."
        ),
        "no_mood_logs": "Записей наблюдений не найдено.",
        "heat_cycle_saved": "Цикл течки записан с {start_date}.",
        "heat_cycle_warning_neutered": (
            "Внимание: питомец отмечен как кастрированный/стерилизованный. "
            "Цикл записан, но проверьте данные профиля."
        ),
        "heat_cycle_warning_male": (
            "Внимание: у самцов не бывает течки. "
            "Цикл записан, но проверьте пол питомца в профиле."
        ),
        "no_heat_cycles": "Записей о циклах течки не найдено.",
        "unknown_tool": "Неизвестная команда. Попробуйте ещё раз.",
        "unknown_command": "Неизвестная команда. Попробуйте ещё раз.",
        "error_occurred": "Произошла ошибка: {error}.",
        # Метки для форматированного вывода read-хэндлеров
        "label_kg": "кг",
        "label_next_date": "след. дата",
        "label_vet_name": "врач",
        "label_batch_number": "серия",
        "label_notes": "заметки",
        "label_dosage": "дозировка",
        "label_frequency": "частота",
        "label_start_date": "начало",
        "label_end_date": "конец",
        "label_status": "статус",
        "label_status_active": "активно",
        "label_status_completed": "завершено",
        "label_portion_size": "порция",
        "label_brand": "Бренд",
        "label_food_type": "тип",
        "label_description": "описание",
        "label_resolved_date": "разрешено",
        "label_clinic": "клиника",
        "label_mood": "настроение",
        "label_appetite": "аппетит",
        "label_issued_date": "дата",
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
        "no_weight_records": "No weight records found.",
        "no_vaccinations": "No vaccination records found.",
        "no_medications": "No medication records found.",
        "medications_section_active": "Active medications:",
        "medications_section_completed": "Completed medications:",
        "medications_section_empty": "  (no records)",
        "no_notes": "No notes found.",
        "no_feeding_entries": "No feeding records found.",
        "no_current_diet": "No current diet set.",
        "medical_record_saved": (
            "Medical record '{title}' ({record_type}) saved on {date}."
        ),
        "no_medical_records": "No medical records found.",
        "measurement_saved": "Measurement {measurement_type}: {value} {unit} recorded.",
        "no_measurements": "No measurement records found.",
        "vet_visit_saved": "Vet visit '{reason}' scheduled for {visit_date}.",
        "no_vet_visits": "No vet visit records found.",
        "mood_log_saved": "Observation recorded: mood — {mood}, appetite — {appetite}.",
        "no_mood_logs": "No mood log records found.",
        "heat_cycle_saved": "Heat cycle recorded from {start_date}.",
        "heat_cycle_warning_neutered": (
            "Warning: pet is marked as neutered/spayed. "
            "Cycle recorded, but please verify profile data."
        ),
        "heat_cycle_warning_male": (
            "Warning: males do not have heat cycles. "
            "Cycle recorded, but please verify pet gender in profile."
        ),
        "no_heat_cycles": "No heat cycle records found.",
        "unknown_tool": "Unknown command. Please try again.",
        "unknown_command": "Unknown command. Please try again.",
        "error_occurred": "An error occurred: {error}.",
        # Labels for formatted read-handler output
        "label_kg": "kg",
        "label_next_date": "next date",
        "label_vet_name": "vet",
        "label_batch_number": "batch",
        "label_notes": "notes",
        "label_dosage": "dosage",
        "label_frequency": "frequency",
        "label_start_date": "start",
        "label_end_date": "end",
        "label_status": "status",
        "label_status_active": "active",
        "label_status_completed": "completed",
        "label_portion_size": "portion",
        "label_brand": "Brand",
        "label_food_type": "type",
        "label_description": "description",
        "label_resolved_date": "resolved",
        "label_clinic": "clinic",
        "label_mood": "mood",
        "label_appetite": "appetite",
        "label_issued_date": "date",
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
