"""Конфигурация приложения через переменные окружения."""
from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Настройки приложения.

    Значения подгружаются из файла .env (если есть) и/или переменных окружения.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Приложение
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_debug: bool = False

    # База данных
    postgres_user: str = "loan_check"
    postgres_password: str = "loan_check_pass"
    postgres_db: str = "loan_check_db"
    postgres_host: str = "db"
    postgres_port: int = 5432
    database_url: str | None = None

    # Хранилище файлов
    upload_dir: str = "/app/uploads"

    # Лимиты проверки документов
    max_file_size_mb: int = 20
    allowed_extensions: str = "pdf,docx,jpg,jpeg,png"

    @property
    def sqlalchemy_database_url(self) -> str:
        """Полная строка подключения к PostgreSQL для SQLAlchemy."""
        if self.database_url:
            return self.database_url
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def allowed_ext_list(self) -> list[str]:
        """Список допустимых расширений файлов в нижнем регистре."""
        return [e.strip().lower() for e in self.allowed_extensions.split(",") if e.strip()]

    @property
    def upload_path(self) -> Path:
        """Path-объект для папки загрузок."""
        return Path(self.upload_dir)


settings = Settings()
