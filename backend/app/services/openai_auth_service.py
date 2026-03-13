"""
Сервис OAuth для OpenAI: PKCE flow, шифрование токенов, fallback на API key.

Реализует полный цикл OAuth 2.0 с PKCE (RFC 7636):
- Генерация code_verifier / code_challenge / state
- Построение authorize URL
- Обмен authorization code на access/refresh tokens
- Прозрачный refresh при истечении access token
- Шифрование токенов через Fernet для хранения в БД
- Fallback: если OAuth недоступен — используется OPENAI_API_KEY

Ограничение: для Fernet требуется OAUTH_ENCRYPTION_KEY (32 байта, base64).
"""

import base64
import hashlib
import logging
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import NotRequired, TypedDict, cast
from urllib.parse import urlencode

import httpx
from backend.app.config import Settings
from backend.app.db.models.family import OAuthCredential
from cryptography.fernet import Fernet
from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Эндпоинты OAuth OpenAI
_AUTHORIZE_URL = "https://auth.openai.com/authorize"
_TOKEN_URL = "https://auth.openai.com/oauth/token"  # noqa: S105

# Минимальная длина code_verifier по RFC 7636
_CODE_VERIFIER_BYTES = 32
_PKCE_CONTEXT_TTL_SECONDS = 900


class TokenData(TypedDict):
    """Ответ token endpoint OpenAI, достаточный для хранения credential."""

    access_token: str
    refresh_token: NotRequired[str]
    expires_in: NotRequired[int]


@dataclass(slots=True)
class PKCEStateContext:
    """Контекст OAuth state для callback.

    Поля:
        code_verifier: PKCE verifier, сгенерированный в /connectai
        workspace_id: ID workspace, к которому привязываются токены
        member_id: Telegram user ID инициатора команды /connectai
        expires_at: UTC-время истечения контекста
    """

    code_verifier: str
    workspace_id: int
    member_id: int
    expires_at: datetime


_pkce_state_context_by_state: dict[str, PKCEStateContext] = {}


def store_pkce_state_context(
    state: str,
    code_verifier: str,
    workspace_id: int,
    member_id: int,
) -> None:
    """Сохраняет PKCE state-контекст до момента OAuth callback.

    Аргументы:
        state: CSRF state из authorize URL
        code_verifier: PKCE code_verifier, связанный с state
        workspace_id: ID workspace инициатора авторизации
        member_id: Telegram user ID инициатора авторизации

    Ошибки:
        ValueError: если state или code_verifier пустые

    Побочные эффекты:
        Обновляет in-memory хранилище state->контекст.
    """
    if not state:
        raise ValueError("OAuth state не может быть пустым")
    if not code_verifier:
        raise ValueError("OAuth code_verifier не может быть пустым")

    now = datetime.now(tz=UTC)
    _drop_expired_pkce_state_contexts(now)
    _pkce_state_context_by_state[state] = PKCEStateContext(
        code_verifier=code_verifier,
        workspace_id=workspace_id,
        member_id=member_id,
        expires_at=now + timedelta(seconds=_PKCE_CONTEXT_TTL_SECONDS),
    )


def consume_pkce_state_context(state: str) -> PKCEStateContext | None:
    """Возвращает и удаляет PKCE state-контекст.

    Аргументы:
        state: CSRF state из OAuth callback

    Возвращает:
        PKCEStateContext | None: контекст для state или None, если не найден/просрочен

    Побочные эффекты:
        Удаляет запись из in-memory хранилища (защита от повторного использования).
    """
    if not state:
        return None

    stored_context = _pkce_state_context_by_state.pop(state, None)
    if stored_context is None:
        return None
    if stored_context.expires_at <= datetime.now(tz=UTC):
        return None
    return stored_context


def _drop_expired_pkce_state_contexts(reference_time: datetime) -> None:
    """Удаляет истёкшие PKCE state-контексты.

    Аргументы:
        reference_time: текущее время UTC для проверки истечения

    Побочные эффекты:
        Очищает in-memory хранилище от устаревших state.
    """
    expired_states = [
        state_key
        for state_key, context in _pkce_state_context_by_state.items()
        if context.expires_at <= reference_time
    ]
    for state_key in expired_states:
        _pkce_state_context_by_state.pop(state_key, None)


