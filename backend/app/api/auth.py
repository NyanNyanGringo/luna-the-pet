"""
OAuth callback endpoint для OpenAI.

Принимает GET /api/auth/openai/callback с параметрами code и state,
обменивает authorization code на токены и сохраняет в БД.

Требует предварительно сохранённые PKCE параметры (code_verifier, state)
в серверном хранилище для верификации.
"""

import logging

from backend.app.api.deps import get_db
from backend.app.config import Settings
from backend.app.services.openai_auth_service import (
    PKCEStateContext,
    consume_pkce_state_context,
    exchange_code_for_tokens,
)
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

auth_router = APIRouter(prefix="/api/auth", tags=["auth"])


@auth_router.get("/openai/callback")
async def openai_oauth_callback(
    code: str = Query(..., description="Authorization code от OpenAI"),
    state: str = Query(..., description="State для CSRF-верификации"),
    session: AsyncSession = Depends(get_db),  # noqa: B008
) -> dict[str, str]:
    """Обрабатывает OAuth callback от OpenAI: обмен code на tokens.

    Аргументы:
        code: authorization code из query string
        state: CSRF state из query string
        session: AsyncSession (DI через Depends)

    Возвращает:
        dict: {"status": "connected"} при успехе

    Ошибки:
        HTTPException(400): если OAuth exchange не удался
        HTTPException(500): если OAUTH_ENCRYPTION_KEY или CLIENT_ID не настроены

    Побочные эффекты:
        Сохраняет зашифрованные OAuth-токены в БД.
        Выполняет HTTP POST на OpenAI token endpoint.
    """
    settings = Settings()
    pkce_context = _consume_pkce_state_context_or_400(state)
    redirect_uri = _build_redirect_uri(settings)

    try:
        await exchange_code_for_tokens(
            session=session,
            member_id=pkce_context.member_id,
            code=code,
            code_verifier=pkce_context.code_verifier,
            redirect_uri=redirect_uri,
        )
        await session.commit()
        logger.info(
            "OAuth подключение завершено для workspace_id=%d member_id=%d",
            pkce_context.workspace_id,
            pkce_context.member_id,
        )
        return {"status": "connected"}
    except ValueError as validation_error:
        logger.error("Ошибка конфигурации OAuth: %s", validation_error)
        raise HTTPException(
            status_code=500,
            detail=str(validation_error),
        ) from validation_error
    except HTTPException:
        raise
    except Exception as exchange_error:
        logger.exception("Ошибка обмена OAuth code на токены")
        raise HTTPException(
            status_code=400,
            detail="Не удалось обменять код авторизации",
        ) from exchange_error


def _consume_pkce_state_context_or_400(state: str) -> PKCEStateContext:
    """Возвращает PKCE-контекст по state или бросает HTTP 400.

    Аргументы:
        state: CSRF state из query-параметра callback

    Возвращает:
        PKCEStateContext: сохранённый контекст авторизации

    Ошибки:
        HTTPException(400): если state отсутствует, не найден или истёк
    """
    pkce_context = consume_pkce_state_context(state)
    if pkce_context is None:
        raise HTTPException(
            status_code=400,
            detail="Некорректный или устаревший OAuth state",
        )
    return pkce_context


def _build_redirect_uri(settings: Settings) -> str:
    """Строит redirect URI на основе WEBHOOK_URL из конфига.

    Аргументы:
        settings: настройки с WEBHOOK_URL

    Возвращает:
        str: URL для OAuth callback (с путём /api/auth/openai/callback)
    """
    base_url = settings.WEBHOOK_URL or "http://localhost:8000"
    # Убираем trailing /webhook если есть — нам нужен базовый URL
    base_url = base_url.replace("/webhook", "")
    return f"{base_url}/api/auth/openai/callback"
