"""Регрессионные тесты runtime-путей запуска backend.

Проверяет три инварианта:
1) Settings выбирает env-файл в корне по правилу `.env.{APP_ENV}` с fallback `.env`.
2) локальный `backend/.env` игнорируется.
3) `import app.main` работает при запуске из каталога backend.
"""

from __future__ import annotations

import importlib
import os
import subprocess
import sys
from pathlib import Path

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


def _expected_root_env_file_path(app_env: str) -> str | None:
    """Возвращает ожидаемый env-файл в корне по контракту 002-dev-environment."""
    env_specific_file_path = PROJECT_ROOT_DIRECTORY / f".env.{app_env}"
    if env_specific_file_path.is_file():
        return str(env_specific_file_path)
    if ROOT_ENV_FILE_PATH.is_file():
        return str(ROOT_ENV_FILE_PATH)
    return None


def test_settings_uses_only_single_root_env_file_path() -> None:
    """Settings выбирает env-файл динамически.

    Контракт: model_config не должен фиксировать абсолютный путь env-файла.
    """
    settings_module = importlib.import_module("app.config")
    settings_class = settings_module.Settings

    assert settings_class.model_config["env_file"] is None

    resolve_env_file_script_text = (
        "from app.config import _resolve_env_file; print(_resolve_env_file())"
    )
    base_subprocess_environment = _build_subprocess_environment()

    for app_env in ("dev", "prod"):
        subprocess_environment = base_subprocess_environment.copy()
        subprocess_environment["APP_ENV"] = app_env
        result = _run_python_script(
            resolve_env_file_script_text,
            BACKEND_WORKING_DIRECTORY,
            subprocess_environment,
        )

        assert result.returncode == 0, result.stderr
        actual_env_file_path = result.stdout.strip()
        normalized_actual_env_file_path = (
            None if actual_env_file_path == "None" else actual_env_file_path
        )
        expected_root_env_file_path = _expected_root_env_file_path(app_env)

        assert normalized_actual_env_file_path == expected_root_env_file_path
        assert normalized_actual_env_file_path != str(BACKEND_ENV_FILE_PATH)


def test_settings_loads_root_env_when_cwd_is_backend() -> None:
    """Settings должен загружаться из корневых env-файлов при запуске из backend."""
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
    """При наличии backend/.env должны использоваться только корневые env-файлы."""
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
