"""Конфигурация Alembic — подключение к БД и метаданные моделей."""
from __future__ import annotations

import logging
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.config import settings
from app.database import Base
from app import models  # noqa: F401  — нужно, чтобы модели зарегистрировались в Base.metadata

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Подставляем URL из настроек приложения.
config.set_main_option("sqlalchemy.url", settings.sqlalchemy_database_url)

logger = logging.getLogger("alembic.env")

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Запуск миграций в оффлайн-режиме (генерация SQL-скрипта)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Запуск миграций в онлайн-режиме (прямое подключение к БД)."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