def generate_pkce_params() -> dict[str, str]:
    """Генерирует параметры PKCE: code_verifier, code_challenge (S256), state.

    code_verifier: случайная строка >= 43 символов (base64url, 32 байта).
    code_challenge: SHA-256 от code_verifier, закодированный в base64url без padding.
    state: случайная строка для защиты от CSRF.

    Возвращает:
        dict: {"code_verifier": str, "code_challenge": str, "state": str}
    """
    code_verifier = _generate_code_verifier()
    code_challenge = _compute_code_challenge(code_verifier)
    state = secrets.token_urlsafe(16)

    return {
        "code_verifier": code_verifier,
        "code_challenge": code_challenge,
        "state": state,
    }


def _generate_code_verifier() -> str:
    """Генерирует криптографически стойкий code_verifier (base64url, без padding).

    Возвращает:
        str: code_verifier длиной >= 43 символов
    """
    return secrets.token_urlsafe(_CODE_VERIFIER_BYTES)


def _compute_code_challenge(code_verifier: str) -> str:
    """Вычисляет code_challenge = base64url(SHA-256(code_verifier)), без padding.

    Аргументы:
        code_verifier: исходная строка для хэширования

    Возвращает:
        str: code_challenge в формате base64url без '='
    """
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def build_authorize_url(
    client_id: str,
    redirect_uri: str,
    pkce_params: dict[str, str],
) -> str:
    """Строит URL для перенаправления пользователя на страницу авторизации OpenAI.

    Аргументы:
        client_id: OAuth client ID приложения
        redirect_uri: URL обратного вызова после авторизации
        pkce_params: словарь с code_challenge и state из generate_pkce_params()

    Возвращает:
        str: полный URL вида https://auth.openai.com/authorize?...
    """
    query_params = urlencode(
        {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "code_challenge": pkce_params["code_challenge"],
            "code_challenge_method": "S256",
            "state": pkce_params["state"],
            "scope": "openai.public",
        }
    )
    return f"{_AUTHORIZE_URL}?{query_params}"


def encrypt_token(token: str, encryption_key: str) -> str:
    """Шифрует токен с помощью Fernet (симметричное шифрование).

    Аргументы:
        token: открытый токен для шифрования
        encryption_key: Fernet-ключ (base64-encoded, 32 байта)

    Возвращает:
        str: зашифрованная строка (Fernet token)

    Ошибки:
        ValueError: если encryption_key невалиден для Fernet
    """
    fernet = Fernet(encryption_key.encode())
    encrypted_token_bytes: bytes = fernet.encrypt(token.encode())
    return encrypted_token_bytes.decode()


def decrypt_token(encrypted_token: str, encryption_key: str) -> str:
    """Расшифровывает токен, зашифрованный через encrypt_token.

    Аргументы:
        encrypted_token: зашифрованная строка (Fernet token)
        encryption_key: тот же Fernet-ключ, что использовался при шифровании

    Возвращает:
        str: расшифрованный оригинальный токен

    Ошибки:
        cryptography.fernet.InvalidToken: если ключ неверный или данные повреждены
    """
    fernet = Fernet(encryption_key.encode())
    decrypted_token_bytes: bytes = fernet.decrypt(encrypted_token.encode())
    return decrypted_token_bytes.decode()


async def exchange_code_for_tokens(
    session: AsyncSession,
    member_id: int,
    code: str,
    code_verifier: str,
    redirect_uri: str,
) -> OAuthCredential:
    """Обменивает authorization code на access/refresh tokens, сохраняет в БД.

    Выполняет POST-запрос на token endpoint OpenAI, шифрует полученные
    токены через Fernet и сохраняет OAuthCredential в БД.

    Аргументы:
        session: AsyncSession для записи в БД
        member_id: Telegram user ID владельца OAuth-токена
        code: authorization code от OAuth callback
        code_verifier: PKCE code_verifier для подтверждения
        redirect_uri: URL обратного вызова (должен совпадать с authorize)

    Возвращает:
        OAuthCredential: созданная запись с зашифрованными токенами

    Ошибки:
        httpx.HTTPStatusError: если token endpoint вернул ошибку
        ValueError: если OAUTH_ENCRYPTION_KEY или OPENAI_OAUTH_CLIENT_ID не настроены

    Побочные эффекты:
        Создаёт или обновляет OAuthCredential в БД.
        Выполняет HTTP POST на https://auth.openai.com/oauth/token.
    """
    settings = Settings()
    encryption_key = _require_encryption_key(settings)
    client_id = _require_client_id(settings)

    token_data = await _request_tokens(code, code_verifier, redirect_uri, client_id)
    credential = await _upsert_openai_credential(
        session=session,
        member_id=member_id,
        token_data=token_data,
        encryption_key=encryption_key,
    )

    logger.info("OAuth credential сохранён для member_id=%d", member_id)
    return credential


