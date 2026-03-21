# Research: Расширение базы данных и инструментов AI-агента

**Feature**: 007-extend-agent-tools
**Date**: 2026-03-17

## Исследование 1: Размещение новых моделей в существующей структуре

**Decision**: Модели Measurement, VetVisit, MoodLog, HeatCycle добавляются в `health.py`. Модель Document — в отдельный файл `documents.py`.

**Rationale**: Модели health.py уже содержат 6 моделей (WeightRecord, Vaccination, MedicalRecord, Medication, Note, EmergencyProfile). Measurement, VetVisit, MoodLog и HeatCycle логически относятся к здоровью питомца. Document — отдельная концепция (хранение ссылок на файлы), заслуживает собственного модуля.

**Alternatives considered**:
- Все 5 в health.py — отклонено: файл станет слишком большим (~600 строк), документы семантически отличаются от здоровья
- Каждая модель в отдельном файле — отклонено: противоречит существующему паттерну группировки по домену

## Исследование 2: Размещение сервисов для новых моделей

**Decision**: Методы для Measurement, VetVisit, MoodLog, HeatCycle добавляются в `health_service.py`. Для Document создаётся `document_service.py`.

**Rationale**: Следуем паттерну «модель ↔ сервис» из текущей кодовой базы: health models → health_service, nutrition models → nutrition_service. Document — отдельный домен.

**Alternatives considered**:
- Отдельный сервис для каждой сущности — отклонено: избыточная фрагментация, не соответствует текущему стилю
- Всё в одном новом сервисе — отклонено: нарушает существующую доменную группировку

## Исследование 3: Паттерн инструментов чтения

**Decision**: Каждый инструмент чтения — отдельная функция OpenAI function calling (get_weight_history, get_vaccinations, get_medications, get_notes, get_feeding_history, get_current_diet, get_medical_records). Возвращают текстовое представление данных.

**Rationale**: Существующие инструменты чтения (get_pet_profile, get_emergency_profile) возвращают текст, не JSON. Агент формирует человеко-читаемый ответ на основе текста. Отдельные инструменты позволяют агенту запрашивать только нужные данные.

**Alternatives considered**:
- Один универсальный get_pet_data с параметром category — отклонено: сложная схема, агенту труднее выбрать правильные параметры
- Возврат JSON — отклонено: нарушает текущий паттерн, агент итак форматирует ответ

## Исследование 4: Enum-значения для новых таблиц

**Decision**: Все enum-значения хранятся как строки (String), не как PostgreSQL ENUM. Допустимые значения валидируются на уровне сервиса.

**Rationale**: Существующий паттерн в проекте — строковые поля (Medication.record_type, Pet.species, Pet.gender). PostgreSQL ENUM требует миграции при добавлении значений, строки проще расширять.

**Alternatives considered**:
- PostgreSQL ENUM — отклонено: требует ALTER TYPE миграций, усложняет добавление новых значений
- Python Enum + SQLAlchemy Enum type — отклонено: тот же недостаток + усложнение ORM-слоя

## Исследование 5: Расширение update_pet whitelist

**Decision**: Добавить origin_story, blood_type, chip_number, vet_contact в `_PET_UPDATE_FIELD_WHITELIST`. Поля name, species, is_active, workspace_id остаются заблокированными.

**Rationale**: Пользователь явно запросил эти поля. Они безопасны для обновления через агента (не влияют на мультитенантность или идентификацию питомца). Поля name/species — идентификаторы, их изменение может нарушить связи.

**Alternatives considered**:
- Разрешить изменение name — отклонено: name используется для поиска питомца в инструментах (pet_name), изменение может сломать контекст
- Отдельный инструмент rename_pet — возможно в будущем, но вне скоупа этой фичи

## Исследование 6: Параметры инструментов чтения с фильтрацией

**Decision**: Инструменты чтения принимают опциональные фильтры:
- get_weight_history: limit (default 10)
- get_vaccinations: без фильтров (все записи)
- get_medications: active_only (default false)
- get_notes: limit (default 10)
- get_feeding_history: days (default 7)
- get_current_diet: без параметров
- get_medical_records: record_type (optional)

**Rationale**: Минимальный набор фильтров, покрывающий типичные сценарии. Агент может уточнить запрос пользователя через параметры. Значения по умолчанию выбраны для разумного объёма ответа.

**Alternatives considered**:
- Полная пагинация (offset + limit) — отклонено: избыточно для семейного использования
- Фильтрация по датам для всех — отклонено: усложняет интерфейс, достаточно limit для большинства сценариев
