---
name: code-review-noodle-brain-principles
description: используй данные принципы когда делаешь code-review.
---

Прочитай указанные ниже файлы, в них содержатся принципы ревью

# Шаг I. Прочитай все файлы из папки `.../principles/*`:

## Core

- [[principles/foundational-thinking]]
- [[principles/redesign-from-first-principles]]
- [[principles/subtract-before-you-add]]
- [[principles/outcome-oriented-execution]]
- [[principles/experience-first]]
- [[principles/exhaust-the-design-space]]

## Architecture

- [[principles/boundary-discipline]]
- [[principles/make-operations-idempotent]]
- [[principles/migrate-callers-then-delete-legacy-apis]]
- [[principles/serialize-shared-state-mutations]]

## Verification

- [[principles/prove-it-works]]
- [[principles/fix-root-causes]]

## Delegation

- [[principles/cost-aware-delegation]]
- [[principles/guard-the-context-window]]
- [[principles/never-block-on-the-human]]

## Meta

- [[principles/encode-lessons-in-structure]]


# Шаг II. Определи scope и intent

Ключевое – ревьюеры атакуют не саму идею, а то, насколько хорошо реализация соответствует намерению автора.

# Шаг III. Спаун ревьюеров в зависимости от размера изменений

меньше 50 строк – 1 ревьюер (Skeptic)
50–200 строк – 2 (Skeptic + Architect)
200+ строк – 3 (Skeptic + Architect + Minimalist)

Каждый ревьюер – это отдельный процесс CLI противоположной модели с конкретным промптом и ролью. Все запускаются параллельно.

# Шаг IV. Синтез вердикта. Дедупликация находок, сортировка по severity:

PASS – нет критичных проблем
CONTESTED – критичные есть, но ревьюеры не согласны между собой
REJECT – консенсус по критичным проблемам

# Шаг V. Финальное суждение основной модели.

Она принимает или отклоняет каждую находку ревьюеров, отмечая false positives и overreach.

Модели проверяют друг друга, у каждой свои слепые пятна, и пересечение находок даёт более надёжный результат.
