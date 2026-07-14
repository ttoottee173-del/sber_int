"""Точка входа FastAPI приложения.

Запуск:
    uvicorn app.main:app --reload
или
    docker compose up
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import settings
from app.database import Base, engine
from app.routers import checks

logging.basicConfig(
    level=logging.DEBUG if settings.app_debug else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Жизненный цикл приложения.

    На старте:
        - создаём папку uploads/ (если её нет),
        - в dev-режиме автоматически создаём таблицы (чтобы можно было
          запускать без Alembic). В проде ВСЕГДА используем Alembic миграции
          (см. README → «Запуск»).
    """
    settings.upload_path.mkdir(parents=True, exist_ok=True)

    if settings.app_debug:
        logger.warning("DEBUG mode: creating tables via Base.metadata.create_all(). "
                       "В проде используйте Alembic.")
        Base.metadata.create_all(bind=engine)

    yield


app = FastAPI(
    title="Loan Check API",
    description="REST API сервиса проверки пакетов документов для льготных кредитов.",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(checks.router)


@app.get("/health", tags=["system"], summary="Проверка живости сервиса")
def health() -> dict:
    """Простой healthcheck для docker-compose."""
    return {"status": "ok"}


@app.get("/", tags=["system"], summary="Корневой эндпоинт")
def root() -> dict:
    return {
        "service": "Loan Check API",
        "docs": "/docs",
        "redoc": "/redoc",
        "health": "/health",
    }