async def _upsert_openai_credential(
    session: AsyncSession,
    member_id: int,
    token_data: TokenData,
    encryption_key: str,
) -> OAuthCredential:
    """Создаёт или обновляет OAuthCredential для member_id/provider=openai.

    Аргументы:
        session: AsyncSession для записи в БД
        member_id: Telegram user ID владельца credential
        token_data: ответ token endpoint с access/refresh/expires_in
        encryption_key: Fernet-ключ для шифрования токенов

    Возвращает:
        OAuthCredential: актуальная запись credential после upsert

    Побочные эффекты:
        Добавляет новую или обновляет существующую запись, выполняет flush.
    """
    existing_credential = await _find_provider_credential(
        session,
        member_id,
        "openai",
    )
    if existing_credential is not None:
        await _update_existing_credential(
            session,
            existing_credential,
            token_data,
            encryption_key,
        )
        return existing_credential

    try:
        return await _insert_new_credential(
            session,
            member_id,
            token_data,
            encryption_key,
        )
    except IntegrityError:
        logger.info(
            "OAuth credential уже создан конкурентной транзакцией member_id=%d",
            member_id,
        )
        concurrent_credential = await _find_provider_credential(
            session,
            member_id,
            "openai",
        )
        if concurrent_credential is None:
            raise
        await _update_existing_credential(
            session,
            concurrent_credential,
            token_data,
            encryption_key,
        )
        return concurrent_credential


async def _insert_new_credential(
    session: AsyncSession,
    member_id: int,
    token_data: TokenData,
    encryption_key: str,
) -> OAuthCredential:
    """Создаёт новую OAuthCredential в savepoint для безопасного upsert.

    Аргументы:
        session: AsyncSession для записи в БД
        member_id: Telegram user ID владельца credential
        token_data: ответ token endpoint с access/refresh/expires_in
        encryption_key: Fernet-ключ для шифрования токенов

    Возвращает:
        OAuthCredential: созданная запись
    """
    new_credential = _build_credential(token_data, member_id, encryption_key)
    async with session.begin_nested():
        session.add(new_credential)
        await session.flush()
    return new_credential


async def _update_existing_credential(
    session: AsyncSession,
    credential: OAuthCredential,
    token_data: TokenData,
    encryption_key: str,
) -> None:
    """Обновляет существующую OAuthCredential и фиксирует active-статус.

    Аргументы:
        session: AsyncSession для записи в БД
        credential: найденная OAuthCredential
        token_data: ответ token endpoint с access/refresh/expires_in
        encryption_key: Fernet-ключ для шифрования токенов
    """
    _update_credential(credential, token_data, encryption_key)
    credential.status = "active"
    await session.flush()


async def get_openai_client(
    session: AsyncSession,
    member_id: int,
) -> AsyncOpenAI:
    """Возвращает AsyncOpenAI клиент: OAuth primary, fallback на API key.

    Логика (из research.md):
    1. Ищет активный OAuthCredential для member_id
    2. Если найден и не истёк — использует access_token
    3. Если истёк — пытается refresh
    4. Если refresh не удался или credential не найден — fallback на OPENAI_API_KEY

    Аргументы:
        session: AsyncSession для чтения credential из БД
        member_id: Telegram user ID инициатора запроса

    Возвращает:
        AsyncOpenAI: настроенный клиент OpenAI

    Побочные эффекты:
        Может обновить OAuthCredential в БД при refresh.
        Может выполнить HTTP-запрос при refresh токена.
    """
    settings = Settings()
    credential = await _find_active_credential(session, member_id)

    if credential is None:
        logger.info(
            "OAuth credential не найден для member_id=%d, fallback",
            member_id,
        )
        return _create_api_key_client(settings)

    return await _resolve_oauth_client(session, credential, settings)


