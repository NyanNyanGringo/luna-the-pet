# REST API контракты

**Базовый URL**: `https://{host}/api`
**Аутентификация**: JWT через Telegram Login Widget
**Формат**: JSON, UTF-8

## Аутентификация

### POST /api/auth/telegram

Верификация Telegram Login Widget callback.

**Запрос**:
```json
{
  "id": 123456789,
  "first_name": "Иван",
  "username": "ivan",
  "photo_url": "https://t.me/...",
  "auth_date": 1709827200,
  "hash": "abc123..."
}
```

**Ответ 200**:
```json
{
  "access_token": "eyJ...",
  "token_type": "bearer",
  "user": {
    "id": 123456789,
    "first_name": "Иван",
    "username": "ivan"
  }
}
```

**Ответ 401**: `{"detail": "Неверная подпись Telegram"}`

---

## Питомцы

### GET /api/pets

Список питомцев семьи.

**Ответ 200**:
```json
[
  {
    "id": 1,
    "name": "Луна",
    "species": "dog",
    "breed": "Лабрадор",
    "birth_date": "2021-03-15",
    "current_weight_kg": 12.0,
    "active_medications_count": 2,
    "upcoming_reminders_count": 1
  }
]
```

### GET /api/pets/{pet_id}

Полный профиль питомца.

**Ответ 200**:
```json
{
  "id": 1,
  "name": "Луна",
  "species": "dog",
  "breed": "Лабрадор",
  "birth_date": "2021-03-15",
  "gender": "female",
  "is_neutered": true,
  "blood_type": null,
  "chip_number": "643094100012345",
  "vet_contact": "Клиника Доктор Вет, +7...",
  "origin_story": "Взяли щенком из питомника",
  "latest_weight": {"weight_kg": 12.0, "measured_at": "2026-03-01"},
  "current_diet": {"food_brand": "Royal Canin", "start_date": "2026-02-01"},
  "active_medications": [
    {"id": 1, "name": "Nexgard", "dosage": "1 таблетка", "frequency": "каждые 3 месяца"}
  ]
}
```

### PUT /api/pets/{pet_id}

Обновление профиля питомца.

**Запрос** (частичное обновление):
```json
{
  "breed": "Лабрадор-ретривер",
  "vet_contact": "Новая клиника, +7..."
}
```

**Ответ 200**: обновлённый объект Pet

---

## Записи о здоровье

### GET /api/pets/{pet_id}/weight

История веса (для графика).

**Query параметры**: `?from=2025-01-01&to=2026-03-07`

**Ответ 200**:
```json
[
  {"id": 1, "weight_kg": 11.5, "measured_at": "2025-06-01"},
  {"id": 2, "weight_kg": 12.0, "measured_at": "2026-03-01"}
]
```

### POST /api/pets/{pet_id}/weight

**Запрос**: `{"weight_kg": 12.5, "measured_at": "2026-03-07"}`
**Ответ 201**: созданная запись

### GET /api/pets/{pet_id}/vaccinations

**Ответ 200**:
```json
[
  {
    "id": 1,
    "vaccine_name": "Бешенство",
    "date": "2026-01-15",
    "next_date": "2027-01-15",
    "vet_name": "Доктор Вет",
    "is_overdue": false
  }
]
```

### POST /api/pets/{pet_id}/vaccinations

**Запрос**:
```json
{
  "vaccine_name": "Бешенство",
  "date": "2026-03-07",
  "next_date": "2027-03-07",
  "vet_name": "Клиника"
}
```

### GET /api/pets/{pet_id}/medical

Медицинские записи.

**Query параметры**: `?type=allergy&active_only=true`

**Ответ 200**:
```json
[
  {
    "id": 1,
    "record_type": "allergy",
    "title": "Аллергия на курицу",
    "date": "2024-05-01",
    "resolved_date": null,
    "is_active": true
  }
]
```

### GET /api/pets/{pet_id}/medications

**Query параметры**: `?active_only=true`

### GET /api/pets/{pet_id}/diet

История диеты (все записи с диапазонами дат).

### GET /api/pets/{pet_id}/notes

**Query параметры**: `?limit=20&offset=0`

### GET /api/pets/{pet_id}/photos

**Query параметры**: `?type=regular&limit=20&offset=0`

---

## CRUD для всех записей

Единообразные эндпоинты для каждого типа записи:

| Метод | URL | Описание |
|-------|-----|----------|
| POST | /api/pets/{pet_id}/{resource} | Создать запись |
| PUT | /api/{resource}/{id} | Обновить запись |
| DELETE | /api/{resource}/{id} | Удалить запись |

Где `{resource}` = weight, vaccinations, medical, medications, diet, feeding, notes, photos, supplies, gift-ideas

---

## Календарь

### GET /api/calendar

Все события и напоминания для всех питомцев семьи.

**Query параметры**: `?year=2026&month=3`

**Ответ 200**:
```json
{
  "events": [
    {
      "id": "vacc-1",
      "type": "vaccination",
      "title": "Луна: Бешенство",
      "date": "2026-01-15",
      "pet_id": 1,
      "is_past": true
    }
  ],
  "reminders": [
    {
      "id": "rem-1",
      "type": "medication",
      "title": "Луна: Nexgard",
      "date": "2026-04-05",
      "pet_id": 1,
      "is_past": false
    }
  ]
}
```

---

## Аналитика

### GET /api/pets/{pet_id}/analytics

**Ответ 200**:
```json
{
  "weight_trend": [
    {"date": "2025-06-01", "weight_kg": 11.5},
    {"date": "2026-03-01", "weight_kg": 12.0}
  ],
  "vaccination_status": [
    {"name": "Бешенство", "status": "current", "next_date": "2027-01-15", "days_until": 314}
  ],
  "medication_stats": {
    "active": 2,
    "completed": 3
  },
  "medical_timeline": [
    {"date": "2024-05-01", "type": "allergy", "title": "Аллергия на курицу", "is_resolved": false}
  ]
}
```

---

## SOS

### GET /api/pets/{pet_id}/sos

Экстренная карточка (аналог `/sos` в Telegram).

**Ответ 200**:
```json
{
  "pet_name": "Луна",
  "allergies": ["Аллергия на курицу"],
  "current_medications": [
    {"name": "Nexgard", "dosage": "1 таблетка", "frequency": "каждые 3 месяца"}
  ],
  "chronic_conditions": [],
  "vet_contact": "Клиника Доктор Вет, +7...",
  "blood_type": null,
  "last_rabies_vaccination": "2026-01-15",
  "latest_weight": {"weight_kg": 12.0, "measured_at": "2026-03-01"}
}
```

---

## Экспорт/Импорт

### GET /api/export

Полный экспорт всех данных семьи в JSON.

**Ответ 200**: JSON-файл (`Content-Disposition: attachment`)

### POST /api/import

Импорт данных из JSON-файла.

**Запрос**: `multipart/form-data` с полем `file`
**Ответ 200**: `{"imported": {"pets": 2, "records": 45}}`
**Ответ 409**: `{"detail": "Конфликт данных", "conflicts": [...]}`

---

## Общие ответы об ошибках

| Код | Описание |
|-----|----------|
| 400 | Невалидные данные (детали в `detail`) |
| 401 | Не авторизован |
| 403 | Нет доступа |
| 404 | Ресурс не найден |
| 409 | Конфликт данных |
| 500 | Внутренняя ошибка |
