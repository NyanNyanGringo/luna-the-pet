"""
Тесты OAuth-сервиса для OpenAI — T147, T149, T150.

Покрывает:
- T147: PKCE генерация (code_verifier, code_challenge, state),
  build_authorize_url, encrypt/decrypt токенов, get_openai_client
- T149: /connectai хендлер — отправка ссылки и ошибка без client_id
- T150: brain.get_ai_client — делегирование к openai_auth_service

Все внешние вызовы (HTTP, OpenAI API) мокируются через unittest.mock.
"""

import re
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# ═══════════════════════════════════════════════════════════════════════════════
# T147: PKCE параметры — generate_pkce_params
# ═══════════════════════════════════════════════════════════════════════════════


class TestGeneratePkceParams:
    """Тесты генерации PKCE параметров (code_verifier, code_challenge, state)."""

    def test_code_verifier_length_at_least_43(self) -> None:
        """code_verifier должен быть длиной >= 43 символов (RFC 7636)."""
        from backend.app.services.openai_auth_service import generate_pkce_params

        params = generate_pkce_params()

        assert len(params["code_verifier"]) >= 43

    def test_code_challenge_is_valid_base64url(self) -> None:
        """code_challenge должен быть валидной base64url строкой без padding."""
        from backend.app.services.openai_auth_service import generate_pkce_params

        params = generate_pkce_params()
        challenge = params["code_challenge"]

        # base64url содержит только [A-Za-z0-9_-], без padding '='
        assert re.fullmatch(r"[A-Za-z0-9_-]+", challenge) is not None

    def test_state_is_non_empty_string(self) -> None:
        """state должен быть непустой строкой для защиты от CSRF."""
        from backend.app.services.openai_auth_service import generate_pkce_params

        params = generate_pkce_params()

        assert isinstance(params["state"], str)
        assert len(params["state"]) > 0


# ═══════════════════════════════════════════════════════════════════════════════
# T147: build_authorize_url
# ═══════════════════════════════════════════════════════════════════════════════


class TestBuildAuthorizeUrl:
    """Тесты построения URL авторизации OAuth."""

    def _build_url(self) -> str:
        """Вспомогательный метод: строит URL с тестовыми параметрами."""
        from backend.app.services.openai_auth_service import (
            build_authorize_url,
            generate_pkce_params,
        )

        pkce_params = generate_pkce_params()
        return build_authorize_url(
            client_id="test-client-id",
            redirect_uri="https://example.com/callback",
            pkce_params=pkce_params,
        )

    def test_url_starts_with_openai_authorize(self) -> None:
        """URL должен начинаться с https://auth.openai.com/authorize."""
        url = self._build_url()

        assert url.startswith("https://auth.openai.com/authorize")

    def test_url_contains_required_params(self) -> None:
        """URL должен содержать client_id, redirect_uri, code_challenge, state."""
        url = self._build_url()

        assert "client_id=test-client-id" in url
        assert "redirect_uri=" in url
        assert "code_challenge=" in url
        assert "state=" in url

    def test_url_contains_response_type_and_challenge_method(self) -> None:
        """URL должен содержать response_type=code и code_challenge_method=S256."""
        url = self._build_url()

        assert "response_type=code" in url
        assert "code_challenge_method=S256" in url


# ═══════════════════════════════════════════════════════════════════════════════
# T147: encrypt / decrypt токенов
# ═══════════════════════════════════════════════════════════════════════════════


class TestEncryptDecrypt:
    """Тесты шифрования и дешифрования токенов через Fernet."""

    def _make_key(self) -> str:
        """Генерирует валидный Fernet-ключ для тестов."""
        return Fernet.generate_key().decode()

    def test_roundtrip_encrypt_decrypt(self) -> None:
        """Зашифрованный токен должен расшифровываться обратно в оригинал."""
        from backend.app.services.openai_auth_service import (
            decrypt_token,
            encrypt_token,
        )

        key = self._make_key()
        original = "sk-test-token-12345"

        encrypted = encrypt_token(original, key)
        decrypted = decrypt_token(encrypted, key)

        assert decrypted == original

    def test_wrong_key_raises_error(self) -> None:
        """Дешифрование чужим ключом должно вызвать ошибку."""
        from backend.app.services.openai_auth_service import (
            decrypt_token,
            encrypt_token,
        )

        key_one = self._make_key()
        key_two = self._make_key()
        original = "sk-test-token-12345"

        encrypted = encrypt_token(original, key_one)

        with pytest.raises(InvalidToken):
            decrypt_token(encrypted, key_two)

    def test_encrypted_differs_from_original(self) -> None:
        """Зашифрованный текст не должен совпадать с оригиналом."""
        from backend.app.services.openai_auth_service import encrypt_token

        key = self._make_key()
        original = "sk-test-token-12345"

        encrypted = encrypt_token(original, key)

        assert encrypted != original