async def _resolve_oauth_client(
    session: AsyncSession,
    credential: OAuthCredential,
    settings: Settings,
) -> AsyncOpenAI:
    """Возвращает клиент по OAuth credential: свежий или после refresh.

    Аргументы:
        session: AsyncSession для обновления credential
        credential: OAuthCredential из БД
        settings: настройки приложения

    Возвращает:
        AsyncOpenAI: клиент с OAuth или API key (fallback)
    """
    encryption_key = settings.OAUTH_ENCRYPTION_KEY
    if encryption_key is None:
        logger.warning("OAUTH_ENCRYPTION_KEY не задан, fallback на API key")
        return _create_api_key_client(settings)

    if not _is_token_expired(credential):
        access_token = decrypt_token(credential.access_token_enc, encryption_key)
        return AsyncOpenAI(api_key=access_token)

    return await _try_refresh_or_fallback(session, credential, settings)


async def _try_refresh_or_fallback(
    session: AsyncSession,
    credential: OAuthCredential,
    settings: Settings,
) -> AsyncOpenAI:
    """Пытается обновить токен; при ошибке — fallback на API key.

    Аргументы:
        session: AsyncSession для обновления credential
        credential: OAuthCredential с истёкшим access token
        settings: настройки приложения

    Возвращает:
        AsyncOpenAI: клиент с обновлённым OAuth или API key (fallback)
    """
    encryption_key = settings.OAUTH_ENCRYPTION_KEY
    if encryption_key is None:
        return _create_api_key_client(settings)

    try:
        refresh_token = decrypt_token(credential.refresh_token_enc, encryption_key)
        token_data = await _refresh_oauth_tokens(refresh_token, settings)
        _update_credential(credential, token_data, encryption_key)
        await session.flush()
        return AsyncOpenAI(api_key=token_data["access_token"])
    except Exception:
        logger.warning(
            "Не удалось обновить OAuth токен для credential_id=%s, fallback",
            getattr(credential, "id", "?"),
        )
        return _create_api_key_client(settings)


def _is_token_expired(credential: OAuthCredential) -> bool:
    """Проверяет, истёк ли access token.

    Аргументы:
        credential: OAuthCredential с expires_at

    Возвращает:
        bool: True если токен истёк или скоро истечёт (запас 60 секунд)
    """
    # Запас 60 секунд, чтобы не использовать токен за секунду до истечения
    buffer = timedelta(seconds=60)
    return datetime.now(tz=UTC) >= credential.expires_at - buffer


def _create_api_key_client(settings: Settings) -> AsyncOpenAI:
    """Создаёт AsyncOpenAI клиент с API key из конфига.

    Аргументы:
        settings: настройки с OPENAI_API_KEY

    Возвращает:
        AsyncOpenAI: клиент с API key
    """
    return AsyncOpenAI(api_key=settings.OPENAI_API_KEY)


async def _find_active_credential(
    session: AsyncSession,
    member_id: int,
) -> OAuthCredential | None:
    """Ищет активный OAuthCredential для пользователя (provider=openai).

    Аргументы:
        session: AsyncSession для запроса
        member_id: Telegram user ID владельца credential

    Возвращает:
        OAuthCredential | None: найденный credential или None
    """
    query = select(OAuthCredential).where(
        OAuthCredential.telegram_user_id == member_id,
        OAuthCredential.provider == "openai",
        OAuthCredential.status == "active",
    )
    result = await session.execute(query)
    return result.scalar_one_or_none()


async def _find_provider_credential(
    session: AsyncSession,
    member_id: int,
    provider: str,
) -> OAuthCredential | None:
    """Ищет OAuthCredential для провайдера без фильтра по статусу.

    Аргументы:
        session: AsyncSession для запроса
        member_id: Telegram user ID владельца credential
        provider: имя OAuth провайдера (например, "openai")

    Возвращает:
        OAuthCredential | None: найденный credential или None
    """
    query = select(OAuthCredential).where(
        OAuthCredential.telegram_user_id == member_id,
        OAuthCredential.provider == provider,
    )
    result = await session.execute(query)
    return result.scalar_one_or_none()


