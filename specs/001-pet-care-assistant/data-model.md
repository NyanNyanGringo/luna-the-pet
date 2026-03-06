# Модель данных: Ассистент по уходу за питомцами

**Дата**: 2026-03-07
**ORM**: SQLAlchemy 2.x async + Alembic
**БД**: PostgreSQL 16

## Диаграмма связей

```
FamilyMember ──┬── Pet ──┬── WeightRecord
               │         ├── Vaccination
               │         ├── MedicalRecord
               │         ├── Medication ──── Reminder
               │         ├── DietRecord
               │         ├── FeedingEntry
               │         ├── Note
               │         ├── Photo
               │         ├── Supply
               │         └── GiftIdea
               │
               └── LanguagePreference
                         │
               ConversationState
```

## Сущности

### FamilyMember (Член семьи)

| Поле | Тип | Ограничения | Описание |
|------|-----|-------------|----------|
| id | BigInteger | PK | Telegram user ID |
| first_name | String(100) | NOT NULL | Имя из Telegram |
| username | String(100) | NULLABLE | @username из Telegram |
| is_authorized | Boolean | DEFAULT true | Авторизован ли для бота |
| created_at | DateTime(tz) | NOT NULL, DEFAULT now | Дата регистрации |

**Связи**: `pets` (M2M через `family_pet`), `language_preferences` (O2M)

---

### Pet (Питомец)

| Поле | Тип | Ограничения | Описание |
|------|-----|-------------|----------|
| id | Integer | PK, autoincrement | |
| name | String(100) | NOT NULL | Имя питомца |
| species | String(50) | NOT NULL | Вид: dog, cat, other |
| breed | String(100) | NULLABLE | Порода |
| birth_date | Date | NULLABLE | Дата рождения |
| gender | String(10) | NULLABLE | male/female |
| origin_story | Text | NULLABLE | История происхождения |
| blood_type | String(20) | NULLABLE | Группа крови |
| chip_number | String(50) | NULLABLE | Номер микрочипа |
| vet_contact | Text | NULLABLE | Контакт ветеринара |
| is_neutered | Boolean | DEFAULT false | Кастрация/стерилизация |
| created_at | DateTime(tz) | NOT NULL, DEFAULT now | |
| created_by | BigInteger | FK -> FamilyMember | Кто создал профиль |

**Связи**: все дочерние сущности по `pet_id`
**Валидация**: `name` — непустая строка, `species` — enum (dog/cat/other)

---

### family_pet (Связь семья-питомец, M2M)

| Поле | Тип | Ограничения |
|------|-----|-------------|
| family_member_id | BigInteger | FK -> FamilyMember, PK |
| pet_id | Integer | FK -> Pet, PK |

---

### WeightRecord (Запись о весе)

| Поле | Тип | Ограничения | Описание |
|------|-----|-------------|----------|
| id | Integer | PK, autoincrement | |
| pet_id | Integer | FK -> Pet, NOT NULL | |
| weight_kg | Numeric(5,2) | NOT NULL | Вес в кг |
| measured_at | Date | NOT NULL | Дата измерения |
| recorded_by | BigInteger | FK -> FamilyMember | Кто записал |
| created_at | DateTime(tz) | NOT NULL, DEFAULT now | |

**Валидация**: `weight_kg` > 0, `measured_at` <= сегодня
**Индексы**: `(pet_id, measured_at)` — для графика веса

---

### Vaccination (Вакцинация)

| Поле | Тип | Ограничения | Описание |
|------|-----|-------------|----------|
| id | Integer | PK, autoincrement | |
| pet_id | Integer | FK -> Pet, NOT NULL | |
| vaccine_name | String(200) | NOT NULL | Название вакцины |
| date | Date | NOT NULL | Дата введения |
| next_date | Date | NULLABLE | Следующая вакцинация |
| vet_name | String(200) | NULLABLE | Ветеринар/клиника |
| batch_number | String(100) | NULLABLE | Номер партии |
| notes | Text | NULLABLE | |
| recorded_by | BigInteger | FK -> FamilyMember | |
| created_at | DateTime(tz) | NOT NULL, DEFAULT now | |

**Индексы**: `(pet_id, date)`, `(pet_id, next_date)` — для статуса и напоминаний

---

### MedicalRecord (Медицинская запись)

