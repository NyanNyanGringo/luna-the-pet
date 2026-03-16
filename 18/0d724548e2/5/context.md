# Session Context

## User Prompts

### Prompt 1

Сделал ревью после реализации всех фаз этапа @specs/005-remove-oauth/ 

Findings

  1. HIGH — После удаления OAuth остались интеграционные тесты, которые всё ещё требуют удалённый callback route. См.
     test_regression_runtime_paths.py#L155 и test_regression_runtime_paths.py#L164.
     В diff удалены auth.py и регистрация роутера в main.py, но тесты...

### Prompt 2

[Request interrupted by user for tool use]

### Prompt 3

Реализуй план

### Prompt 4

Нужно исправить blocker в задаче `specs/005-remove-oauth`, исходя из нового решения: проект ещё не был в проде, dev-среда
  пересоздаётся с нуля, сохранять обратимую историю OAuth не нужно. Вместо починки `downgrade()` надо переписать историю
  миграций так, чтобы `oauth_credential` вообще никогда не существо...

### Prompt 5

Продолжай

