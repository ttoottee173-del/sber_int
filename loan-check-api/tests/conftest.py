"""Общие фикстуры pytest.

Тесты запускаются на SQLite в памяти (чтобы не требовать запущенный
PostgreSQL при unit-тестировании логики). Эндпоинт-тесты используют
TestClient FastAPI с подменой БД на in-memory SQLite.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# ВАЖНО: подменяем DATABASE_URL ДО импорта любых модулей приложения.
# Внешнее окружение может содержать DATABASE_URL, конфликтующий с тестовым.
# Используем явное присваивание (не setdefault), чтобы гарантированно перекрыть.
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["UPLOAD_DIR"] = "/tmp/loan_check_test_uploads"

# Также подменяем настройки, которые могут прийти из окружения.
os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("POSTGRES_USER", "test")
os.environ.setdefault("POSTGRES_PASSWORD", "test")
os.environ.setdefault("POSTGRES_DB", "test")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Добавляем корень проекта в sys.path, чтобы `import app` работал из любого места.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.services import file_storage  # noqa: E402


# ---------- In-memory SQLite для тестов ----------


@pytest.fixture()
def test_db():
    """Создать свежую in-memory SQLite БД со всеми таблицами."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)

    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def client(test_db):
    """TestClient FastAPI с подменённой зависимостью get_db."""

    def _override_get_db():
        try:
            yield test_db
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _tmp_upload_dir(tmp_path, monkeypatch):
    """Перенаправить хранилище файлов во временную папку теста."""
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)

    # Меняем поле upload_dir (НЕ property upload_path — у него нет сеттера).
    # settings — синглтон, его импортируют и file_storage, и check_service.
    monkeypatch.setattr(file_storage.settings, "upload_dir", str(upload_dir))

    # Также меняем base_dir уже созданного глобального storage.
    monkeypatch.setattr(file_storage.storage, "base_dir", upload_dir)

    yield