| Поле | Тип | Ограничения | Описание |
|------|-----|-------------|----------|
| id | Integer | PK, autoincrement | |
| pet_id | Integer | FK -> Pet, NOT NULL | |
| record_type | String(50) | NOT NULL | illness, surgery, checkup, allergy, condition |
| title | String(300) | NOT NULL | Краткое описание |
| description | Text | NULLABLE | Подробности |
| date | Date | NOT NULL | Дата события |
| resolved_date | Date | NULLABLE | Дата разрешения (null = текущее) |
| vet_name | String(200) | NULLABLE | |
| recorded_by | BigInteger | FK -> FamilyMember | |
| created_at | DateTime(tz) | NOT NULL, DEFAULT now | |

**Состояния**: `resolved_date IS NULL` = активное состояние
**Индексы**: `(pet_id, record_type)`, `(pet_id, date)`

---

### Medication (Лекарство)

| Поле | Тип | Ограничения | Описание |
|------|-----|-------------|----------|
| id | Integer | PK, autoincrement | |
| pet_id | Integer | FK -> Pet, NOT NULL | |
| name | String(200) | NOT NULL | Название препарата |
| dosage | String(100) | NULLABLE | Дозировка |
| frequency | String(100) | NULLABLE | Частота: "каждые 3 месяца", "ежедневно" |
| frequency_days | Integer | NULLABLE | Частота в днях (для расчёта) |
| start_date | Date | NOT NULL | |
| end_date | Date | NULLABLE | null = текущий |
| last_given_date | Date | NULLABLE | Последняя доза |
| is_active | Boolean | DEFAULT true | |
| notes | Text | NULLABLE | |
| recorded_by | BigInteger | FK -> FamilyMember | |
| created_at | DateTime(tz) | NOT NULL, DEFAULT now | |

**Состояния**: `is_active=true` + `end_date IS NULL` = текущее лекарство
**Связи**: `reminders` (O2M)
**Индексы**: `(pet_id, is_active)`

---

### Reminder (Напоминание)

| Поле | Тип | Ограничения | Описание |
|------|-----|-------------|----------|
| id | Integer | PK, autoincrement | |
| pet_id | Integer | FK -> Pet, NOT NULL | |
| medication_id | Integer | FK -> Medication, NULLABLE | |
| vaccination_id | Integer | FK -> Vaccination, NULLABLE | |
| reminder_type | String(50) | NOT NULL | medication, vaccination, custom |
| title | String(300) | NOT NULL | Текст напоминания |
| next_fire_at | DateTime(tz) | NOT NULL | Когда сработать |
| frequency_days | Integer | NULLABLE | Для повторяющихся |
| is_active | Boolean | DEFAULT true | |
| follow_up_sent | Boolean | DEFAULT false | Контрольное отправлено |
| confirmed_at | DateTime(tz) | NULLABLE | Когда подтвердили |
| created_at | DateTime(tz) | NOT NULL, DEFAULT now | |

**Состояния**:
- Ожидает: `is_active=true`, `next_fire_at` в будущем
- Сработало: `next_fire_at` в прошлом, `confirmed_at IS NULL`
- Ожидает подтверждения: `follow_up_sent=true`, `confirmed_at IS NULL`
- Подтверждено: `confirmed_at IS NOT NULL`

**Индексы**: `(is_active, next_fire_at)` — для планировщика

---

### DietRecord (Запись о диете)

| Поле | Тип | Ограничения | Описание |
|------|-----|-------------|----------|
| id | Integer | PK, autoincrement | |
| pet_id | Integer | FK -> Pet, NOT NULL | |
| food_brand | String(200) | NOT NULL | Марка/тип корма |
| food_type | String(50) | NULLABLE | dry, wet, raw, mixed |
| start_date | Date | NOT NULL | |
| end_date | Date | NULLABLE | null = текущий корм |
| notes | Text | NULLABLE | |
| recorded_by | BigInteger | FK -> FamilyMember | |
| created_at | DateTime(tz) | NOT NULL, DEFAULT now | |

**Историчность**: при смене корма `end_date` текущей записи = дата смены,
новая запись с `start_date` = дата смены.
**Индексы**: `(pet_id, end_date)` — для текущего корма

---

### FeedingEntry (Запись кормления)

| Поле | Тип | Ограничения | Описание |
|------|-----|-------------|----------|
| id | Integer | PK, autoincrement | |
| pet_id | Integer | FK -> Pet, NOT NULL | |
| fed_at | DateTime(tz) | NOT NULL | Время кормления |
| food_description | String(300) | NOT NULL | Что дано |
| portion_size | String(50) | NULLABLE | Размер порции |
| recorded_by | BigInteger | FK -> FamilyMember | |
| created_at | DateTime(tz) | NOT NULL, DEFAULT now | |

