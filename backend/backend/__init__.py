"""Совместимость импортов backend.app.* при запуске из каталога backend.

Когда рабочая директория — `backend/`, Python видит пакет `backend`
из `backend/backend/__init__.py`. Этот модуль расширяет `__path__`,
чтобы подпакеты (`backend.app`, `backend.alembic` и т.д.) искались также
в родительском каталоге `backend/`.
"""

from pathlib import Path

_PACKAGE_DIRECTORY = Path(__file__).resolve().parent
_BACKEND_ROOT_DIRECTORY = _PACKAGE_DIRECTORY.parent

if str(_BACKEND_ROOT_DIRECTORY) not in __path__:
    __path__.append(str(_BACKEND_ROOT_DIRECTORY))
