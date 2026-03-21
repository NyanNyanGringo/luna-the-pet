# Контракты инструментов записи

**Feature**: 007-extend-agent-tools
**Date**: 2026-03-17

## Расширения существующих инструментов записи

### add_vaccination (расширение)

Существующие обязательные параметры: pet_name, vaccine_name, date.

**Новые опциональные параметры**:

| Параметр | Тип | Описание |
| -------- | --- | -------- |
| next_date | string (YYYY-MM-DD) | Дата следующей прививки |
| vet_name | string | Имя ветеринара |
| batch_number | string | Номер серии вакцины |
| notes | string | Заметки |

---

### add_medication (расширение)

Существующие обязательные параметры: pet_name, name, start_date. Опциональный: dosage.

**Новые опциональные параметры**:

| Параметр | Тип | Описание |
| -------- | --- | -------- |
| frequency | string | Частота приёма (например, «2 раза в день») |
| end_date | string (YYYY-MM-DD) | Дата окончания приёма |
| last_given_date | string (YYYY-MM-DD) | Дата последнего приёма |
| notes | string | Заметки |

---

### add_diet (расширение)

Существующие обязательные параметры: pet_name, food_brand, start_date.

**Новые опциональные параметры**:

| Параметр | Тип | Описание |
| -------- | --- | -------- |
| food_type | string | Тип корма (dry, wet, raw, mixed, homemade) |
| end_date | string (YYYY-MM-DD) | Дата окончания диеты |
| notes | string | Заметки |

---

### add_feeding (расширение)

Существующие обязательные параметры: pet_name, food_description, fed_at.

**Новые опциональные параметры**:

| Параметр | Тип | Описание |
| -------- | --- | -------- |
| portion_size | string | Размер порции (например, «200г», «1 стакан») |

---

### update_pet (расширение whitelist)

Существующие параметры whitelist: breed, birth_date, gender, is_neutered.

**Новые параметры whitelist**:

| Параметр | Тип | Описание |
| -------- | --- | -------- |
| origin_story | string | История появления питомца |
| blood_type | string | Группа крови |
| chip_number | string | Номер микрочипа |
| vet_contact | string | Контакт ветклиники |

---

## Новые инструменты записи

### add_medical_record

Запись медицинской записи (болезнь, осмотр, операция).

**Параметры**:

| Параметр | Тип | Обязательный | Описание |
| -------- | --- | ------------ | -------- |
| pet_name | string | да | Имя питомца |
| record_type | string | да | Тип: illness, checkup, surgery |
| title | string | да | Название / диагноз |
| date | string (YYYY-MM-DD) | да | Дата |
| description | string | нет | Подробное описание |
| resolved_date | string (YYYY-MM-DD) | нет | Дата выздоровления/завершения |
| vet_name | string | нет | Имя ветеринара |

---

### add_measurement

Запись физиологического измерения.

**Параметры**:

| Параметр | Тип | Обязательный | Описание |
| -------- | --- | ------------ | -------- |
| pet_name | string | да | Имя питомца |
| measurement_type | string | да | Тип: temperature, pulse, respiration |
| value | number | да | Числовое значение |
| measured_at | string (YYYY-MM-DD) | да | Дата замера |

**Логика**: единица измерения определяется автоматически по типу (temperature → °C, pulse → уд/мин, respiration → вд/мин).

---

### add_vet_visit

Запись визита к ветеринару.

**Параметры**:

| Параметр | Тип | Обязательный | Описание |
| -------- | --- | ------------ | -------- |
| pet_name | string | да | Имя питомца |
| reason | string | да | Причина визита |
| visit_date | string (YYYY-MM-DD) | да | Дата визита |
| status | string | нет | Статус: planned, completed (default: planned) |
| clinic | string | нет | Название клиники |
| notes | string | нет | Заметки |

---

### add_mood_log

Запись о самочувствии питомца.

**Параметры**:

| Параметр | Тип | Обязательный | Описание |
| -------- | --- | ------------ | -------- |
| pet_name | string | да | Имя питомца |
| mood | string | да | Настроение: excellent, good, normal, poor |
| appetite | string | да | Аппетит: good, reduced, none |
| log_date | string (YYYY-MM-DD) | да | Дата наблюдения |
| notes | string | нет | Заметки |

---

### add_document

Запись ссылки на медицинский документ.

**Параметры**:

| Параметр | Тип | Обязательный | Описание |
| -------- | --- | ------------ | -------- |
| pet_name | string | да | Имя питомца |
| document_type | string | да | Тип: passport, analysis, certificate, other |
| url | string | да | Ссылка на документ |
| issued_date | string (YYYY-MM-DD) | нет | Дата выдачи |
| description | string | нет | Описание документа |

---

### add_heat_cycle

Запись о цикле течки.

**Параметры**:

| Параметр | Тип | Обязательный | Описание |
| -------- | --- | ------------ | -------- |
| pet_name | string | да | Имя питомца |
| start_date | string (YYYY-MM-DD) | да | Дата начала |
| end_date | string (YYYY-MM-DD) | нет | Дата окончания |
| notes | string | нет | Заметки |
