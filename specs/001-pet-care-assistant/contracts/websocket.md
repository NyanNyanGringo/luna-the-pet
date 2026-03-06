# WebSocket контракт чата

**URL**: `wss://{host}/ws/chat`
**Аутентификация**: JWT в query параметре `?token=eyJ...`

## Подключение

```
wss://luna.example.com/ws/chat?token=eyJ...
```

При невалидном или истёкшем токене — закрытие с кодом 4001.

## Сообщения клиент -> сервер

### Отправка сообщения

```json
{
  "type": "message",
  "text": "Какие прививки были у Луны?"
}
```

## Сообщения сервер -> клиент

### Стриминг ответа (token-by-token)

```json
{"type": "stream_start", "message_id": "msg-123"}
{"type": "stream_token", "message_id": "msg-123", "token": "У "}
{"type": "stream_token", "message_id": "msg-123", "token": "Луны "}
{"type": "stream_token", "message_id": "msg-123", "token": "есть "}
{"type": "stream_end", "message_id": "msg-123", "full_text": "У Луны есть следующие вакцинации: ..."}
```

### Ошибка

```json
{
  "type": "error",
  "message": "Не удалось обработать сообщение. Попробуйте ещё раз."
}
```

### Tool call уведомление (опционально, для UX)

```json
{
  "type": "tool_call",
  "message_id": "msg-123",
  "tool_name": "get_vaccination_history",
  "status": "running"
}
```

## Heartbeat

Клиент отправляет ping каждые 30 секунд. Сервер отвечает pong.
Если pong не получен в течение 10 секунд — переподключение.

```json
{"type": "ping"}
{"type": "pong"}
```
