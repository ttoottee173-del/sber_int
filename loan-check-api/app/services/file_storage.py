"""Сохранение загруженных файлов в локальную папку.

Каждый файл сохраняется в подпапку вида uploads/<check_id>/<filename>.
Путь к файлу возвращается и сохраняется в БД (поле documents.storage_path).
"""
from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import BinaryIO

from app.config import settings

logger = logging.getLogger(__name__)


class FileStorage:
    """Локальное файловое хранилище."""

    def __init__(self, base_dir: str | Path | None = None) -> None:
        self.base_dir = Path(base_dir) if base_dir else settings.upload_path

    def ensure_root(self) -> None:
        """Создать корневую папку хранилища, если её нет."""
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def save_file(self, check_id: str, filename: str, content: BinaryIO) -> Path:
        """Сохранить один файл.

        Args:
            check_id: идентификатор проверки (используется как подпапка).
            filename: исходное имя файла.
            content: бинарный поток с содержимым файла.

        Returns:
            Полный путь к сохранённому файлу.
        """
        self.ensure_root()
        target_dir = self.base_dir / check_id
        target_dir.mkdir(parents=True, exist_ok=True)

        # Защита от выхода за пределы папки (если имя содержит ../).
        safe_name = Path(filename).name
        target_path = target_dir / safe_name

        with open(target_path, "wb") as f:
            shutil.copyfileobj(content, f)

        logger.debug("Saved file %s -> %s", filename, target_path)
        return target_path

    def cleanup_check(self, check_id: str) -> None:
        """Удалить все файлы, связанные с проверкой (best-effort)."""
        target_dir = self.base_dir / check_id
        if target_dir.exists():
            shutil.rmtree(target_dir, ignore_errors=True)


# Глобальный экземпляр — можно переопределить в тестах.
storage = FileStorage()
