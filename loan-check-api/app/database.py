"""Настройка подключения к PostgreSQL через SQLAlchemy."""
from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    """Базовый класс для всех ORM-моделей."""


engine = create_engine(
    settings.sqlalchemy_database_url,
    pool_pre_ping=True,
    echo=settings.app_debug,
)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def get_db() -> Generator[Session, None, None]:
    """Зависимость FastAPI: выдаёт сессию БД и гарантированно закрывает её."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