async def _request_tokens(
    code: str,
    code_verifier: str,
    redirect_uri: str,
    client_id: str,
) -> TokenData:
    """Выполняет POST на token endpoint OpenAI для обмена code на токены.

    Аргументы:
        code: authorization code
        code_verifier: PKCE code_verifier
        redirect_uri: URL обратного вызова
        client_id: OAuth client ID

    Возвращает:
        dict: ответ с access_token, refresh_token, expires_in

    Ошибки:
        httpx.HTTPStatusError: при ошибке от token endpoint
    """
    async with httpx.AsyncClient() as http_client:
        response = await http_client.post(
            _TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "code_verifier": code_verifier,
                "redirect_uri": redirect_uri,
                "client_id": client_id,
            },
        )
        response.raise_for_status()
        return cast(TokenData, response.json())


async def _refresh_oauth_tokens(
    refresh_token: str,
    settings: Settings,
) -> TokenData:
    """Обновляет OAuth токены через refresh_token.

    Аргументы:
        refresh_token: действующий refresh token
        settings: настройки с OPENAI_OAUTH_CLIENT_ID

    Возвращает:
        dict: ответ с новым access_token, refresh_token, expires_in

    Ошибки:
        httpx.HTTPStatusError: при ошибке от token endpoint
        ValueError: если OPENAI_OAUTH_CLIENT_ID не задан
    """
    client_id = _require_client_id(settings)

    async with httpx.AsyncClient() as http_client:
        response = await http_client.post(
            _TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": client_id,
            },
        )
        response.raise_for_status()
        return cast(TokenData, response.json())


def _build_credential(
    token_data: TokenData,
    member_id: int,
    encryption_key: str,
) -> OAuthCredential:
    """Создаёт OAuthCredential из ответа token endpoint.

    Аргументы:
        token_data: dict с access_token, refresh_token, expires_in
        member_id: Telegram user ID владельца credential
        encryption_key: Fernet-ключ для шифрования токенов

    Возвращает:
        OAuthCredential: новый объект для сохранения в БД
    """
    expires_in = token_data.get("expires_in", 3600)

    return OAuthCredential(
        telegram_user_id=member_id,
        provider="openai",
        access_token_enc=encrypt_token(token_data["access_token"], encryption_key),
        refresh_token_enc=encrypt_token(token_data["refresh_token"], encryption_key),
        expires_at=datetime.now(tz=UTC) + timedelta(seconds=expires_in),
        status="active",
    )


def _update_credential(
    credential: OAuthCredential,
    token_data: TokenData,
    encryption_key: str,
) -> None:
    """Обновляет поля OAuthCredential после refresh.

    Аргументы:
        credential: существующий OAuthCredential
        token_data: dict с новыми access_token, refresh_token, expires_in
        encryption_key: Fernet-ключ

    Побочные эффекты:
        Мутирует credential:
        access_token_enc, expires_at, updated_at и refresh при наличии.
    """
    expires_in = token_data.get("expires_in", 3600)

    credential.access_token_enc = encrypt_token(
        token_data["access_token"],
        encryption_key,
    )
    refreshed_token = token_data.get("refresh_token")
    if refreshed_token:
        credential.refresh_token_enc = encrypt_token(
            refreshed_token,
            encryption_key,
        )
    credential.expires_at = datetime.now(tz=UTC) + timedelta(
        seconds=expires_in,
    )
    credential.updated_at = datetime.now(tz=UTC)


def _require_encryption_key(settings: Settings) -> str:
    """Возвращает OAUTH_ENCRYPTION_KEY или бросает ValueError.

    Аргументы:
        settings: настройки приложения

    Возвращает:
        str: Fernet encryption key

    Ошибки:
        ValueError: если OAUTH_ENCRYPTION_KEY не задан
    """
    if settings.OAUTH_ENCRYPTION_KEY is None:
        raise ValueError(
            "OAUTH_ENCRYPTION_KEY не задан — невозможно шифровать OAuth-токены"
        )
    return settings.OAUTH_ENCRYPTION_KEY


def _require_client_id(settings: Settings) -> str:
    """Возвращает OPENAI_OAUTH_CLIENT_ID или бросает ValueError.

    Аргументы:
        settings: настройки приложения

    Возвращает:
        str: OAuth client ID

    Ошибки:
        ValueError: если OPENAI_OAUTH_CLIENT_ID не задан
    """
    if settings.OPENAI_OAUTH_CLIENT_ID is None:
        raise ValueError("OPENAI_OAUTH_CLIENT_ID не задан — невозможно выполнить OAuth")
    return settings.OPENAI_OAUTH_CLIENT_ID
