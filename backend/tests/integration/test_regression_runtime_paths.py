"""Регрессионные тесты runtime-путей запуска backend.

Проверяет три инварианта:
1) Settings использует только корневой `.env` проекта.
2) локальный `backend/.env` игнорируется.
3) `import app.main` работает при запуске из каталога backend.
"""

from __future__ import annotations

import importlib
import os
import subprocess
import sys
from pathlib import Path

from httpx import ASGITransport, AsyncClient

PROJECT_ROOT_DIRECTORY = Path(__file__).resolve().parents[3]
BACKEND_WORKING_DIRECTORY = PROJECT_ROOT_DIRECTORY / "backend"
ROOT_ENV_FILE_PATH = PROJECT_ROOT_DIRECTORY / ".env"
BACKEND_ENV_FILE_PATH = BACKEND_WORKING_DIRECTORY / ".env"


def _run_python_script(
    script_text: str,
    backend_working_directory: Path,
    subprocess_environment: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    """Запускает python -c в изолированном backend-каталоге."""
    return subprocess.run(
        [sys.executable, "-c", script_text],
        cwd=backend_working_directory,
        env=subprocess_environment,
        check=False,
        text=True,
        capture_output=True,
    )


def _build_subprocess_environment() -> dict[str, str]:
    """Собирает окружение subprocess без обязательных переменных Settings."""
    subprocess_environment = os.environ.copy()
    subprocess_environment["PYTHONPATH"] = str(BACKEND_WORKING_DIRECTORY)
    for variable_name in ("DATABASE_URL", "TELEGRAM_BOT_TOKEN", "OPENAI_API_KEY"):
        subprocess_environment.pop(variable_name, None)
    return subprocess_environment


def test_settings_uses_only_single_root_env_file_path() -> None:
    """Settings должен ссылаться только на корневой .env проекта."""
    settings_module = importlib.import_module("app.config")
    settings_class = settings_module.Settings

    assert settings_class.model_config["env_file"] == str(ROOT_ENV_FILE_PATH)


def test_settings_loads_root_env_when_cwd_is_backend() -> None:
    """Settings должен загружаться из корневого .env при запуске из backend."""
    subprocess_environment = _build_subprocess_environment()
    result = _run_python_script(
        "from app.config import Settings; Settings()",
        BACKEND_WORKING_DIRECTORY,
        subprocess_environment,
    )
    assert result.returncode == 0, result.stderr


def test_import_app_main_works_without_backend_package_in_sys_path() -> None:
    """import app.main должен работать как в uvicorn app.main:app --reload."""
    subprocess_environment = _build_subprocess_environment()
    result = _run_python_script(
        "import app.main",
        BACKEND_WORKING_DIRECTORY,
        subprocess_environment,
    )
    assert result.returncode == 0, result.stderr


def test_settings_ignores_backend_env_when_root_env_exists() -> None:
    """При наличии backend/.env должен использоваться только корневой .env."""
    fake_backend_token = "backend-local-env-must-be-ignored"
    backend_env_content = "\n".join(
        [
            "DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/backend_local",
            f"TELEGRAM_BOT_TOKEN={fake_backend_token}",
            "OPENAI_API_KEY=sk-backend-local-key",
            "",
        ]
    )
    original_backend_env_content = (
        BACKEND_ENV_FILE_PATH.read_text("utf-8")
        if BACKEND_ENV_FILE_PATH.exists()
        else None
    )
    BACKEND_ENV_FILE_PATH.write_text(backend_env_content, "utf-8")
    try:
        subprocess_environment = _build_subprocess_environment()
        result = _run_python_script(
            (
                "from app.config import Settings; "
                "print(Settings().TELEGRAM_BOT_TOKEN == "
                f"'{fake_backend_token}')"
            ),
            BACKEND_WORKING_DIRECTORY,
            subprocess_environment,
        )
    finally:
        if original_backend_env_content is None:
            BACKEND_ENV_FILE_PATH.unlink(missing_ok=True)
        else:
            BACKEND_ENV_FILE_PATH.write_text(original_backend_env_content, "utf-8")

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "False"


def test_fastapi_registers_openai_callback_route() -> None:
    """FastAPI app должен содержать маршрут /api/auth/openai/callback."""
    main_module = importlib.import_module("app.main")
    fastapi_app = main_module.app

    route_paths = {route.path for route in fastapi_app.routes if hasattr(route, "path")}
    assert "/api/auth/openai/callback" in route_paths


async def test_openai_callback_endpoint_is_not_404() -> None:
    """GET /api/auth/openai/callback не должен возвращать 404."""
    main_module = importlib.import_module("app.main")
    fastapi_app = main_module.app

    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/auth/openai/callback")

    assert response.status_code != 404
