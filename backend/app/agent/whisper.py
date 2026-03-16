"""
Транскрипция голосовых сообщений через OpenAI Whisper.

Скачивает OGG-файл из Telegram, конвертирует в MP3 через pydub,
отправляет в OpenAI Whisper API и возвращает текст.
"""

from __future__ import annotations

import io
import logging
from typing import BinaryIO

from aiogram import Bot
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

# Модель для транскрипции голосовых сообщений
_WHISPER_MODEL = "gpt-4o-mini-transcribe"


async def get_whisper_client() -> AsyncOpenAI:
    """Возвращает AsyncOpenAI клиент для Whisper API.

    Использует API key из конфигурации.

    Возвращает:
        AsyncOpenAI: клиент для Whisper API
    """
    from backend.app.config import Settings

    settings = Settings()
    return AsyncOpenAI(api_key=settings.OPENAI_API_KEY)


async def transcribe_voice(
    bot: Bot,
    voice_file_id: str,
) -> str:
    """Транскрибирует голосовое сообщение из Telegram через OpenAI Whisper.

    Скачивает OGG-файл через Telegram Bot API, отправляет
    в OpenAI Whisper и возвращает распознанный текст.

    Аргументы:
        bot: экземпляр Telegram бота для скачивания файлов
        voice_file_id: ID файла в Telegram

    Возвращает:
        str: текст транскрипции
    """
    audio_file = await _download_voice_file(bot, voice_file_id)
    client = await get_whisper_client()
    return await _transcribe_audio(client, audio_file)


async def _download_voice_file(
    bot: Bot,
    voice_file_id: str,
) -> BinaryIO:
    """Скачивает голосовой файл из Telegram.

    Аргументы:
        bot: экземпляр Telegram бота
        voice_file_id: ID файла в Telegram

    Возвращает:
        BinaryIO: поток аудиофайла, готовый к отправке в OpenAI
    """
    file = await bot.get_file(voice_file_id)
    downloaded_audio = await bot.download_file(file.file_path)
    audio_file = _normalize_downloaded_audio(downloaded_audio)
    return _prepare_audio_file_for_openai(audio_file)


def _normalize_downloaded_audio(downloaded_audio: bytes | BinaryIO) -> BinaryIO:
    """Нормализует результат bot.download_file к BinaryIO."""
    if isinstance(downloaded_audio, bytes | bytearray):
        return io.BytesIO(bytes(downloaded_audio))

    if hasattr(downloaded_audio, "read"):
        return downloaded_audio

    raise TypeError("bot.download_file() должен вернуть bytes или BinaryIO")


def _prepare_audio_file_for_openai(audio_file: BinaryIO) -> BinaryIO:
    """Подготавливает поток к передаче в OpenAI."""
    _ensure_audio_file_name(audio_file)
    _rewind_audio_file(audio_file)
    return audio_file


def _ensure_audio_file_name(audio_file: BinaryIO) -> None:
    """Гарантирует наличие имени файла для OpenAI multipart upload."""
    if getattr(audio_file, "name", None):
        return
    audio_file.name = "voice.ogg"


def _rewind_audio_file(audio_file: BinaryIO) -> None:
    """Перематывает поток в начало перед отправкой в OpenAI."""
    seek_method = getattr(audio_file, "seek", None)
    if seek_method is None:
        return
    seek_method(0)


async def _transcribe_audio(
    client: AsyncOpenAI,
    audio_file: BinaryIO,
) -> str:
    """Отправляет аудио в OpenAI Whisper и возвращает текст.

    Аргументы:
        client: AsyncOpenAI клиент
        audio_file: поток аудиофайла

    Возвращает:
        str: распознанный текст
    """
    transcription = await client.audio.transcriptions.create(
        model=_WHISPER_MODEL,
        file=audio_file,
    )
    return transcription.text
