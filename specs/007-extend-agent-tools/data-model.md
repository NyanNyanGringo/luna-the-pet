# Data Model: Расширение базы данных и инструментов AI-агента

**Feature**: 007-extend-agent-tools
**Date**: 2026-03-17

## Новые сущности

### Measurement (Измерение)

Разовый замер физиологического параметра питомца.

| Поле | Тип | Обязательное | Описание |
| ---- | --- | ------------ | -------- |
| id | Integer, PK | да | Автоинкремент |
| pet_id | Integer, FK → pet.id | да | Питомец |
| measurement_type | String(50) | да | Тип: temperature, pulse, respiration |
| value | Numeric(6,2) | да | Числовое значение замера |
| unit | String(20) | да | Единица измерения (°C, уд/мин, вд/мин) |
| measured_at | Date | да | Дата замера |
| recorded_by | BigInteger | нет | Telegram user ID |
| created_at | DateTime(tz) | да | server_default |

**Индексы**: (pet_id, measured_at), (pet_id, measurement_type)
**FK cascade**: ON DELETE CASCADE от pet
**Валидация**: measurement_type ∈ {temperature, pulse, respiration}

---

### VetVisit (Визит к ветеринару)

Запись о визите к ветеринару — запланированном или состоявшемся.

| Поле | Тип | Обязательное | Описание |
| ---- | --- | ------------ | -------- |
| id | Integer, PK | да | Автоинкремент |
| pet_id | Integer, FK → pet.id | да | Питомец |
| clinic | String(300) | нет | Название клиники |
| reason | String(500) | да | Причина визита |
| visit_date | Date | да | Дата визита |
| status | String(20) | да | Статус: planned, completed |
| notes | Text | нет | Заметки |
| recorded_by | BigInteger | нет | Telegram user ID |
| created_at | DateTime(tz) | да | server_default |

**Индексы**: (pet_id, visit_date), (pet_id, status)
**FK cascade**: ON DELETE CASCADE от pet
**Валидация**: status ∈ {planned, completed}

---

### MoodLog (Самочувствие)

Ежедневное наблюдение за состоянием питомца.

| Поле | Тип | Обязательное | Описание |
| ---- | --- | ------------ | -------- |
| id | Integer, PK | да | Автоинкремент |
| pet_id | Integer, FK → pet.id | да | Питомец |
| mood | String(20) | да | Настроение: excellent, good, normal, poor |
| appetite | String(20) | да | Аппетит: good, reduced, none |
| log_date | Date | да | Дата наблюдения |
| notes | Text | нет | Заметки |
| recorded_by | BigInteger | нет | Telegram user ID |
| created_at | DateTime(tz) | да | server_default |

**Индексы**: (pet_id, log_date)
**FK cascade**: ON DELETE CASCADE от pet
**Валидация**: mood ∈ {excellent, good, normal, poor}, appetite ∈ {good, reduced, none}

---

### Document (Документ)

Ссылка на медицинский документ питомца.

| Поле | Тип | Обязательное | Описание |
| ---- | --- | ------------ | -------- |
| id | Integer, PK | да | Автоинкремент |
| pet_id | Integer, FK → pet.id | да | Питомец |
| document_type | String(100) | да | Тип: passport, analysis, certificate, other |
| url | String(2048) | да | Ссылка на документ |
| issued_date | Date | нет | Дата выдачи |
| description | Text | нет | Описание документа |
| recorded_by | BigInteger | нет | Telegram user ID |
| created_at | DateTime(tz) | да | server_default |

**Индексы**: (pet_id, document_type)
**FK cascade**: ON DELETE CASCADE от pet
**Валидация**: url — непустая строка

---

### HeatCycle (Течка)

Запись о цикле течки для некастрированных самок.

| Поле | Тип | Обязательное | Описание |
| ---- | --- | ------------ | -------- |
| id | Integer, PK | да | Автоинкремент |
| pet_id | Integer, FK → pet.id | да | Питомец |
| start_date | Date | да | Дата начала |
| end_date | Date | нет | Дата окончания |
| notes | Text | нет | Заметки |
| recorded_by | BigInteger | нет | Telegram user ID |
| created_at | DateTime(tz) | да | server_default |

**Индексы**: (pet_id, start_date)
**FK cascade**: ON DELETE CASCADE от pet

---

## Существующие сущности — изменения

### Vaccination (расширение инструмента)

Модель уже содержит все поля. Изменяется только инструмент add_vaccination — добавляются параметры:
- next_date (Date, опционально)
- vet_name (String, опционально)
- batch_number (String, опционально)
- notes (Text, опционально)

### Medication (расширение инструмента)

Модель уже содержит все поля. Изменяется только инструмент add_medication — добавляются параметры:
- frequency (String, опционально)
- end_date (Date, опционально)
- last_given_date (Date, опционально)
- notes (Text, опционально)

### DietRecord (расширение инструмента)

Модель уже содержит все поля. Изменяется только инструмент add_diet — добавляются параметры:
- food_type (String, опционально)
- end_date (Date, опционально)
- notes (Text, опционально)

### FeedingEntry (расширение инструмента)

Модель уже содержит все поля. Изменяется только инструмент add_feeding — добавляется параметр:
- portion_size (String, опционально)

### Pet (расширение whitelist инструмента update_pet)

Модель уже содержит все поля. Расширяется `_PET_UPDATE_FIELD_WHITELIST`:
- origin_story (Text, опционально)
- blood_type (String, опционально)
- chip_number (String, опционально)
- vet_contact (Text, опционально)

---

## Связи между сущностями

```text
Workspace 1──N Pet
  Pet 1──N Measurement      (новая)
  Pet 1──N VetVisit          (новая)
  Pet 1──N MoodLog           (новая)
  Pet 1──N Document          (новая)
  Pet 1──N HeatCycle         (новая)
  Pet 1──N WeightRecord      (существующая)
  Pet 1──N Vaccination       (существующая)
  Pet 1──N MedicalRecord     (существующая)
  Pet 1──N Medication        (существующая)
  Pet 1──N Note              (существующая)
  Pet 1──1 EmergencyProfile  (существующая)
  Pet 1──N DietRecord        (существующая)
  Pet 1──N FeedingEntry      (существующая)
```

## Миграция

Одна Alembic-миграция создаёт 5 новых таблиц: measurement, vet_visit, mood_log, document, heat_cycle. Существующие таблицы не изменяются — расширения касаются только уровня инструментов агента.
