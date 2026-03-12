---
name: chatgpt-codex-oauth
description: используй когда нужно встроить в приложение вход через подписку ChatGPT/Codex без ручного API-ключа, через браузерный OAuth flow, и нужно отделить поддержанный путь Codex app-server от внутренних и reverse-engineered вариантов.
---

1. Сначала выбери правильный режим интеграции.
- Если приложение может работать через Codex `app-server`, используй только managed flow: `account/login/start` с `type: "chatgpt"`.
- Если кто-то предлагает передавать в Codex готовые `access_token` через `chatgptAuthTokens`, не используй это: в исходниках Codex этот режим помечен как `[UNSTABLE] FOR OPENAI INTERNAL USE ONLY - DO NOT USE`.
- Если задача требует напрямую повторять OAuth flow OpenAI вне Codex `app-server`, считай это reverse-engineered решением с риском поломки и без публичной гарантии поддержки.

2. Главный вывод, который нужно проговаривать сразу.
- В исследованных источниках подтверждён вход `Sign in with ChatGPT` для самого Codex и клиентов поверх его `app-server`.
- Публичного задокументированного `Sign in with ChatGPT` OAuth-провайдера для произвольных сторонних приложений мы не нашли.
- Значит, корректная трактовка требований такая: пользователь логинится браузером в Codex-контекст, а приложение работает через Codex, не через собственный прямой backend OAuth к OpenAI.
- Требование "без API-ключа" выполнимо как "без ручного ввода `.env`/`OPENAI_API_KEY`". Но не делай архитектурный вывод, что внутри потока вообще никогда не возникает автоматически созданный ключ: официальный help OpenAI прямо пишет, что flow может создать key автоматически.

3. Рекомендуемый путь для продукта.
- Подними Codex `app-server` или клиент поверх него.
- Перед первым рабочим запросом вызови `account/read`.
- Если вернулось `requiresOpenaiAuth=true` и `account=null`, вызови:
```json
{ "method": "account/login/start", "id": 1, "params": { "type": "chatgpt" } }
```
- Получи `authUrl`, отдай пользователю ссылку или открой встроенный браузер.
- Дождись `account/login/completed` с `success=true`, затем `account/updated` с `authMode="chatgpt"`.
- После этого работай через тот же Codex `app-server`; refresh token и локальное хранение остаются на стороне Codex.
- Для выхода используй `account/logout`.
- Для квот и лимитов используй `account/rateLimits/read`.

4. Что именно делает Codex в managed flow.
- Поднимает localhost callback server, по умолчанию на `http://localhost:1455/auth/callback`.
- Строит browser auth URL на `https://auth.openai.com/oauth/authorize`.
- Использует PKCE `S256`, `state` и scope `openid profile email offline_access api.connectors.read api.connectors.invoke`.
- Меняет `authorization_code` на токены через `POST https://auth.openai.com/oauth/token`.
- Сохраняет auth локально и сам делает refresh через тот же token endpoint.
- Рабочий backend для Codex-запросов идёт через `https://chatgpt.com/backend-api`.

5. Что запрещено рекомендовать как "правильную" реализацию.
- Не советуй `.env`, `OPENAI_API_KEY`, copy-paste API key или server-side shared key, если задача именно про подписочный OAuth ChatGPT/Codex.
- Не строй multi-user SaaS поток на `chatgptAuthTokens`: это внутренний unstable API.
- Не обещай, что можно легально и стабильно использовать ChatGPT subscription как публичный OAuth для любого собственного backend без Codex-слоя. В исследованных источниках такого публичного контракта нет.

6. Когда допускается reverse-engineered путь.
- Только если пользователь осознанно принимает риск неофициального решения.
- Только если нужен personal-use инструмент или controlled environment, а не массовый production OAuth для многих пользователей.
- В этом режиме обычно повторяют тот же flow, что у Codex/OpenClaw/community:
  `auth.openai.com/oauth/authorize` -> localhost callback `:1455/auth/callback` -> `auth.openai.com/oauth/token` -> запросы в `chatgpt.com/backend-api`.
- Сторонние проекты `OpenClaw`, `oauth-codex`, `opencode-openai-codex-auth` и `open-hax/codex` подтверждают техническую реализуемость, но это не равно официальной программе OpenAI для third-party OAuth.
- Формулировку OpenClaw про "explicit support" считай утверждением третьей стороны, а не официальной гарантией OpenAI.

7. Как формулировать решение пользователю или команде.
- "Мы делаем вход через браузерный ChatGPT login, без ручного API-ключа."
- "Поддержанный путь для приложения: использовать Codex app-server managed auth."
- "Публичного OAuth-провайдера ChatGPT для любых сторонних backend-интеграций мы не нашли."
- "Если нужен прямой обходной flow без Codex app-server, это reverse-engineered режим с риском хрупкости, блокировок и изменений со стороны OpenAI."

8. Выбор пути по типу продукта.
- Если продукт — локальный desktop/IDE companion вокруг самого Codex, по умолчанию выбирай `app-server`.
- Если продукт — server-side бот, SaaS или мультитенантное приложение, где backend обслуживает много пользователей или workspace'ов, `app-server` почти всегда превращает ChatGPT/Codex auth в глобальную настройку одного инстанса.
- Если каждому workspace или tenant нужен свой подключённый ChatGPT/Codex-аккаунт, архитектурно ближе reverse-path, а не `app-server`.
- При reverse-path сразу проектируй: кто владелец подписки, кто имеет право переподключать её, что делать при logout/refresh failure и как хранить auth state вне памяти процесса.

9. Multimodal-оговорка.
- Фото и image-input через reverse-path выглядят реалистично, если выбранный runtime реально поддерживает `text + image`.
- Голос обычно не получается провести "целиком через reverse" так же просто, как текст. Практичный путь: отдельно транскрибировать аудио, а в reverse-runtime отправлять уже текст.
- Не обещай "полностью без API-ключей", пока отдельно не проверил audio/transcription pipeline. Во многих продуктах текст/фото можно перевести на reverse раньше, чем голос.

10. Если нужно быстро перепроверить источники, смотри их в таком порядке.
- Codex app-server auth surface: `/Users/user/github/codex/codex-rs/app-server/README.md`
- Статус `chatgptAuthTokens` как internal-only: `/Users/user/github/codex/codex-rs/app-server-protocol/src/protocol/v2.rs`
- Низкоуровневый browser login flow Codex: `/Users/user/github/codex/codex-rs/login/src/server.rs`
- Refresh и локальное хранение Codex: `/Users/user/github/codex/codex-rs/core/src/auth.rs`
- Официальный help center про `Sign in with ChatGPT` и auto-generated key: `https://help.openai.com/en/articles/11381614`
- Reverse-engineered reference внутри OpenClaw: `/Users/user/github/openclaw/docs/concepts/oauth.md`
- OpenClaw runtime wiring: `/Users/user/github/openclaw/src/commands/openai-codex-oauth.ts`
