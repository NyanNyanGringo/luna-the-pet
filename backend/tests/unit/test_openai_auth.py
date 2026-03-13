"""Тесты OAuth flow в workspace-centric режиме."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from backend.app.db.models.family import OAuthCredential
from backend.app.db.models.workspace import Workspace, WorkspaceMember
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


def _make_message() -> MagicMock:
    """Создаёт mock Message для /connectai."""
    message = MagicMock()
    message.answer = AsyncMock()
    return message


async def _create_workspace(session: AsyncSession) -> Workspace:
    """Создаёт workspace для OAuth тестов."""
    workspace = Workspace(
        telegram_chat_id=-100777888999,
        title="OAuth Workspace",
    )
    session.add(workspace)
    await session.flush()
    return workspace


async def _create_member(
    session: AsyncSession,
    workspace_id: int,
    telegram_user_id: int,
) -> WorkspaceMember:
    """Создаёт участника workspace для OAuth тестов."""
    member = WorkspaceMember(
        workspace_id=workspace_id,
        telegram_user_id=telegram_user_id,
        telegram_first_name=f"user-{telegram_user_id}",
    )
    session.add(member)
    await session.flush()
    return member


class TestGetOpenAiClient:
    """Проверки выбора клиента OAuth/API-key."""

    async def test_falls_back_to_api_key_when_no_oauth(self) -> None:
        """Без OAuth credential сервис возвращает API-key клиент."""
        from backend.app.services.openai_auth_service import get_openai_client

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        client = await get_openai_client(mock_session, member_id=1)
        assert client is not None


class TestExchangeCodeForTokens:
    """Проверки сохранения OAuthCredential по telegram_user_id."""

    async def test_upserts_credential_for_member(
        self,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """exchange_code_for_tokens создаёт/обновляет запись на member_id."""
        from backend.app.services.openai_auth_service import exchange_code_for_tokens

        workspace = await _create_workspace(db_session)
        member = await _create_member(db_session, workspace.id, telegram_user_id=501)
        monkeypatch.setenv("OPENAI_OAUTH_CLIENT_ID", "client-test")
        monkeypatch.setenv(
            "OAUTH_ENCRYPTION_KEY",
            "zvQj4sQ49wQik2P8nqsz2pF-R4vV58L_8cFUVh3h9V8=",
        )

        token_payload = {
            "access_token": "access-1",
            "refresh_token": "refresh-1",
            "expires_in": 3600,
        }

        with patch(
            "backend.app.services.openai_auth_service._request_tokens",
            new=AsyncMock(return_value=token_payload),
        ):
            credential = await exchange_code_for_tokens(
                session=db_session,
                member_id=member.telegram_user_id,
                code="code-1",
                code_verifier="verifier-1",
                redirect_uri="https://example.com/api/auth/openai/callback",
            )

        assert credential.telegram_user_id == member.telegram_user_id
        persisted_credential = await db_session.scalar(
            select(OAuthCredential).where(
                OAuthCredential.telegram_user_id == member.telegram_user_id,
                OAuthCredential.provider == "openai",
            )
        )
        assert persisted_credential is not None

    async def test_creates_separate_credentials_for_different_members(
        self,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Разные участники не перезаписывают credential друг друга."""
        from backend.app.services.openai_auth_service import exchange_code_for_tokens

        workspace = await _create_workspace(db_session)
        first_member = await _create_member(
            db_session,
            workspace.id,
            telegram_user_id=601,
        )
        second_member = await _create_member(
            db_session,
            workspace.id,
            telegram_user_id=602,
        )
        monkeypatch.setenv("OPENAI_OAUTH_CLIENT_ID", "client-test")
        monkeypatch.setenv(
            "OAUTH_ENCRYPTION_KEY",
            "zvQj4sQ49wQik2P8nqsz2pF-R4vV58L_8cFUVh3h9V8=",
        )

        with patch(
            "backend.app.services.openai_auth_service._request_tokens",
            new=AsyncMock(
                side_effect=[
                    {
                        "access_token": "member-1-access",
                        "refresh_token": "member-1-refresh",
                        "expires_in": 3600,
                    },
                    {
                        "access_token": "member-2-access",
                        "refresh_token": "member-2-refresh",
                        "expires_in": 3600,
                    },
                ]
            ),
        ):
            await exchange_code_for_tokens(
                session=db_session,
                member_id=first_member.telegram_user_id,
                code="code-1",
                code_verifier="verifier-1",
                redirect_uri="https://example.com/api/auth/openai/callback",
            )
            await exchange_code_for_tokens(
                session=db_session,
                member_id=second_member.telegram_user_id,
                code="code-2",
                code_verifier="verifier-2",
                redirect_uri="https://example.com/api/auth/openai/callback",
            )

        credentials = (
            (
                await db_session.execute(
                    select(OAuthCredential).order_by(OAuthCredential.telegram_user_id)
                )
            )
            .scalars()
            .all()
        )
        assert [item.telegram_user_id for item in credentials] == [601, 602]


class TestConnectAiHandler:
    """Проверки /connectai в group-flow."""

    async def test_connectai_builds_link_with_workspace_context(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """/connectai сохраняет PKCE контекст с workspace_id и отправляет URL."""
        from backend.app.bot.handlers.commands import handle_connectai

        monkeypatch.setenv("OPENAI_OAUTH_CLIENT_ID", "client-test")
        message = _make_message()
        workspace = Workspace(telegram_chat_id=-1001, title="Test")
        workspace.id = 77
        member = MagicMock(telegram_user_id=123)

        with (
            patch(
                "backend.app.bot.handlers.commands.generate_pkce_params",
                return_value={
                    "state": "state-1",
                    "code_verifier": "verifier-1",
                    "code_challenge": "challenge-1",
                },
            ),
            patch(
                "backend.app.bot.handlers.commands.store_pkce_state_context",
            ) as store_ctx_mock,
            patch(
                "backend.app.bot.handlers.commands.build_authorize_url",
                return_value="https://auth.example/link",
            ),
        ):
            await handle_connectai(
                message=message,
                session=AsyncMock(spec=AsyncSession),
                workspace=workspace,
                member=member,
            )

        store_ctx_mock.assert_called_once_with(
            state="state-1",
            code_verifier="verifier-1",
            workspace_id=77,
            member_id=123,
        )
        message.answer.assert_awaited_once()


class TestAuthCallback:
    """Проверки callback endpoint."""

    async def test_callback_passes_workspace_id_to_exchange(self) -> None:
        """Callback передаёт member_id из PKCE-контекста в OAuth upsert."""
        from backend.app.api.auth import openai_oauth_callback
        from backend.app.services.openai_auth_service import PKCEStateContext

        context = PKCEStateContext(
            code_verifier="verifier",
            workspace_id=5,
            member_id=10,
            expires_at=datetime.now(tz=UTC) + timedelta(minutes=5),
        )

        with (
            patch(
                "backend.app.api.auth.consume_pkce_state_context",
                return_value=context,
            ),
            patch(
                "backend.app.api.auth.exchange_code_for_tokens",
                new=AsyncMock(),
            ) as exchange_mock,
        ):
            response = await openai_oauth_callback(
                code="code",
                state="state",
                session=AsyncMock(spec=AsyncSession),
            )

        assert response == {"status": "connected"}
        _, kwargs = exchange_mock.await_args
        assert kwargs["member_id"] == 10