# ═══════════════════════════════════════════════════════════════════════════════
# T147: get_openai_client — получение AI-клиента с OAuth / fallback
# ═══════════════════════════════════════════════════════════════════════════════


def _make_oauth_credential(
    *,
    access_token: str = "enc-access",
    refresh_token: str = "enc-refresh",
    expires_at: datetime | None = None,
    status: str = "active",
) -> MagicMock:
    """Создаёт мок OAuthCredential.

    Аргументы:
        access_token: зашифрованный access token
        refresh_token: зашифрованный refresh token
        expires_at: время истечения токена (default: +1 час)
        status: статус credential

    Возвращает:
        MagicMock: мок OAuthCredential с заданными атрибутами
    """
    if expires_at is None:
        expires_at = datetime.now(tz=UTC) + timedelta(hours=1)

    credential = MagicMock()
    credential.access_token_enc = access_token
    credential.refresh_token_enc = refresh_token
    credential.expires_at = expires_at
    credential.status = status
    return credential


class TestGetOpenaiClient:
    """Тесты получения AsyncOpenAI клиента с OAuth / fallback на API key."""

    @pytest.fixture
    def encryption_key(self, monkeypatch: pytest.MonkeyPatch) -> str:
        """Устанавливает OAUTH_ENCRYPTION_KEY в окружение и возвращает его."""
        key = Fernet.generate_key().decode()
        monkeypatch.setenv("OAUTH_ENCRYPTION_KEY", key)
        return key

    @pytest.mark.usefixtures("encryption_key")
    async def test_active_oauth_returns_client_with_oauth_token(
        self,
        encryption_key: str,
    ) -> None:
        """С активным OAuth credential возвращает AsyncOpenAI с OAuth token."""
        from backend.app.services.openai_auth_service import (
            encrypt_token,
            get_openai_client,
        )

        access_token = "test-oauth-access-token"
        encrypted_access = encrypt_token(access_token, encryption_key)
        encrypted_refresh = encrypt_token("test-refresh", encryption_key)

        credential = _make_oauth_credential(
            access_token=encrypted_access,
            refresh_token=encrypted_refresh,
            # expires_at в будущем — токен не истёк
            expires_at=datetime.now(tz=UTC) + timedelta(hours=1),
        )

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = credential
        mock_session.execute.return_value = mock_result

        client = await get_openai_client(mock_session, family_id=1)

        # Клиент должен использовать OAuth access token
        assert client.api_key == access_token

    @pytest.mark.usefixtures("encryption_key")
    async def test_expired_oauth_refreshes_token(
        self,
        encryption_key: str,
    ) -> None:
        """С истёкшим OAuth credential делает refresh и возвращает клиент."""
        from backend.app.services.openai_auth_service import (
            encrypt_token,
            get_openai_client,
        )

        old_access = encrypt_token("old-access", encryption_key)
        refresh_token_value = "test-refresh-token"
        encrypted_refresh = encrypt_token(refresh_token_value, encryption_key)

        # Токен истёк
        credential = _make_oauth_credential(
            access_token=old_access,
            refresh_token=encrypted_refresh,
            expires_at=datetime.now(tz=UTC) - timedelta(hours=1),
        )

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = credential
        mock_session.execute.return_value = mock_result

        new_access_token = "new-refreshed-access-token"
        refresh_response = {
            "access_token": new_access_token,
            "refresh_token": "new-refresh-token",
            "expires_in": 3600,
        }

        with patch(
            "backend.app.services.openai_auth_service._refresh_oauth_tokens",
            new_callable=AsyncMock,
            return_value=refresh_response,
        ):
            client = await get_openai_client(mock_session, family_id=1)

        assert client.api_key == new_access_token

    async def test_no_oauth_falls_back_to_api_key(self) -> None:
        """Без OAuth credential возвращает клиент с API key из конфига."""
        from backend.app.services.openai_auth_service import get_openai_client

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        client = await get_openai_client(mock_session, family_id=1)

        # Должен использовать OPENAI_API_KEY из Settings
        assert client.api_key == "sk-test-session-import-key"

    @pytest.mark.usefixtures("encryption_key")
    async def test_failed_refresh_falls_back_to_api_key(
        self,
        encryption_key: str,
    ) -> None:
        """При ошибке refresh — fallback на API key с warning в логе."""
        from backend.app.services.openai_auth_service import (
            encrypt_token,
            get_openai_client,
        )

        old_access = encrypt_token("old-access", encryption_key)
        encrypted_refresh = encrypt_token("test-refresh", encryption_key)

        # Токен истёк
        credential = _make_oauth_credential(
            access_token=old_access,
            refresh_token=encrypted_refresh,
            expires_at=datetime.now(tz=UTC) - timedelta(hours=1),
        )

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = credential
        mock_session.execute.return_value = mock_result

        with (
            patch(
                "backend.app.services.openai_auth_service._refresh_oauth_tokens",
                new_callable=AsyncMock,
                side_effect=Exception("refresh failed"),
            ),
            patch("backend.app.services.openai_auth_service.logger") as mock_logger,
        ):
            client = await get_openai_client(mock_session, family_id=1)

        # Fallback на API key
        assert client.api_key == "sk-test-session-import-key"
        # Должен быть warning в логе
        mock_logger.warning.assert_called()