**Индексы**: `(pet_id, fed_at)`

---

### Note (Заметка)

| Поле | Тип | Ограничения | Описание |
|------|-----|-------------|----------|
| id | Integer | PK, autoincrement | |
| pet_id | Integer | FK -> Pet, NOT NULL | |
| content | Text | NOT NULL | Текст заметки |
| recorded_by | BigInteger | FK -> FamilyMember | |
| created_at | DateTime(tz) | NOT NULL, DEFAULT now | |

**Индексы**: `(pet_id, created_at)`

---

### Photo (Фотография)

| Поле | Тип | Ограничения | Описание |
|------|-----|-------------|----------|
| id | Integer | PK, autoincrement | |
| pet_id | Integer | FK -> Pet, NOT NULL | |
| file_path | String(500) | NOT NULL | Путь к файлу |
| telegram_file_id | String(200) | NULLABLE | ID файла Telegram |
| caption | String(500) | NULLABLE | Подпись пользователя |
| ai_description | Text | NULLABLE | Описание от AI |
| photo_type | String(50) | DEFAULT 'regular' | regular, passport, document |
| recorded_by | BigInteger | FK -> FamilyMember | |
| created_at | DateTime(tz) | NOT NULL, DEFAULT now | |

**Индексы**: `(pet_id, created_at)`, `(pet_id, photo_type)`

---

### Supply (Запас)

| Поле | Тип | Ограничения | Описание |
|------|-----|-------------|----------|
| id | Integer | PK, autoincrement | |
| pet_id | Integer | FK -> Pet, NOT NULL | |
| supply_type | String(50) | NOT NULL | food, medication |
| name | String(200) | NOT NULL | Название |
| current_amount | Numeric(8,2) | NOT NULL | Текущее количество |
| unit | String(30) | NOT NULL | kg, tablets, ml |
| threshold | Numeric(8,2) | NULLABLE | Порог для напоминания |
| daily_consumption | Numeric(8,2) | NULLABLE | Расход в день |
| updated_at | DateTime(tz) | NOT NULL, DEFAULT now | |
| created_at | DateTime(tz) | NOT NULL, DEFAULT now | |

**Индексы**: `(pet_id, supply_type)`

---

### GiftIdea (Идея подарка)

| Поле | Тип | Ограничения | Описание |
|------|-----|-------------|----------|
| id | Integer | PK, autoincrement | |
| pet_id | Integer | FK -> Pet, NOT NULL | |
| description | String(500) | NOT NULL | Описание подарка |
| status | String(20) | DEFAULT 'idea' | idea, bought, gifted |
| recorded_by | BigInteger | FK -> FamilyMember | |
| created_at | DateTime(tz) | NOT NULL, DEFAULT now | |

**Индексы**: `(pet_id, status)`

---

### LanguagePreference (Языковое предпочтение)

| Поле | Тип | Ограничения | Описание |
|------|-----|-------------|----------|
| id | Integer | PK, autoincrement | |
| family_member_id | BigInteger | FK -> FamilyMember, NOT NULL | |
| language_name | String(100) | NOT NULL | "Сербский", "Español" |
| language_code | String(10) | NULLABLE | sr, es, en |
| last_used_at | DateTime(tz) | NOT NULL, DEFAULT now | |

**Уникальность**: `(family_member_id, language_name)`

---

### ConversationState (Состояние диалога)

| Поле | Тип | Ограничения | Описание |
|------|-----|-------------|----------|
| user_id | BigInteger | PK | Telegram user ID |
| last_response_id | String(200) | NULLABLE | OpenAI response ID |
| turn_count | Integer | DEFAULT 0 | Количество ходов |
| session_summary | Text | NULLABLE | Сводка при обрезке |
| updated_at | DateTime(tz) | NOT NULL, DEFAULT now | |

---

## Соглашения

- Все таблицы используют `snake_case` для имён
- Все FK имеют `ON DELETE CASCADE` для дочерних записей питомца
- `FamilyMember.id` = Telegram user ID (BigInteger, не autoincrement)
- Все временные метки — `DateTime(timezone=True)` (UTC)
- `MetaData(naming_convention=...)` для единообразных имён индексов в PostgreSQL
- Soft delete не используется — прямое удаление с каскадом (семейный проект,
  KISS-принцип)
