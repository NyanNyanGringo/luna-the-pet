# Session Context

## User Prompts

### Prompt 1

Implement the following plan:

# Удалить инструменты документов (add_document, get_documents)

## Контекст
Бот не умеет принимать фотографии — инструмент `add_document` требует `url`, что бесполезно без обработки файлов. Убираем до реализации приёма фото.

## Файлы и изменения

### 1. `backend/app/agent/tools.py`
- Удалить `_add_doc...

### Prompt 2

Бот путается в полях, которые обязательные, а какие нет. Давай для всех tools сделаем ему подсказку. Пример было

def _add_diet_tool() -> dict:
    """Определение инструмента записи диеты."""
    return {
        "type": "function",
        "name": "add_diet",
        "description": "Добавить запись о диете питомца.",
        "parameters": {
          ...

### Prompt 3

Обнови промпт на английском, чтобы он был схож с русским в @backend/app/agent/prompts.py