# ═══════════════════════════════════════════════════════════════════════════════
# T149: /connectai хендлер
# ═══════════════════════════════════════════════════════════════════════════════


def _make_connectai_message(
    user_id: int = 123456789,
    first_name: str = "Тест",
) -> MagicMock:
    """Создаёт мок Message для команды /connectai.

    Аргументы:
        user_id: Telegram user ID
        first_name: имя пользователя

    Возвращает:
        MagicMock: мок Message с настроенным from_user и answer
    """
    message = MagicMock()
    message.from_user = MagicMock(id=user_id, first_name=first_name)
    message.answer = AsyncMock()
    return message


class TestConnectaiHandler:
    """Тесты обработчика команды /connectai."""

    async def test_connectai_sends_oauth_link(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """/connectai отправляет ссылку OAuth при наличии OPENAI_OAUTH_CLIENT_ID."""
        monkeypatch.setenv("OPENAI_OAUTH_CLIENT_ID", "test-oauth-client")
        monkeypatch.setenv("WEBHOOK_URL", "https://example.com/webhook")

        from backend.app.bot.handlers.commands import handle_connectai

        message = _make_connectai_message()
        mock_session = AsyncMock()

        # Мокируем get_member чтобы вернуть участника
        mock_member = MagicMock()
        mock_member.family_id = 1

        with patch(
            "backend.app.bot.handlers.commands.get_member",
            new_callable=AsyncMock,
            return_value=mock_member,
        ):
            await handle_connectai(message, mock_session)

        # Должен отправить сообщение со ссылкой
        message.answer.assert_called_once()
        sent_text = message.answer.call_args[0][0]
        assert "https://auth.openai.com/authorize" in sent_text

    async def test_connectai_without_client_id_shows_error(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """/connectai без OPENAI_OAUTH_CLIENT_ID сообщает об ошибке."""
        # OPENAI_OAUTH_CLIENT_ID уже удалён autouse фикстурой
        monkeypatch.delenv("OPENAI_OAUTH_CLIENT_ID", raising=False)

        from backend.app.bot.handlers.commands import handle_connectai

        message = _make_connectai_message()
        mock_session = AsyncMock()

        mock_member = MagicMock()
        mock_member.family_id = 1

        with patch(
            "backend.app.bot.handlers.commands.get_member",
            new_callable=AsyncMock,
            return_value=mock_member,
        ):
            await handle_connectai(message, mock_session)

        message.answer.assert_called_once()
        sent_text = message.answer.call_args[0][0]
        # Сообщение должно указывать на отсутствие настройки OAuth
        assert "не настроен" in sent_text.lower() or "oauth" in sent_text.lower()

    async def test_callback_uses_verifier_saved_by_connectai(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """/connectai должен сохранять verifier по state для последующего callback."""
        monkeypatch.setenv("OPENAI_OAUTH_CLIENT_ID", "test-oauth-client")
        monkeypatch.setenv("WEBHOOK_URL", "https://example.com/webhook")

        from backend.app.api.auth import openai_oauth_callback
        from backend.app.bot.handlers.commands import handle_connectai

        message = _make_connectai_message()
        connectai_session = AsyncMock(spec=AsyncSession)
        callback_session = AsyncMock(spec=AsyncSession)
        callback_session.commit = AsyncMock()

        mock_member = MagicMock()
        mock_member.family_id = 1
        pkce_params = {
            "code_verifier": "stored-verifier-123",
            "code_challenge": "challenge-123",
            "state": "state-123",
        }

        with (
            patch(
                "backend.app.bot.handlers.commands.get_member",
                new_callable=AsyncMock,
                return_value=mock_member,
            ),
            patch(
                "backend.app.bot.handlers.commands.generate_pkce_params",
                return_value=pkce_params,
            ),
        ):
            await handle_connectai(message, connectai_session)

        with patch(
            "backend.app.api.auth.exchange_code_for_tokens",
            new_callable=AsyncMock,
        ) as mock_exchange:
            await openai_oauth_callback(
                code="oauth-code",
                state=pkce_params["state"],
                session=callback_session,
            )

        used_verifier = mock_exchange.await_args.kwargs["code_verifier"]
        assert used_verifier == pkce_params["code_verifier"]


class TestExchangeCodeForTokensUpsert:
    """Регрессии сохранения OAuthCredential при повторном callback."""

    async def test_exchange_code_for_tokens_upserts_existing_credential(
        self,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Повторный OAuth callback не должен ломаться на UNIQUE.

        Проверяет ограничение для пары family_id + provider.
        """
        from backend.app.db.models.family import OAuthCredential
        from backend.app.services.family_service import get_or_create_family
        from backend.app.services.openai_auth_service import exchange_code_for_tokens

        family = await get_or_create_family(db_session)
        monkeypatch.setenv("OPENAI_OAUTH_CLIENT_ID", "test-client-id")
        monkeypatch.setenv(
            "OAUTH_ENCRYPTION_KEY",
            Fernet.generate_key().decode(),
        )

        token_responses = [
            {
                "access_token": "access-token-1",
                "refresh_token": "refresh-token-1",
                "expires_in": 3600,
            },
            {
                "access_token": "access-token-2",
                "refresh_token": "refresh-token-2",
                "expires_in": 3600,
            },
        ]

        with patch(
            "backend.app.services.openai_auth_service._request_tokens",
            new_callable=AsyncMock,
            side_effect=token_responses,
        ):
            first_credential = await exchange_code_for_tokens(
                session=db_session,
                family_id=family.id,
                code="code-1",
                code_verifier="verifier-1",
                redirect_uri="https://example.com/api/auth/openai/callback",
            )
            second_credential = await exchange_code_for_tokens(
                session=db_session,
                family_id=family.id,
                code="code-2",
                code_verifier="verifier-2",
                redirect_uri="https://example.com/api/auth/openai/callback",
            )

        result = await db_session.execute(
            select(OAuthCredential).where(
                OAuthCredential.family_id == family.id,
                OAuthCredential.provider == "openai",
            )
        )
        credentials = result.scalars().all()

        assert len(credentials) == 1
        assert second_credential.id == first_credential.id


# ═══════════════════════════════════════════════════════════════════════════════
# T150: brain.get_ai_client
# ═══════════════════════════════════════════════════════════════════════════════


class TestGetAiClient:
    """Тесты функции brain.get_ai_client — делегирование к openai_auth_service."""

    async def test_get_ai_client_delegates_to_auth_service(self) -> None:
        """get_ai_client вызывает openai_auth_service.get_openai_client."""
        from backend.app.agent.brain import get_ai_client

        mock_session = AsyncMock()
        mock_client = MagicMock()

        with patch(
            "backend.app.agent.brain.get_openai_client",
            new_callable=AsyncMock,
            return_value=mock_client,
        ) as mock_get:
            result = await get_ai_client(mock_session, family_id=42)

        mock_get.assert_called_once_with(mock_session, family_id=42)
        assert result is mock_client
